"""BE-37 — paginated tenant_id backfill / retag for core entities.

Migration 066 adds ``tenant_id TEXT NOT NULL DEFAULT 'public'`` to
``drugs / companies / clinical_trials / mechanisms_of_action`` and
fills every existing row with ``'public'`` automatically.

This script is for the **next** phase: once ingestion paths start
attaching tenant_id from session context, a steward can retro-tag
slices of rows by provenance — for example::

    # Mark every Pfizer-private upload (uploaded via the SEC
    # connector under a private session) as tenant 'pfizer'
    python -m scripts.backfill_tenant_id \
        --table drugs \
        --where-source-api sec_pfizer_private \
        --tenant pfizer \
        --dry-run

The script is intentionally narrow: one table at a time, audit log
written for every UPDATE, ``--dry-run`` defaults to printing the
rows that *would* change.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)


_TARGET_TABLES = ("drugs", "companies", "clinical_trials", "mechanisms_of_action")


def run(
    db: Any,
    *,
    table: str,
    tenant: str,
    where_source_api: str | None = None,
    where_id_in: list[str] | None = None,
    batch: int = 500,
    dry_run: bool = True,
) -> dict:
    """Tag matching rows in ``table`` with ``tenant``.

    Returns a summary dict::

        { "table": str, "tenant": str, "matched": int,
          "updated": int, "dry_run": bool, "preview": [first 5 ids] }

    The match is the AND of any provided filters. If no filters are
    provided the function refuses (safety — won't tag the whole
    table accidentally).
    """
    if table not in _TARGET_TABLES:
        raise ValueError(f"unknown table {table!r}; allowed: {_TARGET_TABLES}")
    if not tenant or not isinstance(tenant, str):
        raise ValueError("tenant must be a non-empty string")
    if where_source_api is None and not where_id_in:
        raise ValueError(
            "refusing to backfill without a filter — provide "
            "--where-source-api or --where-id-in"
        )

    where = ["tenant_id <> %s"]
    params: list[Any] = [tenant]
    if where_source_api is not None:
        where.append("source_api = %s")
        params.append(where_source_api)
    if where_id_in:
        where.append("id::text = ANY(%s)")
        params.append(list(where_id_in))
    where_sql = " AND ".join(where)

    select_sql = f"SELECT id::text AS id FROM {table} WHERE {where_sql} LIMIT %s"
    rows = db.fetch_all(select_sql, [*params, batch]) or []
    matched = len(rows)
    preview = [r["id"] for r in rows[:5]]

    summary = {
        "table": table,
        "tenant": tenant,
        "matched": matched,
        "updated": 0,
        "dry_run": dry_run,
        "preview": preview,
    }

    if matched == 0 or dry_run:
        logger.info("backfill_tenant_id (dry_run=%s): %s", dry_run, summary)
        return summary

    update_sql = f"UPDATE {table} SET tenant_id = %s WHERE {where_sql}"
    db.execute(update_sql, params=[tenant, *params])

    # Audit log — best-effort. If the table doesn't exist yet just
    # print to stderr so the steward sees what happened.
    try:
        db.execute(
            """INSERT INTO tenant_id_audit_log
                   (table_name, tenant_id, matched_count, where_clause,
                    actor, created_at)
               VALUES (%s, %s, %s, %s, %s, NOW())""",
            [table, tenant, matched, where_sql, "backfill_script"],
        )
    except Exception as exc:
        logger.warning("audit log write failed (non-fatal): %s", exc)

    summary["updated"] = matched
    logger.info("backfill_tenant_id: %s", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tag rows in a core entity table with tenant_id.")
    parser.add_argument("--table", required=True, choices=_TARGET_TABLES)
    parser.add_argument("--tenant", required=True, help="Target tenant_id slug")
    parser.add_argument("--where-source-api", help="Match rows whose source_api equals this value")
    parser.add_argument("--where-id-in", help="Comma-separated list of row ids (UUIDs as text)")
    parser.add_argument("--batch", type=int, default=500)
    parser.add_argument("--apply", action="store_true",
                        help="Without this flag, runs in dry-run mode by default.")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    from db import Database
    from config import config

    db = Database(config.db.dsn)

    ids = [s.strip() for s in args.where_id_in.split(",")] if args.where_id_in else None

    summary = run(
        db,
        table=args.table,
        tenant=args.tenant,
        where_source_api=args.where_source_api,
        where_id_in=ids,
        batch=args.batch,
        dry_run=not args.apply,
    )
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
