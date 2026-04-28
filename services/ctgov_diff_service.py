"""CT.gov diff service — emits trial_status_change events.

SPEC-016 §7 swimlane A3.1 (Cycle 2).

For each fresh CT.gov snapshot we:
  1. Resolve the trial by nct_id (DB lookup against clinical_trials)
  2. Read the trial's status_history JSONB
  3. Build a candidate StatusHistoryEntry from the snapshot
  4. Decide whether to append (services.trial_status_history.should_append)
  5. If empty history → append baseline, no event
  6. If real change → emit market_events row, then append history
  7. If no change → no-op

The service is the only path that writes trial_status_change events;
the connector itself just produces snapshots and hands them off here.

Idempotency: event_hash is SHA-256 over (trial_id, prev_status,
new_status, prev_phase, new_phase, prev_pcd, new_pcd). Re-running
the same snapshot hits ON CONFLICT(event_hash) DO NOTHING and is a
safe no-op. The history-append step also checks should_append so
the JSONB array won't grow on duplicate observations.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Optional

from services.trial_status_history import (
    build_history_entry,
    diff_summary,
    should_append,
)

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
# DiffResult — observable outcome of one snapshot processing
# ────────────────────────────────────────────────────────────────────


@dataclass
class DiffResult:
    event_emitted: bool = False
    history_appended: bool = False
    skipped_reason: Optional[str] = None
    nct_id: Optional[str] = None


# ────────────────────────────────────────────────────────────────────
# SQL — kept as module constants so tests can grep the query shape
# ────────────────────────────────────────────────────────────────────


_TRIAL_SELECT_SQL = """
    SELECT id, nct_id, status_history
    FROM clinical_trials
    WHERE nct_id = %s
    LIMIT 1
"""

_EVENT_INSERT_SQL = """
    INSERT INTO market_events (
        event_type,
        description,
        primary_entity_type,
        primary_entity_id,
        primary_entity_name,
        event_date,
        disclosed_date,
        source_tier,
        trust_score,
        status,
        event_hash,
        source_feed,
        payload,
        source_document_id,
        corroborating_sources
    ) VALUES (
        %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s,
        %s, %s, %s::jsonb, %s, %s::jsonb
    )
    ON CONFLICT (event_hash) DO NOTHING
    RETURNING id
"""

_HISTORY_UPDATE_SQL = """
    UPDATE clinical_trials
    SET status_history = %s::jsonb
    WHERE nct_id = %s
"""


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────


def _normalise_status(s: Optional[str]) -> str:
    return (s or "").strip()


def _coerce_history(raw: Any) -> list[dict]:
    """clinical_trials.status_history may come back as a parsed list,
    a JSON string, or None depending on the driver. Coerce to list."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return list(raw)
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
            if isinstance(decoded, list):
                return decoded
        except json.JSONDecodeError:
            pass
    return []


def _impact_hint(diff: dict) -> str:
    """Heuristic — overridden by B3 scoring later."""
    new_status = diff.get("new_status") or ""
    if "Terminated" in new_status or "Withdrawn" in new_status \
            or "Suspended" in new_status:
        return "high"
    if diff.get("phase_changed"):
        return "medium"
    pcd_slip = diff.get("pcd_slip_days")
    if pcd_slip is not None and abs(pcd_slip) >= 90:
        return "medium"
    return "low"


def _build_description(nct_id: str, diff: dict) -> str:
    parts = []
    if diff.get("status_changed"):
        parts.append(
            f"status {diff.get('prev_status') or '∅'} → "
            f"{diff.get('new_status')}"
        )
    if diff.get("phase_changed"):
        parts.append(
            f"phase {diff.get('prev_phase') or '∅'} → "
            f"{diff.get('new_phase') or '∅'}"
        )
    if diff.get("pcd_changed"):
        slip = diff.get("pcd_slip_days")
        slip_str = ""
        if slip is not None:
            slip_str = f" ({'+' if slip >= 0 else ''}{slip}d)"
        parts.append(
            f"PCD {diff.get('prev_pcd') or '∅'} → "
            f"{diff.get('new_pcd') or '∅'}{slip_str}"
        )
    body = ", ".join(parts) if parts else "metadata change"
    return f"Trial {nct_id}: {body}"


def _compute_event_hash(*, trial_id: str, diff: dict) -> str:
    parts = [
        "trial_status_change",
        trial_id or "",
        diff.get("prev_status") or "",
        diff.get("new_status") or "",
        diff.get("prev_phase") or "",
        diff.get("new_phase") or "",
        diff.get("prev_pcd") or "",
        diff.get("new_pcd") or "",
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _event_date_from_diff(diff: dict) -> date:
    """Event date = the new PCD if PCD changed, otherwise today.

    For status / phase changes we don't have a precise effective date
    from CT.gov, so 'when we observed it' (today, UTC) is the best
    proxy. The actual observed_at lives inside the history entry.
    """
    new_pcd = diff.get("new_pcd")
    if new_pcd and diff.get("pcd_changed") and not diff.get("status_changed") \
            and not diff.get("phase_changed"):
        try:
            return datetime.fromisoformat(new_pcd).date()
        except ValueError:
            pass
    return datetime.now(timezone.utc).date()


# ────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────


def process_trial_snapshot(
    *,
    snapshot: dict,
    db: Any,
    source_document_id: Optional[str] = None,
) -> DiffResult:
    """Diff a fresh CT.gov snapshot against stored history.

    Args:
      snapshot: dict with keys nct_id, overall_status, phase,
        primary_completion_date. Other CT.gov fields are ignored.
      db: object with fetch_one(sql, params) and execute(sql, params).
      source_document_id: optional UUID linking this observation to
        a source_records row.

    Returns:
      DiffResult describing what happened.
    """
    nct_id = snapshot.get("nct_id")
    if not nct_id:
        return DiffResult(skipped_reason="missing_nct_id")

    row = db.fetch_one(_TRIAL_SELECT_SQL, [nct_id])
    if not row:
        return DiffResult(nct_id=nct_id, skipped_reason="trial_not_found")

    trial_id = str(row.get("id") or "")
    history = _coerce_history(row.get("status_history"))

    new_entry = build_history_entry(
        status=_normalise_status(snapshot.get("overall_status")),
        phase=snapshot.get("phase"),
        primary_completion_date=snapshot.get("primary_completion_date"),
        source_document_id=source_document_id,
    )

    if not should_append(history, new_entry):
        return DiffResult(nct_id=nct_id, skipped_reason="no_change")

    prior = history[-1] if history else None
    diff = diff_summary(prior, new_entry)

    # ---- Append history first (always, when should_append=True) -----
    new_history = list(history) + [new_entry]
    db.execute(_HISTORY_UPDATE_SQL, [json.dumps(new_history), nct_id])

    # ---- Emit event ONLY for real changes (not initial baseline) -----
    if diff.get("initial"):
        return DiffResult(
            nct_id=nct_id,
            history_appended=True,
            event_emitted=False,
        )

    payload = {
        "nct_id": nct_id,
        "status_changed": diff.get("status_changed", False),
        "prev_status": diff.get("prev_status"),
        "new_status": diff.get("new_status"),
        "phase_changed": diff.get("phase_changed", False),
        "prev_phase": diff.get("prev_phase"),
        "new_phase": diff.get("new_phase"),
        "pcd_changed": diff.get("pcd_changed", False),
        "prev_pcd": diff.get("prev_pcd"),
        "new_pcd": diff.get("new_pcd"),
        "pcd_slip_days": diff.get("pcd_slip_days"),
        "impact_hint": _impact_hint(diff),
    }

    event_params = [
        "trial_status_change",                  # event_type
        _build_description(nct_id, diff),       # description
        "trial",                                # primary_entity_type
        trial_id,                               # primary_entity_id
        nct_id,                                 # primary_entity_name
        _event_date_from_diff(diff),            # event_date
        datetime.now(timezone.utc).date(),      # disclosed_date
        "tier_1",                               # source_tier (CT.gov = tier 1)
        0.95,                                   # trust_score
        "new",                                  # status
        _compute_event_hash(trial_id=trial_id, diff=diff),
        "ctgov_diff_service",                   # source_feed
        json.dumps(payload),                    # payload (cast ::jsonb)
        source_document_id,                     # source_document_id
        json.dumps([]),                         # corroborating_sources
    ]
    inserted = db.fetch_one(_EVENT_INSERT_SQL, event_params)
    event_emitted = inserted is not None

    return DiffResult(
        nct_id=nct_id,
        history_appended=True,
        event_emitted=event_emitted,
    )
