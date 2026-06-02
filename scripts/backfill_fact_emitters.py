"""DR-8 (backfill) — run the fact emitters across every active drug.

Breaks the facts-ledger monoculture (audit RC2) by lifting clinical_trials /
adverse_events / drug_labels into the ledger for ALL drugs, not just the demo
ones. Additive + idempotent (emitters skip existing facts on
object_value.source_row_id), so it is safe to re-run / resume after a dropped
connection. Connection-resilient: reconnects per-batch (the Railway proxy drops
long-lived connections).

Usage:
    DATABASE_URL=... python -m scripts.backfill_fact_emitters [--limit-drugs N]
"""

from __future__ import annotations

import argparse
import logging
import os

from db import Database
from services.fact_emitters.base import EmitStats, run_all_emitters

logger = logging.getLogger(__name__)

_ACTIVE_DRUGS_SQL = """
    SELECT id::text AS id FROM drugs
     WHERE record_status IS DISTINCT FROM 'superseded'
       AND record_status IS DISTINCT FROM 'merged'
     ORDER BY id
"""


def _dsn() -> str:
    return os.environ.get("DATABASE_URL") or __import__("config").config.db.dsn


def backfill(db: Database, *, limit_drugs: int | None = None,
             log_every: int = 100) -> dict[str, EmitStats]:
    """Run all emitters per active drug. Returns merged {emitter: EmitStats}."""
    drug_ids = [r["id"] for r in db.fetch_all(_ACTIVE_DRUGS_SQL)]
    if limit_drugs:
        drug_ids = drug_ids[:limit_drugs]
    total = len(drug_ids)
    logger.info("backfill: %d active drugs", total)

    merged: dict[str, EmitStats] = {}
    for i, drug_id in enumerate(drug_ids, 1):
        try:
            per = run_all_emitters(db, drug_id=drug_id)
        except Exception:
            logger.exception("backfill: drug %s failed; reconnecting", drug_id)
            try:
                db.close()
            except Exception:
                pass
            db.connect()
            continue
        for name, st in per.items():
            if name not in merged:
                merged[name] = EmitStats(emitter=name)
            merged[name].merge(st)
        if i % log_every == 0 or i == total:
            summary = ", ".join(
                f"{n}:{s.asserted}a/{s.skipped_existing}e" for n, s in merged.items()
            )
            logger.info("backfill %d/%d drugs — %s", i, total, summary)
    return merged


def main():
    parser = argparse.ArgumentParser(description="Backfill fact emitters over all drugs")
    parser.add_argument("--limit-drugs", type=int, default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s: %(message)s")
    db = Database(_dsn())
    db.connect()
    try:
        merged = backfill(db, limit_drugs=args.limit_drugs)
    finally:
        db.close()
    print("\n=== Fact-emitter backfill ===")
    for name, st in merged.items():
        print(f"  {name}: asserted={st.asserted} existing={st.skipped_existing} "
              f"evidence={st.evidence_written}")


if __name__ == "__main__":
    main()
