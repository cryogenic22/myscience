"""Tests for grounded trial answers (Loop H2). DB-free via a fake db."""
from datetime import datetime, timezone

from services.trial_grounding import (
    summarize_phases,
    format_grounding_block,
    trial_grounding,
)

AS_OF = datetime(2026, 6, 8, tzinfo=timezone.utc)


class _FakeDB:
    """fetch_all dispatches on the SQL: phase-count vs notable-trials."""
    def __init__(self, phase_rows, notable_rows):
        self.phase_rows = phase_rows
        self.notable_rows = notable_rows
        self.calls = 0

    def fetch_all(self, sql, params=None):
        self.calls += 1
        if "GROUP BY" in sql:
            return self.phase_rows
        return self.notable_rows


# ── summarize_phases (pure) ─────────────────────────────────────────
def test_summarize_counts_and_phase3_includes_combined():
    rows = [
        {"phase": "Phase 3", "n": 56},
        {"phase": "Phase 2, Phase 3", "n": 2},   # counts toward Phase 3
        {"phase": "Phase 4", "n": 34},
        {"phase": "Phase 1", "n": 29},
        {"phase": None, "n": 34},                # null → "Not specified"
    ]
    s = summarize_phases(rows)
    assert s["total"] == 155
    assert s["phase3_total"] == 58            # 56 + 2 combined
    assert s["by_phase"]["Phase 4"] == 34
    assert "Not specified" in s["by_phase"]


def test_summarize_empty():
    s = summarize_phases([])
    assert s == {"total": 0, "by_phase": {}, "phase3_total": 0}


# ── format_grounding_block (pure) ───────────────────────────────────
def test_block_has_counts_citations_and_no_underreport_instruction():
    summary = {"total": 155, "by_phase": {"Phase 3": 58, "Phase 4": 34}, "phase3_total": 58}
    notable = [
        {"id": "NCT03914326", "phase": "Phase 3", "status": "Completed",
         "official_title": "Semaglutide Cardiovascular Outcomes Trial (SELECT)", "enrollment": 17604},
        {"id": "NCT03819153", "phase": "Phase 3", "status": "Completed",
         "official_title": "Effect of Semaglutide on renal outcomes (FLOW)", "enrollment": 3534},
    ]
    block = format_grounding_block(summary, notable, drug_name="semaglutide", as_of=AS_OF)
    assert "Phase 3 (incl. combined Phase 2/3): 58" in block
    assert "NCT03914326" in block and "NCT03819153" in block      # citations present
    assert "do NOT under-report" in block
    assert "2026-06-08" in block                                   # as-of stamp


def test_block_zero_trials_is_honest_not_invented():
    block = format_grounding_block({"total": 0, "by_phase": {}, "phase3_total": 0},
                                   [], drug_name="obscuredrug", as_of=AS_OF)
    assert "no trials on record" in block
    assert "do not invent" in block.lower()


# ── trial_grounding (integration via fake db) ───────────────────────
def test_trial_grounding_end_to_end():
    db = _FakeDB(
        phase_rows=[{"phase": "Phase 3", "n": 58}, {"phase": "Phase 4", "n": 34}],
        notable_rows=[{"id": "NCT03914326", "phase": "Phase 3", "status": "Completed",
                       "official_title": "SELECT", "enrollment": 17604}],
    )
    out = trial_grounding(db, "drug-sema", drug_name="semaglutide", as_of=AS_OF)
    assert out["summary"]["phase3_total"] == 58
    assert "58" in out["block"] and "NCT03914326" in out["block"]
    assert db.calls == 2  # phase-count + notable


def test_trial_grounding_skips_notable_query_when_no_phase3():
    db = _FakeDB(phase_rows=[{"phase": "Phase 1", "n": 3}], notable_rows=[])
    out = trial_grounding(db, "drug-x", drug_name="earlydrug", as_of=AS_OF)
    assert out["summary"]["phase3_total"] == 0
    assert db.calls == 1  # no notable query when there are no Phase-3 trials
    assert "Total 3 trials" in out["block"]
