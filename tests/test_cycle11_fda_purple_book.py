"""Cycle 11 — FDA Purple Book connector (biologics + biosimilars).

The Purple Book is the biologics analog of the Orange Book. Each
row is one BLA-approved biologic product, including:
  - Original biologics (BLA Type: Original)
  - Biosimilars (BLA Type: Biosimilar)
  - Interchangeable biosimilars (BLA Type: Interchangeable)

Public source: https://purplebooksearch.fda.gov/downloads (CSV).

Cycle delivers:
  - Pydantic schema  (services/extraction/biologic_product.py)
  - Connector + CSV parser  (connectors/fda_purple_book.py)
  - Event emitter for biosimilar approvals
    (services/event_emitters/biosimilar_approval.py)
"""

from __future__ import annotations

import io
from datetime import date
from unittest.mock import MagicMock, patch

import pytest


_FIXTURE_PURPLE_BOOK_CSV = """\
Proprietary Name,Proper Name,BLA Number,BLA Type,Strength,Dosage Form,\
Route of Administration,Product Presentation,License Status,\
Approval Date,Ref. Product Proprietary Name,Ref. Product Proper Name,\
Application Holder
Humira,adalimumab,125057,Original,40 mg/0.4 mL,injection,\
subcutaneous,prefilled syringe,Licensed,2002-12-31,,,AbbVie Inc.
Amjevita,adalimumab-atto,761024,Biosimilar,40 mg/0.8 mL,injection,\
subcutaneous,prefilled syringe,Licensed,2016-09-23,Humira,adalimumab,\
Amgen Inc.
Cyltezo,adalimumab-adbm,761058,Interchangeable,40 mg/0.8 mL,injection,\
subcutaneous,prefilled syringe,Licensed,2017-08-25,Humira,adalimumab,\
Boehringer Ingelheim Pharmaceuticals Inc.
Avastin,bevacizumab,125085,Original,400 mg/16 mL,injection,\
intravenous,vial,Licensed,2004-02-26,,,Genentech Inc.
"""


# ────────────────────────────────────────────────────────────────────
# Cat 1 — Schema
# ────────────────────────────────────────────────────────────────────


class TestSchema:

    def test_schema_imports(self):
        from services.extraction.biologic_product import BiologicProduct  # noqa: F401

    def test_minimum_validates(self):
        from services.extraction.biologic_product import BiologicProduct
        p = BiologicProduct(
            proprietary_name="Humira",
            proper_name="adalimumab",
            bla_number="125057",
            bla_type="original",
            license_status="licensed",
            approval_date=date(2002, 12, 31),
            applicant="AbbVie Inc.",
        )
        assert p.bla_type == "original"

    def test_biosimilar_requires_ref_product(self):
        """Reference product fields are optional but biosimilars
        usually have them populated."""
        from services.extraction.biologic_product import BiologicProduct
        p = BiologicProduct(
            proprietary_name="Amjevita",
            proper_name="adalimumab-atto",
            bla_number="761024",
            bla_type="biosimilar",
            license_status="licensed",
            approval_date=date(2016, 9, 23),
            applicant="Amgen Inc.",
            ref_product_proprietary_name="Humira",
            ref_product_proper_name="adalimumab",
        )
        assert p.ref_product_proprietary_name == "Humira"

    def test_bla_type_enum(self):
        from services.extraction.biologic_product import BiologicProduct
        with pytest.raises(Exception):
            BiologicProduct(
                proprietary_name="x", proper_name="y",
                bla_number="z", bla_type="bogus",
                license_status="licensed",
                approval_date=date(2020, 1, 1),
                applicant="A",
            )

    def test_extra_fields_forbidden(self):
        from services.extraction.biologic_product import BiologicProduct
        with pytest.raises(Exception):
            BiologicProduct(
                proprietary_name="x", proper_name="y",
                bla_number="z", bla_type="original",
                license_status="licensed",
                approval_date=date(2020, 1, 1),
                applicant="A",
                bogus="boom",
            )


# ────────────────────────────────────────────────────────────────────
# Cat 2 — Parser
# ────────────────────────────────────────────────────────────────────


class TestParser:

    def test_parser_imports(self):
        from connectors.fda_purple_book import parse_purple_book_csv  # noqa: F401

    def test_parses_four_rows(self):
        from connectors.fda_purple_book import parse_purple_book_csv
        records = parse_purple_book_csv(_FIXTURE_PURPLE_BOOK_CSV)
        assert len(records) == 4

    def test_bla_type_normalised(self):
        from connectors.fda_purple_book import parse_purple_book_csv
        records = parse_purple_book_csv(_FIXTURE_PURPLE_BOOK_CSV)
        types = {r.bla_type for r in records}
        assert types == {"original", "biosimilar", "interchangeable"}

    def test_biosimilar_carries_ref_product(self):
        from connectors.fda_purple_book import parse_purple_book_csv
        records = parse_purple_book_csv(_FIXTURE_PURPLE_BOOK_CSV)
        biosimilar = next(r for r in records if r.bla_type == "biosimilar")
        assert biosimilar.ref_product_proprietary_name == "Humira"
        assert biosimilar.ref_product_proper_name == "adalimumab"

    def test_original_has_no_ref_product(self):
        from connectors.fda_purple_book import parse_purple_book_csv
        records = parse_purple_book_csv(_FIXTURE_PURPLE_BOOK_CSV)
        humira = next(r for r in records
                      if r.proprietary_name == "Humira")
        assert humira.ref_product_proprietary_name is None

    def test_approval_date_parsed(self):
        from connectors.fda_purple_book import parse_purple_book_csv
        records = parse_purple_book_csv(_FIXTURE_PURPLE_BOOK_CSV)
        by_name = {r.proprietary_name: r for r in records}
        assert by_name["Humira"].approval_date == date(2002, 12, 31)
        assert by_name["Amjevita"].approval_date == date(2016, 9, 23)

    def test_applicant_extracted(self):
        from connectors.fda_purple_book import parse_purple_book_csv
        records = parse_purple_book_csv(_FIXTURE_PURPLE_BOOK_CSV)
        by_name = {r.proprietary_name: r for r in records}
        assert by_name["Humira"].applicant == "AbbVie Inc."
        assert by_name["Cyltezo"].applicant == \
               "Boehringer Ingelheim Pharmaceuticals Inc."

    def test_empty_csv_returns_empty(self):
        from connectors.fda_purple_book import parse_purple_book_csv
        assert parse_purple_book_csv("") == []
        assert parse_purple_book_csv(
            "Proprietary Name,Proper Name\n",
        ) == []

    def test_malformed_row_skipped_not_raised(self):
        """One bad row must not sink the batch."""
        from connectors.fda_purple_book import parse_purple_book_csv
        bad_csv = (
            "Proprietary Name,Proper Name,BLA Number,BLA Type,Strength,"
            "Dosage Form,Route of Administration,Product Presentation,"
            "License Status,Approval Date,Ref. Product Proprietary Name,"
            "Ref. Product Proper Name,Application Holder\n"
            "X,y,bla,bogus,s,d,r,p,Licensed,2020-01-01,,,A\n"      # bogus type
            "Humira,adalimumab,125057,Original,40 mg,injection,"
            "subcutaneous,syringe,Licensed,2002-12-31,,,AbbVie Inc.\n"
        )
        records = parse_purple_book_csv(bad_csv)
        assert len(records) == 1
        assert records[0].proprietary_name == "Humira"


# ────────────────────────────────────────────────────────────────────
# Cat 3 — Connector
# ────────────────────────────────────────────────────────────────────


class TestConnector:

    def test_connector_imports(self):
        from connectors.fda_purple_book import FdaPurpleBookConnector  # noqa: F401

    def test_constructor_no_network(self):
        from connectors.fda_purple_book import FdaPurpleBookConnector
        c = FdaPurpleBookConnector()
        assert c is not None

    def test_fetch_all_uses_csv_endpoint(self):
        from connectors.fda_purple_book import FdaPurpleBookConnector
        c = FdaPurpleBookConnector()
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, text=_FIXTURE_PURPLE_BOOK_CSV,
            )
            records = c.fetch_all()
            assert len(records) == 4
            args, kwargs = mock_get.call_args
            url = args[0] if args else kwargs.get("url")
            assert "fda" in url.lower()

    def test_fetch_returns_empty_on_404(self):
        from connectors.fda_purple_book import FdaPurpleBookConnector
        c = FdaPurpleBookConnector()
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=404, text="")
            assert c.fetch_all() == []

    def test_fetch_biosimilars_only_filter(self):
        from connectors.fda_purple_book import FdaPurpleBookConnector
        c = FdaPurpleBookConnector()
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, text=_FIXTURE_PURPLE_BOOK_CSV,
            )
            records = c.fetch_biosimilars_and_interchangeables()
            assert len(records) == 2
            assert all(r.bla_type in {"biosimilar", "interchangeable"}
                       for r in records)


# ────────────────────────────────────────────────────────────────────
# Cat 4 — Event emitter (biosimilar approvals only)
# ────────────────────────────────────────────────────────────────────


def _sample_biosimilar(bla_type: str = "biosimilar"):
    from services.extraction.biologic_product import BiologicProduct
    return BiologicProduct(
        proprietary_name="Amjevita",
        proper_name="adalimumab-atto",
        bla_number="761024",
        bla_type=bla_type,
        license_status="licensed",
        approval_date=date(2016, 9, 23),
        applicant="Amgen Inc.",
        ref_product_proprietary_name="Humira",
        ref_product_proper_name="adalimumab",
    )


class TestEventEmitter:

    def test_emitter_imports(self):
        from services.event_emitters.biosimilar_approval import build_event_row  # noqa: F401

    def test_event_row_has_required_fields(self):
        from services.event_emitters.biosimilar_approval import build_event_row
        row = build_event_row(
            product=_sample_biosimilar(),
            biosimilar_drug_id="11111111-1111-1111-1111-111111111111",
            reference_drug_id="22222222-2222-2222-2222-222222222222",
            applicant_company_id="33333333-3333-3333-3333-333333333333",
            source_document_id="44444444-4444-4444-4444-444444444444",
            disclosed_date=date(2016, 9, 23),
        )
        assert row["event_type"] == "biosimilar_approval"
        # Primary entity = the BRANDED biologic (the threat target)
        assert row["primary_entity_type"] == "drug"
        assert row["primary_entity_id"] == \
               "22222222-2222-2222-2222-222222222222"
        assert row["source_tier"] == "tier_1"
        assert row["trust_score"] >= 0.9

    def test_biosimilar_high_impact(self):
        from services.event_emitters.biosimilar_approval import build_event_row
        row = build_event_row(
            product=_sample_biosimilar("biosimilar"),
            biosimilar_drug_id="b", reference_drug_id="r",
            applicant_company_id="c",
            source_document_id="s", disclosed_date=date(2016, 9, 23),
        )
        assert row["impact_hint"] == "high"

    def test_interchangeable_high_impact_too(self):
        """Interchangeable biosimilars are even more competitive
        (auto-substitution at the pharmacy)."""
        from services.event_emitters.biosimilar_approval import build_event_row
        row = build_event_row(
            product=_sample_biosimilar("interchangeable"),
            biosimilar_drug_id="b", reference_drug_id="r",
            applicant_company_id="c",
            source_document_id="s", disclosed_date=date(2017, 8, 25),
        )
        assert row["impact_hint"] == "high"

    def test_event_hash_deterministic(self):
        from services.event_emitters.biosimilar_approval import build_event_row
        kwargs = dict(
            product=_sample_biosimilar(),
            biosimilar_drug_id="b", reference_drug_id="r",
            applicant_company_id="c",
            source_document_id="s",
            disclosed_date=date(2016, 9, 23),
        )
        r1 = build_event_row(**kwargs)
        r2 = build_event_row(**kwargs)
        assert r1["event_hash"] == r2["event_hash"]
        assert len(r1["event_hash"]) == 64

    def test_payload_carries_metadata(self):
        from services.event_emitters.biosimilar_approval import build_event_row
        row = build_event_row(
            product=_sample_biosimilar(),
            biosimilar_drug_id="b", reference_drug_id="r",
            applicant_company_id="c",
            source_document_id="s", disclosed_date=date(2016, 9, 23),
        )
        payload = row["payload"]
        assert payload["proprietary_name"] == "Amjevita"
        assert payload["bla_number"] == "761024"
        assert payload["bla_type"] == "biosimilar"
        assert payload["ref_product_proprietary_name"] == "Humira"
