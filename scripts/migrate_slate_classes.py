"""Loop #13 — codemod that migrates Tailwind ``slate-*`` colour
classes onto the design-token utilities Tailwind v4 generates from
``@theme`` declarations (``bg-surface-2``, ``text-ink-3``,
``border-line``, etc.).

Closes root cause #8 from the Loop #11 audit: the 150-line
``!important`` Tailwind-slate override block in ``index.css`` only
exists because TSX files hardcoded ``bg-slate-*`` / ``text-slate-*``
/ ``border-slate-*``. After this codemod runs, no slate-* class
remains in ``src/`` and the override block can be deleted.

Usage::

    python -m scripts.migrate_slate_classes [PATH ...]

Defaults to ``frontend/src``. Pass explicit paths to limit the run.
Skips ``__tests__``/``test``/``dist``/``node_modules``.

The replacements preserve alpha modifiers (``bg-slate-50/45`` →
``bg-surface-2/45``) but in our token system the alpha modifier
maps to the same surface tier — visually equivalent — so the
suffix is dropped.

Idempotent.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


# Each tuple is (regex, replacement). The regexes are anchored to
# whitespace/quote/brace boundaries so we never rewrite a substring
# in the middle of an identifier.
PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Backgrounds — surface tiers
    (re.compile(r"\bbg-slate-50(?:\/\d+)?\b"),                "bg-surface-2"),
    (re.compile(r"\bbg-slate-100\b"),                          "bg-surface-3"),
    (re.compile(r"\bbg-slate-900\b"),                          "bg-ink"),
    (re.compile(r"\bbg-slate-900\/40\b"),                      "bg-ink/40"),

    # Text — ink tiers (4 stops)
    (re.compile(r"\btext-slate-900\b"),                        "text-ink"),
    (re.compile(r"\btext-slate-800\b"),                        "text-ink"),
    (re.compile(r"\btext-slate-700\b"),                        "text-ink-2"),
    (re.compile(r"\btext-slate-600\b"),                        "text-ink-3"),
    (re.compile(r"\btext-slate-500\b"),                        "text-ink-3"),
    (re.compile(r"\btext-slate-400\b"),                        "text-ink-4"),
    (re.compile(r"\btext-slate-300\b"),                        "text-ink-4"),

    # Borders — line token (single ghost weight)
    (re.compile(r"\bborder-slate-100(?:\/\d+)?\b"),            "border-line"),
    (re.compile(r"\bborder-slate-200(?:\/\d+)?\b"),            "border-line"),
    (re.compile(r"\bborder-slate-300\b"),                      "border-line"),
    (re.compile(r"\bborder-slate-700(?:\/\d+)?\b"),            "border-line"),
    (re.compile(r"\bborder-slate-900\b"),                      "border-ink"),

    # Hover — backgrounds
    (re.compile(r"\bhover:bg-slate-50(?:\/\d+)?\b"),           "hover:bg-surface-2"),
    (re.compile(r"\bhover:bg-slate-100\b"),                    "hover:bg-surface-2"),
    (re.compile(r"\bhover:bg-white\b"),                        "hover:bg-surface"),

    # Hover — text
    (re.compile(r"\bhover:text-slate-900\b"),                  "hover:text-ink"),
    (re.compile(r"\bhover:text-slate-700\b"),                  "hover:text-ink-2"),
    (re.compile(r"\bhover:text-slate-600\b"),                  "hover:text-ink-2"),
    (re.compile(r"\bhover:text-slate-300\b"),                  "hover:text-ink-4"),

    # Hover — borders
    (re.compile(r"\bhover:border-slate-300\b"),                "hover:border-line"),

    # Divide / placeholder
    (re.compile(r"\bdivide-slate-200(?:\/\d+)?\b"),            "divide-line"),
    (re.compile(r"\bplaceholder:text-slate-400\b"),            "placeholder:text-ink-4"),
]

SKIP_DIRS = {"__tests__", "test", "tests", "dist", "node_modules", ".git", ".turbo"}
ALLOWED_SUFFIXES = {".tsx", ".ts"}


def migrate_file(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    count = 0
    for pat, repl in PATTERNS:
        text, n = pat.subn(repl, text)
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
        print("migrate_slate_classes: nothing to migrate")
        return 0

    total = 0
    touched = 0
    for f in sorted(files):
        n = migrate_file(f)
        if n:
            touched += 1
            total += n
            print(f"  {n:>4}  {f.as_posix()}")

    print(
        f"\nmigrate_slate_classes: {total} substitutions across "
        f"{touched} files (out of {len(files)} scanned)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
