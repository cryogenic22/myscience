# ADR-002 — `confidence_tier` enum vs existing `trust_score` float

**Status:** Accepted
**Date:** 2026-04-28
**Decision driver:** SPEC-016 §1.2 + comp_intel_2.md §1.2 — the existing platform has `market_events.trust_score` (float in [0,1]) per migration 026, and the new CI design calls for a `confidence_tier` enum (`confirmed | reported | inferred | disputed`). SPEC-017 D1 listed this as an open Phase 0 gate.

---

## Decision

**Both fields coexist on the new `signals` table; the existing `market_events.trust_score` is left in place and not consumed by CI workflows.** A new `confidence_tier` enum is the canonical primitive for module-facing language gating, scoring rules, hedging in synthesis, and reviewer routing. `trust_score` becomes a *derived diagnostic* — kept for backward compatibility with the existing intelligence feed, but not authoritative for any new CI logic.

The enum is **derived, not assigned**: every signal write computes `confidence_tier` from `(source_class, fact_type, corroboration_count, age)` per the rule in §3 below. Time-decay and corroboration-promotion are first-class.

We do **not** drop `trust_score`. It stays as a derived *float view of the same data* for legacy consumers (`services/intelligence_feed.py`, `services/event_collector.py`, `api/routes/intelligence.py`). The function that computes it is rewritten so that `trust_score` and `confidence_tier` are always consistent.

## Context

### Today (state on `main` as of 2026-04-28)

```
schema/migrations/026_intelligence_events.sql:
  ALTER TABLE market_events ADD COLUMN trust_score FLOAT DEFAULT 0.5;
  ALTER TABLE market_events ADD COLUMN source_tier TEXT DEFAULT 'tier_3';
```

```
services/event_collector.py:
  TIER_BASE_SCORES = { 'tier_1': 0.9, 'tier_2': 0.6, 'tier_3': 0.3 }
  CORROBORATION_BONUS = 0.15
  trust_score = min(base + bonus * corroboration_count, 1.0)
```

```
services/intelligence_feed.py:
  def derive_severity(trust_score, max_impact_magnitude) -> str:
      # high/medium/low cutoffs at trust_score 0.8 / 0.6 / 0.4
```

There are **27 occurrences of `trust_score`** across 4 files. The number is small enough to migrate, but the design question is whether *new* CI code should write floats or enums.

### What CI design wants (SPEC-016 §1.2 / §5.4)

```
confidence_tier ∈ {confirmed, reported, inferred, disputed}

Source class                              → tier
─────────────────────────────────────────────────
SEC filing, regulator, CT.gov,            → confirmed
  Orange Book, DailyMed, peer-reviewed
Company press release / IR / transcript   → confirmed (factual)
                                          → reported (forward-looking)
Trade press (FiercePharma, BioPharma…)   → reported
LinkedIn, X/Twitter, general news, blog   → inferred
Tier 3 vendor (Cortellis, AlphaSense)     → confirmed (facts)
                                          → reported (vendor analysis)
```

Modifiers from comp_intel_2.md §4.3:
- **Corroboration:** `reported` corroborated by ≥2 independent reporteds → can rise to `confirmed` per a rule
- **Disagreement:** two `confirmed`-tier sources disagreeing → drops to `disputed`
- **Time-decay:** press-release-only `confirmed` not backed by SEC within 4 business days → drops to `reported`

The enum drives **language hedging** in synthesis ("Pfizer raised guidance" vs "BioPharma Dive reports Pfizer raised guidance"), **routing** in reviewer queue (only `confirmed` impact=high gets human review), and **alert suppression** (`inferred` doesn't ship without confirmation).

A float can't carry these distinctions cleanly. `trust_score=0.6` could be "tier_2 with 0 corroboration" or "tier_1 fact that just got disputed" — same number, different meanings, different downstream behavior. The enum makes the distinction explicit.

## Options considered

### A — Replace `trust_score` with `confidence_tier` everywhere

Drop `trust_score` from `market_events` (DROP COLUMN), migrate the 4 consuming services to read `confidence_tier`, deprecate `derive_severity(trust_score, …)` in favor of `derive_severity(confidence_tier, impact_tier)`.

**Pros**
- Single primitive, no semantic drift between two fields.
- Forces immediate alignment.

**Cons**
- Touches 27 occurrences across 4 services + 1 API route.
- `services/intelligence_feed.py` is a working production code path. Refactoring it during Phase 0 is scope creep.
- Loses information: a corroboration count of 3 collapses to the same tier as count of 5. For *internal* scoring (impact composite), the float was useful as a continuous knob.
- `market_events` is an ETL target for many connectors (SEC EDGAR, news, FDA). Renaming the column requires synchronized connector + service deploys.

### B — Add `confidence_tier` to `signals` only; leave `market_events.trust_score` alone

`signals` (the new CI unit-of-output) carries `confidence_tier`. `market_events` keeps `trust_score`. The two are **derived from the same upstream data** but `confidence_tier` is the canonical fact for CI workflows; `trust_score` is for the legacy intelligence feed.

**Pros**
- Zero touch to existing code in Phase 0.
- New CI code uses the right primitive from day one.
- Migration is opt-in: services that need the enum query `signals`; legacy services keep reading `market_events`.
- Failure mode is bounded — if a legacy consumer reads stale `trust_score`, it's still the same data we have today, just expressed differently.

**Cons**
- Two fields encoding overlapping concepts.
- Risk of drift if the derivation rules diverge over time.
- Discoverability: a new engineer might use `trust_score` thinking it's the canonical measure.

### C — Add both to `signals`; deprecate `trust_score` after Phase 1 stabilizes

Same as B, plus an explicit deprecation timeline: after Phase 1 ships and the legacy intelligence feed has been migrated to consume `signals`, drop `trust_score` from `market_events` (Phase 2).

**Pros**
- Clean target state.
- Bounded migration window.
- Engineering can reason about the deprecation as a concrete future work item, not a vague aspiration.

**Cons**
- Same coexistence cost as B until deprecation lands.
- Requires discipline to actually execute the deprecation.

## Decision rationale

**Option C is what we land on.** Reasoning:

1. **Phase 0 must not touch existing prod code paths.** SPEC-016 P0 explicitly rules out connector / service refactors. Option A violates this; B and C don't.
2. **The CI unit-of-output is `signals`, not `market_events`.** New CI code reads from `signals`. Putting the enum there from day one means CI is correct from line one.
3. **Legacy must keep working.** `services/intelligence_feed.py` powers an existing surface that internal users consume. We don't break it during a rebrand week.
4. **Deprecation discipline.** Without a stated end-date, "we'll migrate later" becomes "we never do." Setting Phase 2 as the deprecation window forces the design conversation later, in context.

## Implementation plan

### Phase 0 — this ADR

No code changes. This document is the deliverable.

### Phase 1 swimlane B (sprint B2)

Per SPEC-016 §7 swimlane B, sprint B2 already includes:
- "Confidence-tier enum + derivation service (source-class × fact-type matrix)"
- "Tier corroboration modifier"
- "Time-decay rule"
- "Late-arriving high-tier promotion path with explicit `signal_updated` emission"

This ADR locks the column it writes to as `signals.confidence_tier` (enum), with a parallel `signals.trust_score` (float) computed by the same derivation service for legacy compatibility.

```
-- new in B1 sprint
CREATE TABLE signals (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id              UUID NOT NULL REFERENCES market_events(id),
  kbq_tags              TEXT[] NOT NULL DEFAULT '{}',
  headline              VARCHAR(120) NOT NULL,
  summary               VARCHAR(500) NOT NULL,
  direction             TEXT CHECK (direction IN ('positive','negative','neutral','mixed')),
  confidence_tier       TEXT NOT NULL CHECK (confidence_tier IN ('confirmed','reported','inferred','disputed')),
  trust_score           REAL NOT NULL CHECK (trust_score BETWEEN 0 AND 1),
  impact_tier           TEXT NOT NULL CHECK (impact_tier IN ('high','medium','low')),
  impact_score          REAL NOT NULL CHECK (impact_score BETWEEN 0 AND 1),
  rule_version_id       TEXT NOT NULL,
  primary_entity_type   TEXT NOT NULL,
  primary_entity_id     TEXT NOT NULL,
  related_entity_ids    TEXT[] NOT NULL DEFAULT '{}',
  evidence_document_ids UUID[] NOT NULL CHECK (cardinality(evidence_document_ids) >= 1),
  superseded_by         UUID REFERENCES signals(id),
  supersedence_reason   TEXT,
  status                TEXT NOT NULL DEFAULT 'candidate'
                        CHECK (status IN ('candidate','reviewed','shipped','superseded','retracted')),
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  reviewed_by           UUID,
  reviewed_at           TIMESTAMPTZ,
  shipped_at            TIMESTAMPTZ
);

CREATE INDEX idx_signals_event ON signals(event_id);
CREATE INDEX idx_signals_status_impact ON signals(status, impact_tier, created_at DESC);
CREATE INDEX idx_signals_primary_entity ON signals(primary_entity_type, primary_entity_id);
CREATE INDEX idx_signals_kbq ON signals USING GIN (kbq_tags);
```

### Derivation service (services/intelligence/scoring.py — new in B2)

Single function, invoked at every signal write:

```python
def derive_confidence(
    sources: list[Source],
    fact_type: FactType,           # claim | forward_looking | analysis
    age_days: float,
    expected_corroboration_window_days: float | None = None,
) -> tuple[ConfidenceTier, float]:
    """Returns (tier, trust_score) — both authoritative.

    Tier follows the SPEC-016 §5.4 lookup with corroboration + time-decay
    modifiers. Trust_score is derived from the same inputs as a continuous
    function (used for downstream impact_score composition and the legacy
    intelligence_feed surface).
    """
    base_tier, base_score = _tier_from_source_class(sources, fact_type)
    tier_with_corrob = _apply_corroboration(base_tier, sources)
    final_tier = _apply_time_decay(tier_with_corrob, age_days,
                                   expected_corroboration_window_days)
    final_score = _continuous_score(sources, fact_type, age_days)
    return final_tier, final_score
```

Both outputs are written. `signals.trust_score` is **never set independently** of `confidence_tier` — the derivation is the source of truth.

### Phase 1 swimlane B (sprint B7)

Wire `services/intelligence_feed.py` to read `signals.trust_score` (which is now the same number as today's `market_events.trust_score`, just sourced through the new code path). Delete the duplicate scoring code in `event_collector.py`. This is a within-CI-team change; no schema migration.

### Phase 2 — deprecation of `market_events.trust_score`

After Phase 1 has been live for ≥4 weeks and the intelligence feed has been re-pointed at `signals`:

```
-- migration M2.deprecate_trust_score (timeline: Phase 2 week 1)
ALTER TABLE market_events
  DROP COLUMN IF EXISTS trust_score,
  DROP COLUMN IF EXISTS source_tier;
```

Pre-conditions for running this migration:
1. No code in `services/`, `api/`, or `connectors/` references `market_events.trust_score` (verified by static check, similar to SPEC-010 guards).
2. `services/intelligence_feed.py` reads only from `signals`.
3. The `event_collector.py` flow has been ported to write to `signals` directly (with `market_events` as the underlying event spine, but no longer carrying the score).
4. A 7-day soak in staging.

These are tracked as Phase 2 sprint A7+B7 follow-on tasks.

## Static guards added in this ADR

A new test joins the SPEC-010 family:

```python
# tests/test_confidence_tier_invariants.py
def test_signals_trust_score_consistent_with_confidence_tier():
    """trust_score and confidence_tier must agree on every signal row.
    Mismatch indicates the derivation service was bypassed."""
    rows = db.fetch_all("""
        SELECT id, confidence_tier, trust_score FROM signals
    """)
    for row in rows:
        if row['confidence_tier'] == 'confirmed':
            assert row['trust_score'] >= 0.7, f"signal {row['id']} confirmed but score {row['trust_score']}"
        if row['confidence_tier'] == 'inferred':
            assert row['trust_score'] <= 0.5, f"signal {row['id']} inferred but score {row['trust_score']}"
```

This test is created in B2 alongside the derivation service. It runs in CI on every PR.

## Consequences

### Immediate (Phase 0)
- Documentation only. No engineering work.

### Phase 1
- New `signals` table carries both columns. Derivation service writes both atomically.
- Legacy `market_events.trust_score` continues to be written by existing connectors. Unchanged behavior.
- Static-check CI rule added: any new code reading `market_events.trust_score` triggers a warning suggesting `signals.confidence_tier` instead.

### Phase 2
- `market_events.trust_score` and `source_tier` columns are dropped.
- All consumers read from `signals`.
- Single source of truth restored.

### Risk
- Drift between `trust_score` and `confidence_tier` if both are written by separate code paths. **Mitigation:** the invariant test above + the rule that `signals` is written by exactly one service (the derivation service in B2). `market_events.trust_score` is the legacy column; `signals.trust_score` is the new surface; they are semantically the same number sourced via the same logic but live on different tables. Tooling rules out divergence.

## Related

- SPEC-016 §1.2, §5.4 — confidence_tier rules
- SPEC-017 D1 — open decision (now resolved)
- comp_intel_2.md §1.2, §4.3 — critique that surfaced this question
- migration 026 — original `trust_score` introduction
- ADR-001 — monorepo migration plan (this ADR is M0 work)

---

*ADR-002. Successor ADRs may revise this when the deprecation lands in Phase 2.*
