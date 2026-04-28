"""Pydantic schema for 8-K Item 5.02 extraction → exec_change events.

SPEC-016 §7 swimlane A2.1. The schema is what the LLM extractor returns
when given an Item 5.02 narrative block. Every field is locked, so a
malformed LLM response fails Pydantic validation rather than polluting
the database.

Used by:
  - connectors/sec_8k/item_5_02.py (parser orchestrator)
  - services/event_emitters/exec_change.py (event-row builder)
  - tests/test_a2_1_item_5_02_parser.py (stub extractor returns these)

Aligns with the OpenAPI intel.yaml event_type='exec_change' shape and the
roles_history entry shape on investigators (A1.4).
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, ConfigDict


ChangeType = Literal[
    "departure",         # exec leaves the company
    "appointment",       # exec joins / takes a new role at this company
    "promotion",         # exec moves UP within this company
    "role_change",       # exec moves laterally within this company
    "board_election",    # new director elected to the board
    "board_resignation", # director resigns from the board
]

FunctionalArea = Literal[
    "CEO", "CFO", "CSO", "CMO", "CCO",
    "head_of_RD", "board", "other",
]


class ExecChangeExtraction(BaseModel):
    """A single executive change extracted from an Item 5.02 narrative.

    One Item 5.02 filing can produce N of these (e.g. simultaneous
    departure + appointment of a successor → 2 extractions).
    """

    model_config = ConfigDict(extra="forbid")  # reject unknown fields

    person_name: str = Field(
        ...,
        min_length=1,
        description="Full name as it appears in the filing, with honorifics "
                    "and degree suffixes removed (resolver normalises further).",
    )
    change_type: ChangeType = Field(
        ...,
        description="What kind of change is this — departure, appointment, "
                    "promotion, role_change, board_election, board_resignation.",
    )
    effective_date: date = Field(
        ...,
        description="The date the change takes effect (NOT the filing date — "
                    "those can differ by weeks).",
    )

    # Roles
    prior_role: Optional[str] = Field(
        None,
        description="Role being departed from (departure / promotion / "
                    "role_change / board_resignation). None on appointments "
                    "and board_elections.",
    )
    new_role: Optional[str] = Field(
        None,
        description="Role being assumed (appointment / promotion / role_change "
                    "/ board_election). None on departures and board resignations.",
    )

    # Classification (optional but encouraged)
    functional_area: Optional[FunctionalArea] = Field(
        None,
        description="One of CEO|CFO|CSO|CMO|CCO|head_of_RD|board|other. "
                    "Heuristic-classified by the parser if not in the LLM output.",
    )

    # Successor — for departures, the named successor when disclosed;
    # otherwise None and the pattern detector tries to infer via window match.
    successor_name: Optional[str] = Field(
        None,
        description="Named successor (only set on departures when the filing "
                    "explicitly names them in the same disclosure).",
    )

    # Reason — exec departures sometimes disclose 'retirement', 'pursue another
    # opportunity', 'personal reasons', etc. Free text — used as evidence in
    # the Signal narrative, not for routing.
    reason: Optional[str] = Field(
        None,
        max_length=500,
        description="Free-text reason if disclosed — keeps the analyst's "
                    "context. Empty when undisclosed.",
    )

    # Pairing — assigned by assign_transition_ids() AFTER LLM extraction.
    # The LLM never sets this; it's a post-processing field.
    transition_id: Optional[str] = Field(
        None,
        description="UUID linking paired exit + arrival (or solo events) for "
                    "the same role transition. Assigned by the parser, not the "
                    "LLM. Persisted on roles_history entries + market_events.",
    )
