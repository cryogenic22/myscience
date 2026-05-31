# BE-17 — 4-dimension confidence assessment

> Filed in `docs/AGENT_BACKLOG.md#be-17`. Branch:
> `claude/be-017-confidence-breakdown`.

## 1 · Why

Today three inconsistent UI primitives (ConfidenceBadge,
CalibrationChip, ImpactBadge) render different views of confidence
across surfaces. PB-604 collapses them into one ConfidencePill
showing **composite + 4 axis bars**. The pill cannot ship until the
chat response carries a `confidence_assessment` object with the
right shape.

## 2 · Design

`services/confidence.py::compute_confidence_assessment(evidence,
calibration_map=None) -> dict`. Pure function — chat handlers call
it after assembling the evidence pack and splice the result into
the response payload.

Output shape::

    {
      "composite": 0.74,
      "by_dimension": {
        "evidence_quality": 0.82,
        "source_diversity": 0.71,
        "recency":          0.65,
        "calibration":      0.78,
      }
    }

| dimension | computation |
|---|---|
| `evidence_quality` | mean of tier weights (T1=1.0, T2=0.7, T3=0.4, T4=0.6 — same as the materiality scorer) |
| `source_diversity` | 1 - HHI of source distribution. Single source → 0; N evenly-spread → 1 - 1/N |
| `recency` | mean exponential decay over `published_at` / `retrieved_at`; half-life 90 days; undated rows treated as 0.5 (neutral) |
| `calibration` | mean of `calibration_map[source_id]` across unique cited sources; default 0.7 for unmapped (curated source baseline) |

Composite is the weighted mean with `evidence_quality=0.35,
calibration=0.25, source_diversity=0.20, recency=0.20`. Result
clamped to `[0, 1]`.

## 3 · What ships in this PR

- `services/confidence.py` (the helper).
- 16 tests covering shape / per-dim semantics / composite weighting
  / dedup / undated handling / unknown-tier defaults.

## 4 · Follow-up (BE-17-FU1)

The 8 chat handlers must call `compute_confidence_assessment` and
splice `confidence_assessment` into their response payloads (1-line
edit per handler). Tracked separately to keep this diff readable —
same shape as BE-16-FU1.

## 5 · Acceptance

- [x] Output shape matches BE-17 spec exactly.
- [x] Each dimension has a defensible algorithm (documented in the
      module docstring).
- [x] Pure function — no DB calls; calibration source comes in as a
      `calibration_map` param so `services.source_registry` can
      supply the latest snapshot when wiring lands.
- [x] Composite stays in [0, 1] regardless of inputs.
