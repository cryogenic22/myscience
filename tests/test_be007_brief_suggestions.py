"""BE-7 — brief_suggestions service + endpoint tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ════════════════════════════════════════════════════════════════════
# Strategist baseline
# ════════════════════════════════════════════════════════════════════

class TestStrategistBaseline:
    def test_single_option_triggers_add_counter(self):
        from services.brief_suggestions import suggest
        out = suggest(current_text="Para one.\n\nPara two.", current_options=[{"id": "a"}])
        kinds = {s["kind"] for s in out}
        assert "add_counter" in kinds
        for s in out:
            if s["kind"] == "add_counter":
                assert s["agent"] == "strategist"

    def test_two_options_does_not_trigger_add_counter(self):
        from services.brief_suggestions import suggest
        out = suggest(current_text="Body", current_options=[{"id": "a"}, {"id": "b"}])
        assert not any(s["kind"] == "add_counter" and s["agent"] == "strategist" for s in out)

    def test_missing_stakeholder_for_commercial_brief(self):
        from services.brief_suggestions import suggest
        text = "We are evaluating commercial impact and regulatory exposure."
        out = suggest(current_text=text, current_options=[{"id": "a"}, {"id": "b"}])
        assert any(s["kind"] == "name_stakeholder" for s in out)


# ════════════════════════════════════════════════════════════════════
# Curator baseline
# ════════════════════════════════════════════════════════════════════

class TestCuratorBaseline:
    def test_evidence_score_is_emitted(self):
        from services.brief_suggestions import suggest
        out = suggest(
            current_text="Body",
            current_options=[{"id": "a"}, {"id": "b"}],
            evidence_refs=[
                {"evidence_id": "e1", "source_id": "fda"},
                {"evidence_id": "e2", "source_id": "pubmed"},
            ],
        )
        score_items = [s for s in out if s["kind"] == "evidence_score"]
        assert len(score_items) == 1
        assert score_items[0]["agent"] == "curator"
        assert "2/5" in score_items[0]["proposed_text"] or "2 distinct" in score_items[0]["rationale"]

    def test_contradicting_evidence_surfaces_card(self):
        from services.brief_suggestions import suggest
        out = suggest(
            current_text="x",
            current_options=[{"id": "a"}, {"id": "b"}],
            evidence_refs=[
                {"evidence_id": "e1", "source_id": "fda", "relation": "contradicts"},
            ],
        )
        kinds = {s["kind"] for s in out}
        assert "surface_contradiction" in kinds


# ════════════════════════════════════════════════════════════════════
# LLM augmentation
# ════════════════════════════════════════════════════════════════════

class TestLLMAugmentation:
    def test_llm_failure_drops_only_llm_card(self):
        from services.brief_suggestions import suggest

        llm = MagicMock()
        llm.enabled = True
        llm.raw_chat.side_effect = RuntimeError("model down")

        out = suggest(
            current_text="The brief.",
            current_options=[{"id": "a"}],
            evidence_refs=[],
            llm=llm,
        )
        # Heuristics still ran (add_counter from single option, evidence_score)
        assert any(s["kind"] == "add_counter" for s in out)

    def test_llm_response_appended_when_present(self):
        from services.brief_suggestions import suggest

        llm = MagicMock()
        llm.enabled = True
        llm.raw_chat.return_value = "Counter: hold position 4 weeks before reading SURPASS-CVOT."

        out = suggest(
            current_text="brief draft",
            current_options=[{"id": "a"}, {"id": "b"}],
            evidence_refs=[],
            llm=llm,
        )
        # The LLM-generated card has the rationale "LLM-generated counter-recommendation candidate."
        llm_cards = [s for s in out if "LLM-generated" in s["rationale"]]
        assert len(llm_cards) == 1


# ════════════════════════════════════════════════════════════════════
# stale_token
# ════════════════════════════════════════════════════════════════════

class TestStaleToken:
    def test_token_changes_when_text_changes(self):
        from services.brief_suggestions import stale_token
        a = stale_token("draft v1")
        b = stale_token("draft v2")
        assert a != b

    def test_token_stable_for_same_text(self):
        from services.brief_suggestions import stale_token
        assert stale_token("same") == stale_token("same")
