"""BE-2 — regression tests for production materiality 1% bug.

Per specs/BE_002_materiality_diagnostic.md these tests pin down the
four root causes so they cannot recur silently:

- RC-1: signals.materiality_score column must exist (not just _factors)
- RC-2: persist_score_to_signal must NOT silently swallow column-missing
        errors — it must raise so the bug is visible
- RC-3: a score_signal_row helper exists for ingestion paths to call
- RC-4: GET /signals returns materiality_score + materiality_factors

The tests use MockDB-style stubs so they run without a live Postgres.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest


# ════════════════════════════════════════════════════════════════════
# RC-2 · persist_score_to_signal raises on schema-class errors
# ════════════════════════════════════════════════════════════════════

class _UndefinedColumnError(Exception):
    """Stand-in for psycopg2.errors.UndefinedColumn / sqlalchemy ProgrammingError."""
    pgcode = "42703"  # the actual UndefinedColumn SQLSTATE


class TestPersistRaisesOnSchemaError:
    def test_persist_raises_when_column_missing(self):
        """RC-2: a missing-column error must NOT be swallowed."""
        from services.materiality import (
            persist_score_to_signal,
            MaterialityResult,
            MaterialityFactor,
        )

        # Synthesize a real result so the persister has something to write.
        result = MaterialityResult(
            score=72.0,
            factors={
                "source_tier": MaterialityFactor("source_tier", 1, 1.0, 0.30, 30.0),
                "entity_criticality": MaterialityFactor("entity_criticality", "focal", 1.0, 0.30, 30.0),
                "claim_type": MaterialityFactor("claim_type", "clinical_readout", 1.0, 0.25, 25.0),
                "recency": MaterialityFactor("recency", {"days": 0}, 1.0, 0.15, 15.0),
            },
        )

        db = MagicMock()
        db.execute.side_effect = _UndefinedColumnError(
            'column "materiality_score" of relation "signals" does not exist'
        )

        # MUST raise — silent swallow is the RC-2 bug.
        with pytest.raises(_UndefinedColumnError):
            persist_score_to_signal(db, signal_id="sig-1", result=result)

    def test_persist_does_not_misclassify_connection_does_not_exist(self):
        """Red-team: an error like 'connection does not exist' must NOT
        be treated as a schema error — that's a transient runtime
        failure, not a missing column."""
        from services.materiality import (
            persist_score_to_signal,
            MaterialityResult,
            MaterialityFactor,
        )

        result = MaterialityResult(
            score=50.0,
            factors={
                "source_tier": MaterialityFactor("source_tier", 2, 0.7, 0.30, 21.0),
                "entity_criticality": MaterialityFactor("entity_criticality", "watched", 0.5, 0.30, 15.0),
                "claim_type": MaterialityFactor("claim_type", "other", 0.3, 0.25, 7.5),
                "recency": MaterialityFactor("recency", {"days": 30}, 0.5, 0.15, 7.5),
            },
        )

        db = MagicMock()
        db.execute.side_effect = RuntimeError("connection does not exist")

        # Should NOT raise — runtime "does not exist" without a relation
        # kind keyword is transient, not schema.
        persist_score_to_signal(db, signal_id="sig-3", result=result)

    def test_persist_swallows_transient_errors(self):
        """Best-effort still applies for transient failures (deadlock, conn loss).

        Schema errors must raise; transient errors that aren't schema-class
        may still log-and-skip so a single broken row doesn't abort batch
        backfills.
        """
        from services.materiality import (
            persist_score_to_signal,
            MaterialityResult,
            MaterialityFactor,
        )

        result = MaterialityResult(
            score=42.0,
            factors={
                "source_tier": MaterialityFactor("source_tier", 3, 0.4, 0.30, 12.0),
                "entity_criticality": MaterialityFactor("entity_criticality", "other", 0.2, 0.30, 6.0),
                "claim_type": MaterialityFactor("claim_type", "other", 0.3, 0.25, 7.5),
                "recency": MaterialityFactor("recency", {"days": 60}, 0.25, 0.15, 3.75),
            },
        )

        # A transient runtime error (no pgcode on the exception) should be
        # logged but not raised.
        db = MagicMock()
        db.execute.side_effect = RuntimeError("temporary connection blip")

        # Should NOT raise.
        persist_score_to_signal(db, signal_id="sig-2", result=result)


# ════════════════════════════════════════════════════════════════════
# RC-3 · score_signal_row helper for ingestion paths
# ════════════════════════════════════════════════════════════════════

class TestScoreSignalRow:
    def test_helper_exists(self):
        """RC-3: there must be a one-call helper that takes a signals row
        and returns a MaterialityResult so ingestion paths can call it."""
        from services import materiality
        assert hasattr(materiality, "score_signal_row"), (
            "BE-2 RC-3: services.materiality.score_signal_row(...) must exist"
        )

    def test_helper_maps_row_to_inputs(self):
        """The helper should extract source_tier, entity_criticality,
        claim_type, age_days from a signals row + companion fields."""
        from services.materiality import score_signal_row, MaterialityResult

        signal_row = {
            "id": "sig-100",
            "primary_entity_type": "drug",
            "primary_entity_id": "drug-tirzepatide",
            "headline": "Tirzepatide Phase 3 readout: HbA1c -2.4%",
            "kbq_tags": ["clinical"],
            "trust_score": 0.95,
            "impact_score": 0.85,
            "created_at": datetime.now(timezone.utc) - timedelta(days=5),
            # Companion fields (best-effort lookups by score_signal_row):
            "source_tier": 1,
            "entity_criticality": "focal",
            "claim_type": "clinical_readout",
        }

        db = MagicMock()
        db.fetch_one.return_value = None  # no active config → defaults
        db.execute.return_value = None

        result = score_signal_row(db, signal_row, persist=False)
        assert isinstance(result, MaterialityResult)
        assert 80 <= result.score <= 100, (
            f"high-tier focal clinical readout @ 5 days should score >=80, got {result.score}"
        )

    def test_helper_handles_missing_companion_fields(self):
        """If a signal row has no source_tier / criticality / claim_type
        we still get a finite score using documented defaults."""
        from services.materiality import score_signal_row

        signal_row = {
            "id": "sig-200",
            "primary_entity_type": "drug",
            "primary_entity_id": "drug-x",
            "headline": "Press release: company X",
            "trust_score": 0.5,
            "impact_score": 0.3,
            "created_at": datetime.now(timezone.utc) - timedelta(days=180),
        }

        db = MagicMock()
        db.fetch_one.return_value = None
        db.execute.return_value = None

        result = score_signal_row(db, signal_row, persist=False)
        # Default-everything path: tier 3, other, other, 180-day age.
        # 0.30*0.4 + 0.30*0.2 + 0.25*0.3 + 0.15*~0.016 ≈ 25.7
        assert 0 < result.score < 100
        assert result.factors["source_tier"].factor_value == pytest.approx(0.4, abs=1e-3)
        assert result.factors["entity_criticality"].factor_value == pytest.approx(0.2, abs=1e-3)


# ════════════════════════════════════════════════════════════════════
# RC-4 · GET /signals returns materiality fields
# ════════════════════════════════════════════════════════════════════

class TestSignalsAPIIncludesMateriality:
    _DEFAULT_FACTORS = object()

    def _make_db_with_signal(self, *, materiality_score=72, materiality_factors=_DEFAULT_FACTORS):
        """Return a fake DB that serves a single signal row when /signals queries it."""
        if materiality_factors is self._DEFAULT_FACTORS:
            materiality_factors = {
                "source_tier": {"input": 1, "value": 1.0, "weight": 0.30, "contribution": 30.0},
                "entity_criticality": {"input": "focal", "value": 1.0, "weight": 0.30, "contribution": 30.0},
                "claim_type": {"input": "clinical_readout", "value": 1.0, "weight": 0.25, "contribution": 25.0},
                "recency": {"input": {"days": 5}, "value": 0.89, "weight": 0.15, "contribution": 13.4},
            }

        signal_row = {
            "id": "sig-321",
            "event_id": "evt-1",
            "kbq_tags": ["clinical"],
            "headline": "Tirzepatide Phase 3 readout positive",
            "summary": "HbA1c -2.4%",
            "direction": "positive",
            "confidence_tier": "confirmed",
            "trust_score": 0.95,
            "impact_tier": "high",
            "impact_score": 0.85,
            "rule_version_id": "v1",
            "primary_entity_type": "drug",
            "primary_entity_id": "drug-1",
            "primary_entity_name": "tirzepatide",
            "related_entity_ids": [],
            "evidence_document_ids": ["doc-1"],
            "status": "shipped",
            "superseded_by": None,
            "supersedence_reason": None,
            "created_at": datetime.now(timezone.utc),
            "reviewed_by": None,
            "reviewed_at": None,
            "shipped_at": datetime.now(timezone.utc),
            "materiality_score": materiality_score,
            "materiality_factors": materiality_factors,
        }

        db = MagicMock()
        db.fetch_all.return_value = [signal_row]
        db.fetch_one.return_value = signal_row
        return db

    def test_list_returns_materiality_fields(self):
        from fastapi.testclient import TestClient
        from api.app import create_app
        from api.deps import get_db

        db = self._make_db_with_signal()
        app = create_app()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)

        r = client.get("/signals")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["signals"], "expected at least one signal"
        first = body["signals"][0]
        assert "materiality_score" in first, (
            "BE-2 RC-4: /signals must return materiality_score"
        )
        assert "materiality_factors" in first, (
            "BE-2 RC-4: /signals must return materiality_factors"
        )
        assert first["materiality_score"] == 72
        assert first["materiality_factors"]["source_tier"]["value"] == 1.0

    def test_detail_returns_materiality_fields(self):
        from fastapi.testclient import TestClient
        from api.app import create_app
        from api.deps import get_db

        db = self._make_db_with_signal(materiality_score=88)
        app = create_app()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)

        r = client.get("/signals/sig-321")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("materiality_score") == 88
        assert "materiality_factors" in body

    def test_list_handles_null_materiality_gracefully(self):
        """Pre-backfill rows have NULL materiality_score; API must still respond."""
        from fastapi.testclient import TestClient
        from api.app import create_app
        from api.deps import get_db

        db = self._make_db_with_signal(materiality_score=None, materiality_factors=None)
        app = create_app()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)

        r = client.get("/signals")
        assert r.status_code == 200, r.text
        first = r.json()["signals"][0]
        # Field present, value null — frontend can render "—" rather than 1%
        assert first["materiality_score"] is None
        assert first["materiality_factors"] is None


# ════════════════════════════════════════════════════════════════════
# RC-1 · migration sanity (string check on the migration file)
# ════════════════════════════════════════════════════════════════════

class TestMigrationAddsMaterialityScoreColumn:
    def test_migration_065_exists_and_adds_column(self):
        """RC-1: migration 065 must add signals.materiality_score with a
        sane CHECK and an index for framing-trigger threshold queries."""
        from pathlib import Path

        path = Path(__file__).parent.parent / "schema" / "migrations" / "065_signals_materiality_score.sql"
        assert path.exists(), f"BE-2 RC-1: missing migration {path.name}"

        sql = path.read_text(encoding="utf-8").lower()
        assert "alter table signals" in sql, "must alter signals table"
        assert "add column" in sql and "materiality_score" in sql, (
            "must add materiality_score column"
        )
        assert "between 0 and 100" in sql, "must constrain to 0..100"
        assert "create index" in sql and "materiality_score" in sql, (
            "must index materiality_score for threshold queries"
        )


# ════════════════════════════════════════════════════════════════════
# Backfill script smoke test
# ════════════════════════════════════════════════════════════════════

class TestBackfillScript:
    def test_backfill_module_importable(self):
        """The backfill script module must import cleanly."""
        import scripts.backfill_materiality_scores as mod
        assert hasattr(mod, "run"), "backfill must expose run(...)"

    def test_backfill_processes_null_score_rows(self):
        """run() pulls rows with NULL score, scores them, and persists."""
        from scripts.backfill_materiality_scores import run

        # Three signals: two need scoring, one already scored.
        signals = [
            {
                "id": "sig-A",
                "primary_entity_type": "drug",
                "primary_entity_id": "drug-1",
                "headline": "FDA approval",
                "kbq_tags": ["regulatory"],
                "trust_score": 0.9,
                "impact_score": 0.85,
                "created_at": datetime.now(timezone.utc),
                "source_tier": 1,
                "entity_criticality": "focal",
                "claim_type": "regulatory_action",
                "materiality_score": None,
            },
            {
                "id": "sig-B",
                "primary_entity_type": "drug",
                "primary_entity_id": "drug-2",
                "headline": "Earnings",
                "kbq_tags": ["financial"],
                "trust_score": 0.7,
                "impact_score": 0.4,
                "created_at": datetime.now(timezone.utc) - timedelta(days=120),
                "source_tier": 2,
                "entity_criticality": "watched",
                "claim_type": "earnings_commentary",
                "materiality_score": None,
            },
        ]
        persisted = []

        db = MagicMock()
        db.fetch_all.side_effect = lambda sql, params=None: (
            signals if "materiality_score is null" in (sql or "").lower() else []
        )
        db.fetch_one.return_value = None  # no active config — defaults

        def _exec(sql, params=None):
            s = (sql or "").lower()
            if "update signals" in s and "materiality_score" in s and params:
                persisted.append({"score": params[0], "id": str(params[-1])})
            return None

        db.execute.side_effect = _exec

        summary = run(db, batch=10, dry_run=False)
        assert summary["scored"] == 2
        assert len(persisted) == 2
        # Both scores should be > 1 (and varied)
        scores = sorted(p["score"] for p in persisted)
        assert scores[0] > 1, "regulatory action signal must score > 1"
        assert scores[0] != scores[1], "scores must vary by inputs (not stuck at default)"

    def test_backfill_dry_run_does_not_persist(self):
        from scripts.backfill_materiality_scores import run

        db = MagicMock()
        db.fetch_all.return_value = [
            {
                "id": "sig-X",
                "primary_entity_type": "drug",
                "primary_entity_id": "drug-1",
                "headline": "x",
                "trust_score": 0.5,
                "impact_score": 0.5,
                "created_at": datetime.now(timezone.utc),
                "source_tier": 3,
                "entity_criticality": "other",
                "claim_type": "other",
                "materiality_score": None,
            }
        ]
        db.fetch_one.return_value = None

        summary = run(db, batch=10, dry_run=True)
        assert summary["scored"] == 1
        # No UPDATE signals … materiality_score should fire in dry-run
        update_calls = [
            c for c in db.execute.call_args_list
            if c.args and "update signals" in str(c.args[0]).lower()
            and "materiality_score" in str(c.args[0]).lower()
        ]
        assert update_calls == [], "dry-run must not persist"
