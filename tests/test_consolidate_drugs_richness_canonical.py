"""Regression: the scheduled drug consolidation must keep the richest (evidence-
owning) row as canonical and must never demote it.

The legacy in-module merge in scripts/consolidate_drugs picked the canonical by
*source authority* (`_pick_canonical`: FDA > CT.gov > backfill) and only moved
entity_links. Run via the scheduler's auto_curate post-task, it demoted the rich
'tirzepatide' row (269 facts / 112 trials, source 'chembl') to
record_status='merged' behind a thin 'pubchem' look-alike and stranded its
facts/trials — so resolve_entity fell through to a junk row and 'compare
semaglutide vs tirzepatide' reported 1 trial.

consolidate_drugs now delegates to EntityConsolidator(rank_by_richness=True,
drug_name_normalizer=combo_safe_normalize): excludes merged+superseded, keeps the
richest row, and conflict-safe repoints every reference. Pin that wiring so a
future edit can't silently revert to the source-authority pick.
"""

from __future__ import annotations

import scripts.consolidate_drugs as cd


def test_consolidate_drugs_delegates_to_richness_ranked_consolidator(monkeypatch):
    captured: dict = {}

    class _FakeConsolidator:
        def __init__(self, db, **kwargs):
            captured.update(kwargs)

        def consolidate_drugs(self):
            return {"groups_found": 0, "records_merged": 0, "skipped": 0, "plan": []}

    monkeypatch.setattr(
        "integration.entity_consolidator.EntityConsolidator", _FakeConsolidator
    )

    out = cd.consolidate_drugs(db=object(), dry_run=True)

    # The fix: richness-ranked canonical selection (never source-authority) and a
    # combo-safe grouping normalizer.
    assert captured.get("rank_by_richness") is True
    assert captured.get("dry_run") is True
    assert callable(captured.get("drug_name_normalizer"))
    # Return shape preserved for scripts.auto_curate.
    assert set(out) >= {"groups_found", "records_merged", "aliases_created"}


def test_combo_safe_normalizer_keeps_additive_combo_out_of_mono_group():
    # The normalizer handed to the consolidator must not collapse an additive
    # combo into its mono (would wrongly merge Hyzaar into losartan).
    norm = cd.combo_safe_normalize
    assert norm("losartan potassium (+ hydrochlorothiazide)") != norm("losartan")
