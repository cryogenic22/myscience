# @pulse/api-contracts

OpenAPI 3.1 specifications for PulseAction.AI's platform-level APIs.

Three contract surfaces, one per layer:

| File | Surface | Owner |
|---|---|---|
| `src/catalog.yaml` | Data Catalog Layer (`/catalog/*`) — entities, documents, links, resolution, freshness | Platform team |
| `src/intel.yaml` | Intelligence Layer (`/intel/*`) — signals, events, synthesis, ask, health | Platform team |
| `src/platform.yaml` | Cross-cutting (`/platform/*`) — me, modules, activity, cost, audit | Platform team |

Module-specific APIs (e.g. `/ci/digest`, `/ci/watchlists`) are owned by the modules themselves and live in their own services. They are NOT in this package.

## Status

**Phase 0 / M0 contracts.** Hand-authored YAML. No backend implementation yet — these are the *target shapes* the implementation in Phase 1 swimlanes A, B, C will conform to.

## What this enables right now (without backend code)

- Frontend (`apps/landing`, `apps/ci`) can mock against these shapes via tools like `@stoplight/prism-cli` or `msw` with codegen'd handlers.
- Backend (Phase 1) writes endpoints that conform to these YAML contracts — divergence is caught by contract tests.
- Cross-team conversations have a single source of truth.

## Phase 1 follow-ups

| Task | Sprint |
|---|---|
| Add `@redocly/cli` for spec linting (CI gate) | A1 |
| Add `openapi-typescript` codegen → emit `@pulse/domain-types` | A1 |
| Add Schemathesis (or similar) contract tests against the FastAPI implementation | A7 / B7 |
| Render Redoc/Stoplight docs at `/docs/api/` per release | A8 |
| Auto-publish OpenAPI bundle to npm tag matching backend version | B8 |

## Versioning

Bumped per breaking change. Non-breaking additions (new optional fields, new endpoints) bump the patch. Breaking changes (renames, removals, type changes on existing fields) require a major version + a deprecation header in the spec for one minor cycle before removal.

## How to read these specs

- Every endpoint has an `operationId` — used by codegen to name the TS function.
- Every schema is named — used by codegen to name the TS type.
- `tag` groups are the conceptual buckets a frontend dev uses to find what they need.
- Pagination is cursor-based across the board (`cursor` + `next_cursor`).
- Errors follow a single shape: `{ code, message, request_id }`.

## Conventions baked in

- IDs that come from `gen_random_uuid()` are typed as `format: uuid`. IDs that come from external sources (NCT, CIK, DOI) are plain `string`.
- Timestamps are RFC 3339 (`format: date-time`).
- Confidence is always in [0, 1]. Tier enums are explicit and locked.
- Provenance is a first-class object on every Document — never optional.
- Evidence on Signals is `minItems: 1` per the no-fabrication invariant.
