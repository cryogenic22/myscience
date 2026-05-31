# SPEC Z5 — Section 1.1 priority matrix on the BCB

*Bucket 2 (Data model) loop 5. 30 May 2026.*

## Problem
The ZS framework's Section 1.1 priority matrix codifies which dossier domains are Critical / High / Medium for *this specific* engagement. The matrix is what determines where the Intelligence Agent spends its time and how gaps are ranked. Without it, the dossier is treated as a uniform information dump and the gap log has no importance ordering.

## Contract

Eight ZS domains × three priority levels, one matrix per BCB.

```python
class DossierDomain(str, Enum):
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

@dataclass
class PriorityMatrix:
    bcb_id: str
    cells: dict[DossierDomain, Priority]   # all 8 domains required

    def __post_init__(self):
        missing = set(DossierDomain) - set(self.cells.keys())
        if missing:
            raise PriorityMatrixError(f"matrix must cover all 8 domains; missing {missing}")
```

Service:
```python
DEFAULT_LAUNCH_MATRIX:  PriorityMatrix template
DEFAULT_DEFENSE_MATRIX: PriorityMatrix template
DEFAULT_LCM_MATRIX:     PriorityMatrix template

def default_matrix_for(situation: str) -> dict[DossierDomain, Priority]
def set_priority_matrix(db, bcb_id, matrix: dict[DossierDomain, Priority]) -> PriorityMatrix
def get_priority_matrix(db, bcb_id) -> PriorityMatrix | None
```

The defaults are the senior framing built in: a Launch matrix prioritises Competitive + Pricing as Critical; Defense prioritises Pipeline + Wargame-Specific; LCM prioritises HCP + Pricing.

## Database

Migration `070_priority_matrix.sql`: column on `business_context_briefs` (`priority_matrix JSONB`). One matrix per BCB lives inline (the BCB is the natural owner; matrices don't outlive their BCB).

## Acceptance tests
1. **Matrix refuses to construct without all 8 domains** — pure type.
2. **`default_matrix_for('launch')` returns the canonical Launch template** with Competitive + Pricing as Critical.
3. **`default_matrix_for('defense')`** returns Defense template.
4. **`default_matrix_for('lcm')`** returns LCM template.
5. **`default_matrix_for('weird')`** raises.
6. **`set_priority_matrix` persists JSONB**.
7. **`get_priority_matrix` returns the typed PriorityMatrix**.

## Out of scope (drift guard)
- No UI (F5 BriefPage will surface).
- No gap-log integration yet (Z6 IntelligenceGap will read from this matrix).

## Files
- NEW `schema/migrations/070_priority_matrix.sql`
- NEW `services/priority_matrix.py`
- NEW `tests/test_priority_matrix.py`
