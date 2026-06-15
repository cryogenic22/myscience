# Independent DataHub Review - 2026-06-13

Review ID: MZ-DHREVIEW-20260613-001  
Reviewer stance: independent reviewer; pharma SME, AI/data systems, platform/API, frontend contract reviewer  
Scope: merged DataHub loops `#254` D-API-1 `/hub`, `#256` D-API-2 catalog FAIR, `#257` L4a `RssConnector`, plus pre-build review for L4b `WebScrapeConnector`  
Mode: code and diff inspection from merged Git objects on `origin/main`; no product-code edits  

## Executive Verdict

This is a good review area. It is exactly where Market Zero's quality claims
become user-visible: source onboarding, source-level quality, and generic
connectors. The merged work is generally strong and test-backed, especially the
RSS parser's conservation behavior and the `/hub` route's clean error mapping.

The highest-value residuals are seam issues:

- D-API-2 exposes a route named `{source_key}` but appears to query
  `dataset_catalog.dataset_name`, which is not the same identifier.
- Frontend still uses the old proxy quality field and does not call the new FAIR
  endpoint.
- Generic RSS records currently collapse every feed under `SourceType.RSS`,
  which can weaken per-source attribution once multiple RSS feeds are onboarded.

Verdict: `FINDINGS_OPEN`, with no recommendation to block the already-merged
work. The findings should be closed before building more generic connectors on
the same seam.

## Review Log

| Finding ID | Severity | Owner | Status | Summary |
|---|---|---|---|---|
| MZ-DH-20260613-001 | High | Platform | Open | `/catalog/datasets/{source_key}/fair` is keyed like a source key but queries `dataset_name`. |
| MZ-DH-20260613-002 | High | Frontend | Open | Catalog UI still proxies `quality_score_avg` and never calls the new FAIR endpoint. |
| MZ-DH-20260613-003 | Medium | Data | Open | Generic RSS records do not preserve the onboarded `source_id` in downstream provenance. |
| MZ-DH-20260613-004 | Medium | Data / Platform | Open | `/hub/onboarding/{source_id}` idempotent replay still uses HTTP 201 semantics. |
| MZ-DH-20260613-005 | Medium | Data | Open | L4b WebScrapeConnector needs a fail-closed design gate before implementation. |

## Artifacts Reviewed

- Commit `9fe8f5f` - `feat(datahub): D-API-1 - REST surface for L2 connector-taxonomy + onboarding (#254)`
- Commit `e8e54b6` - `feat(datahub): D-API-2 - source-level FAIR aggregate for the Catalog grid ring (#256)`
- Commit `4dac947` - `feat(datahub): L4a - generic config-driven RssConnector (+ SourceType.RSS) (#257)`
- Commit `a7ee278` - coordination update for L4a merged / L4b next / L4c deferred
- `api/routes/hub.py`
- `api/routes/catalog.py`
- `connectors/rss_connector.py`
- `connectors/base.py`
- `services/connector_taxonomy.py`
- `integration/dataset_catalog.py`
- `frontend/src/pages/CatalogPage.tsx`
- `frontend/src/api.ts`
- `tests/test_hub_api.py`
- `tests/test_dataset_fair.py`
- `tests/test_rss_connector.py`

## Findings

### MZ-DH-20260613-001 - FAIR Endpoint Uses The Wrong Key Surface

Owner: Platform  
Severity: High  
Area: D-API-2 / catalog API  
Evidence:

- `api/routes/catalog.py` defines `GET /catalog/datasets/{source_key}/fair`.
- The handler queries `dataset_catalog WHERE dataset_name = %s`.
- `integration/dataset_catalog.py` defines dataset names such as
  `clinical_trials_gov.trials`, `clinical_trials_gov.outcomes`,
  `pubmed.articles`, and `sec_edgar.filings`.
- The frontend source key is `ds.source_type`, for example
  `clinical_trials_gov`, and `datasetProfile(sourceKey)` already uses canonical
  source keys.

Why it matters:

The endpoint name and the frontend contract imply canonical source keys, but the
SQL expects dataset names. A call to `/catalog/datasets/clinical_trials_gov/fair`
can 404 even though that source has multiple catalog datasets and a profile.

Required direction:

- Decide the contract explicitly:
  - If the endpoint is source-level, query by `source_type` and aggregate across
    all rows for that source.
  - If the endpoint is dataset-level, rename the path parameter and frontend
    API method to `dataset_name`, and pass names like `clinical_trials_gov.trials`.
- Add route-level tests for both known and unknown keys. Current tests only cover
  the pure `_dataset_fair` scorer, not HTTP key semantics.
- Keep the output name honest: `source_key` for aggregated source-level output,
  `dataset_name` for one dataset row.

Exit criteria:

- `GET /catalog/datasets/clinical_trials_gov/fair` succeeds if the frontend is
  expected to call it with `source_type`.
- Tests fail if `source_type` and `dataset_name` are mixed up again.

### MZ-DH-20260613-002 - Frontend Still Does Not Consume D-API-2

Owner: Frontend  
Severity: High  
Area: CatalogPage / DataHub source dossier  
Evidence:

- `frontend/src/pages/CatalogPage.tsx` maps `fair_overall` from
  `ds.quality_score_avg`.
- The same file still says source-level FAIR does not exist and sets
  `SourceDetail.fair = null`.
- `frontend/src/api.ts` has `catalogDatasets()` and `datasetProfile()` but no
  visible method for `GET /catalog/datasets/{key}/fair`.

Why it matters:

D-API-2 has landed, but the UI remains on the old degradation path. Users will
see proxy quality values instead of the derived source/dataset FAIR composite,
and source dossiers cannot show the per-dimension breakdown.

Required direction:

- Extend `CatalogDataset` to include `fair_overall`.
- Use `ds.fair_overall` for the grid ring, not `quality_score_avg`.
- Add an API client method for the FAIR endpoint after Platform resolves
  MZ-DH-20260613-001 key semantics.
- On source click, fetch profile and FAIR breakdown together, then populate
  `SourceDetail.fair`.
- Keep the UI honest when FAIR is missing: distinguish `not profiled`, `profile
  failed`, and `0-row red`.

Exit criteria:

- Catalog grid displays backend-provided `fair_overall`.
- Source dossier renders real per-dimension FAIR when available.
- Tests cover `fair_overall` separately from `quality_score_avg`.

### MZ-DH-20260613-003 - Generic RSS Source Attribution Collapses To `rss`

Owner: Data  
Severity: Medium  
Area: L4a `RssConnector` / downstream source attribution  
Evidence:

- `RssConfig` carries `source_id`, but `RawRecord` only carries
  `provenance.source_type = SourceType.RSS`, `source_name`, endpoint, data, and
  identifiers.
- Downstream integration code commonly stores or resolves source attribution from
  `record.provenance.source_type.value`.
- With multiple onboarded RSS feeds, records can collapse under the single
  source key `rss` rather than the registered source id, unless every downstream
  consumer independently inspects endpoint or source name.

Why it matters:

DataHub's generic connector strategy depends on per-source quality, freshness,
review, and provenance. A generic connector type is not the same as a source id.
For pharma intelligence, FDA RSS, company IR RSS, arXiv Atom, and trade press RSS
must remain separable.

Required direction:

- Preserve `config.source_id` in a downstream-visible field. Options:
  - Add a `source_id` field to `Provenance` / `RawRecord` through a deliberate
    contract change.
  - Or consistently include `source_id` in `RawRecord.identifiers` / `data` and
    update downstream storage to prefer it for registry attribution.
- Add tests showing two RSS configs with different `source_id` values produce
  distinguishable downstream attribution.
- Document the distinction between connector type (`RSS`) and source id
  (`fda_press_rss`, `arxiv_pharma_feed`, etc.).

Exit criteria:

- Source quality/freshness can be computed per RSS feed, not just for all RSS
  records together.

### MZ-DH-20260613-004 - Idempotent Onboarding Replay Still Looks Created

Owner: Data / Platform  
Severity: Medium  
Area: D-API-1 `/hub/onboarding/{source_id}`  
Evidence:

- `start_onboarding()` is intentionally idempotent and returns an existing row
  unchanged.
- The route is declared with `status_code=201` for every successful response.
- Tests assert idempotency at function level but do not assert HTTP status or a
  created/existing discriminator.

Why it matters:

The behavior is safe, but the HTTP semantics can mislead the frontend and logs.
An existing onboarding record is not newly created. In a wizard, this distinction
matters for user messaging and audit trails.

Required direction:

- Return `200` for existing rows and `201` for newly inserted rows, or keep `201`
  but include an explicit `created: true/false` flag.
- Add route-level TestClient coverage for create vs replay.

Exit criteria:

- The frontend can distinguish "started now" from "already existed".

### MZ-DH-20260613-005 - L4b Needs A Fail-Closed Design Gate

Owner: Data  
Severity: Medium  
Area: L4b `WebScrapeConnector` pre-build  
Evidence:

- Coordination correctly queues L4b separately because HTML scraping needs
  `bs4`, robots handling, and a real prod probe.
- The repo already has source-specific scraper patterns, but not a generic
  fail-closed HTML-record connector.

Required design before build:

- Robots/politeness:
  - Check robots.txt for each configured source.
  - Use a configured user-agent and timeout.
  - Support rate limits / max pages / max bytes.
  - Denied robots should fail closed with a clear status, not silently scrape.
- Selector contract:
  - Require explicit item selector, id selector, text selector, optional date
    selector, and optional link selector.
  - Empty selector matches should be an error unless the source is explicitly
    allowed to be empty.
  - Missing external id should be skipped and counted, mirroring RSS/CSV.
- Content hygiene:
  - Strip scripts/styles/nav boilerplate.
  - Resolve relative links against the page URL.
  - Decode entities and normalize whitespace.
  - Cap text length while preserving a hash of the full selected HTML/text.
- Provenance:
  - Preserve registered `source_id`, page URL, selector version, retrieval time,
    and content hash.
  - Store enough detail to explain why a record was included/skipped.
- Tests/probes:
  - DB-free fixture tests for normal page, no-id skip, missing selector error,
    undated kept, malformed HTML tolerated only where parser can recover.
  - At least one real public prod probe with robots allowed.

Exit criteria:

- L4b cannot pass with an empty fixture, all-skipped selector, or robots-ignored
  scrape.

## Positive Findings

- D-API-1 is additive and maps taxonomy/service exceptions to clean HTTP errors.
- D-API-1 tests cover direct route functions and route mounting.
- D-API-2 scorer is conservative for missing dimensions and correctly treats
  zero-row datasets as red.
- RSS parser supports RSS 2.0 and Atom, keeps undated records, raises on
  malformed feeds, and includes `content:encoded` in text extraction.
- Splitting L4a/L4b/L4c is the right engineering choice; Warehouse should remain
  deferred until there are drivers and live credentials for a non-vacuous probe.

## Closure Protocol

Each owner should close findings by appending a handoff to `docs/REVIEW_LOG.md`
with:

- Finding IDs addressed.
- Branch/worktree and commit range.
- Tests run and non-vacuity proof.
- For Platform: route-level API tests and OpenAPI/API client contract notes.
- For Data: conservation/provenance proof and live probe details.
- For Frontend: API wiring tests and visible UX states.

