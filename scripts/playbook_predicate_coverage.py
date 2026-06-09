#!/usr/bin/env python
"""Playbook → fact-ledger predicate coverage analyzer (data-lane).

The PLAN stage decomposes a question into dimensions that route to fact-ledger
predicates. A dimension whose predicates barely exist in the ledger renders as a
gap — correct behaviour, but it means the answer is structurally empty there. This
tool reports, per playbook dimension, whether the prod ledger can fill it, so the
data lane builds the emitters the question actually needs.

Pure classification (classify_coverage) is unit-tested DB-free; the CLI probes
the live ledger. Read-only (SELECTs only).

Usage:
    DATABASE_URL=... python -m scripts.playbook_predicate_coverage [playbook.yaml]
    (defaults to domain/pharma/packs/pharma_question_playbooks.yaml)
"""
from __future__ import annotations

import os
import pathlib
import sys

import yaml

# Thresholds for the verdict (rows in the ledger across all routed predicates).
_COVERED_MIN = 100
_PARTIAL_MIN = 20


def dimension_predicates(playbook: dict) -> dict[str, list[str]]:
    """Map each dimension key -> its predicate-route values (the existing
    Playbook schema: routes are 'predicate:foo' strings or {predicate: foo})."""
    out: dict[str, list[str]] = {}
    for dim in playbook.get("dimensions", []) or []:
        preds: list[str] = []
        for r in dim.get("routes", []) or []:
            if isinstance(r, str) and r.startswith("predicate:"):
                preds.append(r.split(":", 1)[1].strip())
            elif isinstance(r, dict) and "predicate" in r:
                preds.append(str(r["predicate"]).strip())
        out[dim["key"]] = preds
    return out


def classify_coverage(predicates: list[str], ledger: dict[str, int]) -> tuple[str, int, list[str]]:
    """Pure: given a dimension's predicates and a {predicate: row_count} ledger
    map, return (verdict, total_rows, missing_predicates).

    verdict ∈ {covered, partial, gap}. A predicate absent from the ledger (or
    zero rows) is 'missing' — the signal for "build an emitter for this".
    """
    total = sum(ledger.get(p, 0) for p in predicates)
    missing = [p for p in predicates if ledger.get(p, 0) <= 0]
    # "covered" requires real coverage of the lens, not a generic fallback
    # inflating the count: fewer than HALF the routed predicates may be missing.
    # Otherwise a single catch-all predicate (e.g. clinical_trial) would mask
    # that the lens-specific predicates (phase_transition, discontinuation)
    # don't exist yet — exactly the development-lens trap on prod.
    majority_missing = len(missing) * 2 >= len(predicates)
    if total >= _COVERED_MIN and not majority_missing:
        verdict = "covered"
    elif total >= _PARTIAL_MIN or (total > 0 and not majority_missing):
        verdict = "partial"
    else:
        verdict = "gap"
    return verdict, total, missing


def _load_ledger(url: str) -> dict[str, int]:
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT predicate, count(*) AS n FROM facts GROUP BY predicate")
    ledger = {r["predicate"]: int(r["n"]) for r in cur.fetchall()}
    cur.close()
    conn.close()
    return ledger


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("postgres")]
    url = os.environ.get("DATABASE_URL") or next(
        (a for a in sys.argv[1:] if a.startswith("postgres")), None)
    default = (pathlib.Path(__file__).parent.parent
               / "domain" / "pharma" / "packs" / "pharma_question_playbooks.yaml")
    pb_path = pathlib.Path(args[0]) if args else default
    playbook = yaml.safe_load(pb_path.read_text(encoding="utf-8"))

    if not url:
        sys.exit("Set DATABASE_URL (read-only ledger probe).")
    ledger = _load_ledger(url)

    dims = dimension_predicates(playbook)
    print(f"=== Predicate coverage for playbook '{playbook.get('id')}' ===")
    print(f"(covered>={_COVERED_MIN} rows AND <half predicates missing | "
          f"partial>={_PARTIAL_MIN} | else gap)\n")
    counts = {"covered": 0, "partial": 0, "gap": 0}
    for key, preds in dims.items():
        verdict, total, missing = classify_coverage(preds, ledger)
        counts[verdict] += 1
        print(f"  [{verdict.upper():<7}] {key:<24} rows={total:<6} "
              f"missing_predicates={missing or '-'}")
    print(f"\nSummary: {counts['covered']} covered | {counts['partial']} partial | "
          f"{counts['gap']} gap (need emitters)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
