# ADR-001 — Monorepo Restructure: Scaffold Alongside, Migrate Incrementally

**Status:** Accepted
**Date:** 2026-04-27
**Decision driver:** SPEC-016 §5.1 mandates a monorepo (`apps/ + packages/ + services/ + schema/`). The existing repo is flat and runs in production. A destructive rename in one PR is too risky.

---

## Decision

We **scaffold the new monorepo structure alongside the existing tree**, leaving every currently-deployed path working unchanged. The existing `frontend/` keeps building via `cd frontend && npm ci && npm run build` (Railway nixpacks). The Python tree at root keeps importing as `from api.app import …`. Migration to the target layout happens incrementally, one workspace at a time, with explicit deletion of the old path only after the new path is proven.

This trades short-term root-directory clutter for zero-risk-of-production-outage during the restructure.

## Context

Current layout (flat):
```
market_zero/
├── api/              ← FastAPI app
├── services/         ← business services
├── connectors/       ← data connectors
├── integration/      ← pipeline glue
├── domain/           ← domain pack
├── schema/           ← SQL migrations
├── frontend/         ← React 19 SPA
├── tests/            ← pytest
└── ...
```

Target (per SPEC-016):
```
market_zero/
├── apps/{landing,ci,research}
├── packages/{design-tokens,ui,api-client,domain-types,eslint-config}
├── services/{platform,module_ci,module_research,workers}
├── packages-py/{catalog,intelligence,domain_pharma}
├── schema/{platform,modules/{ci,research}}
├── ops/, docs/, tests/
```

Production today:
- Railway deploys via `nixpacks.toml` which runs `cd frontend && npm ci && npm run build` and `python start.py`.
- 543+ tests pass against the flat Python tree.
- 32 React components + 7 hooks + 3 pages live in `frontend/src/`.
- 233+ Python source files reference each other as `from api.x import …`, `from services.y import …`, `from connectors.z import …`.

A clean rename of all of these in one PR would touch ~250+ files, break every import, change every Railway path, and require a coordinated deploy. There is no way to validate that PR end-to-end in a single session.

## Constraint we honor

**Never break the existing build path.** Anything that's currently deployed and tested stays at its current path until its replacement at the new path is built, tested, and proven in staging.

## Consequences

### What we add now (scaffold)

```
market_zero/
├── apps/
│   ├── landing/        ← NEW Mission Control SPA (Vite + React)
│   └── ci/             ← NEW MZ · CI module SPA (Vite + React)
├── packages/
│   ├── design-tokens/  ← NEW (token JSON → CSS vars + TS types)
│   ├── ui/             ← NEW (shared primitives + Storybook)
│   └── eslint-config/  ← NEW (shared lint rules)
├── docs/
│   └── adrs/           ← NEW (this file lives here)
├── pnpm-workspace.yaml ← NEW
├── turbo.json          ← NEW (build orchestration)
├── package.json        ← NEW root, workspace-only, scripts pass-through
├── tsconfig.base.json  ← NEW shared TS config
├── .npmrc              ← NEW
└── .nvmrc              ← NEW (node 22)
```

### What we leave alone (for now)

```
market_zero/
├── frontend/           ← UNCHANGED (becomes apps/research/ in Phase 1.5)
├── api/                ← UNCHANGED (becomes services/platform/ + services/module_*/)
├── services/           ← UNCHANGED (factored into platform/ + module_*/)
├── connectors/         ← UNCHANGED (becomes packages-py/catalog/connectors/)
├── integration/        ← UNCHANGED (becomes packages-py/catalog/)
├── domain/             ← UNCHANGED (becomes packages-py/domain_pharma/)
├── schema/             ← UNCHANGED (gets re-rooted under platform/ + modules/)
├── tests/              ← UNCHANGED
└── nixpacks.toml       ← UNCHANGED (existing build path keeps working)
```

The Railway build, the existing test suite, all 17 connectors, and the entire `/research` chat surface keep working through Phase 1 without modification.

## Migration plan (incremental)

Each step ships independently, has its own PR, and is fully tested before the next starts.

| Step | Move | When | Risk | Rollback |
|---|---|---|---|---|
| **M0** | Bootstrap scaffold (this PR) | Now | None — no existing paths touched | Delete the new dirs |
| **M1** | Add design-tokens package, consume it from existing `frontend/src/index.css` via published CSS vars | Phase 0 | Low — additive | Revert the CSS var consumption |
| **M2** | Add `packages/ui` primitives, consume from existing `frontend/` for new components only | Phase 0 / 1 | Low — opt-in usage | Don't import them |
| **M3** | Build new CI surfaces in `apps/ci/` consuming `packages/ui` directly | Phase 1 | Low — separate app | Disable Mission Control routing to /ci |
| **M4** | Build Mission Control in `apps/landing/`; deploy as the new root domain target | Phase 1 mid | Medium — DNS + auth | Revert root route to existing `frontend/` |
| **M5** | Move existing `frontend/` to `apps/research/`; update Railway build path | Phase 1.5 | Medium — touches deploy | Restore old path |
| **M6** | Factor backend: `api/` + `services/` split into `services/platform/` + `services/module_ci/` + `services/module_research/`. Move `connectors/`, `integration/`, `domain/` into `packages-py/` | Phase 1.5 / 2 | High — many imports | Per-package rollback; gate with feature flag if needed |
| **M7** | Re-root `schema/` migrations into `schema/platform/` + `schema/modules/` | Phase 2 | Medium — migration runner change | Restore old paths; migrations themselves are unchanged content |
| **M8** | Delete old paths once nothing references them; update CLAUDE.md and harness docs | Phase 2 end | Low — cleanup | n/a |

## Why not `git mv` everything in one PR

Three reasons:

1. **Production safety.** The Railway nixpacks path, the Python import graph, the test fixtures, and the migration runner all assume the current paths. Coordinated change of all of them is high-risk and can't be staged for review.
2. **Reviewability.** A 250-file rename PR is unreviewable. Incremental migration produces 8 reviewable PRs.
3. **Reversibility.** Each step is independently revertable. A monolithic rename is not.

## Why not stay flat

Three reasons:

1. **Multi-app future.** SPEC-016 commits to a platform with multiple module apps. Sharing `packages/ui` and `packages/design-tokens` across apps requires a workspace.
2. **Build orchestration.** Two apps + three packages + Storybook needs a build orchestrator (Turbo or Nx). Both expect a workspace.
3. **Dependency hygiene.** Each app declares its own dependencies; shared deps live in workspace root. Today, `frontend/` carries the only `package.json` and there is no place for shared design tokens.

## Tooling choices

- **Workspace manager:** `pnpm` workspaces (already installed: 10.12.4). Good monorepo support, fast, content-addressed store.
- **Build orchestrator:** `turbo` for caching + parallel build/test/lint across packages. Free for our scale.
- **Node:** `22.15.0` via `.nvmrc` so contributors get the same version.
- **Python:** unchanged for now. Phase 1.5 introduces `uv` workspaces or `hatch` workspaces for `packages-py/`.

## Acceptance for M0 (this PR)

- `pnpm install` at the repo root succeeds; no errors.
- `cd frontend && npm ci && npm run build` (existing path) still succeeds.
- `cd apps/landing && pnpm dev` runs the Mission Control skeleton.
- `cd apps/ci && pnpm dev` runs the CI module skeleton.
- `cd packages/ui && pnpm storybook` runs Storybook with the first 5 primitives.
- All existing pytest tests pass unchanged (`python -m pytest tests/ -v`).
- Railway deploy unchanged.

## Open follow-ups (not blocking M0)

- M5 will require the Railway build command to switch from `cd frontend && npm ci && npm run build` to `pnpm install && pnpm --filter research build` (or similar). Schedule the deploy-config change with M5.
- The old `frontend/` will live in the repo for several weeks under the new layout's shadow. Make this explicit in CONTRIBUTING.md so contributors know which is live.

---

*Authored: 2026-04-27. Linked to SPEC-016. Successor ADRs (M1–M8) will document each migration step as it ships.*
