# SPEC Z2 — Insight type + synthesis-test gate

*Bucket 2 (Data model) loop 1. Closes Riya's most damaging finding structurally. 30 May 2026.*

## Problem
The v7 demo emitted "insights" as prose without traceable chains back to dossier facts. Riya caught: *"KOLs and specialists are the natural CagriSema audience; PCPs are not"* appeared as a synthesis insight that did not exist as a fact in dossier. If insights can be invented, the platform's whole credibility collapses.

The ZS framework's operating principle: *"Does this insight change what someone would do differently? If not, it is not an insight — it is a fact."* This must be a **type**, not a convention.

## Contract
New module `services/insights.py`:

```python
class StrategicFrame(str, Enum):
    RISK         = "risk"
    OPPORTUNITY  = "opportunity"
    ASSUMPTION   = "assumption"
    TRIGGER      = "trigger"

@dataclass(frozen=True)
class FactCitation:
    fact_id: str
    predicate: str
    contribution: str  # 1-line explanation of HOW this fact supports the insight

@dataclass
class Insight:
    id: str
    statement: str                            # the insight claim
    strategic_frame: StrategicFrame
    derived_from: list[FactCitation]          # MUST be len >= 1
    synthesis_test_passed: bool
    synthesis_test_rationale: str             # required, non-empty
    domain: str                               # ZS dossier domain
    created_by: str = "intelligence_agent"
    created_at: datetime | None = None

    def __post_init__(self):
        # type refuses to construct without a fact chain
        if not self.derived_from or len(self.derived_from) < 1:
            raise InsightContractError("Insight requires >= 1 derived_from facts")
        if not self.statement.strip():
            raise InsightContractError("Insight statement cannot be empty")
        if not self.synthesis_test_rationale.strip():
            raise InsightContractError("synthesis_test_rationale must be non-empty")
        for c in self.derived_from:
            if not c.fact_id or not c.contribution.strip():
                raise InsightContractError("each FactCitation requires fact_id + contribution")
```

```python
def synthesis_test(candidate: dict) -> SynthesisResult:
    """Apply the ZS synthesis test: does this candidate change what someone
    would do differently? Returns {passed: bool, rationale: str}. The test
    enforces three sub-rules:
      1. The statement must reference an entity or specific decision.
      2. It must be derived from >= 1 facts (passed in as derived_from).
      3. It must carry a strategic_frame (the four-way classification).
    A candidate failing any rule passes through as `passed=False` with a
    specific rationale and is persisted as a rejected_insight for audit.
    """

def assert_insight(db, *, statement, strategic_frame, derived_from, domain,
                   synthesis_test_rationale, created_by="intelligence_agent") -> str:
    """Run the synthesis test, persist as either insight (passed) or
    rejected_insight (failed). Returns the insight id (or rejected id)."""

def list_insights(db, *, domain=None, strategic_frame=None) -> list[Insight]:
    """List insights for a dossier domain or frame."""
```

## Database

Migration `066_insights.sql`:
```sql
CREATE TABLE insights (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  statement TEXT NOT NULL,
  strategic_frame TEXT NOT NULL CHECK (strategic_frame IN ('risk','opportunity','assumption','trigger')),
  derived_from JSONB NOT NULL,  -- list of {fact_id, predicate, contribution}
  synthesis_test_passed BOOL NOT NULL DEFAULT TRUE,
  synthesis_test_rationale TEXT NOT NULL,
  domain TEXT NOT NULL,         -- e.g. 'competitive', 'pricing_access'
  created_by TEXT NOT NULL DEFAULT 'intelligence_agent',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  tenant_scope TEXT,
  CONSTRAINT insights_derived_from_nonempty CHECK (jsonb_array_length(derived_from) >= 1)
);

CREATE TABLE rejected_insights (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_statement TEXT NOT NULL,
  rejection_reason TEXT NOT NULL,
  derived_from JSONB,  -- nullable: rejection may be because there were no facts
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_insights_domain ON insights(domain, created_at DESC);
CREATE INDEX idx_insights_frame ON insights(strategic_frame);
```

## Acceptance tests
1. **Insight refuses to construct without derived_from** — pure-type invariant, no DB.
2. **Insight refuses to construct with empty statement** — pure-type invariant.
3. **synthesis_test passes** when candidate has a fact-citation chain and a clear frame.
4. **synthesis_test rejects** when candidate has no fact-citation chain.
5. **assert_insight(passed=True) writes to `insights`**; **assert_insight(passed=False) writes to `rejected_insights`** with the rejection_reason.
6. **list_insights filters by domain and strategic_frame**.

## Out of scope (drift guard)
- No UI surface (F8 builds the SynthesisPage).
- No tenant RLS (E phase).
- No backfill of existing prose-insights (those don't exist as typed objects; nothing to migrate).
- No coupling to Context Layer's `get_entity_360` yet (a later loop wires `Section` types to reference insights).

## Files
- NEW `services/insights.py`
- NEW `tests/test_insights.py`
- NEW `schema/migrations/066_insights.sql`
