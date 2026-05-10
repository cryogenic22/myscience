# Live user feedback — Market Zero

Append-only chronological tracker of all user feedback submissions.
Mirrored from `feedback/backlog.jsonl` by `feedback/sync.sh` on every
cron tick.

Per SPEC_041:

- Each cron tick adds a `## YYYY-MM-DDThh:mmZ — sync (cron)` block.
- Each new entry shows `[id8]` · category · page · priority + title +
  triage verdict.
- Items closed in the same tick (auto-fix-safe) get an "Auto-fixed in
  commit `<sha>`" footer.
- Items routed to the Data Steward (data_quality / data_request) get
  a "→ Auto-routed to Data Steward (steward_action_id: …)" line.
- Items needing human review stay in the queue with
  "Awaiting human" until `/process-feedback` runs.

The slash commands `/triage-feedback`, `/process-feedback`, and
`/feedback-cron` all read from and write to this file.

---

<!-- ENTRIES BELOW — append-only -->
