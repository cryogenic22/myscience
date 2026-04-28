"""Epic 1 α1 — LLM extractor wrapper (TDD).

Generic Anthropic/OpenAI tool-use wrapper that binds the 4 Pydantic
schemas (ExecChange, Deal, Financial+Guidance, CRL). Factory functions
produce extractors conforming to each parser's Protocol so the existing
A2.x parsers can use them without modification.

Critical: this whole module is unit-testable without network calls. We
use a fake `StructuredCall` callable that records its inputs and returns
canned dict responses. The Anthropic + OpenAI adapters are tested with
mocked SDK clients — no real API calls.

Test categories:
  Cat 1 — Generic extract_structured() helper
  Cat 2 — Per-schema factories (4 of them)
  Cat 3 — Anthropic adapter: tool-use call shape + response parsing
  Cat 4 — Retry / error handling
  Cat 5 — Conformance: each factory's output satisfies the parser Protocol
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pytest


# ────────────────────────────────────────────────────────────────────
# Cat 1 — Generic extract_structured helper
# ────────────────────────────────────────────────────────────────────


class TestExtractStructured:

    def test_module_exists(self):
        from services.extraction_llm import extract_structured  # noqa: F401

    def test_happy_path_returns_validated_pydantic(self):
        from services.extraction_llm import extract_structured
        from services.extraction.exec_change import ExecChangeExtraction

        # Fake structured call that returns a valid dict
        captured: dict[str, Any] = {}

        def fake_call(system_prompt: str, user_prompt: str, schema: dict) -> dict:
            captured["system_prompt"] = system_prompt
            captured["user_prompt"] = user_prompt
            captured["schema"] = schema
            return {
                "person_name": "Mikael Dolsten",
                "change_type": "departure",
                "effective_date": "2026-06-30",
                "prior_role": "Chief Scientific Officer",
                "functional_area": "CSO",
            }

        result = extract_structured(
            block="some 8-K text",
            system_prompt="extract executive changes",
            schema_class=ExecChangeExtraction,
            structured_call=fake_call,
        )

        assert result is not None
        assert isinstance(result, ExecChangeExtraction)
        assert result.person_name == "Mikael Dolsten"
        # The wrapper passed our prompts and the JSON schema through
        assert captured["user_prompt"] == "some 8-K text"
        assert "$schema" in captured["schema"] or "type" in captured["schema"]

    def test_empty_response_returns_none(self):
        from services.extraction_llm import extract_structured
        from services.extraction.exec_change import ExecChangeExtraction

        def fake_call(s, u, sch):
            return None

        result = extract_structured(
            block="text",
            system_prompt="prompt",
            schema_class=ExecChangeExtraction,
            structured_call=fake_call,
        )
        assert result is None

    def test_validation_failure_returns_none(self):
        """A response that fails Pydantic validation must NOT raise — the
        parser orchestrator catches None gracefully."""
        from services.extraction_llm import extract_structured
        from services.extraction.exec_change import ExecChangeExtraction

        def fake_call(s, u, sch):
            return {"this_is_not_a_valid_field": "garbage"}

        result = extract_structured(
            block="text",
            system_prompt="prompt",
            schema_class=ExecChangeExtraction,
            structured_call=fake_call,
        )
        assert result is None

    def test_callable_exception_returns_none(self):
        """If the LLM call raises (network, rate limit), wrapper returns
        None and logs — never propagates the exception to the parser."""
        from services.extraction_llm import extract_structured
        from services.extraction.exec_change import ExecChangeExtraction

        def fake_call(s, u, sch):
            raise ConnectionError("simulated")

        result = extract_structured(
            block="text",
            system_prompt="prompt",
            schema_class=ExecChangeExtraction,
            structured_call=fake_call,
        )
        assert result is None


# ────────────────────────────────────────────────────────────────────
# Cat 2 — Per-schema factories
# ────────────────────────────────────────────────────────────────────


class TestExecChangeFactory:

    def test_factory_returns_extractor_conforming_to_protocol(self):
        from services.extraction_llm import make_exec_change_extractor

        def noop(s, u, sch):
            return {"extractions": []}

        ex = make_exec_change_extractor(structured_call=noop)
        # Duck-type Protocol conformance
        assert hasattr(ex, "extract") and callable(ex.extract)

    def test_factory_returns_list_on_happy_path(self):
        from services.extraction_llm import make_exec_change_extractor

        def fake_call(s, u, sch):
            return {
                "extractions": [
                    {
                        "person_name": "Mikael Dolsten",
                        "change_type": "departure",
                        "effective_date": "2026-06-30",
                        "functional_area": "CSO",
                    },
                ],
            }

        ex = make_exec_change_extractor(structured_call=fake_call)
        results = ex.extract("some block")
        assert len(results) == 1
        assert results[0].person_name == "Mikael Dolsten"

    def test_factory_returns_empty_on_no_extractions(self):
        from services.extraction_llm import make_exec_change_extractor

        def fake_call(s, u, sch):
            return {"extractions": []}

        ex = make_exec_change_extractor(structured_call=fake_call)
        assert ex.extract("some block") == []

    def test_factory_returns_empty_on_call_failure(self):
        from services.extraction_llm import make_exec_change_extractor

        def fake_call(s, u, sch):
            raise RuntimeError("simulated")

        ex = make_exec_change_extractor(structured_call=fake_call)
        assert ex.extract("some block") == []

    def test_factory_drops_individual_invalid_extractions(self):
        """If one item in `extractions[]` fails validation, the others
        still pass through — defence-in-depth."""
        from services.extraction_llm import make_exec_change_extractor

        def fake_call(s, u, sch):
            return {
                "extractions": [
                    {"this_is": "garbage"},
                    {
                        "person_name": "Lucas Montarce",
                        "change_type": "appointment",
                        "effective_date": "2026-06-01",
                        "functional_area": "CFO",
                    },
                ],
            }

        ex = make_exec_change_extractor(structured_call=fake_call)
        results = ex.extract("block")
        assert len(results) == 1
        assert results[0].person_name == "Lucas Montarce"


class TestDealFactory:

    def test_returns_list_with_composite_deal_types(self):
        from services.extraction_llm import make_deal_extractor

        def fake_call(s, u, sch):
            return {
                "extractions": [
                    {
                        "deal_types": ["license_in", "co_development", "option"],
                        "announced_date": "2026-04-22",
                        "licensor_name": "Pivotal Bio",
                        "licensee_name": "Pfizer",
                        "upfront_value_usd": 50_000_000,
                        "milestones_total_usd": 500_000_000,
                    },
                ],
            }

        ex = make_deal_extractor(structured_call=fake_call)
        results = ex.extract("block")
        assert len(results) == 1
        assert "license_in" in results[0].deal_types
        assert "co_development" in results[0].deal_types


class TestFinancialFactory:

    def test_returns_tuple_disclosure_plus_guidances(self):
        from services.extraction_llm import make_financial_extractor

        def fake_call(s, u, sch):
            return {
                "financial_disclosure": {
                    "fiscal_period_end": "2026-03-31",
                    "fiscal_period_label": "Q1 2026",
                    "metrics": [
                        {"name": "revenue", "basis": "GAAP",
                         "value_usd": 14_900_000_000},
                    ],
                },
                "guidance_issuances": [
                    {
                        "issued_at": "2026-04-30",
                        "metric": "revenue",
                        "period_label": "FY2026",
                        "basis": "non-GAAP",
                        "direction": "raise",
                        "range_low": 61_000_000_000,
                        "range_high": 64_000_000_000,
                    },
                ],
            }

        ex = make_financial_extractor(structured_call=fake_call)
        disclosure, guidances = ex.extract("block")
        assert disclosure is not None
        assert disclosure.fiscal_period_label == "Q1 2026"
        assert len(guidances) == 1
        assert guidances[0].direction == "raise"

    def test_returns_none_disclosure_on_disclosure_only_omitted(self):
        from services.extraction_llm import make_financial_extractor

        def fake_call(s, u, sch):
            return {
                "financial_disclosure": None,
                "guidance_issuances": [],
            }

        ex = make_financial_extractor(structured_call=fake_call)
        disclosure, guidances = ex.extract("block")
        assert disclosure is None
        assert guidances == []

    def test_financial_failure_returns_none_tuple(self):
        from services.extraction_llm import make_financial_extractor

        def fake_call(s, u, sch):
            raise ConnectionError("network")

        ex = make_financial_extractor(structured_call=fake_call)
        disclosure, guidances = ex.extract("block")
        assert disclosure is None
        assert guidances == []


class TestCRLFactory:

    def test_returns_list_with_reason_categories(self):
        from services.extraction_llm import make_crl_extractor

        def fake_call(s, u, sch):
            return {
                "extractions": [
                    {
                        "agency": "FDA",
                        "received_date": "2026-04-28",
                        "application_type": "NDA",
                        "application_number": "218237",
                        "drug_name": "SRP-9001",
                        "indication": "Duchenne muscular dystrophy",
                        "reason_categories": [
                            "additional_efficacy_data", "manufacturing_cmc",
                        ],
                    },
                ],
            }

        ex = make_crl_extractor(structured_call=fake_call)
        results = ex.extract("block")
        assert len(results) == 1
        assert results[0].drug_name == "SRP-9001"
        assert "manufacturing_cmc" in results[0].reason_categories


# ────────────────────────────────────────────────────────────────────
# Cat 3 — Anthropic adapter
# ────────────────────────────────────────────────────────────────────


class TestAnthropicAdapter:

    def test_module_has_anthropic_factory(self):
        from services.extraction_llm import make_anthropic_structured_call  # noqa: F401

    def test_anthropic_call_passes_correct_tool_spec(self):
        """The adapter must invoke client.messages.create with a tool
        whose input_schema matches the JSON schema we passed in, and
        force tool_choice to that specific tool."""
        from services.extraction_llm import make_anthropic_structured_call

        # Mock the Anthropic client
        mock_client = MagicMock()
        # Build a fake response with one tool_use block
        tool_use = MagicMock()
        tool_use.type = "tool_use"
        tool_use.input = {"person_name": "X", "change_type": "departure",
                          "effective_date": "2026-06-30"}
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "preamble"
        mock_response = MagicMock()
        mock_response.content = [text_block, tool_use]
        mock_client.messages.create.return_value = mock_response

        call = make_anthropic_structured_call(client=mock_client, model="claude-x")
        schema = {"type": "object", "properties": {"person_name": {"type": "string"}}}
        result = call("system", "user-text", schema)

        # Returned the tool_use input
        assert result == {"person_name": "X", "change_type": "departure",
                          "effective_date": "2026-06-30"}

        # Verify the SDK call was made correctly
        mock_client.messages.create.assert_called_once()
        kwargs = mock_client.messages.create.call_args.kwargs
        assert kwargs["model"] == "claude-x"
        assert kwargs["system"] == "system"
        assert kwargs["messages"] == [{"role": "user", "content": "user-text"}]
        # Tool spec
        assert len(kwargs["tools"]) == 1
        assert kwargs["tools"][0]["input_schema"] == schema
        # Forced tool_choice
        tc = kwargs["tool_choice"]
        assert tc["type"] == "tool"

    def test_anthropic_returns_none_when_no_tool_use(self):
        from services.extraction_llm import make_anthropic_structured_call

        mock_client = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "no tool"
        mock_response = MagicMock()
        mock_response.content = [text_block]
        mock_client.messages.create.return_value = mock_response

        call = make_anthropic_structured_call(client=mock_client, model="claude-x")
        result = call("system", "user", {"type": "object"})
        assert result is None


# ────────────────────────────────────────────────────────────────────
# Cat 4 — Conformance to parser Protocols
# ────────────────────────────────────────────────────────────────────


class TestProtocolConformance:

    def test_exec_change_factory_passes_protocol_to_parse_item_5_02(self):
        """End-to-end protocol satisfaction: the factory output works as
        the `extractor` argument to parse_item_5_02 — proving the wrapper
        plugs into A2.1 cleanly."""
        from services.extraction_llm import make_exec_change_extractor
        from connectors.sec_8k.item_5_02 import parse_item_5_02

        def fake_call(s, u, sch):
            return {
                "extractions": [
                    {
                        "person_name": "Anat Ashkenazi",
                        "change_type": "departure",
                        "effective_date": "2026-05-30",
                        "functional_area": "CFO",
                    },
                ],
            }

        ex = make_exec_change_extractor(structured_call=fake_call)
        text = (
            "Item 5.02 Departure of Directors or Certain Officers.\n"
            "On April 20, 2026, Anat Ashkenazi notified the Company of her "
            "decision to leave effective May 30, 2026.\n"
            "Item 9.01 Financial Statements and Exhibits."
        )
        results = parse_item_5_02(text, extractor=ex)
        assert len(results) == 1
        assert results[0].person_name == "Anat Ashkenazi"

    def test_deal_factory_passes_protocol_to_parse_item_1_01(self):
        from services.extraction_llm import make_deal_extractor
        from connectors.sec_8k.item_1_01 import parse_item_1_01

        def fake_call(s, u, sch):
            return {
                "extractions": [
                    {
                        "deal_types": ["license_in"],
                        "announced_date": "2026-04-22",
                        "licensor_name": "Pivotal",
                        "licensee_name": "Pfizer",
                    },
                ],
            }

        ex = make_deal_extractor(structured_call=fake_call)
        text = (
            "Item 1.01 Entry into a Material Definitive Agreement.\n"
            "On April 22, 2026, Pfizer entered into a license with Pivotal.\n"
            "Item 9.01"
        )
        results = parse_item_1_01(text, extractor=ex)
        assert len(results) == 1

    def test_crl_factory_passes_protocol_to_parse_item_8_01(self):
        from services.extraction_llm import make_crl_extractor
        from connectors.sec_8k.item_8_01 import parse_item_8_01

        def fake_call(s, u, sch):
            return {
                "extractions": [
                    {
                        "agency": "FDA",
                        "received_date": "2026-04-28",
                        "application_type": "NDA",
                        "application_number": "218237",
                    },
                ],
            }

        ex = make_crl_extractor(structured_call=fake_call)
        text = (
            "Item 8.01 Other Events.\n"
            "On April 28, 2026, the Company received a Complete Response "
            "Letter from the FDA.\n"
            "Item 9.01"
        )
        results = parse_item_8_01(text, extractor=ex)
        assert len(results) == 1

    def test_financial_factory_passes_protocol_to_parse_item_2_02(self):
        from services.extraction_llm import make_financial_extractor
        from connectors.sec_8k.item_2_02 import parse_item_2_02

        def fake_call(s, u, sch):
            return {
                "financial_disclosure": {
                    "fiscal_period_end": "2026-03-31",
                    "fiscal_period_label": "Q1 2026",
                    "metrics": [
                        {"name": "revenue", "basis": "GAAP",
                         "value_usd": 14_900_000_000},
                    ],
                },
                "guidance_issuances": [],
            }

        ex = make_financial_extractor(structured_call=fake_call)
        text = (
            "Item 2.02 Results of Operations and Financial Condition.\n"
            "Q1 2026 revenue $14.9B.\n"
            "Item 9.01"
        )
        result = parse_item_2_02(text, extractor=ex)
        assert result.financial_disclosure is not None
        assert result.financial_disclosure.fiscal_period_label == "Q1 2026"
