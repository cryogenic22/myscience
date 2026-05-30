"""Z5 — tests for the Section 1.1 priority matrix on the BCB.

The matrix codifies which dossier domains are Critical / High / Medium for
the specific engagement. Defaults vary by situation (launch vs defense vs
lcm). The type refuses to construct without all eight domains covered —
silent gaps would defeat the purpose. See specs/SPEC_Z5_priority_matrix.md.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.priority_matrix import (
    DossierDomain,
    Priority,
    PriorityMatrix,
    PriorityMatrixError,
    default_matrix_for,
    set_priority_matrix,
    get_priority_matrix,
)


# ── Type invariants (no DB) ───────────────────────────────────────


class TestPriorityMatrixInvariants:
    def test_refuses_to_construct_without_all_8_domains(self):
        # Only 3 domains — must be rejected
        with pytest.raises(PriorityMatrixError):
            PriorityMatrix(
                bcb_id="b1",
                cells={
                    DossierDomain.COMPETITIVE: Priority.CRITICAL,
                    DossierDomain.PRICING_AND_ACCESS: Priority.HIGH,
                    DossierDomain.CLINICAL_PROFILE: Priority.HIGH,
                },
            )

    def test_constructs_with_all_8(self):
        cells = {d: Priority.MEDIUM for d in DossierDomain}
        m = PriorityMatrix(bcb_id="b1", cells=cells)
        assert len(m.cells) == 8


# ── default_matrix_for ────────────────────────────────────────────


class TestDefaults:
    def test_launch_makes_competitive_and_pricing_critical(self):
        cells = default_matrix_for("launch")
        assert cells[DossierDomain.COMPETITIVE] is Priority.CRITICAL
        assert cells[DossierDomain.PRICING_AND_ACCESS] is Priority.CRITICAL

    def test_defense_makes_pipeline_and_wargame_critical(self):
        cells = default_matrix_for("defense")
        assert cells[DossierDomain.PIPELINE_AND_MACRO] is Priority.CRITICAL
        assert cells[DossierDomain.WARGAME_SPECIFIC] is Priority.CRITICAL

    def test_lcm_makes_hcp_and_pricing_critical(self):
        cells = default_matrix_for("lcm")
        assert cells[DossierDomain.HCP_AND_PATIENT] is Priority.CRITICAL
        assert cells[DossierDomain.PRICING_AND_ACCESS] is Priority.CRITICAL

    def test_unknown_situation_raises(self):
        with pytest.raises(PriorityMatrixError):
            default_matrix_for("weird")

    def test_defaults_cover_all_8_domains(self):
        for situation in ("launch", "defense", "lcm"):
            cells = default_matrix_for(situation)
            assert set(cells.keys()) == set(DossierDomain)


# ── set_priority_matrix / get_priority_matrix ─────────────────────


def _db(row=None):
    db = MagicMock()
    db.fetch_one = MagicMock(return_value=row or {"id": "b1"})
    db.execute = MagicMock()
    return db


class TestPersistence:
    def test_set_persists_jsonb(self):
        db = _db()
        cells = default_matrix_for("launch")
        m = set_priority_matrix(db, "b1", cells)
        assert m.bcb_id == "b1"
        # Verify the UPDATE was made and contained the JSONB payload
        # in its params — the JSON string should contain "critical".
        calls = db.fetch_one.call_args_list + db.execute.call_args_list
        update_call = next(
            (c for c in calls if c.args and "priority_matrix" in c.args[0]),
            None,
        )
        assert update_call is not None
        params = update_call.args[1]
        # params can be dict or list depending on call shape
        payload = params.get("priority_matrix") if isinstance(params, dict) else str(params)
        assert "critical" in payload

    def test_get_returns_typed_matrix(self):
        row = {
            "id": "b1",
            "priority_matrix": {d.value: "medium" for d in DossierDomain},
        }
        db = _db(row=row)
        m = get_priority_matrix(db, "b1")
        assert m is not None
        assert len(m.cells) == 8
        assert all(p is Priority.MEDIUM for p in m.cells.values())

    def test_get_returns_none_when_no_matrix(self):
        db = _db(row={"id": "b1", "priority_matrix": None})
        assert get_priority_matrix(db, "b1") is None
