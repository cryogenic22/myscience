"""BE-17 — 4-dimension confidence breakdown tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


# ════════════════════════════════════════════════════════════════════
# compute_confidence_assessment
# ════════════════════════════════════════════════════════════════════

class TestShape:
    def test_returns_spec_shape(self):
        from services.confidence import compute_confidence_assessment
        out = compute_confidence_assessment([{"source_id": "pubmed"}])
        assert "composite" in out
        assert "by_dimension" in out
        for key in ("evidence_quality", "source_diversity", "recency", "calibration"):
            assert key in out["by_dimension"]

    def test_empty_evidence_returns_zeros(self):
        from services.confidence import compute_confidence_assessment
        out = compute_confidence_assessment([])
        assert out["composite"] == 0.0
        for v in out["by_dimension"].values():
            assert v == 0.0

    def test_none_evidence_handled(self):
        from services.confidence import compute_confidence_assessment
        out = compute_confidence_assessment(None)
        assert out["composite"] == 0.0


class TestEvidenceQuality:
    def test_t1_only_max(self):
        from services.confidence import compute_confidence_assessment
        out = compute_confidence_assessment([
            {"source_tier": "T1", "source_id": "fda"},
        ])
        assert out["by_dimension"]["evidence_quality"] == pytest.approx(1.0, abs=1e-3)

    def test_t3_only_lower(self):
        from services.confidence import compute_confidence_assessment
        out = compute_confidence_assessment([
            {"source_tier": "T3", "source_id": "pubmed"},
        ])
        assert out["by_dimension"]["evidence_quality"] == pytest.approx(0.4, abs=1e-3)

    def test_unknown_tier_defaults_to_t3(self):
        from services.confidence import compute_confidence_assessment
        out = compute_confidence_assessment([
            {"source_id": "weird-source-no-tier"},
        ])
        assert out["by_dimension"]["evidence_quality"] == pytest.approx(0.4, abs=1e-3)


class TestSourceDiversity:
    def test_single_source_zero(self):
        from services.confidence import compute_confidence_assessment
        out = compute_confidence_assessment([
            {"source_id": "pubmed"}, {"source_id": "pubmed"},
        ])
        assert out["by_dimension"]["source_diversity"] == 0.0

    def test_evenly_spread_high(self):
        from services.confidence import compute_confidence_assessment
        out = compute_confidence_assessment([
            {"source_id": "fda"},
            {"source_id": "pubmed"},
            {"source_id": "sec_edgar"},
            {"source_id": "biorxiv"},
        ])
        # 1 - 4*(1/4)^2 = 0.75
        assert out["by_dimension"]["source_diversity"] == pytest.approx(0.75, abs=1e-3)


class TestRecency:
    def test_fresh_evidence_high(self):
        from services.confidence import compute_confidence_assessment
        now = datetime.now(timezone.utc)
        out = compute_confidence_assessment([
            {"source_id": "fda", "published_at": now},
        ])
        assert out["by_dimension"]["recency"] >= 0.99

    def test_old_evidence_low(self):
        from services.confidence import compute_confidence_assessment
        old = datetime.now(timezone.utc) - timedelta(days=1000)
        out = compute_confidence_assessment([
            {"source_id": "fda", "published_at": old},
        ])
        assert out["by_dimension"]["recency"] < 0.05

    def test_undated_neutral(self):
        from services.confidence import compute_confidence_assessment
        out = compute_confidence_assessment([{"source_id": "fda"}])
        assert out["by_dimension"]["recency"] == pytest.approx(0.5, abs=1e-3)


class TestCalibration:
    def test_uses_calibration_map(self):
        from services.confidence import compute_confidence_assessment
        out = compute_confidence_assessment(
            [{"source_id": "pubmed"}, {"source_id": "fda"}],
            calibration_map={"pubmed": 0.85, "fda": 0.95},
        )
        # Average of the two known rates
        assert out["by_dimension"]["calibration"] == pytest.approx(0.90, abs=1e-3)

    def test_unknown_source_gets_neutral(self):
        from services.confidence import compute_confidence_assessment
        out = compute_confidence_assessment(
            [{"source_id": "weird"}],
            calibration_map=None,
        )
        # Default 0.7 for unknown
        assert out["by_dimension"]["calibration"] == pytest.approx(0.7, abs=1e-3)

    def test_dedups_repeated_sources(self):
        """Two citations from the same source count once for calibration."""
        from services.confidence import compute_confidence_assessment
        out = compute_confidence_assessment(
            [{"source_id": "pubmed"}, {"source_id": "pubmed"}],
            calibration_map={"pubmed": 0.85},
        )
        assert out["by_dimension"]["calibration"] == pytest.approx(0.85, abs=1e-3)


class TestComposite:
    def test_composite_weighted_mean(self):
        """Composite uses the documented weights summing to 1.0."""
        from services.confidence import compute_confidence_assessment
        from datetime import datetime, timezone

        # Simple case: T1 / single source / fresh / high calibration
        out = compute_confidence_assessment(
            [{"source_id": "fda", "source_tier": "T1",
              "published_at": datetime.now(timezone.utc)}],
            calibration_map={"fda": 0.95},
        )
        # eq=1.0 (T1), sd=0.0 (one source), rec≈1.0, cal=0.95
        # composite ≈ 0.35*1 + 0.20*0 + 0.20*1 + 0.25*0.95 ≈ 0.7875
        assert 0.78 <= out["composite"] <= 0.80

    def test_composite_clamped_to_unit_interval(self):
        from services.confidence import compute_confidence_assessment
        out = compute_confidence_assessment([])
        assert 0.0 <= out["composite"] <= 1.0
