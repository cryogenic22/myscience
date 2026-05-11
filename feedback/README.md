# `feedback/` — SPEC_041 user feedback loop

Everything an operator needs to know about the in-app feedback widget,
the Claude-driven triage flow, and the 45-minute cron.

## Files in this directory

| File | Purpose |
|---|---|
| `live_user_feedback.md` | Append-only human-readable tracker. Cron + slash commands write here. **Do not edit by hand** unless you're closing an item manually. |
| `backlog.jsonl` | Machine-readable mirror of the queue (one JSON per line). Source of truth for the slash commands. |
| `sync.sh` | Pulls `GET /feedback?status=new` and appends to both files above. Idempotent (dedup by id). |
| `.gitignore` | Ignores screenshots/* + .paused. |
| `.paused` (optional) | If this file exists, the cron skips its tick. `touch feedback/.paused` to pause; delete to resume. |

## How a feedback item travels through the system

```
 user submits via FeedbackWidget on /ci, /workspace, /search, /catalog…
        │
        ▼
 POST /feedback   →   feedback_entries (DB, status='new')
        │                          │
        │                          └─► services/steward_signals.py::collect_signals
        │                                routes data_quality / data_request to
        │                                the Data Steward queue (auto-resolution
        │                                may flip status='resolved' + resolved_by='steward')
        ▼
 cron (every 45 min)  →  bash feedback/sync.sh
        │
        ▼
 .claude/commands/feedback-cron.md  (slash command Claude runs)
        │
        ├─► /triage-feedback (assessment only — no code changes)
        │   updates each new entry's status to 'triaged' + writes a
        │   Jira-style assessment to live_user_feedback.md
        │
        └─► /process-feedback (Ralph Loop — only auto-fix-safe items)
            Q2 sign-off gate: category=bug && scope_estimate=S &&
            labels excludes [api, schema, auth, security].
            Anything else stays 'triaged' for human-driven processing.
```

## Slash commands

- `/triage-feedback` — assessment only. Reads new entries, classifies
  them, updates status to `triaged`, writes to the tracker. **Never
  changes code.**
- `/process-feedback` — full Ralph Loop on every `Implement` item.
  Used by humans for ad-hoc clearing.
- `/feedback-cron` — entry point the cron calls. Runs sync, then
  triage, then auto-fixes only the safe-classified items.

## Setting up the cron (per-user, per-machine)

The cron itself lives outside this repo. Use the `schedule` skill once:

```
/schedule --every 45m --command /feedback-cron --reason "user feedback loop"
```

This registers a remote agent in `~/.claude/schedules/`. Pause it via
`touch feedback/.paused && git commit -am 'chore: pause feedback cron'`
or via the schedule skill's pause helper.

## Auto-fix safety gate

The cron is autonomous — it can ship code without you in the loop. The
gate (Q2 sign-off, SPEC_041 §8.1):

```
verdict == 'Implement'
&& category == 'bug'
&& scope_estimate == 'S'      (≤3 files, ≤3 hours)
&& labels excludes any of: api, schema, auth, security
```

Anything failing the gate stays `triaged` and waits for a human to type
`/process-feedback`. The cron also commits each auto-fix under
`chore(feedback-cron): <n> items` so you can audit + revert if needed.
