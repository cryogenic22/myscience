"""Z5 — Section 1.1 priority matrix on the BCB.

The matrix codifies which dossier domains are Critical / High / Medium for
the specific engagement. Defaults differ by situation:
  launch  → Competitive + Pricing&Access are Critical
  defense → Pipeline&Macro + Wargame-Specific are Critical
  lcm     → HCP&Patient + Pricing&Access are Critical

The PriorityMatrix type refuses to construct without all 8 domains covered.
Silent gaps in the matrix would defeat its purpose (Phase Z6 IntelligenceGap
uses it to rank gaps by importance). See specs/SPEC_Z5_priority_matrix.md.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class PriorityMatrixError(ValueError):
    """Raised when a matrix violates its invariants (missing domains, bad
    situation, etc.)."""


# ── Enums ─────────────────────────────────────────────────────────


class DossierDomain(str, Enum):
    """Eight ZS framework dossier domains. The set is closed; new domains
    require a migration + spec update."""
    DISEASE_AND_PATIENT     = "disease_and_patient"
    CLINICAL_PROFILE        = "clinical_profile"
    COMPETITIVE             = "competitive"
    PRICING_AND_ACCESS      = "pricing_and_access"
    COMMERCIAL_OPERATIONAL  = "commercial_operational"
    HCP_AND_PATIENT         = "hcp_and_patient"
    PIPELINE_AND_MACRO      = "pipeline_and_macro"
    WARGAME_SPECIFIC        = "wargame_specific"


class Priority(str, Enum):
    CRITICAL = "critical"
    HIGH     = "high"
    MEDIUM   = "medium"


# ── PriorityMatrix dataclass ──────────────────────────────────────


@dataclass
class PriorityMatrix:
    bcb_id: str
    cells: dict[DossierDomain, Priority]

    def __post_init__(self):
        missing = set(DossierDomain) - set(self.cells.keys())
        if missing:
            raise PriorityMatrixError(
                f"matrix must cover all 8 domains; missing "
                f"{sorted(d.value for d in missing)}"
            )
        # All values must be Priority enums (or coercible strings)
        for d, p in list(self.cells.items()):
            if not isinstance(p, Priority):
                try:
                    self.cells[d] = Priority(p)
                except (ValueError, TypeError) as exc:
                    raise PriorityMatrixError(
                        f"invalid priority {p!r} for domain {d.value}"
                    ) from exc


# ── Default templates per situation ───────────────────────────────


_LAUNCH_DEFAULTS = {
    DossierDomain.DISEASE_AND_PATIENT:     Priority.HIGH,
    DossierDomain.CLINICAL_PROFILE:        Priority.HIGH,
    DossierDomain.COMPETITIVE:             Priority.CRITICAL,
    DossierDomain.PRICING_AND_ACCESS:      Priority.CRITICAL,
    DossierDomain.COMMERCIAL_OPERATIONAL:  Priority.MEDIUM,
    DossierDomain.HCP_AND_PATIENT:         Priority.HIGH,
    DossierDomain.PIPELINE_AND_MACRO:      Priority.HIGH,
    DossierDomain.WARGAME_SPECIFIC:        Priority.HIGH,
}

_DEFENSE_DEFAULTS = {
    DossierDomain.DISEASE_AND_PATIENT:     Priority.MEDIUM,
    DossierDomain.CLINICAL_PROFILE:        Priority.HIGH,
    DossierDomain.COMPETITIVE:             Priority.HIGH,
    DossierDomain.PRICING_AND_ACCESS:      Priority.HIGH,
    DossierDomain.COMMERCIAL_OPERATIONAL:  Priority.HIGH,
    DossierDomain.HCP_AND_PATIENT:         Priority.MEDIUM,
    DossierDomain.PIPELINE_AND_MACRO:      Priority.CRITICAL,
    DossierDomain.WARGAME_SPECIFIC:        Priority.CRITICAL,
}

_LCM_DEFAULTS = {
    DossierDomain.DISEASE_AND_PATIENT:     Priority.HIGH,
    DossierDomain.CLINICAL_PROFILE:        Priority.HIGH,
    DossierDomain.COMPETITIVE:             Priority.HIGH,
    DossierDomain.PRICING_AND_ACCESS:      Priority.CRITICAL,
    DossierDomain.COMMERCIAL_OPERATIONAL:  Priority.MEDIUM,
    DossierDomain.HCP_AND_PATIENT:         Priority.CRITICAL,
    DossierDomain.PIPELINE_AND_MACRO:      Priority.MEDIUM,
    DossierDomain.WARGAME_SPECIFIC:        Priority.HIGH,
}

_DEFAULTS_BY_SITUATION = {
    "launch":  _LAUNCH_DEFAULTS,
    "defense": _DEFENSE_DEFAULTS,
    "lcm":     _LCM_DEFAULTS,
}


def default_matrix_for(situation: str) -> dict[DossierDomain, Priority]:
    """Return the canonical default matrix for a situation. Editable by
    the engagement lead from the BCB intake surface."""
    s = (situation or "").strip().lower()
    if s not in _DEFAULTS_BY_SITUATION:
        raise PriorityMatrixError(
            f"unknown situation {situation!r} (known: "
            f"{sorted(_DEFAULTS_BY_SITUATION.keys())})"
        )
    return dict(_DEFAULTS_BY_SITUATION[s])


# ── Persistence ──────────────────────────────────────────────────


_UPDATE_SQL = """
    UPDATE business_context_briefs
       SET priority_matrix = %(priority_matrix)s::jsonb
     WHERE id = %(id)s
     RETURNING id, priority_matrix
"""

_SELECT_SQL = """
    SELECT id, priority_matrix
      FROM business_context_briefs
     WHERE id = %s
"""


def _cells_to_jsonb(cells: dict[DossierDomain, Priority]) -> str:
    return json.dumps({d.value: p.value for d, p in cells.items()})


def _jsonb_to_cells(payload: Any) -> dict[DossierDomain, Priority]:
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise PriorityMatrixError(f"priority_matrix payload must be a dict, got {type(payload).__name__}")
    return {DossierDomain(k): Priority(v) for k, v in payload.items()}


def set_priority_matrix(
    db,
    bcb_id: str,
    cells: dict[DossierDomain, Priority],
) -> PriorityMatrix:
    """Persist the matrix for a BCB. Validates the matrix invariants
    (refuses if not all 8 domains covered) before any DB write."""
    # Coerce string keys/values to enums if the caller passed raw dicts.
    coerced: dict[DossierDomain, Priority] = {}
    for k, v in cells.items():
        kk = k if isinstance(k, DossierDomain) else DossierDomain(k)
        vv = v if isinstance(v, Priority) else Priority(v)
        coerced[kk] = vv
    matrix = PriorityMatrix(bcb_id=bcb_id, cells=coerced)  # invariant check

    params = {
        "id": bcb_id,
        "priority_matrix": _cells_to_jsonb(matrix.cells),
    }
    try:
        if hasattr(db, "fetch_one"):
            db.fetch_one(_UPDATE_SQL, params)
        else:
            db.execute(_UPDATE_SQL, params)
    except Exception:
        logger.exception("set_priority_matrix persist failed for %s", bcb_id)
        # Re-raise so the caller knows the write didn't land
        raise
    return matrix


def get_priority_matrix(db, bcb_id: str) -> Optional[PriorityMatrix]:
    try:
        row = db.fetch_one(_SELECT_SQL, [bcb_id])
    except Exception:
        logger.exception("get_priority_matrix query failed for %s", bcb_id)
        return None
    if not row:
        return None
    payload = row.get("priority_matrix")
    if not payload:
        return None
    try:
        cells = _jsonb_to_cells(payload)
        return PriorityMatrix(bcb_id=str(row["id"]), cells=cells)
    except PriorityMatrixError:
        logger.exception("malformed priority_matrix payload for bcb %s", bcb_id)
        return None
