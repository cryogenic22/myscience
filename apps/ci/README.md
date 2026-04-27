# @mz/ci — Competitive Intelligence module

The CI analyst's surface: digest, signal detail, watchlist, alerts, reviewer queue. Phase 1.5 adds briefs, trackers, connector health.

## Develop

```bash
pnpm install
pnpm --filter @mz/ci dev    # http://localhost:5174
```

## Status

**Phase 0 / M0 skeleton.** Sidebar + TopBar + DailyDigest with mock signals. Other surfaces are placeholder cards.

Phase 1 sprint sequence (see SPEC-016 §7 swimlane C):
- C2: SignalCard / EvidenceStack / ScoreTile / TimeRangeSelector + signals API hook
- C3: DailyDigest with real data + keyboard triage
- C4: SignalDetail with evidence stack, conflict view, historical strip, peer strip
- C5: Watchlist Manager
- C6: Reviewer Queue
- C7: Alert Center
- C8: Polish + a11y audit + Research module visual refresh

## Module identity

Set on `<html>` via `data-module="ci"` so `--mz-color-accent` resolves to CI blue. Per SPEC-016 §4.3.
