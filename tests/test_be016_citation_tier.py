"""BE-16 — citation tier propagation tests.

Pins the contract for ``services.llm.extract_citations_with_tier``
which the chat-response wiring consumes to surface a ``citations``
list with one item per ``[N]`` marker carrying ``source_tier`` and
the other EvidenceCard fields.
"""

from __future__ import annotations

import pytest


# ════════════════════════════════════════════════════════════════════
# extract_citations_with_tier
# ════════════════════════════════════════════════════════════════════

class TestExtractCitationsWithTier:
    def test_empty_inputs_return_empty_list(self):
        from services.llm import extract_citations_with_tier
        assert extract_citations_with_tier("", []) == []
        assert extract_citations_with_tier("hi", None) == []
        assert extract_citations_with_tier("", [{"source_id": "pubmed"}]) == []

    def test_uses_explicit_evidence_tier(self):
        """If evidence record carries source_tier (BE-1 wiring), use it."""
        from services.llm import extract_citations_with_tier

        evidence = [
            {
                "evidence_id": "ev-1",
                "source_id": "custom",
                "source_name": "Custom Source",
                "source_tier": "T1",
                "snippet": "Important.",
            },
        ]
        out = extract_citations_with_tier("Some narrative [1]. More text.", evidence)
        assert len(out) == 1
        assert out[0]["source_tier"] == "T1"
        assert out[0]["source_name"] == "Custom Source"
        assert out[0]["snippet"] == "Important."

    def test_falls_back_to_registry(self):
        """Without explicit tier, look up via lookup_source_metadata."""
        from services.llm import extract_citations_with_tier

        evidence = [
            {"evidence_id": "ev-1", "source_id": "pubmed", "snippet": "x"},
            {"evidence_id": "ev-2", "source_id": "clinical_trials_gov", "snippet": "y"},
        ]
        out = extract_citations_with_tier(
            "Findings from [1] and [2]…", evidence,
        )
        tiers = {c["source_tier"] for c in out}
        # pubmed → T3, clinical_trials_gov → T1
        assert tiers == {"T3", "T1"}

    def test_skips_invalid_markers(self):
        """[7] when only 3 evidence records exist must NOT crash."""
        from services.llm import extract_citations_with_tier
        evidence = [{"source_id": "pubmed"}]
        out = extract_citations_with_tier("Quote [1] and bogus [7].", evidence)
        assert len(out) == 1
        assert out[0]["n"] == 1

    def test_dedups_repeated_markers(self):
        from services.llm import extract_citations_with_tier
        evidence = [{"source_id": "pubmed"}, {"source_id": "fda"}]
        out = extract_citations_with_tier(
            "Per [1], the drug is approved [1]; see also [2].",
            evidence,
        )
        # Each [N] reported once even if cited multiple times
        ns = [c["n"] for c in out]
        assert ns == [1, 2]

    def test_preserves_order_of_first_use(self):
        """Citation order in output matches order of first appearance."""
        from services.llm import extract_citations_with_tier
        evidence = [
            {"source_id": "pubmed"},
            {"source_id": "fda"},
            {"source_id": "sec_edgar"},
        ]
        out = extract_citations_with_tier("[3] said one thing; [1] said another; [2] confirmed.", evidence)
        assert [c["n"] for c in out] == [3, 1, 2]

    def test_emits_source_url_and_published_at(self):
        from services.llm import extract_citations_with_tier
        from datetime import datetime, timezone

        ts = datetime(2026, 4, 1, tzinfo=timezone.utc)
        evidence = [
            {
                "source_id": "pubmed",
                "source_url": "https://pubmed.ncbi.nlm.nih.gov/123",
                "published_at": ts,
                "snippet": "x",
            },
        ]
        out = extract_citations_with_tier("Per [1].", evidence)
        assert out[0]["source_url"] == "https://pubmed.ncbi.nlm.nih.gov/123"
        assert out[0]["published_at"] == ts

    def test_field_shape_matches_spec(self):
        """The frontend ChipPill expects these exact keys."""
        from services.llm import extract_citations_with_tier
        evidence = [{"source_id": "pubmed", "snippet": "abc"}]
        out = extract_citations_with_tier("Per [1].", evidence)
        item = out[0]
        for key in (
            "n", "evidence_id", "source_id", "source_name",
            "source_tier", "published_at", "snippet", "source_url",
        ):
            assert key in item, f"missing key {key!r}"
