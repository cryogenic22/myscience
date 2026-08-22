"""Protected-surface integrity (harness Step 2) — deterministic, DB-free.

Proves the three faces of the boundary never drift:
  1. protected-surface.txt exists and lists real paths (fail-closed if missing).
  2. Every listed path still EXISTS on disk — a protected file silently
     deleted/renamed without updating the list is itself suspicious.
  3. .github/CODEOWNERS equals what scripts/gen_codeowners.py would generate
     (hook = CODEOWNERS = list, the ADR-0003 A1.1 invariant).

Principle 4 (Structural floor over discipline): CODEOWNERS/branch protection is
the floor; this test keeps its source of truth honest. Runs in the Lane-1 gate.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SURFACE = REPO_ROOT / "protected-surface.txt"
RESERVED = REPO_ROOT / "reserved-protected-paths.txt"
CODEOWNERS = REPO_ROOT / ".github" / "CODEOWNERS"


def _surface_lines() -> list[str]:
    lines = []
    for raw in SURFACE.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            lines.append(line)
    return lines


def _reserved_lines() -> list[str]:
    lines = []
    for raw in RESERVED.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            lines.append(line)
    return lines


def test_protected_surface_exists_and_nonempty():
    assert SURFACE.exists(), "protected-surface.txt missing (fail-closed)"
    assert _surface_lines(), "protected-surface.txt defines no paths (fail-closed)"
    assert RESERVED.exists(), "reserved-protected-paths.txt missing (fail-closed)"
    assert _reserved_lines(), "reserved-protected-paths.txt is empty (fail-closed)"
    assert set(_surface_lines()).isdisjoint(_reserved_lines())


@pytest.mark.parametrize("rel", _surface_lines() if SURFACE.exists() else [])
def test_every_protected_path_exists(rel):
    """A protected path that no longer exists means the bar moved without the
    list being updated — surface it."""
    p = REPO_ROOT / rel
    assert p.exists(), (
        f"protected path '{rel}' does not exist — the success-definition surface "
        f"changed without updating protected-surface.txt"
    )


def test_codeowners_in_sync_with_surface():
    """CODEOWNERS must equal the generator output (no hand-drift)."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "gen_codeowners.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"CODEOWNERS out of sync with protected-surface.txt — run "
        f"`python scripts/gen_codeowners.py`.\n{result.stdout}\n{result.stderr}"
    )


def _is_protected(path: str) -> bool:
    return any(
        path == entry.rstrip("/")
        or (entry.endswith("/") and path.startswith(entry))
        for entry in (*_surface_lines(), *_reserved_lines())
    )


def test_coordination_exam_tests_and_dependency_manifests_are_protected():
    graph = json.loads(
        (REPO_ROOT / "coordination" / "contracts" / "work_graph.json").read_text(
            encoding="utf-8"
        )
    )
    declared_tests = {
        verifier.removeprefix("test:")
        for item in graph["items"]
        for criterion in item["spec"]["acceptance"].values()
        for verifier in criterion["verification"]
        if isinstance(verifier, str) and verifier.startswith("test:")
    }
    workflow = (
        REPO_ROOT / ".github" / "workflows" / "coordination-gate.yml"
    ).read_text(encoding="utf-8")
    dependency_manifests = set(re.findall(r"pip install -r ([A-Za-z0-9_./-]+)", workflow))

    required = declared_tests | dependency_manifests | {
        "tests/test_protected_surface_sync.py"
    }
    assert required
    assert {path for path in required if not _is_protected(path)} == set()

    executable_tests = {
        verifier.removeprefix("test:")
        for item in graph["items"]
        if item["contract_status"] == "executable"
        for criterion in item["spec"]["acceptance"].values()
        for verifier in criterion["verification"]
        if isinstance(verifier, str) and verifier.startswith("test:")
    }
    assert executable_tests
    assert executable_tests <= set(_surface_lines())
