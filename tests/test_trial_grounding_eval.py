"""Answer-grounding gold set (Loop C seed) — the #1 missing control.

A Lane-2 (live-DB) eval that pins what a *correct* grounded answer must contain,
so the "3 trials when there are 58" regression cannot return silently. Skips
without DATABASE_URL (like the other live invariants); run it with the Railway
URL to score against prod.

This is a SEED. Extend ``GOLD`` with more drugs / question types (safety,
pricing, competitors) as those grounding paths land.
"""
import os

import pytest

from services.trial_grounding import trial_grounding

DB_URL = os.environ.get("DATABASE_URL")
live = pytest.mark.skipif(not DB_URL, reason="DATABASE_URL not set — live grounding eval skipped")

# Gold expectations grounded in the registry (clinical_trials), not opinion.
# id = the canonical (richest) drug row; min_phase3 is a conservative floor.
GOLD = [
    {
        "drug_id": "15b2232d-b934-4074-a873-2ac5a7f9edd5",  # semaglutide / Ozempic
        "drug_name": "semaglutide",
        "min_phase3": 40,        # registry holds 58; floor guards against the "3" regression
        # Pivotal Phase-3 trials that must be CITED. We assert NCT IDs, not
        # acronyms: trial official_titles are descriptive (e.g. the FLOW renal
        # trial NCT03819153 has no "FLOW" in its title) — the citable, verifiable
        # token is the NCT id. (SELECT's title does contain "SELECT", kept too.)
        "must_cite": ["NCT03574597", "NCT03819153"],  # SELECT (CV), FLOW (renal)
    },
]


@live
@pytest.mark.parametrize("g", GOLD, ids=lambda g: g["drug_name"])
def test_grounded_trial_answer_meets_gold(g):
    from db import Database
    from config import config
    db = Database(config.db.dsn)
    out = trial_grounding(db, g["drug_id"], drug_name=g["drug_name"], top_n=10)

    p3 = out["summary"]["phase3_total"]
    assert p3 >= g["min_phase3"], (
        f"{g['drug_name']}: phase3_total={p3} < floor {g['min_phase3']} "
        f"— grounding regressed (this is the 'answered 3 of 58' guard)."
    )
    block = out["block"]
    for needle in g["must_cite"]:
        assert needle in block, (
            f"{g['drug_name']}: pivotal trial '{needle}' missing from grounded "
            f"answer citations — coverage regressed."
        )
    # The block must instruct against under-reporting (decision-grade discipline).
    assert "under-report" in block
