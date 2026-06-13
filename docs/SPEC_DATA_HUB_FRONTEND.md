# SPEC — DataHub Frontend (the Catalog UX)

*Build spec + task board for the **Frontend (Claude) agent**. Status: ready to
build, 2026-06-13. This is the frontend companion to the backend spec.*

> **Read these two first (the "why" + the picture):**
> - **`docs/SPEC_DATA_HUB.md`** — the full DataHub spec (5 pillars, the lenses §2.1,
>   the two flagship flows §6, the roadmap §9). This frontend spec implements its
>   FRONTEND rows.
> - **`docs/data-hub-vision.html`** — the visual walkthrough / vision deck (open it
>   in a browser; it's the design north-star for look + flow).

---

## 0. Mission

Turn DataHub from a set of backend capabilities into **one product surface**: a
curator can *see* every connected source + dataset + entity (with status + FAIR),
*onboard* a new source through a guided wizard, *curate* it, and *delegate*
enrichment to an agent — governance + provenance always visible. **~80–95% of the
backend already exists** (see §3); your job is mostly **composition over existing
APIs + a few new flows**. Reuse before you build.

## 1. Ground rules (non-negotiable — from `CLAUDE.md`)

- **Reuse-first.** Before any new component/util, read `.claude/rules/anti-slop.md`
  and grep. Reuse the existing `frontend/src/api.ts` clients + types; do NOT
  redefine `CatalogDataset`, `DatasetProfile`, `QualityResult`, `SourceCoverageItem`,
  etc.
- **Styling:** CSS custom properties (`var(--color-ink)`, `var(--color-surface)`,
  `var(--color-accent)`, `var(--color-line)`) + inline styles / authored CSS.
  **NOT** Tailwind color utilities. **NEVER** build class names dynamically
  (`` `text-${x}` ``) — the Tailwind v4 scanner can't see them and they no-op in
  the Railway build. Don't remove the `@source` globs in `index.css`.
- **TDD:** every component/hook ships with a Vitest test that fails without it
  (`frontend/__tests__/...`). Match sibling test patterns.
- **Match patterns:** read 2–3 sibling files before writing (e.g. `SourcesPage`,
  `DataCatalogPanel`).
- **Lane + merge discipline:** Frontend is the **Frontend (Claude) agent** lane
  (`frontend/` app shell + non-CI surfaces). Touch `App.tsx` / shared shell files
  **additively + minimally**. **No self-merge** — every PR gets an independent
  `/review-gate` pass before merge. Claim your loop in `COORDINATION.md` §7.6
  before starting (the STOP-AND-SYNC protocol applies to all lanes now).
- **No vacuous UI:** a source that lands 0 rows shows **RED**, not "connected".
  When a backend field is missing, **degrade honestly** (a "pending"/"profiling"
  placeholder) — never fabricate a number (no coerced FAIR, no fake counts).

## 2. The lens model (what "Catalog" means)

"Catalog" is **one app with lenses** onto the same governed objects — not five apps.
Each lens is **read-mostly**; the only writes are "enhance" actions that route
through the existing pipeline/steward (so provenance + conservation gates still
apply). Lenses (from `SPEC_DATA_HUB.md` §2.1):

| Lens | Surfaces | Loop |
|---|---|---|
| Sources / connectors | catalog home, source dossier, connect wizard | **F1, F5** |
| Documents & vectors | docs/chunks list + embedding status + enhance | **F2** |
| Entities · ontology · data-model | read-only model map + entity graph + MeSH | **F3** |
| Prompts & domain packs | prompt versions + packs + observational impact | **F4** |
| Govern | provenance/lineage/lifecycle board | **F7** |
| AI co-pilot / autonomous jobs | onboarding co-pilot + job timeline | **F6** |

⛔ **Deliberately OUT of scope** (over-engineering traps, per the backend spec):
a full DMS; an interactive ontology/schema **editor** (it's a view); a new
prompt-experimentation / **A/B platform** (surfacing only); true counterfactual
prompt re-runs.

---

## 3. What ALREADY EXISTS — reuse this (grounded inventory)

### 3.1 Backend API (live today — your integration surface)
**Catalog** (`api/routes/catalog.py`, mounted at `/catalog`):
`/datasets`, `/datasets/{key}/profile`, `/featured`, `/entities/{type}`,
`/entities/{type}/{id}` (+ PATCH + `/tags`), `/entity-profile/{type}/{id}` (FAIR
5-dim per entity), `/changes`, `/hitl` (+ `/{id}/resolve`), `/quality`,
`/completeness`, `/freshness`, `/graph-summary`, `/ta-coverage`,
`/pipeline-status`, `/source-profile/{key}`, `/sources/{key}/records`,
`/sources/{key}/connections`, `/stats`, `/24h-stats`, `/enrich`, `/run-enrichment`,
`/bulk-update`, `/bulk-resolve`, `/refresh-views`.
**Sources** (`api/routes/sources.py`, mounted at `/sources`):
`GET /` (list), `POST /` (register), `GET/PATCH /{id}`, `/{id}/fair`,
`/{id}/schema`, `/{id}/history`, `/{id}/recompute`, `/health-summary`.

### 3.2 Frontend already built (reuse / extend — do NOT rewrite)
- **`frontend/src/api.ts` clients:** `catalogStats`, `catalogDatasets`,
  `datasetProfile`, `catalogChanges`, `catalogQuality`, `catalogFreshness`,
  `catalogPipelineStatus`, `sourceProfile` (+ their typed returns).
- **Components:** `components/DataCatalogPanel.tsx` (browse, dataset profiles,
  entity detail/profile, edit + change log), `components/SourceProfileCard.tsx`
  (FAIR breakdown + schema preview + history), `pages/SourcesPage.tsx`
  (source-class tiles + outlet table).
- **✅ Loop F1 is already partially done** on branch **`claude/datahub/phase0-lenses`**
  (NOT yet merged — needs `/review-gate`):
  - `pages/CatalogHomePage.tsx` (commit `b8a7f39`) — searchable/filterable source
    grid (connector type, status verdict, data type, FAIR ring) + source dossier
    (5-dim FAIR, schema preview, coverage). 16 tests.
  - `pages/CatalogPage.tsx` + `/hub/catalog` route (commit `960de83`) — the live
    container wiring `catalogDatasets()` + `catalogPipelineStatus()` + dossier via
    `datasetProfile()`. 5 tests. Typecheck clean.
  - **First action: rebase that branch on `main`, get a `/review-gate`, merge, then
    continue F1 from there** (don't re-build it).

### 3.3 Backend agentic primitives the later loops surface (exist, see SPEC_DATA_HUB §3.4)
`MarketZeroHarness`, tool registry, `AutonomousResearchAgent` (the enrichment-job
loop shape), `llm_gateway` (versioned prompt registry), `learning_service`
(calibration flags + eval-score trend), `schema_introspector` (DB → model map).

---

## 4. Backend dependencies the frontend needs (DATA-LANE will provide)

These do not exist yet; they are the **contract** between this spec and the data
lane. Each frontend loop notes which it needs. **Data lane: build these as small
read-endpoints over the existing services; tracked in `COORDINATION.md` §7.3.**

| ID | Endpoint(s) | Backs | Reuses | Status |
|---|---|---|---|---|
| **D-API-1** | `GET /hub/connector-types`; `GET/POST /hub/onboarding/{source_id}` (start + advance lifecycle) | F5 wizard, F1 status chips | L2 `services/connector_taxonomy.py` (#245) — just expose it | **TODO (data)** |
| **D-API-2** | source-level **FAIR aggregate** — `fair_overall` on `/catalog/datasets` rows OR `GET /catalog/datasets/{key}/fair` | F1 grid ring + dossier | per-entity FAIR exists; aggregate per source | **TODO (data)** |
| **D-API-3** | `GET /hub/documents` (docs/chunks + embedding status); enhance actions `POST /hub/documents/{id}/re-embed|re-extract` | F2 | `api/routes/upload.py` + `search.py` + pipeline | TODO (data, later) |
| **D-API-4** | `GET /hub/model-map` (tables/FKs/join-paths) | F3 | `schema_introspector` | TODO (data, later) |
| **D-API-5** | `GET /hub/prompts` (versions + pack list + calibration/eval trend for a pinned version) | F4 | `llm_gateway` prompt registry + `learning_service` + eval runs | TODO (data, later) |
| **D-API-6** | connector-draft/synthesis/sandbox + enrichment-job endpoints | F5 (AI path), F6 | SPEC_DATA_HUB L6–L10 (not built) | BLOCKED on backend L6+ |

> A frontend loop that needs a missing endpoint should **build against a typed stub
> + degrade gracefully** (the F1 pattern: `fair={null}` → "profiling…"), and the
> wiring is a one-line swap when the endpoint lands. Don't block; don't fake data.

---

## 5. The frontend build loops (each: shippable, TDD, review-gated)

> Claim a loop in `COORDINATION.md` §7.6 before starting. Each loop = its own PR.

### Phase A — Catalog truth (surface what exists)
- **F1 — Catalog Home + Source dossier + nav.** *Mostly done on `phase0-lenses`.*
  Finish: rebase+review+merge that branch; add a **DataHub** entry to the top nav
  (`components/layout/TopBar.tsx`, additive); wire **D-API-2** FAIR aggregate when
  it lands. *Reuse:* `CatalogHomePage`/`CatalogPage`, `SourceProfileCard`,
  `catalogDatasets`/`catalogPipelineStatus`/`datasetProfile`. *Accept:* every source
  visible with connector type + status verdict (0-rows = RED) + FAIR; search +
  filter; dossier drill-in; route in nav; tests green; typecheck clean.
- **F2 — Documents & vectors lens.** Docs/chunks list (what's stored, embedding
  status, source, links) + **enhance** buttons (re-embed / re-extract / re-link)
  that POST to the pipeline. *Needs D-API-3.* *Accept:* list with real embedding
  status; enhance triggers a pipeline run + shows the FAIR delta; no DMS scope.
- **F3 — Ontology & data-model lens (read-only).** Model map (tables, FKs,
  entity_links, join paths) from **D-API-4** + reuse the existing
  `GraphExplorer`/`KnowledgeGraph` for the entity graph + MeSH ontology browse.
  *Accept:* a navigable read-only map; NO editor.
- **F4 — Prompts & packs lens (observational).** Browse `prompt_registry` versions
  + the YAML packs (read-only) via **D-API-5**; **observational impact** view: pin a
  version → show its `learning_service` calibration trend + the eval scores around
  its activation date. *Accept:* surfacing only — **NO experimentation / A-B
  platform** (the #1 trap).

### Phase B — Connect any source
- **F5 — Connect wizard.** Guided onboarding for the 5 source kinds (REST / RSS /
  CSV / web / warehouse). Manual mapping first (declare connector type +
  field/record mapping), register the source + start onboarding lifecycle via
  **D-API-1**; show a sandbox preview when the AI path (**D-API-6**) lands. *Accept:*
  a curator can onboard a CSV/REST source end-to-end through the UI; the lifecycle
  (`draft→test→staged→prod`) is visible + advanceable; every onboarded source must
  declare a contract (trust tier + must-capture) or the wizard blocks.

### Phase C — AI + governance
- **F6 — AI co-pilot + autonomous-job timeline.** Chat-to-onboard ("gather X for
  every Y") → compiles to an enrichment job; a timeline of autonomous runs with
  per-step evidence + FAIR delta + commit/revert. *Needs D-API-6.* *Accept:* a job
  can be expressed, launched, and watched with provenance per step.
- **F7 — Governance board.** Provenance / lineage / lifecycle / license/trust over
  the facts + evidence ledger + conservation-gate verdicts. *Reuse:* the existing
  ledger surfaces + `connector_health`. *Accept:* for any fact/source you can see
  its provenance chain + lineage + lifecycle state + gate status.

---

## 6. Definition of Done (every frontend loop)

1. RED→GREEN: a Vitest test fails without the change, passes with it — **paste the
   output**.
2. `npx tsc --noEmit -p tsconfig.app.json` → exit 0 (no vacuous typecheck).
3. Reuses existing `api.ts` clients/types; no anti-slop duplication.
4. CSS-variable styling; no dynamic class names; `@source` globs intact.
5. Honest degradation for any missing backend field (no fabricated data).
6. Claimed in `COORDINATION.md` §7.6; **independent `/review-gate`** before merge;
   no self-merge; `App.tsx`/shell edits additive + minimal.

---

## 7. Suggested order

`F1 (finish+merge) → F5 (the differentiator: onboard a source) → F2 → F3 → F4 → F7
→ F6`. F1 + F5 deliver the headline "onboarding is a product" story fastest; the
other lenses are incremental reads over existing APIs. F6 waits on backend L9–L10.
