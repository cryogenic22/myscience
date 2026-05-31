# ctxpack Usage Log

*Append-only. One row per ctx call (or batch). Used to compute real token-savings benchmarks over time. See `docs/ctx-protocol.md`.*

## Pack-version history

| Date | Branch | HEAD | pack_version (first 16) | files | entities | trigger |
|---|---|---|---|---|---|---|
| 2026-05-30 | (pre-refresh) | n/a | `c48d5dbdf52e3596` | 764 | 9600 | session probe — stale |
| 2026-05-30 | `claude/frontend-f4-engagement-page` | `ecb19a9` | `18b8255cc3c4f7a0` | 782 | 9805 | post-refresh; reflects F4 working tree |

## Per-call log

Format: `date | task | call | bytes_returned | full_read_alternative_bytes | savings_pct | notes`

| Date | Task | Call | ret_b | alt_b | savings | notes |
|---|---|---|---|---|---|---|
| 2026-05-30 | Benchmark seed | `hydrate(signal_promoter::classify_kbq, d=0)` | 580 | 14279 | 96% | F4 branch · pack `18b8255c` |
| 2026-05-30 | Benchmark seed | `hydrate(facts_ledger::assert_fact, d=0)` | 1750 | 6231 | 72% | F4 branch · pack `18b8255c` |
| 2026-05-30 | Benchmark seed | `hydrate(facts_ledger::_valid_at, d=1)` | 3500 | 11000 | 68% | depth=1 incl. callers + 1 callee · cross-file |

## Aggregate (running)

| Window | hydrate calls | search calls | list calls | bytes_saved | savings_pct |
|---|---|---|---|---|---|
| 2026-05-30 (Run 2 baseline) | 3 | 1 | 4 | ~25,700 | ~74% |

## Notes / caveats

- ctxpack code packer is **Python-only at v0**. TypeScript / TSX / CSS still hit `Read`. When the packer adds those languages, savings should compound (frontend changes are currently un-optimised here).
- `centrality_prior` is global PageRank; per-turn BM25 ranking is "not yet wired" per the manifest caveat. Symbol-search relevance is OK but not great for obscure queries — fall back to two-step search-then-hydrate.
- Pack reflects the **current branch's working tree**, not `main`. A symbol returning `unknown_module` may be a real "this file isn't on this branch" (and the protocol is correct), not a staleness bug.
