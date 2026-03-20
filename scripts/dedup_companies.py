"""Deduplicate companies.

Phase 1.2: Merge duplicate companies (Pfizer Inc / PFIZER, Lupin / Lupin Ltd, etc.),
create aliases for merged names, and exclude misclassified entities.

Usage:
    python -m scripts.dedup_companies [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
import re
from datetime import datetime, timezone

from config import config
from db import Database

logger = logging.getLogger(__name__)

# Suffixes to strip for normalization
COMPANY_SUFFIXES = re.compile(
    r"\b(?:inc\.?|ltd\.?|llc\.?|corp\.?|corporation|company|co\.?"
    r"|plc\.?|ag\.?|sa\.?|se\.?|nv\.?|bv\.?"
    r"|pharms?\.?|pharmaceuticals?|laboratories?|labs?"
    r"|usa|u\.s\.a\.?|intl?\.?|international"
    r"|group|holdings?|limited|gmbh"
    r")\.?\s*$",
    re.IGNORECASE,
)

# Known entities that are NOT companies (hospitals, universities, etc.)
NON_COMPANY_PATTERNS = [
    re.compile(r"\buniversity\b", re.IGNORECASE),
    re.compile(r"\bhospital\b", re.IGNORECASE),
    re.compile(r"\bmedical\s+center\b", re.IGNORECASE),
    re.compile(r"\bclinic\b", re.IGNORECASE),
    re.compile(r"\binstitute\b", re.IGNORECASE),
    re.compile(r"\bresearch\s+center\b", re.IGNORECASE),
    re.compile(r"\bfoundation\b", re.IGNORECASE),
    re.compile(r"\bgovernment\b", re.IGNORECASE),
    re.compile(r"\bministry\b", re.IGNORECASE),
    re.compile(r"\bnational\s+institutes?\b", re.IGNORECASE),
    re.compile(r"\bVA\s+health\b", re.IGNORECASE),
]


def normalize_company_name(name: str) -> str:
    """Normalize company name for dedup matching."""
    name = name.strip()
    # Remove suffixes iteratively (handles "Pfizer Inc Corp")
    for _ in range(3):
        name = COMPANY_SUFFIXES.sub("", name).strip()
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name)
    return name.lower().strip()


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


def _is_non_company(name: str) -> bool:
    """Return True if name looks like a non-company entity."""
    return any(p.search(name) for p in NON_COMPANY_PATTERNS)


def _count_links(db: Database, entity_id: str) -> int:
    """Count entity_links for a given entity."""
    row = db.fetch_one(
        """
        SELECT COUNT(*) AS cnt FROM entity_links
        WHERE source_entity_id = %s OR target_entity_id = %s
        """,
        [entity_id, entity_id],
    )
    return row["cnt"] if row else 0


def _create_alias(db: Database, entity_type: str, entity_id: str,
                  alias_text: str, source_type: str = "dedup") -> None:
    """Create an entity alias if it doesn't exist."""
    db.execute(
        """
        INSERT INTO entity_aliases (entity_type, entity_id, alias_text, source_type, confidence, verified)
        VALUES (%s, %s::uuid, %s, %s, 1.0, true)
        ON CONFLICT DO NOTHING
        """,
        [entity_type, entity_id, alias_text, source_type],
    )


def _merge_links(db: Database, from_id: str, to_id: str) -> int:
    """Transfer entity_links from one entity to another."""
    merged = 0

    # Source side
    links = db.fetch_all(
        """
        SELECT id, source_entity_id, source_entity_type,
               target_entity_id, target_entity_type, link_type
        FROM entity_links
        WHERE source_entity_id = %s AND source_entity_type = 'company'
        """,
        [from_id],
    )
    for link in links:
        # Check if target link already exists
        existing = db.fetch_one(
            """
            SELECT 1 FROM entity_links
            WHERE source_entity_id = %s AND source_entity_type = %s
              AND target_entity_id = %s AND target_entity_type = %s
              AND link_type = %s
            """,
            [to_id, link["source_entity_type"],
             link["target_entity_id"], link["target_entity_type"],
             link["link_type"]],
        )
        if not existing:
            db.execute(
                "UPDATE entity_links SET source_entity_id = %s WHERE id = %s",
                [to_id, link["id"]],
            )
            merged += 1
        else:
            db.execute("DELETE FROM entity_links WHERE id = %s", [link["id"]])

    # Target side
    links = db.fetch_all(
        """
        SELECT id, source_entity_id, source_entity_type,
               target_entity_id, target_entity_type, link_type
        FROM entity_links
        WHERE target_entity_id = %s AND target_entity_type = 'company'
        """,
        [from_id],
    )
    for link in links:
        existing = db.fetch_one(
            """
            SELECT 1 FROM entity_links
            WHERE source_entity_id = %s AND source_entity_type = %s
              AND target_entity_id = %s AND target_entity_type = %s
              AND link_type = %s
            """,
            [link["source_entity_id"], link["source_entity_type"],
             to_id, link["target_entity_type"],
             link["link_type"]],
        )
        if not existing:
            db.execute(
                "UPDATE entity_links SET target_entity_id = %s WHERE id = %s",
                [to_id, link["id"]],
            )
            merged += 1
        else:
            db.execute("DELETE FROM entity_links WHERE id = %s", [link["id"]])

    # Also update drugs.company_id FK
    db.execute(
        "UPDATE drugs SET company_id = %s::uuid WHERE company_id = %s::uuid",
        [to_id, from_id],
    )

    return merged


def dedup_companies(db: Database, dry_run: bool = False) -> dict[str, int]:
    """Find and merge duplicate companies."""
    stats = {"groups_found": 0, "merged": 0, "excluded": 0, "links_transferred": 0}

    companies = db.fetch_all(
        """
        SELECT id, name, ticker, cik, record_status
        FROM companies
        WHERE record_status IS DISTINCT FROM 'merged'
          AND record_status IS DISTINCT FROM 'excluded'
        """
    )

    # Group by normalized name
    groups: dict[str, list[dict]] = {}
    for c in companies:
        norm = normalize_company_name(c["name"])
        if not norm:
            continue
        groups.setdefault(norm, []).append(c)

    # Process groups with duplicates
    for norm_name, members in groups.items():
        if len(members) < 2:
            continue

        stats["groups_found"] += 1

        # Pick the "canonical" entry — prefer one with most links, then ticker, then CIK
        scored = []
        for m in members:
            link_count = _count_links(db, str(m["id"]))
            has_ticker = 1 if m.get("ticker") else 0
            has_cik = 1 if m.get("cik") else 0
            scored.append((link_count, has_ticker, has_cik, m))

        scored.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
        canonical = scored[0][3]
        canonical_id = str(canonical["id"])
        duplicates = [s[3] for s in scored[1:]]

        for dup in duplicates:
            dup_id = str(dup["id"])
            if dry_run:
                logger.info(
                    "[DRY RUN] Merge company %r (id=%s) → %r (id=%s)",
                    dup["name"], dup_id, canonical["name"], canonical_id,
                )
            else:
                # Transfer links
                links_moved = _merge_links(db, dup_id, canonical_id)
                stats["links_transferred"] += links_moved

                # Create alias
                _create_alias(db, "company", canonical_id, dup["name"])

                # Copy enrichment fields if canonical is missing them
                if not canonical.get("ticker") and dup.get("ticker"):
                    db.execute(
                        "UPDATE companies SET ticker = %s WHERE id = %s",
                        [dup["ticker"], canonical["id"]],
                    )
                if not canonical.get("cik") and dup.get("cik"):
                    db.execute(
                        "UPDATE companies SET cik = %s WHERE id = %s",
                        [dup["cik"], canonical["id"]],
                    )

                # Mark duplicate
                db.execute(
                    "UPDATE companies SET record_status = 'merged' WHERE id = %s",
                    [dup["id"]],
                )
                _log_change(db, "company", dup_id, "merged_duplicate",
                            [f"merged_into:{canonical_id}", f"name:{dup['name']}"])

            stats["merged"] += 1

    logger.info(
        "Company dedup: groups=%d, merged=%d, links_transferred=%d",
        stats["groups_found"], stats["merged"], stats["links_transferred"],
    )
    return stats


def exclude_non_companies(db: Database, dry_run: bool = False) -> int:
    """Mark non-company entities (hospitals, universities) as excluded."""
    companies = db.fetch_all(
        """
        SELECT id, name FROM companies
        WHERE record_status IS DISTINCT FROM 'excluded'
          AND record_status IS DISTINCT FROM 'merged'
        """
    )

    excluded = 0
    for c in companies:
        if _is_non_company(c["name"]):
            if dry_run:
                logger.info("[DRY RUN] Exclude non-company: %s (id=%s)", c["name"], c["id"])
            else:
                db.execute(
                    "UPDATE companies SET record_status = 'excluded' WHERE id = %s",
                    [c["id"]],
                )
                _log_change(db, "company", str(c["id"]), "exclude_non_company",
                            [f"name:{c['name']}"])
            excluded += 1

    logger.info("Non-companies excluded: %d", excluded)
    return excluded


def run(dry_run: bool = False) -> dict:
    """Run all company dedup tasks."""
    db = Database(config.db.dsn)
    db.connect()

    try:
        excluded = exclude_non_companies(db, dry_run)
        dedup_stats = dedup_companies(db, dry_run)
        return {
            **dedup_stats,
            "non_companies_excluded": excluded,
        }
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Deduplicate companies")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    results = run(dry_run=args.dry_run)
    print("\n=== Company Dedup Results ===")
    for k, v in results.items():
        print(f"  {k}: {v}")
    if args.dry_run:
        print("  (dry run — no changes written)")


if __name__ == "__main__":
    main()
