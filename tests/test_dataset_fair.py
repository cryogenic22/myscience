"""DataHub D-API-2 — source-level FAIR aggregate for the Catalog grid ring.

DB-free: tests the pure derivation (`_dataset_fair` / `_license_openness`) that
turns dataset_catalog columns into a composite + per-dimension breakdown. The
honesty contract is the point: a dimension is null when its input is absent
(never coerced), the composite is the weighted mean of only the present
dimensions, and a 0-row dataset is NOT accessible.
"""
import pytest

from api.routes.catalog import _dataset_fair, _license_openness


def test_license_openness_tiers():
    assert _license_openness("Public Domain (US Government)") == 1.0
    assert _license_openness("NLM Terms of Use") == 0.7
    assert _license_openness("Proprietary") == 0.4
    assert _license_openness(None) is None      # unknown → null, not coerced
    assert _license_openness("") is None


def test_fully_profiled_dataset_scores_all_dimensions():
    row = {"completeness_pct": 87.4, "quality_score_avg": 0.956,
           "row_count": 5856, "license_name": "Public Domain (US Government)",
           "freshness_days": 1.4}
    composite, dims, freshness = _dataset_fair(row)
    assert dims["completeness"]["value"] == pytest.approx(0.874)
    assert dims["quality"]["value"] == 0.956
    assert dims["accessibility"]["value"] == 1.0
    assert dims["license_openness"]["value"] == 1.0
    assert composite is not None and 0.0 <= composite <= 1.0
    assert freshness == 1.4


def test_zero_row_dataset_is_red():
    # A 0-row dataset is RED overall (conservation: 0 rows ⇒ not healthy), even
    # though completeness_pct=100 and the license is open — those must not prop
    # up an empty dataset's ring. completeness is nulled (vacuous on zero rows).
    row = {"completeness_pct": 100.0, "quality_score_avg": None,
           "row_count": 0, "license_name": "Public Domain", "freshness_days": None}
    composite, dims, _ = _dataset_fair(row)
    assert composite == 0.0                          # RED, not license-propped 0.71
    assert dims["accessibility"]["value"] == 0.0     # 0 rows ⇒ not accessible
    assert dims["completeness"]["value"] is None     # 100% of nothing is vacuous
    assert dims["quality"]["value"] is None          # absent, not zeroed


def test_missing_inputs_are_null_not_coerced_and_excluded():
    row = {"completeness_pct": None, "quality_score_avg": None,
           "row_count": None, "license_name": None, "freshness_days": None}
    composite, dims, _ = _dataset_fair(row)
    assert all(d["value"] is None for d in dims.values())
    assert composite is None        # nothing known → honest null, not 0.0


def test_decimal_completeness_does_not_crash():
    # Defensive: if a future schema delivers completeness_pct as Decimal, the
    # /100 division must not TypeError (float-coerced symmetrically with quality).
    from decimal import Decimal
    row = {"completeness_pct": Decimal("80.0"), "quality_score_avg": Decimal("0.9"),
           "row_count": 100, "license_name": "Public Domain", "freshness_days": None}
    composite, dims, _ = _dataset_fair(row)
    assert dims["completeness"]["value"] == pytest.approx(0.8)
    assert composite is not None


def test_composite_is_weighted_mean_of_present_dimensions_only():
    # Only completeness present → composite equals it (single present dim).
    row = {"completeness_pct": 50.0, "quality_score_avg": None,
           "row_count": None, "license_name": None, "freshness_days": None}
    composite, dims, _ = _dataset_fair(row)
    assert composite == 0.5
    assert dims["completeness"]["value"] == 0.5
