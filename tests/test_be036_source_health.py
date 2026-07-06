"""BE-36 — source health + degradation notice tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ════════════════════════════════════════════════════════════════════
# Migration shape
# ════════════════════════════════════════════════════════════════════

def test_migration_075_adds_health_column():
    sql = (Path(__file__).parent.parent / "schema" / "migrations"
           / "075_source_health_column.sql").read_text(encoding="utf-8").lower()
    assert "alter table sources" in sql
    assert "health" in sql
    for v in ("healthy", "degraded", "down", "unknown"):
        assert v in sql


# ════════════════════════════════════════════════════════════════════
# _classify
# ════════════════════════════════════════════════════════════════════

class TestClassify:
    @pytest.mark.parametrize("hours,expected", [
        (None,    "unknown"),
        (1.0,     "healthy"),
        (24.0,    "healthy"),
        (24.001,  "degraded"),
        (72.0,    "degraded"),
        (72.001,  "down"),
        (200.0,   "down"),
    ])
    def test_buckets(self, hours, expected):
        from services.source_health import _classify
        assert _classify(hours) == expected


# ════════════════════════════════════════════════════════════════════
# check_health
# ════════════════════════════════════════════════════════════════════

class TestCheckHealth:
    def test_marks_each_source(self):
        from services.source_health import check_health

        now = datetime.now(timezone.utc)
        db = MagicMock()
        db.fetch_all.return_value = [
            {"source_id": "fda",        "last_success_at": now - timedelta(hours=2)},
            {"source_id": "pubmed",     "last_success_at": now - timedelta(hours=48)},
            {"source_id": "cms_partd",  "last_success_at": now - timedelta(hours=200)},
            {"source_id": "fresh",      "last_success_at": None},
        ]
        out = check_health(db)
        by_id = {s.source_id: s for s in out}
        assert by_id["fda"].health == "healthy"
        assert by_id["pubmed"].health == "degraded"
        assert by_id["cms_partd"].health == "down"
        assert by_id["fresh"].health == "unknown"

    def test_persist_failure_is_non_fatal(self):
        from services.source_health import check_health

        db = MagicMock()
        db.fetch_all.return_value = [
            {"source_id": "fda", "last_success_at": datetime.now(timezone.utc)},
        ]
        db.execute.side_effect = RuntimeError("table missing")
        # Must not raise even though the UPDATE fails.
        check_health(db)


# ════════════════════════════════════════════════════════════════════
# degradation_notice
# ════════════════════════════════════════════════════════════════════

class TestDegradationNotice:
    def test_returns_none_when_all_healthy(self):
        from services.source_health import degradation_notice
        db = MagicMock()
        db.fetch_all.return_value = [
            {"source_id": "fda",    "health": "healthy"},
            {"source_id": "pubmed", "health": "healthy"},
        ]
        assert degradation_notice(db, ["fda", "pubmed"]) is None

    def test_returns_string_when_degraded(self):
        from services.source_health import degradation_notice
        db = MagicMock()
        db.fetch_all.return_value = [
            {"source_id": "fda",    "health": "healthy"},
            {"source_id": "pubmed", "health": "degraded"},
        ]
        out = degradation_notice(db, ["fda", "pubmed"])
        assert out is not None
        assert "pubmed" in out
        assert "degraded" in out

    def test_skips_unknown_only(self):
        from services.source_health import degradation_notice
        db = MagicMock()
        db.fetch_all.return_value = [
            {"source_id": "weird", "health": "unknown"},
        ]
        # 'unknown' alone shouldn't trigger a notice (don't claim a
        # source is broken if we just don't know yet).
        assert degradation_notice(db, ["weird"]) is None

    def test_handles_empty_input(self):
        from services.source_health import degradation_notice
        assert degradation_notice(MagicMock(), []) is None
