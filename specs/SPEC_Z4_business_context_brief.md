# SPEC Z4 — Business Context Brief (BCB)

*Bucket 2 (Data model) loop 4. 30 May 2026.*

## Problem
The ZS framework's most upstream commitment: every engagement starts when the lead says *"this is a Launch situation; prioritise Competitive + Pricing as Critical; here are the five strategic decisions this wargame must inform."* Without a typed BCB, the dossier has no scoping principle and the gap log has no importance ranking. We don't have this object today.

## Contract

### Service `services/business_context_brief.py`
```python
@dataclass
class StrategicDecision:
    statement: str      # "Should Novo pre-launch CagriSema at WAC parity with Zepbound?"
    rationale: str      # 1-line reason this decision is worth the wargame's time

@dataclass
class CompetitorThreat:
    entity_ref: str     # "drug:zepbound" or "company:lilly"
    threat_level: str   # "primary" | "secondary" | "watch"
    note: str           # 1-line specific concern

@dataclass
class BusinessContextBrief:
    id: str
    engagement_id: str
    focal_asset: str            # "drug:cagrisema"
    situation: str              # mirrors Engagement.situation (launch/defense/lcm)
    strategic_decisions: list[StrategicDecision]   # 3–7 expected
    competitive_set: list[CompetitorThreat]        # 3–8 expected
    success_criteria: list[str]                    # what makes this wargame valuable
    constraints: list[str]                         # what the wargame must respect (legal/budget/timing)
    created_by: str
    created_at: datetime
    signed_off: bool = False
    signed_off_by: str | None = None
    signed_off_at: datetime | None = None

    def __post_init__(self):
        # type refuses to construct without at least one strategic decision —
        # the wargame must INFORM something. No decisions = no point.
        if not self.strategic_decisions or len(self.strategic_decisions) < 1:
            raise BCBContractError(">= 1 strategic_decisions required")
        if not self.focal_asset.strip():
            raise BCBContractError("focal_asset cannot be empty")
        for d in self.strategic_decisions:
            if not d.statement.strip() or not d.rationale.strip():
                raise BCBContractError("each StrategicDecision needs statement + rationale")
```

```python
def create_bcb(db, *, engagement_id, focal_asset, situation,
               strategic_decisions, competitive_set,
               success_criteria=None, constraints=None,
               created_by) -> str
def get_bcb_for_engagement(db, engagement_id) -> BusinessContextBrief | None
def sign_off_bcb(db, bcb_id, *, by) -> BusinessContextBrief
```

### Database
Migration `069_business_context_brief.sql`:
- One BCB per Engagement (UNIQUE constraint on engagement_id).
- JSONB columns for `strategic_decisions`, `competitive_set`, `success_criteria`, `constraints`.
- CHECK constraint: at least one strategic decision in JSONB.
- Sign-off triple: `signed_off, signed_off_by, signed_off_at` — paired constraint (all three null or all three set, mirroring the signals paired-state pattern).
- FK to engagements.

## Acceptance tests
1. **BCB refuses to construct without strategic_decisions** — pure type.
2. **BCB refuses to construct with empty focal_asset** — pure type.
3. **`create_bcb` persists** with at least one strategic decision.
4. **`get_bcb_for_engagement(eid)` returns the BCB**; returns None when none exists.
5. **`sign_off_bcb` sets all three sign-off fields** and emits an audit entry to the engagement audit log (cross-system).
6. **Cannot create two BCBs for the same engagement** (UNIQUE).
7. **`StrategicDecision` requires statement + rationale** — pure type.

## Out of scope (drift guard)
- No UI surface (F5 BriefPage).
- No priority matrix yet (Z5 builds it as a typed object on the BCB).

## Files
- NEW `schema/migrations/069_business_context_brief.sql`
- NEW `services/business_context_brief.py`
- NEW `tests/test_business_context_brief.py`
