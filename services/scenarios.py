"""Scenarios (PB-H09) — first-class probabilistic objects grounded in the dossier.

A scenario is a named, plausible future ("Competitive pressure: tirzepatide")
DERIVED from a dossier snapshot, citing the specific facts that justify it
(provenance) and carrying a PRIOR probability. This closes the missing vertebra
in the provenance spine:

    signal -> fact -> insight -> SCENARIO -> decision -> outcome

Scope of this loop: the OBJECT, its derivation from the dossier, its provenance,
its prior, and its persistence. Deliberately NOT in this loop (each its own):
  * current_prob re-weighting as signals arrive  -> PB-H14 (calibration loop)
  * per-team moves + NPV-scored decision options  -> PB-H10 / PB-H11
  * LLM-polished scenario narrative               -> later narrative loop

Derivation here is deterministic + reuse-first (no LLM): scenarios are built from
the dossier's most material content — competitive pressure (rival entities routed
into the competitive domain by B5) and high-signal facts in critical/high domains
— each citing the dossier facts it springs from, and inheriting the dossier's
high-importance gaps as `blocked_by_gaps` (reusing the D1 actionable-gaps surface).

The prior is an explicit STRUCTURAL HEURISTIC (a defensible starting point), not a
forecast. The real number comes from calibration (PB-H14). We keep it honest:
grounded evidence and stronger graph edges nudge the prior up, bounded to [0.1, 0.7].

Serialization matches the frontend ScenariosPage.tsx `Scenario` interface exactly
(camelCase: factId / npv5yDkkBn / probabilityCurrent / blockedByGaps) — assembly is
server-side, the UI is dumb.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from services.dossier_kb import DossierSnapshot, _DOMAIN_LABEL

logger = logging.getLogger(__name__)

_MAX_SCENARIOS = 6          # mirror the benchmark's 6 scenarios (A–F)
_MAX_COMPETITIVE = 4        # don't let rivals crowd out signal-driven futures
_EDGE_RE = re.compile(r"\((\d+)\s+edges?\)")
_LEADING_TAG_RE = re.compile(r"^\[[^\]]+\]\s*")


# ── Domain model (serializes to the frontend Scenario interface) ────


@dataclass
class ScenarioEvidence:
    fact_id: str
    predicate: str

    def to_dict(self) -> dict:
        return {"factId": self.fact_id, "predicate": self.predicate}


@dataclass
class TeamMove:
    team: str
    move: str
    rationale: str
    # PB-H11: illustrative directional impact of this move on each team, in
    # [-1, 1] (acting team gains, others affected per strategic logic). A
    # transparent structural estimate for guided war-gaming — NOT a forecast.
    impact: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "team": self.team, "move": self.move, "rationale": self.rationale,
            "impact": {k: round(float(v), 2) for k, v in (self.impact or {}).items()},
        }


@dataclass
class DecisionOption:
    id: str
    statement: str
    rationale: str
    npv_5y_dkk_bn: Optional[float] = None
    recommended: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "statement": self.statement,
            "rationale": self.rationale,
            "npv5yDkkBn": self.npv_5y_dkk_bn,
            "recommended": self.recommended,
        }


@dataclass
class Scenario:
    name: str
    trigger_event: str
    prior_prob: float
    evidence: list[ScenarioEvidence] = field(default_factory=list)
    trigger_date: Optional[str] = None
    current_prob: Optional[float] = None
    calibration_note: Optional[str] = None
    team_moves: list[TeamMove] = field(default_factory=list)
    decision_options: list[DecisionOption] = field(default_factory=list)
    decision_output: Optional[str] = None
    blocked_by_gaps: list[str] = field(default_factory=list)
    # PB-H10c: the dossier domain(s) this scenario draws its evidence from —
    # used to scope which gaps block it (own-domain gaps only, not every high
    # gap). Transient: not serialized, not persisted.
    source_domains: list[str] = field(default_factory=list, compare=False)
    # set on persist / read
    id: Optional[str] = None
    engagement_id: Optional[str] = None
    dossier_snapshot_id: Optional[str] = None
    created_by: str = "system"
    created_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "trigger": {
                "event": self.trigger_event,
                "date": self.trigger_date,
                "evidence": [e.to_dict() for e in self.evidence],
            },
            "probability": round(self.prior_prob, 3),
            "probabilityCurrent": round(self.current_prob, 3)
                if self.current_prob is not None else None,
            # PB-H14 — why current moved (cites the corroborating signal).
            "calibrationNote": self.calibration_note,
            "teamMoves": [m.to_dict() for m in self.team_moves],
            "decisionOptions": [o.to_dict() for o in self.decision_options],
            "decisionOutput": self.decision_output,
            "blockedByGaps": list(self.blocked_by_gaps),
        }


# ── Pure derivation (no DB) — the testable core ─────────────────────


def _prior_from_fact(claim: str, fact_class: str, *, base: float = 0.3) -> float:
    """Structural heuristic prior in [0.1, 0.7]. Grounded evidence lifts it;
    a denser competitive graph edge lifts it further. Honest starting point —
    calibration (PB-H14) supplies the real probability."""
    p = base
    if fact_class in ("corporate", "reference"):
        p += 0.10
    m = _EDGE_RE.search(claim or "")
    if m:
        p += min(int(m.group(1)), 5) * 0.04   # up to +0.20 for a well-linked rival
    return round(min(max(p, 0.1), 0.7), 2)


def _focal_pretty(focal_asset: Optional[str]) -> str:
    """`drug:semaglutide` → `semaglutide`; falls back to a neutral label."""
    if not focal_asset:
        return "the focal asset"
    return focal_asset.split(":")[-1].strip() or "the focal asset"


# PB-H10/H11 — team moves + decision options.
#
# Deterministic, grounded scaffolding (NO LLM, always present). Moves are framed
# from each actor's RATIONAL INTEREST given the scenario; options are mutually-
# exclusive strategic paths for the client (the focal-asset owner), exactly one
# marked recommended by a defensible heuristic. NPV is left None on purpose — we
# have no value model yet, and fabricating bn-DKK figures would be dishonest
# (quantitative NPV is its own loop, PB-H11b). The frontend renders options
# cleanly without the NPV line.


def _competitive_team_moves(rival: str, focal: str) -> list[TeamMove]:
    return [
        TeamMove(
            team=rival,
            move=f"Press the advantage — expand into {focal}'s shared indications "
                 f"and bid aggressively for formulary position.",
            rationale=f"{rival} holds a live competitive edge; rational self-interest "
                      f"is to convert it into share before {focal} can respond.",
            impact={rival: 0.6, focal: -0.4, "Payers": 0.1},
        ),
        TeamMove(
            team=focal,
            move=f"Defend share — reinforce differentiation (outcomes, dosing, access) "
                 f"and lock in payer contracts ahead of {rival}'s push.",
            rationale="Protecting installed base and formulary tier is cheaper than "
                      "re-winning share once lost.",
            impact={focal: 0.5, rival: -0.3, "Payers": -0.1},
        ),
        TeamMove(
            team="Payers",
            move=f"Exploit the rivalry — extract deeper rebates across the class while "
                 f"{rival} and {focal} compete.",
            rationale="A contested class is leverage; payers rationally play suppliers "
                      "against one another.",
            impact={"Payers": 0.6, rival: -0.3, focal: -0.3},
        ),
    ]


def _competitive_options(rival: str, focal: str, prior: float) -> list[DecisionOption]:
    recommend_defend = prior >= 0.4   # higher threat → defend; lower → margin focus
    return [
        DecisionOption(
            id="defend-differentiate",
            statement=f"Defend & differentiate {focal}",
            rationale=f"Out-evidence {rival} on outcomes and secure preferred access — "
                      f"protects premium positioning.",
            recommended=recommend_defend,
        ),
        DecisionOption(
            id="compete-access",
            statement="Compete on price & access",
            rationale=f"Match {rival}'s contracting to hold formulary share, accepting "
                      f"margin compression.",
            recommended=False,
        ),
        DecisionOption(
            id="segment-defend",
            statement="Segment & defend the core",
            rationale=f"Concede price-sensitive segments to {rival}; concentrate spend on "
                      f"the highest-value patients and channels.",
            recommended=not recommend_defend,
        ),
    ]


def _signal_team_moves(headline: str, focal: str) -> list[TeamMove]:
    return [
        TeamMove(
            team="Market mover",
            move="Capitalize on the development — move first to convert it into a "
                 "commercial or regulatory advantage.",
            rationale=f"The party behind “{headline}” is rationally motivated to "
                      f"press the opening.",
            impact={"Market mover": 0.6, focal: -0.3, "Regulators & payers": 0.0},
        ),
        TeamMove(
            team=focal,
            move=f"Adapt the plan — stress-test the {focal} launch/defense assumptions "
                 f"this development invalidates and pre-empt the downside.",
            rationale="Early adaptation preserves optionality; waiting cedes initiative.",
            impact={focal: 0.4, "Market mover": -0.2},
        ),
        TeamMove(
            team="Regulators & payers",
            move="Reassess the class — the development may shift reimbursement or "
                 "approval posture across comparable assets.",
            rationale="Institutional actors recalibrate when the evidence or market "
                      "structure changes.",
            impact={"Regulators & payers": 0.3, focal: -0.2, "Market mover": -0.2},
        ),
    ]


def _signal_options(focal: str) -> list[DecisionOption]:
    return [
        DecisionOption(
            id="preempt",
            statement="Pre-empt the shift",
            rationale=f"Invest ahead of the curve so {focal} shapes rather than reacts "
                      f"to the development.",
            recommended=True,
        ),
        DecisionOption(
            id="monitor",
            statement="Monitor & stage the response",
            rationale="Hold spend until the signal resolves into a confirmed trend; act "
                      "on pre-set triggers.",
            recommended=False,
        ),
        DecisionOption(
            id="hedge",
            statement="Hedge across outcomes",
            rationale=f"Split investment so {focal} is protected whether or not the "
                      f"development materializes.",
            recommended=False,
        ),
    ]


def _competitive_pretty(claim: str) -> str:
    """Rival display name from a competitive fact claim like
    'drug:tirzepatide — competes_with (4 edges)' → 'tirzepatide'."""
    head = (claim or "").split(" — ")[0].split(" (")[0].strip()
    return head.split(":")[-1].strip() if ":" in head else head


def _is_self_competitor(rival_pretty: str, focal: str) -> bool:
    """PB-H10c: suppress focal self-matches — e.g. a 'GLP-1 analogue - semaglutide'
    competitor row when the focal asset IS semaglutide. Substring either way (the
    rival label often embeds the focal generic)."""
    r = (rival_pretty or "").strip().lower()
    f = (focal or "").strip().lower()
    if not r or not f or f in ("the focal asset",):
        return False
    return r == f or f in r or r in f


def _competitive_scenario(fact, focal_asset: Optional[str] = None) -> Scenario:
    pretty = _competitive_pretty(fact.claim)
    focal = _focal_pretty(focal_asset)
    prior = _prior_from_fact(fact.claim, fact.fact_class)
    return Scenario(
        name=f"Competitive pressure: {pretty}",
        trigger_event=(
            f"{fact.claim} — escalation here would directly pressure the focal "
            f"asset's competitive position."
        ),
        prior_prob=prior,
        evidence=[ScenarioEvidence(fact_id=fact.id, predicate="competitive_relation")],
        team_moves=_competitive_team_moves(pretty, focal),
        decision_options=_competitive_options(pretty, focal, prior),
        source_domains=["competitive"],
    )


def _signal_scenario(domain: str, fact, focal_asset: Optional[str] = None) -> Scenario:
    name = _LEADING_TAG_RE.sub("", fact.claim).strip()[:80]
    label = _DOMAIN_LABEL.get(domain, domain.replace("_", " "))
    focal = _focal_pretty(focal_asset)
    return Scenario(
        name=f"Signal: {name}",
        trigger_event=(
            f"{fact.claim} — a development in {label} that could shift the "
            f"competitive picture."
        ),
        prior_prob=_prior_from_fact(fact.claim, fact.fact_class),
        evidence=[ScenarioEvidence(fact_id=fact.id, predicate="signal")],
        team_moves=_signal_team_moves(name, focal),
        decision_options=_signal_options(focal),
        source_domains=[domain],
    )


def _domain(snapshot: DossierSnapshot, name: str):
    for d in snapshot.domains:
        if d.domain == name:
            return d
    return None


def derive_scenarios(snapshot: DossierSnapshot) -> list[Scenario]:
    """Pure: build candidate scenarios from a dossier snapshot. No DB, no LLM —
    the testable keystone. Competitive-pressure scenarios from the competitive
    domain + signal-driven scenarios from critical/high domains, deduped by
    name, sorted by prior, capped at _MAX_SCENARIOS. Every scenario cites the
    fact(s) it sprang from; all inherit the dossier's high-importance gaps as
    blocked_by_gaps (reusing the D1 gaps surface)."""
    candidates: list[Scenario] = []

    focal = getattr(snapshot, "focal_asset", None)

    focal_pretty = _focal_pretty(focal)
    comp = _domain(snapshot, "competitive")
    if comp is not None:
        for f in comp.facts[:_MAX_COMPETITIVE]:
            # PB-H10c: drop focal self-matches (e.g. "GLP-1 analogue - semaglutide"
            # when the focal asset is semaglutide).
            if _is_self_competitor(_competitive_pretty(f.claim), focal_pretty):
                continue
            candidates.append(_competitive_scenario(f, focal))

    for dv in snapshot.domains:
        # Signal-driven scenarios come from the substantive strategic domains.
        # Skip wargame_specific (the uncategorized catch-all) — its signals are
        # generic events (e.g. routine recalls/shortages), noise rather than a
        # decision-forcing scenario (PB-H07).
        if dv.priority not in ("critical", "high") or dv.domain == "wargame_specific":
            continue
        for f in dv.facts:
            if f.fact_class == "signal":
                candidates.append(_signal_scenario(dv.domain, f, focal))

    # Dedupe by name (keep the first / highest later via sort), cap, sort.
    seen: set[str] = set()
    uniq: list[Scenario] = []
    for s in candidates:
        if s.name in seen:
            continue
        seen.add(s.name)
        uniq.append(s)
    uniq.sort(key=lambda s: s.prior_prob, reverse=True)
    uniq = uniq[:_MAX_SCENARIOS]

    # PB-H10c: block each scenario only on high-importance gaps in the domain(s)
    # it actually draws evidence from — NOT every high gap in the dossier. A
    # scenario with sufficient own-evidence stays playable (provisional);
    # peripheral context gaps are surfaced by the gaps stage, not hard-blockers.
    # This fixes the prior behaviour where ALL scenarios were always blocked.
    high_gaps = [
        g for g in snapshot.gaps(include_thin=False)
        if g.get("importance") == "high"
    ]
    for s in uniq:
        s.blocked_by_gaps = [
            g["text"] for g in high_gaps
            if g.get("domain") in s.source_domains
        ]
    return uniq


# ── DB-backed orchestration ─────────────────────────────────────────


def assemble_scenarios(
    db,
    engagement_id: str,
    *,
    as_of: Optional[datetime] = None,
    assembled_by: str = "system",
    synthesizer=None,
) -> list[Scenario]:
    """Derive scenarios for an engagement from its latest dossier snapshot
    (assembling one on the fly if none persisted yet). Does NOT persist.

    If `synthesizer` is supplied and enabled (PB-H16), each scenario's
    decision_output is filled by grounded LLM synthesis over the facts it
    cites; otherwise scenarios keep their templated state (no LLM, no cost)."""
    from services import dossier_kb

    snap = dossier_kb.get_latest_snapshot(db, engagement_id)
    if snap is None:
        snap = dossier_kb.assemble_dossier(db, engagement_id, as_of=as_of)

    scenarios = derive_scenarios(snap)
    for s in scenarios:
        s.engagement_id = str(engagement_id)
        s.dossier_snapshot_id = snap.id
        s.created_by = assembled_by

    if synthesizer is not None and getattr(synthesizer, "enabled", False):
        try:
            from services.scenario_narrative import enrich_scenarios_with_narrative
            enrich_scenarios_with_narrative(scenarios, snap, synthesizer)
        except Exception:
            logger.warning("scenario narrative enrichment failed", exc_info=True)
    return scenarios


_ARCHIVE_SQL = """
    UPDATE scenarios SET is_archived = TRUE
     WHERE engagement_id = %s AND is_archived = FALSE
"""

_INSERT_SQL = """
    INSERT INTO scenarios (
        engagement_id, dossier_snapshot_id, name, trigger_event, trigger_date,
        from_fact_ids, prior_prob, current_prob, calibration_note,
        team_moves, decision_options, decision_output, blocked_by_gaps, created_by
    ) VALUES (
        %(engagement_id)s, %(dossier_snapshot_id)s, %(name)s, %(trigger_event)s, %(trigger_date)s,
        %(from_fact_ids)s::jsonb, %(prior_prob)s, %(current_prob)s, %(calibration_note)s,
        %(team_moves)s::jsonb, %(decision_options)s::jsonb, %(decision_output)s,
        %(blocked_by_gaps)s::jsonb, %(created_by)s
    )
    RETURNING id, created_at
"""

_LIST_SQL = """
    SELECT id, engagement_id, dossier_snapshot_id, name, trigger_event, trigger_date,
           from_fact_ids, prior_prob, current_prob, calibration_note,
           team_moves, decision_options, decision_output, blocked_by_gaps,
           created_by, created_at
      FROM scenarios
     WHERE engagement_id = %s AND is_archived = FALSE
     ORDER BY prior_prob DESC, created_at DESC
"""


def _insert_params(s: Scenario) -> dict:
    return {
        "engagement_id": s.engagement_id,
        "dossier_snapshot_id": s.dossier_snapshot_id,
        "name": s.name,
        "trigger_event": s.trigger_event,
        "trigger_date": s.trigger_date,
        "from_fact_ids": json.dumps([e.to_dict() for e in s.evidence]),
        "prior_prob": round(s.prior_prob, 4),
        "current_prob": s.current_prob,
        "calibration_note": s.calibration_note,
        "team_moves": json.dumps([m.to_dict() for m in s.team_moves]),
        "decision_options": json.dumps([o.to_dict() for o in s.decision_options]),
        "decision_output": s.decision_output,
        "blocked_by_gaps": json.dumps(list(s.blocked_by_gaps)),
        "created_by": s.created_by,
    }


def persist_scenarios(db, engagement_id: str, scenarios: list[Scenario]) -> list[Scenario]:
    """Archive the engagement's current scenarios, then insert this batch as the
    new live set. Mutates each scenario (id, created_at). Append-only in spirit:
    prior rows are archived, never deleted."""
    try:
        db.execute(_ARCHIVE_SQL, [str(engagement_id)])
    except Exception:
        logger.exception("archive prior scenarios failed for %s", engagement_id)
    for s in scenarios:
        s.engagement_id = str(engagement_id)
        res = db.fetch_one(_INSERT_SQL, _insert_params(s))
        if res:
            s.id = str(res["id"]) if res.get("id") is not None else None
            if res.get("created_at") is not None:
                s.created_at = res["created_at"]
    return scenarios


def assemble_and_persist(
    db,
    engagement_id: str,
    *,
    as_of: Optional[datetime] = None,
    assembled_by: str = "system",
    synthesizer=None,
) -> list[Scenario]:
    scenarios = assemble_scenarios(
        db, engagement_id, as_of=as_of, assembled_by=assembled_by,
        synthesizer=synthesizer)
    persist_scenarios(db, engagement_id, scenarios)
    return scenarios


def _coerce_json_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return []
    return value if isinstance(value, list) else []


def _row_to_scenario(row: dict) -> Scenario:
    evidence = [
        ScenarioEvidence(fact_id=str(e.get("factId", "")), predicate=str(e.get("predicate", "")))
        for e in _coerce_json_list(row.get("from_fact_ids"))
        if isinstance(e, dict)
    ]
    moves = [
        TeamMove(team=m.get("team", ""), move=m.get("move", ""), rationale=m.get("rationale", ""),
                 impact=m.get("impact") if isinstance(m.get("impact"), dict) else {})
        for m in _coerce_json_list(row.get("team_moves"))
        if isinstance(m, dict)
    ]
    options = [
        DecisionOption(
            id=str(o.get("id", "")),
            statement=o.get("statement", ""),
            rationale=o.get("rationale", ""),
            npv_5y_dkk_bn=o.get("npv5yDkkBn"),
            recommended=bool(o.get("recommended", False)),
        )
        for o in _coerce_json_list(row.get("decision_options"))
        if isinstance(o, dict)
    ]
    trigger_date = row.get("trigger_date")
    if isinstance(trigger_date, (datetime,)):
        trigger_date = trigger_date.isoformat()[:10]
    elif trigger_date is not None and not isinstance(trigger_date, str):
        trigger_date = str(trigger_date)
    cur = row.get("current_prob")
    return Scenario(
        id=str(row["id"]) if row.get("id") is not None else None,
        engagement_id=str(row["engagement_id"]) if row.get("engagement_id") is not None else None,
        dossier_snapshot_id=str(row["dossier_snapshot_id"])
            if row.get("dossier_snapshot_id") is not None else None,
        name=row.get("name", ""),
        trigger_event=row.get("trigger_event", ""),
        trigger_date=trigger_date,
        evidence=evidence,
        prior_prob=float(row.get("prior_prob") or 0.0),
        current_prob=float(cur) if cur is not None else None,
        calibration_note=row.get("calibration_note"),
        team_moves=moves,
        decision_options=options,
        decision_output=row.get("decision_output"),
        blocked_by_gaps=[str(g) for g in _coerce_json_list(row.get("blocked_by_gaps"))],
        created_by=row.get("created_by", "system"),
        created_at=row.get("created_at"),
    )


def list_scenarios(db, engagement_id: str) -> list[Scenario]:
    try:
        rows = db.fetch_all(_LIST_SQL, [str(engagement_id)])
    except Exception:
        logger.exception("list_scenarios failed for %s", engagement_id)
        return []
    return [_row_to_scenario(r) for r in (rows or [])]
