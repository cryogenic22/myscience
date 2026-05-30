"""Refresh the ctxpack code pack for this repo.

Deterministic helper invoked at session start, after branch switches, and
when the pack is stale relative to working-tree state.

Usage:
    python scripts/refresh_ctx_pack.py
    python scripts/refresh_ctx_pack.py --check    # version + freshness probe, no rebuild

Honest design notes:
    The pack indexes the CURRENT WORKING TREE, not main. After every branch
    switch the pack is "stale for the branch you just landed on" until you
    re-pack. This script is the single command to run; the protocol in
    docs/ctx-protocol.md says when to run it.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# Default CTX_mod location (override via env). Mirrors .mcp.json.
CTX_MOD = Path(os.environ.get(
    "CTX_MOD_PATH",
    r"C:\Users\kapil\Documents\CTX_mod",
))


def _run_in_ctx_mod(code: str) -> dict:
    """Run a Python snippet against the CTX_mod packer and return its JSON output."""
    env = {
        **os.environ,
        "PYTHONSAFEPATH": "1",
        "PYTHONPATH": str(CTX_MOD),
    }
    proc = subprocess.run(
        [sys.executable, "-P", "-c", code],
        env=env, capture_output=True, text=True, cwd=str(REPO_ROOT),
        check=False,
    )
    if proc.returncode != 0:
        sys.stderr.write(f"ctxpack failed:\n{proc.stderr}\n")
        sys.exit(proc.returncode)
    return json.loads(proc.stdout.strip().splitlines()[-1])


def cmd_check() -> int:
    code = (
        "from ctxpack.core.code.pack import current_pack_version; "
        "import json; print(json.dumps({'version': current_pack_version() or 'none'}))"
    )
    try:
        out = _run_in_ctx_mod(code)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"check failed: {exc}\n")
        return 1
    branch = subprocess.check_output(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True, cwd=REPO_ROOT,
    ).strip()
    head = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], text=True, cwd=REPO_ROOT,
    ).strip()
    print(f"branch={branch} head={head} pack_version={out['version']}")
    return 0


def cmd_refresh() -> int:
    code = (
        "from ctxpack.core.code.pack import pack_codebase; "
        "import json; r=pack_codebase('.'); "
        "print(json.dumps({'version': r.pack_version, 'files': r.served.files, 'entities': r.served.entities}))"
    )
    print(f"refreshing pack against {REPO_ROOT}...")
    out = _run_in_ctx_mod(code)
    print(f"OK  pack_version={out['version'][:16]}…  files={out['files']}  entities={out['entities']}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Refresh ctxpack code pack")
    p.add_argument("--check", action="store_true",
                   help="probe only; don't rebuild")
    args = p.parse_args()
    if args.check:
        return cmd_check()
    return cmd_refresh()


if __name__ == "__main__":
    raise SystemExit(main())
