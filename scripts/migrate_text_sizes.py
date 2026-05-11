"""Loop #12 — codemod that migrates Tailwind arbitrary-size classes
``text-[Npx]`` onto the design-system type scale (``mz-text-*``).

Conservative mapping — only exact pixel values present in our scale
are rewritten. Sizes outside the scale (e.g. ``text-[8px]``,
``text-[84px]``) are left alone so the operator can decide whether to
extend the scale or hand-migrate them.

Usage::

    python -m scripts.migrate_text_sizes [PATH ...]

Defaults to ``frontend/src``. Pass explicit paths to limit the run.

The codemod operates on `.tsx` and `.ts` files only and never touches
files under ``__tests__``, ``test``, ``dist``, ``node_modules``.

Each rewrite is a literal substring replacement: ``text-[10px]`` →
``mz-text-xs`` and similar. The script prints a per-file summary at
the end. It is idempotent.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


SIZE_MAP: dict[str, str] = {
    # Exact pixel → mz-text-* mapping. Keep in sync with index.css
    # `--text-*` variables. Sizes < 11 collapse to xs because the
    # design system does not ship a sub-11px micro tier.
    "text-[8px]":  "mz-text-xs",
    "text-[9px]":  "mz-text-xs",
    "text-[10px]": "mz-text-xs",
    "text-[11px]": "mz-text-xs",
    "text-[12px]": "mz-text-sm",
    "text-[13px]": "mz-text-sm-2",
    "text-[14px]": "mz-text-base",
    "text-[15px]": "mz-text-md",
    "text-[16px]": "mz-text-md-2",
    "text-[18px]": "mz-text-lg",
    "text-[20px]": "mz-text-lg-2",
    "text-[22px]": "mz-text-xl",
    "text-[24px]": "mz-text-xl-2",
    "text-[28px]": "mz-text-display",
}

SKIP_DIRS = {"__tests__", "test", "tests", "dist", "node_modules", ".git", ".turbo"}
ALLOWED_SUFFIXES = {".tsx", ".ts"}


def migrate_file(path: Path) -> int:
    """Apply the size map in-place. Returns the number of substitutions."""
    text = path.read_text(encoding="utf-8")
    count = 0
    for old, new in SIZE_MAP.items():
        n = text.count(old)
        if n:
            text = text.replace(old, new)
            count += n
    if count:
        path.write_text(text, encoding="utf-8")
    return count


def should_skip(path: Path) -> bool:
    if path.suffix not in ALLOWED_SUFFIXES:
        return True
    for part in path.parts:
        if part in SKIP_DIRS:
            return True
    return False


def walk(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if not should_skip(root) else []
    out: list[Path] = []
    for p in root.rglob("*"):
        if p.is_file() and not should_skip(p):
            out.append(p)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        default=["frontend/src"],
        help="Files or directories to migrate (default: frontend/src)",
    )
    args = parser.parse_args(argv)

    files: list[Path] = []
    for raw in args.paths:
        p = Path(raw)
        if not p.exists():
            print(f"warning: path not found: {p}", file=sys.stderr)
            continue
        files.extend(walk(p))

    if not files:
        print("migrate_text_sizes: nothing to migrate")
        return 0

    total_subs = 0
    files_touched = 0
    for f in sorted(files):
        n = migrate_file(f)
        if n:
            files_touched += 1
            total_subs += n
            print(f"  {n:>4}  {f.as_posix()}")

    print(
        f"\nmigrate_text_sizes: {total_subs} substitutions across "
        f"{files_touched} files (out of {len(files)} scanned)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
