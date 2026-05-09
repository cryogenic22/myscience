"""Tests for SPEC_042 Centralized Product Backlog.

Two modules under test:
  - scripts/validate_product_backlog.py — schema + uniqueness + cross-ref validator
  - scripts/migrate_legacy_backlogs.py    — one-shot consolidator

Stage 3 (TDD): all tests fail until Stage 4 builds the modules.
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


# ── Schema validation ──


class TestProductBacklogSchema:
    """Each PB-NNN block must declare every required field with a valid value."""

    def test_validator_module_importable(self):
        from scripts import validate_product_backlog  # noqa: F401

    def test_well_formed_item_passes(self, tmp_path: Path):
        """An item with every required field + valid enum values passes."""
        from scripts.validate_product_backlog import validate_text

        body = textwrap.dedent(
            """
            # Product Backlog

            ## Dashboard

            | Status        | Count |
            |---------------|-------|
            | in-progress   | 1     |

            ## Items

            ### [PB-001] Sample item
            - **Type**: feature
            - **Status**: in-progress
            - **Priority**: high
            - **Owner**: frontend-claude
            - **Source**: spec
            - **Source ref**: SPEC-022
            - **Created**: 2026-05-09
            - **Last touched**: 2026-05-09
            - **Notes**: An example.
            """
        ).strip()
        report = validate_text(body, repo_root=REPO_ROOT)
        assert report.ok, report.errors

    def test_missing_required_field_fails(self):
        from scripts.validate_product_backlog import validate_text

        body = textwrap.dedent(
            """
            ## Items

            ### [PB-001] Missing priority
            - **Type**: feature
            - **Status**: triaged
            - **Owner**: frontend-claude
            - **Source**: adhoc
            - **Source ref**: n/a
            - **Created**: 2026-05-09
            - **Last touched**: 2026-05-09
            - **Notes**: Forgot priority.
            """
        ).strip()
        report = validate_text(body, repo_root=REPO_ROOT)
        assert not report.ok
        assert any("Priority" in err for err in report.errors)

    def test_invalid_enum_fails(self):
        from scripts.validate_product_backlog import validate_text

        body = textwrap.dedent(
            """
            ### [PB-001] Bad status
            - **Type**: feature
            - **Status**: WHATEVER
            - **Priority**: high
            - **Owner**: frontend-claude
            - **Source**: adhoc
            - **Source ref**: n/a
            - **Created**: 2026-05-09
            - **Last touched**: 2026-05-09
            - **Notes**: Status is invalid.
            """
        ).strip()
        report = validate_text(body, repo_root=REPO_ROOT)
        assert not report.ok
        assert any("Status" in err and "WHATEVER" in err for err in report.errors)


# ── ID uniqueness ──


class TestProductBacklogUniqueness:
    """PB-NNN identifiers must be globally unique within the file."""

    def test_duplicate_id_fails(self):
        from scripts.validate_product_backlog import validate_text

        body = textwrap.dedent(
            """
            ### [PB-007] First
            - **Type**: feature
            - **Status**: triaged
            - **Priority**: medium
            - **Owner**: unassigned
            - **Source**: adhoc
            - **Source ref**: n/a
            - **Created**: 2026-05-09
            - **Last touched**: 2026-05-09
            - **Notes**: a

            ### [PB-007] Duplicate
            - **Type**: bug
            - **Status**: proposed
            - **Priority**: low
            - **Owner**: unassigned
            - **Source**: adhoc
            - **Source ref**: n/a
            - **Created**: 2026-05-09
            - **Last touched**: 2026-05-09
            - **Notes**: b
            """
        ).strip()
        report = validate_text(body, repo_root=REPO_ROOT)
        assert not report.ok
        assert any("PB-007" in err and "duplicate" in err.lower() for err in report.errors)


# ── Cross references ──


class TestProductBacklogCrossReferences:
    """Source ref pointers and Blocked by references must resolve."""

    def test_unknown_spec_ref_fails(self, tmp_path: Path):
        from scripts.validate_product_backlog import validate_text

        body = textwrap.dedent(
            """
            ### [PB-001] Refers to a missing spec
            - **Type**: feature
            - **Status**: triaged
            - **Priority**: medium
            - **Owner**: backend-claude
            - **Source**: spec
            - **Source ref**: SPEC-9999
            - **Created**: 2026-05-09
            - **Last touched**: 2026-05-09
            - **Notes**: There is no SPEC-9999.
            """
        ).strip()
        report = validate_text(body, repo_root=REPO_ROOT)
        assert not report.ok
        assert any("SPEC-9999" in err for err in report.errors)

    def test_blocked_by_unknown_id_fails(self):
        from scripts.validate_product_backlog import validate_text

        body = textwrap.dedent(
            """
            ### [PB-001] Blocked on phantom
            - **Type**: feature
            - **Status**: blocked
            - **Priority**: high
            - **Owner**: unassigned
            - **Source**: adhoc
            - **Source ref**: n/a
            - **Blocked by**: PB-999
            - **Created**: 2026-05-09
            - **Last touched**: 2026-05-09
            - **Notes**: PB-999 doesn't exist.
            """
        ).strip()
        report = validate_text(body, repo_root=REPO_ROOT)
        assert not report.ok
        assert any("PB-999" in err for err in report.errors)


# ── Dashboard regeneration ──


class TestDashboardRegeneration:
    """`--regenerate-summary` rewrites the dashboard counts to match the body."""

    def test_regenerate_writes_correct_counts(self):
        from scripts.validate_product_backlog import regenerate_summary

        body = textwrap.dedent(
            """
            # Product Backlog

            ## Dashboard

            | Status        | Count |
            |---------------|-------|
            | in-progress   | 99    |

            ## Items

            ### [PB-001] One
            - **Type**: feature
            - **Status**: in-progress
            - **Priority**: high
            - **Owner**: frontend-claude
            - **Source**: adhoc
            - **Source ref**: n/a
            - **Created**: 2026-05-09
            - **Last touched**: 2026-05-09
            - **Notes**: a

            ### [PB-002] Two
            - **Type**: bug
            - **Status**: triaged
            - **Priority**: medium
            - **Owner**: unassigned
            - **Source**: adhoc
            - **Source ref**: n/a
            - **Created**: 2026-05-09
            - **Last touched**: 2026-05-09
            - **Notes**: b
            """
        ).strip()
        rebuilt = regenerate_summary(body)
        # Should contain "in-progress | 1" and "triaged | 1"
        assert "| in-progress" in rebuilt
        assert "| triaged" in rebuilt
        # The stale "99" must be gone
        assert "| 99" not in rebuilt


# ── Migration helper ──


class TestMigration:
    """Migrator extracts items from the legacy backlogs and emits PB-NNN rows."""

    def test_migrator_module_importable(self):
        from scripts import migrate_legacy_backlogs  # noqa: F401

    def test_migrator_skips_already_shipped_phases(self, tmp_path: Path):
        """ROADMAP Phases 0-2 are explicitly out per §10a.6 — must be skipped."""
        from scripts.migrate_legacy_backlogs import extract_roadmap_items

        roadmap = textwrap.dedent(
            """
            ## Phase 0 — Data Foundation (Week 1)

            ### Should be skipped
            Phase 0 is shipped.

            ## Phase 3 — Scientific Depth

            ### Should appear
            Phase 3 is in flight.
            """
        ).strip()
        items = extract_roadmap_items(roadmap)
        titles = [it["title"] for it in items]
        assert "Should appear" in titles
        assert "Should be skipped" not in titles

    def test_migrator_extracts_agent_backlog_open_asks(self):
        """Each `[BACKEND]` / `[FRONTEND]` open ask becomes one stub item."""
        from scripts.migrate_legacy_backlogs import extract_agent_backlog_stubs

        agent = textwrap.dedent(
            """
            ## [BACKEND] Sample backend ask
            - Filed: 2026-05-09 by Frontend Claude
            - Status: open

            ## [FRONTEND] Sample frontend ask
            - Filed: 2026-05-09 by Backend Claude
            - Status: done

            ## [BACKEND] Another open ask
            - Status: open
            """
        ).strip()
        stubs = extract_agent_backlog_stubs(agent)
        # Only the two `Status: open` entries become stubs.
        assert len(stubs) == 2
        titles = [s["title"] for s in stubs]
        assert "Sample backend ask" in titles
        assert "Another open ask" in titles
        assert "Sample frontend ask" not in titles  # already done


# ── Archive redirects ──


class TestArchiveRedirects:
    """Every file declared archived must have a redirect header at original path
    and exist at the new path under docs/archive/."""

    @pytest.mark.parametrize("category, original, archived", [
        ("brainstorms", "vision_rough.md", "docs/archive/brainstorms/vision_rough.md"),
        ("communications", "comp_intelligence.md", "docs/archive/communications/comp_intelligence.md"),
        ("legacy-backlogs", "BACKLOG.md", "docs/archive/legacy-backlogs/BACKLOG.md"),
    ])
    def test_archived_file_has_redirect_at_original_path(
        self, category: str, original: str, archived: str
    ):
        original_path = REPO_ROOT / original
        archived_path = REPO_ROOT / archived

        assert archived_path.exists(), f"Archive missing: {archived_path}"
        assert original_path.exists(), f"Redirect stub missing at: {original_path}"

        head = original_path.read_text(encoding="utf-8").splitlines()[0]
        assert "Archived" in head and "PRODUCT_BACKLOG" in head, (
            f"Original {original} lacks redirect header. First line was: {head!r}"
        )
