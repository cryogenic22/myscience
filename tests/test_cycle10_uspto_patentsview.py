"""Cycle 10 — USPTO PatentsView connector (A5.1).

PatentsView is the USPTO's free patent-search API. Provides granted
patents with assignee, inventors, classification, abstract, and key
dates. This is the data spine for KBQ 6 (SWOT — patent / LOE risk)
and feeds the Cycle N+ LOE computation service (A5.2).

Cycle 10 delivers:
  - PatentRecord schema (services/extraction/patent.PatentRecord)
  - Connector + parser (connectors/uspto_patentsview.py)
  - Event emitter (services/event_emitters/patent_grant.build_event_row)
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest


_FIXTURE_PATENTSVIEW_RESPONSE = {
    "patents": [
        {
            "patent_number": "10,123,456",
            "patent_title": "Method of treating diabetes with tirzepatide",
            "patent_abstract": "Methods are disclosed for the treatment "
                                "of type 2 diabetes mellitus using a "
                                "compound of formula I (tirzepatide) ...",
            "patent_date": "2024-03-12",
            "patent_num_claims": 25,
            "assignees": [
                {
                    "assignee_organization": "Eli Lilly and Company",
                    "assignee_country": "US",
                },
            ],
            "inventors": [
                {"inventor_first_name": "Jane", "inventor_last_name": "Smith"},
                {"inventor_first_name": "John", "inventor_last_name": "Doe"},
            ],
            "cpcs": [
                {"cpc_group_id": "A61K38/26",
                 "cpc_group_title": "Glucagon-like peptides"},
            ],
            "application_number": "16/123,456",
            "filing_date": "2020-01-15",
        },
        {
            "patent_number": "10,987,654",
            "patent_title": "Combination therapy of GLP-1 and SGLT2",
            "patent_abstract": "Pharmaceutical compositions ...",
            "patent_date": "2024-04-09",
            "patent_num_claims": 18,
            "assignees": [
                {
                    "assignee_organization": "Boehringer Ingelheim International GmbH",
                    "assignee_country": "DE",
                },
            ],
            "inventors": [],
            "cpcs": [],
            "application_number": "17/777,888",
            "filing_date": "2021-06-22",
        },
    ],
    "count": 2,
    "total_patent_count": 2,
}


# ────────────────────────────────────────────────────────────────────
# Cat 1 — Schema
# ────────────────────────────────────────────────────────────────────


class TestSchema:

    def test_schema_imports(self):
        from services.extraction.patent import PatentRecord  # noqa: F401

    def test_minimum_validates(self):
        from services.extraction.patent import PatentRecord
        p = PatentRecord(
            patent_number="10,123,456",
            title="Method of treating X",
            assignee_name="Eli Lilly and Company",
            grant_date=date(2024, 3, 12),
        )
        assert p.patent_number == "10,123,456"

    def test_extra_fields_forbidden(self):
        from services.extraction.patent import PatentRecord
        with pytest.raises(Exception):
            PatentRecord(
                patent_number="x", title="t", assignee_name="a",
                grant_date=date(2024, 1, 1),
                bogus="boom",
            )

    def test_optional_fields(self):
        from services.extraction.patent import PatentRecord
        p = PatentRecord(
            patent_number="10,123,456",
            title="Method of treating X",
            assignee_name="Lilly",
            grant_date=date(2024, 3, 12),
            abstract="An abstract",
            filing_date=date(2020, 1, 15),
            application_number="16/123,456",
            inventors=["Jane Smith", "John Doe"],
            num_claims=25,
            cpc_groups=["A61K38/26"],
        )
        assert len(p.inventors) == 2
        assert p.num_claims == 25


# ────────────────────────────────────────────────────────────────────
# Cat 2 — Parser
# ────────────────────────────────────────────────────────────────────


class TestParser:

    def test_parser_imports(self):
        from connectors.uspto_patentsview import parse_patentsview_response  # noqa: F401

    def test_parses_two_patents(self):
        from connectors.uspto_patentsview import parse_patentsview_response
        records = parse_patentsview_response(_FIXTURE_PATENTSVIEW_RESPONSE)
        assert len(records) == 2

    def test_patent_number_carried(self):
        from connectors.uspto_patentsview import parse_patentsview_response
        records = parse_patentsview_response(_FIXTURE_PATENTSVIEW_RESPONSE)
        nums = {r.patent_number for r in records}
        assert nums == {"10,123,456", "10,987,654"}

    def test_assignee_extracted(self):
        from connectors.uspto_patentsview import parse_patentsview_response
        records = parse_patentsview_response(_FIXTURE_PATENTSVIEW_RESPONSE)
        by_num = {r.patent_number: r for r in records}
        assert by_num["10,123,456"].assignee_name == "Eli Lilly and Company"

    def test_grant_date_parsed(self):
        from connectors.uspto_patentsview import parse_patentsview_response
        records = parse_patentsview_response(_FIXTURE_PATENTSVIEW_RESPONSE)
        by_num = {r.patent_number: r for r in records}
        assert by_num["10,123,456"].grant_date == date(2024, 3, 12)

    def test_inventors_flattened(self):
        from connectors.uspto_patentsview import parse_patentsview_response
        records = parse_patentsview_response(_FIXTURE_PATENTSVIEW_RESPONSE)
        by_num = {r.patent_number: r for r in records}
        assert "Jane Smith" in by_num["10,123,456"].inventors

    def test_cpc_groups_flattened(self):
        from connectors.uspto_patentsview import parse_patentsview_response
        records = parse_patentsview_response(_FIXTURE_PATENTSVIEW_RESPONSE)
        by_num = {r.patent_number: r for r in records}
        assert "A61K38/26" in by_num["10,123,456"].cpc_groups

    def test_filing_date_parsed(self):
        from connectors.uspto_patentsview import parse_patentsview_response
        records = parse_patentsview_response(_FIXTURE_PATENTSVIEW_RESPONSE)
        by_num = {r.patent_number: r for r in records}
        assert by_num["10,123,456"].filing_date == date(2020, 1, 15)

    def test_empty_response_returns_empty(self):
        from connectors.uspto_patentsview import parse_patentsview_response
        assert parse_patentsview_response({}) == []
        assert parse_patentsview_response({"patents": []}) == []


# ────────────────────────────────────────────────────────────────────
# Cat 3 — Connector
# ────────────────────────────────────────────────────────────────────


class TestConnector:

    def test_connector_imports(self):
        from connectors.uspto_patentsview import PatentsViewConnector  # noqa: F401

    def test_constructor_no_network(self):
        from connectors.uspto_patentsview import PatentsViewConnector
        c = PatentsViewConnector()
        assert c is not None

    def test_search_by_assignee_uses_api(self):
        from connectors.uspto_patentsview import PatentsViewConnector
        c = PatentsViewConnector()
        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                json=lambda: _FIXTURE_PATENTSVIEW_RESPONSE,
            )
            records = c.search_by_assignee(
                assignee_name="Eli Lilly",
                limit=10,
            )
            assert len(records) == 2
            args, kwargs = mock_post.call_args
            url = args[0] if args else kwargs.get("url")
            assert "patentsview.org" in url

    def test_search_by_text_uses_api(self):
        from connectors.uspto_patentsview import PatentsViewConnector
        c = PatentsViewConnector()
        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=200,
                json=lambda: _FIXTURE_PATENTSVIEW_RESPONSE,
            )
            records = c.search_by_text(
                text_query="tirzepatide",
                limit=10,
            )
            assert len(records) == 2

    def test_search_returns_empty_on_404(self):
        from connectors.uspto_patentsview import PatentsViewConnector
        c = PatentsViewConnector()
        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                status_code=404, json=lambda: {},
            )
            assert c.search_by_assignee(assignee_name="x") == []


# ────────────────────────────────────────────────────────────────────
# Cat 4 — Event emitter
# ────────────────────────────────────────────────────────────────────


def _sample_patent(patent_number: str = "10,123,456"):
    from services.extraction.patent import PatentRecord
    return PatentRecord(
        patent_number=patent_number,
        title="Method of treating diabetes with tirzepatide",
        assignee_name="Eli Lilly and Company",
        grant_date=date(2024, 3, 12),
        abstract="Methods of treatment ...",
        filing_date=date(2020, 1, 15),
        application_number="16/123,456",
        inventors=["Jane Smith"],
        num_claims=25,
        cpc_groups=["A61K38/26"],
    )


class TestEventEmitter:

    def test_emitter_imports(self):
        from services.event_emitters.patent_grant import build_event_row  # noqa: F401

    def test_event_row_has_required_fields(self):
        from services.event_emitters.patent_grant import build_event_row
        row = build_event_row(
            patent=_sample_patent(),
            company_id="11111111-1111-1111-1111-111111111111",
            company_name="Eli Lilly",
            source_document_id="22222222-2222-2222-2222-222222222222",
            disclosed_date=date(2024, 3, 12),
        )
        assert row["event_type"] == "patent_grant"
        assert row["primary_entity_type"] == "company"
        assert row["source_tier"] == "tier_1"
        assert row["trust_score"] >= 0.9
        assert "event_hash" in row

    def test_high_claim_count_high_impact(self):
        """Many claims = broader patent → high impact."""
        from services.event_emitters.patent_grant import build_event_row
        from services.extraction.patent import PatentRecord
        big = PatentRecord(
            patent_number="10,123,456", title="t",
            assignee_name="L", grant_date=date(2024, 3, 12),
            num_claims=50,
        )
        row = build_event_row(
            patent=big, company_id="c", company_name="C",
            source_document_id="s", disclosed_date=date(2024, 3, 12),
        )
        assert row["impact_hint"] == "high"

    def test_low_claim_count_low_impact(self):
        from services.event_emitters.patent_grant import build_event_row
        from services.extraction.patent import PatentRecord
        small = PatentRecord(
            patent_number="10,123,456", title="t",
            assignee_name="L", grant_date=date(2024, 3, 12),
            num_claims=3,
        )
        row = build_event_row(
            patent=small, company_id="c", company_name="C",
            source_document_id="s", disclosed_date=date(2024, 3, 12),
        )
        assert row["impact_hint"] == "low"

    def test_event_hash_deterministic(self):
        from services.event_emitters.patent_grant import build_event_row
        kwargs = dict(
            patent=_sample_patent(),
            company_id="c", company_name="C",
            source_document_id="s",
            disclosed_date=date(2024, 3, 12),
        )
        r1 = build_event_row(**kwargs)
        r2 = build_event_row(**kwargs)
        assert r1["event_hash"] == r2["event_hash"]

    def test_payload_carries_metadata(self):
        from services.event_emitters.patent_grant import build_event_row
        row = build_event_row(
            patent=_sample_patent(),
            company_id="c", company_name="C",
            source_document_id="s",
            disclosed_date=date(2024, 3, 12),
        )
        payload = row["payload"]
        assert payload["patent_number"] == "10,123,456"
        assert payload["assignee_name"] == "Eli Lilly and Company"
        assert payload["num_claims"] == 25
        assert payload["filing_date"] == "2020-01-15"
