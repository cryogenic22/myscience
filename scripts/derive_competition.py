"""Derive COMPETES_WITH links between drugs sharing mechanism + therapeutic area.

Two drugs compete when they target the same mechanism of action within the
same therapeutic area. This is the core competitive intelligence relationship.

Usage:
    python scripts/derive_competition.py [--dry-run]

Deterministic: no LLM cost. Pure SQL derivation.
"""

from __future__ import annotations

import argparse
import logging

logger = logging.getLogger(__name__)

COMPETITION_SQL = """
WITH drug_targets AS (
    SELECT
        d.id AS drug_id,
        d.generic_name,
        d.mechanism_id,
        d.therapeutic_area_id
    FROM drugs d
    WHERE d.mechanism_id IS NOT NULL
      AND d.therapeutic_area_id IS NOT NULL
      AND d.record_status = 'active'
)
SELECT DISTINCT
    a.drug_id AS drug_a_id,
    a.generic_name AS drug_a_name,
    b.drug_id AS drug_b_id,
    b.generic_name AS drug_b_name,
    a.mechanism_id,
    a.therapeutic_area_id
FROM drug_targets a
JOIN drug_targets b
    ON a.mechanism_id = b.mechanism_id
    AND a.therapeutic_area_id = b.therapeutic_area_id
    AND a.drug_id < b.drug_id  -- prevent duplicates and self-links
"""

INSERT_LINK_SQL = """
INSERT INTO entity_links (
    source_entity_id, source_entity_type,
    target_entity_id, target_entity_type,
    link_type, confidence, link_via
)
VALUES (%s, 'drug', %s, 'drug', 'COMPETES_WITH', %s, %s)
ON CONFLICT DO NOTHING
"""


def derive_competition(db, dry_run: bool = False) -> dict:
    """Derive COMPETES_WITH links from shared mechanism + TA pairs."""
    pairs = db.fetch_all(COMPETITION_SQL)
    logger.info("Found %d competitive pairs", len(pairs))

    created = 0
    skipped = 0
    for pair in pairs:
        via = f"shared mechanism {pair['mechanism_id']} in TA {pair['therapeutic_area_id']}"

        if dry_run:
            logger.info(
                "DRY RUN: %s ↔ %s (mechanism=%s, TA=%s)",
                pair['drug_a_name'], pair['drug_b_name'],
                pair['mechanism_id'], pair['therapeutic_area_id'],
            )
            created += 1
            continue

        try:
            # Bidirectional: A→B and B→A
            db.execute(INSERT_LINK_SQL, [pair['drug_a_id'], pair['drug_b_id'], 0.85, via])
            db.execute(INSERT_LINK_SQL, [pair['drug_b_id'], pair['drug_a_id'], 0.85, via])
            created += 1
        except Exception as e:
            logger.warning("Skip pair %s↔%s: %s", pair['drug_a_name'], pair['drug_b_name'], e)
            skipped += 1

    result = {
        "total_pairs": len(pairs),
        "links_created": created * 2,  # bidirectional
        "skipped": skipped,
        "dry_run": dry_run,
    }
    logger.info("Competition derivation: %s", result)
    return result


def run(dry_run: bool = False) -> dict:
    """Run competition derivation (creates own DB connection)."""
    from config import config
    from db import Database
    db = Database(config.db.dsn)
    db.connect()
    try:
        return derive_competition(db, dry_run)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Derive COMPETES_WITH links")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    result = run(dry_run=args.dry_run)
    print(f"\nResult: {result}")


if __name__ == "__main__":
    main()
