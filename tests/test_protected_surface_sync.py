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

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SURFACE = REPO_ROOT / "protected-surface.txt"
CODEOWNERS = REPO_ROOT / ".github" / "CODEOWNERS"


def _surface_lines() -> list[str]:
    lines = []
    for raw in SURFACE.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            lines.append(line)
    return lines


def test_protected_surface_exists_and_nonempty():
    assert SURFACE.exists(), "protected-surface.txt missing (fail-closed)"
    assert _surface_lines(), "protected-surface.txt defines no paths (fail-closed)"


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
