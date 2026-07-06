"""BE-25 — licence-model migration + /sources/licences endpoint tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ════════════════════════════════════════════════════════════════════
# Migration 070 shape
# ════════════════════════════════════════════════════════════════════

class TestMigration070:
    def _sql(self) -> str:
        path = (
            Path(__file__).parent.parent
            / "schema" / "migrations" / "070_source_licence_fields.sql"
        )
        assert path.exists(), f"missing {path.name}"
        return path.read_text(encoding="utf-8").lower()

    def test_adds_three_columns(self):
        sql = self._sql()
        for col in ("annual_cost_usd", "licence_type", "phase"):
            assert col in sql, f"missing column {col}"

    def test_check_constraint_on_licence_type(self):
        sql = self._sql()
        assert "public_domain" in sql and "commercial" in sql and "enterprise" in sql

    def test_idempotent(self):
        sql = self._sql()
        assert "if not exists" in sql


# ════════════════════════════════════════════════════════════════════
# /sources/licences endpoint
# ════════════════════════════════════════════════════════════════════

def _make_row(source_id, *, cost=0, status="not_applicable",
              phase="now", licence_type="public_domain",
              renewal_at=None, active=True):
    return {
        "source_id": source_id,
        "display_name": source_id.upper(),
        "tier": 1,
        "licence_type": licence_type,
        "license_status": status,
        "annual_cost_usd": cost,
        "license_renewal_at": renewal_at,
        "active": active,
        "phase": phase,
    }


class TestListLicences:
    def _call(self, rows):
        from api.routes.sources import list_licences
        db = MagicMock()
        db.fetch_all.return_value = rows
        user = {"id": "u-1", "role": "viewer"}
        return list_licences(user=user, db=db)

    def test_empty_when_db_fails(self):
        from api.routes.sources import list_licences
        db = MagicMock()
        db.fetch_all.side_effect = RuntimeError("table missing")
        out = list_licences(user={"id": "u", "role": "viewer"}, db=db)
        assert out["sources"] == []
        assert out["total_today"] == 0
        assert out["projected_after_phase2"] == 0

    def test_health_buckets(self):
        soon = datetime.utcnow() + timedelta(days=10)
        far = datetime.utcnow() + timedelta(days=400)
        past = datetime.utcnow() - timedelta(days=5)
        out = self._call([
            _make_row("a", renewal_at=soon),     # expiring
            _make_row("b", renewal_at=far),      # active
            _make_row("c", renewal_at=past),     # expired
            _make_row("d", status="expired"),    # expired (status)
        ])
        by_id = {s["source_id"]: s for s in out["sources"]}
        assert by_id["a"]["health"] == "expiring"
        assert by_id["b"]["health"] == "active"
        assert by_id["c"]["health"] == "expired"
        assert by_id["d"]["health"] == "expired"

    def test_totals_aggregate_by_phase(self):
        out = self._call([
            _make_row("a", cost=100, phase="now"),       # both totals
            _make_row("b", cost=50, phase="phase1"),     # both totals
            _make_row("c", cost=200, phase="phase2"),    # projected only
            _make_row("d", cost=300, phase="phase3"),    # neither
        ])
        # total_today = phase=now + phase=phase1 (rolled-out) = 150
        assert out["total_today"] == 150
        # projected_after_phase2 = now + phase1 + phase2 = 350
        assert out["projected_after_phase2"] == 350

    def test_inactive_excluded_from_total_today(self):
        out = self._call([
            _make_row("a", cost=100, phase="now", active=False),
        ])
        assert out["total_today"] == 0
        assert out["projected_after_phase2"] == 100

    def test_currency_is_usd(self):
        out = self._call([])
        assert out["currency"] == "USD"
