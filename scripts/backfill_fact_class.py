"""Backfill / reconcile fact_class on existing facts rows (Z1 + D-Q1).

Idempotent — safe to re-run. The class is resolved primarily by SOURCE
(COORDINATION §8.2, Design A): a fact that fell into the ``corporate`` default but
originates from an authoritative registry/regulatory source (ClinicalTrials.gov,
FDA Orange Book / SPL labels / drug-shortage feeds) is reference-grade ground
truth → ``reference``. Any remaining bare ``corporate`` default is then refined by
predicate via the same map ``fact_ingest`` uses; deliberately-classed facts
(``signal`` / ``inferred`` / already-``reference``) are left untouched. UPDATEs in
place — the ledger trigger blocks DELETE, not UPDATE.

This is the existing-rows half of D-Q1; the forward half is
``services.fact_emitters.base.resolve_fact_class`` (applied in ``emit_one``). Both
share ``AUTHORITATIVE_SOURCES`` so they can never drift.

Usage:
    python scripts/backfill_fact_class.py [--dry-run] [--limit N] [--predicate P]
"""

from __future__ import annotations

import argparse
import logging
from collections import Counter

from config import config
from db import Database
from services.fact_emitters.base import resolve_fact_class
from services.fact_ingest import classify_predicate
from services.facts_ledger import DEFAULT_FACT_CLASS

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


_UPDATE_SQL = """
    UPDATE facts SET fact_class = %s
     WHERE id = %s AND fact_class IS DISTINCT FROM %s
"""

# LEFT JOIN evidence so the class can be resolved by the originating SOURCE
# (facts.created_by is generic plumbing — 'fact_emitter'/'data_automaton';
# evidence_records.source_id is the real origin signal).
_FETCH_SQL = """
    SELECT f.id, f.predicate, f.fact_class, e.source_id
      FROM facts f
      LEFT JOIN evidence_records e ON e.evidence_id = f.source_doc_id
     {where}
     ORDER BY f.created_at
     {limit}
"""


def desired_fact_class(source_id, predicate, current) -> str:
    """Source-first resolution (D-Q1 §8.2) with a predicate-refinement fallback (Z1).

    1. authoritative source + ``corporate`` default  → ``reference``
    2. otherwise a bare ``corporate`` default         → refine by predicate
    3. otherwise (deliberate signal/inferred/reference) → leave unchanged
    """
    upgraded = resolve_fact_class(source_id, current)
    if upgraded != current:
        return upgraded
    if current == DEFAULT_FACT_CLASS:
        return classify_predicate(predicate)
    return current


def run(dry_run: bool = False, limit=None, predicate=None) -> dict:
    """Reconcile fact_class across the ledger. Returns a stats dict (for auto_curate)."""
    db = Database(config.db.dsn)
    clauses: list[str] = []
    params: list = []
    if predicate:
        clauses.append("f.predicate = %s")
        params.append(predicate)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    limit_sql = f"LIMIT {int(limit)}" if limit is not None else ""
    sql = _FETCH_SQL.format(where=where, limit=limit_sql)

    rows = db.fetch_all(sql, params)
    before: Counter = Counter(r.get("fact_class") for r in rows)  # pre-state audit snapshot
    counts: Counter = Counter()
    changed = 0
    for r in rows:
        current = r.get("fact_class")
        desired = desired_fact_class(r.get("source_id"), r.get("predicate"), current)
        if desired != current:
            if not dry_run:
                db.execute(_UPDATE_SQL, [desired, r["id"], desired])
            counts[f"{current}->{desired}"] += 1
            changed += 1
        else:
            counts["unchanged"] += 1
    db.close()

    summary = {
        "scanned": len(rows),
        "changed": changed,
        "before_distribution": dict(before),  # self-contained audit of the pre-state
        "transitions": dict(counts),
        "dry_run": dry_run,
    }
    logger.info("fact_class reconcile: %s", summary)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Reconcile fact_class (source-first, Z1 + D-Q1)")
    ap.add_argument("--dry-run", action="store_true",
                    help="count transitions without writing")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--predicate", type=str, default=None,
                    help="restrict to facts matching this predicate")
    args = ap.parse_args()

    res = run(dry_run=args.dry_run, limit=args.limit, predicate=args.predicate)
    print(f"scanned={res['scanned']} changed={res['changed']} "
          f"dry_run={res['dry_run']}")
    for k, v in sorted(res["transitions"].items()):
        print(f"  {k}={v}")


if __name__ == "__main__":
    main()
