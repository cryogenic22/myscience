# Repository Inventory — SPEC_HANDOFF_001 · H0.1 (hardened, on canonical baseline · 2026-08-13)

**Non-destructive census.** Nothing was moved, deleted, closed, merged, or pruned to produce
this document. It classifies every delivery object with a **proposed** disposition for owner
review in H0.2. This is the **hardened** revision: full 64-char SHA-256 artifact hashes, full
40-char Git SHAs, an all-branches disposition manifest, and a tested preservation set.

Companion files (this directory, on the baseline):
- [`BRANCH_DISPOSITION.csv`](BRANCH_DISPOSITION.csv) — **all 312 local branches** (full SHA).
- [`WORKTREE_DISPOSITION.csv`](WORKTREE_DISPOSITION.csv) — 79 worktrees (full HEAD SHA).
- [`PR_DISPOSITION.md`](PR_DISPOSITION.md) — 41 open PRs.
- [`UNTRACKED_ARTIFACT_MANIFEST.csv`](UNTRACKED_ARTIFACT_MANIFEST.csv) — 97 files, full SHA-256.
- [`PRESERVATION_MANIFEST.csv`](PRESERVATION_MANIFEST.csv) + [`PRESERVATION_README.md`](PRESERVATION_README.md) — bundles/patches/archives + tested restore.

---

## 1. Canonical baseline (selected & created)

Per the owner decision (2026-08-13), the canonical integration baseline is a **fresh clean
worktree from `origin/main`** — created this session:

| Field | Value |
|---|---|
| Baseline worktree | `C:/Users/kapil/Documents/mz-handoff-baseline` |
| Baseline branch | `claude/handoff/h0-baseline` (based on `origin/main` only — **no #318 ctx-hooks ancestry**) |
| Baseline HEAD | `31d923a712bdcd7611b885f438c858747960b0c2` (== `origin/main`, **0 divergence**) |
| origin/main tip | `31d923a` — 2026-07-04 17:53 +0100 (PR #312). **No PR merged in ~40d.** |
| Migrations on baseline | up to `099_source_onboarding_contract.sql` |
| Deployment SHA | assumed = `origin/main` `31d923a` (Railway auto-deploys `main`); **owner to confirm in Railway** |
| Tags | 2 — `v2.0.0`, `v2.0.1` |

The prior local checkout (`claude/chore/ctxpack-session-memory-hooks`@`38889b5`) is a **stale
offshoot, 37 commits behind `origin/main`**; it is **not** the baseline. The earlier
`claude/handoff/h0-repository-transfer` branch (holding the first-pass board + inventory) is
**superseded** by this baseline and will be retired once the baseline commit is verified — its
content was 3-way re-reconciled here; it is **not** to be opened as a PR (owner ruling).

---

## 2. Board reconciliation (H0.3 planning-truth — done on the baseline)

`origin/main`'s coordination docs were **~2 months stale** and diverged from the local
governance in **both** directions. A proper **3-way merge** (base = merge-base `6f30f55`)
reconciled them onto the baseline:

- **origin/main was missing** COORDINATION §9 (security red-team), §10 (2-team model),
  §11 (data-platform program), §12 (handoff program), and **all PRODUCT_BACKLOG P0 sections**.
  These owner-ratified governance edits lived only on unmerged local branches → ported forward.
- **origin/main had newer content** the local branch lacked: migration registry `097–100`,
  a `clinical_trials.start_date` recency ASK, PRODUCT_BACKLOG `E11`, and a newer **CLAUDE.md**
  (ConversationMemory documented as *wired*, not "not yet wired") → preserved.
- **One collision resolved:** two different ASKs were both numbered **A4** on divergent
  branches (SEC-002 tenant vs `start_date` recency). Kept the tenant ASK as **A4** (referenced
  throughout §9/§10); renumbered the recency ASK → **A6** with an inline note.
- Result on baseline: COORDINATION §1–§12 coherent (ASKs A1–A6); PRODUCT_BACKLOG all 3 P0
  sections + E11. Backlog validator: **`OK`**.

**Also ported (were untracked drafts, now present on baseline):** `SPEC_HANDOFF_001`,
`SPEC_003`, `WP-0/1/4`, `specs/data_strategy.md` (also never on main), and the two grounding
reviews (`…handoff_readiness_review_2026_08_13.md`, `…data_pipeline_deep_design_review_2026_08_07.md`).
They are committed on the baseline **as drafts** — H0.3 ratification (owner sign-off) is a
separate step; a committed draft is preserved, not ratified.

**Deferred to H0.3:** `CLAUDE.md` — `origin/main`'s version is newer than the CLAUDE.md this
session was launched with (which still said ConversationMemory "not yet wired"). Reconcile the
ctx-hooks section (PR #318 concern) against main's wired version there.

---

## 3. Delivery-object census (counts)

| Object | Count | Breakdown |
|---|---|---|
| Local branches | **312** | 202 merged · 57 on-origin/no-PR · 36 on-origin/open-PR · **13 LOCAL-ONLY (bundle required)** · 4 PROTECT |
| Registered worktrees | **79** | 50 clean · 29 dirty · incl. the new baseline worktree (clean, PROTECT) |
| Open PRs | **41** | 32 MERGEABLE · 9 CONFLICTING · **0 with any review decision** |
| Tracked-mod + untracked artifacts | **97** (6.6 MB) | full-SHA-256 in the manifest; rollup below |

**Artifact disposition rollup** (`UNTRACKED_ARTIFACT_MANIFEST.csv`, full 64-char hashes):

| Disposition | # | Meaning |
|---|---|---|
| PROTECT | 17 | `.claude/ctx/` session-memory ledger + gists — never delete / never in an H0 commit |
| PRESERVE | 35 | raw benchmark/SME eval evidence, review deliverables, prototypes |
| REVIEW | 27 | report HTML / eval fixtures / ad-hoc scripts — classify in H0.2 |
| ARCHIVE-COMMIT | 9 | `docs/archive/reports/*.html` already in the archive dir but untracked |
| RATIFIED-on-baseline | 8 | program specs + grounding reviews — ported+committed to baseline; main-checkout copies are duplicates to remove in H0.2 |
| TRACKED-MOD | 1 | `CLAUDE.md` (ctx-hooks; H0.3 reconcile vs main's newer version) |

---

## 4. Verified drift vs SPEC_HANDOFF_001 / the handoff review

✅ verified this pass · ⏳ deferred to its gate.

| # | Claim | Finding |
|---|---|---|
| D1 | Review baseline `31d923a` | ✅ == `origin/main`. |
| D2 | *(found here)* | ✅ Local checkout is **37 behind** main (stale). Planning-spec code line-refs must delta-verify vs `origin/main` (§H8.1). |
| D3 | "board must not cite an untracked doc as ratified" | ✅ Confirmed — `origin/main`'s board was stale at §8; §9–§12 + all P0 sections + the program specs + `data_strategy.md` were unmerged/untracked. Reconciled + ported this pass (§2). |
| D4 | WP-0: "migration 098 already adds `records_skipped`/`records_failed`" | ✅ Confirmed — `098_etl_runs_skip_visibility.sql` **is on `origin/main`** (baseline has it). WP-0 delta **stands**; do not re-spec those columns. |
| D5 | OpenAPI "381 committed paths" | ✅ `schema/openapi.json` = 381. "518 generated" → ⏳ H3 (needs app run). |
| D6 | "78 worktrees · 41 review-less PRs" | ✅ Confirmed (79 now = +baseline). |
| D7 | SEC-001a/b · PRIV-001 · prod demo-auth · DLQ 1,547 / red sources / 22 stuck runs · FE lint 306 + Rules-of-Hooks · false-`Saved` autosave | ⏳ Verify at their gates (H1 / H2 / H4) against `origin/main`. |
| D8 | *(found here)* | ✅ `.gitignore` globally ignores `*.md`; `docs/handoff/` was **not** whitelisted → handoff evidence files silently un-committable. Fixed on baseline (`!docs/handoff/**/*.md`). |

---

## 5. Preservation ledger (H0.1 hardening — see PRESERVATION_MANIFEST.csv)

Everything at risk of local loss is preserved **before** any H0.2 cleanup:

- **13 LOCAL-ONLY branches** (unique commits on **no** remote) → **Git bundles** (verified).
- **29 dirty worktrees** → binary **staged + unstaged patches** (`git diff --binary`) + a
  **hashed archive of untracked files** per worktree (not a patch alone).
- **Tested restore** — at least one bundle cloned + verified and one patch re-applied in a
  scratch clone; evidence in `PRESERVATION_README.md`.
- **PROTECT (never touched, never in an H0 commit):** the 17 `.claude/ctx/` session-ledger +
  gist files. No `.env`/secret is untracked this pass.
- **202 merged branches** → prune-eligible (0 unique commits); **57 on-origin/no-PR** &
  **36 on-origin/PR** → preserved on the remote (no local bundle needed), review/keep per PR.

**Nothing in this ledger was acted on during H0.1.** Cleanup is H0.2, after owner approval.

---

## 6. Status & next steps

- ✅ **H0.1 complete (hardened):** baseline created; board reconciled; specs ported; inventory
  regenerated with full SHAs/hashes + 312-branch manifest; preservation bundled + tested.
- ⏭ **H0.2 (this deliverable):** a **dry-run** cleanup action list is provided for owner
  sign-off — see `PRESERVATION_README.md` §"H0.2 dry-run". **No cleanup is executed.**
- ⏭ **H1 (in parallel, authorized):** independent review + rebase of **#325 (SEC-001a)** and
  **#326 (PRIV-001)** onto clean `origin/main`; their branches/worktrees are **PROTECT** —
  excluded from H0.2 cleanup.

*Generated 2026-08-13 for SPEC_HANDOFF_001 H0.1 (hardened). Dispositions are proposals pending owner review.*
