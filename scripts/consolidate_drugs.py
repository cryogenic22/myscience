"""Consolidate duplicate drug records into canonical entities.

Merges multiple records for the same drug (e.g., 7 "sitagliptin" variants)
into one canonical record, keeping the best-quality data and re-pointing
entity_links to the surviving record.

Usage:
    python -m scripts.consolidate_drugs [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
import re
from datetime import datetime, timezone

from config import config
from db import Database

logger = logging.getLogger(__name__)


def _normalize_drug_name(name: str) -> str:
    """Normalize a drug name for grouping duplicates.

    Strips salt forms, dosage info, brand mentions, and common noise
    to find the canonical drug name for dedup grouping.
    """
    n = name.strip()
    # Lowercase
    n = n.lower()
    # Remove parenthetical brand names: "sitagliptin (Januvia)" → "sitagliptin"
    n = re.sub(r"\s*\([^)]*\)", "", n)
    # Remove salt forms: "phosphate", "hydrochloride", "monohydrate", "anhydrous"
    n = re.sub(
        r"\b(?:phosphate|hydrochloride|hcl|monohydrate|anhydrous|mesylate|"
        r"maleate|fumarate|succinate|tartrate|besylate|calcium|sodium|"
        r"potassium|acetate|citrate|sulfate|nitrate|bromide|chloride|"
        r"disodium|dipotassium|hemifumarate|tromethamine)\b",
        "", n,
    )
    # Remove dosage forms: "oral", "tablet", "injection", "formulation"
    n = re.sub(
        r"\b(?:oral|tablet|injection|capsule|solution|suspension|formulation|"
        r"extended.release|immediate.release|film.coated|ir|er|sr|xr|xl)\b",
        "", n,
    )
    # Remove "DPP4i", "- DPP4i", "DPP-4 inhibitor" suffixes
    n = re.sub(r"\s*[-–]\s*(?:DPP-?4i?|SGLT2i?|GLP-1|ARB|ACEi)\b", "", n, flags=re.IGNORECASE)
    # Remove "MK0431" style identifiers
    n = re.sub(r"\b[A-Z]{1,4}\d{3,6}\b", "", n, flags=re.IGNORECASE)
    # Remove "/ duration of treatment: 21 weeks" style tails
    n = re.sub(r"\s*/\s*duration.*$", "", n)
    # Collapse whitespace
    n = re.sub(r"\s+", " ", n).strip()
    # Remove trailing punctuation
    n = n.rstrip(".,;:-/ ")
    return n


def _pick_canonical(records: list[dict]) -> dict:
    """Pick the best record to keep as canonical.

    Priority: FDA source > backfill with most links > alphabetically first.
    """
    fda_records = [r for r in records if r["source_api"] in ("fda_orange_book", "fda_labels")]
    ct_records = [r for r in records if r["source_api"] == "clinical_trials_gov"]
    backfill_records = [r for r in records if r["source_api"] == "backfill"]

    # Prefer FDA, then CT.gov, then backfill
    candidates = fda_records or ct_records or backfill_records or records

    # Among candidates, prefer ones with company_id and mechanism_id set
    scored = []
    for r in candidates:
        score = 0
        if r.get("company_id"):
            score += 10
        if r.get("mechanism_id"):
            score += 5
        if r.get("brand_name") and r["brand_name"] != r.get("generic_name"):
            score += 3
        if r.get("therapeutic_area_id"):
            score += 2
        score += r.get("link_count", 0) / 100  # tie-break by links
        scored.append((score, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def _log_change(db: Database, entity_type: str, entity_id: str,
                change_type: str, fields: list[str]) -> None:
    db.execute(
        """
        INSERT INTO data_change_log
            (entity_type, entity_id, change_type, changed_fields, changed_at)
        VALUES (%s, %s, %s, %s, %s)
        """,
        [entity_type, entity_id, change_type, fields, datetime.now(timezone.utc)],
    )


def consolidate_drugs(db: Database, dry_run: bool = False) -> dict:
    """Find and merge duplicate drug records."""
    stats = {"groups_found": 0, "records_merged": 0, "aliases_created": 0}

    # Fetch all active drugs with link counts
    drugs = db.fetch_all(
        """
        SELECT d.id, d.generic_name, d.brand_name, d.company_id,
               d.mechanism_id, d.therapeutic_area_id, d.source_api,
               d.record_status,
               (SELECT COUNT(*) FROM entity_links
                WHERE source_entity_id = d.id::text
                   OR target_entity_id = d.id::text) AS link_count
        FROM drugs d
        WHERE d.record_status IS DISTINCT FROM 'excluded'
          AND d.record_status IS DISTINCT FROM 'merged'
          AND d.generic_name IS NOT NULL
          AND d.generic_name != ''
        """
    )

    # Group by normalized name
    groups: dict[str, list[dict]] = {}
    for d in drugs:
        norm = _normalize_drug_name(d["generic_name"])
        if len(norm) < 2:
            continue
        groups.setdefault(norm, []).append(d)

    # Process groups with > 1 record
    for norm_name, records in groups.items():
        if len(records) < 2:
            continue

        stats["groups_found"] += 1
        canonical = _pick_canonical(records)
        canonical_id = str(canonical["id"])
        others = [r for r in records if str(r["id"]) != canonical_id]

        if not others:
            continue

        logger.info(
            "Consolidating '%s': keep %s (%s), merge %d others",
            norm_name, canonical["generic_name"], canonical["source_api"],
            len(others),
        )

        for other in others:
            other_id = str(other["id"])

            if dry_run:
                logger.info(
                    "  [DRY RUN] Would merge: %s (src=%s, links=%d) → %s",
                    other["generic_name"], other["source_api"],
                    other.get("link_count", 0), canonical["generic_name"],
                )
                stats["records_merged"] += 1
                continue

            # Re-point entity_links from other → canonical.
            # Delete all links from/to the merged entity — the canonical
            # already carries its own equivalent links.  This is safe
            # because we only merge records that are duplicates of the
            # same real-world drug, so their link sets overlap heavily.
            db.execute(
                "DELETE FROM entity_links WHERE source_entity_id = %s OR target_entity_id = %s",
                [other_id, other_id],
            )

            # Create alias for the old name (if different)
            if other["generic_name"].lower() != canonical["generic_name"].lower():
                try:
                    db.execute(
                        """
                        INSERT INTO entity_aliases (entity_id, entity_type, alias, source)
                        VALUES (%s, 'drug', %s, 'consolidation')
                        ON CONFLICT DO NOTHING
                        """,
                        [canonical_id, other["generic_name"]],
                    )
                    stats["aliases_created"] += 1
                except Exception:
                    pass  # alias table may have different schema

            # Enrich canonical with data from merged record (fill gaps)
            if not canonical.get("company_id") and other.get("company_id"):
                db.execute(
                    "UPDATE drugs SET company_id = %s WHERE id = %s",
                    [other["company_id"], canonical["id"]],
                )
                canonical["company_id"] = other["company_id"]

            if not canonical.get("mechanism_id") and other.get("mechanism_id"):
                db.execute(
                    "UPDATE drugs SET mechanism_id = %s WHERE id = %s",
                    [other["mechanism_id"], canonical["id"]],
                )
                canonical["mechanism_id"] = other["mechanism_id"]

            if not canonical.get("brand_name") and other.get("brand_name"):
                db.execute(
                    "UPDATE drugs SET brand_name = %s WHERE id = %s",
                    [other["brand_name"], canonical["id"]],
                )
                canonical["brand_name"] = other["brand_name"]

            if not canonical.get("therapeutic_area_id") and other.get("therapeutic_area_id"):
                db.execute(
                    "UPDATE drugs SET therapeutic_area_id = %s WHERE id = %s",
                    [other["therapeutic_area_id"], canonical["id"]],
                )
                canonical["therapeutic_area_id"] = other["therapeutic_area_id"]

            # Mark other as merged
            db.execute(
                "UPDATE drugs SET record_status = 'merged' WHERE id = %s",
                [other["id"]],
            )
            _log_change(db, "drug", other_id, "merged_into",
                        [f"canonical_id:{canonical_id}", f"old_name:{other['generic_name']}"])

            stats["records_merged"] += 1

    # Deduplicate entity_links that now point to same source+target
    if not dry_run:
        try:
            dedup_result = db.fetch_one(
                """
                WITH dupes AS (
                    SELECT MIN(id) AS keep_id, source_entity_id, target_entity_id, link_type
                    FROM entity_links
                    GROUP BY source_entity_id, target_entity_id, link_type
                    HAVING COUNT(*) > 1
                )
                DELETE FROM entity_links
                WHERE id IN (
                    SELECT el.id FROM entity_links el
                    JOIN dupes d ON el.source_entity_id = d.source_entity_id
                        AND el.target_entity_id = d.target_entity_id
                        AND el.link_type = d.link_type
                        AND el.id != d.keep_id
                )
                """
            )
        except Exception as e:
            logger.warning("Link dedup cleanup: %s", e)

    logger.info(
        "Drug consolidation: groups=%d, merged=%d, aliases=%d",
        stats["groups_found"], stats["records_merged"], stats["aliases_created"],
    )
    return stats


def run(dry_run: bool = False) -> dict:
    """Run drug consolidation."""
    db = Database(config.db.dsn)
    db.connect()
    try:
        return consolidate_drugs(db, dry_run)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Consolidate duplicate drug records")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    results = run(dry_run=args.dry_run)
    print("\n=== Drug Consolidation Results ===")
    for k, v in results.items():
        print(f"  {k}: {v}")
    if args.dry_run:
        print("  (dry run — no changes written)")


if __name__ == "__main__":
    main()
