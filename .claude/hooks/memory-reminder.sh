#!/usr/bin/env bash
# Stop hook — advisory memory-staleness reminder.
#
# Fires when Claude stops. If the latest git commit is NEWER than the most
# recently-updated memory file, it means work shipped without the resume
# pointer being updated — so it emits a systemMessage nudge. Non-blocking:
# never prevents stopping, never loops. Just surfaces the reminder.
#
# Wired from .claude/settings.json -> hooks.Stop. Edit/disable via /hooks.
set -uo pipefail

REPO="C:/Users/kapil/Documents/market_zero"
MEM_DIR="C:/Users/kapil/.claude/projects/C--Users-kapil-Documents-market-zero/memory"

# Latest commit time (epoch); 0 if unavailable.
commit_ts="$(git -C "$REPO" log -1 --format=%ct 2>/dev/null || echo 0)"
[ -z "$commit_ts" ] && commit_ts=0

# Newest mtime across the memory index + the active resume-state file.
mem_ts=0
for f in "$MEM_DIR/MEMORY.md" "$MEM_DIR/project_dossier_kb_and_intel_diagnosis.md"; do
  if [ -f "$f" ]; then
    t="$(stat -c %Y "$f" 2>/dev/null || echo 0)"
    [ "$t" -gt "$mem_ts" ] && mem_ts="$t"
  fi
done

# Only nudge when commits are strictly newer than memory.
if [ "$commit_ts" -gt "$mem_ts" ]; then
  printf '%s' '{"systemMessage":"⚠ Memory may be stale — the latest git commit is newer than your memory resume pointer. Before ending, update MEMORY.md (the ACTIVE RESUME POINT) and the relevant project_*.md state file so a future session can resume from where this one stopped."}'
fi
exit 0
