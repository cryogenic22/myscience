#!/usr/bin/env python
"""C1 (conservation floor) — relink clinical_trials to drugs via the INTERVENTIONS field.

A trial's authoritative drug is the one it administers — its `interventions`, NOT its
title. The title often names a drug that is only a comparator or the disease context
("...in patients on metformin"), so title-matching over-links and silently corrupts
(a false drug_id is worse than a NULL). This relinker matches ONLY the intervention
names (after stripping the ClinicalTrials.gov `TYPE:` prefixes), reusing the deterministic,
richness-ranked name-index matcher from scripts/relink_literature.py (anti-slop: no
duplicate matcher) with its hardened stop-list that drops polluted drug rows.

Conservation: additive + idempotent (only fills NULL drug_id, COALESCE never overwrites),
high-precision (intervention-scoped, junk excluded), and a trial that does not resolve is
left NULL and COUNTED — never force-linked or dropped.

IMPORTANT (probed 14-Jun-2026): high-precision linkage recovers only the genuinely-drug
trials; the MAJORITY of NULL-drug_id trials are legitimately drug-less (observational /
behavioral / device) or study novel drugs absent from our table. This script does NOT, and
should not, drive `clinical_trials.drug_id` orphan share to ~0 — that would require corrupt
title-matching. The orphan-ceiling denominator counting drug-less trials as orphans is a
separate, owner-reviewed bar question (see docs/DATA_INTEL_STRATEGY_AUDIT.md, C1).

Usage:
    DATABASE_URL=... python -m scripts.relink_trials [--limit N] [--dry-run]
Default is APPLY (writes). Pass --dry-run to report without writing.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import Database  # noqa: E402
from scripts.relink_literature import (  # noqa: E402
    _load_name_index,
    compile_matcher,
    match_drug_in_text,
)

# ClinicalTrials.gov intervention types that denote an administered substance. Items
# of other types (BEHAVIORAL / DEVICE / PROCEDURE / RADIATION / OTHER / DIAGNOSTIC_TEST)
# are not drugs; their descriptive text is still passed to the matcher but, being
# non-drug prose, will not resolve — so we don't need to hard-filter on type, just
# strip the prefix.
_PREFIX_RE = re.compile(r"^[A-Z_]+:\s*")


def intervention_text(raw: str | None) -> str:
    """Parse the stored `interventions` column (a Postgres text array rendered like
    ``{"BIOLOGICAL: Semaglutide","OTHER: Resistance exercise"}``) into a single string
    of intervention names with the ``TYPE:`` prefixes stripped. Pure — no DB."""
    if not raw:
        return ""
    items = re.findall(r'"([^"]+)"', raw) or [raw]
    names = [_PREFIX_RE.sub("", it).strip() for it in items if it.strip()]
    return " ; ".join(n for n in names if n)


def relink_trials(db: Database, limit: int | None = None, dry_run: bool = False) -> dict:
    name_index = _load_name_index(db)
    matcher = compile_matcher(name_index)
    limit_sql = f"LIMIT {int(limit)}" if limit else ""
    trials = db.fetch_all(
        f"""
        SELECT id, interventions::text AS interventions
        FROM clinical_trials
        WHERE drug_id IS NULL
        {limit_sql}
        """
    )
    matched = 0
    for t in trials:
        text = intervention_text(t.get("interventions"))
        dn = match_drug_in_text(text, name_index, matcher)
        if not dn:
            continue
        matched += 1
        if not dry_run:
            db.execute(
                "UPDATE clinical_trials SET drug_id = %s, updated_at = NOW() "
                "WHERE id = %s AND drug_id IS NULL",
                [dn.drug_id, t["id"]],
            )
    return {
        "candidates": len(trials),
        "matched": matched,
        "still_null": len(trials) - matched,
        "dry_run": dry_run,
    }


def run(dry_run: bool = False) -> dict:
    """Scheduler entrypoint (called from scripts/auto_curate.py post-tasks) so trial
    relinking is self-healing every curate cycle — new NULL-drug_id trials don't
    accumulate (the durability lesson from the #242 one-shot backfill)."""
    from config import config

    db = Database(config.db.dsn)
    db.connect()
    try:
        return relink_trials(db, dry_run=dry_run)
    finally:
        db.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    ap.add_argument("db_url", nargs="?", default=os.environ.get("DATABASE_URL"))
    args = ap.parse_args()
    if not args.db_url:
        sys.exit("Pass a DB url or set DATABASE_URL.")
    db = Database(args.db_url)
    db.connect()
    try:
        result = relink_trials(db, limit=args.limit, dry_run=args.dry_run)
        mode = "DRY RUN (no writes)" if args.dry_run else "APPLIED"
        print(f"[{mode}] {result}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
