---
description: Triage + implement Implement-verdict feedback items via the Ralph Loop
---

# /process-feedback — full Ralph Loop on the feedback queue

You are running the Ralph Loop (`docs/runbooks/RALPH_LOOP.md`)
end-to-end on every `Implement`-verdict feedback item in the queue.
Used by humans for ad-hoc clearing AND by `/feedback-cron` (in
restricted mode — see §"Cron mode" below).

## Step 0 — triage first

Run `/triage-feedback` (or, equivalently, perform Steps 1–3 of
`triage-feedback.md` inline). Skip if the queue is already triaged
fresh enough that no `status='new'` rows remain.

## Step 1 — pick the next item

Pull the next `triaged` row from `feedback/backlog.jsonl` whose
verdict is `Implement`. If none, exit with "Nothing to process."

PATCH `/feedback/<id>` with `{ "status": "in_progress" }` so other
ticks of the cron don't double-pick the same item.

## Step 2 — Ralph Loop on that one item

Run the standard 7 stages on the item, scaled to its scope:

1. **Spec** — for `S` scope items, the spec is just the assessment
   block in `live_user_feedback.md`; no separate `specs/SPEC_NNN_*.md`
   needed unless scope >= `M`.
2. **Design** — only for items that touch a new visible UI surface.
   Bugfixes can skip; refactors must include a one-paragraph design
   note.
3. **TDD** — write the failing test first. Mandatory. The test name
   should be the `id-short` of the feedback item so the linkage is
   obvious.
4. **Build** — minimal change. No scope creep. Re-read existing code
   first; match patterns.
5. **Red-team** — for `S` items a 5-line self-review block in the
   commit message suffices. For `M+` follow the full RALPH_LOOP §5.
6. **Fix-all** — close blockers + majors before commit.
7. **Deploy** — commit + push.

## Step 3 — close the loop

After the commit lands:

1. PATCH `/feedback/<id>` with
   `{ "status": "resolved", "resolved_by": "claude", "resolution":
   "fixed in <commit-sha>; <one-line summary>" }`.
2. Append to `feedback/live_user_feedback.md` under the next
   "Closed in this run" subheading:
   ```
   - [`<id-short>`] resolved in <sha>; files: <list>; tests added: <n>
   ```
3. If the item was `data_quality` / `data_request` and the steward
   already auto-resolved it, the PATCH is a no-op (status will
   already be `resolved`). Don't fight the steward — just log it.

## Step 4 — repeat

Loop back to Step 1 until there are no more `triaged + Implement`
rows. Then print:

```
## /process-feedback report
| ID | Title | Result | Commit |
|----|-------|--------|--------|
| .. |  ..   |  ..    |  ..    |
```

## Cron mode

When this command is invoked from `/feedback-cron`, restrict the
items processed to those whose triage marked them `Auto-fix-safe? yes`
per SPEC_041 §8.1 (Q2 sign-off):

```
verdict === 'Implement'
&& category === 'bug'
&& scope_estimate === 'S'
&& labels does NOT include any of: api, schema, auth, security
```

Anything outside that gate is left at status `triaged` so a human
running `/process-feedback` directly will pick it up.

Cron-mode commits are tagged `chore(feedback-cron): <id-short> <title>`.
The cron also pushes after each item so the audit trail is durable.

## Important rules

- One feedback item = one commit. No batching. (Cron mode commits
  individually so you can revert any single auto-fix.)
- TDD is non-negotiable — every fix needs at least one regression
  test that fails before the fix and passes after.
- Match existing patterns. Read 2–3 sibling files before writing.
- If the fix would touch a file labeled `api/`, `schema/migrations/`,
  `services/auth.py`, or anything under `auth`/`security`/`crypto`
  paths AND you're in cron mode, abort the item and leave a comment
  on the tracker: "out of cron auto-fix gate, awaiting human".
- Never bypass the test gate. If `npx vitest run --no-file-parallelism`
  doesn't exit 0 after your fix, REVERT and mark the item
  `status='rejected'` with `resolution='auto-fix attempt failed
  tests, see commit <sha> for details'`.
