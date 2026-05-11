#!/usr/bin/env bash
# =============================================================================
# SPEC_041 — feedback sync helper
# Pulls all status='new' entries from /feedback?status=new and:
#   1. Appends each to feedback/backlog.jsonl (append-only, dedup by id).
#   2. Appends a per-tick block to feedback/live_user_feedback.md so the
#      tracker stays human-readable.
# Used by:
#   - /feedback-cron (every 45 min, autonomous)
#   - /triage-feedback (assessment only, on demand)
#   - /process-feedback (full Ralph Loop, on demand)
# =============================================================================

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Pause switch — touch feedback/.paused to skip a tick.
if [[ -f feedback/.paused ]]; then
  echo "feedback/sync.sh: paused (feedback/.paused exists). skipping."
  exit 0
fi

API_BASE="${MZ_API_BASE:-http://localhost:8020}"
TIMESTAMP="$(date -u +'%Y-%m-%dT%H:%MZ')"

# Pull the new items
RESPONSE="$(curl -fsS "${API_BASE}/feedback?status=new&limit=100" 2>/dev/null || echo '')"
if [[ -z "$RESPONSE" ]]; then
  echo "feedback/sync.sh: API unreachable at ${API_BASE} — skipping tick."
  exit 0
fi

NEW_COUNT="$(echo "$RESPONSE" | python -c 'import json,sys; print(len(json.load(sys.stdin).get("items",[])))' 2>/dev/null || echo 0)"

if [[ "$NEW_COUNT" == "0" ]]; then
  echo "feedback/sync.sh: 0 new entries at ${TIMESTAMP}"
  exit 0
fi

# Append to backlog.jsonl (one row per item, dedup by id)
python - "$RESPONSE" <<'PY'
import json
import os
import sys

resp = json.loads(sys.argv[1])
items = resp.get("items", [])

backlog_path = "feedback/backlog.jsonl"
existing_ids = set()
if os.path.exists(backlog_path):
    with open(backlog_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                existing_ids.add(json.loads(line).get("id"))
            except Exception:
                pass

added = 0
with open(backlog_path, "a", encoding="utf-8") as f:
    for it in items:
        if it.get("id") in existing_ids:
            continue
        f.write(json.dumps(it) + "\n")
        added += 1

print(f"feedback/sync.sh: appended {added} new entries to backlog.jsonl")
PY

# Append the tracker block
python - "$RESPONSE" "$TIMESTAMP" <<'PY'
import json
import sys

resp = json.loads(sys.argv[1])
items = resp.get("items", [])
ts = sys.argv[2]

lines = [
    "",
    f"## {ts} — sync (cron)",
    "",
    f"{len(items)} new submissions pulled.",
    "",
    "### New entries",
    "",
]
for it in items:
    short = it["id"][:8]
    cat = it.get("category", "?")
    page = it.get("page_url") or "(no page)"
    pri = it.get("priority", "medium")
    title = it.get("title") or "(no title)"
    lines.append(f"- [`{short}`] **{cat}** · `{page}` · _{pri}_ — \"{title}\"")
lines.append("")

with open("feedback/live_user_feedback.md", "a", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"feedback/sync.sh: appended {len(items)} entries to live_user_feedback.md")
PY
