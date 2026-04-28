"""Trial status-history helpers.

SPEC-016 §7 swimlane A1.3. Used by:
  - The A3.1 CT.gov diff connector — calls build_history_entry() with
    fresh-from-CT.gov values, calls should_append() to skip no-ops, and
    calls diff_summary() to populate the trial_status_change event payload
  - The intel layer's clustering service — reads diff_summary() output
    when assembling Signal context
  - The pattern detector — looks at history length / repeated PCD slips

Three pure functions, no DB I/O, fully unit-testable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TypedDict


class StatusHistoryEntry(TypedDict, total=False):
    status: str
    phase: str | None
    primary_completion_date: str | None  # ISO date YYYY-MM-DD
    observed_at: str                      # ISO datetime with tz
    source_document_id: str | None        # UUID string


def _now_utc_iso() -> str:
    """ISO 8601 with timezone — Postgres-compatible round-trip."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_history_entry(
    *,
    status: str,
    phase: str | None,
    primary_completion_date: str | None,
    source_document_id: str | None,
    observed_at: str | None = None,
) -> StatusHistoryEntry:
    """Construct one history entry. observed_at defaults to NOW UTC."""
    return {
        "status": status,
        "phase": phase,
        "primary_completion_date": primary_completion_date,
        "observed_at": observed_at or _now_utc_iso(),
        "source_document_id": source_document_id,
    }


def _key(entry: dict) -> tuple[str | None, str | None, str | None]:
    """The dedup key for an entry — ignores observed_at + source_doc."""
    return (
        entry.get("status"),
        entry.get("phase"),
        entry.get("primary_completion_date"),
    )


def should_append(
    history: list[dict],
    new_entry: dict,
) -> bool:
    """True iff appending `new_entry` records a meaningful change.

    Rules:
      - If history is empty → True (first observation).
      - If the (status, phase, primary_completion_date) tuple differs from
        the last entry → True.
      - Otherwise → False (no-op observation; don't pollute history).
    """
    if not history:
        return True
    last = history[-1]
    return _key(last) != _key(new_entry)


def _parse_iso_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # Accept YYYY-MM-DD or full ISO
        if "T" in value:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def diff_summary(
    prior: dict | None,
    new: dict,
) -> dict:
    """Structured description of what changed between two history entries.

    Output is consumed by the A3.1 connector to populate the
    `trial_status_change` event payload. Shape:

        {
          "initial": bool,                 # True if prior is None
          "status_changed": bool,
          "prev_status": str | None,
          "new_status": str,
          "phase_changed": bool,
          "prev_phase": str | None,
          "new_phase": str | None,
          "pcd_changed": bool,
          "prev_pcd": str | None,
          "new_pcd": str | None,
          "pcd_slip_days": int | None,    # positive if slipped LATER, negative if earlier
        }
    """
    if prior is None:
        return {
            "initial": True,
            "status_changed": False,
            "prev_status": None,
            "new_status": new["status"],
            "phase_changed": False,
            "prev_phase": None,
            "new_phase": new.get("phase"),
            "pcd_changed": False,
            "prev_pcd": None,
            "new_pcd": new.get("primary_completion_date"),
            "pcd_slip_days": None,
        }

    prev_pcd = prior.get("primary_completion_date")
    new_pcd = new.get("primary_completion_date")
    pcd_slip_days: int | None = None
    if prev_pcd != new_pcd:
        prev_dt = _parse_iso_date(prev_pcd)
        new_dt = _parse_iso_date(new_pcd)
        if prev_dt and new_dt:
            pcd_slip_days = (new_dt - prev_dt).days

    return {
        "initial": False,
        "status_changed": prior.get("status") != new["status"],
        "prev_status": prior.get("status"),
        "new_status": new["status"],
        "phase_changed": prior.get("phase") != new.get("phase"),
        "prev_phase": prior.get("phase"),
        "new_phase": new.get("phase"),
        "pcd_changed": prev_pcd != new_pcd,
        "prev_pcd": prev_pcd,
        "new_pcd": new_pcd,
        "pcd_slip_days": pcd_slip_days,
    }
