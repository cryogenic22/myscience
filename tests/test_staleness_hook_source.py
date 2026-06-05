"""D1: StalenessHook source-level freshness check.

The per-record staleness map historically omitted openfda_labels / openfda_faers
— the two sources that silently went 105 days stale. This pins the new
source-level check that reads scheduler.config.FRESHNESS_SLA_DAYS, so every
*scheduled* source is covered automatically.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from integration.pipeline_hooks import HookContext, StalenessHook


class _FakeDB:
    """Routes fetch_one by SQL substring; returns a configured freshness row."""

    def __init__(self, newest, n):
        self._newest, self._n = newest, n

    def fetch_one(self, sql, params=None):
        s = sql.lower()
        if "set record_status" in s:  # the per-record UPDATE...RETURNING
            return {"cnt": 0}
        if "max(" in s:  # source freshness probe
            return {"newest": self._newest, "n": self._n}
        return None


def _hook(newest, n):
    cfg = MagicMock()
    cfg.pipeline.freshness_max_days = 30
    # No domain pack → uses the built-in per-record map (which omits labels)
    return StalenessHook(_FakeDB(newest, n), cfg, domain_pack=None)


def _ctx(source):
    return HookContext(hook_point="ON_RUN_COMPLETE", source_type=source, etl_run_id="r1")


def test_stale_labels_source_flagged():
    """labels newest 105d old (SLA 14d) → source_stale True."""
    old = datetime.now(timezone.utc) - timedelta(days=105)
    res = _hook(old, n=185).execute(_ctx("openfda_labels"))
    assert res.data["source_stale"] is True
    assert "OVER SLA" in res.message


def test_fresh_labels_source_not_flagged():
    fresh = datetime.now(timezone.utc) - timedelta(days=1)
    res = _hook(fresh, n=185).execute(_ctx("openfda_labels"))
    assert res.data["source_stale"] is False


def test_empty_source_flagged():
    res = _hook(None, n=0).execute(_ctx("pmc"))
    assert res.data["source_stale"] is True


def test_unscheduled_source_not_flagged():
    """A source not in FRESHNESS_SLA_DAYS is simply not source-checked."""
    res = _hook(None, n=0).execute(_ctx("user_document"))
    assert res.data["source_stale"] is False
