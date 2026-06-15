#!/usr/bin/env bash
# Stop hook — conservation-gates turn review.
#
# Fix for the infinite re-block loop: a prompt-type Stop hook cannot read
# `stop_hook_active`, so it re-injected the review on EVERY turn-end and never
# knew it had already fired — blocking the stop until the 9x cap kicked in.
# This command-type hook honors `stop_hook_active`: it asks for the review ONCE
# per turn, then allows the stop instead of re-blocking forever.

# `stop_hook_active` is true only when this hook is re-firing because of its own
# prior block this turn. If so, the review already happened — allow the stop.
ACTIVE=$(python -c "import sys, json
try:
    print('1' if json.load(sys.stdin).get('stop_hook_active') else '0')
except Exception:
    print('0')" 2>/dev/null)

if [ "$ACTIVE" = "1" ]; then
  exit 0   # already reviewed this turn -> allow the stop (this breaks the loop)
fi

# First stop of the turn -> request the conservation review once. Exit code 2
# feeds this stderr back to the model as the reason it cannot stop yet.
cat >&2 <<'REVIEW'
Review THIS TURN's changes against the conservation/anti-regression rules (.claude/rules/conservation-gates.md). Flag each issue with its tag; if clean, reply exactly 'Turn review: clean.' If this turn made NO code/test/gate changes (e.g. analysis, spawning subagents, waiting on background tasks), reply exactly 'Turn review: clean.' — there is nothing to review.

1. SILENT DATA LOSS: did any resolve/consolidate/compress/coerce path drop rows, fields, or provenance without recording it (soft-delete, dropped-manifest, or a logged count)? Flag [SILENT-LOSS].
2. CODE/TEST DELETION: was existing code, a test, or an assertion deleted, weakened, skipped, or xfail'd that the user did not request? Flag [TEST-WEAKENED] / [REGRESSION-RISK].
3. MOVED THE BAR: was a gate threshold, freshness SLA, orphan ceiling, eval gold set, or schema floor edited to make work pass (vs. genuinely improved)? Flag [BAR-MOVED] — protected-surface; route through the owner.
4. VACUOUS GREEN: was any gate made to pass by checking nothing (empty suite, all-skipped, typecheck of 0 files, tolerated-error allowance with no expiry)? Flag [VACUOUS-GREEN].
5. UNGROUNDED CLAIM: is any number / 'done' / 'verified' stated without pasted evidence (a query result, test output, or probe)? Flag [UNGROUNDED].
6. SILENT CATCH: any new bare 'except:' / 'except Exception: pass' that hides a failure? Flag [SILENT-CATCH].
REVIEW
exit 2
