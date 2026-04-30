"""Cycle 9 — FDA Drug Discontinuation connector (A4.4).

Source: OpenFDA drugsfda.json `products[].marketing_status` field.
Products in 'Discontinued' or 'Withdrawn for Sale' status feed
drug_discontinuation events. The Drugs@FDA system is the canonical
US source for marketing-status changes.

Cycle delivers:
  - Pydantic schema (services/extraction/drug_discontinuation.DrugDiscontinuation)
  - Connector + parser (connectors/fda_discontinuations.py)
  - Event emitter (services/event_emitters/drug_discontinuation.build_event_row)
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest


_FIXTURE_OPENFDA_RESPONSE = {
    "results": [
        {
            "application_number": "NDA019875",
            "sponsor_name": "Sanofi-Aventis",
            "openfda": {
                "generic_name": ["irbesartan"],
                "brand_name": ["Avapro"],
            },
            "products": [
                {
                    "product_number": "001",
                    "marketing_status": "Discontinued",
                    "active_ingredients": [
                        {"name": "irbesartan", "strength": "75mg"},
                    ],
                    "dosage_form": "TABLET",
                    "route": "ORAL",
                },
                {
                    "product_number": "002",
                    "marketing_status": "Prescription",
                    "active_ingredients": [
                        {"name": "irbesartan", "strength": "150mg"},
                    ],
                    "dosage_form": "TABLET",
                    "route": "ORAL",
                },
            ],
        },
        {
            "application_number": "NDA021077",
            "sponsor_name": "Merck",
            "openfda": {
                "generic_name": ["aprepitant"],
                "brand_name": ["Emend"],
            },
            "products": [
                {
                    "product_number": "001",
                    "marketing_status": "Withdrawn for Sale",
                    "active_ingredients": [
                        {"name": "aprepitant", "strength": "80mg"},
                    ],
                    "dosage_form": "CAPSULE",
                    "route": "ORAL",
                },
            ],
        },
    ],
    "meta": {"results": {"total": 2}},
}


# ────────────────────────────────────────────────────────────────────
# Cat 1 — Schema
# ────────────────────────────────────────────────────────────────────


class TestSchema:

    def test_schema_imports(self):
        from services.extraction.drug_discontinuation import DrugDiscontinuation  # noqa: F401

    def test_minimum_validates(self):
        from services.extraction.drug_discontinuation import DrugDiscontinuation
        d = DrugDiscontinuation(
            drug_name="irbesartan",
            sponsor_name="Sanofi-Aventis",
            application_number="NDA019875",
            product_number="001",
            marketing_status="discontinued",
            observed_date=date(2026, 4, 30),
            dosage_form="TABLET",
            strength="75mg",
        )
        assert d.marketing_status == "discontinued"

    def test_status_enum(self):
        from services.extraction.drug_discontinuation import DrugDiscontinuation
        with pytest.raises(Exception):
            DrugDiscontinuation(
                drug_name="x", sponsor_name="y",
                application_number="z", product_number="1",
                marketing_status="bogus",
                observed_date=date(2026, 1, 1),
            )

    def test_extra_fields_forbidden(self):
        from services.extraction.drug_discontinuation import DrugDiscontinuation
        with pytest.raises(Exception):
            DrugDiscontinuation(
                drug_name="x", sponsor_name="y",
                application_number="z", product_number="1",
                marketing_status="discontinued",
                observed_date=date(2026, 1, 1),
                bogus="boom",
            )


# ────────────────────────────────────────────────────────────────────
# Cat 2 — Parser
# ────────────────────────────────────────────────────────────────────


class TestParser:

    def test_parser_imports(self):
        from connectors.fda_discontinuations import parse_openfda_results  # noqa: F401

    def test_extracts_only_discontinued_or_withdrawn(self):
        from connectors.fda_discontinuations import parse_openfda_results
        records = parse_openfda_results(
            _FIXTURE_OPENFDA_RESPONSE,
            observed_date=date(2026, 4, 30),
        )
        # One discontinued + one withdrawn = 2 records
        assert len(records) == 2

    def test_active_products_skipped(self):
        from connectors.fda_discontinuations import parse_openfda_results
        records = parse_openfda_results(
            _FIXTURE_OPENFDA_RESPONSE,
            observed_date=date(2026, 4, 30),
        )
        names = [r.drug_name for r in records]
        # The 150mg irbesartan is Prescription (active) — must NOT appear
        assert names.count("irbesartan") == 1   # only the discontinued one

    def test_status_normalised(self):
        from connectors.fda_discontinuations import parse_openfda_results
        records = parse_openfda_results(
            _FIXTURE_OPENFDA_RESPONSE,
            observed_date=date(2026, 4, 30),
        )
        statuses = {r.marketing_status for r in records}
        assert statuses == {"discontinued", "withdrawn"}

    def test_application_number_carried(self):
        from connectors.fda_discontinuations import parse_openfda_results
        records = parse_openfda_results(
            _FIXTURE_OPENFDA_RESPONSE,
            observed_date=date(2026, 4, 30),
        )
        app_numbers = {r.application_number for r in records}
        assert app_numbers == {"NDA019875", "NDA021077"}

    def test_strength_extracted(self):
        from connectors.fda_discontinuations import parse_openfda_results
        records = parse_openfda_results(
            _FIXTURE_OPENFDA_RESPONSE,
            observed_date=date(2026, 4, 30),
        )
        by_drug = {r.drug_name: r for r in records}
        assert by_drug["irbesartan"].strength == "75mg"

    def test_empty_payload_returns_empty(self):
        from connectors.fda_discontinuations import parse_openfda_results
        assert parse_openfda_results({}, observed_date=date(2026, 4, 30)) == []
        assert parse_openfda_results(
            {"results": [], "meta": {}},
            observed_date=date(2026, 4, 30),
        ) == []


# ────────────────────────────────────────────────────────────────────
# Cat 3 — Connector
# ────────────────────────────────────────────────────────────────────


class TestConnector:

    def test_connector_imports(self):
        from connectors.fda_discontinuations import FdaDiscontinuationsConnector  # noqa: F401

    def test_constructor_no_network(self):
        from connectors.fda_discontinuations import FdaDiscontinuationsConnector
        c = FdaDiscontinuationsConnector()
        assert c is not None

    def test_fetch_recent_uses_openfda(self):
        from connectors.fda_discontinuations import FdaDiscontinuationsConnector
        c = FdaDiscontinuationsConnector()
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: _FIXTURE_OPENFDA_RESPONSE,
            )
            records = c.fetch_recent(observed_date=date(2026, 4, 30))
            assert len(records) == 2
            args, kwargs = mock_get.call_args
            url = args[0] if args else kwargs.get("url")
            assert "api.fda.gov" in url

    def test_fetch_for_drug_filters_by_name(self):
        from connectors.fda_discontinuations import FdaDiscontinuationsConnector
        c = FdaDiscontinuationsConnector()
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: _FIXTURE_OPENFDA_RESPONSE,
            )
            records = c.fetch_for_drug_name(
                drug_name="irbesartan",
                observed_date=date(2026, 4, 30),
            )
            assert len(records) >= 1

    def test_fetch_returns_empty_on_404(self):
        from connectors.fda_discontinuations import FdaDiscontinuationsConnector
        c = FdaDiscontinuationsConnector()
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=404, json=lambda: {})
            assert c.fetch_recent(observed_date=date(2026, 4, 30)) == []


# ────────────────────────────────────────────────────────────────────
# Cat 4 — Event emitter
# ────────────────────────────────────────────────────────────────────


def _sample_record(status: str = "discontinued"):
    from services.extraction.drug_discontinuation import DrugDiscontinuation
    return DrugDiscontinuation(
        drug_name="irbesartan",
        sponsor_name="Sanofi-Aventis",
        application_number="NDA019875",
        product_number="001",
        marketing_status=status,
        observed_date=date(2026, 4, 30),
        dosage_form="TABLET",
        strength="75mg",
    )


class TestEventEmitter:

    def test_emitter_imports(self):
        from services.event_emitters.drug_discontinuation import build_event_row  # noqa: F401

    def test_event_row_has_required_fields(self):
        from services.event_emitters.drug_discontinuation import build_event_row
        row = build_event_row(
            record=_sample_record(),
            drug_id="11111111-1111-1111-1111-111111111111",
            company_id="22222222-2222-2222-2222-222222222222",
            company_name="Sanofi",
            source_document_id="33333333-3333-3333-3333-333333333333",
            disclosed_date=date(2026, 4, 30),
        )
        assert row["event_type"] == "drug_discontinuation"
        assert row["primary_entity_type"] == "drug"
        assert row["source_tier"] == "tier_1"
        assert row["trust_score"] >= 0.9
        assert "event_hash" in row
        assert len(row["event_hash"]) == 64

    def test_withdrawn_high_impact(self):
        from services.event_emitters.drug_discontinuation import build_event_row
        row = build_event_row(
            record=_sample_record("withdrawn"),
            drug_id="d", company_id="c", company_name="C",
            source_document_id="s", disclosed_date=date(2026, 4, 30),
        )
        assert row["impact_hint"] == "high"

    def test_discontinued_medium_impact(self):
        from services.event_emitters.drug_discontinuation import build_event_row
        row = build_event_row(
            record=_sample_record("discontinued"),
            drug_id="d", company_id="c", company_name="C",
            source_document_id="s", disclosed_date=date(2026, 4, 30),
        )
        assert row["impact_hint"] == "medium"

    def test_event_hash_deterministic(self):
        from services.event_emitters.drug_discontinuation import build_event_row
        kwargs = dict(
            record=_sample_record(),
            drug_id="d", company_id="c", company_name="C",
            source_document_id="s", disclosed_date=date(2026, 4, 30),
        )
        r1 = build_event_row(**kwargs)
        r2 = build_event_row(**kwargs)
        assert r1["event_hash"] == r2["event_hash"]

    def test_payload_carries_metadata(self):
        from services.event_emitters.drug_discontinuation import build_event_row
        row = build_event_row(
            record=_sample_record(),
            drug_id="d", company_id="c", company_name="C",
            source_document_id="s", disclosed_date=date(2026, 4, 30),
        )
        payload = row["payload"]
        assert payload["application_number"] == "NDA019875"
        assert payload["product_number"] == "001"
        assert payload["marketing_status"] == "discontinued"
        assert payload["strength"] == "75mg"
