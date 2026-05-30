"""A2a — lint test: section builders in the Context Layer must NEVER swallow
exceptions silently into an empty result. They must surface as
UNAVAILABLE_ERROR with a reason.

This is the structural enforcement of "no silent empty section" — it pairs
with the FillState __post_init__ invariant in test_context_layer.py.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Files whose section-builder functions MUST NOT return empty on exception.
# (Add to this list as Context Layer composition grows.)
GUARDED_FILES = [
    "services/context_layer.py",
]

# Patterns that indicate a swallow: `except ...: return []`, `: return None`,
# `: return {}`, `: pass`, `: continue` inside an `except` block.
SWALLOW_PATTERNS = [
    re.compile(r"except[^:]*:\s*\n\s*return\s*\[\s*\]"),
    re.compile(r"except[^:]*:\s*\n\s*return\s*None\b"),
    re.compile(r"except[^:]*:\s*\n\s*return\s*\{\s*\}"),
    re.compile(r"except[^:]*:\s*\n\s*pass\b"),
    re.compile(r"except[^:]*:\s*return\s*\[\s*\]"),
    re.compile(r"except[^:]*:\s*return\s*None\b"),
    re.compile(r"except[^:]*:\s*return\s*\{\s*\}"),
    re.compile(r"except[^:]*:\s*pass\b"),
]

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("filename", GUARDED_FILES)
def test_no_silent_empty_swallows(filename):
    """Forbid silent-empty exception swallows inside Context Layer section builders.

    The Context Layer's contract is that every section returns with an explicit
    FillState. A bare `except: return []` violates that contract — the section
    silently disappears with no reason. This test fails any new code that does it.
    """
    p = REPO_ROOT / filename
    if not p.exists():
        pytest.skip(f"{filename} not yet present")
    src = p.read_text(encoding="utf-8")

    # Find the body inside any function/method called *section* or build_*_section
    # — those are section builders. (We allow swallows OUTSIDE section builders;
    # for example a top-level `query_facts` may catch DB errors and re-raise as
    # ContextContractError — that's caught separately by being not a section-build.)
    # Simpler check for the skeleton phase: assert no swallow patterns anywhere
    # in the module. We tighten this as the file grows.
    violations: list[str] = []
    for pat in SWALLOW_PATTERNS:
        for m in pat.finditer(src):
            line_no = src[: m.start()].count("\n") + 1
            violations.append(f"{filename}:{line_no} matched {pat.pattern!r}")

    assert not violations, (
        "Context Layer section builders must not silently swallow exceptions:\n"
        + "\n".join(violations)
    )
