"""C3 (learning loops) — query → quality → research trigger.

A weak/low-confidence answer (gap detected) auto-spawns a deep_research_jobs
row to fill the gap — the trigger the dormant research path never had.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from services.gap_research import maybe_trigger_gap_research, GAP_TRIGGERS


def _db_no_open_job():
    """A db whose dedup check finds no existing open job, and whose
    create_research_job (via ChatWorkspaceService) returns a job row."""
    db = MagicMock()
    # 1st fetch_one = dedup check (None) ; 2nd = workspace.get_research_job after insert
    db.fetch_one.side_effect = [
        None,  # _has_open_gap_job
        {  # get_research_job result
            "id": "99999999-9999-9999-9999-999999999999",
            "scope_key": "default", "question": "q",
            "options": {"auto_gap_research": True},
            "status": "queued",
        },
    ]
    return db


def test_low_confidence_spawns_research_job():
    db = _db_no_open_job()
    job = maybe_trigger_gap_research(
        db, question="What is obscure-drug-xyz?",
        gap_type="low_confidence", gap_details={"confidence": 0.2},
    )
    assert job is not None
    assert job["id"] == "99999999-9999-9999-9999-999999999999"
    # an INSERT into deep_research_jobs happened
    assert any(
        "insert into deep_research_jobs" in str(c[0][0]).lower()
        for c in db.execute.call_args_list
    )


def test_missing_entity_and_low_evidence_also_trigger():
    for gap in ("missing_entity", "low_evidence"):
        db = _db_no_open_job()
        job = maybe_trigger_gap_research(db, question="q?", gap_type=gap)
        assert job is not None, f"{gap} should trigger"
    assert GAP_TRIGGERS == {"missing_entity", "low_confidence", "low_evidence"}


def test_no_gap_does_not_trigger():
    db = MagicMock()
    job = maybe_trigger_gap_research(db, question="q", gap_type=None)
    assert job is None
    assert not db.execute.called


def test_dedup_skips_when_open_job_exists():
    db = MagicMock()
    db.fetch_one.return_value = {"?column?": 1}  # _has_open_gap_job → truthy
    job = maybe_trigger_gap_research(db, question="q", gap_type="low_confidence")
    assert job is None  # already queued → no duplicate


def test_empty_question_does_not_trigger():
    db = MagicMock()
    assert maybe_trigger_gap_research(db, question="  ", gap_type="low_confidence") is None


def test_helper_never_raises_on_db_error():
    db = MagicMock()
    db.fetch_one.side_effect = RuntimeError("db down")
    # dedup check swallows, then create path also guarded — returns None, no raise
    job = maybe_trigger_gap_research(db, question="q", gap_type="low_confidence")
    assert job is None
