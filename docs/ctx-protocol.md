# ctxpack Usage Protocol

*Durable. Versioned in repo. Loaded into agent memory via `[[ctx_usage_protocol]]`.*

## Why this exists
The ctxpack code MCP serves **symbol-level code on demand** — function body + signature + docstring + 1-hop neighbours — instead of forcing whole-file reads. Real measured savings: **68–96% per call** on this repo (see "Baseline benchmark" below). Without a deterministic protocol, the savings are forgotten in practice. This doc + the memory pointer keep it deterministic.

## The pack is the current working tree
The pack indexes whatever is on disk *now*. Two consequences:
1. **Pack staleness ≠ time** — it's "the disk has changed since the last `ctx_code_pack`."
2. **Branch switches invalidate the pack** for the branch you just landed on (files that exist on one branch and not another flip in and out).

Refresh tool: `python scripts/refresh_ctx_pack.py`. Check without rebuilding: `python scripts/refresh_ctx_pack.py --check`.

## The deterministic protocol

### A. Session-start probe (every session, before any Read)
1. `mcp__ctxpack-code__ctx_code_version` → capture `pack_version`.
2. Compare against the last-known version in `docs/ctx-usage-log.md` (the most recent entry).
3. If different OR if the user mentions a branch change since: run `scripts/refresh_ctx_pack.py`.

### B. Branch-switch probe (every `git checkout`)
1. After any branch switch, re-pack (`scripts/refresh_ctx_pack.py`).
2. Log the new pack_version with branch + HEAD shortsha in `docs/ctx-usage-log.md`.

### C. Per-task decision rule (which tool for which job)
| Situation | Tool | Why |
|---|---|---|
| Need one function/class body | `ctx_code_hydrate_symbol(name, depth=0)` | 70–96% savings vs full file |
| Need that + call neighbours | `ctx_code_hydrate_symbol(name, depth=1)` | Saves a second hydrate; caps at 4K BPE |
| Don't know the symbol name | `ctx_code_search_symbols(query, k=5)` first, then hydrate | Two cheap calls cheaper than one broad Read |
| Want a module's table of contents | `ctx_code_list_symbols(module, k=10)` | ~30× cheaper than full Read |
| File I edited this session | **`Read` or memory** | Pack is stale for that file until next refresh |
| Non-Python (TS/TSX/CSS/MD) | `Read` or `Grep` | Code packer is Python-only at v0 |
| Search by string content | `Grep` | Pack is by symbol, not text |
| Pack returns `unknown_module` | Check working tree; if file exists, **refresh** | Pack is stale |
| Edited file repeatedly in session | `Read` last-edited form, hold in conversation | Hydrate would return earlier state |

### D. After every loop (post-PUSH)
Append a row to `docs/ctx-usage-log.md` capturing:
- ctx hydrate count, search count, list count
- Approximate tokens saved (sum of `file_size - hydrate_response_size` per hydrate)
- New pack_version if re-packed

## Baseline benchmark (30 May 2026)

Three real hydrate calls against this repo. **Cost compared = ctx response size vs the full file `Read` would have returned.**

| Call | Hydrate bytes | Full-file bytes | Savings |
|---|---|---|---|
| `services/signal_promoter.py::classify_kbq` (depth 0) | ~580 | 14,279 | **~96%** |
| `services/facts_ledger.py::assert_fact` (depth 0) | ~1,750 | 6,231 | **~72%** |
| `services/facts_ledger.py::_valid_at` (depth 1 incl. 1 callee + 6 caller tests) | ~3,500 | ~11,000 (incl. test file) | **~68%** |

Even at depth=1 (the most expensive realistic use — function + its neighbours + their bodies) the savings hold. Aggregate target: **>60% token reduction on code-reading operations per loop.**

## What ctx does NOT replace
- Reading docs/specs/markdown — those are doc-corpus territory (`ctx/pack`, `ctx/hydrate`).
- Non-Python source (TypeScript, CSS, SQL) — out of scope for v0 of code packer.
- Files just modified in-session — hold them in conversation, don't re-hydrate.
- Wide pattern search across many files — that's `Grep`'s job.

## Memory pointer
The session-start probe is held in `memory/ctx_usage_protocol.md` and surfaces in the system reminder of every session. If the protocol changes, update both this doc and that memory file.
