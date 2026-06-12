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

# How much each signal moves the scenario's probability, by confidence tier. This
# is an EVIDENCE weight, not a probability anchor: a disputed signal contributes
# nothing (we do not let unconfirmed/contested news move a scenario), a confirmed
# one fully. The same weight scales BOTH directions — corroboration pulls toward
# the ceiling, refutation toward the floor (see ``signal_stance``).
CORROBORATION_WEIGHT: dict[str, float] = {
    "confirmed": 1.0,
    "reported": 0.65,
    "inferred": 0.35,
    "disputed": 0.0,
}
_DEFAULT_WEIGHT = 0.35

# How hard a fully-weighted signal pulls toward its bound. Modest, so a single
# signal never swings a scenario wildly; evidence accumulates over many.
_ALPHA = 0.30

_CEIL = 0.95
_FLOOR = 0.05
_MAX_SIGNALS = 50  # bound the per-scenario evidence window

# Backwards-compatible alias for any external reader of the old name.
OBSERVATION_BY_CONFIDENCE = CORROBORATION_WEIGHT

# Helix gap #3 — scenario-relative stance. A scenario's probability should not
# only rise on corroboration; a signal pointing the OTHER way must be able to
# refute it ("contradictions are often the insight"). Stance is grounded in the
# signals.direction column (positive/negative/neutral — DB-checked), not guessed.
SUPPORTS = "supports"
CONTRADICTS = "contradicts"
NEUTRAL = "neutral"


def signal_stance(direction: Optional[str], *, scenario_is_competitive: bool) -> str:
    """Stance of one signal toward a scenario — grounded in ``signals.direction``.

    A *competitive-pressure* scenario is about a RIVAL; it materialises when the
    rival gets STRONGER. So a NEGATIVE rival signal (trial failure, regulatory
    setback, supply disruption) CONTRADICTS it — the rival weakened, pressure
    recedes. That is the one new, well-grounded refutation case (Helix gap #3).

    Everything else stays SUPPORTS — identical to the pre-stance behaviour, so
    there is no regression: a positive/neutral/unknown rival signal still
    accumulates evidence, and focal-asset (non-competitive) scenarios, for which
    we have no reliable polarity model yet, treat every signal as corroboration.
    """
    if scenario_is_competitive and (direction or "").lower() == "negative":
        return CONTRADICTS
    return SUPPORTS


def _weight(confidence_tier: Optional[str]) -> float:
    return CORROBORATION_WEIGHT.get((confidence_tier or "").lower(), _DEFAULT_WEIGHT)


def calibrate_scenario_prob(
    *, prior: float, signals: list[dict], entity_label: str,
) -> tuple[Optional[float], Optional[str]]:
    """Pure: re-weight a scenario's prior into a current probability from the
    signals about its target entity, by their STANCE. Returns (current_prob,
    calibration_note), or (None, None) when no weighted, non-neutral signal
    applies (scenario stays uncalibrated — honest about "no news yet").

    Each signal nudges the running probability proportionally to its confidence
    weight: a SUPPORTS signal toward the ceiling, a CONTRADICTS signal toward the
    floor (Helix gap #3 — refutation). Stance comes from ``s['stance']``; absent,
    it defaults to SUPPORTS, so a caller that never sets stance gets the exact
    pre-stance behaviour. `signals` are expected pre-filtered to those that
    arrived AFTER derivation, oldest first; the last mover is cited.
    """
    movers = [
        s for s in signals
        if _weight(s.get("confidence_tier")) > 0
        and s.get("stance", SUPPORTS) in (SUPPORTS, CONTRADICTS)
    ]
    if not movers:
        return None, None

    current = float(prior)
    n_sup = n_con = 0
    for sig in movers[:_MAX_SIGNALS]:
        w = _weight(sig.get("confidence_tier"))
        if sig.get("stance", SUPPORTS) == CONTRADICTS:
            current = current - w * _ALPHA * (current - _FLOOR)  # toward floor
            n_con += 1
        else:
            current = current + w * _ALPHA * (_CEIL - current)   # toward ceiling
            n_sup += 1

    current = round(min(_CEIL, max(_FLOOR, current)), 3)

    latest = movers[-1]
    n = len(movers)
    headline = (latest.get("headline") or "").strip()
    conf = (latest.get("confidence_tier") or "unrated")
    date_s = str(latest.get("created_at") or "")[:10]
    moved = "raised" if current >= round(prior, 3) else "lowered"
    mix = (f"{n_sup} corroborating" + (f", {n_con} contradicting" if n_con else "")) \
        if n_sup else f"{n_con} contradicting"
    note = (
        f"{mix} signal{'s' if n != 1 else ''} on {entity_label} since derivation "
        f"{moved} this scenario from {round(prior, 2)} to {current}. "
        f"Latest: \"{headline}\" ({conf}{f', {date_s}' if date_s else ''})."
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
    SELECT id, confidence_tier, impact_tier, direction, headline, created_at
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
        # Stance per signal (Helix gap #3). Only a competitive-pressure scenario
        # whose target resolved to a DISTINCT rival gets directional refutation;
        # if it fell back to the focal asset, polarity is unknown → treat as
        # non-competitive (every signal supports — no wrong-direction refutation).
        is_competitive = (
            (scn.get("name") or "").strip().startswith(_COMPETITIVE_PREFIX)
            and t_id != focal_id
        )
        signals = [
            {**dict(s),
             "stance": signal_stance(s.get("direction"),
                                     scenario_is_competitive=is_competitive)}
            for s in signals
        ]
        current, note = calibrate_scenario_prob(
            prior=float(scn.get("prior_prob") or 0.0),
            signals=signals,
            entity_label=t_label,
        )
        if current is None:
            # No corroborating evidence now. If the scenario carries a stale
            # current_prob from a prior run, clear it back to uncalibrated so the
            # loop stays fully idempotent (reflects today's evidence, not history).
            if scn.get("current_prob") is not None:
                try:
                    db.execute(_UPDATE_SQL, [None, None, str(scn["id"])])
                    updated += 1
                except Exception:
                    logger.exception("calibrate: clear failed for scenario %s", scn.get("id"))
            continue
        try:
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
