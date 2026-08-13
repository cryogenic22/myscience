"""BE-1 — paginated first-fill of evidence_records card fields.

Runs after migration 068 ships. For each row where any of
``source_name`` / ``source_tier`` / ``published_at`` / ``snippet``
is NULL, computes the registry default + snippet and UPDATEs in
place. The append-only trigger allows this first-fill (one-time
NULL → value transition).

Usage::

    python -m scripts.backfill_evidence_card_fields                    # 500/batch, dry-run
    python -m scripts.backfill_evidence_card_fields --apply
    python -m scripts.backfill_evidence_card_fields --batch 1000 --apply

Idempotent — only touches rows with at least one of the four columns
NULL. Re-running is safe.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)


_SELECT_PENDING_SQL = """
    SELECT evidence_id, source_id, extracted_text, retrieved_at,
           source_name, source_tier, published_at, snippet
      FROM evidence_records
     WHERE source_name IS NULL
        OR source_tier IS NULL
        OR published_at IS NULL
        OR snippet IS NULL
     ORDER BY created_at ASC
     LIMIT %s
"""


def run(db: Any, *, batch: int = 500, dry_run: bool = True) -> dict:
    """Backfill one batch. Returns a summary dict."""
    from services.evidence_ledger import lookup_source_metadata, make_snippet

    rows = db.fetch_all(_SELECT_PENDING_SQL, [batch]) or []
    if not rows:
        return {"matched": 0, "updated": 0, "dry_run": dry_run}

    updated = 0
    for row in rows:
        evidence_id = str(row["evidence_id"])
        source_id = row.get("source_id") or ""
        reg_name, reg_tier = lookup_source_metadata(source_id)

        new_name = row.get("source_name") or reg_name
        new_tier = row.get("source_tier") or reg_tier
        new_published_at = row.get("published_at") or row.get("retrieved_at")
        new_snippet = row.get("snippet") or make_snippet(row.get("extracted_text") or "")

        if dry_run:
            updated += 1
            continue

        try:
            db.execute(
                """
                UPDATE evidence_records
                   SET source_name  = COALESCE(source_name, %s),
                       source_tier  = COALESCE(source_tier, %s),
                       published_at = COALESCE(published_at, %s),
                       snippet      = COALESCE(snippet, %s)
                 WHERE evidence_id = %s
                """,
                [new_name, new_tier, new_published_at, new_snippet, evidence_id],
            )
            updated += 1
        except Exception as exc:
            logger.warning(
                "backfill_evidence_card_fields: skipping %s — %s",
                evidence_id, exc,
            )

    summary = {"matched": len(rows), "updated": updated, "dry_run": dry_run}
    logger.info("backfill_evidence_card_fields: %s", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="First-fill evidence_records card-render fields.")
    parser.add_argument("--batch", type=int, default=500)
    parser.add_argument("--apply", action="store_true",
                        help="Without --apply, defaults to dry-run.")
    parser.add_argument("--max-passes", type=int, default=20)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    from db import Database
    from config import config

    db = Database(config.db.dsn)

    total_matched = 0
    total_updated = 0
    for pass_idx in range(args.max_passes):
        s = run(db, batch=args.batch, dry_run=not args.apply)
        total_matched += s["matched"]
        total_updated += s["updated"]
        if s["matched"] == 0:
            logger.info("backfill complete after %d passes", pass_idx + 1)
            break
    else:
        logger.warning("hit --max-passes=%d cap with rows still pending", args.max_passes)

    print(f"backfill: matched={total_matched} updated={total_updated} dry_run={not args.apply}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
