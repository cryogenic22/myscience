"""Backfill: correct clinical_trial fact `valid_from` to the trial's start_date.

Closes a silent-loss bug: ClinicalTrialEmitter used to set
``valid_from = completion_date``. For ongoing / not-yet-completed trials that put
the fact's validity start in the FUTURE, so ``facts_as_of(now)`` silently hid
them — a recruiting Phase-3 trial that completes in 2027 is real *today*.

A trial's existence is valid FROM when it started (open-ended; a completed trial
remains a fact about the drug). This script recomputes ``valid_from`` from
``clinical_trials.start_date`` for existing facts. Idempotent (re-runs are a
no-op via ``IS DISTINCT FROM``), additive (corrects a metadata field only, never
drops a fact), and conservation-safe (facts whose trial has no start_date are
left untouched and counted, not dropped).

Usage:  DATABASE_URL=<railway url> python -m scripts.backfill_trial_fact_valid_from [--dry-run]
"""
from __future__ import annotations

import sys

from config import config
from db import Database

_HIDDEN = ("SELECT count(*) FROM facts WHERE predicate='clinical_trial' "
           "AND valid_from > now()")
_NULL_START = (
    "SELECT count(*) FROM facts f JOIN clinical_trials ct "
    "ON f.object_value->>'trial_id' = ct.id "
    "WHERE f.predicate='clinical_trial' AND ct.start_date IS NULL"
)
_UPDATE = """
  UPDATE facts f
     SET valid_from = ct.start_date::timestamptz
    FROM clinical_trials ct
   WHERE f.predicate='clinical_trial'
     AND f.object_value->>'trial_id' = ct.id
     AND ct.start_date IS NOT NULL
     AND (f.valid_from IS DISTINCT FROM ct.start_date::timestamptz)
"""


def run(db: Database, *, dry_run: bool = False) -> dict:
    before = db.fetch_one(_HIDDEN)["count"]
    null_start = db.fetch_one(_NULL_START)["count"]
    if dry_run:
        # count how many WOULD change
        would = db.fetch_one(
            "SELECT count(*) FROM facts f JOIN clinical_trials ct "
            "ON f.object_value->>'trial_id'=ct.id WHERE f.predicate='clinical_trial' "
            "AND ct.start_date IS NOT NULL "
            "AND f.valid_from IS DISTINCT FROM ct.start_date::timestamptz"
        )["count"]
        stats = {"dry_run": True, "hidden_before": before,
                 "would_update": would, "null_start_untouched": null_start}
        print(stats)
        return stats
    db.execute(_UPDATE)  # corrects valid_from in place; returns None
    after = db.fetch_one(_HIDDEN)["count"]
    stats = {"hidden_before": before, "hidden_after": after,
             "recovered": before - after, "null_start_untouched": null_start}
    print(stats)
    return stats


if __name__ == "__main__":
    run(Database(config.db.dsn), dry_run="--dry-run" in sys.argv)
