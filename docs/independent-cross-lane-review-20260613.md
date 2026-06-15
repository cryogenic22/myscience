# Independent Cross-Lane Review - 2026-06-13

Review ID: MZ-XREVIEW-20260613-001  
Reviewer stance: independent third-party reviewer; pharma SME, AI/data systems, product-quality reviewer  
Scope: Platform/F6 synthesis and eval work, Data/source-coverage and NADAC/alias branches, Frontend/DataHub catalog branch  
Mode: read-only code review; no product-code edits and no tests run  

## Executive Verdict

The work is directionally strong and materially improves the product-quality bar.
The F6 specialist eval is the right kind of adversarial gate for pharma
intelligence: it tests provenance, closed-world honesty, count-fallacy risk, and
domain correctness rather than only route success.

The main remaining risk is seam drift between lanes. Platform has added
deterministic coverage-honesty wording, while Data is building source-coverage
and reviving NADAC. Those must converge into one data-driven response contract,
otherwise the system can become confidently honest about yesterday's source
state rather than today's source state.

Verdict: FINDINGS_OPEN. The system is improving, but the findings below should
be treated as lane backlog items before the work is considered high-quality for
SME-grade pharma intelligence.

## Review Log

| Finding ID | Severity | Owner | Status | Summary |
|---|---|---|---|---|
| MZ-XR-20260613-001 | High | Data | Open | Source coverage counts shared tables and can overstate source-specific availability. |
| MZ-XR-20260613-002 | High | Platform | Open | Coverage-honesty guard is hardcoded and not yet driven by source-state contracts. |
| MZ-XR-20260613-003 | Medium | Data | Open | NADAC revival stores legacy/dead Socrata source URL for DKAN CSV-sourced rows. |
| MZ-XR-20260613-004 | Medium | Frontend | Open | DataHub labels proxy quality as FAIR and hides profile failures as empty dossiers. |
| MZ-XR-20260613-005 | Medium | Platform | Open | Legacy eval runner is useful smoke coverage but not sufficient for content richness. |
| MZ-XR-20260613-006 | Low | Data | Open | Brand alias backfill is reversible for cleared fields, but alias-only audit trail is weak. |

## Findings

### MZ-XR-20260613-001 - Source Coverage Can Overstate Availability

Owner: Data  
Severity: High  
Branch/worktree reviewed: `.claude/worktrees/data+source-coverage-freshness`  
Evidence:

- `services/source_coverage.py` counts each configured source by running one
  `SELECT count(*), max(recency)` over the configured table.
- `scheduler/config.py` maps several source types to shared tables. For example,
  EMA and ClinicalTrials.gov both use `clinical_trials`; News and FDA Shortages
  both use `market_events`; PubChem and FDA Orange Book both use `drugs`.

Why it matters:

The answer-path guard can claim a source is populated/fresh because another
source filled the same table. In pharma terms, this is a serious auditability
risk: "EMA available" and "clinical_trials has rows" are not equivalent.

Required direction:

- Add source-specific filters to the coverage configuration, not only table and
  recency column. Examples: `clinical_trials.source_api = 'ema'`,
  `market_events.source_api = 'pharma_news'`, `drug_pricing.source_api =
  'cms_nadac'`.
- Add regression tests where a shared table has rows for source A but zero rows
  for source B; source B must report `NO DATA`.
- Keep row count, age, flow, trust tier, and `may_emit` in the same structured
  object so Platform can consume it without parsing prose.

Exit criteria:

- A source with no source-specific rows cannot be marked GREEN/AMBER merely
  because its table has unrelated rows.
- `coverage_brief` and structured summary agree for shared-table sources.

### MZ-XR-20260613-002 - Platform Coverage Honesty Is Hardcoded

Owner: Platform  
Severity: High  
Branch/worktree reviewed: `C:\Users\kapil\Documents\mz-f6`  
Evidence:

- `services/unified_handler.py` adds `_COVERAGE_LIMITS` regexes for EMA, payer,
  pricing, biosimilar, and sales/revenue limitations.
- The output appends `Coverage limits` text and `data.limitations`, but the
  limitation source is question-text matching rather than the live coverage
  provider.

Why it matters:

The current fix improves F6 G2 behavior, but it can drift as Data changes source
state. NADAC is the obvious example: Data is reviving the pricing source while
Platform still says pricing is "not reliably available" based on hardcoded
phrasing.

Required direction:

- Consume Data's structured source-coverage summary after MZ-XR-20260613-001 is
  fixed.
- Replace generic `SOURCE_COVERAGE_GAP` with source/domain-specific flags such
  as `NO_PAYER_SOURCE`, `EMA_PRODUCT_INFO_NOT_INGESTED`, `NADAC_NO_ROWS`,
  `NADAC_PARTIAL_ROWS`, and `NO_NET_PRICE_SOURCE`.
- Preserve deterministic fallback wording for domains that truly have no
  source, but bind it to a source-state object, not only regex matches.
- Add tests for both sides: a source absent case and a revived/partial source
  case.

Exit criteria:

- A pricing query can distinguish "no payer data", "NADAC has rows but no net
  price", and "NADAC currently has no rows".
- Frontend can read structured `limitations` and `review_flags` without scraping
  the narrative.

### MZ-XR-20260613-003 - NADAC Provenance Points To Dead Legacy URL

Owner: Data  
Severity: Medium  
Branch/worktree reviewed: `.claude/worktrees/data+nadac-pricing-revival`  
Evidence:

- The branch resolves current DKAN CSV URLs dynamically.
- Parsed rows still set `source_url` to legacy `NADAC_API_URL`
  (`https://data.medicaid.gov/resource/4j6z-xnwq.json`), which the branch itself
  documents as dead.

Why it matters:

For pharma pricing evidence, a citation/provenance link must point to the actual
source artifact used. A dead URL weakens trust and makes post-hoc audit harder.

Required direction:

- Carry the resolved DKAN CSV URL into each parsed record or into batch metadata
  joined from pricing rows.
- Store/reveal dataset year/title, retrieval timestamp, and download URL.
- Adjust `stored` stats to reflect actual inserted row count where feasible, or
  rename it to `attempted_store` so idempotent no-op runs are not overstated.

Exit criteria:

- A pricing row can be traced to the exact DKAN CSV distribution used for that
  run.
- Re-running the weekly snapshot does not report attempted inserts as new rows.

### MZ-XR-20260613-004 - DataHub Quality Signals Need More Honest UX

Owner: Frontend  
Severity: Medium  
Branch/worktree reviewed: `C:\Users\kapil\Documents\mz-fe-datahub`  
Evidence:

- `CatalogPage.tsx` maps dataset `quality_score_avg` into `fair_overall`.
- `CatalogHomePage.tsx` labels the ring as FAIR.
- `datasetProfile` failures are converted into a minimal empty dossier with
  `coverage: []`, `records: 0`, and `fair: null`.

Why it matters:

The UI is moving in the right direction by exposing source status, quality, and
freshness. But a proxy dataset quality score is not source-level FAIR, and a
profile failure should not look like an unprofiled but otherwise valid source.

Required direction:

- Label the grid ring "Quality" until a true source-level FAIR endpoint exists.
- Add an explicit degraded/error state for profile load failure, including the
  source key and retry action.
- When Platform/Data provide structured limitations/review flags, surface them
  in DataHub/source dossier as first-class warning rows.

Exit criteria:

- Users can distinguish "not scored yet", "profile endpoint missing/failed",
  and "source is scored but low quality".
- No source-quality UI uses FAIR language unless the underlying API provides
  FAIR dimensions.

### MZ-XR-20260613-005 - Legacy Eval Runner Is Not A Content-Richness Gate

Owner: Platform  
Severity: Medium  
Branch/worktree reviewed: main `benchmark/eval_runner.py` and F6 eval worktree  
Evidence:

- `benchmark/eval_runner.py` scores intent, grounding, factual numeric match,
  evidence count, and bracket citation validity.
- `benchmark/scorers.py` is useful but mostly mechanical; it cannot judge SME
  synthesis, contradiction surfacing, count fallacy, or source-coverage honesty.
- F6 `pharma_eval.py` and `eval_pharma_v2.yaml` test those richer dimensions.

Why it matters:

A system can pass the older runner while still producing thin, overconfident, or
commercially misleading pharma answers.

Required direction:

- Treat the old eval runner as smoke/regression coverage.
- Promote F6 pharma eval to the content-quality gate once merged.
- Track gate-level trends: provenance, closed-world honesty, count-fallacy, and
  domain correctness separately from mean score.

Exit criteria:

- Coordination and release criteria state clearly which eval is smoke coverage
  and which eval is the SME content-quality gate.

### MZ-XR-20260613-006 - Brand Alias Audit Trail Is Partial

Owner: Data  
Severity: Low  
Branch/worktree reviewed: `.claude/worktrees/data+brand-alias-backfill`  
Evidence:

- The backfill is dry-run by default, does not delete rows, and writes a
  manifest for cleared `brand_name` values.
- Alias inserts use `ON CONFLICT DO NOTHING`; reverse deletes all aliases with
  `source_type = brand_backfill`.

Why it matters:

The branch is conservative and useful for brand-name eval cases, but alias-only
changes are not represented in the manifest. If the script inserts aliases but
clears no brand fields, there may be no file-level artifact describing what was
added.

Required direction:

- Include inserted alias candidates in the manifest, even when no rows are
  de-smeared.
- Record canonical choice inputs: brand, chosen canonical id, active/inactive
  status, richness value, and number of competing rows.

Exit criteria:

- Every apply run has a manifest explaining both alias inserts and field clears.

## Lane Instructions

### Platform

1. Own MZ-XR-20260613-002 and MZ-XR-20260613-005.
2. Do not broaden F6 pass claims until coverage honesty is source-state driven
   or the residual is explicitly accepted by the owner.
3. After Data fixes MZ-XR-20260613-001, wire the structured source-coverage
   output into `UnifiedChatHandler`.
4. Keep the old eval runner, but document it as smoke/regression only.

### Data

1. Own MZ-XR-20260613-001, MZ-XR-20260613-003, and MZ-XR-20260613-006.
2. Fix shared-table source coverage before Platform consumes the coverage brief.
3. Make NADAC provenance point to the exact live DKAN artifact, not the dead
   legacy endpoint.
4. Keep conservation proof in the handoff: row counts, source filters, recency,
   manifest rows, and idempotence evidence.

### Frontend

1. Own MZ-XR-20260613-004.
2. Rename proxy FAIR language to quality language until a true source-FAIR API
   exists.
3. Add a visible profile-load failure state.
4. Prepare the DataHub source dossier to display structured limitations and
   review flags once Platform/Data expose them.

## Suggested Review Gate

Before closing these items, each lane should append a handoff in
`docs/REVIEW_LOG.md` with:

- Finding IDs addressed.
- Branch/worktree and commit range.
- Tests run and non-vacuity proof.
- For Data: conservation/provenance proof.
- For Platform: eval gate deltas and response-contract evidence.
- For Frontend: visual/UX test evidence and API contract assumptions.

