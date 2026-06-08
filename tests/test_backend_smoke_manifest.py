"""Guard for the backend-unit-smoke manifest (tests/backend_smoke_suite.txt).

The smoke gate is only as honest as its manifest. If an agent under pressure
empties or guts the list to go green, the gate would pass while covering almost
nothing — a vacuous green (principle #3). These DB-free guards fail closed if
that happens: the manifest must name a real, non-trivial set of existing suites.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "tests" / "backend_smoke_suite.txt"

# The smoke set must not be silently shrunk below this. It is a floor, not a
# target — raise it as the core grows; never lower it to make a red gate pass.
MIN_SUITES = 20


def _listed_suites() -> list[str]:
    lines = MANIFEST.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]


def test_manifest_exists():
    assert MANIFEST.is_file(), "backend_smoke_suite.txt is missing"


def test_backend_smoke_suite_is_honest():
    """The manifest names at least MIN_SUITES real suites — fails closed if gutted."""
    suites = _listed_suites()
    assert len(suites) >= MIN_SUITES, (
        f"backend smoke manifest lists only {len(suites)} suites (floor {MIN_SUITES}) "
        f"— refusing a near-vacuous smoke gate"
    )


@pytest.mark.parametrize("rel", _listed_suites())
def test_listed_suite_exists(rel):
    """Every path in the manifest points at a real test file (no dead entries)."""
    assert (REPO_ROOT / rel).is_file(), f"{rel} listed in smoke manifest but not found"
