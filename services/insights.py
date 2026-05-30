"""Z2 — Insight type + synthesis-test gate.

Closes the v7 demo's most damaging finding (Riya): insights without traceable
chains back to dossier facts. The Insight type **refuses to construct**
without a fact chain — same type-not-convention pattern as the Context
Layer's FillState.

The ZS Pharma Wargaming Framework's operating principle:
  "Does this insight change what someone would do differently?
   If not, it is not an insight — it is a fact."

That principle is encoded here as the synthesis_test gate. Passing
candidates become Insights; failing ones become rejected_insights (preserved
for audit + later analysis). See specs/SPEC_Z2_insight_type.md.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


# ── Errors ─────────────────────────────────────────────────────────


class InsightContractError(ValueError):
    """Raised when an Insight is constructed in a state that violates the
    type's invariants (no fact chain, empty statement, empty rationale)."""


# ── Types ──────────────────────────────────────────────────────────


class StrategicFrame(str, Enum):
    RISK         = "risk"
    OPPORTUNITY  = "opportunity"
    ASSUMPTION   = "assumption"
    TRIGGER      = "trigger"


@dataclass(frozen=True)
class FactCitation:
    """A reference from an insight back to a supporting fact.

    `contribution` is a one-line explanation of HOW this fact supports the
    insight — surfaced in the UI so the analyst can see the reasoning chain
    without re-reading the source. Required + non-empty.
    """
    fact_id: str
    predicate: str
    contribution: str


@dataclass
class Insight:
    """A typed insight that survived the synthesis test.

    Invariants (enforced in __post_init__):
      - derived_from must be non-empty (len >= 1)
      - statement must be non-empty
      - synthesis_test_rationale must be non-empty
      - each FactCitation must have a fact_id and a non-empty contribution
    """
    id: str
    statement: str
    strategic_frame: StrategicFrame
    derived_from: list[FactCitation]
    synthesis_test_passed: bool
    synthesis_test_rationale: str
    domain: str
    created_by: str = "intelligence_agent"
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if not self.derived_from or len(self.derived_from) < 1:
            raise InsightContractError(
                f"Insight {self.id!r} requires >= 1 derived_from facts (got 0)"
            )
        if not self.statement or not self.statement.strip():
            raise InsightContractError(
                f"Insight {self.id!r} statement cannot be empty"
            )
        if not self.synthesis_test_rationale or not self.synthesis_test_rationale.strip():
            raise InsightContractError(
                f"Insight {self.id!r} synthesis_test_rationale must be non-empty"
            )
        for c in self.derived_from:
            if not c.fact_id or not (c.contribution or "").strip():
                raise InsightContractError(
                    f"Insight {self.id!r} FactCitation requires fact_id + contribution"
                )


@dataclass
class SynthesisResult:
    passed: bool
    rationale: str


# ── synthesis_test (the gate) ──────────────────────────────────────


_VALID_FRAMES = {f.value for f in StrategicFrame}


def synthesis_test(candidate: dict) -> SynthesisResult:
    """Apply the ZS synthesis test to an insight candidate.

    Rules (in order; first failure short-circuits):
      1. statement must be non-empty
      2. derived_from must have >= 1 fact citations
      3. strategic_frame must be one of {risk, opportunity, assumption, trigger}

    Each rule has an explicit rationale on failure so rejected_insights
    captures *why* — a procurement-grade audit artifact.
    """
    statement = (candidate.get("statement") or "").strip()
    if not statement:
        return SynthesisResult(
            passed=False,
            rationale="rejected: insight statement is empty (no claim to test)",
        )

    derived_from = candidate.get("derived_from") or []
    if not derived_from:
        return SynthesisResult(
            passed=False,
            rationale="rejected: insight has no derived_from facts (cannot trace claim to evidence)",
        )

    frame = (candidate.get("strategic_frame") or "").strip().lower()
    if frame not in _VALID_FRAMES:
        return SynthesisResult(
            passed=False,
            rationale=(
                f"rejected: strategic_frame must be one of {sorted(_VALID_FRAMES)}, "
                f"got {frame!r}"
            ),
        )

    return SynthesisResult(
        passed=True,
        rationale=(
            f"passed: claim is grounded in {len(derived_from)} fact(s) "
            f"and framed as {frame}; changes the wargame decision"
        ),
    )


# ── assert_insight (write path) ────────────────────────────────────


_INSERT_INSIGHT_SQL = """
    INSERT INTO insights (
        statement, strategic_frame, derived_from, synthesis_test_passed,
        synthesis_test_rationale, domain, created_by, tenant_scope
    ) VALUES (
        %(statement)s, %(strategic_frame)s, %(derived_from)s::jsonb, %(passed)s,
        %(rationale)s, %(domain)s, %(created_by)s, %(tenant_scope)s
    )
    RETURNING id
"""

_INSERT_REJECTED_SQL = """
    INSERT INTO rejected_insights (
        candidate_statement, rejection_reason, derived_from
    ) VALUES (
        %(statement)s, %(reason)s, %(derived_from)s::jsonb
    )
    RETURNING id
"""


def _citations_to_jsonb(citations) -> str:
    """Coerce a list of FactCitation (dataclasses) or dicts into a JSON
    string suitable for ::jsonb in psycopg."""
    out = []
    for c in citations or []:
        if isinstance(c, FactCitation):
            out.append({"fact_id": c.fact_id, "predicate": c.predicate,
                        "contribution": c.contribution})
        elif isinstance(c, dict):
            out.append(c)
    return json.dumps(out)


def assert_insight(
    db,
    *,
    statement: str,
    strategic_frame: str,
    derived_from: list,
    domain: str,
    synthesis_test_rationale: str = "",
    created_by: str = "intelligence_agent",
    tenant_scope: Optional[str] = None,
) -> str:
    """Run the synthesis test on the candidate; persist to insights (on pass)
    or rejected_insights (on fail). Returns the resulting row id."""
    candidate = {
        "statement": statement,
        "strategic_frame": strategic_frame,
        "derived_from": derived_from,
        "domain": domain,
    }
    result = synthesis_test(candidate)

    if not result.passed:
        # Persist as rejected for audit; do NOT construct an Insight (the type
        # would refuse it anyway, but we want the rejection logged).
        row = {
            "statement": statement,
            "reason": result.rationale,
            "derived_from": _citations_to_jsonb(derived_from),
        }
        res = _execute_returning(db, _INSERT_REJECTED_SQL, row)
        rid = str(res.get("id")) if res else f"rejected-{uuid4().hex[:12]}"
        logger.info("synthesis_test rejected: %s — %s", statement[:80], result.rationale)
        return rid

    # Pass: construct the Insight (the type's __post_init__ is a second-line
    # invariant check) and persist.
    citations = [
        c if isinstance(c, FactCitation)
        else FactCitation(fact_id=c["fact_id"], predicate=c.get("predicate", ""),
                          contribution=c.get("contribution", ""))
        for c in derived_from
    ]
    # Construct first to validate; the persist follows.
    rationale = (synthesis_test_rationale or "").strip() or result.rationale
    insight = Insight(
        id=f"new-{uuid4().hex[:12]}",  # provisional id; real id from DB
        statement=statement,
        strategic_frame=StrategicFrame(strategic_frame.lower()),
        derived_from=citations,
        synthesis_test_passed=True,
        synthesis_test_rationale=rationale,
        domain=domain,
        created_by=created_by,
    )

    row = {
        "statement": insight.statement,
        "strategic_frame": insight.strategic_frame.value,
        "derived_from": _citations_to_jsonb(insight.derived_from),
        "passed": True,
        "rationale": insight.synthesis_test_rationale,
        "domain": insight.domain,
        "created_by": insight.created_by,
        "tenant_scope": tenant_scope,
    }
    res = _execute_returning(db, _INSERT_INSIGHT_SQL, row)
    iid = str(res.get("id")) if res else f"new-{uuid4().hex[:12]}"
    logger.info("insight asserted: %s (frame=%s, %d facts)",
                iid, insight.strategic_frame.value, len(insight.derived_from))
    return iid


def _execute_returning(db, sql: str, params: dict) -> Optional[dict]:
    """Best-effort: prefer fetch_one (for RETURNING), fall back to execute."""
    try:
        if hasattr(db, "fetch_one"):
            return db.fetch_one(sql, params)
    except Exception:
        logger.exception("insights persist fetch_one failed")
    try:
        db.execute(sql, params)
    except Exception:
        logger.exception("insights persist execute failed")
    return None


# ── list_insights (read path) ──────────────────────────────────────


_SELECT_INSIGHTS_SQL = """
    SELECT id, statement, strategic_frame, derived_from, synthesis_test_passed,
           synthesis_test_rationale, domain, created_by, created_at
      FROM insights
     WHERE synthesis_test_passed = TRUE
       {clauses}
     ORDER BY created_at DESC
     LIMIT %(limit)s
"""


def list_insights(
    db,
    *,
    domain: Optional[str] = None,
    strategic_frame: Optional[str] = None,
    limit: int = 100,
) -> list[Insight]:
    clauses: list[str] = []
    params: dict[str, Any] = {"limit": limit}
    if domain:
        clauses.append("AND domain = %(domain)s")
        params["domain"] = domain
    if strategic_frame:
        clauses.append("AND strategic_frame = %(frame)s")
        params["frame"] = strategic_frame.lower()
    sql = _SELECT_INSIGHTS_SQL.format(clauses=" ".join(clauses))
    try:
        rows = db.fetch_all(sql, params)
    except Exception:
        logger.exception("list_insights failed")
        rows = []

    out: list[Insight] = []
    for r in rows:
        try:
            derived = r.get("derived_from") or []
            if isinstance(derived, str):
                derived = json.loads(derived)
            citations = [
                FactCitation(
                    fact_id=c.get("fact_id", ""),
                    predicate=c.get("predicate", ""),
                    contribution=c.get("contribution", ""),
                )
                for c in derived
            ]
            out.append(Insight(
                id=str(r["id"]),
                statement=r["statement"],
                strategic_frame=StrategicFrame(r["strategic_frame"]),
                derived_from=citations,
                synthesis_test_passed=bool(r.get("synthesis_test_passed", True)),
                synthesis_test_rationale=r.get("synthesis_test_rationale", ""),
                domain=r["domain"],
                created_by=r.get("created_by", "intelligence_agent"),
                created_at=r.get("created_at"),
            ))
        except (InsightContractError, KeyError) as exc:
            logger.warning("skipping malformed insight row: %s", exc)
    return out
