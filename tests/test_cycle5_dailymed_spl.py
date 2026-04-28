"""Cycle 5 — DailyMed SPL connector + section-keyed parser (A4.1).

DailyMed (NIH) is the canonical store of FDA-approved drug labels in
SPL (Structured Product Labeling) XML format. Each label decomposes
into LOINC-coded sections — the same code maps to the same conceptual
section across all drugs, which is what makes section-level diffing
(Cycle 6 / A4.2) work.

This cycle delivers the building blocks:

  1. SPL XML parser (services/spl_section_parser.py)
       parse_sections(xml_text) → list[SplSection]
       extract_section_text(section_element) → str

  2. DailyMed connector (connectors/dailymed_spl.py)
       fetch_spl_xml(setid)            → XML text
       list_setids_for_drug(drug_name) → list[str]
       list_changes_since(date)        → list[setid]

The connector wraps requests, retries, and handles the v2 JSON +
XML endpoints. The parser is pure (no I/O) so it's testable on
fixture XML. The diff service (Cycle 6) consumes parser output.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ────────────────────────────────────────────────────────────────────
# Fixture XML — minimal SPL with three sections (LOINC-coded)
# ────────────────────────────────────────────────────────────────────


_FIXTURE_SPL_XML = """<?xml version="1.0" encoding="UTF-8"?>
<document xmlns="urn:hl7-org:v3">
  <id root="00000000-0000-0000-0000-000000000001"/>
  <code code="34390-5" codeSystem="2.16.840.1.113883.6.1"
        displayName="HUMAN PRESCRIPTION DRUG LABEL"/>
  <title>EXAMPLE DRUG (test only) Tablets</title>
  <component>
    <structuredBody>
      <component>
        <section>
          <code code="34066-1" codeSystem="2.16.840.1.113883.6.1"
                displayName="BOXED WARNING"/>
          <title>BOXED WARNING</title>
          <text>
            <paragraph>WARNING: SERIOUS RISK</paragraph>
            <paragraph>This drug carries a risk of X.</paragraph>
          </text>
        </section>
      </component>
      <component>
        <section>
          <code code="34067-9" codeSystem="2.16.840.1.113883.6.1"
                displayName="INDICATIONS AND USAGE"/>
          <title>1 INDICATIONS AND USAGE</title>
          <text>
            <paragraph>Indicated for the treatment of condition Y.</paragraph>
          </text>
        </section>
      </component>
      <component>
        <section>
          <code code="34071-1" codeSystem="2.16.840.1.113883.6.1"
                displayName="ADVERSE REACTIONS"/>
          <title>6 ADVERSE REACTIONS</title>
          <text>
            <paragraph>Most common adverse reactions: nausea, fatigue.</paragraph>
            <list>
              <item>nausea (12%)</item>
              <item>fatigue (8%)</item>
              <item>headache (5%)</item>
            </list>
          </text>
        </section>
      </component>
    </structuredBody>
  </component>
</document>
"""


# ────────────────────────────────────────────────────────────────────
# Cat 1 — Parser module
# ────────────────────────────────────────────────────────────────────


class TestParserModule:

    def test_module_imports(self):
        from services.spl_section_parser import parse_sections  # noqa: F401

    def test_spl_section_dataclass_exists(self):
        from services.spl_section_parser import SplSection
        s = SplSection(loinc_code="34066-1", display_name="BOXED WARNING",
                       title="BOXED WARNING", text="content")
        assert s.loinc_code == "34066-1"


# ────────────────────────────────────────────────────────────────────
# Cat 2 — Section extraction
# ────────────────────────────────────────────────────────────────────


class TestSectionExtraction:

    def test_extracts_three_sections(self):
        from services.spl_section_parser import parse_sections
        sections = parse_sections(_FIXTURE_SPL_XML)
        assert len(sections) == 3

    def test_loinc_codes_extracted(self):
        from services.spl_section_parser import parse_sections
        sections = parse_sections(_FIXTURE_SPL_XML)
        codes = {s.loinc_code for s in sections}
        assert codes == {"34066-1", "34067-9", "34071-1"}

    def test_display_names_extracted(self):
        from services.spl_section_parser import parse_sections
        sections = parse_sections(_FIXTURE_SPL_XML)
        by_code = {s.loinc_code: s for s in sections}
        assert by_code["34066-1"].display_name == "BOXED WARNING"
        assert by_code["34067-9"].display_name == "INDICATIONS AND USAGE"
        assert by_code["34071-1"].display_name == "ADVERSE REACTIONS"

    def test_text_content_flattened(self):
        from services.spl_section_parser import parse_sections
        sections = parse_sections(_FIXTURE_SPL_XML)
        by_code = {s.loinc_code: s for s in sections}
        assert "SERIOUS RISK" in by_code["34066-1"].text
        assert "risk of X" in by_code["34066-1"].text

    def test_list_items_preserved(self):
        from services.spl_section_parser import parse_sections
        sections = parse_sections(_FIXTURE_SPL_XML)
        by_code = {s.loinc_code: s for s in sections}
        text = by_code["34071-1"].text
        assert "nausea" in text
        assert "fatigue" in text
        assert "headache" in text


# ────────────────────────────────────────────────────────────────────
# Cat 3 — Edge cases
# ────────────────────────────────────────────────────────────────────


class TestParserEdgeCases:

    def test_empty_xml_returns_empty_list(self):
        from services.spl_section_parser import parse_sections
        assert parse_sections(
            '<?xml version="1.0"?><document xmlns="urn:hl7-org:v3"/>'
        ) == []

    def test_malformed_xml_raises(self):
        from services.spl_section_parser import parse_sections
        with pytest.raises(Exception):
            parse_sections("not even close to xml")

    def test_section_without_loinc_code_dropped(self):
        from services.spl_section_parser import parse_sections
        xml = """<?xml version="1.0"?>
        <document xmlns="urn:hl7-org:v3">
          <component>
            <structuredBody>
              <component>
                <section>
                  <title>untyped</title>
                  <text><paragraph>x</paragraph></text>
                </section>
              </component>
            </structuredBody>
          </component>
        </document>"""
        sections = parse_sections(xml)
        assert sections == []


# ────────────────────────────────────────────────────────────────────
# Cat 4 — Connector module
# ────────────────────────────────────────────────────────────────────


class TestConnectorModule:

    def test_module_imports(self):
        from connectors.dailymed_spl import DailyMedSplConnector  # noqa: F401

    def test_constructor_does_not_fetch(self):
        """No HTTP at construction — constructor just sets defaults."""
        from connectors.dailymed_spl import DailyMedSplConnector
        c = DailyMedSplConnector()
        assert c is not None


# ────────────────────────────────────────────────────────────────────
# Cat 5 — Connector fetch_spl_xml
# ────────────────────────────────────────────────────────────────────


class TestFetchSplXml:

    def test_fetches_xml_for_setid(self):
        from connectors.dailymed_spl import DailyMedSplConnector
        c = DailyMedSplConnector()
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock(status_code=200, text=_FIXTURE_SPL_XML)
            mock_get.return_value = mock_resp
            xml = c.fetch_spl_xml(setid="abc-123")
            assert "<document" in xml
            # Make sure we hit the v2 XML endpoint with setid
            args, kwargs = mock_get.call_args
            url = args[0] if args else kwargs.get("url")
            assert "abc-123" in url
            assert "/v2/spls/" in url or "/v2/" in url

    def test_returns_none_on_404(self):
        from connectors.dailymed_spl import DailyMedSplConnector
        c = DailyMedSplConnector()
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=404, text="")
            xml = c.fetch_spl_xml(setid="missing")
            assert xml is None


# ────────────────────────────────────────────────────────────────────
# Cat 6 — Connector list_setids_for_drug
# ────────────────────────────────────────────────────────────────────


class TestListSetidsForDrug:

    def test_lists_setids_from_json_response(self):
        from connectors.dailymed_spl import DailyMedSplConnector
        c = DailyMedSplConnector()
        fake_json = {
            "data": [
                {"setid": "set-1", "title": "DRUG ONE 10mg"},
                {"setid": "set-2", "title": "DRUG ONE 20mg"},
            ],
            "metadata": {"total_pages": 1, "current_page": 1},
        }
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: fake_json,
            )
            setids = c.list_setids_for_drug(drug_name="drug one")
            assert setids == ["set-1", "set-2"]

    def test_returns_empty_when_no_results(self):
        from connectors.dailymed_spl import DailyMedSplConnector
        c = DailyMedSplConnector()
        empty_json = {"data": [], "metadata": {}}
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: empty_json,
            )
            assert c.list_setids_for_drug(drug_name="nonsense") == []


# ────────────────────────────────────────────────────────────────────
# Cat 7 — End-to-end: connector → parser
# ────────────────────────────────────────────────────────────────────


class TestEndToEnd:

    def test_fetch_then_parse(self):
        from connectors.dailymed_spl import DailyMedSplConnector
        from services.spl_section_parser import parse_sections

        c = DailyMedSplConnector()
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, text=_FIXTURE_SPL_XML,
            )
            xml = c.fetch_spl_xml(setid="abc")
            sections = parse_sections(xml)
            codes = {s.loinc_code for s in sections}
            assert codes == {"34066-1", "34067-9", "34071-1"}
