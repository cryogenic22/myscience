"""Migration-sequence integrity — Lane-1 deterministic, DB-free.

The failure this guards against (conservation principle 3, "no vacuous green"):
a migration applied to prod whose `.sql` file is missing from
`schema/migrations/`. `migrate.py` builds a database by applying every on-disk
file in number order and recording it in `schema_migrations`; a number that is
silently absent from disk means a *fresh* rebuild (a Railway redeploy that runs
the migrations from scratch, a new contributor, disaster recovery) produces a
schema missing the tables/columns that later migrations and application code
depend on — the "fresh-DB crash risk". Nothing checked the on-disk sequence was
complete, so migration 090 (fact governance) sat lost on `main` undetected.
This gate makes that class of loss fail closed at PR time.

Two explicit categories keep the allowance honest (no untracked tolerance):

  SKIPPED_NUMBERS  — numbers that were never authored (the sequence jumped
                     083 -> 087). Permanent, documented; no file is ever
                     expected for them.

  PENDING_RESTORE  — numbers that ARE real migrations, currently lost from
                     `main`, whose restoration is an in-flight PR. Each entry
                     MUST name its owning PR, and the allowance SELF-EXPIRES:
                     the moment the restored file lands on disk,
                     `test_pending_restore_self_expires` fails and forces the
                     entry's removal. A tolerated gap with no expiry is itself a
                     vacuous green; this one expires.

Any OTHER gap — a number neither present, skipped, nor pending — fails the gate.
That is the new-silent-loss signal.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = REPO_ROOT / "schema" / "migrations"

# Numbers the sequence intentionally skips — never authored. Documented so a
# gap here reads as a known hole, not a lost migration. (Verified against all
# git refs 2026-06-28: no 084/085/086 file has ever existed in any branch.)
SKIPPED_NUMBERS: dict[int, str] = {
    84: "never authored — sequence jumped 083_domain_forge -> 087_eval_runs",
    85: "never authored — sequence jumped 083_domain_forge -> 087_eval_runs",
    86: "never authored — sequence jumped 083_domain_forge -> 087_eval_runs",
}

# Real migrations lost from `main`, restoration in-flight. The value is the
# owning PR. This dict MUST shrink to empty as the PRs land — enforced by
# test_pending_restore_self_expires. Do NOT add a number here without a PR;
# that is enforced by test_pending_restore_entries_name_an_owner.
PENDING_RESTORE: dict[int, str] = {
    89: "PR #304 — restores 089_bioactivity_molecule_chembl_id.sql",
    90: "PR #185 — restores 090_fact_governance.sql",
}

FILENAME_RE = re.compile(r"^(\d{3})_[a-z0-9][a-z0-9_]*\.sql$")


def _migration_files() -> list[str]:
    return sorted(f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql"))


def _numbers_on_disk() -> list[int]:
    out: list[int] = []
    for f in _migration_files():
        m = FILENAME_RE.match(f)
        if m:
            out.append(int(m.group(1)))
    return out


def find_unexplained_gaps(
    numbers: list[int],
    skipped: dict[int, str] | set[int],
    pending: dict[int, str] | set[int],
) -> list[int]:
    """Pure core: numbers in [1, max(numbers)] that are absent AND neither
    skipped nor pending-restore. An empty list means the sequence is fully
    explained. Kept side-effect-free so it can be exercised on synthetic input
    (see test_gap_detector_catches_a_synthetic_loss).

    Scope: the range is bounded by the highest number ON DISK, so this catches
    *interior* loss (e.g. 090, lost between 089 and 091 — the realised failure
    mode) but NOT a migration lost ABOVE the current max; there is no DB-free
    source of the true ceiling. That top-edge hole self-closes the moment any
    higher migration lands. Documented in the runbook."""
    if not numbers:
        return []
    present = set(numbers)
    allowed = set(skipped) | set(pending)
    return [
        n
        for n in range(1, max(numbers) + 1)
        if n not in present and n not in allowed
    ]


# ── Filename hygiene ───────────────────────────────────────────────────────
def test_migration_filenames_wellformed():
    """Every .sql is NNN_lowercase_name.sql so the number parse is unambiguous
    and `migrate.py`'s sorted-by-filename apply order matches numeric order."""
    bad = [f for f in _migration_files() if not FILENAME_RE.match(f)]
    assert not bad, f"migration files not matching NNN_lowercase_name.sql: {bad}"


def test_no_duplicate_migration_numbers():
    nums = _numbers_on_disk()
    dupes = sorted({n for n in nums if nums.count(n) > 1})
    assert not dupes, f"duplicate migration numbers on disk: {dupes}"


# ── The core invariant: no unexplained gap ─────────────────────────────────
def test_no_unexplained_migration_gaps():
    nums = _numbers_on_disk()
    # Non-vacuous guard: find_unexplained_gaps returns [] on empty input, so an
    # empty schema/migrations/ would otherwise pass clean. The suite must fail
    # closed if the migrations vanish (mirrors test_auto_migrate's `total > 0`).
    assert nums, "no migration files found in schema/migrations/ — gate is vacuous"
    gaps = find_unexplained_gaps(nums, SKIPPED_NUMBERS, PENDING_RESTORE)
    assert not gaps, (
        f"Unexplained gap(s) in the migration sequence: {gaps}.\n"
        "A migration number is missing from schema/migrations/ that is neither a "
        "documented SKIPPED_NUMBER nor a tracked PENDING_RESTORE. If a migration "
        "was applied to prod but its file was never committed, a fresh-DB rebuild "
        "(`python migrate.py`) will be missing it. Commit the file, or — if it is "
        "a real lost migration being restored elsewhere — add it to PENDING_RESTORE "
        "with its owning PR in tests/test_migration_integrity.py."
    )


# ── Keep the allowances honest ─────────────────────────────────────────────
def test_skipped_and_pending_do_not_overlap():
    overlap = sorted(set(SKIPPED_NUMBERS) & set(PENDING_RESTORE))
    assert not overlap, f"a number is both skipped and pending-restore: {overlap}"


def test_pending_restore_entries_name_an_owner():
    """No number may sit in PENDING_RESTORE without a non-empty owning-PR string
    — stops the allowance becoming a silent dumping ground."""
    unowned = [n for n, owner in PENDING_RESTORE.items() if not (owner or "").strip()]
    assert not unowned, f"PENDING_RESTORE entries missing an owning PR: {unowned}"


@pytest.mark.parametrize("num", sorted(PENDING_RESTORE))
def test_pending_restore_self_expires(num):
    """The moment a pending migration's file lands on disk, its allowance is
    redundant and MUST be removed. This fails loudly to force that cleanup, so
    the tolerance cannot outlive the loss it documents (no expiry == vacuous)."""
    present = set(_numbers_on_disk())
    assert num not in present, (
        f"migration {num:03d} now has a file on disk — its restoration is "
        f"complete ({PENDING_RESTORE[num]}). Remove {num} from PENDING_RESTORE "
        f"in tests/test_migration_integrity.py (the allowance has expired)."
    )


# ── The gate has teeth (demonstrates the detector on synthetic input) ──────
def test_gap_detector_catches_a_synthetic_loss():
    # 4 is lost: present 1,2,3,5 with 4 neither skipped nor pending -> caught.
    assert find_unexplained_gaps([1, 2, 3, 5], {}, {}) == [4]
    # Same hole, explained as skipped -> clean.
    assert find_unexplained_gaps([1, 2, 3, 5], {4: "skipped"}, {}) == []
    # Same hole, explained as pending-restore -> clean.
    assert find_unexplained_gaps([1, 2, 3, 5], {}, {4: "PR #x"}) == []
    # Contiguous and empty inputs are both clean.
    assert find_unexplained_gaps([1, 2, 3], {}, {}) == []
    assert find_unexplained_gaps([], {}, {}) == []
