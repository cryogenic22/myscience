"""PB-H14 — scenario calibration loop (the Learn-loop vertebra).

A scenario (services/scenarios.py) is derived from a dossier snapshot with a
structural PRIOR probability. The benchmark's whole "wargaming" identity rests
on that prior being RE-WEIGHTED into a CURRENT probability as fresh signals
arrive — each shift carrying a calibration_note tracing to the causing signal.
This closes the flywheel: signal → fact → insight → scenario → (re-weight).

Link model (honest, reuse-first). `affects_scenario_ids` (PB-H01) was never
added, and a scenario's `from_fact_ids` mix real facts.id UUIDs with synthetic
metric-/graph-derived ids, so a fact-id join is unreliable. The robust, grounded
link is ENTITY-LEVEL: a scenario belongs to an engagement whose focal asset is
an entity; signals about that entity that arrive AFTER the scenario was derived
are fresh evidence that the conditions underlying it are active.

Calibration is deliberately a measure of evidence ACCUMULATION, not a forecast:
we move current_prob toward a per-signal support level (by confidence tier) via
EWMA (reusing learning_service.ewma_update). Confirmed signals lift it;
weak/disputed ones blend toward neutral. We never claim a scenario reversed
(that needs contradiction detection — a later loop). Everything is bounded to
[0.05, 0.95] and every shift is explained in the note.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Per-signal support level the scenario's probability is pulled toward, by the
# signal's confidence tier. A confirmed development is strong corroboration; a
# How much each signal corroborates the scenario, by confidence tier. This is a
# SUPPORT weight, not a probability anchor: a disputed signal contributes nothing
# (we do not let unconfirmed/contested news inflate a scenario's probability),
# a confirmed one fully. Honesty: we model evidence ACCUMULATION only — fresh
# corroboration raises the probability monotonically toward a ceiling; we do NOT
# yet model refutation (a signal that should LOWER a scenario), so the loop never
# moves current_prob below the structural prior. Downward calibration needs
# scenario-relative stance detection — an explicit follow-up.
CORROBORATION_WEIGHT: dict[str, float] = {
    "confirmed": 1.0,
    "reported": 0.65,
    "inferred": 0.35,
    "disputed": 0.0,
}
_DEFAULT_WEIGHT = 0.35

# How hard a fully-corroborating signal pulls toward the ceiling. Modest, so a
# single signal never swings a scenario wildly; evidence accumulates over many.
_ALPHA = 0.30

_CEIL = 0.95
_FLOOR = 0.05
_MAX_SIGNALS = 50  # bound the per-scenario evidence window

# Backwards-compatible alias for any external reader of the old name.
OBSERVATION_BY_CONFIDENCE = CORROBORATION_WEIGHT


def _weight(confidence_tier: Optional[str]) -> float:
    return CORROBORATION_WEIGHT.get((confidence_tier or "").lower(), _DEFAULT_WEIGHT)


def _stance(sig: dict, competitive: bool) -> str:
    """Whether a signal SUPPORTS or CONTRADICTS its scenario.

    Stance = signal polarity × scenario direction. The crisp, defensible case is
    a competitive-pressure scenario (the threat is a RIVAL being strong): a
    ``negative``-on-rival signal (setback, failed readout) is evidence the threat
    receded → CONTRADICTS. Outside that framing we do NOT guess a contradiction
    (a negative focal signal often SUPPORTS a risk scenario), so everything else
    SUPPORTS — preserving the prior corroboration-only behaviour."""
    if competitive and (sig.get("direction") or "").lower() == "negative":
        return "contradict"
    return "support"


def _calibrate(
    *, prior: float, signals: list[dict], entity_label: str, competitive: bool,
) -> tuple[Optional[float], Optional[str], int, int]:
    """Core calibration → (current_prob, note, n_supporting, n_contradicting).

    The stance mix is computed HERE so it can be PERSISTED (Loop 1+2 follow-up /
    OQ3 — surface contradictions as structured data, not only as note prose).
    ``calibrate_scenario_prob`` is the public 2-tuple wrapper; the DB orchestrator
    calls this to also get the counts for the probability-history ledger."""
    weighted = [s for s in signals if _weight(s.get("confidence_tier")) > 0]
    if not weighted:
        return None, None, 0, 0

    current = float(prior)
    n_support = n_contra = 0
    for sig in weighted[:_MAX_SIGNALS]:
        w = _weight(sig.get("confidence_tier"))
        if _stance(sig, competitive) == "contradict":
            current = current - w * _ALPHA * (current - _FLOOR)  # toward floor
            n_contra += 1
        else:
            current = current + w * _ALPHA * (_CEIL - current)   # toward ceiling
            n_support += 1

    current = round(min(_CEIL, max(_FLOOR, current)), 3)

    latest = weighted[-1]
    headline = (latest.get("headline") or "").strip()
    conf = (latest.get("confidence_tier") or "unrated")
    date_s = str(latest.get("created_at") or "")[:10]
    parts = []
    if n_support:
        parts.append(f"{n_support} corroborating")
    if n_contra:
        parts.append(f"{n_contra} contradicting")
    verb = "raised" if current >= float(prior) else "lowered"
    note = (
        f"{' and '.join(parts)} signal{'s' if (n_support + n_contra) != 1 else ''} on "
        f"{entity_label} since derivation {verb} this scenario from "
        f"{round(prior, 2)} to {current}. "
        f"Latest: \"{headline}\" ({conf}{f', {date_s}' if date_s else ''})."
    )
    return current, note, n_support, n_contra


def calibrate_scenario_prob(
    *, prior: float, signals: list[dict], entity_label: str,
    competitive: bool = False,
) -> tuple[Optional[float], Optional[str]]:
    """Pure: re-weight a scenario's prior into a current probability from the
    signals about its target entity. Returns (current_prob, calibration_note),
    or (None, None) when there is no weighted evidence (uncalibrated — honest
    about "no news yet").

    Each weighted signal nudges the running probability by its confidence weight:
    a SUPPORTING signal toward the ceiling, a CONTRADICTING one toward the floor
    (Loop 1 / OQ3 — a rival's setback can now LOWER a competitive-pressure
    scenario, not just fail to raise it). Contradictions are surfaced in the note,
    never averaged away. ``competitive`` marks competitive-pressure scenarios,
    the only framing where a ``negative`` signal is read as a contradiction.
    `signals` arrive oldest-first; the last weighted one is the latest mover."""
    current, note, _, _ = _calibrate(
        prior=prior, signals=signals, entity_label=entity_label,
        competitive=competitive,
    )
    return current, note


# ── DB-backed orchestration ─────────────────────────────────────────

_ENGAGEMENT_SQL = "SELECT asset FROM engagements WHERE id::text = %s"

_SCENARIOS_SQL = """
    SELECT id, name, prior_prob, current_prob, created_at
      FROM scenarios
     WHERE engagement_id::text = %s AND is_archived = FALSE
"""

# Signals about the focal entity that arrived AFTER the scenario was derived.
_SIGNALS_SQL = """
    SELECT id, confidence_tier, impact_tier, headline, direction, created_at
      FROM signals
     WHERE primary_entity_type = %s
       AND primary_entity_id = %s
       AND status IN ('candidate', 'reviewed', 'shipped')
       AND created_at > %s
     ORDER BY created_at ASC
     LIMIT %s
"""

_UPDATE_SQL = """
    UPDATE scenarios
       SET current_prob = %s, calibration_note = %s
     WHERE id::text = %s
"""

_PROB_HISTORY_INSERT_SQL = """
    INSERT INTO scenario_probability_history
        (scenario_id, prev_prob, new_prob, delta, triggering_signal_ids, method, note,
         n_supporting, n_contradicting)
    VALUES (%s, %s, %s, %s, %s::uuid[], %s, %s, %s, %s)
"""


def _record_prob_history(db, scenario_id, prev, new, signal_ids, method, note,
                         n_supporting: int = 0, n_contradicting: int = 0) -> None:
    """Append a probability-change row (Loop 2 / OQ2). ``n_supporting`` /
    ``n_contradicting`` record the STANCE MIX behind the move (OQ3 — a move driven
    by a contradiction is now structured, not buried in the note). Never blocks
    calibration: a missing table or write error is logged, not raised — the audit
    ledger is an enrichment, the calibration UPDATE is the source of truth."""
    delta = (round(float(new) - float(prev), 3)
             if (prev is not None and new is not None) else None)
    try:
        db.execute(_PROB_HISTORY_INSERT_SQL, [
            str(scenario_id), prev, new, delta,
            [str(s) for s in (signal_ids or [])], method, note,
            int(n_supporting), int(n_contradicting),
        ])
    except Exception:
        logger.warning("prob-history write skipped for scenario %s", scenario_id,
                       exc_info=True)


def get_scenario_probability_history(db, scenario_id: str) -> list[dict]:
    """The probability time-series for a scenario, newest first — the
    'why did this move?' answer (as-of / decision-over-time). Each row carries the
    stance mix (n_supporting / n_contradicting) behind that move."""
    try:
        return db.fetch_all(
            "SELECT prev_prob, new_prob, delta, triggering_signal_ids, method, "
            "note, n_supporting, n_contradicting, created_at "
            "FROM scenario_probability_history "
            "WHERE scenario_id::text = %s ORDER BY created_at DESC",
            [str(scenario_id)],
        ) or []
    except Exception:
        logger.warning("prob-history read failed for %s", scenario_id, exc_info=True)
        return []


def latest_stance_mix(db, scenario_id: str) -> dict:
    """Stance mix of a scenario's LATEST probability move — the structured answer
    to "is this scenario currently contradicted?" (OQ3 / dossier ``contradicted``
    readiness state H-d). Returns {n_supporting, n_contradicting, contradicted};
    all-zero / contradicted=False when the scenario has never moved or on error.
    Read-only seam for the API / scenario read-path (Platform / CI surfaces)."""
    try:
        row = db.fetch_one(
            "SELECT n_supporting, n_contradicting FROM scenario_probability_history "
            "WHERE scenario_id::text = %s ORDER BY created_at DESC LIMIT 1",
            [str(scenario_id)],
        )
    except Exception:
        logger.warning("stance-mix read failed for %s", scenario_id, exc_info=True)
        row = None
    n_sup = int((row or {}).get("n_supporting") or 0)
    n_con = int((row or {}).get("n_contradicting") or 0)
    return {"n_supporting": n_sup, "n_contradicting": n_con,
            "contradicted": n_con > 0}


# A competitive-pressure scenario is about a RIVAL ("Competitive pressure:
# tirzepatide"); its probability is corroborated by signals about that rival, NOT
# the focal asset. Other scenarios (signal-driven) are about the focal asset.
_COMPETITIVE_PREFIX = "Competitive pressure:"


def _scenario_target(db, name: str, focal: tuple[str, str], focal_label: str):
    """Resolve the entity whose signals corroborate this scenario.
    Returns (entity_type, entity_id, label) — the rival for competitive-pressure
    scenarios, else the focal asset. Falls back to focal if the rival can't be
    resolved to a distinct entity."""
    nm = (name or "").strip()
    if nm.startswith(_COMPETITIVE_PREFIX):
        rival = nm[len(_COMPETITIVE_PREFIX):].strip()
        if rival:
            rtype, rid = resolve_asset_to_subject(db, rival)
            # Only target the rival if it resolved to a real, distinct entity
            # (resolve returns the raw slug when unmatched).
            if rid and rid != rival and rid != focal[1]:
                return rtype, rid, rival
    return focal[0], focal[1], focal_label


def calibrate_engagement_scenarios(db, engagement_id: str) -> int:
    """Re-weight every live scenario of an engagement from CORROBORATING signals
    about its target entity (the rival for competitive-pressure scenarios, the
    focal asset otherwise). Returns the number of scenarios updated. Idempotent:
    re-running with the same evidence yields the same current_prob/note (it
    recomputes from prior each time, not incrementally)."""
    row = db.fetch_one(_ENGAGEMENT_SQL, [str(engagement_id)])
    if not row or not row.get("asset"):
        return 0
    asset = row["asset"]
    focal_type, focal_id = resolve_asset_to_subject(db, asset)
    if not focal_id:
        return 0
    focal_label = asset.split(":")[-1].strip() or asset

    try:
        scenarios = db.fetch_all(_SCENARIOS_SQL, [str(engagement_id)]) or []
    except Exception:
        logger.exception("calibrate: scenario fetch failed for %s", engagement_id)
        return 0

    updated = 0
    for scn in scenarios:
        t_type, t_id, t_label = _scenario_target(
            db, scn.get("name", ""), (focal_type, focal_id), focal_label,
        )
        try:
            signals = db.fetch_all(
                _SIGNALS_SQL,
                [t_type, t_id, scn.get("created_at"), _MAX_SIGNALS],
            ) or []
        except Exception:
            logger.exception("calibrate: signal fetch failed for scenario %s", scn.get("id"))
            continue
        current, note, n_sup, n_con = _calibrate(
            prior=float(scn.get("prior_prob") or 0.0),
            signals=list(signals),
            entity_label=t_label,
            competitive=(scn.get("name") or "").strip().startswith(_COMPETITIVE_PREFIX),
        )
        prev = scn.get("current_prob")
        prev_r = round(float(prev), 3) if prev is not None else None
        if current is None:
            # No corroborating evidence now. If the scenario carries a stale
            # current_prob from a prior run, clear it back to uncalibrated so the
            # loop stays fully idempotent (reflects today's evidence, not history).
            if prev is not None:
                try:
                    # Record the reversion to uncalibrated BEFORE the clear (OQ2).
                    _record_prob_history(db, scn["id"], prev, None, [],
                                         "evidence_lapsed", None)
                    db.execute(_UPDATE_SQL, [None, None, str(scn["id"])])
                    updated += 1
                except Exception:
                    logger.exception("calibrate: clear failed for scenario %s", scn.get("id"))
            continue
        try:
            # Append a history row only on a genuine change (keeps the ledger
            # idempotent: re-running with the same evidence writes nothing).
            if prev_r != current:
                _record_prob_history(
                    db, scn["id"], prev, current,
                    [s.get("id") for s in signals if s.get("id")],
                    "ewma_calibration", note,
                    n_supporting=n_sup, n_contradicting=n_con,
                )
            db.execute(_UPDATE_SQL, [current, note, str(scn["id"])])
            updated += 1
        except Exception:
            logger.exception("calibrate: update failed for scenario %s", scn.get("id"))
    return updated


def calibrate_all_engagements(db, *, limit: int = 200) -> dict:
    """Scheduler entry point — calibrate scenarios across active engagements.
    Bounded; returns a small stats dict for the runner log."""
    try:
        rows = db.fetch_all(
            "SELECT DISTINCT engagement_id::text AS eid FROM scenarios "
            "WHERE is_archived = FALSE LIMIT %s",
            [limit],
        ) or []
    except Exception:
        logger.exception("calibrate_all: engagement scan failed")
        return {"engagements": 0, "scenarios_updated": 0}

    total = 0
    for r in rows:
        eid = r.get("eid")
        if eid:
            total += calibrate_engagement_scenarios(db, eid)
    return {"engagements": len(rows), "scenarios_updated": total}


# dossier_kb owns the canonical, richness-ranked asset→entity resolver.
from services.dossier_kb import resolve_asset_to_subject  # noqa: E402
