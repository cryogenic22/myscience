"""Z3 — tests for the Engagement entity + 7-stage lifecycle FSM.

The FSM enforces walk-the-lifecycle discipline: forward progression between
adjacent stages, back-track allowed with audit, skip-ahead rejected. Stage
changes blocked when status is draft. Every mutation writes an audit-log
row. See specs/SPEC_Z3_engagement_entity.md.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from services.engagement import (
    LifecycleStage,
    EngagementStatus,
    Engagement,
    InvalidStageTransition,
    InvalidStatusTransition,
    InvalidSituation,
    create_engagement,
    get_engagement,
    list_engagements,
    advance_stage,
    set_status,
    STAGE_ORDER,
)

NOW = datetime(2026, 5, 30, tzinfo=timezone.utc)


def _row(**over):
    """Synthetic DB row matching the engagements table shape."""
    base = {
        "id": "e1",
        "name": "CagriSema Pre-Launch Wargame, May 2026",
        "asset": "drug:cagrisema",
        "sponsor": "novo_nordisk",
        "situation": "launch",
        "workshop_date": NOW,
        "stage": "brief",
        "status": "active",
        "scope": {},
        "created_by": "kapil",
        "created_at": NOW,
        "updated_at": NOW,
        "tenant_scope": None,
    }
    base.update(over)
    return base


def _db(row=None, rows=None):
    db = MagicMock()
    db.fetch_one = MagicMock(return_value=row or _row())
    db.fetch_all = MagicMock(return_value=rows or [])
    db.execute = MagicMock()
    return db


# ── Lifecycle order ────────────────────────────────────────────────


class TestStageOrder:
    def test_stage_order_matches_v7_doc(self):
        assert STAGE_ORDER == [
            LifecycleStage.BRIEF,
            LifecycleStage.SOURCES,
            LifecycleStage.DOSSIER,
            LifecycleStage.SYNTHESIS,
            LifecycleStage.GAPS,
            LifecycleStage.SCENARIOS,
            LifecycleStage.WORKSHOP,
        ]


# ── create_engagement ──────────────────────────────────────────────


class TestCreateEngagement:
    def test_creates_in_draft_status_at_brief_stage(self):
        db = _db()
        db.fetch_one.return_value = {"id": "new-id"}
        eid = create_engagement(
            db, name="X", asset="drug:cagrisema",
            situation="launch", created_by="kapil",
        )
        assert eid == "new-id"
        # INSERT should have status=draft, stage=brief
        call = db.fetch_one.call_args
        params = call.args[1]
        assert params.get("stage") == "brief"
        assert params.get("status") == "draft"

    def test_rejects_invalid_situation(self):
        db = _db()
        with pytest.raises(InvalidSituation):
            create_engagement(
                db, name="X", asset="drug:x",
                situation="not-a-real-situation",
                created_by="kapil",
            )

    def test_writes_audit_log_entry_on_create(self):
        db = _db()
        db.fetch_one.return_value = {"id": "new-id"}
        create_engagement(
            db, name="X", asset="drug:cagrisema",
            situation="launch", created_by="kapil",
        )
        # Look for an audit INSERT
        audit_calls = [
            c for c in (db.execute.call_args_list + db.fetch_one.call_args_list)
            if c.args and "engagement_audit_log" in c.args[0]
        ]
        assert audit_calls, "create must write to engagement_audit_log"


# ── get / list ─────────────────────────────────────────────────────


class TestGetEngagement:
    def test_returns_engagement(self):
        db = _db(row=_row())
        e = get_engagement(db, "e1")
        assert e is not None
        assert e.id == "e1"
        assert e.stage is LifecycleStage.BRIEF
        assert e.status is EngagementStatus.ACTIVE

    def test_unknown_id_returns_none(self):
        db = _db()
        db.fetch_one.return_value = None
        assert get_engagement(db, "nope") is None


class TestListEngagements:
    def test_returns_list(self):
        db = _db(rows=[_row(id="e1"), _row(id="e2", status="completed")])
        out = list_engagements(db)
        assert len(out) == 2

    def test_filters_by_status(self):
        # The SQL builder appends WHERE clauses; we just verify the call
        # included a status param when given.
        db = _db(rows=[_row(status="active")])
        list_engagements(db, status="active")
        call = db.fetch_all.call_args
        # Second positional arg is params (list)
        assert "active" in (call.args[1] if len(call.args) > 1 else [])


# ── advance_stage (the FSM) ────────────────────────────────────────


class TestAdvanceStage:
    def test_forward_one_step_works(self):
        db = _db(row=_row(stage="brief", status="active"))
        out = advance_stage(db, "e1", to_stage="sources",
                            rationale="brief complete, source register up", actor="kapil")
        assert out.stage is LifecycleStage.SOURCES

    def test_skip_ahead_rejected(self):
        db = _db(row=_row(stage="brief", status="active"))
        with pytest.raises(InvalidStageTransition):
            advance_stage(db, "e1", to_stage="scenarios",
                          rationale="why not", actor="kapil")

    def test_backtrack_allowed_with_audit(self):
        db = _db(row=_row(stage="dossier", status="active"))
        out = advance_stage(db, "e1", to_stage="sources",
                            rationale="new source landed; redo sources",
                            actor="kapil")
        assert out.stage is LifecycleStage.SOURCES
        # Audit entry must be written
        audit_calls = [
            c for c in (db.execute.call_args_list + db.fetch_one.call_args_list)
            if c.args and "engagement_audit_log" in c.args[0]
        ]
        assert audit_calls, "backtrack must write to audit log"

    def test_stage_change_blocked_when_draft(self):
        db = _db(row=_row(stage="brief", status="draft"))
        with pytest.raises(InvalidStageTransition):
            advance_stage(db, "e1", to_stage="sources",
                          rationale="x", actor="kapil")

    def test_rationale_required(self):
        db = _db(row=_row(stage="brief", status="active"))
        with pytest.raises(InvalidStageTransition):
            advance_stage(db, "e1", to_stage="sources", rationale="", actor="kapil")

    def test_unknown_engagement_raises_or_returns_none(self):
        db = _db()
        db.fetch_one.return_value = None
        # Either behavior is acceptable; pick one and lock it.
        with pytest.raises(InvalidStageTransition):
            advance_stage(db, "nope", to_stage="sources",
                          rationale="x", actor="kapil")


# ── set_status ─────────────────────────────────────────────────────


class TestSetStatus:
    def test_draft_to_active(self):
        db = _db(row=_row(status="draft"))
        out = set_status(db, "e1", to_status="active", actor="kapil")
        assert out.status is EngagementStatus.ACTIVE

    def test_draft_to_completed_rejected(self):
        db = _db(row=_row(status="draft"))
        with pytest.raises(InvalidStatusTransition):
            set_status(db, "e1", to_status="completed", actor="kapil")

    def test_workshop_active_to_completed(self):
        db = _db(row=_row(stage="workshop", status="active"))
        out = set_status(db, "e1", to_status="completed", actor="kapil")
        assert out.status is EngagementStatus.COMPLETED

    def test_non_workshop_active_to_completed_rejected(self):
        db = _db(row=_row(stage="dossier", status="active"))
        with pytest.raises(InvalidStatusTransition):
            set_status(db, "e1", to_status="completed", actor="kapil")

    def test_archive_always_allowed(self):
        for stage in ("brief", "scenarios", "workshop"):
            for status in ("draft", "active", "completed"):
                db = _db(row=_row(stage=stage, status=status))
                out = set_status(db, "e1", to_status="archived", actor="kapil")
                assert out.status is EngagementStatus.ARCHIVED


# ── Engagement dataclass invariants ────────────────────────────────


class TestEngagementInvariants:
    def test_constructs_with_valid_fields(self):
        e = Engagement(
            id="e1", name="X", asset="drug:cagrisema", sponsor="novo",
            situation="launch", workshop_date=NOW,
            stage=LifecycleStage.BRIEF, status=EngagementStatus.DRAFT,
            scope={}, created_by="kapil",
            created_at=NOW, updated_at=NOW, tenant_scope=None,
        )
        assert e.id == "e1"

    def test_rejects_empty_name(self):
        with pytest.raises(ValueError):
            Engagement(
                id="e1", name="   ", asset="drug:x", sponsor=None,
                situation="launch", workshop_date=None,
                stage=LifecycleStage.BRIEF, status=EngagementStatus.DRAFT,
                scope={}, created_by="x",
                created_at=NOW, updated_at=NOW, tenant_scope=None,
            )
