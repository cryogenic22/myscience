# Connector spec schema

A **connector spec** is one plain YAML file in this directory that declares how to
ingest one data source — no Python required. The agent ("Connector Press") and the
Connect wizard both produce these files; `connectors/spec.py` loads + lints them
and turns them into one of the existing generic connectors
(`RestConnector` / `CsvConnector` / `RssConnector`). Because those emit the
universal `RawRecord`, an onboarded source then flows through the *same*
`IntegrationPipeline` as every built-in connector — entity resolution,
cross-linking, FAIR scoring, quality gates and catalog preview all light up
automatically.

> The spec file owns the **definition** (git-tracked, reviewable, the compounding
> library). The DB (`sources` + `source_onboarding`) owns **runtime state**
> (lifecycle status, etl_runs, FAIR history). `register` keeps them in step.

## Fields

| Field | Required | Meaning |
|---|---|---|
| `source_id` | ✓ | Stable string key (e.g. `eu_drug_pricing`). Becomes the per-source identity everywhere (`etl_runs.source_name`, `source_api`, FAIR, catalog). |
| `source_name` | ✓ | Human-readable display name. |
| `connector_type` | ✓ | One of `API_REST`, `CSV_FILE`, `RSS`, `WEB_SCRAPE`, `WAREHOUSE`, `MANUAL`. Only the first three have a runtime connector today; the rest persist + draft but do not auto-run yet. |
| `record_type` | ✓ | Which **existing** core entity these rows are: `drug`, `company`, `trial`, `event`, `literature`, … (a `RecordType`). Phase 1 onboards sources that map to an existing entity type. |
| `config` | ✓ (runtime types) | The connector config — keys mirror `RestConfig` / `CsvConfig` / `RssConfig` (see below). |
| `trust_tier` | — | Data-contract trust tier `1` \| `2` \| `3`. |
| `must_capture` | — | Field names that must be present or the row is rejected (the contract). |
| `license` | — | Data licence string. |
| `cadence` | — | APScheduler `CronTrigger` kwargs, e.g. `{hour: "*/12"}`. Omit ⇒ a default by tier/connector type. |

### `config` keys by connector type
- **API_REST** (`RestConfig`): `url` (req), `external_id_field` (req), `records_path`, `field_map`, `identifiers_map`, `text_field`, `since_field`, `pagination` (`none`\|`page`\|`offset`\|`cursor`), `auth_type` (`none`\|`bearer`\|`basic`\|`api_key`), `query_params`, … Secrets (`auth_token`, `api_key`, `auth_password`) are **not** stored in this file — they are supplied out-of-band (DB/env).
- **CSV_FILE** (`CsvConfig`): exactly one of `url`/`path` (req), `external_id_field` (req), `field_map`, `identifiers_map`, `text_field`, `since_field`, `delimiter`.
- **RSS** (`RssConfig`): `url` (req), `external_id_field` (default `guid→id→link`), `field_map`, `identifiers_map`, `text_field`.

`field_map` maps a source field → the data key our pipeline reads;
`identifiers_map` maps a source field → a resolver key (the keys the 6-strategy
entity resolver matches on, e.g. `generic_name`, `nct_id`, `cik`) so the records
auto-link to the core data model.

## Ops
- **lint** — `ConnectorSpec.load(path).lint()` returns a list of problems (`[]` = valid).
- **build** — `build_connector_from_spec(spec)` returns a ready connector.
- **register** — persists the spec (file + DB) and, once promoted to `prod`,
  the scheduler runs it on `cadence` and the source lights up with every feature.

See `example_rest.yaml` for a template.
