"""Cycle 8 — FDA designations connector (A4.3).

FDA expedited-program designations are public, structured (JSON via
OpenFDA), and high-value for KBQ 1 (Indications) and KBQ 6 (SWOT —
designations are a leading indicator of future approval).

Designation types covered:
  - Orphan Drug Designation
  - Breakthrough Therapy Designation (BTD)
  - Fast Track Designation
  - Accelerated Approval
  - Priority Review
  - RMAT (Regenerative Medicine Advanced Therapy)
  - QIDP (Qualified Infectious Disease Product)

This cycle delivers:
  - Pydantic schema (services/extraction/fda_designation.FdaDesignation)
  - Connector (connectors/fda_designations.FdaDesignationsConnector)
  - Event emitter (services/event_emitters/fda_designation.build_event_row)
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest


_FIXTURE_OPENFDA_RESPONSE = {
    "results": [
        {
            "application_number": "NDA218237",
            "sponsor_name": "Eli Lilly",
            "openfda": {
                "generic_name": ["tirzepatide"],
                "brand_name": ["Zepbound"],
            },
            "products": [
                {
                    "marketing_status": "Prescription",
                    "active_ingredients": [
                        {"name": "tirzepatide", "strength": "10mg"},
                    ],
                },
            ],
            "submissions": [
                {
                    "submission_type": "ORIG",
                    "submission_number": "1",
                    "submission_status": "AP",
                    "submission_status_date": "20231108",
                    "review_priority": "PRIORITY",
                    "submission_class_code": "BREAKTHROUGH",
                    "submission_class_code_description":
                        "Breakthrough Therapy Designation granted",
                },
            ],
        },
    ],
    "meta": {"results": {"total": 1}},
}


# ────────────────────────────────────────────────────────────────────
# Cat 1 — Schema
# ────────────────────────────────────────────────────────────────────


class TestSchema:

    def test_schema_imports(self):
        from services.extraction.fda_designation import FdaDesignation  # noqa: F401

    def test_minimum_fields_validate(self):
        from services.extraction.fda_designation import FdaDesignation
        d = FdaDesignation(
            drug_name="tirzepatide",
            sponsor_name="Eli Lilly",
            designation_type="breakthrough",
            granted_date=date(2023, 11, 8),
            indication="Type 2 diabetes mellitus",
        )
        assert d.designation_type == "breakthrough"

    def test_designation_type_enum(self):
        from services.extraction.fda_designation import FdaDesignation
        with pytest.raises(Exception):
            FdaDesignation(
                drug_name="x", sponsor_name="y",
                designation_type="bogus",
                granted_date=date(2023, 1, 1),
                indication="...",
            )

    def test_extra_fields_forbidden(self):
        from services.extraction.fda_designation import FdaDesignation
        with pytest.raises(Exception):
            FdaDesignation(
                drug_name="x", sponsor_name="y",
                designation_type="orphan",
                granted_date=date(2023, 1, 1),
                indication="...",
                bogus="boom",
            )

    def test_optional_fields(self):
        from services.extraction.fda_designation import FdaDesignation
        d = FdaDesignation(
            drug_name="x", sponsor_name="y",
            designation_type="orphan",
            granted_date=date(2023, 1, 1),
            indication="rare disease",
            application_number="NDA218237",
            notes="Transferred from prior sponsor",
        )
        assert d.application_number == "NDA218237"


# ────────────────────────────────────────────────────────────────────
# Cat 2 — OpenFDA submission parser (extracts designations)
# ────────────────────────────────────────────────────────────────────


class TestOpenFDAParser:

    def test_parser_imports(self):
        from connectors.fda_designations import parse_openfda_results  # noqa: F401

    def test_extracts_breakthrough_designation(self):
        from connectors.fda_designations import parse_openfda_results
        designations = parse_openfda_results(_FIXTURE_OPENFDA_RESPONSE)
        assert len(designations) >= 1
        types = {d.designation_type for d in designations}
        assert "breakthrough" in types

    def test_extracts_priority_review(self):
        from connectors.fda_designations import parse_openfda_results
        designations = parse_openfda_results(_FIXTURE_OPENFDA_RESPONSE)
        types = {d.designation_type for d in designations}
        assert "priority_review" in types

    def test_drug_name_resolved(self):
        from connectors.fda_designations import parse_openfda_results
        designations = parse_openfda_results(_FIXTURE_OPENFDA_RESPONSE)
        assert any(d.drug_name.lower() == "tirzepatide" for d in designations)

    def test_sponsor_extracted(self):
        from connectors.fda_designations import parse_openfda_results
        designations = parse_openfda_results(_FIXTURE_OPENFDA_RESPONSE)
        assert any(d.sponsor_name == "Eli Lilly" for d in designations)

    def test_granted_date_parsed_yyyymmdd(self):
        from connectors.fda_designations import parse_openfda_results
        designations = parse_openfda_results(_FIXTURE_OPENFDA_RESPONSE)
        for d in designations:
            assert d.granted_date == date(2023, 11, 8)

    def test_application_number_carried(self):
        from connectors.fda_designations import parse_openfda_results
        designations = parse_openfda_results(_FIXTURE_OPENFDA_RESPONSE)
        for d in designations:
            assert d.application_number == "NDA218237"

    def test_empty_results_returns_empty(self):
        from connectors.fda_designations import parse_openfda_results
        assert parse_openfda_results({"results": [], "meta": {}}) == []
        assert parse_openfda_results({}) == []


# ────────────────────────────────────────────────────────────────────
# Cat 3 — Connector
# ────────────────────────────────────────────────────────────────────


class TestConnector:

    def test_connector_imports(self):
        from connectors.fda_designations import FdaDesignationsConnector  # noqa: F401

    def test_constructor_no_network(self):
        from connectors.fda_designations import FdaDesignationsConnector
        c = FdaDesignationsConnector()
        assert c is not None

    def test_fetch_for_drug_name_uses_openfda(self):
        from connectors.fda_designations import FdaDesignationsConnector
        c = FdaDesignationsConnector()
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: _FIXTURE_OPENFDA_RESPONSE,
            )
            designations = c.fetch_for_drug_name(drug_name="tirzepatide")
            assert len(designations) >= 1
            args, kwargs = mock_get.call_args
            url = args[0] if args else kwargs.get("url")
            assert "api.fda.gov" in url

    def test_fetch_returns_empty_on_404(self):
        from connectors.fda_designations import FdaDesignationsConnector
        c = FdaDesignationsConnector()
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=404, json=lambda: {})
            assert c.fetch_for_drug_name(drug_name="missing") == []


# ────────────────────────────────────────────────────────────────────
# Cat 4 — Event emitter
# ────────────────────────────────────────────────────────────────────


def _sample_designation(designation_type: str = "breakthrough"):
    from services.extraction.fda_designation import FdaDesignation
    return FdaDesignation(
        drug_name="tirzepatide",
        sponsor_name="Eli Lilly",
        designation_type=designation_type,
        granted_date=date(2023, 11, 8),
        indication="Type 2 diabetes mellitus",
        application_number="NDA218237",
    )


class TestEventEmitter:

    def test_emitter_imports(self):
        from services.event_emitters.fda_designation import build_event_row  # noqa: F401

    def test_event_row_has_required_fields(self):
        from services.event_emitters.fda_designation import build_event_row
        row = build_event_row(
            designation=_sample_designation(),
            drug_id="11111111-1111-1111-1111-111111111111",
            company_id="22222222-2222-2222-2222-222222222222",
            company_name="Eli Lilly",
            source_document_id="33333333-3333-3333-3333-333333333333",
            disclosed_date=date(2023, 11, 8),
        )
        assert row["event_type"] == "fda_designation"
        assert row["primary_entity_type"] == "drug"
        assert row["source_tier"] == "tier_1"
        assert row["trust_score"] >= 0.9
        assert "event_hash" in row
        assert len(row["event_hash"]) == 64

    def test_breakthrough_high_impact(self):
        from services.event_emitters.fda_designation import build_event_row
        row = build_event_row(
            designation=_sample_designation("breakthrough"),
            drug_id="d", company_id="c", company_name="C",
            source_document_id="s", disclosed_date=date(2023, 11, 8),
        )
        assert row["impact_hint"] == "high"

    def test_priority_review_high_impact(self):
        from services.event_emitters.fda_designation import build_event_row
        row = build_event_row(
            designation=_sample_designation("priority_review"),
            drug_id="d", company_id="c", company_name="C",
            source_document_id="s", disclosed_date=date(2023, 11, 8),
        )
        assert row["impact_hint"] == "high"

    def test_orphan_medium_impact(self):
        from services.event_emitters.fda_designation import build_event_row
        row = build_event_row(
            designation=_sample_designation("orphan"),
            drug_id="d", company_id="c", company_name="C",
            source_document_id="s", disclosed_date=date(2023, 11, 8),
        )
        assert row["impact_hint"] == "medium"

    def test_event_hash_deterministic(self):
        from services.event_emitters.fda_designation import build_event_row
        kwargs = dict(
            designation=_sample_designation(),
            drug_id="d", company_id="c", company_name="C",
            source_document_id="s", disclosed_date=date(2023, 11, 8),
        )
        r1 = build_event_row(**kwargs)
        r2 = build_event_row(**kwargs)
        assert r1["event_hash"] == r2["event_hash"]

    def test_payload_carries_designation_metadata(self):
        from services.event_emitters.fda_designation import build_event_row
        row = build_event_row(
            designation=_sample_designation(),
            drug_id="d", company_id="c", company_name="C",
            source_document_id="s", disclosed_date=date(2023, 11, 8),
        )
        payload = row["payload"]
        assert payload["designation_type"] == "breakthrough"
        assert payload["drug_name"] == "tirzepatide"
        assert payload["application_number"] == "NDA218237"
        assert "diabetes" in payload["indication"]
