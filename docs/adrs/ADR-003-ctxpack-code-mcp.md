# ADR-003 — ctxpack code-packer MCP for Claude Code context

**Status:** Accepted (2026-05-22) · **Decision:** Use CTX_mod's code-packer as a
local MCP server to serve symbol-level code to the coding agent. Config is
local-only (gitignored); each dev replicates per the setup below.

---

Serves **symbol-level code on demand** to Claude Code so the agent hydrates
only the relevant function/class (+ call-graph neighbours + provenance)
instead of bulk-reading whole files. ~38% fewer tokens on a small focused
task; larger savings when orienting in unfamiliar code.

`.mcp.json` is **gitignored** because it hardcodes a machine-specific path to
the CTX_mod checkout. Each developer creates their own.

## Prerequisites

- The `CTX_mod` repo checked out locally (it contains the code-packer; the
  copy vendored under `market_zero/ctxpack/` does **not**).
- Python 3.11+ (this repo uses 3.13).
- ctxpack's `[code]` extra deps available (tree-sitter + tiktoken). If the
  server fails to import the code packer:
  `pip install -e "<path-to-CTX_mod>[code]"`.

## Create `.mcp.json` at the repo root

Replace the path with **your** CTX_mod location:

```json
{
  "mcpServers": {
    "ctxpack-code": {
      "command": "python",
      "args": ["-P", "-m", "ctxpack.integrations.mcp_server"],
      "env": {
        "PYTHONSAFEPATH": "1",
        "PYTHONPATH": "C:\\path\\to\\CTX_mod"
      }
    }
  }
}
```

`PYTHONSAFEPATH=1` + `PYTHONPATH` are required: this repo vendors an older
ctxpack without the code-packer, and it would otherwise shadow CTX_mod's
copy when the server launches from the project cwd.

## Activate

1. Restart Claude Code / reopen this project so it reads `.mcp.json`.
2. Approve the `ctxpack-code` server when prompted.
3. Tools become available: `ctx/code_pack` (build the index — pass
   `root` = this repo), then `ctx/code_search_symbols`,
   `ctx/code_hydrate_symbol`, `ctx/code_list_symbols`, `ctx/code_raw_file`.

## Smoke test (without Claude Code)

```bash
PYTHONSAFEPATH=1 PYTHONPATH="<path-to-CTX_mod>" \
  python -P -c "from ctxpack.core.code.pack import pack_codebase, search_symbols; \
  p=pack_codebase('.'); print(search_symbols(p,'EvidenceStack',k=3))"
```
