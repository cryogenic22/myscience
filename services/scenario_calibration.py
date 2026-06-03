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

from services.learning_service import ewma_update

logger = logging.getLogger(__name__)

# Per-signal support level the scenario's probability is pulled toward, by the
# signal's confidence tier. A confirmed development is strong corroboration; a
# disputed one barely moves the needle. These are the EWMA observations.
OBSERVATION_BY_CONFIDENCE: dict[str, float] = {
    "confirmed": 0.90,
    "reported": 0.72,
    "inferred": 0.58,
    "disputed": 0.45,
}
_DEFAULT_OBS = 0.58

# How hard each signal pulls the running probability. Modest so a single signal
# never swings a scenario wildly; evidence accumulates over many.
_ALPHA = 0.25

_FLOOR, _CEIL = 0.05, 0.95
_MAX_SIGNALS = 50  # bound the per-scenario evidence window


def _obs(confidence_tier: Optional[str]) -> float:
    return OBSERVATION_BY_CONFIDENCE.get((confidence_tier or "").lower(), _DEFAULT_OBS)


def calibrate_scenario_prob(
    *, prior: float, signals: list[dict], entity_label: str,
) -> tuple[Optional[float], Optional[str]]:
    """Pure: re-weight a scenario's prior into a current probability from the
    corroborating signals. Returns (current_prob, calibration_note), or
    (None, None) when there is no new evidence (scenario stays uncalibrated).

    `signals` are dicts with confidence_tier / headline / created_at, expected
    pre-filtered to those that arrived AFTER the scenario was derived, newest
    last (the last one is cited as the latest mover).
    """
    if not signals:
        return None, None

    current: Optional[float] = prior
    for sig in signals[:_MAX_SIGNALS]:
        current = ewma_update(prior=current, observation=_obs(sig.get("confidence_tier")), alpha=_ALPHA)

    current = round(max(_FLOOR, min(_CEIL, float(current))), 3)

    latest = signals[-1]
    n = len(signals)
    headline = (latest.get("headline") or "").strip()
    conf = (latest.get("confidence_tier") or "unrated")
    date = (latest.get("created_at") or "")
    date_s = str(date)[:10]
    note = (
        f"{n} signal{'s' if n != 1 else ''} on {entity_label} since derivation "
        f"re-weighted this scenario (prior {round(prior, 2)} → {current}). "
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
    SELECT id, confidence_tier, impact_tier, headline, created_at
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


def calibrate_engagement_scenarios(db, engagement_id: str) -> int:
    """Re-weight every live scenario of an engagement from signals about its
    focal entity. Returns the number of scenarios updated. Idempotent: re-running
    with the same evidence yields the same current_prob/note (it recomputes from
    prior each time, not incrementally)."""
    row = db.fetch_one(_ENGAGEMENT_SQL, [str(engagement_id)])
    if not row or not row.get("asset"):
        return 0
    asset = row["asset"]
    entity_type, entity_id = resolve_asset_to_subject(db, asset)
    if not entity_id:
        return 0
    entity_label = asset.split(":")[-1].strip() or asset

    try:
        scenarios = db.fetch_all(_SCENARIOS_SQL, [str(engagement_id)]) or []
    except Exception:
        logger.exception("calibrate: scenario fetch failed for %s", engagement_id)
        return 0

    updated = 0
    for scn in scenarios:
        try:
            signals = db.fetch_all(
                _SIGNALS_SQL,
                [entity_type, entity_id, scn.get("created_at"), _MAX_SIGNALS],
            ) or []
        except Exception:
            logger.exception("calibrate: signal fetch failed for scenario %s", scn.get("id"))
            continue
        current, note = calibrate_scenario_prob(
            prior=float(scn.get("prior_prob") or 0.0),
            signals=list(signals),
            entity_label=entity_label,
        )
        if current is None:
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
