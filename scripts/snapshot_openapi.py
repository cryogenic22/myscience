"""Snapshot the live OpenAPI spec to schema/openapi.json.

Run from repo root:
    python -m scripts.snapshot_openapi

This is the single source of truth Antigravity uses to keep
frontend/src/api.ts in sync with the backend. Claude must regenerate
on every API-changing PR.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from api.app import create_app

    app = create_app()
    spec = app.openapi()

    out = repo_root / "schema" / "openapi.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Wrote {out.relative_to(repo_root)} ({len(spec.get('paths', {}))} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
