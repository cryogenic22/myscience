"""Fact governance & trust model — the Agent Readiness Layer keystone.

Every fact in the ledger should carry the trust metadata an autonomous agent
needs to reason *safely*: not a single opaque ``confidence`` REAL, but a small
set of computed, explainable dimensions that compose into one ``trust_score`` an
agent can rank and gate on, plus a ``review_status`` lifecycle.

This module is PURE — no DB, no I/O, fully unit-testable. The DB-touching parts
(reading resolution_audit, UPDATEing facts) live in
``scripts/backfill_fact_governance.py`` and in the ``assert_fact`` wrapper.

The six governed dimensions (FAIR "Reusable" + agent trust):

  source_reliability    [0,1]  tier of the originating source, keyed off
                               fact_class (and overridable per created_by/source).
  extraction_confidence [0,1]  1.0 for structured/connector facts; the model's
                               own confidence for LLM/document-extracted facts.
  resolver_confidence   [0,1]  confidence the subject entity was resolved
                               correctly (from resolution_audit when available).
  freshness_at          ts     the as-of timestamp staleness is measured from
                               (valid_from, else created_at).
  review_status         enum   unreviewed | auto_approved | human_approved | flagged
  schema_version        int    version of THIS trust model (so a future re-score
                               can find rows written by an older model).

and the composite they feed:

  trust_score           [0,1]  a documented weighted blend (see TRUST_FORMULA).

THE FORMULA (trust_score)
-------------------------
trust_score is a weighted geometric-ish blend that is *conjunctive* — a fact is
only as trustworthy as its weakest credible link, so a low resolver_confidence
or a very stale fact MUST pull the score down even if the source is gold. We use
a weighted product of the four [0,1] quality factors, with freshness as a
multiplicative decay:

    quality   = source_reliability ** W_SOURCE
              * resolver_confidence ** W_RESOLVER
              * extraction_confidence ** W_EXTRACTION
    trust_score = quality * freshness_decay(age_days)

The exponents are weights (they sum to 1.0) — a higher weight means that factor
dominates the blend. Source and resolver are weighted most heavily (a wrongly-
resolved subject makes the fact actively dangerous to an agent). Freshness is a
separate multiplicative term because a perfectly-sourced fact about a price from
2018 is still misleading *today* — staleness caps trust regardless of source.

This is conjunctive on purpose: it is NOT an average (an average lets a gold
source paper over a coin-flip resolver). The weakest dimension drags the result.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

# Bump when the formula or its weights change so re-scores can target old rows.
GOVERNANCE_SCHEMA_VERSION = 1

# Source reliability by fact_class — the dominant tier signal. Reference =
# regulatory / peer-reviewed (FDA label, ClinicalTrials.gov, PubMed); corporate
# = company filing / disclosure (10-K, 8-K, press); signal = observed news /
# market event; inferred = derived / agent-reasoned (no primary source).
SOURCE_RELIABILITY: dict[str, float] = {
    "reference": 0.95,
    "corporate": 0.85,
    "signal": 0.60,
    "inferred": 0.40,
}
_DEFAULT_RELIABILITY = SOURCE_RELIABILITY["signal"]

# created_by / emitter markers that indicate an LLM/document extraction (its
# extraction_confidence is the model's own confidence, not a blanket 1.0).
# Everything else (structured connectors, fact_emitter lifts of typed rows) is
# treated as deterministic extraction → 1.0.
_LLM_EXTRACTION_MARKERS = (
    "document_facts",  # DR-9 deck/PDF extraction
    "llm",
    "agent",           # agent-reasoned / inferred
    "gpt",
    "extractor",
)

# Default resolver_confidence when no resolution_audit row exists. The facts
# ledger is keyed by an already-resolved (type, id); absence of an audit row
# usually means the subject came in pre-resolved (structured connector) rather
# than a fuzzy match, so a moderately-high default is fair — but not 1.0.
DEFAULT_RESOLVER_CONFIDENCE = 0.75

# Trust-score weights (exponents; sum to 1.0). See module docstring.
W_SOURCE = 0.45
W_RESOLVER = 0.35
W_EXTRACTION = 0.20

# Freshness: half-life decay. A fact loses half its freshness weight every
# FRESHNESS_HALF_LIFE_DAYS. ~2 years half-life — a 2-year-old fact is ~0.5
# fresh, a decade-old fact ~0.03. Reference facts (approvals) are still useful
# when old, but trust *as a current claim* legitimately decays.
FRESHNESS_HALF_LIFE_DAYS = 730.0

# review_status auto-rule thresholds.
AUTO_APPROVE_TRUST = 0.80   # high-trust structured → auto_approved
FLAG_TRUST = 0.25           # very-low trust → flagged for human review


@dataclass
class FactGovernance:
    """The computed governance bundle for a single fact."""

    source_reliability: float
    extraction_confidence: float
    resolver_confidence: float
    freshness_at: Optional[datetime]
    review_status: str
    schema_version: int
    trust_score: float


def _coerce_dt(v: Any) -> Optional[datetime]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _clamp01(x: float) -> float:
    return min(1.0, max(0.0, float(x)))


def freshness_decay(age_days: float) -> float:
    """Monotonic, bounded [0,1] freshness weight from age in days.

    Exponential half-life decay: weight = 0.5 ** (age / half_life). age=0 → 1.0;
    age == half_life → 0.5; strictly decreasing, asymptotes to 0. Negative ages
    (future-dated anticipatory facts) clamp to fully-fresh (1.0)."""
    if age_days <= 0:
        return 1.0
    return _clamp01(math.pow(0.5, age_days / FRESHNESS_HALF_LIFE_DAYS))


def _is_llm_extraction(created_by: str, object_value: Any) -> bool:
    cb = (created_by or "").lower()
    if any(m in cb for m in _LLM_EXTRACTION_MARKERS):
        return True
    if isinstance(object_value, dict):
        emitter = str(object_value.get("emitter", "")).lower()
        if any(m in emitter for m in _LLM_EXTRACTION_MARKERS):
            return True
    return False


def _source_reliability(fact_class: str, source_reliability_map: dict[str, float]) -> float:
    return source_reliability_map.get(fact_class, _DEFAULT_RELIABILITY)


def _extraction_confidence(fact: dict) -> float:
    """1.0 for structured/connector facts; the fact's own confidence for
    LLM/document-extracted facts (capped to [0,1])."""
    created_by = fact.get("created_by") or ""
    if _is_llm_extraction(created_by, fact.get("object_value")):
        conf = fact.get("confidence")
        try:
            return _clamp01(conf) if conf is not None else 0.7
        except (TypeError, ValueError):
            return 0.7
    return 1.0


def _freshness_at(fact: dict) -> Optional[datetime]:
    return _coerce_dt(fact.get("valid_from")) or _coerce_dt(fact.get("created_at"))


def _review_status(trust_score: float, is_llm: bool) -> str:
    """Auto-rule:
      * very-low trust → flagged (needs a human look).
      * high-trust AND structured (not LLM-extracted) → auto_approved.
      * everything else (incl. all LLM-extracted facts) → unreviewed.
    Never returns human_approved — that state is only set by a human and is
    preserved by the backfill / wrapper, never overwritten here."""
    if trust_score < FLAG_TRUST:
        return "flagged"
    if trust_score >= AUTO_APPROVE_TRUST and not is_llm:
        return "auto_approved"
    return "unreviewed"


def score_fact(
    fact: dict,
    *,
    source_reliability_map: dict[str, float] = SOURCE_RELIABILITY,
    resolver_conf: Optional[float] = None,
    now: Optional[datetime] = None,
) -> FactGovernance:
    """Compute the governance bundle for ``fact`` (a ledger-row-shaped dict).

    Pure: no DB, no clock unless ``now`` is omitted (then uses utcnow). Returns a
    ``FactGovernance`` with all six dimensions + the composite ``trust_score``.
    """
    now = now or datetime.now(timezone.utc)
    fact_class = fact.get("fact_class") or "signal"

    source_reliability = _source_reliability(fact_class, source_reliability_map)
    extraction_confidence = _extraction_confidence(fact)
    resolver_confidence = (
        _clamp01(resolver_conf) if resolver_conf is not None
        else DEFAULT_RESOLVER_CONFIDENCE
    )

    freshness_at = _freshness_at(fact)
    if freshness_at is not None:
        age_days = (now - freshness_at).total_seconds() / 86400.0
    else:
        age_days = 0.0  # unknown age → no decay penalty (don't punish missing ts)
    freshness = freshness_decay(age_days)

    # Conjunctive weighted-product quality, then multiplicative freshness decay.
    quality = (
        math.pow(max(source_reliability, 1e-9), W_SOURCE)
        * math.pow(max(resolver_confidence, 1e-9), W_RESOLVER)
        * math.pow(max(extraction_confidence, 1e-9), W_EXTRACTION)
    )
    trust_score = _clamp01(quality * freshness)

    is_llm = _is_llm_extraction(fact.get("created_by") or "", fact.get("object_value"))
    review_status = _review_status(trust_score, is_llm)

    return FactGovernance(
        source_reliability=round(source_reliability, 4),
        extraction_confidence=round(extraction_confidence, 4),
        resolver_confidence=round(resolver_confidence, 4),
        freshness_at=freshness_at,
        review_status=review_status,
        schema_version=GOVERNANCE_SCHEMA_VERSION,
        trust_score=round(trust_score, 4),
    )
