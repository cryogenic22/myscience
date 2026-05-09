---
description: 45-min cron entry point — sync queue, triage, auto-fix safe items
---

# /feedback-cron — autonomous tick

Entry point the `schedule` skill calls every 45 minutes. SPEC_041 §8.1.

## What this run does

1. **Pause check** — if `feedback/.paused` exists, log
   `chore(feedback-cron): paused` and exit. No further work.
2. **Sync** — run `bash feedback/sync.sh`. If it reports
   "0 new entries" AND there are no `triaged + Auto-fix-safe`
   carryovers from previous ticks, log
   `chore(feedback-cron): empty queue` and exit.
3. **Triage** — run `/triage-feedback` against `status='new'` rows.
   Each gets a Jira-style assessment with `Auto-fix-safe?` flag.
4. **Auto-fix** — run `/process-feedback` in **cron mode** so it only
   touches `Auto-fix-safe? yes` items. Other items stay `triaged`
   for the next human-driven `/process-feedback` invocation.
5. **Push** — `git push` after each commit. The cron commits
   individually under `chore(feedback-cron): ...` for auditability.
6. **Report** — append a final block to `feedback/live_user_feedback.md`:

```
## <ts> — cron tick complete
- Synced: <n> new
- Triaged: <n>
- Auto-fixed: <n> (commits <sha-1>, <sha-2>, …)
- Awaiting human: <n>
- Already-resolved by steward: <n>
```

## Failure modes the cron must tolerate

- **API unreachable** → `sync.sh` exits 0 with a message; cron logs
  and exits.
- **Test suite breaks during a fix** → `/process-feedback` reverts
  the commit and PATCHes the item `status='rejected'`. Do not retry
  in the same tick.
- **A test takes >120s** → kill it; PATCH `status='rejected'` with
  resolution citing the timeout; the next human can pick it up.
- **Merge conflict on push** → `git pull --rebase` once; if conflicts
  remain, abort the rebase, leave the items `triaged`, exit with
  `chore(feedback-cron): rebase conflict — human needed`.

## Important rules

- The cron has commit + push privileges. Treat them seriously: every
  commit is conventional + signed by the cron's prefix
  `chore(feedback-cron): ...` so a human can `git revert` quickly if
  they don't agree with a change.
- Never run two cron ticks concurrently. The schedule skill should
  enforce this, but if you detect a `feedback/.cron-lock` file exists
  with a timestamp <90 minutes old, exit.
- Maximum 5 auto-fix items per tick, even if more are eligible. Keeps
  blast radius small and gives humans space to react.
- After 3 consecutive ticks with `chore(feedback-cron): empty queue`,
  stay quiet — don't spam the tracker with "still empty" headers.
