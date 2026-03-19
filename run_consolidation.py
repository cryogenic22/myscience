"""
CLI orchestrator for entity consolidation.

Usage:
    python run_consolidation.py              # full run (sweep + dedup)
    python run_consolidation.py --dry-run    # preview only
    python run_consolidation.py --sweep-only # only exact-match sweep (P0-A)
    python run_consolidation.py --dedup-only # only entity dedup (P0-B)
"""

import argparse
import logging
import sys

from config import config
from db import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger(__name__)


def get_state(db) -> dict:
    """Snapshot current entity counts for before/after comparison."""
    state = {}
    state["unresolved_pending"] = db.fetch_one(
        "SELECT count(*) AS c FROM unresolved_entities WHERE resolved = FALSE AND (status IS NULL OR status = 'pending')"
    )["c"]
    state["unresolved_total"] = db.fetch_one(
        "SELECT count(*) AS c FROM unresolved_entities WHERE resolved = FALSE"
    )["c"]
    state["drugs_active"] = db.fetch_one(
        "SELECT count(*) AS c FROM drugs WHERE record_status != 'superseded'"
    )["c"]
    state["drugs_superseded"] = db.fetch_one(
        "SELECT count(*) AS c FROM drugs WHERE record_status = 'superseded'"
    )["c"]
    state["companies_active"] = db.fetch_one(
        "SELECT count(*) AS c FROM companies WHERE record_status != 'superseded'"
    )["c"]
    state["companies_superseded"] = db.fetch_one(
        "SELECT count(*) AS c FROM companies WHERE record_status = 'superseded'"
    )["c"]
    state["drug_dup_groups"] = db.fetch_one(
        """
        SELECT count(*) AS c FROM (
            SELECT LOWER(generic_name)
            FROM drugs WHERE record_status != 'superseded' AND generic_name IS NOT NULL
            GROUP BY LOWER(generic_name) HAVING count(*) > 1
        ) sub
        """
    )["c"]
    state["company_dup_groups"] = db.fetch_one(
        """
        SELECT count(*) AS c FROM (
            SELECT LOWER(name)
            FROM companies WHERE record_status != 'superseded' AND name IS NOT NULL
            GROUP BY LOWER(name) HAVING count(*) > 1
        ) sub
        """
    )["c"]
    return state


def print_state(label: str, state: dict):
    """Pretty-print a state snapshot."""
    print(f"\n  {label}:")
    print(f"    Unresolved (pending):        {state['unresolved_pending']}")
    print(f"    Unresolved (total):          {state['unresolved_total']}")
    print(f"    Drugs (active):              {state['drugs_active']}")
    print(f"    Drugs (superseded):          {state['drugs_superseded']}")
    print(f"    Drug duplicate groups:       {state['drug_dup_groups']}")
    print(f"    Companies (active):          {state['companies_active']}")
    print(f"    Companies (superseded):      {state['companies_superseded']}")
    print(f"    Company duplicate groups:    {state['company_dup_groups']}")


def main():
    parser = argparse.ArgumentParser(description="Market-Zero Entity Consolidation")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no writes")
    parser.add_argument("--sweep-only", action="store_true", help="Only run exact-match sweep (P0-A)")
    parser.add_argument("--dedup-only", action="store_true", help="Only run entity dedup (P0-B)")
    args = parser.parse_args()

    db = Database(config.db.dsn)
    db.connect()

    # Load domain pack
    domain_pack = None
    try:
        from domain.pharma.pack import get_pharma_pack
        domain_pack = get_pharma_pack()
    except Exception as e:
        logger.warning("Could not load pharma domain pack: %s", e)

    mode = "DRY RUN" if args.dry_run else "LIVE"
    print("=" * 60)
    print(f"Market-Zero: Entity Consolidation ({mode})")
    print("=" * 60)

    # Pre-state
    pre = get_state(db)
    print_state("Pre-consolidation state", pre)

    run_sweep = not args.dedup_only
    run_dedup = not args.sweep_only

    # P0-A: Exact-match sweep
    if run_sweep:
        print("\n--- P0-A: Exact-Match Sweep ---")
        if args.dry_run:
            print("  [DRY RUN] Sweep would process all pending unresolved entities")
            # Still run the sweep queries to show counts
            from process_unresolved import exact_match_sweep
            sweep_stats = exact_match_sweep(db, domain_pack=domain_pack)
            print(f"  Drugs resolved:     {sweep_stats['drugs_resolved']}")
            print(f"  Companies resolved: {sweep_stats['companies_resolved']}")
            print(f"  Skipped:            {sweep_stats['skipped']}")
        else:
            from process_unresolved import exact_match_sweep
            sweep_stats = exact_match_sweep(db, domain_pack=domain_pack)
            print(f"  Drugs resolved:     {sweep_stats['drugs_resolved']}")
            print(f"  Companies resolved: {sweep_stats['companies_resolved']}")
            print(f"  Skipped:            {sweep_stats['skipped']}")

    # P0-B: Entity dedup
    if run_dedup:
        print("\n--- P0-B: Entity Deduplication ---")
        from integration.entity_consolidator import EntityConsolidator

        consolidator = EntityConsolidator(db, domain_pack=domain_pack, dry_run=args.dry_run)
        results = consolidator.run()

        print(f"\n  Drug dedup:")
        print(f"    Duplicate groups found: {results['drugs']['groups_found']}")
        print(f"    Records merged:         {results['drugs']['records_merged']}")
        print(f"  Company dedup:")
        print(f"    Duplicate groups found: {results['companies']['groups_found']}")
        print(f"    Records merged:         {results['companies']['records_merged']}")

    # Post-state
    post = get_state(db)
    print_state("Post-consolidation state", post)

    # Delta
    print("\n  Changes:")
    print(f"    Unresolved resolved:   {pre['unresolved_pending'] - post['unresolved_pending']}")
    print(f"    Drugs superseded:      {post['drugs_superseded'] - pre['drugs_superseded']}")
    print(f"    Companies superseded:  {post['companies_superseded'] - pre['companies_superseded']}")
    print(f"    Drug dup groups left:  {post['drug_dup_groups']}")
    print(f"    Company dup groups:    {post['company_dup_groups']}")

    db.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
