"""LLM extractor wrapper — Epic 1 α1.

Generic Anthropic/OpenAI tool-use wrapper that binds the 4 Pydantic
extraction schemas to the parser Protocols defined in connectors/sec_8k/.

Architecture
  - StructuredCall = Callable[(system_prompt, user_prompt, json_schema), dict | None]
    Provider-agnostic abstraction. Real providers go through adapters
    (make_anthropic_structured_call, make_openai_structured_call).
    Tests pass a fake callable.

  - extract_structured(...)        single-instance helper
  - make_*_extractor(structured_call)  factory per parser Protocol:
      make_exec_change_extractor   → A2.1
      make_deal_extractor          → A2.2
      make_financial_extractor     → A2.3 (returns tuple)
      make_crl_extractor           → A2.4

Design notes
  - List-extracting factories use a wrapper schema { extractions: [Schema] }
    so the LLM returns one tool call containing all instances at once.
  - Validation failures on individual list items are dropped, the rest
    pass through (defence-in-depth).
  - The financial factory uses a different wrapper schema with two top-level
    fields because Item 2.02 produces a heterogeneous output.
  - All factory outputs are exception-safe — if the underlying call fails
    or returns invalid data, you get an empty list (or None tuple), never
    a thrown exception.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from services.extraction.exec_change import ExecChangeExtraction
from services.extraction.deal_announced import DealExtraction
from services.extraction.financial_disclosure import (
    FinancialDisclosureExtraction,
    GuidanceIssuance,
)
from services.extraction.regulatory_crl import CRLExtraction
from services.extraction.trial_readout import TrialReadoutExtraction
from services.llm_gateway import guard_anthropic_messages, guard_openai_chat  # PRIV-001b egress adapter

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
# Provider-agnostic call signature
# ────────────────────────────────────────────────────────────────────


# A StructuredCall takes (system_prompt, user_prompt, json_schema) and
# returns the LLM's structured output as a dict, or None if the LLM
# refused / returned no structured content.
#
# Errors during the call (network, rate-limit) are raised; callers wrap
# them in retry / fallback logic.
StructuredCall = Callable[[str, str, dict[str, Any]], Optional[dict[str, Any]]]


# ────────────────────────────────────────────────────────────────────
# Generic single-instance extraction
# ────────────────────────────────────────────────────────────────────


T = TypeVar("T", bound=BaseModel)


def extract_structured(
    block: str,
    *,
    system_prompt: str,
    schema_class: type[T],
    structured_call: StructuredCall,
) -> Optional[T]:
    """Extract a single Pydantic model instance from `block`.

    Returns None on:
      - structured_call raises (network, rate-limit)
      - structured_call returns None / empty
      - Pydantic validation fails

    Logs warnings on failures but never propagates exceptions.
    """
    json_schema = schema_class.model_json_schema()
    try:
        raw = structured_call(system_prompt, block, json_schema)
    except Exception as exc:
        logger.warning(
            "structured_call raised for %s: %s", schema_class.__name__, exc,
        )
        return None
    if not raw:
        return None
    try:
        return schema_class.model_validate(raw)
    except Exception as exc:
        logger.warning(
            "validation failed for %s: %s; raw=%r",
            schema_class.__name__, exc, raw,
        )
        return None


def _validate_list_items(
    raw_list: list[Any],
    schema_class: type[T],
) -> list[T]:
    """Validate each item in a list; drop the invalid ones."""
    out: list[T] = []
    for i, item in enumerate(raw_list or []):
        if isinstance(item, schema_class):
            out.append(item)
            continue
        try:
            out.append(schema_class.model_validate(item))
        except Exception as exc:
            logger.warning(
                "list item %d failed validation for %s: %s",
                i, schema_class.__name__, exc,
            )
    return out


def _extract_list(
    block: str,
    *,
    system_prompt: str,
    schema_class: type[T],
    structured_call: StructuredCall,
    list_field: str = "extractions",
) -> list[T]:
    """Extract a list of T. Items that fail validation are dropped
    individually (defence-in-depth — one bad LLM item doesn't poison
    the whole batch).

    Builds a permissive JSON schema asking for a list-of-target-schema;
    validates per-item afterward at the Python level.
    """
    json_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            list_field: {
                "type": "array",
                "items": schema_class.model_json_schema(),
            },
        },
        "required": [list_field],
    }
    try:
        raw = structured_call(system_prompt, block, json_schema)
    except Exception as exc:
        logger.warning(
            "structured_call raised for %s list: %s",
            schema_class.__name__, exc,
        )
        return []
    if not raw:
        return []
    items = raw.get(list_field, [])
    if not isinstance(items, list):
        logger.warning("%s field is not a list: %r", list_field, items)
        return []
    return _validate_list_items(items, schema_class)


# ────────────────────────────────────────────────────────────────────
# System prompts
# ────────────────────────────────────────────────────────────────────


_EXEC_CHANGE_PROMPT = """You extract executive-change events from SEC 8-K Item 5.02 narrative blocks.

For each distinct executive change in the block, emit one item in the `extractions` array.

Rules:
- Only emit changes that are explicitly stated in the block.
- person_name: full name with honorifics + degree suffixes removed.
- change_type:
    "departure" - exec leaving the company
    "appointment" - exec joining or taking a new role at this company
    "promotion" - exec moving up within this company
    "role_change" - exec moving laterally within this company
    "board_election" - new director on the board
    "board_resignation" - director resigning from the board
- effective_date: the date the change takes effect (NOT the filing date).
  Use ISO format YYYY-MM-DD. If only a year/month given, use first day.
- successor_name: ONLY when the filing explicitly names a successor in the
  same disclosure for a departure event.
- functional_area: classify into CEO|CFO|CSO|CMO|CCO|head_of_RD|board|other.
- reason: short free text reason if disclosed (retirement, "to pursue
  another opportunity", personal reasons, etc.). Empty when undisclosed.

If no executive changes are present, return {"extractions": []}.

Never invent fields. Never include a person not named in the block."""


_DEAL_PROMPT = """You extract deal events from SEC 8-K Item 1.01 narrative blocks.

For each deal disclosed in the block, emit one item in the `extractions` array.

Rules:
- deal_types is a LIST. A deal can be multiple types simultaneously
  (e.g. ["license_in", "co_development", "option"]). Members:
    "acquisition" "asset_purchase" "license_in" "license_out"
    "collaboration" "option" "co_promotion" "co_development"
    "royalty_monetisation"
- announced_date: the date the deal is announced (filing exhibit date).
- Direction-aware parties:
    M&A: acquirer_name + target_name
    Licenses: licensor_name + licensee_name
- subject_drug_names[]: any drug compound codes / generic names mentioned.
- subject_indication: indication descriptor as free text.
- geography: ISO country code, "WW", "EU5", "ROW" if disclosed.
- Financial terms: extract values verbatim. Use full dollars (50_000_000
  for $50M, not 50). Keep undisclosed values as null.
- upfront_disclosed: false ONLY when the press release explicitly says
  "terms not disclosed" or similar.
- Sanity: upfront + max_milestones must NOT exceed total_potential.

If no deals are present, return {"extractions": []}."""


_FINANCIAL_PROMPT = """You extract financial-disclosure events and guidance issuances from SEC 8-K Item 2.02 narrative blocks.

The filing typically contains BOTH:
1. Reported financials for the just-ended period -> financial_disclosure
2. Guidance for upcoming period(s) -> guidance_issuances[]

Rules for financial_disclosure:
- fiscal_period_end: last day of the period being reported.
- fiscal_period_label: human label like "Q1 2026" or "FY2025".
- metrics[]: each one has name + basis (GAAP|non-GAAP) + EITHER value
  (per-share/ratio/count) OR value_usd (currency, full dollars).
  Common metric names: revenue, eps, rd, sga, operating_income,
  net_income, gross_margin, free_cash_flow.

Rules for guidance_issuances[]:
- direction: raise|lower|reaffirm|narrow|initiate|withdraw
- range_low / range_high in raw values (full dollars or per-share)
- prior_range_low / prior_range_high when the filing states what was
  previously guided. range_low <= range_high; same for prior.
- basis: GAAP or non-GAAP

If no financial disclosure: financial_disclosure = null.
If no guidance issuances: guidance_issuances = []."""


_CRL_PROMPT = """You extract Complete Response Letter (CRL) events from SEC 8-K Item 8.01 narrative blocks.

Most Item 8.01 blocks are NOT CRLs. Only emit an extraction when the block clearly states the company received a Complete Response Letter / CRL from a regulator.

For each CRL disclosed, emit one item in `extractions`.

Rules:
- agency: FDA|EMA|MHRA|PMDA|Health_Canada|TGA
- received_date: when the CRL was received (filing date if not stated).
- application_type: NDA|BLA|ANDA|sNDA|sBLA|510k|PMA|MAA|JMA
- application_number: e.g. "218237"
- drug_name: drug code or generic name as written
- indication: free text
- reason_categories[]: pick from these enums based on what the FDA cited:
    additional_efficacy_data | additional_safety_data | manufacturing_cmc
    | facility_inspection | labelling | post_marketing_commitment
    | trial_design | comparator_arm | biostatistics | other
- plan_for_response: short summary of how the company plans to respond.

If the block is not a CRL: return {"extractions": []}."""


_TRIAL_READOUT_PROMPT = """You extract trial-readout events from company press releases or news articles.

Most press releases are NOT trial readouts. Only emit an extraction when the text clearly describes results from a clinical trial — endpoints met / not met, efficacy numerics, primary completion, or readout of a Phase 1/2/3/4 study.

For each readout disclosed, emit one item in `extractions`.

Rules:
- trial_identifier: NCT id, acronym, or sponsor protocol id as stated in the press release. Use the acronym ("CHECKMATE-816") when stated; fall back to the NCT id only when no acronym is given.
- phase: pick from Early Phase 1, Phase 1, Phase 1, Phase 2, Phase 2, Phase 2, Phase 3, Phase 3, Phase 4, N/A.
- drug_name: as stated. Code names ("DS-8201") and generics ("trastuzumab deruxtecan") both fine.
- sponsor_name: lead sponsor as stated.
- indication: short condition phrase ("HER2-positive metastatic breast cancer").
- primary_endpoint_met: true ONLY when the press release explicitly states the trial met its PRIMARY endpoint. A secondary-only positive readout with a missed primary is false.
- readout_date: when the readout was announced (release date).
- sample_size: total trial sample size, if stated.
- efficacy_outcomes[]: one entry per stated endpoint with structured numerics. Each:
    * endpoint_name: stated phrase ("progression-free survival", "ORR")
    * endpoint_type: primary | secondary | exploratory
    * met: did this specific endpoint hit its bar?
    * hazard_ratio: 0.0-10.0 if a survival/TTE endpoint and stated
    * p_value: 0.0-1.0 if stated
    * ci_low / ci_high: confidence interval bounds if stated
    * response_rate_pct: 0-100 if a response-rate endpoint and stated
    * sample_size: patients evaluated for THIS endpoint, if stated
- safety_summary: short free-text TEAE / SAE summary if stated.
- headline_summary: one-paragraph narrative summary suitable for the event description.

Do NOT invent numerics. If a value is not stated, leave it null. If the text is not a trial readout, return {"extractions": []}."""


# ────────────────────────────────────────────────────────────────────
# Wrapper schemas (LLM returns one of these per call)
# ────────────────────────────────────────────────────────────────────


class _ExecChangeContainer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    extractions: list[ExecChangeExtraction] = Field(default_factory=list)


class _DealContainer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    extractions: list[DealExtraction] = Field(default_factory=list)


class _CRLContainer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    extractions: list[CRLExtraction] = Field(default_factory=list)


class _TrialReadoutContainer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    extractions: list[TrialReadoutExtraction] = Field(default_factory=list)


class _FinancialContainer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    financial_disclosure: Optional[FinancialDisclosureExtraction] = None
    guidance_issuances: list[GuidanceIssuance] = Field(default_factory=list)


# ────────────────────────────────────────────────────────────────────
# Per-Protocol factories
# ────────────────────────────────────────────────────────────────────


class _ExecChangeExtractorImpl:
    def __init__(self, structured_call: StructuredCall):
        self._call = structured_call

    def extract(self, block: str) -> list[ExecChangeExtraction]:
        return _extract_list(
            block,
            system_prompt=_EXEC_CHANGE_PROMPT,
            schema_class=ExecChangeExtraction,
            structured_call=self._call,
        )


def make_exec_change_extractor(
    *, structured_call: StructuredCall,
) -> _ExecChangeExtractorImpl:
    """Factory: returns an extractor satisfying the ExecChangeExtractor
    Protocol used by connectors/sec_8k/item_5_02.parse_item_5_02."""
    return _ExecChangeExtractorImpl(structured_call)


class _DealExtractorImpl:
    def __init__(self, structured_call: StructuredCall):
        self._call = structured_call

    def extract(self, block: str) -> list[DealExtraction]:
        return _extract_list(
            block,
            system_prompt=_DEAL_PROMPT,
            schema_class=DealExtraction,
            structured_call=self._call,
        )


def make_deal_extractor(
    *, structured_call: StructuredCall,
) -> _DealExtractorImpl:
    """Factory: returns an extractor satisfying the DealExtractor
    Protocol used by connectors/sec_8k/item_1_01.parse_item_1_01."""
    return _DealExtractorImpl(structured_call)


class _CRLExtractorImpl:
    def __init__(self, structured_call: StructuredCall):
        self._call = structured_call

    def extract(self, block: str) -> list[CRLExtraction]:
        return _extract_list(
            block,
            system_prompt=_CRL_PROMPT,
            schema_class=CRLExtraction,
            structured_call=self._call,
        )


def make_crl_extractor(
    *, structured_call: StructuredCall,
) -> _CRLExtractorImpl:
    """Factory: returns an extractor satisfying the CRLExtractor
    Protocol used by connectors/sec_8k/item_8_01.parse_item_8_01."""
    return _CRLExtractorImpl(structured_call)


class _TrialReadoutExtractorImpl:
    def __init__(self, structured_call: StructuredCall):
        self._call = structured_call

    def extract(self, block: str) -> list[TrialReadoutExtraction]:
        return _extract_list(
            block,
            system_prompt=_TRIAL_READOUT_PROMPT,
            schema_class=TrialReadoutExtraction,
            structured_call=self._call,
        )


def make_trial_readout_extractor(
    *, structured_call: StructuredCall,
) -> _TrialReadoutExtractorImpl:
    """Factory: returns an extractor for press-release trial readouts.

    Used by the A3.3 press-release runner (Cycle 4) to extract structured
    trial_readout events from company press releases / news articles.
    """
    return _TrialReadoutExtractorImpl(structured_call)


class _FinancialExtractorImpl:
    def __init__(self, structured_call: StructuredCall):
        self._call = structured_call

    def extract(
        self, block: str,
    ) -> tuple[Optional[FinancialDisclosureExtraction], list[GuidanceIssuance]]:
        result = extract_structured(
            block,
            system_prompt=_FINANCIAL_PROMPT,
            schema_class=_FinancialContainer,
            structured_call=self._call,
        )
        if not result:
            return None, []
        return (
            result.financial_disclosure,
            list(result.guidance_issuances),
        )


def make_financial_extractor(
    *, structured_call: StructuredCall,
) -> _FinancialExtractorImpl:
    """Factory: returns an extractor satisfying the FinancialExtractor
    Protocol used by connectors/sec_8k/item_2_02.parse_item_2_02.
    Note this one returns a TUPLE (disclosure, guidance_list)."""
    return _FinancialExtractorImpl(structured_call)


# ────────────────────────────────────────────────────────────────────
# Anthropic adapter — produces a StructuredCall using tool-use
# ────────────────────────────────────────────────────────────────────


_ANTHROPIC_TOOL_NAME = "extract_data"


def make_anthropic_structured_call(
    *,
    client: Any,                 # anthropic.Anthropic instance
    model: str,
    max_tokens: int = 4096,
    max_retries: int = 3,
    retry_base_seconds: float = 1.0,
) -> StructuredCall:
    """Build a StructuredCall backed by an Anthropic client using tool-use.

    The returned callable forces the model to invoke a single tool whose
    input_schema matches the JSON schema we pass in. The tool's input is
    returned as the structured response.

    Retries on transient errors (rate limit, 5xx) with exponential backoff.
    """
    def call(
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        tool = {
            "name": _ANTHROPIC_TOOL_NAME,
            "description": (
                "Return structured data extracted from the user-provided "
                "narrative block. ALWAYS call this tool. ALWAYS conform to "
                "the input_schema."
            ),
            "input_schema": json_schema,
        }
        last_exc: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                response = guard_anthropic_messages(
                    client,
                    model=model,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    tools=[tool],
                    tool_choice={"type": "tool", "name": _ANTHROPIC_TOOL_NAME},
                )
                # Find the tool_use content block
                for block in response.content or []:
                    if getattr(block, "type", None) == "tool_use":
                        return getattr(block, "input", None)
                # No tool_use block — model refused or returned only text
                return None
            except Exception as exc:
                last_exc = exc
                if _is_transient_anthropic_error(exc) and attempt < max_retries - 1:
                    backoff = retry_base_seconds * (2 ** attempt)
                    logger.warning(
                        "anthropic call attempt %d failed (%s); "
                        "backing off %.1fs",
                        attempt + 1, exc, backoff,
                    )
                    time.sleep(backoff)
                    continue
                raise
        # Loop exhausted (defensive — usually we re-raise above)
        if last_exc is not None:
            raise last_exc
        return None

    return call


def _is_transient_anthropic_error(exc: Exception) -> bool:
    """Heuristic — duck-typing avoids hard import dependency."""
    name = exc.__class__.__name__.lower()
    if "ratelimit" in name or "timeout" in name:
        return True
    # Some Anthropic errors expose a status_code attribute
    status = getattr(exc, "status_code", None)
    if status in (429, 500, 502, 503, 504):
        return True
    return False


# ────────────────────────────────────────────────────────────────────
# OpenAI adapter — for environments that already have OpenAI credentials
# ────────────────────────────────────────────────────────────────────


def make_openai_structured_call(
    *,
    client: Any,                 # openai.OpenAI instance
    model: str,
    max_retries: int = 3,
    retry_base_seconds: float = 1.0,
) -> StructuredCall:
    """Build a StructuredCall backed by an OpenAI client using tool calling.

    OpenAI's function-calling has a similar shape to Anthropic tool-use.
    """
    import json

    def call(
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        tool = {
            "type": "function",
            "function": {
                "name": "extract_data",
                "description": (
                    "Return structured data extracted from the user prompt."
                ),
                "parameters": json_schema,
            },
        }
        last_exc: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                response = guard_openai_chat(
                    client,
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    tools=[tool],
                    tool_choice={
                        "type": "function",
                        "function": {"name": "extract_data"},
                    },
                )
                msg = response.choices[0].message
                tcs = getattr(msg, "tool_calls", None) or []
                if not tcs:
                    return None
                args_str = tcs[0].function.arguments
                if not args_str:
                    return None
                return json.loads(args_str)
            except Exception as exc:
                last_exc = exc
                if attempt < max_retries - 1:
                    backoff = retry_base_seconds * (2 ** attempt)
                    logger.warning(
                        "openai call attempt %d failed (%s); backing off %.1fs",
                        attempt + 1, exc, backoff,
                    )
                    time.sleep(backoff)
                    continue
                raise
        if last_exc is not None:
            raise last_exc
        return None

    return call
