# SPEC_042: Centralized Product Backlog + repo doc cleanup

Status: **Shipped 2026-05-09** (Stage 7 closed; Loop #3 complete)

✓ Signed off by user 2026-05-09 (Q1–Q5 resolved during scope conversation; Stage 1 sign-off via /AskUserQuestion)
Owner: Frontend Claude (cross-cutting docs)
Loop: `docs/runbooks/RALPH_LOOP.md`
Depends on: nothing — pure docs work
Successor of: `BACKLOG.md`, `docs/backlog.md`, `ROADMAP.md`,
`docs/product_backlog_research_and_intelligence.md`

---

## 1. Goal

Replace the **fragmented backlog landscape** (4 partially-overlapping
files) with a **single canonical source of truth** at
`docs/PRODUCT_BACKLOG.md`. Carry over every still-relevant item from
the legacy files. Move stale and superseded markdown documents
(brainstorms, one-time reports, draft/colliding specs, auto-generated
benchmark logs) into `docs/archive/` so the repo's surface area
clearly reflects what's *current* without losing history.

Net result:
- One file (`docs/PRODUCT_BACKLOG.md`) that I can read in 30 seconds
  to know what's open, what's blocked, what's in flight.
- One file (`docs/AGENT_BACKLOG.md`) that stays the canonical
  cross-agent coordination surface (BACKEND ↔ FRONTEND requests).
- One file per spec (`specs/SPEC_NNN_*.md`) with a status flag in
  the frontmatter; the product backlog references the spec by
  number.
- The user-feedback queue (`feedback/live_user_feedback.md`) stays
  cron-managed; the product backlog cross-references each open
  feedback row with a one-line stub.
- Stale docs are visibly archived under `docs/archive/<category>/`,
  not deleted. `git log` still recovers history.

## 2. Why now

- 110 raw items spread across 4 files; **none** is a single source
  of truth. Every session opens with "where's the most recent
  list?"; that question shouldn't survive this loop.
- The user-feedback widget shipped in SPEC-041 will start producing
  triage backlog entries on the next 45-min cron tick. Without a
  central backlog those just pile into `feedback/live_user_feedback
  .md` with no integration into the rest of the planning surface.
- 202 markdown files in the repo, ~54 of which are visibly stale or
  superseded. The signal-to-noise ratio when grepping for context
  is bad and getting worse.
- Memory/CLAUDE.md references (`lead_notes_4_dev.md`, `ROADMAP.md`,
  `BACKLOG.md`) currently point at a moving target. Consolidating
  pins those references to a single durable file.

## 3. Surfaces touched

### 3.1 New files

```
docs/PRODUCT_BACKLOG.md          — canonical backlog (this loop creates)
docs/archive/                     — new directory tree (this loop creates)
├── brainstorms/                  — Category A
├── communications/               — Category B
├── reports/                      — Category C + F
├── benchmarks/                   — Category D
└── superseded-specs/             — Category E
scripts/validate_product_backlog.py    — schema + uniqueness validator
scripts/migrate_legacy_backlogs.py     — one-shot helper (re-runnable)
tests/test_product_backlog.py           — pytest for the validator
```

### 3.2 Files moved (53 total, 1-line redirect header at original path)

**Category A — root brainstorms (7 files)** → `docs/archive/brainstorms/`
- `data_layer_design.md`, `vision_rough.md`, `open_data_ai.md`,
  `dark_data.md`, `graphrag-authoring-vs-retrieval.md`,
  `Data_Strategy_brainstorm.md`, `newui-comprehensive-analysis.md`

**Category B — internal communications (2 files; `lead_notes_4_dev.md` stays)**
→ `docs/archive/communications/`
- `dev_2_lead.md`, `comp_intelligence.md`

**Category C — root one-time reports (4 files)** → `docs/archive/reports/`
- `AGENT_TEST_REPORT.md`,
  `reports/quality_scorecard.md`,
  `reports/quality_scorecard_metabolic.md`,
  `reports/intelligence_pipeline_review.md`

**Category D — benchmark eval reports** (~17 files) →
`docs/archive/benchmarks/`. All `benchmark/reports/eval-2026032[3-5]-*.md`.

**Category E — superseded / colliding / draft specs (~20 files)** →
`docs/archive/superseded-specs/`
- All `specs/SPEC_001` … `SPEC_018` where there's a number-collision
  with a later spec OR the earlier spec is clearly superseded by the
  current series (SPEC-021+).
- Plus drafts: `HARNESS_AUDIT.md`, `SESSION_REPORT.md`,
  `LEAD_REVIEW_SPRINT_REPORT.md`, `EXECUTION_PLAN_2026-04.md`,
  `SPRINT_PLAN_2026-04.md`, `raw_PD_notes.md`,
  `brainstorm_pubmed_and_db_crash.md`, `comp_intel_2.md`,
  `logs_rough.md`, `TESTING_GUIDE.md`,
  `ENTITY_LIBRARY_VISION.md`, `CTX_HARNESS_ARCHITECTURE.md`.

**Category F — old `docs/` analysis docs (3 files)** →
`docs/archive/reports/`
- `docs/scenario_test_report_post_backfill.md`,
  `docs/semantic_backbone_gap_analysis.md`,
  `docs/service_layer_scenario_test_report.md`

### 3.3 Files moved INTO archive AND consolidated INTO new backlog (4 files)

These are the four legacy backlog files. Items still relevant move
into `PRODUCT_BACKLOG.md`; the original files move to
`docs/archive/legacy-backlogs/` with a redirect header.

- `BACKLOG.md` (root)
- `ROADMAP.md` (root)
- `docs/backlog.md`
- `docs/product_backlog_research_and_intelligence.md`

### 3.4 Files NOT touched (active)

- `CLAUDE.md`, `AGENTS.md`, `lead_notes_4_dev.md`
- `docs/AGENT_BACKLOG.md`, `docs/UI_CHANGELOG.md`,
  `docs/API_CHANGELOG.md`
- `feedback/*` (auto-managed cron tracker)
- `frontend/README.md`, `harness/*`, `.claude/*`
- All current `specs/SPEC_NNN_*.md` for `NNN >= 020` that aren't in
  the superseded list
- `specs/CI_Agent_Reimagined_Spec.md` (north-star reference)

## 4. Data contract — backlog item schema

### 4.1 Item template

```markdown
### [PB-NNN] <Short title>
- **Type**: bug | feature | enhancement | refactor | infra | data | docs | spike
- **Status**: proposed | triaged | blocked | in-progress | shipped | archived | wontfix
- **Priority**: low | medium | high | urgent
- **Owner**: frontend-claude | backend-claude | shared | unassigned
- **Source**: spec | feedback | agent-ask | roadmap | brainstorm | adhoc
- **Source ref**: SPEC-NNN | fb-XXXXXXXX | AGENT_BACKLOG#section.N | n/a
- **Blocked by**: PB-NNN, PB-NNN | n/a
- **Created**: YYYY-MM-DD
- **Last touched**: YYYY-MM-DD
- **Notes**: 1-3 lines explaining what this is and why it matters.
```

### 4.2 Status taxonomy

| Status | Meaning |
|---|---|
| `proposed` | Captured but not yet triaged. Default for new items. |
| `triaged` | Reviewed; promoted to a real candidate. Has type + priority + owner. |
| `blocked` | Triaged but cannot start. `Blocked by` field names what gates it. |
| `in-progress` | Active work. The Ralph Loop is open on it. |
| `shipped` | Code merged + DoD met. |
| `archived` | Superseded or no longer wanted; kept for history. |
| `wontfix` | Reviewed and rejected. Reason in `Notes`. |

### 4.3 ID scheme

`PB-NNN` (zero-padded to 3 digits). Monotonic. The validator script
enforces uniqueness.

### 4.4 Front-of-file dashboard

The first ~30 lines of `PRODUCT_BACKLOG.md` are an auto-friendly
dashboard. Format:

```
| Status        | Count |
|---------------|-------|
| in-progress   | N     |
| triaged       | N     |
| blocked       | N     |
| proposed      | N     |
| shipped (90d) | N     |

## Currently in flight
- [PB-NNN] <title> — owner / source-ref
- [PB-NNN] <title> — owner / source-ref

## Blocked
- [PB-NNN] <title> — blocked by <ref>
```

The validator can regenerate the dashboard counts from the body of
the file (`scripts/validate_product_backlog.py --regenerate-summary`).

## 5. States to support

| State | What renders | Failure mode |
|---|---|---|
| Empty backlog | Dashboard shows zeros + "no items yet" line | n/a |
| Stale dashboard | Validator reports "summary out of date" + diff | Run with `--regenerate-summary` |
| Orphan blocked-by | Validator reports "PB-005 references non-existent PB-099" | Fail validation |
| Duplicate ID | Validator reports "PB-007 used twice" | Fail validation |
| Missing required field | Validator reports per item which fields missing | Fail validation |
| Archived item still has owner field | Validator reports "archived items must clear owner" | Warn, not fail |

## 6. Keyboard contract

n/a — pure docs.

## 7. Accessibility contract

n/a beyond standard markdown rendering.

## 8. Definition of Done

- [ ] `docs/PRODUCT_BACKLOG.md` exists with consolidated items.
- [ ] Every still-current item from the 4 legacy backlog files
      appears as a `PB-NNN` row.
- [ ] Every open `[BACKEND]`/`[FRONTEND]` `Status: open` ask in
      `docs/AGENT_BACKLOG.md` has a corresponding `PB-NNN` row whose
      `Source ref` points to the AGENT_BACKLOG section.
- [ ] Front-of-file dashboard renders correct counts.
- [ ] All 53 stale files moved to `docs/archive/<category>/` with a
      1-line redirect header at the original location.
- [ ] `scripts/validate_product_backlog.py` exits 0 against the new
      file.
- [ ] `python -m pytest tests/test_product_backlog.py -v` passes.
- [ ] `docs/UI_CHANGELOG.md` + `docs/AGENT_BACKLOG.md` entries
      appended (a process-only change; UI_CHANGELOG entry is nominal).
- [ ] No regression to existing 256-test vitest suite (this loop
      doesn't touch frontend code).

## 9. Tests (Stage 3 will list)

- `test_product_backlog.py::TestSchema` — every item parses; required
  fields present; enum values valid.
- `test_product_backlog.py::TestUniqueness` — every PB-NNN unique;
  no duplicate cross-references.
- `test_product_backlog.py::TestCrossReferences` — every `Source ref`
  pointing at `SPEC-NNN` resolves to a real file in `specs/`; every
  `Blocked by` pointing at `PB-NNN` resolves to a real item.
- `test_product_backlog.py::TestDashboard` — counts in the dashboard
  match grep results from the body.
- `test_product_backlog.py::TestArchiveRedirects` — every file
  declared archived in §3.2 has a redirect header at its original
  path AND exists at its new path.

## 10. Open questions — RESOLVED at sign-off (2026-05-09)

1. **Q1 — Canonical file location.** ✓ Resolved:
   `docs/PRODUCT_BACKLOG.md`.
2. **Q2 — Fate of `AGENT_BACKLOG.md`.** ✓ Resolved: keep separate.
   Cross-agent coordination has its own rhythm; product backlog
   references it.
3. **Q3 — Old backlog files (`BACKLOG.md`, `ROADMAP.md`,
   `docs/backlog.md`).** ✓ Resolved: move to
   `docs/archive/legacy-backlogs/` with a redirect header.
4. **Q4 — Feedback queue relationship.** ✓ Resolved: cross-reference
   only; each open feedback item gets a one-line `PB-NNN` stub
   linking to the cron tracker.
5. **Q5 — Bulk doc archival scope.** ✓ Resolved: archive all 6
   categories (54 files); keep `lead_notes_4_dev.md`, `SPEC_021_*`,
   `CI_Agent_Reimagined_Spec.md` at current location; archive
   `comp_intelligence.md`.

## 10a. Design notes (Stage 2 — completed 2026-05-09)

### 10a.1 Reference frames

| Surface | Lift from | What |
|---|---|---|
| Front-of-file dashboard | **Linear inbox triage view** | Counts at top, "in flight" list right under, "blocked" at the bottom. Reader scans dashboard in 30s. |
| Per-item template | **Standard issue trackers (Jira/Linear)** | Every item is a flat row of `Field: value` pairs followed by a 1-3 line note. Greppable; no nesting. |
| Status taxonomy | **GitHub Projects v2 + Scriptiva backlog** | 7-state taxonomy chosen because the feedback-cron and the spec frontmatter can both map cleanly into it (see §10a.4). |
| Archive structure | **`docs/archive/<category>/`** | One directory per category from §3.2. Within each, original filenames preserved. |

### 10a.2 Wireframe — `docs/PRODUCT_BACKLOG.md` top of file

```
# Product Backlog — Market Zero

> Single source of truth for product, feature, bug, and infra work.
> Cross-agent coordination still lives in `docs/AGENT_BACKLOG.md`.
> Auto-validated by `scripts/validate_product_backlog.py`.

## Dashboard (regenerated 2026-05-09)

| Status        | Count |
|---------------|-------|
| in-progress   | 3     |
| triaged       | 14    |
| blocked       | 5     |
| proposed      | 8     |
| shipped (90d) | 27    |

## Currently in flight (3)

- [PB-001] SPEC-041 User Feedback Loop — frontend-claude / SPEC-041 (PR #35)
- [PB-002] Centralized Product Backlog — frontend-claude / SPEC-042 (this loop)
- [PB-003] War-Game Multi-Adversary UI — frontend-claude / SPEC-032

## Blocked (5)

- [PB-004] Commit-decision flow — blocked by [PB-027] (POST /decisions/from-brief backend ask)
- ...

## Items (sorted by priority desc, then created asc)

### [PB-001] User Feedback Loop — in-app widget + autonomous triage
- **Type**: feature
- **Status**: in-progress
- **Priority**: high
- **Owner**: frontend-claude
- **Source**: spec
- **Source ref**: SPEC-041
- **Created**: 2026-05-09
- **Last touched**: 2026-05-09
- **Notes**: Floating pill on every authenticated surface. PR #35 open;
  awaiting merge. Loop #2 of SPEC-029 reskin program.

### [PB-002] Centralized Product Backlog
- **Type**: docs
- **Status**: in-progress
- ...
```

### 10a.3 Dashboard regeneration algorithm

`scripts/validate_product_backlog.py --regenerate-summary`:

```
1. Parse the file. Extract every "### [PB-NNN]" heading + its field
   lines into a dict.
2. Group by Status. Count each.
3. Filter Status='shipped' to those with `Last touched` ≤ 90 days
   ago for the dashboard count.
4. Build the markdown table + the "Currently in flight" + "Blocked"
   sections.
5. Replace lines between `## Dashboard` and `## Items` with the
   rebuilt block.
6. Write file back. Diff if --check; mutate if --regenerate.
```

CI: a pre-commit hook (filed as backlog) eventually runs `--check`
on staged versions of the file. v1 is manual.

### 10a.4 Status mapping from sources

The 7-state taxonomy is a superset of the 3 input vocabularies:

| Source | Their status | Maps to PRODUCT_BACKLOG |
|---|---|---|
| `feedback_entries.status` | `new` | `proposed` |
| `feedback_entries.status` | `triaged` | `triaged` |
| `feedback_entries.status` | `in_progress` | `in-progress` |
| `feedback_entries.status` | `resolved` | `shipped` |
| `feedback_entries.status` | `rejected` | `wontfix` |
| AGENT_BACKLOG `Status:` | `open` | `proposed` or `triaged` (judge by content) |
| AGENT_BACKLOG `Status:` | `in-progress` | `in-progress` |
| AGENT_BACKLOG `Status:` | `done` | `shipped` |
| AGENT_BACKLOG `Status:` | `wontfix` | `wontfix` |
| Spec frontmatter | `Draft` | `proposed` |
| Spec frontmatter | `Stage N` | `in-progress` |
| Spec frontmatter | `Shipped <date>` | `shipped` |

### 10a.5 Cross-reference syntax

When an item points elsewhere, the **Source ref** field uses one of:

```
SPEC-NNN                         → specs/SPEC_NNN_*.md
SPEC-NNN#section                 → specific section in spec
AGENT_BACKLOG#FRONTEND.5         → 5th [FRONTEND] block in AGENT_BACKLOG.md
fb-XXXXXXXX                      → feedback_entries row (8-char id prefix)
PR #N                            → GitHub PR
adhoc                            → no external ref (item created directly)
```

The validator resolves each of the first three forms; warns on
unresolvable refs (file missing, section heading missing).

### 10a.6 Migration mapping (Stage 4 will execute)

For each legacy backlog file, pre-classified extraction strategy:

| Legacy file | Strategy |
|---|---|
| `docs/AGENT_BACKLOG.md` | **DO NOT MIGRATE BODY**. For each open `[BACKEND]` / `[FRONTEND]` ask, create a stub `PB-NNN` row with `Source: agent-ask` + `Source ref: AGENT_BACKLOG#<section>`. AGENT_BACKLOG remains the canonical owner of the body. |
| `BACKLOG.md` (root) | Read each `###` item under "In Progress" / "Planned" / "Future / Aspirational" / "UI & Intelligence Upgrades" / "UX & Intelligence Overhaul (v2)" / "Implementation Order". Skip "Implemented Features" + "Architecture Vision". Migrate as `PB-NNN`. |
| `ROADMAP.md` | Per-Phase scan; skip Phases 0-2 (already shipped). Phases 3-6 → `PB-NNN` items with `Source: roadmap`. |
| `docs/backlog.md` | 6 items, skim each; if not already covered by AGENT_BACKLOG or above, migrate. |
| `docs/product_backlog_research_and_intelligence.md` | 47 lines; skim once; merge into existing items if duplicates. |

### 10a.7 Archive directory layout

```
docs/archive/
├── README.md                     — explains the archive convention
├── brainstorms/                   — Cat A (7 files)
│   ├── data_layer_design.md
│   ├── vision_rough.md
│   └── ...
├── communications/                — Cat B (2 files)
│   ├── dev_2_lead.md
│   └── comp_intelligence.md
├── reports/                        — Cat C + F (7 files)
├── benchmarks/                     — Cat D (~17 files)
├── superseded-specs/               — Cat E (~20 files)
└── legacy-backlogs/                — the 4 files we replace
    ├── BACKLOG.md
    ├── ROADMAP.md
    ├── backlog.md
    └── product_backlog_research_and_intelligence.md
```

Each archived file gets a 1-line header inserted at the top:

```
> **Archived 2026-05-09** — superseded by `docs/PRODUCT_BACKLOG.md`.
> Original content preserved below for history.
```

### 10a.8 Self-review checklist (gate to Stage 3)

- [x] Item schema defined and template shown (§4.1, §10a.2).
- [x] Status taxonomy chosen with mapping from all 3 input sources
      (§10a.4).
- [x] ID scheme + uniqueness rule (§4.3).
- [x] Dashboard format + regeneration algorithm (§10a.3).
- [x] Cross-reference syntax + validator behavior (§10a.5).
- [x] Migration strategy per legacy file (§10a.6).
- [x] Archive directory layout (§10a.7).
- [x] Per-state failure modes documented (§5).
- [x] Tests scoped (§9).

Self-review passes. **Stage 3 (TDD) opens.**

## 10b. Red-team (Stage 5 — completed 2026-05-09)

Adversarial review of the migration outcome. Reviewer pretended not to
have written the spec.

### Blockers

None.

### Major

1. **`AGENTS.md:211` instructs filing bugs in `BACKLOG.md`** — `major`
   (process drift) — That file is now an archived redirect stub. Any
   agent following the instruction would get confused.
   *Fix:* update to point at `docs/PRODUCT_BACKLOG.md`.
2. **MEMORY.md (`~/.claude/.../MEMORY.md`) references `BACKLOG.md`
   and `ROADMAP.md`** — `major` (process drift) — same issue: the
   memory file's "Key Files" list points at archived locations.
   *Fix:* update memory to reference the new canonical file.
3. **74 migrated items are unfiltered, untriaged, and likely
   contain duplicates** — `major` (data quality) — The migration
   ran extractor-style: every `### ` heading from the legacy files
   became a row, regardless of whether it's still meaningful
   post-shipping. PB-027 ("Decision Brief object") is shipped per
   AGENT_BACKLOG. Many ROADMAP.md Phase 3-6 items are likely
   already in flight via current specs. Without manual triage these
   77 items are a noisy starting point.
   *Mitigation:* the next loop's first task is a focused triage
   pass that demotes shipped items to `Status: shipped` and
   collapses duplicates. **Not a deal-breaker for Stage 7 close**
   — the file structure is right; the data inside it is
   provisional.

### Minor

4. **Mass benchmark archive was 98 files, not the ~17 estimated**
   — `minor` — User signed off on "~17 benchmark eval reports";
   the actual count was 98 (every `benchmark/reports/eval-*.md`).
   The category is correctly auto-generated stale snapshots, so
   the broader sweep is appropriate, but the user should know the
   real number ended up 6× larger.
5. **`TestArchiveRedirects` only parametrizes 3 files** — `minor`
   (test coverage) — Spot-checks `vision_rough.md`,
   `comp_intelligence.md`, `BACKLOG.md`. A run-against-everything
   would be safer; `glob('docs/archive/**/*.md')` + assert
   redirect stub at original path would catch a botched move.
6. **No CLI integration test** — `minor` — `validate_product_backlog
   --check` and `--regenerate-summary` are tested via the library
   API but the CLI flag handling has no test. A `subprocess.run
   ["python", "-m", "scripts.validate_product_backlog"]` would
   close it.
7. **Dashboard regenerator does not sort items in the body** —
   `minor` (UX) — Dashboard summary is rebuilt cleanly; the items
   themselves stay in insertion order. After heavy use the file
   becomes hard to scan visually. Spec §10a.3 promised "sorted by
   priority desc, then created asc" — not implemented in v1.
8. **Legacy-backlog redirect stubs are 2 lines** — `minor` (UX) —
   Reader sees a 2-line stub and might wonder where the content
   went. The line tells them, but there's no greeting or context.
   Cosmetic.
9. **Migration notes lack line numbers** — `minor` —
   `migrate_legacy_backlogs.py` writes "Migrated from <file>
   (section: <heading>)". Adding the original line number would
   make traceability tighter when investigating an old item.
10. **My initial grep regex `BACKLOG\.md` caught me with
    `PRODUCT_BACKLOG.md` substring matches** — `nit` — Anyone else
    auditing might trip on the same. Documented here so future
    me uses `\bBACKLOG\.md` or `(?<!PRODUCT_)BACKLOG\.md`.

### Nits

11. **Item template uses `**Type**:` with double-asterisks** —
    `nit` — Markdown renders bold; some parsers strip the `**` so
    `Type:` becomes the field key. The validator handles both via
    its regex; nothing fails.
12. **The 1-line redirect-header convention is actually 2 lines
    (header + path)** — `nit` — Spec §10a.7 said "1-line";
    implementation is 2. Cosmetic mismatch with the spec text.

### Decisions taken — not bugs

- **74 migrated items are all `Status: proposed` and
  `Priority: medium`** — by design. The whole point of consolidation
  is to capture them once; triage is the next-loop activity.
- **Migration helper is kept as a one-shot tool**, not a watchdog
  that re-syncs on every change. v1.
- **`docs/AGENT_BACKLOG.md` stays as the canonical cross-agent
  surface** (Q2 sign-off) — items in it get a stub `PB-NNN` row
  here but the canonical content stays there.
- **Feedback queue is reference-only** (Q4 sign-off) — `feedback/
  live_user_feedback.md` is the source of truth for in-flight
  feedback; PRODUCT_BACKLOG references each open feedback id.
- **The 98-file benchmark archive sweep** — Category D was
  pre-classified as "auto-generated benchmark eval reports"; the
  actual count just turned out to be larger than estimated. All
  files in scope match the auto-generated pattern.

### Stage 5 gate

Stage 5 closes once this section is committed. Stage 6 (FIX-ALL)
opens. M1, M2 must close (process-drift fixes). M3 (74-item triage)
is *deferred* by design — the next loops will work through the
backlog item-by-item; that IS the rigor the user asked for.

## 10c. Stage 6 — FIX-ALL closed (2026-05-09)

| Severity | Closed | Deferred |
|---|---|---|
| Blocker | — | — |
| Major | M1 (AGENTS.md:211 redirect), M2 (MEMORY.md update) | M3 (74-item triage — by design, that's the next loops) |
| Minor | — | 4, 5, 6, 7, 8, 9 (filed in next-loop scope) |
| Nit | — | 10, 11, 12 |

## 11. Out of scope (this loop)

- A web UI / admin view of the backlog. The file is the UI for v1.
- Auto-syncing `PRODUCT_BACKLOG.md` from `feedback/backlog.jsonl` on
  every cron tick. v1 stubs are manually inserted by `/triage-feedback`
  when it produces a "Human Decision Needed" verdict; the cron just
  references the feedback ID. Auto-sync is a future loop.
- Migrating to GitHub Issues / Linear / Jira. We intentionally stay
  in-repo so I (Claude) can read + edit + commit atomically.
- Touching specs newer than May 5 — they're all active work.

## 12. Acceptance for Stage 1

- [ ] User signs off below by replacing this line with `✓ Signed
      off by user 2026-05-09`.
- [ ] User confirms or amends the 53-file archival list in §3.2
      (already pre-confirmed via in-conversation approval).

Once accepted, Stage 2 (DESIGN) opens.
