#!/usr/bin/env python3
"""Generate CODEOWNERS from active and reserved protected-path manifests.

Active paths must exist and define the current assurance bar. Reserved paths
may be absent, but CODEOWNERS protects their future location before creation.
The sync test verifies both manifests and the generated file.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


OWNER = "@cryogenic22"

REPO_ROOT = Path(__file__).resolve().parents[1]
SURFACE = REPO_ROOT / "protected-surface.txt"
RESERVED = REPO_ROOT / "reserved-protected-paths.txt"
CODEOWNERS = REPO_ROOT / ".github" / "CODEOWNERS"

HEADER = """\
# GENERATED FILE - do not edit by hand.
# Sources: protected-surface.txt and reserved-protected-paths.txt
# Regenerate: python scripts/gen_codeowners.py
# These paths define or will define the assurance bar. Changes require owner review.
"""


def _manifest_paths(path: Path) -> list[str]:
    if not path.exists():
        print(f"ERROR: {path.name} missing (fail-closed).", file=sys.stderr)
        raise SystemExit(1)
    paths: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            normalized = line.rstrip("/")
            parts = normalized.split("/")
            if (
                not normalized
                or line.startswith("/")
                or "\\" in line
                or "*" in line
                or any(part in {"", ".", ".."} for part in parts)
            ):
                print(
                    f"ERROR: unsafe protected path {line!r} in {path.name}.",
                    file=sys.stderr,
                )
                raise SystemExit(1)
            paths.append(line)
    if not paths:
        print(f"ERROR: {path.name} defines no paths (fail-closed).", file=sys.stderr)
        raise SystemExit(1)
    if len(paths) != len(set(paths)):
        print(f"ERROR: {path.name} contains duplicate paths.", file=sys.stderr)
        raise SystemExit(1)
    return paths


def _surface_paths() -> list[str]:
    active = _manifest_paths(SURFACE)
    reserved = _manifest_paths(RESERVED)
    duplicates = set(active) & set(reserved)
    if duplicates:
        print(
            f"ERROR: paths cannot be active and reserved: {sorted(duplicates)}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return [*active, *reserved]


def _to_codeowners_rule(path: str) -> str:
    return f"/{path} {OWNER}"


def render() -> str:
    return "\n".join([HEADER, *map(_to_codeowners_rule, _surface_paths())]) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if CODEOWNERS is out of sync",
    )
    args = parser.parse_args()

    expected = render()
    if args.check:
        actual = CODEOWNERS.read_text(encoding="utf-8") if CODEOWNERS.exists() else ""
        if actual != expected:
            print(
                "CODEOWNERS is OUT OF SYNC with protected manifests - "
                "run: python scripts/gen_codeowners.py",
                file=sys.stderr,
            )
            return 1
        print("CODEOWNERS in sync with protected manifests")
        return 0

    CODEOWNERS.parent.mkdir(parents=True, exist_ok=True)
    CODEOWNERS.write_text(expected, encoding="utf-8")
    print(
        f"Wrote {CODEOWNERS.relative_to(REPO_ROOT)} "
        f"({len(_surface_paths())} protected paths)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
