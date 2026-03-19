"""CLI entry point: python -m scheduler

Usage:
    python -m scheduler                    Start daemon (cron-scheduled runs)
    python -m scheduler --run-now          Run all connectors once and exit
    python -m scheduler --run pubmed       Run a single connector and exit
    python -m scheduler --status           Show last run times and exit
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("scheduler")


def main():
    parser = argparse.ArgumentParser(
        description="Market-Zero data pipeline scheduler",
    )
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="Run all connectors once in order and exit",
    )
    parser.add_argument(
        "--run",
        type=str,
        metavar="CONNECTOR",
        help="Run a single connector by name (e.g. pubmed, clinical_trials_gov)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show last run status for all connectors",
    )
    args = parser.parse_args()

    from scheduler.runner import DataPipelineScheduler

    sched = DataPipelineScheduler()

    if args.status:
        _print_status(sched)
        return

    if args.run:
        logger.info("Running single connector: %s", args.run)
        result = sched.run_one(args.run)
        logger.info("Result: %s", result)
        return

    if args.run_now:
        logger.info("Running all connectors once...")
        results = sched.run_now()
        logger.info("Results:")
        for name, status in results.items():
            logger.info("  %-25s %s", name, status)
        return

    # Default: daemon mode
    logger.info("Starting scheduler in daemon mode...")
    sched.start()


def _print_status(sched):
    """Pretty-print the last run status for each connector."""
    rows = sched.status()
    if not rows:
        print("No ETL runs found in the database.")
        return

    # Header
    print(f"\n{'Connector':<28} {'Status':<10} {'Processed':>10} {'Inserted':>9} {'Completed At':<22}")
    print("-" * 85)

    for r in rows:
        completed = r.get("completed_at")
        if isinstance(completed, datetime):
            completed_str = completed.strftime("%Y-%m-%d %H:%M:%S")
        else:
            completed_str = str(completed or "—")

        print(
            f"{r.get('source_name', '?'):<28} "
            f"{r.get('status', '?'):<10} "
            f"{r.get('records_processed', 0):>10} "
            f"{r.get('records_inserted', 0):>9} "
            f"{completed_str:<22}"
        )

        if r.get("error_message"):
            print(f"  +-- error: {r['error_message'][:80]}")

    print()


if __name__ == "__main__":
    main()
