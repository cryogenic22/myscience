"""Cycle 4 — Press-release-as-readout extraction (A3.3).

Tests three layers:

  1. Pydantic schema (services/extraction/trial_readout.TrialReadoutExtraction)
     — field validation, enum constraints, conditional rules.

  2. LLM extractor factory (services/extraction_llm.make_trial_readout_extractor)
     — verified with a stub StructuredCall (no real LLM) so tests are fast
     and deterministic.

  3. Event emitter (services/event_emitters/trial_readout.build_event_row)
     — produces a dict shaped for INSERT INTO market_events with a
     deterministic event_hash.

A press-release readout is a tier-2 signal (company self-reported,
later corroborated by CT.gov posted_results, journal pub, FDA approval).
The event is born with confidence_tier="reported" — promoted to
"confirmed" by the corroboration loop when CT.gov / FDA confirm.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

import pytest


# ────────────────────────────────────────────────────────────────────
# Cat 1 — Schema basics
# ────────────────────────────────────────────────────────────────────


class TestSchemaShape:

    def test_module_imports(self):
        from services.extraction.trial_readout import TrialReadoutExtraction  # noqa: F401

    def test_minimal_payload_validates(self):
        from services.extraction.trial_readout import TrialReadoutExtraction
        ex = TrialReadoutExtraction(
            trial_identifier="NCT01234567",
            drug_name="Test-101",
            indication="HER2-positive breast cancer",
            primary_endpoint_met=True,
            readout_date=date(2026, 4, 15),
            phase="Phase 3",
            headline_summary="Met primary endpoint with statistically "
                             "significant improvement in PFS.",
        )
        assert ex.trial_identifier == "NCT01234567"
        assert ex.primary_endpoint_met is True

    def test_extra_fields_forbidden(self):
        from services.extraction.trial_readout import TrialReadoutExtraction
        with pytest.raises(Exception):
            TrialReadoutExtraction(
                trial_identifier="NCT01234567",
                drug_name="X",
                primary_endpoint_met=True,
                readout_date=date(2026, 1, 1),
                phase="Phase 3",
                headline_summary="...",
                bogus_field="should fail",  # extra=forbid
            )

    def test_phase_enum_constraint(self):
        from services.extraction.trial_readout import TrialReadoutExtraction
        with pytest.raises(Exception):
            TrialReadoutExtraction(
                trial_identifier="NCT01234567",
                drug_name="X",
                primary_endpoint_met=True,
                readout_date=date(2026, 1, 1),
                phase="Phase 99",  # not in enum
                headline_summary="...",
            )


class TestSchemaEfficacyOutcomes:

    def test_efficacy_outcome_validates(self):
        from services.extraction.trial_readout import (
            TrialReadoutExtraction, EfficacyOutcome,
        )
        out = EfficacyOutcome(
            endpoint_name="progression-free survival",
            endpoint_type="primary",
            hazard_ratio=0.45,
            p_value=0.001,
            ci_low=0.32,
            ci_high=0.62,
            sample_size=480,
            met=True,
        )
        assert out.hazard_ratio == 0.45

    def test_p_value_must_be_in_zero_to_one(self):
        from services.extraction.trial_readout import EfficacyOutcome
        with pytest.raises(Exception):
            EfficacyOutcome(
                endpoint_name="OS",
                endpoint_type="primary",
                p_value=1.5,
                met=True,
            )

    def test_endpoint_type_enum(self):
        from services.extraction.trial_readout import EfficacyOutcome
        with pytest.raises(Exception):
            EfficacyOutcome(
                endpoint_name="OS",
                endpoint_type="bogus",
                met=True,
            )


# ────────────────────────────────────────────────────────────────────
# Cat 2 — LLM extractor factory
# ────────────────────────────────────────────────────────────────────


class TestExtractorFactory:

    def test_factory_returns_callable_extractor(self):
        from services.extraction_llm import make_trial_readout_extractor

        def stub_call(system, user, schema):
            return {"extractions": []}

        extractor = make_trial_readout_extractor(structured_call=stub_call)
        assert hasattr(extractor, "extract")

    def test_extractor_returns_empty_list_when_llm_returns_none(self):
        from services.extraction_llm import make_trial_readout_extractor

        def stub_call(system, user, schema):
            return None

        extractor = make_trial_readout_extractor(structured_call=stub_call)
        result = extractor.extract("Some press release text...")
        assert result == []

    def test_extractor_parses_valid_extraction(self):
        from services.extraction_llm import make_trial_readout_extractor
        from services.extraction.trial_readout import TrialReadoutExtraction

        def stub_call(system, user, schema):
            return {
                "extractions": [
                    {
                        "trial_identifier": "NCT09999999",
                        "drug_name": "DrugX",
                        "indication": "NSCLC",
                        "primary_endpoint_met": True,
                        "readout_date": "2026-04-15",
                        "phase": "Phase 3",
                        "headline_summary": "Met primary endpoint",
                        "efficacy_outcomes": [],
                    }
                ]
            }

        extractor = make_trial_readout_extractor(structured_call=stub_call)
        result = extractor.extract("...")
        assert len(result) == 1
        assert isinstance(result[0], TrialReadoutExtraction)
        assert result[0].trial_identifier == "NCT09999999"

    def test_extractor_drops_invalid_items_keeps_valid(self):
        """Defence-in-depth: one bad item shouldn't sink the whole batch."""
        from services.extraction_llm import make_trial_readout_extractor

        def stub_call(system, user, schema):
            return {
                "extractions": [
                    {  # bad — phase is invalid
                        "trial_identifier": "NCT001",
                        "drug_name": "BadDrug",
                        "primary_endpoint_met": True,
                        "readout_date": "2026-04-15",
                        "phase": "Phase 99",  # bad
                        "headline_summary": "...",
                        "efficacy_outcomes": [],
                    },
                    {  # good
                        "trial_identifier": "NCT002",
                        "drug_name": "GoodDrug",
                        "primary_endpoint_met": True,
                        "readout_date": "2026-04-15",
                        "phase": "Phase 3",
                        "headline_summary": "Met primary",
                        "efficacy_outcomes": [],
                    },
                ]
            }

        extractor = make_trial_readout_extractor(structured_call=stub_call)
        result = extractor.extract("...")
        assert len(result) == 1
        assert result[0].drug_name == "GoodDrug"


# ────────────────────────────────────────────────────────────────────
# Cat 3 — Event emitter
# ────────────────────────────────────────────────────────────────────


def _sample_extraction():
    from services.extraction.trial_readout import (
        TrialReadoutExtraction, EfficacyOutcome,
    )
    return TrialReadoutExtraction(
        trial_identifier="NCT01234567",
        drug_name="Trastuzumab-deruxtecan",
        sponsor_name="Daiichi Sankyo",
        indication="HER2-positive breast cancer",
        primary_endpoint_met=True,
        readout_date=date(2026, 4, 15),
        phase="Phase 3",
        sample_size=480,
        headline_summary="DESTINY-Breast04 met its primary endpoint with "
                         "statistically significant PFS improvement.",
        efficacy_outcomes=[
            EfficacyOutcome(
                endpoint_name="progression-free survival",
                endpoint_type="primary",
                hazard_ratio=0.50,
                p_value=0.0001,
                met=True,
            ),
        ],
    )


class TestEventEmitter:

    def test_module_imports(self):
        from services.event_emitters.trial_readout import build_event_row  # noqa: F401

    def test_event_row_has_required_fields(self):
        from services.event_emitters.trial_readout import build_event_row
        row = build_event_row(
            extraction=_sample_extraction(),
            company_id="11111111-1111-1111-1111-111111111111",
            company_name="Daiichi Sankyo",
            trial_id="22222222-2222-2222-2222-222222222222",
            source_document_id="33333333-3333-3333-3333-333333333333",
            disclosed_date=date(2026, 4, 15),
        )
        assert row["event_type"] == "trial_readout"
        assert row["primary_entity_type"] == "trial"
        assert row["primary_entity_id"] == "22222222-2222-2222-2222-222222222222"
        assert row["event_date"] == date(2026, 4, 15)
        assert row["disclosed_date"] == date(2026, 4, 15)
        assert "event_hash" in row
        assert len(row["event_hash"]) == 64  # SHA-256 hex
        assert row["source_feed"] == "press_release_readout"
        assert row["source_tier"] == "tier_2"  # company-self-reported = tier 2

    def test_event_payload_includes_efficacy_data(self):
        from services.event_emitters.trial_readout import build_event_row
        row = build_event_row(
            extraction=_sample_extraction(),
            company_id="11111111-1111-1111-1111-111111111111",
            company_name="Daiichi Sankyo",
            trial_id="22222222-2222-2222-2222-222222222222",
            source_document_id="33333333-3333-3333-3333-333333333333",
            disclosed_date=date(2026, 4, 15),
        )
        payload = row["payload"]
        assert payload["primary_endpoint_met"] is True
        assert payload["drug_name"] == "Trastuzumab-deruxtecan"
        assert payload["phase"] == "Phase 3"
        assert payload["sample_size"] == 480
        assert "efficacy_outcomes" in payload
        assert payload["efficacy_outcomes"][0]["hazard_ratio"] == 0.50
        assert payload["efficacy_outcomes"][0]["met"] is True

    def test_event_hash_deterministic(self):
        """Same extraction + ids = same hash. Drives idempotency."""
        from services.event_emitters.trial_readout import build_event_row
        ex = _sample_extraction()
        row1 = build_event_row(
            extraction=ex,
            company_id="cid",
            company_name="Sponsor",
            trial_id="tid",
            source_document_id="sdid",
            disclosed_date=date(2026, 4, 15),
        )
        row2 = build_event_row(
            extraction=ex,
            company_id="cid",
            company_name="Sponsor",
            trial_id="tid",
            source_document_id="sdid",
            disclosed_date=date(2026, 4, 15),
        )
        assert row1["event_hash"] == row2["event_hash"]

    def test_missed_endpoint_flagged_high_impact(self):
        """Negative readouts always high impact — they move stocks more."""
        from services.event_emitters.trial_readout import build_event_row
        from services.extraction.trial_readout import TrialReadoutExtraction
        ex = TrialReadoutExtraction(
            trial_identifier="NCT001",
            drug_name="DrugX",
            primary_endpoint_met=False,
            readout_date=date(2026, 1, 1),
            phase="Phase 3",
            headline_summary="Did not meet primary endpoint.",
            efficacy_outcomes=[],
        )
        row = build_event_row(
            extraction=ex,
            company_id="cid",
            company_name="Sponsor",
            trial_id="tid",
            source_document_id="sdid",
            disclosed_date=date(2026, 1, 1),
        )
        assert row["impact_hint"] == "high"

    def test_phase_3_higher_impact_than_phase_1(self):
        from services.event_emitters.trial_readout import build_event_row
        from services.extraction.trial_readout import TrialReadoutExtraction
        ex_phase1 = TrialReadoutExtraction(
            trial_identifier="NCT001",
            drug_name="DrugX",
            primary_endpoint_met=True,
            readout_date=date(2026, 1, 1),
            phase="Phase 1",
            headline_summary="...",
            efficacy_outcomes=[],
        )
        ex_phase3 = TrialReadoutExtraction(
            trial_identifier="NCT002",
            drug_name="DrugY",
            primary_endpoint_met=True,
            readout_date=date(2026, 1, 1),
            phase="Phase 3",
            headline_summary="...",
            efficacy_outcomes=[],
        )
        kwargs = dict(
            company_id="c", company_name="S", trial_id="t",
            source_document_id="d", disclosed_date=date(2026, 1, 1),
        )
        r1 = build_event_row(extraction=ex_phase1, **kwargs)
        r3 = build_event_row(extraction=ex_phase3, **kwargs)
        impact_rank = {"low": 1, "medium": 2, "high": 3}
        assert impact_rank[r3["impact_hint"]] > impact_rank[r1["impact_hint"]]


# ────────────────────────────────────────────────────────────────────
# Cat 4 — Trust score
# ────────────────────────────────────────────────────────────────────


class TestTrustScore:

    def test_press_release_lower_than_8k(self):
        """Per ADR-002 / SPEC-016: company press release = tier_2 ≈ 0.7-0.8.
        SEC 8-K = tier_1 ≈ 0.95. The trust score reflects the source."""
        from services.event_emitters.trial_readout import build_event_row
        row = build_event_row(
            extraction=_sample_extraction(),
            company_id="cid",
            company_name="S",
            trial_id="tid",
            source_document_id="sdid",
            disclosed_date=date(2026, 4, 15),
        )
        assert row["trust_score"] < 0.95  # below 8-K
        assert row["trust_score"] >= 0.5  # above pure rumour
