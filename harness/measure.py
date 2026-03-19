#!/usr/bin/env python3
"""Harness Effectiveness Measurement — Track agent code quality over time.

Run weekly:  python harness/measure.py
Reports on: duplicate functions, test coverage trend, regression rate, session quality.

Portable: works on any repo with the harness installed.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

SKIP_DIRS = {
    "node_modules", ".next", "__pycache__", ".git", "dist", "build",
    "coverage", ".venv", "venv", ".env", "env", ".claude", ".coverage",
    ".share_build", "share_build", "harness",
}

SOURCE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx"}


def find_repo_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / ".git").exists():
            return p
    return start


def count_duplicate_functions(root: Path) -> dict[str, list[str]]:
    """Find function names defined in more than one file."""
    func_defs: dict[str, list[str]] = defaultdict(list)
    pattern_py = re.compile(r"^(?:async\s+)?def\s+(\w+)\s*\(")
    pattern_ts = re.compile(r"^export\s+(?:async\s+)?function\s+(\w+)")

    for path in root.rglob("*"):
        if any(skip in path.parts for skip in SKIP_DIRS):
            continue
        if path.suffix not in SOURCE_EXTS or not path.is_file():
            continue
        if "test" in path.name.lower():
            continue

        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        rel = str(path.relative_to(root)).replace("\\", "/")
        pat = pattern_py if path.suffix == ".py" else pattern_ts

        for line in content.splitlines():
            m = pat.match(line.strip())
            if m and not m.group(1).startswith("_"):
                func_defs[m.group(1)].append(rel)

    return {k: v for k, v in func_defs.items() if len(v) > 1}


def count_test_files(root: Path) -> dict[str, int]:
    """Count test files by area."""
    be_tests = len(list((root / "apps" / "api" / "tests").glob("test_*.py"))) if (root / "apps" / "api" / "tests").exists() else 0
    fe_tests = len(list((root / "apps" / "web" / "__tests__").rglob("*.test.tsx"))) + len(list((root / "apps" / "web" / "__tests__").rglob("*.test.ts"))) if (root / "apps" / "web" / "__tests__").exists() else 0
    return {"backend": be_tests, "frontend": fe_tests, "total": be_tests + fe_tests}


def get_coverage_floor(root: Path) -> int | None:
    """Read coverage floor from pyproject.toml."""
    pyproject = root / "apps" / "api" / "pyproject.toml"
    if not pyproject.exists():
        return None
    content = pyproject.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"cov-fail-under=(\d+)", content)
    return int(m.group(1)) if m else None


def get_recent_regression_rate(root: Path, days: int = 14) -> dict[str, int]:
    """Count fix commits vs total commits in recent history."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "log", f"--since={days} days ago", "--oneline", "--format=%s"],
            capture_output=True, text=True, timeout=10,
        )
        messages = result.stdout.strip().splitlines()
    except Exception:
        return {"total": 0, "fixes": 0, "features": 0}

    fixes = sum(1 for m in messages if m.startswith("fix"))
    features = sum(1 for m in messages if m.startswith("feat"))
    return {"total": len(messages), "fixes": fixes, "features": features}


def main():
    root = find_repo_root(Path.cwd())
    print(f"Harness Health Report — {root.name}")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # 1. Duplicate functions
    dupes = count_duplicate_functions(root)
    print(f"\n1. UTILITY DUPLICATION: {len(dupes)} duplicate function names")
    if dupes:
        top = sorted(dupes.items(), key=lambda x: -len(x[1]))[:10]
        for name, files in top:
            print(f"   - {name} ({len(files)} copies): {', '.join(files[:3])}")
    else:
        print("   No duplicates found!")

    # 2. Test coverage
    tests = count_test_files(root)
    floor = get_coverage_floor(root)
    print(f"\n2. TEST COVERAGE:")
    print(f"   Backend test files:  {tests['backend']}")
    print(f"   Frontend test files: {tests['frontend']}")
    print(f"   Total:               {tests['total']}")
    if floor:
        print(f"   Coverage floor:      {floor}%")

    # 3. Regression rate
    regressions = get_recent_regression_rate(root)
    if regressions["total"] > 0:
        fix_rate = regressions["fixes"] / regressions["total"] * 100
        print(f"\n3. REGRESSION RATE (last 14 days):")
        print(f"   Total commits:  {regressions['total']}")
        print(f"   Fix commits:    {regressions['fixes']} ({fix_rate:.0f}%)")
        print(f"   Feat commits:   {regressions['features']}")
        if fix_rate > 40:
            print(f"   WARNING: High fix rate ({fix_rate:.0f}%) — agents may be introducing bugs")
        elif fix_rate < 15:
            print(f"   GOOD: Low fix rate ({fix_rate:.0f}%) — code quality is stable")
    else:
        print("\n3. REGRESSION RATE: No recent commits")

    # 4. Harness freshness
    anti_slop = root / ".claude" / "rules" / "anti-slop.md"
    if anti_slop.exists():
        content = anti_slop.read_text(encoding="utf-8")
        m = re.search(r"Auto-generated: (\d{4}-\d{2}-\d{2})", content)
        if m:
            gen_date = datetime.strptime(m.group(1), "%Y-%m-%d")
            age_days = (datetime.now() - gen_date).days
            print(f"\n4. HARNESS FRESHNESS:")
            print(f"   Last generated: {m.group(1)} ({age_days} days ago)")
            if age_days > 7:
                print(f"   STALE: Re-run `python harness/generate.py --refresh`")
            else:
                print(f"   FRESH: Up to date")
    else:
        print("\n4. HARNESS: Not installed — run `python harness/generate.py`")

    # Save report
    report = {
        "date": datetime.now().isoformat(),
        "duplicates": len(dupes),
        "test_files": tests,
        "coverage_floor": floor,
        "regressions_14d": regressions,
    }
    report_file = root / "harness" / "health-report.json"
    report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport saved: {report_file}")


if __name__ == "__main__":
    main()
