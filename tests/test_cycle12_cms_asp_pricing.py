"""Cycle 12 — CMS ASP pricing connector.

CMS ASP = Average Sales Price. Quarterly file at:
  https://www.cms.gov/medicare/medicare-part-b-drug-average-sales-price/asp-pricing-files

Each row is one HCPCS code with its quarterly Part B payment limit
(ASP + small markup historically; IRA-negotiated drugs follow a
different rule but appear in the same file).

Public source. Closes the public side of KBQ 7 (Pricing). Pairs
later with NADAC (Part D acquisition cost) for the full picture.

Cycle delivers:
  - Pydantic schema (services/extraction/pricing_observation.py)
  - Connector + CSV parser (connectors/cms_asp.py)
  - Event emitter (services/event_emitters/pricing_observation.py)
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest


_FIXTURE_ASP_CSV = """\
HCPCS Code,Short Description,HCPCS Code Dosage,Payment Limit,Notes
J3262,Tocilizumab injection,1 mg,3.7501,
J9035,Bevacizumab injection,10 mg,79.832,
J9304,Pemetrexed injection,10 mg,15.6781,
J0490,Belimumab injection,10 mg,12.0152,
"""


# ────────────────────────────────────────────────────────────────────
# Cat 1 — Schema
# ────────────────────────────────────────────────────────────────────


class TestSchema:

    def test_schema_imports(self):
        from services.extraction.pricing_observation import PricingObservation  # noqa: F401

    def test_minimum_validates(self):
        from services.extraction.pricing_observation import PricingObservation
        p = PricingObservation(
            hcpcs_code="J3262",
            short_description="Tocilizumab injection",
            dosage_unit="1 mg",
            payment_limit_usd=3.7501,
            payment_basis="asp",
            period_start=date(2026, 4, 1),
            period_end=date(2026, 6, 30),
            source_program="medicare_part_b",
        )
        assert p.payment_limit_usd == 3.7501

    def test_payment_basis_enum(self):
        from services.extraction.pricing_observation import PricingObservation
        with pytest.raises(Exception):
            PricingObservation(
                hcpcs_code="X", short_description="d",
                dosage_unit="1mg", payment_limit_usd=1.0,
                payment_basis="bogus",
                period_start=date(2026, 1, 1),
                period_end=date(2026, 3, 31),
                source_program="medicare_part_b",
            )

    def test_payment_limit_positive(self):
        from services.extraction.pricing_observation import PricingObservation
        with pytest.raises(Exception):
            PricingObservation(
                hcpcs_code="X", short_description="d",
                dosage_unit="1mg", payment_limit_usd=-1.0,
                payment_basis="asp",
                period_start=date(2026, 1, 1),
                period_end=date(2026, 3, 31),
                source_program="medicare_part_b",
            )

    def test_extra_fields_forbidden(self):
        from services.extraction.pricing_observation import PricingObservation
        with pytest.raises(Exception):
            PricingObservation(
                hcpcs_code="X", short_description="d",
                dosage_unit="1mg", payment_limit_usd=1.0,
                payment_basis="asp",
                period_start=date(2026, 1, 1),
                period_end=date(2026, 3, 31),
                source_program="medicare_part_b",
                bogus="boom",
            )


# ────────────────────────────────────────────────────────────────────
# Cat 2 — Parser
# ────────────────────────────────────────────────────────────────────


class TestParser:

    def test_parser_imports(self):
        from connectors.cms_asp import parse_asp_csv  # noqa: F401

    def test_parses_four_rows(self):
        from connectors.cms_asp import parse_asp_csv
        records = parse_asp_csv(
            _FIXTURE_ASP_CSV,
            period_start=date(2026, 4, 1),
            period_end=date(2026, 6, 30),
        )
        assert len(records) == 4

    def test_hcpcs_codes_extracted(self):
        from connectors.cms_asp import parse_asp_csv
        records = parse_asp_csv(
            _FIXTURE_ASP_CSV,
            period_start=date(2026, 4, 1),
            period_end=date(2026, 6, 30),
        )
        codes = {r.hcpcs_code for r in records}
        assert codes == {"J3262", "J9035", "J9304", "J0490"}

    def test_payment_limit_parsed_as_float(self):
        from connectors.cms_asp import parse_asp_csv
        records = parse_asp_csv(
            _FIXTURE_ASP_CSV,
            period_start=date(2026, 4, 1),
            period_end=date(2026, 6, 30),
        )
        by_code = {r.hcpcs_code: r for r in records}
        assert abs(by_code["J3262"].payment_limit_usd - 3.7501) < 1e-9
        assert abs(by_code["J9035"].payment_limit_usd - 79.832) < 1e-9

    def test_period_carried_through(self):
        from connectors.cms_asp import parse_asp_csv
        records = parse_asp_csv(
            _FIXTURE_ASP_CSV,
            period_start=date(2026, 4, 1),
            period_end=date(2026, 6, 30),
        )
        for r in records:
            assert r.period_start == date(2026, 4, 1)
            assert r.period_end == date(2026, 6, 30)

    def test_empty_csv_returns_empty(self):
        from connectors.cms_asp import parse_asp_csv
        assert parse_asp_csv(
            "",
            period_start=date(2026, 1, 1),
            period_end=date(2026, 3, 31),
        ) == []
        assert parse_asp_csv(
            "HCPCS Code,Short Description\n",
            period_start=date(2026, 1, 1),
            period_end=date(2026, 3, 31),
        ) == []

    def test_malformed_payment_limit_skipped(self):
        from connectors.cms_asp import parse_asp_csv
        bad_csv = (
            "HCPCS Code,Short Description,HCPCS Code Dosage,"
            "Payment Limit,Notes\n"
            "J0001,Bad row,1 mg,not-a-number,\n"
            "J3262,Good row,1 mg,3.7501,\n"
        )
        records = parse_asp_csv(
            bad_csv,
            period_start=date(2026, 4, 1),
            period_end=date(2026, 6, 30),
        )
        assert len(records) == 1
        assert records[0].hcpcs_code == "J3262"


# ────────────────────────────────────────────────────────────────────
# Cat 3 — Connector
# ────────────────────────────────────────────────────────────────────


class TestConnector:

    def test_connector_imports(self):
        from connectors.cms_asp import CmsAspConnector  # noqa: F401

    def test_constructor_no_network(self):
        from connectors.cms_asp import CmsAspConnector
        c = CmsAspConnector()
        assert c is not None

    def test_fetch_quarter_uses_csv_endpoint(self):
        from connectors.cms_asp import CmsAspConnector
        c = CmsAspConnector()
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, text=_FIXTURE_ASP_CSV,
            )
            records = c.fetch_quarter(
                quarter_url="https://www.cms.gov/files/asp_2026_q2.csv",
                period_start=date(2026, 4, 1),
                period_end=date(2026, 6, 30),
            )
            assert len(records) == 4

    def test_fetch_returns_empty_on_404(self):
        from connectors.cms_asp import CmsAspConnector
        c = CmsAspConnector()
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=404, text="")
            records = c.fetch_quarter(
                quarter_url="https://www.cms.gov/missing.csv",
                period_start=date(2026, 4, 1),
                period_end=date(2026, 6, 30),
            )
            assert records == []


# ────────────────────────────────────────────────────────────────────
# Cat 4 — Event emitter
# ────────────────────────────────────────────────────────────────────


def _sample_obs(amount: float = 3.7501):
    from services.extraction.pricing_observation import PricingObservation
    return PricingObservation(
        hcpcs_code="J3262",
        short_description="Tocilizumab injection",
        dosage_unit="1 mg",
        payment_limit_usd=amount,
        payment_basis="asp",
        period_start=date(2026, 4, 1),
        period_end=date(2026, 6, 30),
        source_program="medicare_part_b",
    )


class TestEventEmitter:

    def test_emitter_imports(self):
        from services.event_emitters.pricing_observation import build_event_row  # noqa: F401

    def test_event_row_has_required_fields(self):
        from services.event_emitters.pricing_observation import build_event_row
        row = build_event_row(
            observation=_sample_obs(),
            drug_id="11111111-1111-1111-1111-111111111111",
            source_document_id="22222222-2222-2222-2222-222222222222",
            disclosed_date=date(2026, 4, 1),
        )
        assert row["event_type"] == "pricing_observation"
        assert row["primary_entity_type"] == "drug"
        assert row["source_tier"] == "tier_1"
        assert row["trust_score"] >= 0.9

    def test_low_impact_default(self):
        """Pricing observations are low-impact by default. The
        delta-detector (Cycle N+) emits high-impact events when ASP
        moves more than X% QoQ."""
        from services.event_emitters.pricing_observation import build_event_row
        row = build_event_row(
            observation=_sample_obs(),
            drug_id="d", source_document_id="s",
            disclosed_date=date(2026, 4, 1),
        )
        assert row["impact_hint"] == "low"

    def test_event_hash_deterministic(self):
        from services.event_emitters.pricing_observation import build_event_row
        kwargs = dict(
            observation=_sample_obs(),
            drug_id="d", source_document_id="s",
            disclosed_date=date(2026, 4, 1),
        )
        r1 = build_event_row(**kwargs)
        r2 = build_event_row(**kwargs)
        assert r1["event_hash"] == r2["event_hash"]
        assert len(r1["event_hash"]) == 64

    def test_event_hash_changes_with_period(self):
        """Different quarters produce different hashes."""
        from services.event_emitters.pricing_observation import build_event_row
        from services.extraction.pricing_observation import PricingObservation

        a = _sample_obs()
        b = PricingObservation(
            hcpcs_code="J3262",
            short_description="Tocilizumab injection",
            dosage_unit="1 mg",
            payment_limit_usd=3.7501,
            payment_basis="asp",
            period_start=date(2026, 7, 1),
            period_end=date(2026, 9, 30),
            source_program="medicare_part_b",
        )
        ra = build_event_row(
            observation=a, drug_id="d",
            source_document_id="s", disclosed_date=date(2026, 4, 1),
        )
        rb = build_event_row(
            observation=b, drug_id="d",
            source_document_id="s", disclosed_date=date(2026, 7, 1),
        )
        assert ra["event_hash"] != rb["event_hash"]

    def test_payload_carries_metadata(self):
        from services.event_emitters.pricing_observation import build_event_row
        row = build_event_row(
            observation=_sample_obs(),
            drug_id="d", source_document_id="s",
            disclosed_date=date(2026, 4, 1),
        )
        payload = row["payload"]
        assert payload["hcpcs_code"] == "J3262"
        assert payload["payment_limit_usd"] == 3.7501
        assert payload["dosage_unit"] == "1 mg"
        assert payload["payment_basis"] == "asp"
        assert payload["source_program"] == "medicare_part_b"
