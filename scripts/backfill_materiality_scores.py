"""BE-2 — backfill materiality_score on existing signals.

After migration 065 lands, every existing signal has
``materiality_score = NULL``. This script pages through the table,
calls ``services.materiality.score_signal_row`` on each row, and
persists the result.

Usage::

    python -m scripts.backfill_materiality_scores                # 500/batch
    python -m scripts.backfill_materiality_scores --batch 1000
    python -m scripts.backfill_materiality_scores --dry-run      # no UPDATE

The script is idempotent — only rows where ``materiality_score IS
NULL`` are picked up. Re-running is safe.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)


_SELECT_NULL_SCORE_SQL = """
    SELECT
        s.id, s.event_id, s.kbq_tags, s.headline, s.summary,
        s.direction, s.confidence_tier, s.trust_score, s.impact_tier,
        s.impact_score, s.primary_entity_type, s.primary_entity_id,
        s.primary_entity_name, s.related_entity_ids, s.created_at,
        s.materiality_score
      FROM signals s
     WHERE s.materiality_score IS NULL
     ORDER BY s.created_at DESC
     LIMIT %s
"""


def run(db: Any, *, batch: int = 500, dry_run: bool = False) -> dict:
    """Score one batch of unscored signals.

    Returns a summary dict::

        {
          "scored": int,        # rows successfully scored
          "skipped": int,       # rows that errored during scoring
          "dry_run": bool,
          "score_min": int|None,
          "score_max": int|None,
          "score_avg": float|None,
        }

    The function is one-batch-per-call by design so callers / cron jobs
    can tune cadence and the function stays easy to test.
    """
    from services.materiality import score_signal_row, get_active_config

    rows = db.fetch_all(_SELECT_NULL_SCORE_SQL, [batch]) or []
    if not rows:
        logger.info("backfill_materiality_scores: no NULL-score rows")
        return {"scored": 0, "skipped": 0, "dry_run": dry_run,
                "score_min": None, "score_max": None, "score_avg": None}

    cfg = get_active_config(db)
    scored = 0
    skipped = 0
    score_values: list[int] = []

    for row in rows:
        try:
            result = score_signal_row(db, dict(row), config=cfg, persist=not dry_run)
            score_values.append(int(round(result.score)))
            scored += 1
        except Exception as exc:
            skipped += 1
            logger.warning(
                "backfill_materiality_scores: skipping signal %s — %s",
                row.get("id"),
                exc,
            )

    summary = {
        "scored": scored,
        "skipped": skipped,
        "dry_run": dry_run,
        "score_min": min(score_values) if score_values else None,
        "score_max": max(score_values) if score_values else None,
        "score_avg": (sum(score_values) / len(score_values)) if score_values else None,
    }
    logger.info("backfill_materiality_scores: %s", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill materiality scores on signals.")
    parser.add_argument("--batch", type=int, default=500, help="rows per pass (default 500)")
    parser.add_argument("--dry-run", action="store_true", help="score but do not UPDATE")
    parser.add_argument("--max-passes", type=int, default=20,
                        help="cap on consecutive batches (default 20 → up to 10k rows)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    from db import Database
    from config import config

    db = Database(config.db.dsn)

    total_scored = 0
    total_skipped = 0
    for pass_idx in range(args.max_passes):
        summary = run(db, batch=args.batch, dry_run=args.dry_run)
        total_scored += summary["scored"]
        total_skipped += summary["skipped"]
        if summary["scored"] == 0:
            logger.info("backfill complete after %d passes", pass_idx + 1)
            break
    else:
        logger.warning("hit --max-passes=%d cap with rows still pending", args.max_passes)

    print(f"backfill: scored={total_scored} skipped={total_skipped} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
