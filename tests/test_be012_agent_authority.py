"""BE-12 — agent authority service tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ════════════════════════════════════════════════════════════════════
# Migration shape
# ════════════════════════════════════════════════════════════════════

class TestMigration072:
    def test_creates_authority_tables(self):
        path = Path(__file__).parent.parent / "schema" / "migrations" / "072_agent_authority.sql"
        sql = path.read_text(encoding="utf-8").lower()
        assert "create table" in sql
        assert "agent_authority" in sql
        assert "agent_authority_promotions" in sql
        # 1..5 spectrum CHECK
        assert "between 1 and 5" in sql


# ════════════════════════════════════════════════════════════════════
# Service
# ════════════════════════════════════════════════════════════════════

def _row(agent="strategist", st="launch_timing",
         level=1, score=0.5, count=0, last_promoted=None):
    return {
        "agent": agent,
        "scenario_type": st,
        "current_level": level,
        "calibration_score": score,
        "scenario_count": count,
        "last_promoted_at": last_promoted,
    }


class TestRecordOutcome:
    def test_first_datapoint_inserts_row(self):
        from services.agent.authority import record_outcome
        db = MagicMock()
        db.fetch_one.return_value = None  # no existing row
        out = record_outcome(db, agent="strategist", scenario_type="launch_timing", correct=True)
        assert out.scenario_count == 1
        assert out.calibration_score == 1.0
        # Insert call fired
        sqls = [str(c.args[0]).lower() for c in db.execute.call_args_list if c.args]
        assert any("insert into agent_authority" in s for s in sqls)

    def test_existing_row_updates_score(self):
        from services.agent.authority import record_outcome
        db = MagicMock()
        # 5 prior outcomes, all correct (score = 1.0). New one wrong → 5/6.
        db.fetch_one.side_effect = [
            _row(level=1, score=1.0, count=5),
            _row(level=1, score=5/6, count=6),
        ]
        out = record_outcome(db, agent="x", scenario_type="y", correct=False)
        assert out.scenario_count == 6
        assert out.calibration_score == pytest.approx(5/6, abs=1e-6)

    def test_promotion_at_threshold(self):
        from services.agent.authority import record_outcome, WINDOW_SIZE
        db = MagicMock()
        # 13 correct already; adding the 14th correct → score 14/14 ≥ 0.70
        db.fetch_one.side_effect = [
            _row(level=2, score=13/13, count=13),
            _row(level=3, score=1.0, count=14, last_promoted=datetime.now(timezone.utc)),
        ]
        out = record_outcome(db, agent="x", scenario_type="y", correct=True)
        assert out.current_level == 3
        # Promotion log inserted
        sqls = [str(c.args[0]).lower() for c in db.execute.call_args_list if c.args]
        assert any("insert into agent_authority_promotions" in s for s in sqls)

    def test_demotion_at_threshold(self):
        from services.agent.authority import record_outcome
        db = MagicMock()
        # 13 wrong, then 14th wrong → score 0.0 ≤ 0.50, level 3 → 2
        db.fetch_one.side_effect = [
            _row(level=3, score=0.0, count=13),
            _row(level=2, score=0.0, count=14, last_promoted=datetime.now(timezone.utc)),
        ]
        out = record_outcome(db, agent="x", scenario_type="y", correct=False)
        assert out.current_level == 2

    def test_no_promotion_below_window(self):
        from services.agent.authority import record_outcome
        db = MagicMock()
        # Only 5 datapoints → no promotion no matter the score.
        db.fetch_one.side_effect = [
            _row(level=1, score=1.0, count=4),
            _row(level=1, score=1.0, count=5),
        ]
        out = record_outcome(db, agent="x", scenario_type="y", correct=True)
        assert out.current_level == 1


class TestManualOverride:
    def test_update_authority_writes_promotion_log_with_actor(self):
        from services.agent.authority import update_authority
        db = MagicMock()
        db.fetch_one.side_effect = [
            _row(level=2, score=0.6, count=10),  # GET inside update_authority
            _row(level=4, score=0.6, count=10, last_promoted=datetime.now(timezone.utc)),  # final GET
        ]
        out = update_authority(
            db, agent="strategist", scenario_type="launch_timing",
            new_level=4, actor_user_id="u-admin",
        )
        assert out.current_level == 4
        sqls = [str(c.args[0]).lower() for c in db.execute.call_args_list if c.args]
        assert any("insert into agent_authority_promotions" in s for s in sqls)

    def test_update_authority_rejects_out_of_range(self):
        from services.agent.authority import update_authority
        db = MagicMock()
        with pytest.raises(ValueError):
            update_authority(db, agent="x", scenario_type="y", new_level=99, actor_user_id="u")
