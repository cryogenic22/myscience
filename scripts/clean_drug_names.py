"""Clean drug names and resolve unknown entity types.

Phase 1.3 + 1.7: Remove dosage patterns from drug names, exclude
placebo/study drug entries, and resolve 'unknown' entity types in
entity_links.

Usage:
    python -m scripts.clean_drug_names [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
import re
from datetime import datetime, timezone

from config import config
from db import Database

logger = logging.getLogger(__name__)

# Patterns that indicate a raw intervention string, not a real drug name
DOSAGE_PATTERN = re.compile(
    r"\d+\s*(?:mg|ml|units?|mcg|µg|iu|g/d|mg/d|cc|mmol|meq|%)",
    re.IGNORECASE,
)

EXCLUDE_PATTERNS = [
    re.compile(r"^placebo", re.IGNORECASE),
    re.compile(r"^study\s+drug", re.IGNORECASE),
    re.compile(r"^investigational", re.IGNORECASE),
    re.compile(r"^anti-", re.IGNORECASE),
    re.compile(r"^standard\s+(of\s+)?care", re.IGNORECASE),
    re.compile(r"^usual\s+care", re.IGNORECASE),
    re.compile(r"^comparator", re.IGNORECASE),
    re.compile(r"^matching\s+placebo", re.IGNORECASE),
    re.compile(r"^sham\b", re.IGNORECASE),
    re.compile(r"^no\s+intervention", re.IGNORECASE),
    re.compile(r"^dietary\s+supplement", re.IGNORECASE),
    re.compile(r"^behavioral", re.IGNORECASE),
    re.compile(r"^lifestyle", re.IGNORECASE),
    re.compile(r"^device:", re.IGNORECASE),
    re.compile(r"^procedure:", re.IGNORECASE),
]

# Regex to extract a likely drug name from an intervention string
# e.g., "0.5 units/kg daily insulin glargine" → "insulin glargine"
DRUG_EXTRACT_PATTERNS = [
    # "dose drug_name" pattern
    re.compile(
        r"(?:\d[\d.]*\s*(?:mg|ml|units?|mcg|µg|iu)\s*(?:/\s*\w+\s*)?(?:daily|weekly|once|twice|bid|tid|qd)?\s*)"
        r"(.+)",
        re.IGNORECASE,
    ),
    # "drug_name dose" pattern
    re.compile(
        r"^([a-zA-Z][a-zA-Z\s/-]+?)\s+\d[\d.]*\s*(?:mg|ml|units?|mcg|µg|iu)",
        re.IGNORECASE,
    ),
]


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


def _extract_drug_name(raw: str) -> str | None:
    """Try to extract a clean drug name from a raw intervention string."""
    for pattern in DRUG_EXTRACT_PATTERNS:
        m = pattern.match(raw.strip())
        if m:
            name = m.group(1).strip().rstrip(".,;:")
            # Must be at least 3 chars and look like a word
            if len(name) >= 3 and re.match(r"^[a-zA-Z]", name):
                return name
    return None


def _should_exclude(name: str) -> bool:
    """Return True if the drug name matches an exclude pattern."""
    return any(p.match(name) for p in EXCLUDE_PATTERNS)


def clean_drug_names(db: Database, dry_run: bool = False) -> dict[str, int]:
    """Clean drug names: fix dosage patterns, exclude non-drugs."""
    stats = {"cleaned": 0, "excluded": 0, "skipped": 0}

    # Find drugs with dosage patterns in their names
    drugs = db.fetch_all(
        """
        SELECT id, generic_name, brand_name, source_api, record_status
        FROM drugs
        WHERE record_status IS DISTINCT FROM 'excluded'
          AND record_status IS DISTINCT FROM 'merged'
        """
    )

    for drug in drugs:
        name = drug.get("generic_name") or ""
        drug_id = str(drug["id"])

        # Check for exclusion patterns first
        if _should_exclude(name):
            if dry_run:
                logger.info("[DRY RUN] Exclude: %s (id=%s)", name, drug_id)
            else:
                db.execute(
                    "UPDATE drugs SET record_status = 'excluded' WHERE id = %s",
                    [drug["id"]],
                )
                _log_change(db, "drug", drug_id, "exclude_non_drug",
                            ["record_status", f"reason:exclude_pattern:{name}"])
            stats["excluded"] += 1
            continue

        # Check for dosage patterns
        if DOSAGE_PATTERN.search(name):
            extracted = _extract_drug_name(name)
            if extracted and extracted.lower() != name.lower():
                if dry_run:
                    logger.info(
                        "[DRY RUN] Clean: %r → %r (id=%s)",
                        name, extracted, drug_id,
                    )
                else:
                    db.execute(
                        "UPDATE drugs SET generic_name = %s WHERE id = %s",
                        [extracted, drug["id"]],
                    )
                    _log_change(db, "drug", drug_id, "clean_drug_name",
                                ["generic_name", f"old:{name}", f"new:{extracted}"])
                stats["cleaned"] += 1
            else:
                # Can't extract — exclude if it looks like pure dosage info
                if len(name) < 60 and not any(c.isalpha() for c in name.split()[0] if name.split()):
                    pass  # skip ambiguous
                if dry_run:
                    logger.info("[DRY RUN] Skip ambiguous: %s (id=%s)", name, drug_id)
                stats["skipped"] += 1

    logger.info(
        "Drug name cleanup: cleaned=%d, excluded=%d, skipped=%d",
        stats["cleaned"], stats["excluded"], stats["skipped"],
    )
    return stats


def resolve_unknown_entity_types(db: Database, dry_run: bool = False) -> int:
    """Resolve entity_links where source or target type is 'unknown'."""
    resolved = 0

    # Entity type detection tables
    type_tables = {
        "drug": ("drugs", "id"),
        "company": ("companies", "id"),
        "trial": ("clinical_trials", "id"),
        "therapeutic_area": ("therapeutic_areas", "id"),
        "mechanism": ("mechanisms_of_action", "id"),
        "article": ("pubmed_articles", "id"),
    }

    # Find links with unknown types
    unknown_links = db.fetch_all(
        """
        SELECT id, source_entity_id, source_entity_type,
               target_entity_id, target_entity_type, link_type
        FROM entity_links
        WHERE source_entity_type = 'unknown' OR target_entity_type = 'unknown'
        """
    )

    logger.info("Found %d links with unknown entity types", len(unknown_links))

    for link in unknown_links:
        link_id = link["id"]
        updated = False

        # Try to resolve source type
        if link["source_entity_type"] == "unknown":
            entity_id = link["source_entity_id"]
            for etype, (table, id_col) in type_tables.items():
                row = db.fetch_one(
                    f"SELECT 1 FROM {table} WHERE {id_col}::text = %s",
                    [entity_id],
                )
                if row:
                    if dry_run:
                        logger.info(
                            "[DRY RUN] Resolve source %s → %s (link=%s)",
                            entity_id, etype, link_id,
                        )
                    else:
                        db.execute(
                            "UPDATE entity_links SET source_entity_type = %s WHERE id = %s",
                            [etype, link_id],
                        )
                    updated = True
                    resolved += 1
                    break

        # Try to resolve target type
        if link["target_entity_type"] == "unknown":
            entity_id = link["target_entity_id"]
            for etype, (table, id_col) in type_tables.items():
                row = db.fetch_one(
                    f"SELECT 1 FROM {table} WHERE {id_col}::text = %s",
                    [entity_id],
                )
                if row:
                    if dry_run:
                        logger.info(
                            "[DRY RUN] Resolve target %s → %s (link=%s)",
                            entity_id, etype, link_id,
                        )
                    else:
                        db.execute(
                            "UPDATE entity_links SET target_entity_type = %s WHERE id = %s",
                            [etype, link_id],
                        )
                    updated = True
                    resolved += 1
                    break

        # If neither side resolved, delete orphaned link
        if not updated and not dry_run:
            src_unresolved = link["source_entity_type"] == "unknown"
            tgt_unresolved = link["target_entity_type"] == "unknown"
            if src_unresolved or tgt_unresolved:
                db.execute("DELETE FROM entity_links WHERE id = %s", [link_id])
                logger.debug("Deleted orphaned link %s", link_id)

    logger.info("Unknown entity types resolved: %d", resolved)
    return resolved


def run(dry_run: bool = False) -> dict:
    """Run all drug cleanup tasks."""
    db = Database(config.db.dsn)
    db.connect()

    try:
        name_stats = clean_drug_names(db, dry_run)
        unknown_resolved = resolve_unknown_entity_types(db, dry_run)
        return {
            **name_stats,
            "unknown_types_resolved": unknown_resolved,
        }
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Clean drug names and resolve unknown types")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    results = run(dry_run=args.dry_run)
    print("\n=== Drug Cleanup Results ===")
    for k, v in results.items():
        print(f"  {k}: {v}")
    if args.dry_run:
        print("  (dry run — no changes written)")


if __name__ == "__main__":
    main()
