---
description: Triage new user feedback (assessment only — no code changes)
---

# /triage-feedback — assessment only

You are acting as a **seasoned Product Analyst + PM** for Market Zero.
Read every entry in `feedback/backlog.jsonl` whose `status === 'new'`,
verify each is real, classify it, update its status to `triaged` via
`PATCH /feedback/{id}`, and append a Jira-style assessment block to
`feedback/live_user_feedback.md`.

**Do NOT change any source files in this command.** Implementation
happens in `/process-feedback`. This command is read-only on the
codebase + write-only on the queue.

## Step 1 — sync the queue

Run `bash feedback/sync.sh`. It hits `GET /feedback?status=new`,
appends new rows to `backlog.jsonl`, appends a header to
`live_user_feedback.md`. If it reports 0 new entries, exit cleanly.

## Step 2 — for EACH new entry, MANDATORY pre-checks

For each new feedback row in `backlog.jsonl`:

1. **Has it already been fixed?** Run `git log --oneline -30 -- <files
   the user mentioned>`. If a recent commit clearly addresses it,
   PATCH status='resolved' + resolved_by='already-fixed' + resolution
   referencing the SHA. Stop processing this item.
2. **Is it a duplicate?** grep `feedback/backlog.jsonl` for similar
   titles. If a near-duplicate is already `triaged` or beyond, PATCH
   status='resolved' + resolved_by='duplicate' + resolution
   referencing the original id. Stop.
3. **Can you reproduce from the code?** Read the source files for
   the page/route the user mentioned. Confirm the issue exists. If
   the code does not have the reported problem, mark
   verdict='Needs Manual Verification' and continue without
   speculating.

## Step 3 — write the assessment

For verified entries, append to `feedback/live_user_feedback.md`:

```
### [<id-short>] <title>
- **Type**: bug | issue | enhancement | feature | data_quality | data_request
- **Priority**: low | medium | high | critical
- **Verdict**: Implement | Human Decision Needed | Out of Scope | Already fixed
- **Auto-fix-safe?**: yes (bug + scope=S + labels excludes api/schema/auth/security) | no
- **Labels**: [ui, decisions, signals, ...]
- **Description (rewritten)**: 2-3 sentences in PM voice
- **Acceptance criteria**: 2-4 testable bullets
- **Scope estimate**: S (≤3 files) | M (4-10) | L (11+)
- **Files likely touched**: list
- **Rationale**: why this verdict, aligned with product?
```

Then `PATCH /feedback/<id>` with `{ "status": "triaged" }`.

## Step 4 — final report

Print a summary table:

```
| ID  | Cat | Pri | Title | Verdict | Auto-fix-safe? |
|-----|-----|-----|-------|---------|-----------------|
| ... | ... | ... |  ...  |   ...   |       ...       |
```

## Verdict criteria

- **Implement** — Bugs in shipped code. Data integrity. Missing error
  handling that crashes. Documented gaps in shipped specs.
- **Human Decision Needed** — Feature direction shifts. UX overhauls
  spanning >5 files. New backend dependencies. Anything ambiguous.
  Anything that would change a sign-off in an existing spec.
- **Out of Scope** — Tech-stack changes. Cosmetic-only without
  functional impact. Requests that contradict a shipped spec's
  explicit Q-resolved sign-off.
- **Already fixed / Duplicate** — see Step 2.

## Auto-fix-safe gate (SPEC_041 §8.1, Q2 sign-off)

Mark `Auto-fix-safe? yes` ONLY when ALL of:
- verdict === 'Implement'
- category === 'bug'
- scope_estimate === 'S'
- labels does NOT include any of: `api`, `schema`, `auth`, `security`

Otherwise `no`. The cron uses this flag to decide what to ship without
human review.

## Important rules

- You may run `git log` / `Read` / `Grep` / `Glob` / `Bash` for
  inspection but you may NOT call `Edit`, `Write`, or any code-changing
  tool in this command.
- One feedback item = one assessment block. If a single submission
  contains multiple distinct asks, file each as its own assessment
  with `Verdict: Human Decision Needed — split into NEW entries` and
  list the suggested new entries.
- Always include the assessment block in `live_user_feedback.md`
  BEFORE the PATCH so a partial run still leaves the tracker honest.
- If the API at `$MZ_API_BASE` is unreachable, exit cleanly without
  modifying any tracker file.
