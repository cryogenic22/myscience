# WP-2 Connector-Platform lane — work-item ledger

**Protocol:** Owner directive of 2026-08-16 (Connector Lane Independent-Review Protocol).
**This file is a RECORD, not a gate.** Per the directive's "do not implement a duplicate local
review gate", nothing here executes, validates, or attests. Enforcement waits on the central
WP-12 control (#327). No lane-specific copy of the review machinery exists or may be created.

**Builder:** Claude connector team. **Independent reviewer:** Codex
(`codexindependentreviewer[bot]`, App ID 4614805). The builder has never requested, inspected,
copied, minted, or used that identity's key or token, has not added it to any bypass list, and has
not granted it repository-content write access. **The builder does not approve its own work and has
not produced any APPROVE artifact.**

---

## 1. Pre-work verification (directive §"Before starting or resuming any work item")

Re-run against `origin` after `git fetch` for **round 3** (C.4), 2026-08-16. **Every value below was
re-derived from the repository, not recalled**, including the values that were unchanged.

| Check | Verified value | Status |
|---|---|---|
| Authoritative board fetched | `docs/COORDINATION.md` @ `da6887c` (H0.3 line) | ✅ |
| Lane row re-read | §13 Connector-Platform lane; §13.3 sequence gate; §13.5 ASKs | ✅ |
| **Base SHA** | `claude/handoff/h0-baseline` @ **`da6887c`** — unmoved; `merge-base --is-ancestor da6887c HEAD` passes | ✅ unchanged |
| Predecessor gate | H0 → H1 → H2 → WP-12 → WP-0 → WP-1 → H3/H4/H5 → **WP-2**. WP-12 (#327) **not landed** | ⛔ **implementation blocked, as expected** |
| Owned paths | `specs/data_platform/WP-2*` — **edited: they are this work item's output** · `services/connector_taxonomy.py`, `api/routes/hub.py`, `tests/connector_platform/` — untouched | ✅ |
| Contested paths / PRs | **#320** OPEN (`api/routes/sources.py`) · **#324** OPEN (`services/source_registry.py`) · **#56** OPEN (`api/routes/sources.py`) · **#66** OPEN (`connectors/base.py` +8) | ✅ all still open; **none touched** |
| Migration reservation | **NONE reserved.** Highest existing = `099_source_onboarding_contract.sql`. Reservation deferred to implementation time per SPEC-003 §9 / COORDINATION §7.4 | ✅ correct-by-abstention |
| Protected surfaces | `protected-surface.txt` @ blob `1354ff1e`; **`changed ∩ protected = ∅`** and **`changed ∩ contested = ∅`** asserted separately (A5) | ✅ untouched |
| Protected-surface change in flight | **#327 modifies `protected-surface.txt` + `.github/CODEOWNERS`**, adding `assurance/contract/`, the validator/scanner/CLI, the WP-12 spec and its three test files. **No WP-2-owned path becomes protected.** | ⚠️ recorded dependency — re-verify forbidden paths after #327 lands |
| Assurance floor | see the round-3 snapshot below | ⛔ floor not landed |

### 1.1 Round-3 dependency snapshot (re-taken, not carried forward)

| Dependency | State | Head at round 3 | Movement since round 2 |
|---|---|---|---|
| Base `claude/handoff/h0-baseline` | — | `da6887c` | unmoved |
| **#327** WP-12 assurance kernel | OPEN, unmerged | **`6a1014d`** | **moved again** (`3002424` → `0368356` → `6a1014d`) |
| **#328** PRIV-001b | OPEN, unmerged | `eee2219` | unmoved |
| #320 contested (`api/routes/sources.py`) | OPEN | `b1c876d` | — |
| #324 contested (`services/source_registry.py`) | OPEN | `d215bea` | — |
| #56 contested (`api/routes/sources.py`) | OPEN | `5953679` | — |
| #66 contested (`connectors/base.py` +8) | OPEN | `64bf427` | — |

#327 has now moved in **both** intervening rounds. That is ordinary external drift, and it is the
concrete reason this snapshot is **re-derived every round rather than carried forward** — a stale
dependency head in a review request is indistinguishable from a misrepresentation to the reviewer.

**Collisions resolved locally by assumption: none.** #327's protected-surface expansion still adds
no WP-2-owned path; it remains a recorded dependency to re-verify after it lands, not something
acted on here.

## 2. Work item

| Field | Value |
|---|---|
| **Work-item ID** | **WP2-SPEC-001** |
| **Title** | WP-2 safe-fetch threat model + versioned source-contract control-plane specification |
| **Phase** | Design/specification — A, B, C, C.1, C.2, C.3, **C.4** complete |
| **Class** | **DESIGN-ONLY.** Zero runtime code. |
| **review_status** | **`REVIEW_READY_PENDING_ASSURANCE_FLOOR`** |
| **code_head_sha (H3) — the specification content submitted for fresh review** | **`99e51ca9d3d53a9ebf494d269a453445a265a047`** |
| **Superseded** | H1 `c65be6f` (10 defects) → H2 `9f6503f` (12 findings) → **H3**. Each round's evidence is **stale by construction**; only H3 is offered |
| **ledger commit** | the branch tip. **`parent(tip) == H`**, and `git diff --name-only H tip` returns this file alone. Its own hash is deliberately not recorded here — see the note in §3 |
| **Branch** | `claude/connector/wp2-source-contract-spec` (local == `origin/…`) |
| **Base** | `claude/handoff/h0-baseline` @ `da6887c` |
| **Worktree** | `../mz-connector-platform` |
| **PR** | **None open.** Deliberate — the directive says stop at REVIEW_READY. |

### 2.1 Goal

Specify, without building, the control plane that makes a *user-authored* source endpoint safe:
immutable versioned contracts, first-class source identity, a deterministic authority boundary for
network access and credentials, and the acceptance evidence that would prove it.

### 2.2 Explicit non-goals

Runtime wiring · migrations · executable tests · fixtures · the identity slice · DB implementation ·
enabling generic CSV/RSS/REST connectors · touching contested files · OpenAPI regeneration ·
cursors/leases (**WP-9**) · `DomainPack` activation (**WP-3**) · untrusted-content handling
(**WP-5**) · quality-as-promotion-gate (**WP-8**) · net-new connector breadth (paused, SPEC-003 §3) ·
any lane-local review gate.

### 2.3 Acceptance criteria — **PROPOSED, NOT RATIFIED**

The directive requires owner-ratified criteria *before implementation*. **None exist yet**, so
WP2-SPEC-001 is a *proposal* of the bar, not a claim against it. Ratification is an owner act; the
builder will not self-author it, and `assurance/contract/` becomes protected surface when #327
lands, which is the correct home for the ratified set.

| ID | Proposed criterion | Independent truth source |
|---|---|---|
| **A1** | Every finding the spec relies on is re-verified against code at `da6887c`, with drift recorded not silently corrected | `WP-2_findings_reverification.md`; re-runnable greps at cited file:line |
| **A2** | No claimed control contradicts another document in the package | Cross-document diff of the four specs |
| **A3** | Every "today" claim cites a verifiable file:line at the pinned base | The repository at `da6887c` |
| **A4** | Ownership claims match SPEC-003 §6 exactly | `specs/SPEC_003_data_platform_hardening.md` §6 |
| **A5** | Contested/protected files unedited | **Two separate assertions** (C.3 fix — a chained `changed ∩ protected ∩ contested` can pass when a changed file is protected but *not* contested): `changed ∩ protected = ∅` **AND** `changed ∩ contested = ∅` |
| **A6** | Every proposed DDL constraint is valid PostgreSQL | DDL applied to an empty database (unwritten — M-35c) |
| **A7** | No artefact is described as existing unless it exists | Filesystem at H |
| **A8** | Unratified dependencies are marked provisional and pinned | SHA-256 digests recorded in spec §2 |
| **A9** | Cross-lane conflicts are raised as ASKs, not resolved unilaterally | COORDINATION §13.5 |
| **A10** | Deferred threats are named, never silently omitted | "Coverage honesty" sections |

### 2.4 RED / mutation cases

**Counts, recounted at H3 (third correction — see the note below):**

| Artefact | Count | Command |
|---|---|---|
| Invariants | **22** | `grep -cE '^\| \*\*INV-'` |
| Mutation-case rows in the test spec | **83** | `grep -cE '^\| \*\*?M-'` |
| Distinct mutation-case IDs | **83** | same, `\| sort -u` — rows and IDs now coincide |
| Safe-fetch cases (threat model §7) | **11 numbered + 8 SF-variants = 19** | `grep -cE '^[0-9]+\.'` and `grep -cE '^\*\*SF-'` |
| **Total named cases** | **124** (22 + 83 + 19) | derived |

**I have now got this count wrong twice** — "~60 / 11" in C.2, then "70 distinct / 95 rows" in C.3,
and the reviewer corrected both. The root cause was greping a moving target with a regex that
matched cross-references as well as definitions, and reporting the result without re-deriving it
after the edits that followed. Every figure above is re-derived at H3 with the exact command shown,
and the commands are recorded so the next round recounts rather than carries forward.

> **None is RED. RED means executed and observed to fail; nothing here has been executed.** All are
> **unmet design criteria** — unwritten and unrun. This distinction is recorded because C.1
> violated it by labelling M-28a "RED at spec time"; C.2 corrected it. No case may be cited in a
> RED→GREEN claim until executed.

Highest-value cases, each derived from a *verified* defect rather than a hypothesis:
**M-20a** secret canary across every sink · **M-22** new credential-shaped field cannot reach
storage by construction · **M-35c** DDL applies to an empty database (would have caught C.1's
invalid composite FK) · **M-35a** projections rebuild byte-identically from the event log ·
**M-11** missing/expired/forged/hash-mismatched grant · **M-39d** tenancy at the worker boundary,
which never passes through a route.

### 2.5 Conservation requirements

No historical `etl_runs` row orphaned by the identity migration (`legacy_source_key` UNIQUE) · no
silent row/field/provenance drop in backfill — a conservation report with reasons · migration 099
columns deprecated, never dropped; cleanup a separate PR · superseded/revoked rows stay queryable ·
preview reports dropped rows per stream · **ASK-WP2-3: WP-1's content-addressed `retention_class`
silently collapses two acquisitions' rights to one — an open conservation defect at the seam.**

### 2.6 Security and provenance requirements

Standing invariant: *AI proposes declarative contracts; deterministic validators control network
access, persistence and promotion.* No arbitrary SQL/Python callables · no unrestricted URL fetch ·
safe fetch covers SSRF, redirects, DNS rebinding, private/link-local (incl. IPv4-mapped IPv6), TLS
hostname verification under IP pinning, env proxies, credential scope, response limits · credential
**slots + FetchGrant**, never inline values or a bare locator; query placement forbidden by default;
credential values **excluded, never hashed**, from every persisted artefact · every source carries
`source_instance_id`, contract version, rights, certification grade, refresh policy · no silent
truncation or watermark advance after partial extraction · **preview uses the same parsing and
transformation contract as execution, and a preview green may never substitute for a production
probe** · generic connectors stay unreachable until contract + safe-fetch are ratified.

### 2.7 Required gates

| Gate | Status at H | Honest note |
|---|---|---|
| Lane-1 `conservation-gate.yml` | **NOT RUN** | Triggers only on push-to-`main` / PR-to-`main`. No PR exists by directive. `gh run list --branch …` returns **empty**. **No CI run ID exists to cite, and none is claimed.** |
| Lane-2 `operational-health.yml` | **N/A** | Scheduled/live; no data path touched |
| Protected-surface sync | **N/A at H** | No protected file edited; the test runs in CI |
| Focused local tests | See §2.7.1 for the full command, full output, a determinism re-run and a baseline run at `da6887c` | **Corroborating only — not the load-bearing argument.** See the note below. |
| Vacuous-green check | **Not applicable, and stated rather than implied** | Nothing was skipped, emptied or filtered to produce a pass; a docs-only change has no suite to make vacuous |

### 2.7.1 Test evidence — pasted, with its limits stated

An earlier draft of this ledger asserted "31 focused tests pass locally" as regression evidence
without pasting the command or output, and without showing the run was deterministic or that the
baseline was unchanged. That is an ungrounded claim by this project's own DoD
(`conservation-gates.md`: *"The passing command **and its pasted output** are in the close-out"*),
and it is corrected here rather than left standing in a record under review.

**The load-bearing argument is the diff, not the test run.** A test run cannot prove a docs-only
change is inert; the diff can:

```
$ git diff --stat da6887c..HEAD -- tests/
(empty — every test file is byte-identical to the base)

$ git diff --name-only da6887c..HEAD | grep -vE '\.md$'
(no output — the cumulative diff is 100% Markdown)
```

Because no `.py` file differs from the base, any test run at HEAD executes byte-identical code to a
run at `da6887c`. The runs below **corroborate** that; they do not establish it.

```
$ python -m pytest tests/test_connector_spec.py tests/test_connector_taxonomy.py -p no:randomly

### RUN 1 (at HEAD)
collected 31 items
tests\test_connector_spec.py .............                               [ 41%]
tests\test_connector_taxonomy.py ..................                      [100%]
============================= 31 passed in 1.01s ==============================

### RUN 2 (determinism re-run, same tree)
tests\test_connector_taxonomy.py ..................                      [100%]
============================= 31 passed in 0.54s ==============================

### BASELINE (detached worktree at da6887c, pre-lane; removed after the run)
collected 31 items
tests\test_connector_spec.py .............                               [ 41%]
tests\test_connector_taxonomy.py ..................                      [100%]
============================= 31 passed in 1.66s ==============================
```

Baseline and HEAD agree: **31 collected, 31 passed, identical per-file distribution.**

**What this evidence does NOT support**, stated so it cannot be over-read:

- It is **not** the Lane-1 gate. Lane 1 has not run (no PR; the workflow triggers on `main` only).
- It is **two files out of the suite**, chosen because they cover `connectors/spec.py` and
  `services/connector_taxonomy.py` — the modules this specification reasons about. It is not a
  full-suite result and must not be cited as one.
- Passing tests say nothing about whether the *specification* is correct. No specification claim in
  this package is supported by a test; all are supported by cited file:line evidence at `da6887c`.

### 2.8 Declared residual limitations

1. **Three blocking cross-lane ASKs unresolved** — WP-0 outcome vocabulary, WP-9 cursor/lease
   interface, WP-1 rights attachment (COORDINATION §13.5).
2. **Acceptance criteria not owner-ratified** (§2.3).
3. **No executable evidence exists.** Every control is asserted by design, not demonstrated.
4. **TIV2 dependency provisional** — untracked, DRAFT, "Implementation authority: none". Pinned by
   digest; WP-2 renames if it ratifies differently.
5. **Separation of authorship is discipline, not structure** — worktree agents run under the
   owner's git identity, so INV-10 makes a violation visible, not impossible.
6. **Secret resolver, preview authorization, certification authority, egress default and legacy
   backfill scope** are unresolved owner decisions (spec §14).
7. **T-19 / T-20** (source poisoning; fetched content reaching synthesis as instructions) are named
   and **not covered** — WP-8 / WP-5.
8. **#327 will change the protected surface**; forbidden paths must be re-verified after it lands.

### 2.9 Files owned / forbidden

**Changed at H (5, all `.md`):** `docs/COORDINATION.md` (§13 lane registration + §13.5 ASKs) ·
`specs/data_platform/WP-2_findings_reverification.md` · `…_safe_fetch_threat_model.md` ·
`…_source_contract_control_plane.md` · `…_test_specifications.md`.
Verified: `git diff --name-only da6887c..H | grep -v '\.md$'` → **empty**.

**Owned:** `specs/data_platform/WP-2*` — **these are this work item's principal changes**, not
untouched (C.3 fix: the earlier wording called all owned paths "untouched" while the WP-2 specs are
exactly what H changes). **Owned and genuinely untouched:** `services/connector_taxonomy.py` ·
`api/routes/hub.py` · `tests/connector_platform/` (does not exist).

**Forbidden and untouched:** `integration/pipeline.py` · `integration/pipeline_hooks.py` ·
`scheduler/runner.py` · `services/agent/harness.py` · `services/llm_gateway.py` ·
`schema/openapi.json` · `frontend/` · everything in `protected-surface.txt` · **contested:**
`services/source_registry.py` (#324) · `api/routes/sources.py` (#320, #56) · `connectors/` (#66,
plus WP-1 holds `BaseConnector`).

### 2.10 Rollback / disable strategy

**Documentation-only, so rollback is `git revert` of the **9** commits from base to the ledger tip
(8 substantive `da6887c..H3` + this evidence commit; `git rev-list --count da6887c..HEAD`) with zero
runtime effect** — no
migration, no schema, no feature flag, no deployed behaviour. The lane's branch is unmerged and no
PR exists; abandoning it changes nothing in any environment.

For the *specified* system (not yet built), the designed disable path is:
`execution_enabled = FALSE` on the deployment → no grant issuable → no outbound request; contracts
remain stored and inert. Rollback re-deploys a prior immutable contract version; **cursor rollback
is deliberately NOT automatic** (safety depends on cursor kind and sink idempotency — WP-9).

## 3. Review-ready record

**On SHAs — a self-referential ledger is impossible, so it does not try.** (`H` below means the
current reviewed head **H3 = `99e51ca`**.) A file cannot record the
hash of the commit that contains it: writing the value changes the value. Any ledger that appears
to do so is either stale or was amended after the fact. This one therefore pins **only H — the
reviewed specification content** — and describes its own commit *relationally*, which is verifiable
without a hash:

```
parent(branch tip) == H                     # the ledger sits directly on the reviewed content
git diff --name-only H <tip> == this file   # it is evidence-only; it changes nothing reviewed
```

That matches the protocol's own evidence-commit shape. If the reviewer's verdict requires a change
to the *specification*, that produces a new H and this ledger is rewritten against it — the review
evidence goes stale automatically, as the protocol requires. Only the reviewer's own attestation
needs to pin a live-head SHA, and that is the reviewer's artifact to produce, not the builder's.

### 2.7.1b Round-3 finding register (every finding recorded, per the directive)

| # | Finding (H2 review) | Disposition at H3 |
|---|---|---|
| 1 | `etl_run_id UNIQUE` is not 1:1 — no FK, no reverse totality | FIXED — FK added; both directions asserted (M-05l) |
| 2 | Grant stream/certification authority in unconstrained parallel arrays | FIXED — `fetch_grant_streams` child table, composite FKs (M-11i) |
| 3 | PreviewGrant uses a schema requiring certifications | FIXED — nullable `certification_id` + trigger; schema now expresses the difference |
| 4 | Query-credential exceptions unlinked and unchecked at request time | FIXED — linked to the grant; validity condition 10 (M-11j) |
| 5 | Certification partial-unique DDL invalid; scope kinds unclosed | FIXED — `CREATE UNIQUE INDEX … WHERE` for certifications *and* deployments; `CHECK IN` (M-35o) |
| 6 | Containment too late — resolve/embed/DLQ precede canonical store | FIXED — moved to ingress; verified `pipeline.py:343/364/274`; shared DLQ brought inside the boundary (M-33h/i) |
| 7 | `legacy_unverified` prevention relies on an impossible cross-table CHECK | FIXED — trigger + enable path + grant-issue re-read (M-35k) |
| 8 | Event replay and rights lineage incomplete/unconstrained | FIXED — closed vocabularies, no-gap sequence, schema retention, lineage FK chain (M-35l/m/n) |
| 9 | Byte accounting cannot enforce before streaming | FIXED — reserve → stream-with-abort → settle + per-request cap (M-11k/l) |
| 10 | M-40 vacuous for individual safe-fetch variants | FIXED — `SF-02a`…`SF-06a` IDs; manifest enumerates variants |
| 11 | Normative contradictions: `source_jobs`, `job_id`, `'*'` sentinel, rollup, INV-10, T-19/T-20 | FIXED — all five live references corrected; historical mentions retained deliberately and labelled |
| 12 | E2 counts wrong: 8 commits not 7; ≥99 semantic cases not 70 | FIXED — recounted with recorded commands (§2.4); see the honesty note there |

**Nothing was disputed.** All twelve were verified in-file before rewriting, and three of them
(5, 6, 7) were things C.3 specified that PostgreSQL or the live pipeline cannot do.

### 2.7.2 Normative-regression sweep (new in C.3)

The C.2 ledger recorded `conservation_result: no_regression_possible_docs_only`. **That was false**,
and the review was right to reject it. A Markdown-only diff proves no *runtime* regression; it
proves nothing about *normative* regression — and C.2 had in fact regressed the normative surface
in two places: the board asserting M-28a "stays RED" against the test spec's own vocabulary rule,
and "two boundaries" against three declared ASKs. Documentation is the specification here, so its
consistency is a conservation property.

So the docs-only class gets its own check, run each round and recorded:

| Sweep | Method | Round-2 result |
|---|---|---|
| Cross-document contradiction | grep each normative term across all four specs + the board | 4 found and fixed (M-28a, ASK count, "ships fixtures", stale rev refs) |
| Stale object references | grep for every renamed/removed object (`source_jobs`, `source_job_streams`, `rollup_outcome`, `'*'` sentinel, `credential_ref`) | 6 live references found and fixed; historical mentions retained deliberately |
| Revision-marker consistency | every doc's status line, companion refs and cross-refs name the same revision | aligned at C.3 |
| Claim-vs-artefact | every "exists"/"ships"/"committed" claim checked against the filesystem | 1 residual fixture claim fixed in C.2; none remaining |

```yaml
work_item_id: WP2-SPEC-001
review_round: 3
code_head_sha: 99e51ca9d3d53a9ebf494d269a453445a265a047    # H3 — spec content for fresh review
superseded_heads:
  - c65be6fef5578edbef20f87ac2548de04d5355df   # H1 — CHANGES REQUIRED (10 defects)
  - 9f6503fa7532cd5aec4a914a65719a386cf18af0   # H2 — CHANGES REQUIRED (12 findings)
ledger_commit: "branch tip; parent == H; changes only this file (hash deliberately unpinned)"
branch: claude/connector/wp2-source-contract-spec
base_ref: claude/handoff/h0-baseline
base_sha: da6887c7149dfc7783090665b8f22066691542b8
pr_number: none
work_class: design-only
changed_paths:
  - docs/COORDINATION.md
  - specs/data_platform/WP-2_findings_reverification.md
  - specs/data_platform/WP-2_safe_fetch_threat_model.md
  - specs/data_platform/WP-2_source_contract_control_plane.md
  - specs/data_platform/WP-2_test_specifications.md
non_markdown_paths_changed: []
migration_reserved: none
protected_surface_touched: false
contested_files_touched: false
ci_runs: []            # no PR exists; workflows trigger on main only — none claimed
inertness_proof:                 # the load-bearing argument (§2.7.1)
  test_files_changed_vs_base: none      # git diff --stat da6887c..HEAD -- tests/  -> empty
  non_markdown_paths_changed: none      # cumulative diff is 100% Markdown
local_tests:                     # corroborating only; full output pasted in §2.7.1
  - command: python -m pytest tests/test_connector_spec.py tests/test_connector_taxonomy.py -p no:randomly
    head_run: "31 collected, 31 passed in 1.01s"
    determinism_rerun: "31 passed in 0.54s"
    baseline_run_at_da6887c: "31 collected, 31 passed in 1.66s"
    scope: two files only; NOT the full suite; NOT the Lane-1 gate; proves nothing about spec correctness
acceptance_matrix: proposed_not_ratified   # see §2.3
conservation_result: no_runtime_regression_possible   # C.3 fix: NOT "no regression possible".
  # The Markdown-only diff proves no RUNTIME regression. It does not prove no NORMATIVE
  # regression: Markdown can and did regress the specification and the coordination board —
  # the M-28a "stays RED" and two-vs-three-ASK contradictions were exactly that.
normative_regression_check: performed_by_cross_document_sweep   # see §2.7.2
ddl_verified_by_execution: false   # C.4: NO DDL in this package has ever been run.
  # M-35c ("apply the DDL to an empty database") was specified in C.2 and never executed,
  # which is why C.3 shipped an invalid inline partial UNIQUE and, before it, C.1 shipped an
  # unbacked composite FK. DDL claims here are DESIGN INTENT, not verified syntax.
open_asks: [ASK-WP2-1, ASK-WP2-2, ASK-WP2-3]
review_status: REVIEW_READY_PENDING_ASSURANCE_FLOOR
builder_approval_claimed: false
reviewer_app_invoked: false
```

## 4. What the builder has NOT done (stated explicitly)

Not opened a PR · not invoked or contacted `codexindependentreviewer[bot]` · not created an APPROVE
artifact or any review evidence commit · not claimed formal APPROVE · not merged anything · not
implemented a lane-local review gate · not begun dependent implementation · not touched runtime,
migrations, fixtures, contested or protected files · not reserved a migration number · not
requested or handled the reviewer App's credentials.

**Stopped here, awaiting a completely fresh independent review of exact head
`99e51ca9d3d53a9ebf494d269a453445a265a047` (H3).** Evidence from rounds 1 and 2 (`c65be6f`,
`9f6503f`) is stale by construction and is not offered.

## 5. Next bounded deliverable (NOT started)

**WP2-SPEC-002 — resolve the three blocking ASKs**, which is *not* solo work: ASK-WP2-1 needs WP-0,
ASK-WP2-2 needs WP-9, ASK-WP2-3 needs WP-1. The builder's contribution is a proposed normative
interface per ASK; ratification is cross-lane and owner-recorded.

Implementation of any WP-2 slice remains blocked behind the full §12/§13.3 predecessor sequence,
which is unchanged by this protocol.
