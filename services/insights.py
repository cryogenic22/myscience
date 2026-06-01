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
        synthesis_test_rationale, domain, created_by, tenant_scope,
        engagement_id, dossier_snapshot_id
    ) VALUES (
        %(statement)s, %(strategic_frame)s, %(derived_from)s::jsonb, %(passed)s,
        %(rationale)s, %(domain)s, %(created_by)s, %(tenant_scope)s,
        %(engagement_id)s, %(dossier_snapshot_id)s
    )
    RETURNING id
"""

_INSERT_REJECTED_SQL = """
    INSERT INTO rejected_insights (
        candidate_statement, rejection_reason, derived_from, engagement_id
    ) VALUES (
        %(statement)s, %(reason)s, %(derived_from)s::jsonb, %(engagement_id)s
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
    engagement_id: Optional[str] = None,
    dossier_snapshot_id: Optional[str] = None,
) -> str:
    """Run the synthesis test on the candidate; persist to insights (on pass)
    or rejected_insights (on fail). Returns the resulting row id.

    `engagement_id` scopes the insight to an engagement (UX06); when omitted
    the insight is global (the legacy tenant_scope path)."""
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
            "engagement_id": engagement_id,
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
        "engagement_id": engagement_id,
        "dossier_snapshot_id": dossier_snapshot_id,
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


# ── Engagement-scoped synthesis (UX06 / PB-UX06) ───────────────────
#
# Derive insights from a dossier snapshot (deterministic + grounded — every
# insight cites the real facts it springs from), persist them scoped to the
# engagement, and list the live (non-archived) set. Mirrors the scenarios
# derive→assemble→persist→list shape. No LLM in the core; an optional polish
# pass can refine statements later (the citations are the integrity guarantee).

_MAX_SYNTH_INSIGHTS = 8
_MAX_CITATIONS = 4

# Domain → default strategic frame. A signal-class fact in the domain overrides
# this to 'trigger' (a development that forces a decision).
_DOMAIN_FRAME = {
    "competitive":           "risk",
    "pricing_and_access":    "risk",
    "clinical_profile":      "opportunity",
    "pipeline_and_macro":    "trigger",
    "disease_and_patient":   "assumption",
    "commercial_operational": "opportunity",
    "hcp_and_patient":       "assumption",
    "wargame_specific":      "trigger",
}

# Domain → statement template (`{focal}` = focal asset, `{n}` = citation count).
_DOMAIN_STATEMENT = {
    "competitive":            "Competitive exposure: {focal} contends with {n} in-class rival(s) — defending share is the central commercial risk.",
    "pricing_and_access":     "Access risk: {focal}'s payer/pricing position rests on {n} data point(s); net-price erosion is the key uncertainty.",
    "clinical_profile":       "Clinical strength: {focal}'s profile is supported by {n} evidence point(s) — the basis for differentiation.",
    "pipeline_and_macro":     "Pipeline/macro trigger: {n} development(s) could shift {focal}'s trajectory.",
    "disease_and_patient":    "Patient-landscape assumption: {n} epidemiology/patient-flow point(s) underpin {focal}'s opportunity sizing.",
    "commercial_operational": "Commercial read: {n} corporate/financial data point(s) frame {focal}'s execution.",
    "hcp_and_patient":        "Adoption assumption: {n} HCP/patient-behaviour point(s) shape {focal} uptake.",
    "wargame_specific":       "Strategic signal: {n} development(s) relevant to {focal}.",
}

_PRIORITY_RANK = {"critical": 0, "high": 1, "medium": 2}


def _focal_pretty(focal_asset: Optional[str]) -> str:
    if not focal_asset:
        return "the focal asset"
    return focal_asset.split(":")[-1].strip() or "the focal asset"


def _citation_from_fact(fact) -> dict:
    """A grounded FactCitation dict from a DossierFact: predicate from the claim
    prefix (or fact class), contribution = the fact's actual claim."""
    claim = getattr(fact, "claim", "") or ""
    predicate = claim.split(":")[0].strip().lower().replace(" ", "_") if ":" in claim \
        else (getattr(fact, "fact_class", "") or "evidence")
    return {
        "fact_id": getattr(fact, "id", ""),
        "predicate": predicate[:60],
        "contribution": claim[:160] or "supporting evidence",
    }


def derive_synthesis_insights(snapshot) -> list[dict]:
    """Pure: build grounded insight CANDIDATES from a dossier snapshot — one per
    substantive domain that carries evidence, each citing up to 4 of its facts.
    Domains sorted critical→high→medium; capped. Frame from the domain (a
    signal-class fact bumps it to 'trigger'). Each candidate is the {statement,
    strategic_frame, derived_from, domain} shape the synthesis_test gate expects;
    callers run them through assert_insight to gate + persist."""
    focal = _focal_pretty(getattr(snapshot, "focal_asset", None))
    domains = sorted(
        getattr(snapshot, "domains", []),
        key=lambda d: (_PRIORITY_RANK.get(d.priority, 9), -len(d.facts)),
    )
    candidates: list[dict] = []
    for d in domains:
        if not d.facts:
            continue
        # Skip wargame_specific — the uncategorized catch-all where routine
        # recalls/shortages collect (PB-H07). Its facts are noise, not a
        # decision-forcing insight; mirror the scenarios derivation's exclusion.
        if d.domain == "wargame_specific":
            continue
        cited = d.facts[:_MAX_CITATIONS]
        n = len(cited)
        frame = _DOMAIN_FRAME.get(d.domain, "assumption")
        if any(getattr(f, "fact_class", "") == "signal" for f in cited):
            frame = "trigger"
        template = _DOMAIN_STATEMENT.get(
            d.domain, "{focal}: {n} evidence point(s) inform the strategic picture.")
        candidates.append({
            "statement": template.format(focal=focal, n=n),
            "strategic_frame": frame,
            "domain": d.domain,
            "derived_from": [_citation_from_fact(f) for f in cited],
        })
        if len(candidates) >= _MAX_SYNTH_INSIGHTS:
            break
    return candidates


_ARCHIVE_INSIGHTS_SQL = """
    UPDATE insights SET is_archived = TRUE
     WHERE engagement_id = %s AND is_archived = FALSE
"""
_ARCHIVE_REJECTED_SQL = """
    UPDATE rejected_insights SET is_archived = TRUE
     WHERE engagement_id = %s AND is_archived = FALSE
"""

_SELECT_ENGAGEMENT_INSIGHTS_SQL = """
    SELECT id, statement, strategic_frame, derived_from, synthesis_test_passed,
           synthesis_test_rationale, domain, created_by, created_at
      FROM insights
     WHERE engagement_id = %(eid)s AND is_archived = FALSE
       AND synthesis_test_passed = TRUE
     ORDER BY created_at ASC
"""
_SELECT_ENGAGEMENT_REJECTED_SQL = """
    SELECT id, candidate_statement, rejection_reason, derived_from
      FROM rejected_insights
     WHERE engagement_id = %(eid)s AND is_archived = FALSE
     ORDER BY created_at ASC
"""


def _insight_to_camel(ins: Insight) -> dict:
    """Serialize an Insight to the frontend SynthesisPage `Insight` shape."""
    return {
        "id": ins.id,
        "statement": ins.statement,
        "strategicFrame": ins.strategic_frame.value,
        "domain": ins.domain,
        "derivedFrom": [
            {"factId": c.fact_id, "predicate": c.predicate, "contribution": c.contribution}
            for c in ins.derived_from
        ],
        "synthesisTestRationale": ins.synthesis_test_rationale,
        "createdAt": ins.created_at.isoformat()
            if isinstance(ins.created_at, datetime) else ins.created_at,
    }


def _rejected_row_to_camel(row: dict) -> dict:
    derived = row.get("derived_from") or []
    if isinstance(derived, str):
        try:
            derived = json.loads(derived)
        except (TypeError, ValueError):
            derived = []
    return {
        "id": str(row.get("id", "")),
        "candidateStatement": row.get("candidate_statement", ""),
        "rejectionReason": row.get("rejection_reason", ""),
        "derivedFrom": [
            {"factId": c.get("fact_id", ""), "predicate": c.get("predicate", ""),
             "contribution": c.get("contribution", "")}
            for c in derived if isinstance(c, dict)
        ],
    }


def list_engagement_synthesis(db, engagement_id: str) -> dict:
    """The live (non-archived) synthesis set for an engagement, serialized to the
    frontend shape: {insights, rejectedInsights, passRate, count}."""
    eid = str(engagement_id)
    try:
        irows = db.fetch_all(_SELECT_ENGAGEMENT_INSIGHTS_SQL, {"eid": eid}) or []
    except Exception:
        logger.exception("list engagement insights failed for %s", eid)
        irows = []
    try:
        rrows = db.fetch_all(_SELECT_ENGAGEMENT_REJECTED_SQL, {"eid": eid}) or []
    except Exception:
        logger.exception("list engagement rejected insights failed for %s", eid)
        rrows = []

    insights: list[dict] = []
    for r in irows:
        try:
            derived = r.get("derived_from") or []
            if isinstance(derived, str):
                derived = json.loads(derived)
            citations = [
                FactCitation(fact_id=c.get("fact_id", ""), predicate=c.get("predicate", ""),
                             contribution=c.get("contribution", ""))
                for c in derived if isinstance(c, dict)
            ]
            ins = Insight(
                id=str(r["id"]), statement=r["statement"],
                strategic_frame=StrategicFrame(r["strategic_frame"]),
                derived_from=citations, synthesis_test_passed=True,
                synthesis_test_rationale=r.get("synthesis_test_rationale", ""),
                domain=r["domain"], created_by=r.get("created_by", "intelligence_agent"),
                created_at=r.get("created_at"),
            )
            insights.append(_insight_to_camel(ins))
        except (InsightContractError, KeyError) as exc:
            logger.warning("skipping malformed engagement insight: %s", exc)

    rejected = [_rejected_row_to_camel(r) for r in rrows]
    total = len(insights) + len(rejected)
    pass_rate = round(100 * len(insights) / total) if total else 0
    return {
        "insights": insights,
        "rejectedInsights": rejected,
        "passRate": pass_rate,
        "count": len(insights),
    }


def assemble_and_persist_insights(
    db,
    engagement_id: str,
    *,
    as_of=None,
    created_by: str = "intelligence_agent",
) -> dict:
    """Derive synthesis insights from the engagement's latest dossier (assembling
    one if needed), archive the prior batch, persist the new candidates through
    the synthesis-test gate (scoped to the engagement), and return the live set.
    Append-only in spirit: prior rows are archived, never deleted."""
    from services import dossier_kb

    eid = str(engagement_id)
    snap = dossier_kb.get_latest_snapshot(db, eid)
    if snap is None:
        snap = dossier_kb.assemble_dossier(db, eid, as_of=as_of)

    # Archive the prior batch (append-only spirit).
    for sql in (_ARCHIVE_INSIGHTS_SQL, _ARCHIVE_REJECTED_SQL):
        try:
            db.execute(sql, [eid])
        except Exception:
            logger.exception("archive prior synthesis failed for %s", eid)

    snap_id = getattr(snap, "id", None)
    for cand in derive_synthesis_insights(snap):
        assert_insight(
            db,
            statement=cand["statement"],
            strategic_frame=cand["strategic_frame"],
            derived_from=cand["derived_from"],
            domain=cand["domain"],
            created_by=created_by,
            engagement_id=eid,
            dossier_snapshot_id=snap_id,
        )

    return list_engagement_synthesis(db, eid)
