"""BE-1 — evidence_records card fields tests.

Covers the migration shape, the source registry / snippet helper,
the in-row default substitution, the EvidenceItemResponse schema,
and the backfill script.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ════════════════════════════════════════════════════════════════════
# Migration 068 shape
# ════════════════════════════════════════════════════════════════════

class TestMigration068:
    def _sql(self) -> str:
        path = (
            Path(__file__).parent.parent
            / "schema" / "migrations" / "068_evidence_card_fields.sql"
        )
        assert path.exists(), f"missing {path.name}"
        return path.read_text(encoding="utf-8").lower()

    def test_adds_four_columns(self):
        sql = self._sql()
        for col in ("source_name", "source_tier", "published_at", "snippet"):
            assert col in sql, f"migration must mention {col}"

    def test_tier_check_constraint(self):
        sql = self._sql()
        assert "t1" in sql and "t2" in sql and "t3" in sql and "t4" in sql, (
            "source_tier must be CHECK-constrained to T1..T4"
        )

    def test_snippet_length_check(self):
        sql = self._sql()
        assert "char_length(snippet)" in sql or "length(snippet)" in sql, (
            "snippet must be length-bounded"
        )

    def test_widens_append_only_trigger(self):
        sql = self._sql()
        # The trigger must mention each new column so first-fill is allowed
        assert "evidence_records_append_only" in sql
        for col in ("source_name", "source_tier", "published_at", "snippet"):
            assert col in sql.split("create or replace function evidence_records_append_only")[1], (
                f"{col} must be allow-listed in the trigger first-fill block"
            )

    def test_idempotent(self):
        sql = self._sql()
        assert "if not exists" in sql, "ALTER must guard with IF NOT EXISTS"


# ════════════════════════════════════════════════════════════════════
# Source registry
# ════════════════════════════════════════════════════════════════════

class TestSourceRegistry:
    @pytest.mark.parametrize("source_id,expected_tier", [
        ("clinical_trials_gov", "T1"),
        ("CLINICALTRIALS.GOV", "T1"),
        ("openfda_faers_pull_2026_05", "T1"),  # substring match
        ("fda_orange_book", "T1"),
        ("uspto", "T1"),
        ("who_ictrp", "T1"),
        ("sec_edgar", "T2"),
        ("pubmed", "T3"),
        ("biorxiv", "T3"),
        ("aacr", "T3"),
    ])
    def test_known_source_tier(self, source_id, expected_tier):
        from services.evidence_ledger import lookup_source_metadata
        _, tier = lookup_source_metadata(source_id)
        assert tier == expected_tier

    def test_unknown_source_falls_back_to_t3(self):
        from services.evidence_ledger import lookup_source_metadata
        name, tier = lookup_source_metadata("totally_made_up_source")
        # Per spec — unknown defaults to (source_id verbatim, T3)
        assert name == "totally_made_up_source"
        assert tier == "T3"

    def test_empty_source_returns_none(self):
        from services.evidence_ledger import lookup_source_metadata
        assert lookup_source_metadata("") == (None, None)

    def test_friendly_names_used(self):
        from services.evidence_ledger import lookup_source_metadata
        name, _ = lookup_source_metadata("clinical_trials_gov")
        assert name == "ClinicalTrials.gov"
        name, _ = lookup_source_metadata("pubmed")
        assert name == "PubMed"


# ════════════════════════════════════════════════════════════════════
# make_snippet
# ════════════════════════════════════════════════════════════════════

class TestMakeSnippet:
    def test_short_text_returned_verbatim(self):
        from services.evidence_ledger import make_snippet
        out = make_snippet("This is a short claim.")
        assert out == "This is a short claim."

    def test_long_text_truncated_at_sentence(self):
        from services.evidence_ledger import make_snippet
        text = (
            "Tirzepatide reduced HbA1c by 2.4 percentage points in the SURMOUNT-2 trial. "
            "The drug also drove substantial weight loss compared to placebo. "
            "Cardiovascular outcomes remain under investigation in SURPASS-CVOT."
        )
        out = make_snippet(text, max_chars=100)
        # Must end at a sentence boundary, ellipsis appended
        assert out.endswith(" …")
        # Cuts at the period
        assert "SURMOUNT-2 trial." in out
        assert "Cardiovascular" not in out

    def test_collapses_whitespace(self):
        from services.evidence_ledger import make_snippet
        out = make_snippet("Line one.\n\n  Line   two.\nLine three.")
        assert "\n" not in out
        assert "  " not in out

    def test_empty_returns_none(self):
        from services.evidence_ledger import make_snippet
        assert make_snippet("") is None
        assert make_snippet(None) is None


# ════════════════════════════════════════════════════════════════════
# _row_to_evidence default substitution
# ════════════════════════════════════════════════════════════════════

class TestRowToEvidenceDefaults:
    def test_falls_back_to_registry_when_columns_null(self):
        from services.evidence_ledger import _row_to_evidence

        row = {
            "evidence_id": "ev-1",
            "source_id": "pubmed",
            "source_url": "https://pubmed.ncbi.nlm.nih.gov/123",
            "source_content_hash": b"\x00" * 32,
            "archived_snapshot_ref": None,
            "retrieved_at": datetime(2026, 5, 10, tzinfo=timezone.utc),
            "extraction_method": {},
            "extracted_text": "Tirzepatide showed superior HbA1c reduction.",
            "confidence": 0.9,
            "retrieved_by_user_id": None,
            "created_at": datetime(2026, 5, 10, tzinfo=timezone.utc),
            "source_name": None,
            "source_tier": None,
            "published_at": None,
            "snippet": None,
        }
        ev = _row_to_evidence(row)
        # Filled from registry
        assert ev.source_name == "PubMed"
        assert ev.source_tier == "T3"
        # Snippet auto-generated from extracted_text
        assert ev.snippet is not None
        assert "Tirzepatide" in ev.snippet

    def test_explicit_columns_take_precedence(self):
        from services.evidence_ledger import _row_to_evidence

        row = {
            "evidence_id": "ev-2",
            "source_id": "pubmed",
            "source_url": None,
            "source_content_hash": b"\x00" * 32,
            "archived_snapshot_ref": None,
            "retrieved_at": datetime(2026, 5, 10, tzinfo=timezone.utc),
            "extraction_method": {},
            "extracted_text": "x",
            "confidence": None,
            "retrieved_by_user_id": None,
            "created_at": datetime(2026, 5, 10, tzinfo=timezone.utc),
            "source_name": "Custom Name Override",
            "source_tier": "T1",
            "published_at": datetime(2026, 4, 1, tzinfo=timezone.utc),
            "snippet": "Custom snippet override.",
        }
        ev = _row_to_evidence(row)
        assert ev.source_name == "Custom Name Override"
        assert ev.source_tier == "T1"
        assert ev.snippet == "Custom snippet override."


# ════════════════════════════════════════════════════════════════════
# EvidenceItemResponse schema
# ════════════════════════════════════════════════════════════════════

class TestEvidenceItemResponseSchema:
    def test_new_fields_present_and_optional(self):
        from api.schemas import EvidenceItemResponse

        # Should accept a payload with the four new fields populated
        item = EvidenceItemResponse(
            source="pubmed",
            entity_type="drug",
            entity_id="drug-1",
            content="Tirzepatide…",
            relevance=0.92,
            provenance={"url": "https://pubmed.ncbi.nlm.nih.gov/123"},
            source_name="PubMed",
            source_tier="T3",
            published_at="2026-04-01T00:00:00Z",
            snippet="Tirzepatide showed superior HbA1c reduction.",
        )
        assert item.source_name == "PubMed"
        assert item.source_tier == "T3"

        # And legacy producers (no new fields) still work
        legacy = EvidenceItemResponse(
            source="pubmed",
            entity_type="drug",
            entity_id="drug-2",
            content="...",
            relevance=0.5,
            provenance={},
        )
        assert legacy.source_name is None
        assert legacy.source_tier is None
        assert legacy.snippet is None


# ════════════════════════════════════════════════════════════════════
# Backfill script
# ════════════════════════════════════════════════════════════════════

class TestBackfillScript:
    def test_module_importable(self):
        import scripts.backfill_evidence_card_fields as mod
        assert hasattr(mod, "run")

    def test_dry_run_does_not_update(self):
        from scripts.backfill_evidence_card_fields import run

        db = MagicMock()
        db.fetch_all.return_value = [
            {
                "evidence_id": "ev-1",
                "source_id": "pubmed",
                "extracted_text": "Tirzepatide reduced HbA1c by 2.4 percentage points.",
                "retrieved_at": datetime(2026, 5, 10, tzinfo=timezone.utc),
                "source_name": None,
                "source_tier": None,
                "published_at": None,
                "snippet": None,
            }
        ]

        summary = run(db, batch=10, dry_run=True)
        assert summary["matched"] == 1
        assert summary["updated"] == 1
        assert summary["dry_run"] is True
        # No UPDATE evidence_records SET ... should fire
        update_calls = [
            c for c in db.execute.call_args_list
            if c.args and "update evidence_records" in str(c.args[0]).lower()
        ]
        assert update_calls == []

    def test_apply_writes_update_with_coalesce(self):
        from scripts.backfill_evidence_card_fields import run

        db = MagicMock()
        db.fetch_all.return_value = [
            {
                "evidence_id": "ev-2",
                "source_id": "pubmed",
                "extracted_text": "Tirzepatide x.",
                "retrieved_at": datetime(2026, 5, 10, tzinfo=timezone.utc),
                "source_name": None,
                "source_tier": None,
                "published_at": None,
                "snippet": None,
            }
        ]

        summary = run(db, batch=10, dry_run=False)
        assert summary["updated"] == 1
        update_sqls = [
            str(c.args[0]).lower() for c in db.execute.call_args_list
            if c.args and "update evidence_records" in str(c.args[0]).lower()
        ]
        assert len(update_sqls) == 1
        # Must use COALESCE so a row that already has source_name set
        # by another writer is not clobbered.
        assert "coalesce" in update_sqls[0]
