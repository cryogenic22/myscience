"""A2.1 — 8-K Item 5.02 parser → exec_change events (TDD).

SPEC-016 §7 swimlane A2, task A2.1. The 8-K parser is the single
highest-leverage connector extension — Items 1.01, 2.02, 5.02, 8.01
unlock four KBQs (Deal, Financial, Exec, CRL).

This PR ships Item 5.02 (Departure/Election of Directors or Principal
Officers) — most structured Item, simplest start. Same pattern then
templates for A2.2/A2.3/A2.4.

Architecture
  - Pydantic-locked extraction schema (ExecChangeExtraction)
  - Rule-based header detection (no LLM needed)
  - Extractor Protocol — real LLM is a thin wrapper, tests use a stub
  - transition_id pairing for paired exit + arrival within window
  - Event-row builder returning a dict (not writing DB) — keeps unit
    tests pure; the writer is a thin layer added in A7

Test categories
  Cat 1 — Pydantic schema invariants
  Cat 2 — Header detection (regex on filing text)
  Cat 3 — Parser orchestration with stub extractor
  Cat 4 — transition_id pairing logic
  Cat 5 — Event-row builder shape + idempotency
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest


# ────────────────────────────────────────────────────────────────────
# Fixtures — synthetic filing snippets covering common Item 5.02 shapes
# ────────────────────────────────────────────────────────────────────

ITEM_5_02_DEPARTURE_ONLY = """
SECURITIES AND EXCHANGE COMMISSION
Washington, D.C. 20549

FORM 8-K

CURRENT REPORT

Pursuant to Section 13 or 15(d) of the Securities Exchange Act of 1934

Date of Report (Date of earliest event reported): April 15, 2026

PFIZER INC.
(Exact name of registrant as specified in its charter)

Item 5.02 Departure of Directors or Certain Officers; Election of Directors;
Appointment of Certain Officers; Compensatory Arrangements of Certain Officers.

On April 15, 2026, Mikael Dolsten, M.D., Ph.D., Chief Scientific Officer and
President, Worldwide Research, Development and Medical of Pfizer Inc. (the
"Company"), notified the Company of his decision to retire from the Company,
effective June 30, 2026. The Company has commenced a search for his successor.

Item 9.01 Financial Statements and Exhibits.
"""

ITEM_5_02_DEPARTURE_AND_APPOINTMENT = """
Item 5.02 Departure of Directors or Certain Officers; Election of Directors;
Appointment of Certain Officers; Compensatory Arrangements of Certain Officers.

(b) Departure of Principal Officer.

On April 20, 2026, the Board of Directors of Eli Lilly and Company (the
"Company") was notified by Anat Ashkenazi, the Company's Executive Vice
President and Chief Financial Officer, of her decision to leave the Company
effective May 30, 2026 to pursue another opportunity.

(c) Appointment of Principal Officer.

On April 20, 2026, the Company's Board of Directors appointed Lucas Montarce
as Executive Vice President and Chief Financial Officer of the Company,
effective June 1, 2026. Mr. Montarce, age 48, has served as Senior Vice
President, Finance since 2022.

Item 9.01 Financial Statements and Exhibits.
"""

ITEM_5_02_BOARD_ELECTION = """
Item 5.02 Departure of Directors or Certain Officers; Election of Directors;
Appointment of Certain Officers; Compensatory Arrangements of Certain Officers.

(d) Election of New Director.

Effective April 22, 2026, the Board of Directors of Moderna, Inc. elected
Dr. Sarah Smith to serve as a director of the Company. Dr. Smith was elected
to fill the vacancy created by the resignation of John Doe, who resigned on
April 1, 2026 for personal reasons.
"""

NO_ITEM_5_02 = """
Item 1.01 Entry into a Material Definitive Agreement.

On April 15, 2026, the Company entered into a license agreement with...
"""


# ────────────────────────────────────────────────────────────────────
# Cat 1 — Pydantic schema invariants
# ────────────────────────────────────────────────────────────────────

class TestExecChangeSchema:

    def test_module_exists(self):
        from services.extraction import exec_change  # noqa: F401

    def test_schema_required_fields(self):
        from services.extraction.exec_change import ExecChangeExtraction
        from pydantic import ValidationError

        # All required fields present → valid
        ec = ExecChangeExtraction(
            person_name="Jane Doe",
            change_type="departure",
            effective_date=date(2026, 6, 30),
        )
        assert ec.person_name == "Jane Doe"
        assert ec.change_type == "departure"
        assert ec.effective_date == date(2026, 6, 30)

        # Missing person_name → invalid
        with pytest.raises(ValidationError):
            ExecChangeExtraction(  # type: ignore[call-arg]
                change_type="departure",
                effective_date=date(2026, 6, 30),
            )

    def test_schema_change_type_enum(self):
        """change_type must be one of: departure, appointment, promotion,
        role_change, board_election, board_resignation."""
        from services.extraction.exec_change import (
            ExecChangeExtraction,
            ChangeType,
        )

        for ct in ["departure", "appointment", "promotion",
                   "role_change", "board_election", "board_resignation"]:
            ExecChangeExtraction(
                person_name="X",
                change_type=ct,  # type: ignore[arg-type]
                effective_date=date(2026, 1, 1),
            )

        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ExecChangeExtraction(
                person_name="X",
                change_type="invalid",  # type: ignore[arg-type]
                effective_date=date(2026, 1, 1),
            )

    def test_schema_optional_fields_default_none(self):
        from services.extraction.exec_change import ExecChangeExtraction
        ec = ExecChangeExtraction(
            person_name="X",
            change_type="departure",
            effective_date=date(2026, 1, 1),
        )
        assert ec.prior_role is None
        assert ec.new_role is None
        assert ec.successor_name is None
        assert ec.reason is None
        assert ec.functional_area is None

    def test_schema_serialises_to_dict(self):
        from services.extraction.exec_change import ExecChangeExtraction
        ec = ExecChangeExtraction(
            person_name="Mikael Dolsten",
            change_type="departure",
            prior_role="Chief Scientific Officer",
            effective_date=date(2026, 6, 30),
            functional_area="CSO",
        )
        d = ec.model_dump(mode="json")
        assert d["person_name"] == "Mikael Dolsten"
        assert d["effective_date"] == "2026-06-30"


# ────────────────────────────────────────────────────────────────────
# Cat 2 — Header detection
# ────────────────────────────────────────────────────────────────────

class TestHeaderDetection:

    def test_module_exists(self):
        from connectors.sec_8k import item_5_02  # noqa: F401

    def test_detects_item_5_02_block(self):
        from connectors.sec_8k.item_5_02 import detect_item_5_02_blocks
        blocks = detect_item_5_02_blocks(ITEM_5_02_DEPARTURE_ONLY)
        assert len(blocks) == 1
        assert "Mikael Dolsten" in blocks[0]
        assert "retire from the Company" in blocks[0]

    def test_block_does_not_include_next_item(self):
        from connectors.sec_8k.item_5_02 import detect_item_5_02_blocks
        blocks = detect_item_5_02_blocks(ITEM_5_02_DEPARTURE_ONLY)
        # The Item 5.02 block must NOT include the Item 9.01 header
        assert "Item 9.01" not in blocks[0]

    def test_returns_empty_list_when_no_item_5_02(self):
        from connectors.sec_8k.item_5_02 import detect_item_5_02_blocks
        assert detect_item_5_02_blocks(NO_ITEM_5_02) == []

    def test_detects_compound_filing_with_subitems(self):
        from connectors.sec_8k.item_5_02 import detect_item_5_02_blocks
        blocks = detect_item_5_02_blocks(ITEM_5_02_DEPARTURE_AND_APPOINTMENT)
        assert len(blocks) == 1
        assert "Anat Ashkenazi" in blocks[0]
        assert "Lucas Montarce" in blocks[0]
        # Subsection headers (b), (c) preserved
        assert "(b)" in blocks[0]
        assert "(c)" in blocks[0]

    def test_detects_board_election(self):
        from connectors.sec_8k.item_5_02 import detect_item_5_02_blocks
        blocks = detect_item_5_02_blocks(ITEM_5_02_BOARD_ELECTION)
        assert len(blocks) == 1
        assert "Dr. Sarah Smith" in blocks[0]


# ────────────────────────────────────────────────────────────────────
# Cat 3 — Parser orchestration with stub extractor
# ────────────────────────────────────────────────────────────────────

class StubExtractor:
    """Deterministic test double for the LLM extractor.

    Returns canned ExecChangeExtraction lists keyed by substring match
    on the input block, so a test author can declare 'when this block
    contains "Mikael Dolsten", return this extraction'.
    """

    def __init__(self, plan: dict[str, list]):
        self.plan = plan
        self.calls: list[str] = []

    def extract(self, block: str) -> list:
        self.calls.append(block)
        for key, value in self.plan.items():
            if key in block:
                return value
        return []


class TestParserOrchestration:

    def test_parser_calls_extractor_for_each_block(self):
        from connectors.sec_8k.item_5_02 import parse_item_5_02
        from services.extraction.exec_change import ExecChangeExtraction

        stub = StubExtractor({
            "Mikael Dolsten": [
                ExecChangeExtraction(
                    person_name="Mikael Dolsten",
                    change_type="departure",
                    prior_role="Chief Scientific Officer",
                    effective_date=date(2026, 6, 30),
                    functional_area="CSO",
                ),
            ],
        })

        results = parse_item_5_02(ITEM_5_02_DEPARTURE_ONLY, extractor=stub)

        assert len(results) == 1
        assert results[0].person_name == "Mikael Dolsten"
        assert results[0].change_type == "departure"
        assert len(stub.calls) == 1

    def test_parser_returns_empty_when_no_blocks(self):
        from connectors.sec_8k.item_5_02 import parse_item_5_02
        stub = StubExtractor({})
        assert parse_item_5_02(NO_ITEM_5_02, extractor=stub) == []
        assert stub.calls == []  # extractor not called when no blocks

    def test_parser_handles_compound_subitems(self):
        from connectors.sec_8k.item_5_02 import parse_item_5_02
        from services.extraction.exec_change import ExecChangeExtraction

        stub = StubExtractor({
            "Anat Ashkenazi": [
                ExecChangeExtraction(
                    person_name="Anat Ashkenazi",
                    change_type="departure",
                    prior_role="Executive Vice President and CFO",
                    effective_date=date(2026, 5, 30),
                    functional_area="CFO",
                    successor_name="Lucas Montarce",
                ),
                ExecChangeExtraction(
                    person_name="Lucas Montarce",
                    change_type="appointment",
                    new_role="Executive Vice President and CFO",
                    effective_date=date(2026, 6, 1),
                    functional_area="CFO",
                ),
            ],
        })

        results = parse_item_5_02(
            ITEM_5_02_DEPARTURE_AND_APPOINTMENT, extractor=stub,
        )
        assert len(results) == 2
        names = {r.person_name for r in results}
        assert names == {"Anat Ashkenazi", "Lucas Montarce"}

    def test_parser_skips_invalid_extractor_output(self):
        """If the extractor returns garbage (raises during validation),
        the parser logs and continues — never propagates the error."""
        from connectors.sec_8k.item_5_02 import parse_item_5_02

        class BrokenExtractor:
            def extract(self, block):  # noqa: D401
                raise ValueError("LLM returned non-JSON")

        # Should not raise, should return []
        out = parse_item_5_02(ITEM_5_02_DEPARTURE_ONLY,
                              extractor=BrokenExtractor())
        assert out == []


# ────────────────────────────────────────────────────────────────────
# Cat 4 — transition_id pairing
# ────────────────────────────────────────────────────────────────────

class TestTransitionPairing:

    def test_pair_departure_with_named_successor(self):
        """A departure that names a successor + an appointment for that
        same name → both share a transition_id."""
        from connectors.sec_8k.item_5_02 import assign_transition_ids
        from services.extraction.exec_change import ExecChangeExtraction

        items = [
            ExecChangeExtraction(
                person_name="Anat Ashkenazi",
                change_type="departure",
                prior_role="Executive Vice President and CFO",
                effective_date=date(2026, 5, 30),
                functional_area="CFO",
                successor_name="Lucas Montarce",
            ),
            ExecChangeExtraction(
                person_name="Lucas Montarce",
                change_type="appointment",
                new_role="Executive Vice President and CFO",
                effective_date=date(2026, 6, 1),
                functional_area="CFO",
            ),
        ]
        paired = assign_transition_ids(items, company_id="lly")

        # Both items got the same transition_id (non-None)
        assert paired[0].transition_id is not None
        assert paired[0].transition_id == paired[1].transition_id

    def test_pair_by_functional_area_when_successor_unnamed(self):
        """Departure with no successor + appointment to same functional
        area at same company within 90d → pair them."""
        from connectors.sec_8k.item_5_02 import assign_transition_ids
        from services.extraction.exec_change import ExecChangeExtraction

        items = [
            ExecChangeExtraction(
                person_name="Old CFO",
                change_type="departure",
                prior_role="CFO",
                effective_date=date(2026, 4, 1),
                functional_area="CFO",
            ),
            ExecChangeExtraction(
                person_name="New CFO",
                change_type="appointment",
                new_role="CFO",
                effective_date=date(2026, 5, 1),
                functional_area="CFO",
            ),
        ]
        paired = assign_transition_ids(items, company_id="abc")
        assert paired[0].transition_id == paired[1].transition_id

    def test_no_pairing_when_outside_window(self):
        """Same company, same functional area, but >120d apart → no pair."""
        from connectors.sec_8k.item_5_02 import assign_transition_ids
        from services.extraction.exec_change import ExecChangeExtraction

        items = [
            ExecChangeExtraction(
                person_name="A",
                change_type="departure",
                prior_role="CFO",
                effective_date=date(2026, 1, 1),
                functional_area="CFO",
            ),
            ExecChangeExtraction(
                person_name="B",
                change_type="appointment",
                new_role="CFO",
                effective_date=date(2026, 6, 1),  # 5 months later
                functional_area="CFO",
            ),
        ]
        paired = assign_transition_ids(items, company_id="abc")
        # Each gets its own (or None) transition — different IDs
        assert paired[0].transition_id != paired[1].transition_id

    def test_lone_change_gets_solo_transition_id(self):
        from connectors.sec_8k.item_5_02 import assign_transition_ids
        from services.extraction.exec_change import ExecChangeExtraction

        items = [
            ExecChangeExtraction(
                person_name="X",
                change_type="board_resignation",
                effective_date=date(2026, 4, 1),
            ),
        ]
        paired = assign_transition_ids(items, company_id="abc")
        # Solo events still get an ID (so the entry can be linked to
        # market_events row even without a sibling)
        assert paired[0].transition_id is not None


# ────────────────────────────────────────────────────────────────────
# Cat 5 — Event-row builder
# ────────────────────────────────────────────────────────────────────

class TestEventRowBuilder:

    def test_module_exists(self):
        from services.event_emitters import exec_change  # noqa: F401

    def test_build_event_row_required_fields(self):
        from services.event_emitters.exec_change import build_event_row
        from services.extraction.exec_change import ExecChangeExtraction

        ec = ExecChangeExtraction(
            person_name="Mikael Dolsten",
            change_type="departure",
            prior_role="Chief Scientific Officer",
            effective_date=date(2026, 6, 30),
            functional_area="CSO",
            transition_id="00000000-0000-0000-0000-000000000001",
        )

        row = build_event_row(
            extraction=ec,
            company_id="00000000-0000-0000-0000-00000000aaaa",
            company_name="Pfizer Inc.",
            source_document_id="00000000-0000-0000-0000-00000000bbbb",
            disclosed_date=date(2026, 4, 15),
        )

        assert row["event_type"] == "exec_change"
        assert row["primary_entity_type"] == "company"
        assert row["primary_entity_id"] == "00000000-0000-0000-0000-00000000aaaa"
        assert row["primary_entity_name"] == "Pfizer Inc."
        assert row["event_date"] == date(2026, 6, 30)
        assert row["disclosed_date"] == date(2026, 4, 15)
        assert row["source_tier"] == "tier_1"      # SEC = tier 1
        assert row["status"] == "new"
        # event_hash deterministic from inputs
        assert isinstance(row["event_hash"], str) and len(row["event_hash"]) == 64
        # description includes the change type + role + name for human readability
        assert "Dolsten" in row["description"]
        assert "departure" in row["description"].lower()

    def test_event_hash_deterministic(self):
        """Same inputs → same hash. Re-running the connector doesn't
        create duplicate market_events rows."""
        from services.event_emitters.exec_change import build_event_row
        from services.extraction.exec_change import ExecChangeExtraction

        ec = ExecChangeExtraction(
            person_name="X",
            change_type="appointment",
            new_role="CFO",
            effective_date=date(2026, 6, 1),
            functional_area="CFO",
        )
        kwargs = dict(
            extraction=ec,
            company_id="00000000-0000-0000-0000-000000000001",
            company_name="Co",
            source_document_id="00000000-0000-0000-0000-000000000002",
            disclosed_date=date(2026, 4, 15),
        )
        row1 = build_event_row(**kwargs)
        row2 = build_event_row(**kwargs)
        assert row1["event_hash"] == row2["event_hash"]

    def test_event_hash_changes_with_person(self):
        """Different person, same role/company/date → different hash."""
        from services.event_emitters.exec_change import build_event_row
        from services.extraction.exec_change import ExecChangeExtraction

        a = ExecChangeExtraction(
            person_name="A",
            change_type="appointment",
            new_role="CFO",
            effective_date=date(2026, 6, 1),
        )
        b = ExecChangeExtraction(
            person_name="B",
            change_type="appointment",
            new_role="CFO",
            effective_date=date(2026, 6, 1),
        )
        row_a = build_event_row(
            extraction=a,
            company_id="00000000-0000-0000-0000-000000000001",
            company_name="Co",
            source_document_id="00000000-0000-0000-0000-000000000002",
            disclosed_date=date(2026, 4, 15),
        )
        row_b = build_event_row(
            extraction=b,
            company_id="00000000-0000-0000-0000-000000000001",
            company_name="Co",
            source_document_id="00000000-0000-0000-0000-000000000002",
            disclosed_date=date(2026, 4, 15),
        )
        assert row_a["event_hash"] != row_b["event_hash"]

    def test_impact_tier_csuite_change_is_high(self):
        """C-suite changes are high-impact per CI HR2.3."""
        from services.event_emitters.exec_change import build_event_row
        from services.extraction.exec_change import ExecChangeExtraction

        ec = ExecChangeExtraction(
            person_name="X",
            change_type="departure",
            prior_role="Chief Executive Officer",
            effective_date=date(2026, 6, 30),
            functional_area="CEO",
        )
        row = build_event_row(
            extraction=ec,
            company_id="00000000-0000-0000-0000-000000000001",
            company_name="Co",
            source_document_id="00000000-0000-0000-0000-000000000002",
            disclosed_date=date(2026, 4, 15),
        )
        assert row.get("impact_hint") == "high"

    def test_impact_tier_director_change_is_low(self):
        from services.event_emitters.exec_change import build_event_row
        from services.extraction.exec_change import ExecChangeExtraction

        ec = ExecChangeExtraction(
            person_name="X",
            change_type="departure",
            prior_role="Director, Investor Relations",
            effective_date=date(2026, 6, 30),
        )
        row = build_event_row(
            extraction=ec,
            company_id="00000000-0000-0000-0000-000000000001",
            company_name="Co",
            source_document_id="00000000-0000-0000-0000-000000000002",
            disclosed_date=date(2026, 4, 15),
        )
        assert row.get("impact_hint") == "low"
