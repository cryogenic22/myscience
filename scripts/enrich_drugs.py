"""Enrich drug completeness.

Phase 1.4: Fill missing brand_name, approval_date, and company_id
from regulatory_milestones, trial sponsors, and OpenFDA labels.

Usage:
    python -m scripts.enrich_drugs [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone

from config import config
from db import Database

logger = logging.getLogger(__name__)


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


def _table_exists(db: Database, table_name: str) -> bool:
    row = db.fetch_one(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s) AS exists_",
        [table_name],
    )
    return bool(row and row.get("exists_"))


def enrich_from_milestones(db: Database, dry_run: bool = False) -> dict[str, int]:
    """Backfill brand_name and approval_date from regulatory_milestones."""
    stats = {"brand_name": 0, "approval_date": 0}

    if not _table_exists(db, "regulatory_milestones"):
        logger.info("regulatory_milestones table not found, skipping milestone enrichment")
        return stats

    # Brand name from milestones
    rows = db.fetch_all(
        """
        SELECT d.id AS drug_id, rm.brand_name, rm.approval_date
        FROM drugs d
        JOIN entity_links el ON el.target_entity_id = d.id::text
          AND el.target_entity_type = 'drug'
          AND el.link_type = 'HAS_MILESTONE'
        JOIN regulatory_milestones rm ON rm.id::text = el.source_entity_id
        WHERE (d.brand_name IS NULL OR d.brand_name = '')
          AND rm.brand_name IS NOT NULL AND rm.brand_name != ''
        """
    )
    for row in rows:
        drug_id = str(row["drug_id"])
        if dry_run:
            logger.info("[DRY RUN] Enrich drug %s brand_name=%s", drug_id, row["brand_name"])
        else:
            db.execute(
                "UPDATE drugs SET brand_name = %s WHERE id = %s AND (brand_name IS NULL OR brand_name = '')",
                [row["brand_name"], row["drug_id"]],
            )
            _log_change(db, "drug", drug_id, "enrich_brand_from_milestone",
                        ["brand_name"])
        stats["brand_name"] += 1

    # Approval date from milestones
    rows = db.fetch_all(
        """
        SELECT d.id AS drug_id, MIN(rm.approval_date) AS earliest_approval
        FROM drugs d
        JOIN entity_links el ON el.target_entity_id = d.id::text
          AND el.target_entity_type = 'drug'
          AND el.link_type = 'HAS_MILESTONE'
        JOIN regulatory_milestones rm ON rm.id::text = el.source_entity_id
        WHERE d.approval_date IS NULL
          AND rm.approval_date IS NOT NULL
        GROUP BY d.id
        """
    )
    for row in rows:
        drug_id = str(row["drug_id"])
        if dry_run:
            logger.info("[DRY RUN] Enrich drug %s approval_date=%s", drug_id, row["earliest_approval"])
        else:
            db.execute(
                "UPDATE drugs SET approval_date = %s WHERE id = %s AND approval_date IS NULL",
                [row["earliest_approval"], row["drug_id"]],
            )
            _log_change(db, "drug", drug_id, "enrich_approval_from_milestone",
                        ["approval_date"])
        stats["approval_date"] += 1

    logger.info("Milestone enrichment: brand_name=%d, approval_date=%d",
                stats["brand_name"], stats["approval_date"])
    return stats


def enrich_company_from_trials(db: Database, dry_run: bool = False) -> int:
    """Infer company_id from trial sponsor names."""
    count = 0

    # Find drugs without company_id that have linked trials with sponsor_name
    rows = db.fetch_all(
        """
        SELECT DISTINCT d.id AS drug_id, ct.sponsor_name
        FROM drugs d
        JOIN entity_links el ON el.target_entity_id = d.id::text
          AND el.target_entity_type = 'drug'
          AND el.link_type = 'INVESTIGATES'
        JOIN clinical_trials ct ON ct.id = el.source_entity_id
        WHERE d.company_id IS NULL
          AND ct.sponsor_name IS NOT NULL
          AND ct.sponsor_name != ''
        """
    )

    for row in rows:
        sponsor = row["sponsor_name"]
        drug_id = str(row["drug_id"])

        # Try exact match first
        company = db.fetch_one(
            """
            SELECT id FROM companies
            WHERE LOWER(name) = LOWER(%s)
              AND record_status IS DISTINCT FROM 'merged'
              AND record_status IS DISTINCT FROM 'excluded'
            LIMIT 1
            """,
            [sponsor],
        )

        # Try fuzzy match via trigram similarity
        if not company:
            company = db.fetch_one(
                """
                SELECT id, name, similarity(LOWER(name), LOWER(%s)) AS sim
                FROM companies
                WHERE record_status IS DISTINCT FROM 'merged'
                  AND record_status IS DISTINCT FROM 'excluded'
                  AND similarity(LOWER(name), LOWER(%s)) > 0.6
                ORDER BY sim DESC
                LIMIT 1
                """,
                [sponsor, sponsor],
            )

        # Try alias lookup
        if not company and _table_exists(db, "entity_aliases"):
            alias_row = db.fetch_one(
                """
                SELECT entity_id FROM entity_aliases
                WHERE entity_type = 'company'
                  AND LOWER(alias_text) = LOWER(%s)
                LIMIT 1
                """,
                [sponsor],
            )
            if alias_row:
                company = {"id": alias_row["entity_id"]}

        if company:
            if dry_run:
                logger.info(
                    "[DRY RUN] Set drug %s company_id=%s (sponsor=%s)",
                    drug_id, company["id"], sponsor,
                )
            else:
                db.execute(
                    "UPDATE drugs SET company_id = %s WHERE id = %s AND company_id IS NULL",
                    [company["id"], row["drug_id"]],
                )
                # Also create OWNS link
                existing_link = db.fetch_one(
                    """
                    SELECT 1 FROM entity_links
                    WHERE source_entity_id = %s AND source_entity_type = 'company'
                      AND target_entity_id = %s AND target_entity_type = 'drug'
                      AND link_type = 'OWNS'
                    """,
                    [str(company["id"]), drug_id],
                )
                if not existing_link:
                    db.execute(
                        """
                        INSERT INTO entity_links
                            (source_entity_id, source_entity_type,
                             target_entity_id, target_entity_type,
                             link_type, confidence, provenance_source)
                        VALUES (%s, 'company', %s, 'drug', 'OWNS', 0.7, 'enrich_from_sponsor')
                        ON CONFLICT DO NOTHING
                        """,
                        [str(company["id"]), drug_id],
                    )
                _log_change(db, "drug", drug_id, "enrich_company_from_sponsor",
                            ["company_id", f"sponsor:{sponsor}"])
            count += 1

    logger.info("Drugs enriched with company_id from sponsors: %d", count)
    return count


def enrich_from_labels(db: Database, dry_run: bool = False) -> dict[str, int]:
    """Enrich drug brand_name and company from OpenFDA label data."""
    stats = {"brand_name": 0, "company": 0}

    if not _table_exists(db, "drug_labels"):
        logger.info("drug_labels table not found, skipping label enrichment")
        return stats

    # Brand name from labels
    rows = db.fetch_all(
        """
        SELECT d.id AS drug_id, dl.brand_name, dl.manufacturer_name
        FROM drugs d
        JOIN entity_links el ON el.target_entity_id = d.id::text
          AND el.target_entity_type = 'drug'
          AND el.link_type = 'HAS_LABEL'
        JOIN drug_labels dl ON dl.id::text = el.source_entity_id
        WHERE (d.brand_name IS NULL OR d.brand_name = '')
          AND dl.brand_name IS NOT NULL AND dl.brand_name != ''
        """
    )
    for row in rows:
        drug_id = str(row["drug_id"])
        brand = row["brand_name"]
        if dry_run:
            logger.info("[DRY RUN] Enrich drug %s brand_name=%s from label", drug_id, brand)
        else:
            db.execute(
                "UPDATE drugs SET brand_name = %s WHERE id = %s AND (brand_name IS NULL OR brand_name = '')",
                [brand, row["drug_id"]],
            )
            _log_change(db, "drug", drug_id, "enrich_brand_from_label", ["brand_name"])
        stats["brand_name"] += 1

    logger.info("Label enrichment: brand_name=%d, company=%d", stats["brand_name"], stats["company"])
    return stats


def run(dry_run: bool = False) -> dict:
    """Run all drug enrichment tasks."""
    db = Database(config.db.dsn)
    db.connect()

    try:
        milestone_stats = enrich_from_milestones(db, dry_run)
        sponsor_count = enrich_company_from_trials(db, dry_run)
        label_stats = enrich_from_labels(db, dry_run)
        return {
            "brand_from_milestones": milestone_stats["brand_name"],
            "approval_from_milestones": milestone_stats["approval_date"],
            "company_from_sponsors": sponsor_count,
            "brand_from_labels": label_stats["brand_name"],
            "company_from_labels": label_stats["company"],
        }
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Enrich drug completeness")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    results = run(dry_run=args.dry_run)
    print("\n=== Drug Enrichment Results ===")
    for k, v in results.items():
        print(f"  {k}: {v}")
    total = sum(results.values())
    print(f"  TOTAL enrichments: {total}")
    if args.dry_run:
        print("  (dry run — no changes written)")


if __name__ == "__main__":
    main()
