"""Cycle 7 — EMA CHMP opinion connector + parser (A6.1).

CHMP (Committee for Medicinal Products for Human Use) issues
monthly opinions on Marketing Authorization Applications. EMA
publishes these as meeting-highlights pages with structured tables:

  - Positive opinions on new medicines
  - Recommendations on extensions of therapeutic indication
  - Negative opinions on new medicines
  - Withdrawals of new applications

Each row gives drug INN, brand name, applicant (MAH), indication.
This cycle delivers:

  1. Pure parser  — services/ema_chmp_parser.parse_highlights(html)
  2. Connector    — connectors/ema_chmp.EMAChmpConnector
  3. Schema       — services/extraction/ema_chmp_opinion.ChmpOpinion
  4. Event emitter— services/event_emitters/ema_chmp_opinion.build_event_row
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest


# ────────────────────────────────────────────────────────────────────
# Fixture HTML — abridged CHMP highlights page
# ────────────────────────────────────────────────────────────────────


_FIXTURE_HIGHLIGHTS_HTML = """<!DOCTYPE html>
<html><body>
<h1>Meeting highlights from the CHMP, 15-18 April 2026</h1>

<h2>Positive opinions on new medicines</h2>
<table>
  <thead><tr>
    <th>Name</th><th>INN</th><th>Applicant</th><th>Indication</th>
  </tr></thead>
  <tbody>
    <tr>
      <td>Ozembrand</td>
      <td>tirzepatide</td>
      <td>Eli Lilly Nederland B.V.</td>
      <td>Type 2 diabetes mellitus</td>
    </tr>
    <tr>
      <td>Verquvo</td>
      <td>vericiguat</td>
      <td>Bayer AG</td>
      <td>Heart failure with reduced ejection fraction</td>
    </tr>
  </tbody>
</table>

<h2>Negative opinions on new medicines</h2>
<table>
  <thead><tr>
    <th>Name</th><th>INN</th><th>Applicant</th><th>Indication</th>
  </tr></thead>
  <tbody>
    <tr>
      <td>FailDrug</td>
      <td>flunkomab</td>
      <td>SmallBio S.A.</td>
      <td>Severe rare condition X</td>
    </tr>
  </tbody>
</table>

<h2>Withdrawals of new applications</h2>
<table>
  <thead><tr>
    <th>Name</th><th>INN</th><th>Applicant</th><th>Indication</th>
  </tr></thead>
  <tbody>
    <tr>
      <td>WithdrawnDrug</td>
      <td>cancellumab</td>
      <td>BigPharma A/S</td>
      <td>Rheumatoid arthritis</td>
    </tr>
  </tbody>
</table>
</body></html>
"""


# ────────────────────────────────────────────────────────────────────
# Cat 1 — Schema
# ────────────────────────────────────────────────────────────────────


class TestSchema:

    def test_schema_imports(self):
        from services.extraction.ema_chmp_opinion import ChmpOpinion  # noqa: F401

    def test_minimum_fields_validate(self):
        from services.extraction.ema_chmp_opinion import ChmpOpinion
        op = ChmpOpinion(
            inn="tirzepatide",
            brand_name="Ozembrand",
            applicant="Eli Lilly Nederland B.V.",
            opinion_type="positive",
            opinion_date=date(2026, 4, 18),
            indication="Type 2 diabetes mellitus",
        )
        assert op.inn == "tirzepatide"
        assert op.opinion_type == "positive"

    def test_opinion_type_enum(self):
        from services.extraction.ema_chmp_opinion import ChmpOpinion
        with pytest.raises(Exception):
            ChmpOpinion(
                inn="x", brand_name="X", applicant="A",
                opinion_type="bogus", opinion_date=date(2026, 4, 18),
                indication="...",
            )

    def test_extra_fields_forbidden(self):
        from services.extraction.ema_chmp_opinion import ChmpOpinion
        with pytest.raises(Exception):
            ChmpOpinion(
                inn="x", brand_name="X", applicant="A",
                opinion_type="positive",
                opinion_date=date(2026, 4, 18),
                indication="...",
                extra_garbage="boom",
            )


# ────────────────────────────────────────────────────────────────────
# Cat 2 — Parser
# ────────────────────────────────────────────────────────────────────


class TestParser:

    def test_parser_imports(self):
        from services.ema_chmp_parser import parse_highlights  # noqa: F401

    def test_extracts_three_groups(self):
        from services.ema_chmp_parser import parse_highlights
        opinions = parse_highlights(
            _FIXTURE_HIGHLIGHTS_HTML,
            opinion_date=date(2026, 4, 18),
        )
        # 2 positive + 1 negative + 1 withdrawn = 4
        assert len(opinions) == 4

    def test_positive_opinions_typed(self):
        from services.ema_chmp_parser import parse_highlights
        opinions = parse_highlights(
            _FIXTURE_HIGHLIGHTS_HTML,
            opinion_date=date(2026, 4, 18),
        )
        positives = [o for o in opinions if o.opinion_type == "positive"]
        assert len(positives) == 2
        inns = {o.inn for o in positives}
        assert "tirzepatide" in inns
        assert "vericiguat" in inns

    def test_negative_opinion_typed(self):
        from services.ema_chmp_parser import parse_highlights
        opinions = parse_highlights(
            _FIXTURE_HIGHLIGHTS_HTML,
            opinion_date=date(2026, 4, 18),
        )
        negatives = [o for o in opinions if o.opinion_type == "negative"]
        assert len(negatives) == 1
        assert negatives[0].inn == "flunkomab"

    def test_withdrawal_typed(self):
        from services.ema_chmp_parser import parse_highlights
        opinions = parse_highlights(
            _FIXTURE_HIGHLIGHTS_HTML,
            opinion_date=date(2026, 4, 18),
        )
        withdrawals = [o for o in opinions if o.opinion_type == "withdrawn"]
        assert len(withdrawals) == 1
        assert withdrawals[0].inn == "cancellumab"

    def test_applicant_extracted(self):
        from services.ema_chmp_parser import parse_highlights
        opinions = parse_highlights(
            _FIXTURE_HIGHLIGHTS_HTML,
            opinion_date=date(2026, 4, 18),
        )
        by_inn = {o.inn: o for o in opinions}
        assert by_inn["tirzepatide"].applicant == "Eli Lilly Nederland B.V."
        assert by_inn["vericiguat"].applicant == "Bayer AG"

    def test_indication_extracted(self):
        from services.ema_chmp_parser import parse_highlights
        opinions = parse_highlights(
            _FIXTURE_HIGHLIGHTS_HTML,
            opinion_date=date(2026, 4, 18),
        )
        by_inn = {o.inn: o for o in opinions}
        assert "Type 2 diabetes" in by_inn["tirzepatide"].indication
        assert "Heart failure" in by_inn["vericiguat"].indication

    def test_brand_name_extracted(self):
        from services.ema_chmp_parser import parse_highlights
        opinions = parse_highlights(
            _FIXTURE_HIGHLIGHTS_HTML,
            opinion_date=date(2026, 4, 18),
        )
        by_inn = {o.inn: o for o in opinions}
        assert by_inn["tirzepatide"].brand_name == "Ozembrand"

    def test_empty_html_returns_empty_list(self):
        from services.ema_chmp_parser import parse_highlights
        assert parse_highlights("<html></html>", opinion_date=date(2026, 1, 1)) == []

    def test_malformed_section_skipped(self):
        from services.ema_chmp_parser import parse_highlights
        html = """<html><body>
        <h2>Random unrelated table</h2>
        <table><tr><td>noise</td></tr></table>
        </body></html>"""
        # No CHMP-recognised section headers → no opinions extracted
        assert parse_highlights(html, opinion_date=date(2026, 1, 1)) == []


# ────────────────────────────────────────────────────────────────────
# Cat 3 — Connector (HTTP-mocked)
# ────────────────────────────────────────────────────────────────────


class TestConnector:

    def test_connector_imports(self):
        from connectors.ema_chmp import EMAChmpConnector  # noqa: F401

    def test_constructor_no_network(self):
        from connectors.ema_chmp import EMAChmpConnector
        c = EMAChmpConnector()
        assert c is not None

    def test_fetch_meeting_highlights_uses_mocked_http(self):
        from connectors.ema_chmp import EMAChmpConnector
        c = EMAChmpConnector()
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, text=_FIXTURE_HIGHLIGHTS_HTML,
            )
            opinions = c.fetch_meeting_highlights(
                meeting_url="https://www.ema.europa.eu/en/news/foo",
                opinion_date=date(2026, 4, 18),
            )
            assert len(opinions) == 4
            args, kwargs = mock_get.call_args
            assert "ema.europa.eu" in (args[0] if args else kwargs.get("url"))

    def test_fetch_returns_empty_on_404(self):
        from connectors.ema_chmp import EMAChmpConnector
        c = EMAChmpConnector()
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=404, text="")
            opinions = c.fetch_meeting_highlights(
                meeting_url="https://www.ema.europa.eu/missing",
                opinion_date=date(2026, 4, 18),
            )
            assert opinions == []


# ────────────────────────────────────────────────────────────────────
# Cat 4 — Event emitter
# ────────────────────────────────────────────────────────────────────


def _sample_opinion(opinion_type: str = "positive"):
    from services.extraction.ema_chmp_opinion import ChmpOpinion
    return ChmpOpinion(
        inn="tirzepatide",
        brand_name="Ozembrand",
        applicant="Eli Lilly Nederland B.V.",
        opinion_type=opinion_type,
        opinion_date=date(2026, 4, 18),
        indication="Type 2 diabetes mellitus",
    )


class TestEventEmitter:

    def test_emitter_imports(self):
        from services.event_emitters.ema_chmp_opinion import build_event_row  # noqa: F401

    def test_event_row_has_required_fields(self):
        from services.event_emitters.ema_chmp_opinion import build_event_row
        row = build_event_row(
            opinion=_sample_opinion(),
            drug_id="11111111-1111-1111-1111-111111111111",
            company_id="22222222-2222-2222-2222-222222222222",
            company_name="Eli Lilly Nederland B.V.",
            source_document_id="33333333-3333-3333-3333-333333333333",
            disclosed_date=date(2026, 4, 18),
        )
        assert row["event_type"] == "ema_chmp_opinion"
        assert row["primary_entity_type"] == "drug"
        assert row["primary_entity_id"] == \
               "11111111-1111-1111-1111-111111111111"
        assert row["event_date"] == date(2026, 4, 18)
        assert row["source_tier"] == "tier_1"   # EMA = tier 1
        assert row["trust_score"] >= 0.9
        assert "event_hash" in row
        assert len(row["event_hash"]) == 64

    def test_negative_opinion_high_impact(self):
        from services.event_emitters.ema_chmp_opinion import build_event_row
        row = build_event_row(
            opinion=_sample_opinion(opinion_type="negative"),
            drug_id="d", company_id="c", company_name="C",
            source_document_id="s",
            disclosed_date=date(2026, 4, 18),
        )
        assert row["impact_hint"] == "high"

    def test_withdrawn_opinion_high_impact(self):
        from services.event_emitters.ema_chmp_opinion import build_event_row
        row = build_event_row(
            opinion=_sample_opinion(opinion_type="withdrawn"),
            drug_id="d", company_id="c", company_name="C",
            source_document_id="s",
            disclosed_date=date(2026, 4, 18),
        )
        assert row["impact_hint"] == "high"

    def test_positive_opinion_high_impact_too(self):
        """First-cycle EMA approval is market-moving."""
        from services.event_emitters.ema_chmp_opinion import build_event_row
        row = build_event_row(
            opinion=_sample_opinion(opinion_type="positive"),
            drug_id="d", company_id="c", company_name="C",
            source_document_id="s",
            disclosed_date=date(2026, 4, 18),
        )
        assert row["impact_hint"] == "high"

    def test_extension_opinion_medium_impact(self):
        """Label extension to a new indication = medium (less binary
        than first approval)."""
        from services.event_emitters.ema_chmp_opinion import build_event_row
        row = build_event_row(
            opinion=_sample_opinion(opinion_type="extension"),
            drug_id="d", company_id="c", company_name="C",
            source_document_id="s",
            disclosed_date=date(2026, 4, 18),
        )
        assert row["impact_hint"] == "medium"

    def test_event_hash_deterministic(self):
        from services.event_emitters.ema_chmp_opinion import build_event_row
        kwargs = dict(
            opinion=_sample_opinion(),
            drug_id="d", company_id="c", company_name="C",
            source_document_id="s",
            disclosed_date=date(2026, 4, 18),
        )
        r1 = build_event_row(**kwargs)
        r2 = build_event_row(**kwargs)
        assert r1["event_hash"] == r2["event_hash"]

    def test_payload_has_inn_and_indication(self):
        from services.event_emitters.ema_chmp_opinion import build_event_row
        row = build_event_row(
            opinion=_sample_opinion(),
            drug_id="d", company_id="c", company_name="C",
            source_document_id="s",
            disclosed_date=date(2026, 4, 18),
        )
        payload = row["payload"]
        assert payload["inn"] == "tirzepatide"
        assert payload["brand_name"] == "Ozembrand"
        assert "diabetes" in payload["indication"]
        assert payload["opinion_type"] == "positive"
