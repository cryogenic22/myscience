# Market Zero repository handoff-readiness review

**Review date:** 2026-08-13  
**Reviewer posture:** independent architecture, backend, frontend, security, data-integrity, operations, and delivery-governance review  
**Decision baseline:** clean detached worktree at `origin/main` commit `31d923a712bdcd7611b885f438c858747960b0c2`  
**Execution plan:** `specs/SPEC_HANDOFF_001_repository_maturity_and_transfer.md`

## Executive decision

**Market Zero is not ready for an unqualified dev-team handoff today.** It is a substantial late-prototype / early-product codebase with good architectural instincts and unusually strong test depth, but its canonical branch, security boundary, operational state, API contract, and delivery hygiene do not yet tell one coherent and safe story.

The correct disposition is **conditional handoff after a bounded hardening program**, not a rewrite. The strongest parts should be preserved: connector abstractions, evidence and fact ledgers, conservation gates, schema migration discipline, a broad product surface, and extensive backend/frontend tests. The immediate work is to make those strengths enforceable on the branch the receiving team will actually inherit.

The principal blockers are:

1. Critical security fixes exist in green PRs but are not on `main`; mutation-route authorization remains incomplete.
2. `main` still exposes development/control-plane behaviors that are unsafe as production defaults, while the frontend automatically acquires an enterprise demo token.
3. The live operational-health gate is correctly red: four scheduled sources were red on 2026-08-13, 22 ETL runs were stuck for more than 12 hours, and the DLQ had 1,547 pending rows.
4. The saved OpenAPI contract is materially behind the application (`381` saved paths versus `518` generated paths at the audited SHA).
5. Frontend tests, type checking, and production build pass, but lint has 306 errors, including actual Rules-of-Hooks violations.
6. The full backend suite collects 4,514 tests but did not complete inside a 15-minute audit window, and CI runs only a curated smoke subset.
7. GitHub/repository coordination is heavily overgrown: 41 open PRs, 79 registered worktrees at audit time, no open PR with a review decision, and no required approval count in branch protection.
8. Some visible UI states claim persistence or authentication behavior more strongly than the implementation supports.
9. The August data-platform program is directionally strong but is already drifting from code in at least one material detail; it must be delta-audited before implementation.

This is a **NO-GO for external production claims or a context-free transfer**. It is a **GO for an assisted handoff** once the P0 exit criteria in the linked spec are satisfied and the remaining P1 work is explicitly accepted by the receiving lead.

## Maturity scorecard

| Area | Status | Independent assessment |
|---|---|---|
| Product/domain architecture | AMBER-GREEN | Rich domain model, evidence-oriented design, and credible vertical depth. Several large modules blur boundaries. |
| Backend implementation | AMBER | Broad capabilities and strong tests; router composition, exception policy, transactionality, and runtime controls need hardening. |
| Frontend implementation | AMBER | Large, tested product surface and passing build/typecheck; lint debt, oversized components, scattered auth/fetch behavior, and misleading states remain. |
| Security and privacy | RED | Two important fixes are unmerged; route authorization/ownership is incomplete; unsafe demo/control-plane defaults remain on `main`. |
| Data platform | AMBER-RED | Strong ingestion substrate and conservation culture; raw replay, atomic records, deterministic identity, and truthful controls are not complete. |
| Automated assurance | AMBER | Excellent test quantity and conservation doctrine; full enforcement, frontend lint/build/test CI, and backend completion time are missing. |
| Operations and recovery | RED | Nightly health is actively red; stuck-run recovery, DLQ ownership, leases, and deployment/runbook truth need closure. |
| API contract | RED | Repository snapshot is materially stale and the TypeScript client is largely hand-maintained. |
| Repository/delivery hygiene | RED | PR, branch, worktree, report, and planning-document sprawl makes ownership and the canonical state ambiguous. |
| Documentation/governance | AMBER | Serious documentation exists, but counts, lane descriptions, paths, spec IDs, and status claims have drifted. |

## What is already worth preserving

This review is not a recommendation to replace the system. The following are real assets:

- The repository contains a serious pharmaceutical intelligence model rather than a thin demo around an LLM.
- Connector, integration, knowledge-store, resolver, evidence, fact, benchmark, and quality seams exist and are independently testable.
- Conservation and no-vacuous-green principles are better than those in many production codebases.
- The clean baseline collected **4,514 backend tests** and the frontend executed **1,110 test cases** (`1,088 passed`, `22 todo`) across **121 files**.
- The audited backend smoke set passed **489 tests with 27 skipped**; the conservation set passed **100 with 23 skipped**.
- Frontend TypeScript checking and production build both pass.
- Migrations are additive in style and current tracked migration numbers were unique during the audit.
- OpenAPI, changelogs, cross-lane specs, operational health, live evaluation, benchmark, and schema-drift concepts all exist. The problem is enforcement and reconciliation, not lack of intent.
- The data-platform diagnosis correctly favors evolving the current system, raw capture, deterministic identity, and truthful outcomes over introducing Kafka/Spark or adding connector breadth indiscriminately.

## Review baseline and method

### Canonical code baseline

The active local checkout was not suitable as the review baseline:

- branch: `claude/chore/ctxpack-session-memory-hooks`
- HEAD: `38889b54354f457de1d7f37a371c61507ffa5ebe`
- relation to `origin/main`: one unique local commit and 37 commits behind
- three tracked modifications plus dozens of untracked entries

All code and validation claims in this report therefore use a clean detached worktree at the fetched `origin/main` SHA above. Local planning documents created in August were reviewed separately and are identified as local/unmerged where relevant.

### Surfaces reviewed

- Repository governance: `docs/COORDINATION.md`, `CLAUDE.md`, `AGENTS.md`, changelogs, boards, specs, worktrees, PR state, and branch protection.
- Backend: app composition, routes, auth, database/transaction behavior, integrations, connectors, scheduler, migrations, exceptions, dependency policy, and tests.
- Frontend: composition, API/auth access, UX truthfulness, hooks, build/type/lint/test posture, bundle shape, design-token discipline, and module size.
- Data platform: the 2026-08-07 deep-design review, `SPEC_003_data_platform_hardening.md`, and WP-0/WP-1/WP-4.
- Operations: current GitHub Actions status and the latest live operational-health evidence.

No production write, migration, deployment, branch deletion, PR merge, or worktree cleanup was performed.

## P0 blockers

### H-01 - The security truth is stranded outside `main`

`origin/main` still contains the vulnerable forms, while two remediation PRs are open:

- **PR #325**, `SEC-001a - fail-close the /debug/* + /zs control-plane surface`: open, non-draft, merge state CLEAN, five required checks green, no review decision.
- **PR #326**, `PRIV-001 - redact PII on the direct synthesis path`: open, non-draft, merge state CLEAN, five required checks green, no review decision.

The team-reported post-nit affected suite for #325 is useful evidence, but it is not evidence about `main`. The independent GitHub check here establishes only that the PR checks are green and the branches are mergeable; it does not substitute for a current independent code review and post-rebase test run.

The local branch `claude/platform/sec-001b-route-auth` contains only the first of three planned loops, covering enrichment mutations. It has no corresponding open PR in the audited list. A static route-policy inventory produced 100 unguarded mutation candidates when aliases were included. That number is not equivalent to 100 exploitable vulnerabilities: it includes `/api/v1` aliases and read-like POST endpoints such as search/query operations. It did, however, confirm genuinely unguarded mutation families in catalog/steward, metrics, enrichment, feedback, intelligence, chat/research-session, and debug/control-plane surfaces.

**Required outcome:** rebase, independently review, and land #325/#326; finish a route-by-route auth/ownership matrix; enforce it with a non-vacuous test that fails for a new unclassified mutation route.

### H-02 - Production defaults and frontend authentication are unsafe together

On the audited baseline:

- `api/app.py:427`, `:445`, and `:479` define `/debug/migrate`, `/debug/seed-users`, and `/debug/routes` without an auth dependency.
- Debug exception responses expose traceback details.
- `api/routes/zs.py:61-71` retains fallback credentials `zs` / `zs-future` when environment configuration is absent.
- `frontend/src/pages/CIPage.tsx:144` invokes `useDemoAutoLogin()` unconditionally.
- `frontend/src/hooks/useDemoAutoLogin.ts:29-30` hardcodes `enterprise@demo.market-zero.io` / `demo`, logs in through the real auth endpoint, and stores the returned enterprise JWT in local storage.
- The seed behavior and frontend behavior together can turn a convenience path into automatic enterprise access.
- `services/auth.py` creates a random process-local JWT secret when no configured secret exists. That is tolerable for an isolated developer process but must be rejected by a production startup policy.

**Required outcome:** production has no development route or credential fallback; demo autologin is absent from production bundles and default-off everywhere; required production secrets are validated before readiness; errors never return raw tracebacks.

### H-03 - Authorization is not yet an ownership or tenancy model

Role checks alone do not establish resource ownership. A receiving team could incorrectly infer multi-user or multi-tenant safety from the presence of JWT roles. User-created workspaces, briefs, research sessions, feedback, war rooms, and similar resources need one of two explicit contracts:

1. enforced owner/tenant scoping in data access and mutations, or
2. a guarded, documented single-tenant deployment mode that makes multi-tenant use impossible to enable accidentally.

**Required outcome:** an explicit deployment-mode decision, owner/tenant fields and checks for sensitive resources, negative cross-user tests, and no marketing/architecture claim beyond the enforced mode.

### H-04 - The live system is reporting real operational degradation

The latest `Operational Health (Lane 2 - live)` run on 2026-08-13 failed for a substantive reason, not a CI setup problem:

- 9 GREEN, 1 AMBER, 4 RED among 14 scheduled sources.
- RED: `clinical_trials_gov`, `openfda_labels`, `openfda_faers`, `mesh_ontology`.
- 1 stuck clinical-trials run and 21 stuck MeSH runs older than 12 hours.
- OpenFDA label and FAERS data were approximately 41 and 69 days old respectively, even though their last run was classified as a legitimate no-change cycle.
- DLQ: 1,547 pending, with 10 new in seven days.
- Some DLQ causes contain a Python bound-method representation for ChEMBL rather than the intended stable source identifier.
- The action correctly updated tracking issue #207 and exited non-zero.

This is exactly the kind of signal a mature handoff must not relabel or suppress.

**Required outcome:** diagnose and repair or explicitly decommission each red source; reconcile stuck runs; correct source identifiers in DLQ rows; assign DLQ ownership/SLA; demonstrate a stable green observation window without weakening thresholds.

### H-05 - OpenAPI is not the current contract

At the audited SHA:

- `schema/openapi.json`: 381 paths.
- freshly generated FastAPI schema: 518 paths.
- 137 generated paths were absent from the snapshot; no snapshot-only stale paths were observed.

Some generated paths are duplicate legacy `/api/v1` aliases or SPA/static routes and should not necessarily remain public API. That makes the mismatch more concerning, not less: the repository has not made a deliberate contract decision.

`frontend/src/api.ts` is 3,031 lines and mixes shared helpers, endpoint-specific types, direct fetches, ad hoc auth, and error handling. Additional direct fetches occur outside it, including `/steward/refresh` calls whose errors are swallowed.

**Required outcome:** define which routes are API contract, exclude non-API routes from schema, deliberately handle aliases/deprecations, regenerate the snapshot, and add a hard generation-diff gate. Generate or validate frontend types from the snapshot and route mutations through one authenticated client.

### H-06 - Some visible UI states overstate what happened

`frontend/src/hooks/useBriefAutosave.ts` documents an intended POST but `persistDraft()` only logs `would POST`; the hook nevertheless begins at `saved` and transitions back to `saved`. This is a false-success state and a potential silent-loss mechanism.

The direct steward-refresh calls in `DataCatalogPanel.tsx` and `NewWorkspace.tsx` do not use the shared auth/error path and swallow failures. Preview-only flows such as connector onboarding must remain explicitly labelled as previews until persistence and backend contracts are real.

**Required outcome:** either implement real persisted autosave with failure/retry/conflict semantics, or rename the state to an honest local draft and never show `Saved`. Centralize mutation requests and surface failures.

## Backend review

### Application composition fails open

`api/app.py` imports nearly every route module inside its own broad `try/except` and starts without a failed router. That keeps optional features from crashing local development, but it can also deploy an application silently missing required APIs. The app then registers most routers twice, at legacy and `/api/v1` paths.

Replace this with a typed router manifest:

- required router import/registration failure: startup/readiness failure;
- optional plugin failure: structured degraded state exposed by readiness and telemetry;
- one declared canonical prefix and an explicit deprecation map for aliases;
- a test comparing the manifest, registered routes, and OpenAPI.

### Error handling is too permissive to audit manually

A broad scan found 797 `except Exception` sites across backend runtime surfaces and 116 lines matching empty `pass`/`continue` patterns near exception handlers. `api/routes/catalog.py` alone contained 27 such candidates. These are audit candidates, not 797 confirmed defects: cleanup, telemetry, optional enrichment, and best-effort integrations legitimately need different failure semantics.

The problem is that the policy is implicit. Every catch should be classified as one of:

- advisory and observable;
- retryable with bounded retry/backoff;
- record failure with DLQ/quarantine/conservation accounting;
- required and fail-closed;
- process-fatal/startup-fatal.

The known fail-open ingestion path in `integration/pipeline_hooks.py:116-118` converts any hook exception to `continue`. `integration/pipeline.py:422` consumes POST_STORE output without enforcing a block, and `:454` contains an empty catch. These are correctly targeted by data-platform WP-0.

### Transaction and runtime boundaries are incomplete

`db.py` defaults connections to autocommit while exposing a transaction helper. The central record pipeline does not wrap store/link/quality/HITL operations in that helper, so a mid-record failure can leave partial state. WP-1 correctly addresses this.

Migrations run at app startup by default, and migration failures are logged while startup continues. Process-local scheduled jobs do not establish a distributed lease. These defaults are risky when a receiving team scales the service beyond one instance.

Required maturation:

- release-phase migration job that fails closed;
- app runtime starts only after schema compatibility is verified;
- distinct `/healthz` liveness and `/readyz` dependency/schema/router readiness;
- one scheduler leader enforced by lease, or scheduler split to a dedicated worker;
- stuck-run reconciliation and idempotent retry semantics.

### Module boundaries have become expensive

Representative line counts at the baseline:

- `api/routes/catalog.py`: 3,164
- `services/unified_handler.py`: 1,800
- `services/chat_handlers/handlers.py`: 1,780
- `integration/knowledge_store.py`: 1,717
- `services/llm.py`: 1,644
- `services/dossier_kb.py`: 1,210
- `integration/entity_resolver.py`: 1,153
- `api/routes/war_room.py`: 1,117

Line count alone is not a defect, but these modules combine policy, IO, serialization, persistence, and orchestration. Split only behind characterization tests and stable public interfaces. Do not conduct a repository-wide rewrite.

### Static quality and dependency controls are not reproducible

A default `ruff check` over core backend directories reported zero findings, but the repository has no committed Ruff/mypy/Bandit policy. A raw Bandit run reported 9 high, 179 medium, and 71 low heuristic findings. The nine high findings were weak-hash uses that appear primarily intended for deterministic identifiers; they require review, not automatic replacement. The 173 dynamic-SQL warnings similarly need identifier-validation review and documented suppressions. Fifty B110 findings reinforce the exception-policy concern.

Python dependencies are broad lower bounds rather than a reproducible application lock. A global-environment `pip check` was deliberately excluded from the verdict because it was not a clean project environment.

Required maturation:

- committed lint/type/security configuration with a reviewed baseline;
- no global disable to create a vacuous green;
- locked/hashed deploy and test inputs;
- a fresh-venv install, `pip check`, smoke, and full-suite workflow.

## Frontend review

### What passed

- `npm run typecheck`: pass.
- full Vitest run: 121 files passed; 1,088 cases passed; 22 todo.
- production Vite build: pass, 2,986 modules transformed.
- no `dangerouslySetInnerHTML` usage was found in `frontend/src`.

This is a meaningful base. The frontend is not untested or a disposable mock.

### Lint is a real quality gate failure

Full frontend lint reported **306 errors and 4 warnings across 87 files**. A source-only view still contained **86 errors and 4 warnings across 52 source files**. Dominant categories included:

- 241 `no-explicit-any` overall;
- 24 `react-hooks/set-state-in-effect`;
- 21 unused values;
- 11 `react-refresh/only-export-components`;
- 3 Rules-of-Hooks errors.

`frontend/src/components/EntityProfileCard.tsx:351-356` calls state/effect hooks after early returns. That is a runtime-correctness problem, not cosmetic lint. Fix Rules of Hooks first, then ratchet the remaining categories without weakening configuration or adding blanket disables.

### Client/auth architecture is fragmented

Authentication state is read directly from local storage across numerous components and hooks. `api.ts` has generic `get`/`post` helpers, but auth and the standard error envelope are not uniformly enforced there. Several callers construct fetch requests themselves.

Create an API transport/auth boundary that owns:

- base URL and canonical prefix;
- bearer/session handling;
- 401/403/429 policy;
- standard error-envelope parsing;
- cancellation/timeouts and request IDs;
- typed request/response contracts;
- mutation retries only where idempotency makes them safe.

Longer-term, move JWTs to secure httpOnly cookies if the deployment architecture supports it. That is not a substitute for removing demo autologin now.

### Bundle and component boundaries need a controlled split

The production entry chunk was approximately **1,924 kB minified / 535 kB gzip**, generating Rollup's over-500-kB warning. No route-level `React.lazy`/dynamic import seam was found.

Large frontend units include:

- `frontend/src/api.ts`: 3,031 lines
- `DataCatalogPanel.tsx`: 1,475
- `GraphExplorer.tsx`: 1,278

Introduce route/surface lazy loading and split units by stable product boundaries. Begin with a measured bundle ratchet rather than an arbitrary one-shot target.

### Design-system compliance is not mechanically enforced

A source scan found 382 hexadecimal color occurrences. Some belong to SVGs, charts, semantic palettes, or fixtures, so this is an inventory rather than 382 violations. The frontend mandate requires design tokens. Add an allowlisted test/lint rule that permits intentional data-visualization palettes and rejects new unapproved hardcoded UI colors.

## Automated assurance and CI review

### Independent clean-baseline results

| Check | Result | Interpretation |
|---|---|---|
| Backend test collection | 4,514 collected; one unknown `integration` marker warning | Deep suite, missing committed pytest marker policy. |
| Backend curated smoke | 489 passed, 27 skipped in 40.30s | Healthy selected baseline. |
| Conservation suite | 100 passed, 23 skipped in 4.97s | Strong deterministic integrity floor. |
| Full backend suite | did not finish within 904 seconds | Completion unverified; this is a timeout, not a test failure. |
| Frontend typecheck | pass in 19.4s | Good. |
| Frontend tests | 121 files passed; 1,088 passed, 22 todo in 114.22s | Good breadth; todos need owners/expiry. |
| Frontend build | pass in 40.65s | Good; bundle warning remains. |
| Frontend lint | 306 errors, 4 warnings | Failing baseline; includes correctness issues. |
| Default Ruff scan | zero findings | Encouraging but non-authoritative without committed policy. |

Some initial Windows test attempts failed because the audit sandbox could not write temporary/report files. Those were execution-environment artifacts and are not counted as product failures; the relevant suites were rerun with a writable temp location.

### CI enforcement gaps

Current PR checks enforce:

- backend collection plus a curated smoke manifest;
- conservation tests;
- schema-drift static tests;
- benchmark;
- frontend non-vacuous typecheck plus one harness test.

They do **not** enforce:

- full backend execution;
- full frontend Vitest;
- frontend lint;
- frontend production build;
- OpenAPI generation equality;
- committed Python lint/type/security policy.

The correct solution is a ratcheted gate rollout: characterize, fix the correctness blockers, establish a reviewed baseline, then make each gate required in the same PR that makes it reliably green.

## GitHub and repository hygiene review

### Pull requests and branch protection

As of 2026-08-13:

- 41 open PRs.
- 40 had not been updated within 30 days.
- all 41 had an empty review decision.
- 22 reported merge state CLEAN.
- branch protection required five status checks but `strict` was false.
- administrators were covered and force pushes/deletions were disabled.
- no required approving-review count or CODEOWNER-review requirement was returned.

This allows a technically green but unreviewed, non-up-to-date branch to remain the apparent delivery unit. For a team handoff, every open PR needs an owner and disposition: merge, supersede, split, preserve as evidence, or close.

### Worktrees and local state

The registry contained 79 worktrees at audit time:

- 51 inside `.claude/worktrees` under the repository;
- 25 sibling worktrees under `Documents`;
- 2 under `C:\tmp`, one of which was the isolated audit worktree created for this review.

Thus 78 pre-existed the audit. Numeric reduction alone is not the goal. The goal is **zero unclassified worktrees and zero unpreserved dirty work**. Each must be tied to an active task/PR, preserved as a patch/bundle, or proven clean and merged before removal.

The active root checkout also has user/team modifications and many untracked documents and artifacts. They must be inventoried and hashed before any cleanup transaction. Existing environmental files, databases, backups, prototypes, session memory, and evidence bundles are protected unless explicitly dispositioned.

### Documentation and generated artifacts

The tracked repository contains hundreds of reports and benchmark artifacts. At audit time, 230 tracked generated/report artifacts occupied about 4.37 MB, including 216 benchmark reports. Size is not yet a Git performance emergency, but the absence of a retention/index policy makes authoritative evidence difficult to find.

`CLAUDE.md` and some rule files contain stale counts and paths. Spec numbering is already non-unique (`SPEC_003`, `SPEC_004`, and others have multiple meanings), so this review uses the namespaced ID `SPEC_HANDOFF_001` rather than creating another misleading sequential number.

## Alignment with the data-platform program

The architectural direction in `SPEC_003_data_platform_hardening.md` is aligned with this review:

1. WP-0 truthful outcomes and controls.
2. WP-1 immutable raw capture, replay, and per-record atomicity.
3. WP-4 deterministic identity spine after the integrity substrate.
4. WP-12 assurance applied throughout.

However, **"fully specced and code-verified" is no longer an accurate execution guarantee**. At least one WP-0 current-state statement has drifted:

- WP-0 says `records_skipped` and `records_failed` are not persisted and proposes adding both.
- audited `origin/main` already contains migration `098_etl_runs_skip_visibility.sql` and `_finalize_etl_run()` writes both fields.

The remaining WP-0 gaps are still real: fail-open hook severity, POST_STORE blocking, quarantine/raw preservation, broader disposition counters, conservation classification, dead `method` versus `matched_via` logic, and scheduler outcome propagation. The correction is to delta-update the spec and migration design, not discard the WP.

Every data-platform WP must therefore begin with:

- chosen baseline SHA;
- current code/migration evidence;
- already-landed capability list;
- stale/removed instruction list;
- revised RED tests and migration number reserved at implementation time.

Do not begin WP-0/WP-1/WP-4 until the repository/security handoff floor is green and the owner explicitly selects the next WP, consistent with the program's ratified rule.

## Recommended delivery sequence

| Sequence | Outcome | Why first |
|---:|---|---|
| 0 | Preserve and select the canonical baseline | Prevents cleanup or rebasing from losing untracked/dirty work. |
| 1 | Land security/privacy fixes and finish route policy | A receiving team must not inherit known exploitable defaults. |
| 2 | Restore live operational health | The handoff branch must correspond to a system that is not actively degraded. |
| 3 | Make UI persistence/auth states truthful | Prevents silent user loss and demo credentials from masking backend reality. |
| 4 | Reconcile OpenAPI and client contract | Establishes the backend/frontend boundary the team will use. |
| 5 | Establish full, reproducible quality gates and review protection | Converts local evidence into enforceable delivery policy. |
| 6 | Reduce repository/PR/worktree ambiguity and publish handoff runbooks | Creates an operable transfer package. |
| 7 | Modularize high-change hotspots and runtime boundaries | P1 maintainability work after the safety floor. |
| 8 | Delta-update and execute SPEC-003 WP-0, then WP-1, then WP-4 | Evolves the data platform on a trustworthy base. |

## Definition of handoff-ready

The repository is ready for the receiving lead to accept when all of the following are evidenced:

- one documented canonical branch/SHA; clean reproducible clone instructions;
- every local modification, untracked artifact, PR, branch, and worktree classified with no silent deletion;
- #325 and #326 independently reviewed/rebased/merged or replaced by equivalent verified changes;
- all mutating routes classified and protected; owner/tenant mode explicit and tested;
- no production demo autologin, weak credential fallback, unauthenticated debug mutation, or raw traceback response;
- operational-health gate green for the agreed observation window, or each accepted exception has owner, expiry, and an honest degraded status;
- no stuck run beyond SLA and DLQ has owner, cause taxonomy, and replay/disposition plan;
- OpenAPI snapshot equals deliberately generated API schema; frontend types/client validation agree;
- no UI reports server persistence without an acknowledged server response;
- frontend Rules-of-Hooks errors are zero; lint, typecheck, full tests, and build are green in CI;
- backend full suite completes in sharded CI; marker/config warnings are resolved;
- required branch checks are strict/up-to-date and at least one independent approval is required;
- deployment, migration, rollback, restore, secret, scheduler, and incident runbooks exist and have been exercised proportionately;
- receiving lead signs a known-debt register that separates P0 accepted exceptions from P1/P2 roadmap work.

## Final architectural position

Market Zero has enough real substance to hand to a serious engineering team, but only after its **delivery truth catches up with its design truth**. The repository already knows many of the right ideas: provenance, conservation, evidence, contracts, staged rollouts, and independent review. The present gap is that these ideas are unevenly wired into `main`, CI, runtime behavior, and the visible frontend.

Complete `SPEC_HANDOFF_001` as the transfer floor. Then execute the existing data-platform program in its intended sequence, after a fresh code delta. That route preserves the team's work, removes the current safety ambiguity, and gives the incoming developers an honest platform rather than an impressive but internally contradictory snapshot.

## Review limitations and honesty notes

- A 15-minute full-backend timeout establishes only that completion was not verified in the audit window; it does not establish failing tests.
- Static route and exception counts are triage inventories. Each item needs semantic classification before being called a vulnerability or defect.
- Bandit severity is heuristic. Weak hashes used for stable non-security IDs and validated dynamic identifiers may be acceptable with explicit rationale.
- No penetration test, browser E2E run, accessibility/Lighthouse run, load test, backup restore, migration against production, or production mutation was performed.
- Live operational facts are point-in-time observations from the 2026-08-13 GitHub Actions run and may change; the handoff evidence pack must refresh them at execution time.
