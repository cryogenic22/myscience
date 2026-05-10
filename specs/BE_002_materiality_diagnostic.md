# BE-2 — Production materiality scores all 1% (DIAGNOSTIC + FIX)

> Filed in `docs/AGENT_BACKLOG.md#be-2`. Loop opened 2026-05-10.
> Branch: `claude/be-002-materiality-diagnostic`.

## 1 · Symptom (live walk, 2026-05-09)

Every signal on production renders as `materiality_score = 1%` in the
frontend. The materiality drawer (PB-103) cannot ship until this is
fixed because the underlying value is uniformly broken.

## 2 · Investigation

Searched for the data path end-to-end:

- `services/materiality.py::compute_materiality()` — **pure scorer is
  correct**. `tests/test_materiality_api.py` proves the math: a focal
  + clinical_readout + tier-1 + 0-day signal scores ~95.
- `services/materiality.py::persist_score_to_signal()` — UPDATEs both
  `signals.materiality_score` and `signals.materiality_factors`.
  Wrapped in `try/except` that swallows the error and emits
  `logger.warning`.
- `api/routes/materiality.py::POST /materiality/score` — **the only
  caller** of `compute_materiality` + `persist_score_to_signal`. No
  ingestion path invokes the scorer.
- `schema/migrations/037_signals_table.sql` — defines `signals` with
  `trust_score REAL` and `impact_score REAL` (both 0..1). **No
  `materiality_score` column.**
- `schema/migrations/058_materiality_scoring.sql` — adds
  `materiality_factors JSONB` to `signals`, but **does not add
  `materiality_score`**.
- `api/routes/signals.py::list_signals + get_signal` — SELECT lists
  `trust_score, impact_score` but **does not select
  `materiality_score` or `materiality_factors`**, and `_row_to_dict`
  does not return them in the JSON payload.

## 3 · Root causes (4 stacked bugs)

| # | Cause | Effect |
|---|---|---|
| RC-1 | `signals.materiality_score` column was never created | `persist_score_to_signal` UPDATE fails with `column "materiality_score" does not exist`. |
| RC-2 | `persist_score_to_signal` swallows the exception silently (`logger.warning`) | RC-1 has been invisible since SPEC-031 shipped. |
| RC-3 | `compute_materiality` is not wired into any ingestion / signal-creation path | Even with the column present, every signal's `materiality_score` would stay NULL until a user POST'd `/materiality/score`. |
| RC-4 | `GET /signals` does not return `materiality_score` or `materiality_factors` | Frontend reads `null` and renders the field's missing-default (`0` or `0.01`) as **1%**. |

The "1%" rendering on production is the visible artefact of RC-4 +
RC-1/2/3 (no scorer ever ran, the field never got populated, the API
never returned it, the frontend defaults to `0.01` or treats `null`
as `0` and formats as a percentage).

## 4 · Fix surface

Five changes, all on this branch:

1. **Migration 065** — `ALTER TABLE signals ADD COLUMN
   materiality_score INTEGER CHECK (materiality_score BETWEEN 0 AND
   100)`. NULL allowed (legacy + unscored). Index on
   `(materiality_score)` for framing-trigger threshold queries.
2. **`services/materiality.py`** — change
   `persist_score_to_signal` to log at `ERROR` level and re-raise on
   schema-class errors (`UndefinedColumn`); only swallow truly
   transient failures. Add `score_signal_row(db, signal_row)`
   convenience that pulls inputs from a signals row + companion
   tables and returns/persists a `MaterialityResult`.
3. **`api/routes/signals.py`** — extend the SELECT and `_row_to_dict`
   to include `materiality_score` and `materiality_factors` (jsonb).
4. **`scripts/backfill_materiality_scores.py`** — paginated
   one-shot: `python -m scripts.backfill_materiality_scores
   [--batch 500] [--dry-run]`. Reads signals with
   `materiality_score IS NULL`, calls `score_signal_row`, persists.
5. **Tests** — `tests/test_materiality_persistence.py`:
   - persist_score_to_signal raises (does NOT swallow) when the column
     is missing
   - persist_score_to_signal succeeds when the column is present
   - score_signal_row maps tier / criticality / claim_type / age_days
     from a signals row + connector source row
   - GET /signals returns materiality_score + materiality_factors
   - backfill script processes a batch of NULL-score rows

## 5 · Acceptance

Per BE-2:

- [x] Written diagnostic with root cause (this file)
- [x] Fix landed (migration + scorer + API + backfill)
- [ ] Spot-check 10 signals showing varied scores (>1% with sensible
  spread) — runs after deploy + backfill against prod data; capture
  in PR description.

## 6 · Red-team findings (Stage 5)

| ID | Finding | Disposition |
|---|---|---|
| RT-1 | `_is_schema_error` could false-positive on a transient `connection does not exist` and falsely raise from `persist_score_to_signal`. | **Fixed** — message-pattern fallback now requires a relation-kind keyword (column / table / relation / type / function) before the "does not exist" trigger; new test pins the regression. |
| RT-10 | `signals` table has no `source_tier` column, so `score_signal_row` defaults every legacy row to tier 3 (factor value 0.4). The fix unblocks the 1% bug, but range will be 25-65 not full 0-100 until the connector → tier lookup is wired. | Documented; tracked as follow-up below. |

## 7 · Out of scope (deferred — filed as follow-ups)

- **`source_tier` lookup from connectors** — `signals.source_tier` does not
  exist; populating it requires joining `signals → market_events → connector → sources.tier`.
  Worthwhile follow-up that lives naturally with BE-24 (source detail
  FAIR endpoint), since both depend on the same source registry tier
  field. Tracked at AGENT_BACKLOG#BE-2-FU1.
- **Wiring scorer into the live signal-creation path** — production
  signals are not inserted from any `services/` path visible in this
  tree; the insert site appears to live outside the current codebase.
  Once located, calling `score_signal_row` at INSERT time is a
  one-line follow-up.
- **Frontend display** — that's the FE Claude track. Once `materiality_*`
  fields land in the GET payload, FE renders correctly without
  further BE work.
