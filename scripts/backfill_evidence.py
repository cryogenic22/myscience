"""D5 — evidence completeness backfill (SPEC_DATA_001 §D5).

~31% of live facts have ``source_doc_id`` NULL → the dossier can't drill through
to a source. Nearly all are ``data_automaton`` facts asserted by
``services.fact_ingest`` from market_events (market_event / regulatory_approval /
trial_result / ma_deal / …): they DO carry a citeable source in
``object_value`` (``description`` + ``source_url`` + ``source_feed`` /
``event_type``) but predate DR-5, so no evidence_record was written.

This is **additive + idempotent**: for each backfillable NULL-source fact it
writes a standalone ``evidence_record`` (reusing
``services.fact_emitters.base._write_evidence`` — dedups on
(source_content_hash, source_id)) and sets ``facts.source_doc_id`` only where it
is still NULL. Re-running reuses the evidence record and skips already-linked
facts. Facts with no usable text are left NULL (genuinely sourceless — reported,
not invented).

Usage:
    python scripts/backfill_evidence.py "<db url>" --dry-run
    python scripts/backfill_evidence.py "<db url>"
"""

from __future__ import annotations

import argparse
import logging
import sys

from services.fact_emitters.base import EmittedFact, _write_evidence

logger = logging.getLogger(__name__)


# Live facts missing evidence that carry a backfillable source in object_value.
_SELECT_BACKFILLABLE = """
    SELECT id, predicate, object_value, confidence
      FROM facts
     WHERE source_doc_id IS NULL
       AND superseded_by IS NULL
       AND (object_value ? 'description' OR object_value ? 'source_url')
     ORDER BY asserted_at DESC
     {limit}
"""


def _fact_to_evidence(row: dict) -> EmittedFact | None:
    """Shape a NULL-source fact into the EmittedFact that _write_evidence needs.

    The evidence text is the event description (the citeable claim); source_id
    is the feed/predicate; source_url drills through. Returns None when there is
    no text to attest (genuinely sourceless — leave NULL)."""
    ov = row.get("object_value") or {}
    desc = (ov.get("description") or "").strip()
    url = ov.get("source_url")
    if not desc:
        # no description: fall back to a minimal claim from the url, else skip.
        if not url:
            return None
        desc = url
    source_id = (ov.get("source_feed") or ov.get("event_type")
                 or row.get("predicate") or "fact_ingest")
    return EmittedFact(
        predicate=row.get("predicate") or "market_event",
        subject_entity_type="",   # unused by _write_evidence
        subject_entity_id="",
        object_value=ov,
        source_row_id=str(row["id"]),
        confidence=float(row.get("confidence") or 0.5),
        evidence_text=desc,
        source_id=str(source_id),
        source_url=url,
    )


def run(db, *, dry_run: bool = False, limit: int | None = None) -> dict:
    limit_sql = f"LIMIT {int(limit)}" if limit else ""
    rows = db.fetch_all(_SELECT_BACKFILLABLE.format(limit=limit_sql))
    stats = {
        "candidates": len(rows),
        "linked": 0,
        "skipped_no_text": 0,
        "evidence_failed": 0,
    }
    for row in rows:
        ef = _fact_to_evidence(row)
        if ef is None:
            stats["skipped_no_text"] += 1
            continue
        if dry_run:
            stats["linked"] += 1
            continue
        eid = _write_evidence(db, ef)
        if not eid:
            stats["evidence_failed"] += 1
            continue
        db.execute(
            "UPDATE facts SET source_doc_id = %s "
            "WHERE id = %s AND source_doc_id IS NULL",
            [eid, str(row["id"])],
        )
        stats["linked"] += 1
    logger.info("evidence backfill: %s", stats)
    return stats


def null_share(db) -> tuple[int, int]:
    r = db.fetch_one(
        "SELECT count(*) FILTER (WHERE source_doc_id IS NULL) n, count(*) t "
        "FROM facts WHERE superseded_by IS NULL"
    ) or {}
    return r.get("n", 0), r.get("t", 0)


def _connect(url: str):
    from db import Database
    db = Database(url)
    db.connect()
    return db


def main() -> None:
    ap = argparse.ArgumentParser(description="D5 evidence completeness backfill")
    ap.add_argument("db_url", nargs="?")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    import os
    url = args.db_url or os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("Pass a postgres url or set DATABASE_URL")
    db = _connect(url)
    try:
        n0, t0 = null_share(db)
        print(f"before: {n0}/{t0} facts NULL source_doc_id ({100*n0/t0:.1f}%)")
        stats = run(db, dry_run=args.dry_run, limit=args.limit)
        print("=== evidence backfill ===")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        if not args.dry_run:
            n1, t1 = null_share(db)
            print(f"after:  {n1}/{t1} facts NULL source_doc_id ({100*n1/t1:.1f}%)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
