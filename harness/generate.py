#!/usr/bin/env python3
"""Harness Generator — Portable codebase intelligence for Claude Code agents.

Drop this into any repo and run:
    python harness/generate.py

Generates:
    .claude/rules/anti-slop.md          — Utility/helper catalog (DO NOT DUPLICATE)
    .claude/rules/test-requirements.md  — Testing conventions per directory
    .claude/rules/commit-conventions.md — Commit format from git history
    .claude/codebase-map.md             — Full module structure map
    .claude/agents/code-navigator.md    — Subagent: search before coding
    .claude/agents/test-writer.md       — Subagent: write tests matching conventions

Portable: works on any Python/TypeScript/mixed monorepo.
Re-run after major changes: python harness/generate.py --refresh
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SKIP_DIRS = {
    "node_modules", ".next", "__pycache__", ".git", "dist", "build",
    "coverage", ".venv", "venv", ".env", "env", ".claude", ".coverage",
    "playwright-report", "test-results", "sdk_export", "harness",
    ".share_build", "share_build", ".tmp", "tmp",
}

SOURCE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx"}
TEST_PATTERNS = {"test_", "_test.", ".test.", ".spec.", "tests/", "__tests__/"}

MAX_FILE_SCAN = 2000  # Max files to scan for utilities


def find_repo_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / ".git").exists():
            return p
    return start


# ---------------------------------------------------------------------------
# 1. Anti-Slop: Utility/Helper Catalog
# ---------------------------------------------------------------------------

# Patterns that indicate a utility/helper function worth cataloging
UTILITY_PATTERNS = {
    "python": [
        r"^def\s+(\w+)\s*\(",            # function def
        r"^async\s+def\s+(\w+)\s*\(",     # async function def
        r"^class\s+(\w+)\s*[:\(]",        # class def
    ],
    "typescript": [
        r"^export\s+(?:async\s+)?function\s+(\w+)",  # exported function
        r"^export\s+const\s+(\w+)\s*=",               # exported const
        r"^export\s+class\s+(\w+)",                    # exported class
        r"^export\s+interface\s+(\w+)",                # exported interface
        r"^export\s+type\s+(\w+)",                     # exported type
    ],
}

# Directories that typically contain shared utilities
UTILITY_DIRS = {
    "utils", "lib", "helpers", "core", "services", "hooks",
    "components/ui", "shared", "common",
}


def scan_utilities(root: Path) -> list[dict[str, str]]:
    """Scan codebase for exported/public utilities."""
    utilities: list[dict[str, str]] = []
    files_scanned = 0

    for path in sorted(root.rglob("*")):
        if files_scanned >= MAX_FILE_SCAN:
            break
        if any(skip in path.parts for skip in SKIP_DIRS):
            continue
        if path.suffix not in SOURCE_EXTS or not path.is_file():
            continue
        if any(p in str(path) for p in TEST_PATTERNS):
            continue

        files_scanned += 1
        rel = path.relative_to(root)
        lang = "python" if path.suffix == ".py" else "typescript"
        patterns = UTILITY_PATTERNS[lang]

        # Prioritize utility directories
        is_utility_dir = any(ud in str(rel).replace("\\", "/") for ud in UTILITY_DIRS)

        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for line_num, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            for pat in patterns:
                m = re.match(pat, stripped)
                if m:
                    name = m.group(1)
                    # Skip private/internal (Python _ prefix, JS _ prefix)
                    if name.startswith("_") and not name.startswith("__"):
                        continue
                    utilities.append({
                        "name": name,
                        "file": str(rel).replace("\\", "/"),
                        "line": str(line_num),
                        "type": _classify_export(stripped, lang),
                        "priority": "high" if is_utility_dir else "normal",
                    })
    return utilities


def _classify_export(line: str, lang: str) -> str:
    if "class " in line:
        return "class"
    if "interface " in line or "type " in line:
        return "type"
    if "async " in line:
        return "async function"
    if "def " in line or "function " in line:
        return "function"
    if "const " in line:
        return "constant"
    return "export"


def generate_anti_slop(root: Path, utilities: list[dict[str, str]]) -> str:
    """Generate anti-slop.md content."""
    # Group by directory
    by_dir: dict[str, list[dict[str, str]]] = defaultdict(list)
    for u in utilities:
        dir_path = "/".join(u["file"].split("/")[:-1]) or "."
        by_dir[dir_path].append(u)

    # Find duplicates
    name_count: dict[str, list[str]] = defaultdict(list)
    for u in utilities:
        name_count[u["name"]].append(u["file"])
    duplicates = {k: v for k, v in name_count.items() if len(v) > 1}

    lines = [
        "# Anti-Slop Rules — DO NOT DUPLICATE Existing Utilities",
        "",
        f"*Auto-generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        f"*Scanned: {len(utilities)} exports across {len(by_dir)} directories*",
        "",
        "**BEFORE creating any new function, class, or constant:**",
        "1. Search this list for an existing implementation",
        "2. If it exists, import it — do NOT create a new version",
        "3. If you need a variant, extend the existing one",
        "",
    ]

    if duplicates:
        lines.append(f"## Known Duplicates ({len(duplicates)} — consolidate these)")
        lines.append("")
        for name, files in sorted(duplicates.items()):
            lines.append(f"- **`{name}`** — defined in: {', '.join(f'`{f}`' for f in files)}")
        lines.append("")

    # List high-priority utility directories first
    high_dirs = sorted(d for d in by_dir if any(ud in d for ud in UTILITY_DIRS))
    other_dirs = sorted(d for d in by_dir if d not in high_dirs)

    if high_dirs:
        lines.append("## Shared Utilities (check these FIRST)")
        lines.append("")
        for dir_path in high_dirs:
            items = by_dir[dir_path]
            lines.append(f"### `{dir_path}/`")
            lines.append("| Name | Type | File:Line |")
            lines.append("|------|------|-----------|")
            for u in sorted(items, key=lambda x: x["name"]):
                lines.append(f"| `{u['name']}` | {u['type']} | `{u['file']}:{u['line']}` |")
            lines.append("")

    if other_dirs:
        lines.append("## Other Exports (top directories only)")
        lines.append("")
        lines.append("*Use `Grep` to search for specific functions — this list shows key directories only.*")
        lines.append("")
        for dir_path in other_dirs[:15]:  # Top 15 only
            items = by_dir[dir_path]
            lines.append(f"### `{dir_path}/` ({len(items)} exports)")
            # Only show first 10 per directory
            for u in sorted(items, key=lambda x: x["name"])[:10]:
                lines.append(f"- `{u['name']}` ({u['type']}) — `{u['file']}:{u['line']}`")
            if len(items) > 10:
                lines.append(f"- *...and {len(items) - 10} more — search with Grep*")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 2. Test Requirements
# ---------------------------------------------------------------------------

def scan_test_conventions(root: Path) -> dict[str, Any]:
    """Detect testing framework and conventions from existing test files."""
    conventions: dict[str, Any] = {
        "backend": {"framework": None, "fixtures": [], "patterns": [], "test_dir": None},
        "frontend": {"framework": None, "patterns": [], "test_dir": None},
    }

    # Backend: check for pytest
    pyproject = root / "apps" / "api" / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text(encoding="utf-8", errors="ignore")
        if "pytest" in content:
            conventions["backend"]["framework"] = "pytest"
        cov_match = re.search(r"cov-fail-under=(\d+)", content)
        if cov_match:
            conventions["backend"]["coverage_min"] = int(cov_match.group(1))

    # Backend: scan conftest for fixtures
    conftest = root / "apps" / "api" / "tests" / "conftest.py"
    if conftest.exists():
        content = conftest.read_text(encoding="utf-8", errors="ignore")
        conventions["backend"]["test_dir"] = "apps/api/tests/"
        fixtures = re.findall(r"@pytest\.fixture.*\ndef\s+(\w+)", content)
        conventions["backend"]["fixtures"] = fixtures
        if "testcontainers" in content or "PostgresContainer" in content:
            conventions["backend"]["uses_real_db"] = True

    # Backend: count test files
    test_dir = root / "apps" / "api" / "tests"
    if test_dir.exists():
        conventions["backend"]["test_count"] = len(list(test_dir.glob("test_*.py")))

    # Frontend: check for vitest
    for cfg in ["vitest.config.ts", "vitest.config.js"]:
        if (root / "apps" / "web" / cfg).exists():
            conventions["frontend"]["framework"] = "vitest"
            break

    # Frontend: check package.json for test runner
    pkg = root / "apps" / "web" / "package.json"
    if pkg.exists():
        content = pkg.read_text(encoding="utf-8", errors="ignore")
        if "vitest" in content:
            conventions["frontend"]["framework"] = "vitest"

    # Frontend: count test files
    fe_test_dir = root / "apps" / "web" / "__tests__"
    if fe_test_dir.exists():
        conventions["frontend"]["test_dir"] = "apps/web/__tests__/"
        conventions["frontend"]["test_count"] = len(list(fe_test_dir.rglob("*.test.tsx")) + list(fe_test_dir.rglob("*.test.ts")))

    # Scan a sample test to extract patterns
    sample_tests = list((root / "apps" / "api" / "tests").glob("test_*.py"))[:3] if test_dir.exists() else []
    for st in sample_tests:
        content = st.read_text(encoding="utf-8", errors="ignore")
        if "def auth(" in content:
            conventions["backend"]["patterns"].append("auth() helper for Bearer token headers")
        if "client: TestClient" in content:
            conventions["backend"]["patterns"].append("client fixture (TestClient) from conftest.py")
        if "patch(" in content or "mock" in content.lower():
            conventions["backend"]["patterns"].append("unittest.mock.patch for external service mocking")

    return conventions


def generate_test_requirements(conventions: dict[str, Any]) -> str:
    """Generate test-requirements.md content."""
    lines = [
        "# Test Requirements — Every Change Needs a Test",
        "",
        f"*Auto-generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
    ]

    be = conventions["backend"]
    if be["framework"]:
        lines.append("## Backend Tests")
        lines.append("")
        lines.append(f"- **Framework**: {be['framework']}")
        lines.append(f"- **Test directory**: `{be.get('test_dir', 'tests/')}`")
        lines.append(f"- **Test files**: {be.get('test_count', '?')} files")
        if be.get("coverage_min"):
            lines.append(f"- **Coverage minimum**: {be['coverage_min']}% (ratchet — only goes up)")
        if be.get("uses_real_db"):
            lines.append("- **Database**: Real PostgreSQL via testcontainers (NOT mocked)")
        if be.get("fixtures"):
            lines.append(f"- **Available fixtures**: `{'`, `'.join(be['fixtures'])}`")
        lines.append("")
        lines.append("### Patterns")
        for p in sorted(set(be.get("patterns", []))):
            lines.append(f"- {p}")
        lines.append("")
        lines.append("### Rules")
        lines.append("- File naming: `test_<feature>.py`")
        lines.append("- TDD: Write the test FIRST, then implement")
        lines.append("- Use `client` fixture for API endpoint tests")
        lines.append("- Use `auth(username, [roles])` helper for authenticated requests")
        lines.append("- Mark async tests with `@pytest.mark.asyncio`")
        lines.append("")

    fe = conventions["frontend"]
    if fe["framework"]:
        lines.append("## Frontend Tests")
        lines.append("")
        lines.append(f"- **Framework**: {fe['framework']} + React Testing Library")
        lines.append(f"- **Test directory**: `{fe.get('test_dir', '__tests__/')}`")
        lines.append(f"- **Test files**: {fe.get('test_count', '?')} files")
        lines.append("")
        lines.append("### Rules")
        lines.append("- File naming: `<feature>.test.tsx`")
        lines.append("- Mock external dependencies with `vi.mock()`")
        lines.append("- Mock UI components (Badge, Button, Card, etc.) to avoid import chains")
        lines.append("- Use `data-testid` attributes for element selection")
        lines.append("- Wrap state updates in `act(async () => { ... })`")
        lines.append("- Use `waitFor()` for async renders")
        lines.append("")

    lines.append("## What Needs a Test")
    lines.append("")
    lines.append("| Change Type | Test Type | Location |")
    lines.append("|-------------|-----------|----------|")
    lines.append("| New API endpoint | pytest integration test | `apps/api/tests/test_<feature>.py` |")
    lines.append("| Service/business logic | pytest unit test | `apps/api/tests/test_<service>.py` |")
    lines.append("| New React component | Vitest render test | `apps/web/__tests__/<dir>/<name>.test.tsx` |")
    lines.append("| Hook/logic change | Vitest unit test | `apps/web/__tests__/<dir>/<name>.test.tsx` |")
    lines.append("| Bug fix | Regression test (fails without fix) | Same as above |")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 3. Commit Conventions (from git history)
# ---------------------------------------------------------------------------

def scan_commit_conventions(root: Path) -> str:
    """Extract commit conventions from recent git history."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "log", "--oneline", "-50", "--format=%s"],
            capture_output=True, text=True, timeout=10,
        )
        messages = result.stdout.strip().splitlines()
    except Exception:
        messages = []

    # Detect conventional commits pattern
    conventional = 0
    prefixes: dict[str, int] = defaultdict(int)
    for msg in messages:
        m = re.match(r"^(feat|fix|chore|docs|test|refactor|style|perf|ci)\b", msg)
        if m:
            conventional += 1
            prefixes[m.group(1)] += 1

    lines = [
        "# Commit Conventions",
        "",
        f"*Auto-generated from last {len(messages)} commits: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
    ]

    if conventional > len(messages) * 0.5:
        lines.append("## Format: Conventional Commits")
        lines.append("")
        lines.append("```")
        lines.append("<type>(<scope>): <description>")
        lines.append("```")
        lines.append("")
        lines.append("### Prefixes (by frequency)")
        for prefix, count in sorted(prefixes.items(), key=lambda x: -x[1]):
            lines.append(f"- `{prefix}:` — {count} commits")
        lines.append("")
        lines.append("### Examples from this repo")
        for msg in messages[:10]:
            lines.append(f"- `{msg}`")
    else:
        lines.append("## Format")
        lines.append("")
        lines.append("Use conventional commits: `feat(scope):`, `fix(scope):`, `chore:`, `docs:`")
        lines.append("")
        lines.append("### Recent commits")
        for msg in messages[:10]:
            lines.append(f"- `{msg}`")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 4. Codebase Map
# ---------------------------------------------------------------------------

def generate_codebase_map(root: Path) -> str:
    """Generate a structural map of the codebase."""
    lines = [
        "# Codebase Map",
        "",
        f"*Auto-generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
    ]

    # Count stats
    stats: dict[str, int] = defaultdict(int)
    dir_files: dict[str, list[str]] = defaultdict(list)

    for path in sorted(root.rglob("*")):
        if any(skip in path.parts for skip in SKIP_DIRS):
            continue
        if not path.is_file():
            continue
        if path.suffix in SOURCE_EXTS:
            rel = path.relative_to(root)
            dir_key = "/".join(str(rel).replace("\\", "/").split("/")[:3])
            dir_files[dir_key].append(str(rel).replace("\\", "/"))
            stats[path.suffix] += 1

    lines.append("## Stats")
    lines.append("")
    for ext, count in sorted(stats.items(), key=lambda x: -x[1]):
        lang = {".py": "Python", ".ts": "TypeScript", ".tsx": "TSX/React", ".js": "JavaScript"}.get(ext, ext)
        lines.append(f"- **{lang}**: {count} files")
    lines.append(f"- **Total source files**: {sum(stats.values())}")
    lines.append("")

    lines.append("## Directory Structure")
    lines.append("")

    # Group into major areas
    areas: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for dir_key, files in sorted(dir_files.items()):
        area = dir_key.split("/")[0] if "/" in dir_key else dir_key
        areas[area][dir_key] = len(files)

    for area in sorted(areas):
        total = sum(areas[area].values())
        lines.append(f"### `{area}/` ({total} files)")
        lines.append("")
        for dir_key in sorted(areas[area]):
            count = areas[area][dir_key]
            lines.append(f"- `{dir_key}/` — {count} files")
        lines.append("")

    # Key entry points
    lines.append("## Key Entry Points")
    lines.append("")
    key_files = [
        ("apps/api/app/main.py", "Backend app factory"),
        ("apps/api/app/api/v1/router.py", "API route registration"),
        ("apps/api/app/db.py", "Database engine and session"),
        ("apps/api/app/config.py", "Backend settings"),
        ("apps/web/app/layout.tsx", "Frontend root layout"),
        ("apps/web/lib/api.ts", "Frontend API client (fetchJson)"),
        ("apps/web/lib/api-platform.ts", "Platform API functions"),
        ("apps/web/lib/api-domains.ts", "Domain API functions"),
    ]
    for fpath, desc in key_files:
        exists = "exists" if (root / fpath).exists() else "MISSING"
        lines.append(f"- `{fpath}` — {desc} [{exists}]")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 5. Subagent Definitions
# ---------------------------------------------------------------------------

def generate_code_navigator() -> str:
    return """---
description: Find files, patterns, and utilities in the codebase before writing new code
tools: Read, Glob, Grep
model: sonnet
---

You are a code navigator. Before writing any new code, search the codebase for existing implementations.

**Your job**: Answer "does this already exist?" and "what pattern should I follow?"

## Process
1. Search for the function/class/component name with Grep
2. Check utility directories first: `lib/`, `services/`, `core/`, `hooks/`, `components/ui/`
3. If found, report the exact file:line and how to import it
4. If not found, find the closest sibling file to use as a pattern reference

## Key locations
@.claude/codebase-map.md

## Anti-slop rules
@.claude/rules/anti-slop.md

## Report format
- **Found**: `file:line` — description, how to import
- **Not found**: closest pattern reference file to follow
- **Duplicates**: list if the same name exists in multiple places
"""


def generate_test_writer() -> str:
    return """---
description: Write tests matching existing codebase conventions
tools: Read, Write, Glob, Bash
model: sonnet
---

You write tests for this codebase. Match existing patterns exactly.

## Before writing any test
1. Read the source file being tested
2. Find existing test files in the same module: `Glob("**/test_*.py")` or `Glob("**/*.test.tsx")`
3. Match their import patterns, fixtures, assertion style, and mock setup exactly

## Testing conventions
@.claude/rules/test-requirements.md

## Rules
- NEVER create a test that doesn't run — verify with the test runner
- ALWAYS use existing fixtures (e.g., `client` for API tests, `vi.mock` patterns for frontend)
- Match the EXACT auth helper pattern: `auth(user, [roles])` returning Bearer token header
- For async Python tests: `@pytest.mark.asyncio`
- For React tests: mock UI components, use `data-testid`, wrap updates in `act()`
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate Claude Code harness rules")
    parser.add_argument("path", nargs="?", default=".", help="Repository root path")
    parser.add_argument("--refresh", action="store_true", help="Force regeneration")
    args = parser.parse_args()

    root = find_repo_root(Path(args.path).resolve())
    print(f"Generating harness for: {root}")

    # Ensure directories exist
    (root / ".claude" / "rules").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "agents").mkdir(parents=True, exist_ok=True)

    # 1. Anti-slop
    print("  [1/5] Scanning utilities for anti-slop rules...")
    utilities = scan_utilities(root)
    anti_slop = generate_anti_slop(root, utilities)
    (root / ".claude" / "rules" / "anti-slop.md").write_text(anti_slop, encoding="utf-8")
    print(f"         Found {len(utilities)} exports")

    # 2. Test requirements
    print("  [2/5] Detecting test conventions...")
    conventions = scan_test_conventions(root)
    test_req = generate_test_requirements(conventions)
    (root / ".claude" / "rules" / "test-requirements.md").write_text(test_req, encoding="utf-8")

    # 3. Commit conventions
    print("  [3/5] Analyzing commit history...")
    commit_conv = scan_commit_conventions(root)
    (root / ".claude" / "rules" / "commit-conventions.md").write_text(commit_conv, encoding="utf-8")

    # 4. Codebase map
    print("  [4/5] Building codebase map...")
    codebase_map = generate_codebase_map(root)
    (root / ".claude" / "codebase-map.md").write_text(codebase_map, encoding="utf-8")

    # 5. Subagents
    print("  [5/5] Writing subagent definitions...")
    (root / ".claude" / "agents" / "code-navigator.md").write_text(generate_code_navigator(), encoding="utf-8")
    (root / ".claude" / "agents" / "test-writer.md").write_text(generate_test_writer(), encoding="utf-8")

    print()
    print("Harness generated:")
    print(f"  .claude/rules/anti-slop.md          ({len(utilities)} utilities cataloged)")
    print(f"  .claude/rules/test-requirements.md   (testing conventions)")
    print(f"  .claude/rules/commit-conventions.md  (commit format)")
    print(f"  .claude/codebase-map.md              (structure map)")
    print(f"  .claude/agents/code-navigator.md     (search-before-code agent)")
    print(f"  .claude/agents/test-writer.md         (test-writing agent)")
    print()
    print("Add to CLAUDE.md:  ## Codebase Map\\n@.claude/codebase-map.md")
    print("Refresh with:      python harness/generate.py --refresh")


if __name__ == "__main__":
    main()
