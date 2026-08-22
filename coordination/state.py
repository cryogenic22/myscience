"""Closed work-item state machine for the TIV2 controller."""

from __future__ import annotations

from .model import Violation


STATES = {
    "planned",
    "claimed",
    "red",
    "building",
    "green_local",
    "ci",
    "review_ready",
    "changes_required",
    "approved",
    "merged",
    "observed",
    "closed",
    "blocked",
    "cancelled",
}
ACTIVE_STATES = {
    "claimed",
    "red",
    "building",
    "green_local",
    "ci",
    "review_ready",
    "changes_required",
    "approved",
    "blocked",
}
DEPENDENCY_COMPLETE_STATES = {"observed", "closed"}
REVIEWABLE_STATES = {"ci", "review_ready"}
REVIEW_EVIDENCE_STATES = {
    "ci",
    "review_ready",
    "changes_required",
    "approved",
    "merged",
    "observed",
    "closed",
}
TERMINAL_PROOF_STATES = {"merged", "observed", "closed"}
REVIEW_VERDICTS = {"APPROVE", "CHANGES-REQUIRED"}
NORMAL_TRANSITIONS = {
    "planned": {"claimed", "blocked"},
    "claimed": {"red", "blocked"},
    "red": {"building", "blocked"},
    "building": {"green_local", "blocked"},
    "green_local": {"ci", "building", "blocked"},
    "ci": {"review_ready", "building", "blocked"},
    "review_ready": {"changes_required", "approved", "building", "blocked"},
    "changes_required": {"building", "blocked"},
    "approved": {"merged", "building", "blocked"},
    "merged": {"observed"},
    "observed": {"closed"},
    "closed": set(),
    "cancelled": set(),
}


def transition_violations(
    item_id: str,
    from_state: str,
    to_state: str,
    *,
    actor_role: str,
    blocked_from_state: str | None = None,
) -> list[Violation]:
    """Validate one controller-applied state transition."""

    if from_state not in STATES or to_state not in STATES:
        return [
            Violation("INVALID_STATE", item_id, f"{from_state!r} -> {to_state!r}")
        ]

    out: list[Violation] = []
    if to_state == "cancelled":
        if actor_role != "controller-owner":
            out.append(
                Violation(
                    "OWNER_ONLY_CANCELLATION",
                    item_id,
                    "cancellation needs owner-authorized controller identity",
                )
            )
        if from_state in {"closed", "cancelled"}:
            out.append(
                Violation(
                    "INVALID_TRANSITION",
                    item_id,
                    f"cannot cancel terminal state {from_state}",
                )
            )
        return sorted(set(out))

    if actor_role != "controller":
        out.append(
            Violation(
                "UNTRUSTED_STATE_ACTOR",
                item_id,
                "only the controller applies state transitions",
            )
        )
    if from_state == "blocked":
        if blocked_from_state not in STATES or blocked_from_state in {
            "blocked",
            "closed",
            "cancelled",
        }:
            out.append(
                Violation(
                    "INVALID_RESUME_STATE",
                    item_id,
                    "blocked resume must restore its recorded actionable state",
                )
            )
        elif to_state != blocked_from_state:
            out.append(
                Violation(
                    "INVALID_TRANSITION",
                    item_id,
                    f"blocked item must resume to {blocked_from_state}, not {to_state}",
                )
            )
        return sorted(set(out))

    if to_state not in NORMAL_TRANSITIONS.get(from_state, set()):
        out.append(
            Violation(
                "INVALID_TRANSITION",
                item_id,
                f"{from_state} -> {to_state} is not allowed",
            )
        )
    return sorted(set(out))
