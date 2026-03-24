"""Backfill SPONSORS links between companies and clinical trials.

Many trials have sponsor_name that matches company names, but the
entity_links table is sparse because the cross-linker requires exact
foreign key matches. This script uses fuzzy name matching to create
SPONSORS links.

Usage:
    python scripts/backfill_sponsor_links.py [--dry-run] [--limit 100]
"""

from __future__ import annotations
import argparse
import logging

logger = logging.getLogger(__name__)

MATCH_SQL = """
WITH clean_companies AS (
    SELECT id, name,
           TRIM(REGEXP_REPLACE(
               REGEXP_REPLACE(LOWER(name), '\s*(inc\.?|corp\.?|ltd\.?|plc|co\.?|llc|a/s|ag|sa|se|gmbh)\s*$', '', 'i'),
               '\s+', ' ', 'g'
           )) AS clean_name
    FROM companies
    WHERE LENGTH(name) > 3
),
clean_sponsors AS (
    SELECT id, sponsor_name,
           TRIM(REGEXP_REPLACE(
               REGEXP_REPLACE(LOWER(sponsor_name), '\s*(inc\.?|corp\.?|ltd\.?|plc|co\.?|llc|a/s|ag|sa|se|gmbh)\s*$', '', 'i'),
               '\s+', ' ', 'g'
           )) AS clean_sponsor
    FROM clinical_trials
    WHERE sponsor_name IS NOT NULL AND LENGTH(sponsor_name) > 3
)
SELECT DISTINCT
    cc.id::text AS company_id,
    cc.name AS company_name,
    cs.id::text AS trial_id,
    cs.sponsor_name AS trial_title
FROM clean_companies cc
JOIN clean_sponsors cs ON cs.clean_sponsor LIKE CONCAT('%%', cc.clean_name, '%%')
    OR cc.clean_name LIKE CONCAT('%%', cs.clean_sponsor, '%%')
WHERE LENGTH(cc.clean_name) >= 5
  AND NOT EXISTS (
    SELECT 1 FROM entity_links el
    WHERE el.source_entity_id = cc.id::text
      AND el.target_entity_id = cs.id::text
      AND el.link_type = 'SPONSORS'
)
LIMIT %s
"""

INSERT_SQL = """
INSERT INTO entity_links (
    source_entity_id, source_entity_type,
    target_entity_id, target_entity_type,
    link_type, confidence, link_via,
    provenance_source
)
VALUES (%s, 'company', %s, 'trial', 'SPONSORS', %s, %s, 'backfill_sponsor_links')
ON CONFLICT DO NOTHING
"""


def backfill_sponsor_links(db, limit: int = 1000, dry_run: bool = False) -> dict:
    """Create SPONSORS links from trial sponsor_name → company name matching."""
    matches = db.fetch_all(MATCH_SQL, [limit])
    logger.info("Found %d sponsor matches to backfill", len(matches))

    created = 0
    for m in matches:
        via = f"sponsor_name match: {m['company_name']}"
        if dry_run:
            logger.info("DRY: %s → %s", m['company_name'], (m.get('trial_title') or '')[:60])
            created += 1
            continue
        try:
            db.execute(INSERT_SQL, [m['company_id'], m['trial_id'], 0.85, via])
            created += 1
        except Exception as e:
            logger.warning("Skip: %s", e)

    return {"total_matches": len(matches), "links_created": created, "dry_run": dry_run}


def run(limit: int = 1000, dry_run: bool = False) -> dict:
    from config import config
    from db import Database
    db = Database(config.db.dsn)
    db.connect()
    try:
        return backfill_sponsor_links(db, limit=limit, dry_run=dry_run)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Backfill SPONSORS links")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    result = run(limit=args.limit, dry_run=args.dry_run)
    print(f"\nResult: {result}")


if __name__ == "__main__":
    main()
