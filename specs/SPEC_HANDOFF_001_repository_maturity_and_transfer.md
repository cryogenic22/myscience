# SPEC_HANDOFF_001 - Repository Maturity and Dev-Team Transfer

**Status:** execution-ready draft for owner and receiving-lead ratification  
**Priority:** P0 transfer floor, followed by explicitly accepted P1 debt  
**Requested by:** Market Zero owner  
**Primary executor:** Claude/backend lead, coordinating with the frontend lead on `frontend/**`  
**Independent review:** mandatory for every security, contract, migration, branch-protection, and cleanup PR  
**Grounding review:** `design-review-output/market_zero_handoff_readiness_review_2026_08_13.md`  
**Code baseline used by review:** `origin/main@31d923a712bdcd7611b885f438c858747960b0c2`

## 1. Goal

Transfer Market Zero to a development team as a coherent, reproducible, secure, operable repository with:

- one unambiguous canonical baseline;
- no unpreserved local work;
- production-safe authentication/control-plane behavior;
- a complete mutation authorization and ownership policy;
- a truthful frontend and runtime;
- a generated backend/frontend API contract;
- full, non-vacuous CI evidence;
- green or explicitly accepted operational health;
- a compact handoff/runbook package;
- an owner-approved known-debt register for work that remains after transfer.

This program **evolves the current system**. It does not replace the architecture or interrupt the existing data-platform program. It creates the integrity floor on which `SPEC_003_data_platform_hardening.md` can safely execute.

## 2. Transfer decision

The transfer has two decisions:

1. **P0 clean handoff:** all P0 gates in this spec are mandatory. Until then, the repository may be shared only as an assisted work-in-progress with the red findings disclosed.
2. **P1 accepted handoff:** P1 tasks may remain if the receiving engineering lead signs the known-debt register with owner, due date, risk, and interim control.

No item can be changed from P0 to P1 merely because it is difficult or old. A downgrade requires an owner decision recorded in the spec/board with the residual risk.

## 3. Non-goals

- No wholesale backend or frontend rewrite.
- No Kafka, Spark, lakehouse, or microservice decomposition without measured need and an ADR.
- No net-new connector breadth before the data-integrity floor, except a connector change needed to repair a red production source or emit deterministic identifiers.
- No cosmetic redesign unrelated to truthful states, accessibility, or the changed handoff surface.
- No silent deletion of reports, worktrees, branches, databases, backups, prototypes, session memory, benchmark evidence, or untracked files.
- No weakening tests, thresholds, schemas, protected surfaces, lint rules, or operational classifications to create green output.
- No implementation of WP-0/WP-1/WP-4 until their current-state claims are reverified and the owner selects the WP.

## 4. Required execution protocol

### 4.1 Session handshake

Before every implementation session, Claude must:

1. Read `docs/COORDINATION.md`, then `CLAUDE.md`, then `AGENTS.md`.
2. Read the other lane's changelog for the last two weeks.
3. Read relevant items in `docs/AGENT_BACKLOG.md` and `docs/PRODUCT_BACKLOG.md`.
4. Fetch/prune remotes and record the current `origin/main` SHA.
5. Inspect `git status --short --untracked-files=all`, all worktrees, and the target branch before writing.
6. Read this spec and the finding being implemented from the grounding review.
7. Verify every cited current-state claim against the selected SHA. Record drift before changing code.

### 4.2 Change shape

- One bounded work package or coherent sub-loop per PR.
- Characterization/RED test first for behavior changes.
- Additive and reversible migrations; reserve the next migration number at implementation time.
- API change: regenerate `schema/openapi.json` and append `docs/API_CHANGELOG.md`.
- Frontend change: append `docs/UI_CHANGELOG.md`; frontend lead owns the implementation/review unless the emergency protocol applies.
- Shared spec/governance change: both lane leads sign off.
- Every PR body states `Other-side impact: none` or links the exact contract/changelog task.
- Run the final affected suite **after the last nit**. Pre-nit results must be labelled as such and cannot ground the final claim.
- Claude must not self-approve or self-merge a PR requiring independent review.

### 4.3 Evidence format

Each task closes with an evidence block committed to the PR description or `docs/handoff/evidence/<task-id>.md`:

```text
Task:
Baseline SHA:
Final diff SHA:
RED command and relevant failure:
GREEN command and exact summary:
Regression command and exact summary:
Migration forward/back verification (if applicable):
OpenAPI/frontend impact:
Operational read-only probe (if applicable):
Known exceptions with owner/expiry:
Independent reviewer and decision:
```

No completion claim may depend only on an earlier chat message or an unlinked log.

## 5. Program sequence

```text
H0 preserve/select baseline
        |
        v
H1 security/privacy/ownership -----> H4 truthful frontend
        |                                  |
        v                                  v
H2 operational recovery ----------> H3 API contract
        \                                  /
         v                                v
          H5 full assurance + protection
                         |
                         v
           H7 handoff package + acceptance
                         |
              receiving-lead sign-off
                         |
                         v
          H6 P1 maintainability/runtime
                         |
                         v
       SPEC-003 delta audit -> WP-0 -> WP-1 -> WP-4
```

H0 must precede any cleanup. H1 security changes may run in parallel only when they do not touch the same files. H2 requires deployment authority and must preserve historical run truth. H3/H4 must coordinate through OpenAPI and changelogs. H5 becomes required only in the same PR that establishes a reliable green baseline.

## 6. Work-package register

| ID | Priority | Work package | Transfer gate |
|---|---|---|---|
| H0 | P0 | Preserve work and select canonical baseline | No unclassified or unpreserved local state |
| H1 | P0 | Security, privacy, mutation policy, ownership | No unsafe default/control-plane/auth path |
| H2 | P0 | Operational-health and recovery closure | Stable healthy or explicitly accepted degraded system |
| H3 | P0 | OpenAPI and backend/frontend contract truth | Generated contract equals repository/client contract |
| H4 | P0 | Frontend truthfulness and correctness | No false persistence/auth success; Rules of Hooks clean |
| H5 | P0 | Reproducible assurance and delivery protection | Full required gates and independent approval |
| H6 | P1 | Backend/frontend maintainability and runtime boundaries | Accepted debt if not complete at transfer |
| H7 | P0 | Documentation, repository hygiene, and handoff exercise | Receiving team can operate a fresh clone |
| H8 | Post-transfer program | Delta-update and execute data-platform WPs | Owner selects after P0 transfer floor |

## 7. H0 - Preserve work and select the canonical baseline

### H0.1 Create a non-destructive repository inventory

**Output:**

- `docs/handoff/REPOSITORY_INVENTORY.md`
- `docs/handoff/WORKTREE_DISPOSITION.csv`
- `docs/handoff/PR_DISPOSITION.md`
- `docs/handoff/UNTRACKED_ARTIFACT_MANIFEST.csv`

**Steps:**

1. Record remotes, `origin/main` SHA/date, local branch SHAs, ahead/behind counts, tags, and the current deployment SHA.
2. Enumerate every registered worktree. Required fields: absolute path, branch/detached SHA, porcelain status, last commit date, open PR, owner, purpose, disposition, and preservation artifact.
3. Enumerate all open PRs. Assign one disposition: `merge-candidate`, `needs-rebase`, `superseded`, `split`, `evidence-only`, or `close-after-preserve`.
4. Enumerate tracked modifications and every untracked file with path, size, SHA-256, likely class, and disposition. Do not print secret contents.
5. Protect by default: `.env*`, databases, backups, session memory, `.claude/ctx`, raw benchmark/SME evidence, prototypes, and any dirty worktree.
6. For a dirty branch/worktree that may be retired, create and hash both a patch and, where commits are not on a remote, a Git bundle. Verify the patch/bundle can be inspected before cleanup is proposed.
7. Select the canonical integration baseline. The default is a new clean worktree from current `origin/main`; deviations require an ADR explaining why.
8. Commit the inventory separately. Do not combine inventory and deletion/move operations.

**Validation:**

```powershell
git fetch --all --prune
git status --short --untracked-files=all
git worktree list --porcelain
git branch -vv
gh pr list --state open --limit 100
```

**Exit:** every local/remote delivery object is classified; every dirty object has a preservation path; the chosen baseline SHA is documented.

### H0.2 Execute the approved cleanup transaction

This step begins only after owner review of H0.1.

1. Recheck SHA/status against the manifest immediately before each move/removal.
2. Move approved stale reports with history-preserving Git moves into `docs/archive/reports/`; add an archive index with original path, date, reason, and replacement.
3. The prior audit identified these high-confidence archive candidates, subject to unchanged-hash verification:
   - `DELIVERY_DASHBOARD.html`
   - `backlog-triage.html`
   - `data-layer-status-20260627.html`
   - `harness-gate-coverage.html`
   - `overnight-run-summary.html`
   - `overnight-run-2-summary.html`
   - `sense-data-side-review.html`
   - `state-of-strategy-actuals-20260627.html`
   - `v7-merge-review.html`
4. Close/supersede PRs only after recording the reason and successor. Do not infer that an old PR has no unique commits.
5. Remove a worktree only when it is clean, its branch is merged/superseded, and its manifest row names the preservation evidence. Use native `git worktree remove`, not recursive filesystem deletion.
6. Prune registrations only after the physical/branch state is verified.
7. Add ignore/retention rules for generated outputs, but never use a new ignore rule to conceal an already-unreviewed artifact.

**Exit:** zero unclassified worktrees/PRs/artifacts; only task-owned worktrees remain; canonical worktree is clean; archive index resolves every move.

### H0.3 Reconcile planning truth

1. Make `docs/COORDINATION.md` the canonical lane/active-task board.
2. Update `CLAUDE.md` and `.claude/rules/*` where connector counts, migration ranges, test paths, or commands are stale.
3. Retain `AGENTS.md` as the API/ownership contract, but replace superseded lane language with links rather than duplicated instructions.
4. Add `specs/SPEC_INDEX.md` with stable namespaced IDs and status. Do not renumber historical specs; record aliases/collisions.
5. Ensure `SPEC_003_data_platform_hardening.md` and its WPs are either committed/approved or clearly labelled local draft. A board must not call an untracked document ratified implementation truth.

## 8. H1 - Security, privacy, mutation policy, and ownership

### H1.1 Rebase and land SEC-001a and PRIV-001

**Scope:** PRs #325 and #326 or equivalent replacement PRs.

1. Rebase each onto the selected canonical baseline.
2. Review the final diff independently, including route registration/config behavior, not only tests.
3. For #325, verify all `/debug/*` routes are absent in production or require both the correct role and an explicit debug-control secret; verify `/zs` fails closed when credentials are missing; verify tracebacks are never returned.
4. For #326, enumerate every LLM egress path and prove each passes through the redaction/policy gateway; retain a static no-bypass test.
5. Run the affected suites after the final nit, then the complete backend smoke and conservation suites.
6. Regenerate OpenAPI/changelog if the exposed route contract changes.
7. Obtain independent approval before merge.

**Minimum tests:**

- production config cannot register unauthenticated debug mutations;
- absent `/zs` credentials produce unavailable/denied, never fallback access;
- exception details use the standard error envelope without traceback/file paths;
- direct synthesis and gateway synthesis redact the same PII fixture;
- bypass inventory test fails when a new raw provider call site is introduced.

**Disposition (2026-08-13 — independent review + owner ruling).** #326 is re-scoped **PRIV-001a**:
it redacts PII on the direct `services/llm.py` synthesis egress (4 sites, fail-closed, real
call-site tests — **APPROVE-WITH-NITS**) but does **NOT** satisfy item 4 or the last two minimum
tests. Raw provider egress still exists at `services/extraction_llm.py` (OpenAI **and** Anthropic),
`integration/entity_resolver.py` (chat + embeddings), `integration/embedder.py`, `services/search.py`,
and operational scripts; neither the static no-bypass inventory test nor the direct-vs-gateway parity
test exists. **H1.1 closure = CHANGES REQUIRED**, tracked as **P0 PRIV-001b** (COORDINATION §12 /
PRODUCT_BACKLOG P0): one **provider-agnostic** egress guard (OpenAI chat + embeddings, Anthropic
messages); an AST **static no-bypass test** that fails on any raw SDK `*.create` outside an
allowlisted adapter (benchmarks/tests allowlisted with reasons); per-site capture tests proving a
scan failure ⇒ **zero** provider calls; and `MZ_PII_POLICY=allow` forbidden/guarded in production.
Sensitive-data / multi-tenant onboarding stays **BLOCKED** until PRIV-001b lands.

### H1.2 Finish SEC-001b with a route-policy registry

Do not scatter another round of ad hoc `Depends(require_role(...))` calls without an enforceable inventory.

1. Add a typed route-security policy/metadata registry. For every route record:
   - canonical operation ID;
   - read versus mutation semantics (POST searches must be explicitly read-like);
   - minimum role;
   - authentication required/optional;
   - ownership/tenant scope;
   - idempotency behavior;
   - legacy alias/deprecation state.
2. Introspect registered FastAPI routes in `tests/test_route_security_policy.py`.
3. Fail if any mutation is absent from the registry, lacks an auth dependency, or declares resource ownership without an ownership check.
4. Explicitly review and fix at least these mutation families:
   - catalog tags, HITL, bulk/pipeline, refresh/enrich;
   - steward refresh/action endpoints;
   - metrics refresh/compute;
   - enrichment mutations;
   - feedback mutations;
   - intelligence dismiss/update actions;
   - chat/research session create/delete/update;
   - decisions, war rooms, comments, and outcomes;
   - debug/control-plane operations.
5. Test both canonical and legacy aliases. An alias must not have weaker policy.
6. Append the API changelog and preserve the 14-day deprecation window where a client-visible legacy path changes.

**Negative tests:** anonymous, viewer-on-editor, editor-on-enterprise, user-A-on-user-B resource, malformed/expired JWT, missing owner, and duplicate/idempotent request.

### H1.3 Make deployment mode and ownership explicit

1. Decide and document `single_tenant` versus `multi_tenant` as an ADR.
2. If multi-tenant is supported, add tenant/owner columns and indexes additively, backfill safely, and enforce scope in repository/service queries, not only route code.
3. If only single-tenant is supported at transfer, validate that mode at startup, disable multi-user claims/features that imply isolation, and create the P1 migration plan.
4. Resource types requiring an explicit decision include workspaces, engagements, dossiers, briefs, research sessions/jobs, decisions, war rooms/comments, feedback, connector credentials/configuration, uploads, and exports.
5. Add cross-user and enumeration tests, including guessed UUIDs.

### H1.4 Remove production demo-auth behavior

1. Remove `useDemoAutoLogin()` from the normal CI page path.
2. If a demo build is retained, compile it only behind an explicit `VITE_MZ_DEMO_MODE=true` build flag that defaults false and is rejected by production deployment config.
3. Never ship a default enterprise credential in the production bundle.
4. Seed users only through an explicit operator command/environment and force non-default credentials.
5. Validate `MZ_JWT_SECRET`/`SECRET_KEY` strength and presence in production before readiness.
6. Centralize logout/token-expiry behavior; do not let components independently reinterpret auth state.

**Exit for H1:** route-policy inventory has zero unclassified mutations; all negative tests pass; #325/#326 are on the canonical branch; production artifact contains no demo credential; independent security reviewer approves.

## 9. H2 - Operational health and recovery

### H2.1 Close the current red operational-health state

Use issue #207 and a fresh run as the starting record.

1. Re-run health read-only and capture current source state before changes.
2. Diagnose `clinical_trials_gov`: reconcile/terminate the stuck run with an explicit terminal reason and determine whether zero rows were quiet, truncated, or false green.
3. Diagnose `mesh_ontology`: reconcile the 21 stuck runs, identify scheduler/worker ownership, and prevent duplicate/orphan starts.
4. Diagnose `openfda_labels` and `openfda_faers`: determine whether source quietness, cursor logic, disabled schedule, source failure, or stale materialization explains 41/69-day ages. Do not call stale data healthy solely because the latest run says `SUCCESS_NO_CHANGE`.
5. Correct ChEMBL DLQ source serialization so a stable source ID is stored, never a bound-method representation.
6. Classify all 1,547 pending DLQ rows by source/cause/age. Assign replay, quarantine, supersede, or accepted-debt disposition without deleting history.
7. Publish owner and SLA for red connector, stuck-run, and DLQ alerts.

### H2.2 Make recovery automatic and conservative

1. Add a lease/heartbeat to scheduled connector runs or enforce a single dedicated scheduler instance.
2. Add a reconciler that marks expired RUNNING rows `ABANDONED`/`FAILURE` with reason and timestamps; never rewrite them to SUCCESS.
3. Make retries idempotent by source/cursor/run key.
4. Separate liveness from readiness and expose degraded dependencies/router/schema state.
5. Add backup/restore and migration rollback exercises to the evidence pack.

**Validation/exit:**

- no RUNNING row older than the agreed SLA;
- no duplicate active lease for the same source/partition;
- DLQ conservation: `pending_before + new = replayed + quarantined + superseded + pending_after`;
- seven consecutive scheduled operational-health runs green, or an owner-approved exception names risk, owner, expiry, user-visible degraded state, and non-weakened threshold;
- issue #207 updated with evidence rather than closed by assertion.

## 10. H3 - OpenAPI and backend/frontend contract truth

### H3.1 Reconcile the path set

1. Generate OpenAPI from the selected SHA and compare path/operation IDs to `schema/openapi.json`.
2. Classify every delta as API, legacy alias, debug/operator-only, SPA/static, or accidental registration.
3. Mark SPA/static routes `include_in_schema=False`.
4. Decide the canonical API prefix. Keep legacy endpoints for the required deprecation window and mark `deprecated: true`; do not register undocumented duplicates indefinitely.
5. Give every contracted operation a stable unique `operation_id`.
6. Regenerate `schema/openapi.json` and append `docs/API_CHANGELOG.md`.

### H3.2 Make drift impossible to merge

1. Update `scripts/snapshot_openapi.py` to be deterministic.
2. Add a CI command that generates to a temporary file, normalizes it using the same code path, and fails on any diff.
3. Add a non-vacuous assertion that the schema contains an owner-approved minimum number of API operations and key security schemes.
4. Add a route-manifest/OpenAPI equality test for required routers.

Suggested gate:

```powershell
python -m scripts.snapshot_openapi --check
git diff --exit-code -- schema/openapi.json
```

### H3.3 Establish a typed frontend client boundary

1. Generate TypeScript OpenAPI types into a clearly generated, non-hand-edited file, or add an equivalent schema-to-client conformance test.
2. Keep a compatibility facade while splitting `frontend/src/api.ts` by domain; do not change all callers in one PR.
3. Central transport owns auth, standard error envelopes, request IDs, abort/timeouts, 429 `Retry-After`, and safe retry policy.
4. Remove direct mutation fetches from components/hooks, beginning with steward refresh and autosave.
5. Contract-test representative 2xx, 401, 403, 404, 409, 422, 429, and 5xx envelopes.

**Exit for H3:** generated schema equals snapshot; zero accidental SPA/debug paths; aliases intentionally documented; frontend conformance/type generation is green; no changed mutation bypasses the client.

## 11. H4 - Frontend truthfulness and correctness

### H4.1 Fix false persistence states

For `useBriefAutosave`, choose one honest contract:

- **Server persistence:** call the documented endpoint, include auth/version, await acknowledgment, handle retry/conflict/offline state, and show `Saved` only after server success; or
- **Local draft only:** persist locally with an explicit `Saved on this device` label and never imply server persistence.

Steps:

1. Write a RED test showing the current hook reaches `saved` without a network/local persistence acknowledgment.
2. Implement one contract end-to-end; do not leave a no-op promise.
3. Test pending debounce, success, error, retry, unmount cancellation, stale response ordering, 401, and 409/version conflict.
4. Make preview-only connector/onboarding flows visually and semantically explicit until their server contract exists.

### H4.2 Fix mutation error visibility

1. Replace component-level `/steward/refresh` fetches with the typed client.
2. Remove `.catch(() => {})` on user-triggered mutations.
3. Show accessible pending/success/error states and retain a retry path.
4. Add tests asserting an error cannot render as success/unchanged without explanation.

### H4.3 Eliminate hook correctness errors before lint cosmetics

1. Fix `EntityProfileCard.tsx` so all hooks execute unconditionally before returns, preferably by splitting loading/error/content components.
2. Fix all Rules-of-Hooks errors and add render-transition tests (loading -> data -> new entity; error -> retry).
3. Address `set-state-in-effect` cases by deriving state or moving resets to event/keyed-component boundaries where appropriate.
4. Remove unused disables and unused values.
5. Ratchet `no-explicit-any` by domain; replace with generated types, `unknown` plus validation, or precise types. Do not globally disable the rule.
6. Keep `npm run typecheck`, full Vitest, and build green after every slice.

### H4.4 Centralize auth/session behavior

1. Add an auth/session provider or store as the sole semantic source for token, role, expiry, and login state.
2. Components consume capabilities (`canEdit`, `canAdmin`) rather than reading local storage directly.
3. Centralize 401 logout, 403 messaging, and token refresh/expiry.
4. Plan httpOnly secure cookies as a P1 ADR if cross-origin/deployment constraints permit.

**Exit for H4:** no production demo autologin; no false saved state; changed mutations surface failures; Rules-of-Hooks errors zero; full frontend tests/typecheck/build green; changed surfaces meet light/dark and Lighthouse accessibility >=95 per frontend mandate.

## 12. H5 - Reproducible assurance and delivery protection

### H5.1 Commit Python test/tool policy

1. Add `pyproject.toml` or focused configs for pytest, Ruff, type checking, and Bandit.
2. Register the `integration` marker and set explicit asyncio fixture-loop behavior.
3. Start with a reviewed baseline/allowlist for existing security warnings; every suppression includes rule, file/line scope, rationale, owner, and expiry where applicable.
4. Add `ruff` and security/config checks to CI without using repository-wide ignores.
5. Introduce typing incrementally at stable service/schema boundaries; do not require an all-repo mypy rewrite in one PR.

### H5.2 Make the backend full suite finish in CI

1. Profile the 4,514-test suite with durations and identify hangs/external waits.
2. Ensure unit tests have network/LLM/DB guards and bounded timeouts.
3. Partition deterministically by surface or collected manifest; preserve a final collection/conservation check so no shard silently omits files.
4. Run shards on PRs or merge queue and publish JUnit/duration artifacts.
5. Establish the green baseline before making it required.
6. Keep Lane-2/live tests separate and truthfully skipped/failing when credentials are unavailable.

### H5.3 Enforce full frontend quality

Gate rollout:

1. PR A: Rules-of-Hooks and parser errors zero; enforce those rules.
2. PR B: source lint zero or reviewed ratchet; enforce no regression.
3. PR C: test lint debt zero/ratcheted; enforce full `npm run lint -- --max-warnings=0`.
4. Add full Vitest, typecheck, lint, and production build to CI.
5. Inventory 22 todo tests with owner, reason, and expiry; disallow new unowned todo/skip.
6. Add bundle analysis. Ratchet the current entry bundle first, then introduce route-level lazy loading and set an owner-approved target from measured surface budgets.

### H5.4 Protect the delivery branch

After all named checks are reliably green:

1. Set required status checks to strict/up-to-date.
2. Require at least one independent approval.
3. Require CODEOWNER review for protected security/schema/contract/workflow files.
4. Dismiss stale approvals when protected surfaces change.
5. Preserve admin enforcement, force-push prohibition, and deletion prohibition.
6. Test the policy with a disposable PR; record screenshots/API output in the evidence pack.

**Required command floor:**

```powershell
python -m pytest tests -q
python -m pytest tests/test_conservation_gates.py -q
python -m scripts.snapshot_openapi --check
cd frontend
npm run lint -- --max-warnings=0
npm run typecheck
npm test
npm run build
```

If the frontend test script changes, document and use the package's canonical non-watch command. A command that collects zero files is a failure.

## 13. H6 - P1 maintainability and runtime boundaries

These are important but may be accepted as dated P1 debt after the P0 floor.

### H6.1 Typed router composition and readiness

1. Replace per-router import `try/except` blocks with a manifest declaring required/optional status.
2. Required router failure blocks startup/readiness.
3. Optional router failure produces a structured degraded readiness item and alert.
4. Test required manifest == registered routes == OpenAPI operations.

### H6.2 Release migrations and scheduler ownership

1. Move migrations to a release/predeploy job that fails closed.
2. Runtime verifies compatible schema version and does not auto-migrate by default in production.
3. Add forward/backward compatibility tests for rolling deploys.
4. Run scheduler as one leased leader or dedicated worker; test lease expiry/failover.

### H6.3 Exception-policy ratchet

1. Produce a generated inventory of broad/empty catches in runtime directories.
2. Classify the highest-risk data mutation, auth, startup, and scheduler catches first.
3. Replace silent loss with typed result, counted quarantine/DLQ, retry, or fail-closed behavior.
4. Allow best-effort cleanup/telemetry only with structured logging and an explicit advisory policy.
5. Add a no-new-unclassified-catch gate for changed files.

### H6.4 Split high-change modules safely

Recommended order:

1. Characterize public route/service behavior.
2. Extract pure schemas/policies.
3. Extract persistence repositories.
4. Extract orchestration by domain.
5. Preserve facade/import compatibility.
6. Compare OpenAPI, test collection, and relevant behavior after each extraction.

Initial candidates: `api/routes/catalog.py`, `services/unified_handler.py`, `services/chat_handlers/handlers.py`, `integration/knowledge_store.py`, `services/llm.py`, `frontend/src/api.ts`, `DataCatalogPanel.tsx`, and `GraphExplorer.tsx`.

### H6.5 Reproducible dependencies and build layout

1. Produce a locked/hashed Python deployment/test dependency set using an owner-approved tool.
2. Build/test from a fresh venv and run `pip check` there.
3. Resolve the stale root `pulseaction`/pnpm/Turbo scaffold: remove it if provably unused, or restore/document the real workspace. Nixpacks must not need a comment/workaround to bypass an accidental root build forever.
4. Keep `frontend/package-lock.json` authoritative for the actual npm build.
5. Add dependency/SBOM and vulnerability update policy.

## 14. H7 - Documentation, hygiene, and receiving-team exercise

### H7.1 Publish the transfer package

Create/update:

- `docs/HANDOFF.md` - canonical start page;
- `docs/ARCHITECTURE.md` plus the existing simple HTML architecture view - layers, tools, skills/agents, data/control flow, deployment boundaries;
- `docs/LOCAL_DEVELOPMENT.md` - fresh clone, services, fixtures, commands, troubleshooting;
- `docs/DEPLOYMENT_RUNBOOK.md` - environments, secrets by name, predeploy migration, deploy, rollback, verification;
- `docs/OPERATIONS_RUNBOOK.md` - health, scheduler, connectors, stuck runs, DLQ, alerts, incident ownership;
- `docs/BACKUP_RESTORE_RUNBOOK.md` - RPO/RTO and exercised restore;
- `docs/SECURITY_MODEL.md` - auth, roles, ownership/tenancy, PII/LLM egress, debug/operator paths;
- `docs/API_CONTRACT.md` - canonical prefix, generation, deprecation, client process;
- `docs/KNOWN_DEBT.md` - risk, impact, owner, due date, interim control, acceptance signature;
- `docs/ADR_INDEX.md` - accepted/superseded architecture decisions;
- `docs/handoff/evidence/` - final command/probe summaries without secrets.

Avoid duplicating live status across documents. `HANDOFF.md` links to canonical sources.

### H7.2 Prove onboarding from a fresh clone

Have a developer who did not implement the changes:

1. clone the repository to a new path;
2. follow only documented prerequisites;
3. create backend/frontend environments;
4. run migrations against a disposable DB;
5. start backend and frontend;
6. log in without demo fallback;
7. run smoke, contract, frontend tests/typecheck/build;
8. execute one read-only connector fixture and inspect provenance;
9. locate an alert, DLQ item, migration, API contract, and rollback instruction;
10. record every undocumented step and repair the docs.

**Exit for H7:** receiving lead completes the exercise, signs the known-debt register, and can identify the canonical code, contract, runbooks, and on-call/escalation owner without relying on chat history.

## 15. H8 - Delta-update and execute the data-platform program

H8 begins after the P0 transfer floor unless the owner explicitly changes the sequence.

### H8.1 Correct the program status before implementation

1. Reverify `SPEC_003_data_platform_hardening.md` and each selected WP against the new canonical SHA.
2. Add a `Baseline delta` section listing landed, partial, stale, and remaining behavior.
3. Correct WP-0 immediately:
   - migration 098 already adds `records_skipped` and `records_failed`;
   - `_finalize_etl_run()` already writes them;
   - do not propose duplicate columns or claim they are absent;
   - retain/add the still-missing fetched, emitted, filtered, quarantined, truncated/accounting design as verified;
   - reverify all cited line numbers after security/runtime refactors.
4. Reverify WP-1 transaction threading against the current DB/pool implementation and any H6 migration changes.
5. Reverify WP-4 against current resolver, crosswalk, schema, and production fill before choosing a migration/view design.
6. Mark the board `specced`, `delta-verified`, and `implemented` as separate states.

### H8.2 Execute only after owner selection

Recommended sequence remains:

1. WP-0 truthful outcomes and controls.
2. WP-1 raw artifacts, deterministic replay, and per-record atomicity.
3. WP-4 grain-typed deterministic identity spine.
4. WP-12 assurance throughout.

Use shadow -> dual-read -> reversible flag -> cutover -> separate cleanup. Preserve every conservation equation and require real Lane-2 evidence where the WP makes a production-data claim.

## 16. Final P0 acceptance checklist

- [ ] H0 inventory committed and owner-approved; no unpreserved local state.
- [ ] Canonical baseline and deployed SHA documented.
- [ ] PR #325 and #326 landed or equivalently replaced after independent review.
- [ ] Route-policy test reports zero unclassified/unguarded mutations.
- [ ] Ownership/tenancy mode explicit and negative isolation tests green.
- [ ] Production bundle/config has no demo credential, weak fallback, or unauthenticated debug mutation.
- [ ] Operational health satisfies the observation gate; stuck-run and DLQ equations reconcile.
- [ ] OpenAPI generation exactly matches the committed contract and frontend conformance.
- [ ] No visible UI reports unacknowledged persistence as saved/success.
- [ ] Frontend Rules-of-Hooks zero; lint/typecheck/full tests/build required and green.
- [ ] Backend full suite executes in non-vacuous CI; marker/config warnings resolved.
- [ ] Required checks strict/up-to-date and independent approval required.
- [ ] Archive/PR/worktree cleanup applied only from the approved manifest.
- [ ] Fresh-clone onboarding and restore/rollback exercise recorded.
- [ ] Receiving lead signs `docs/KNOWN_DEBT.md` and transfer acceptance.
- [ ] SPEC-003 status corrected; implementation remains gated on owner WP selection.

## 17. Claude kickoff instruction

The owner can paste the following into a fresh Claude session:

> Execute `specs/SPEC_HANDOFF_001_repository_maturity_and_transfer.md` as the repository transfer program. Read `docs/COORDINATION.md`, `CLAUDE.md`, and `AGENTS.md` first. Start with H0 only: build and commit the non-destructive repository/PR/worktree/untracked-artifact inventory from a clean current `origin/main` worktree. Preserve all dirty and untracked work; do not move, delete, close, merge, or prune anything during H0.1. Verify every review claim against the chosen SHA and record drift. Then propose the exact cleanup and P0 PR sequence for owner approval. After approval, execute one bounded PR at a time in spec order with RED/GREEN/final-regression evidence run after the final diff, OpenAPI/changelog protocol, and independent review. Never weaken a test/gate or reuse pre-nit output as final evidence. Do not start SPEC-003 WP implementation until the handoff P0 floor is green, its specs are delta-updated, and the owner explicitly selects the WP.

## 18. Sign-off

```text
Owner acceptance of P0 scope: __________________  Date: __________
Backend/Claude lead: ___________________________  Date: __________
Frontend lead: _________________________________  Date: __________
Independent security reviewer: _________________  Date: __________
Receiving engineering lead: ____________________  Date: __________
Canonical accepted SHA: _________________________________________
Known-debt register commit: _____________________________________
```
