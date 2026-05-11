# Loop #9 — Swap mocks to real data (BE-3 / BE-6 / BE-8 just merged)

**Status:** Shipped 2026-05-11
**Type:** refactor (productionises 2 frontend scaffolds)
**Closes:**
- PB-301 (dossier) goes from mock to live data via BE-6.
- PB-501 (payoff matrix) goes from mock to live data via BE-8.

## Why

Loops 6 + 7 shipped frontend scaffolds for the dossier and payoff
matrix surfaces while their backend composers were still in review.
PR #57 (BE-6 `GET /dossier/{type}/{slug}`) and PR #59 (BE-8
`POST /war-rooms/{id}/payoff-matrix`) merged moments before this
loop, so the placeholder banners come down and the hooks point at
real endpoints.

BE-3 (PR #50 — `agent` field on `/agent/events`) merged in the same
batch but it unblocks PB-202 (live activity feed), not PB-201; no
swap is required for the agent identity strip.

## What ships

1. **`src/types/dossier.ts`** — `Dossier` keeps the frontend-friendly
   shape (`canonical_name`, `external_ids`, `primary_attributes`,
   `evidence`, `watchers`). `is_mock` field removed.
2. **`src/types/payoff.ts`** — `PayoffMatrix` keeps the flat
   `cells[]` keyed by `row_id`/`col_id`. `is_mock` field removed.
3. **`src/hooks/useDossier.ts`**
   - Exposes `adaptDossierResponse(wire, slug)` so the
     wire→frontend mapping is unit-testable.
   - `fetchDossier` hits the real `GET /dossier/{type}/{slug}`.
   - Mapping rules:
     - `entity.name` → `entity.canonical_name`
     - URL slug → `entity.slug` (backend does not echo)
     - `entity.identity_fields` partitioned: known external-ID keys
       (`rxnorm`, `chembl`, `unii`, `inn`, `cas`, `ndc`, `nct_id`,
       `cik`, `lei`, `ticker`, `mesh_id`, `doi`, `pmid`, `wikidata`,
       anything ending in `_id`) → `external_ids`; other scalars →
       `primary_attributes`; arrays / nested objects dropped.
     - `synthesis.text_with_citation_marks` → `synthesis.summary`;
       citations remain `[]` until PB-302 wires inline marks.
     - `evidence_refs` → `evidence` (renamed `evidence_id` → `id`,
       `source_tier` → `tier`); invalid/missing tier defaults to T3.
     - `watching` → `watchers`; `watcher_count` derived from length.
4. **`src/hooks/usePayoffMatrix.ts`**
   - Exposes `adaptPayoffResponse(wire, roomId, ourMoves,
     adversaryStates)`.
   - `fetchPayoffMatrix` POSTs to
     `/war-rooms/{id}/payoff-matrix` with sensible defaults
     (`our_moves: ['launch_q3', 'wait_q4']`, `adversary_states:
     ['defend', 'cede']`, `samples: 1200`). Future PB (PB-502 /
     PB-503) will let analysts customise these.
   - Mapping rules:
     - 2D `cells[][]` → flat `cells[]` keyed by `r-<move>` /
       `c-<state>` IDs.
     - `recommended_cell: [r, c]` → `{ row_id, col_id }`; null
       passes through.
     - `outcome` derived from `delta_pct`: `|d| < 2 → neutral`,
       `d > 0 → win`, `d < 0 → lose`.
   - Auth header added — endpoint requires uploader role.
5. **`src/pages/DossierPage.tsx`** — drops the "Showing placeholder
   data" banner. Component logic unchanged.
6. **`src/components/ci/war/PayoffMatrix.tsx`** — drops the
   placeholder banner. Component logic unchanged.
7. **`src/api.ts`** — `BASE` is now exported so hooks share the
   single source of truth.

## Tests

- `__tests__/hooks/useDossier.adapter.test.ts` — 8 cases covering
  the BE-6 → frontend mapping (name, slug, identity-field
  partitioning, synthesis null/text, evidence rename + tier default,
  watcher count).
- `__tests__/hooks/usePayoffMatrix.adapter.test.ts` — 7 cases
  covering the BE-8 → frontend mapping (2D→flat reshape, row/col
  labels, recommended pair, outcome derivation, null recommended,
  dimension validation).
- `__tests__/pages/DossierPage.test.tsx` — 1 banner test removed;
  `is_mock` field stripped from fixture.
- `__tests__/ci/war/PayoffMatrix.test.tsx` — 2 banner tests removed;
  `is_mock` field stripped from fixtures.

## Quality gate

- `npx tsc --noEmit` → clean
- `npx vitest run --no-file-parallelism` → **339 passing, 22 todo,
  0 failures attributable to this loop**.
  (One pre-existing flake in `DecisionWorkspace.test.tsx`
  "cmd+enter advances state when allowed" — passes when run in
  isolation; SPEC-030 territory, untouched here.)
- `python -m scripts.validate_product_backlog` → OK

## What this loop does NOT touch

- `synthesis.citations` rendering — PB-302 wires inline citation
  marks from `synthesise_dossier`. The summary text is shown
  verbatim today, marks included.
- Customisable `our_moves` / `adversary_states` — defaults baked in
  via `DEFAULT_OUR_MOVES` / `DEFAULT_ADVERSARY_STATES` constants;
  PB-502 / PB-503 add the UI for analysts to choose.
- Auth fallback when the user lacks the uploader role — payoff
  matrix simply fails silently (matches Loop #7 behaviour); a
  follow-up loop can add a "log in to simulate" hint.
- AgentIdentityStrip — BE-3's `agent` field on `/agent/events`
  unblocks PB-202 (live feed), not PB-201; no change here.
