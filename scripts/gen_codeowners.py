#!/usr/bin/env python3
"""Generate .github/CODEOWNERS from protected-surface.txt (single source of truth).

The protected surface is defined once in protected-surface.txt. CODEOWNERS — the
structural floor (review required once branch protection is on) — is derived from
it so the two can never silently drift. tests/test_protected_surface_sync.py
asserts the file on disk equals what this script would generate.

Usage:
    python scripts/gen_codeowners.py            # write .github/CODEOWNERS
    python scripts/gen_codeowners.py --check     # exit 1 if out of sync (CI/test)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# The repo owner who must review changes to the bar. Keep in sync with the
# GitHub account that holds branch-protection / admin on the repo.
OWNER = "@cryogenic22"

REPO_ROOT = Path(__file__).resolve().parents[1]
SURFACE = REPO_ROOT / "protected-surface.txt"
CODEOWNERS = REPO_ROOT / ".github" / "CODEOWNERS"

HEADER = """\
# GENERATED FILE — do not edit by hand.
# Source of truth: protected-surface.txt · Regenerate: python scripts/gen_codeowners.py
# These paths are the success-definition surface (the BAR). Changes require the
# owner's review so a builder cannot quietly weaken its own gate.
"""


def _surface_paths() -> list[str]:
    if not SURFACE.exists():
        print("ERROR: protected-surface.txt missing (fail-closed).", file=sys.stderr)
        sys.exit(1)
    paths: list[str] = []
    for raw in SURFACE.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            paths.append(line)
    if not paths:
        print("ERROR: protected-surface.txt defines no paths (fail-closed).", file=sys.stderr)
        sys.exit(1)
    return paths


def _to_codeowners_rule(path: str) -> str:
    """A leading '/' anchors the pattern at the repo root; a trailing '/' (a
    directory) is preserved so everything under it is owned."""
    return f"/{path} {OWNER}"


def render() -> str:
    lines = [HEADER]
    for p in _surface_paths():
        lines.append(_to_codeowners_rule(p))
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="exit 1 if CODEOWNERS is out of sync")
    args = ap.parse_args()

    expected = render()
    if args.check:
        actual = CODEOWNERS.read_text(encoding="utf-8") if CODEOWNERS.exists() else ""
        if actual != expected:
            print(
                "CODEOWNERS is OUT OF SYNC with protected-surface.txt — "
                "run: python scripts/gen_codeowners.py",
                file=sys.stderr,
            )
            return 1
        print("CODEOWNERS in sync with protected-surface.txt")
        return 0

    CODEOWNERS.parent.mkdir(parents=True, exist_ok=True)
    CODEOWNERS.write_text(expected, encoding="utf-8")
    print(f"Wrote {CODEOWNERS.relative_to(REPO_ROOT)} ({len(_surface_paths())} protected paths).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
