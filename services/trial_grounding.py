"""Grounded trial answers (Loop H2).

The chat synthesizer answered "What Phase 3 trials does semaglutide have?" with
"three" when the substrate holds 58 — because the question was routed to a
narrative/RAG path that retrieved a few trial blurbs instead of counting the
``clinical_trials`` registry. This module produces a small, authoritative,
CITABLE grounding block (counts by phase + the notable trials with NCT IDs +
an as-of stamp) that is injected into the LLM context so any path answers from
ground truth, with citations, and is told not to under-report.

Grounds directly on the ``clinical_trials`` table (the registry of record), so
it is independent of the facts-ledger temporal model. Pure helpers
(``summarize_phases``, ``format_grounding_block``) are DB-free and unit-tested;
only ``trial_grounding`` touches the DB.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

# Active rows only: exclude soft-deleted/superseded trial records.
_PHASE_COUNT_SQL = """
    SELECT COALESCE(NULLIF(TRIM(phase), ''), 'Not specified') AS phase, COUNT(*) AS n
      FROM clinical_trials
     WHERE drug_id = %s
       AND record_status IS DISTINCT FROM 'superseded'
       AND record_status IS DISTINCT FROM 'merged'
     GROUP BY 1
"""

# Notable trials: prefer later-phase, larger, with a title — the ones worth citing.
_NOTABLE_SQL = """
    SELECT id, phase, status, official_title,
           COALESCE(actual_enrollment, enrollment_target) AS enrollment, source_url
      FROM clinical_trials
     WHERE drug_id = %s
       AND record_status IS DISTINCT FROM 'superseded'
       AND record_status IS DISTINCT FROM 'merged'
       AND phase ILIKE %s
     ORDER BY COALESCE(actual_enrollment, enrollment_target, 0) DESC NULLS LAST
     LIMIT %s
"""


def _is_phase3(phase: str) -> bool:
    """True for any phase string that includes Phase 3 (incl. 'Phase 2, Phase 3')."""
    return "3" in (phase or "")


def summarize_phases(rows: list[dict]) -> dict:
    """Pure: fold ``[{phase, n}]`` into a grounding summary.

    Returns ``{total, by_phase (sorted desc), phase3_total}``. ``phase3_total``
    counts every bucket whose phase mentions 3 (so 'Phase 2, Phase 3' is
    included once) — the figure a 'how many Phase 3 trials' question needs.
    """
    by_phase: dict[str, int] = {}
    for r in rows:
        phase = (r.get("phase") or "Not specified").strip() or "Not specified"
        by_phase[phase] = by_phase.get(phase, 0) + int(r.get("n") or 0)
    total = sum(by_phase.values())
    phase3_total = sum(n for p, n in by_phase.items() if _is_phase3(p))
    ordered = dict(sorted(by_phase.items(), key=lambda kv: kv[1], reverse=True))
    return {"total": total, "by_phase": ordered, "phase3_total": phase3_total}


def _short_title(title: Optional[str], limit: int = 70) -> str:
    t = (title or "").strip()
    return (t[: limit - 1] + "…") if len(t) > limit else t


def format_grounding_block(summary: dict, notable: list[dict], *,
                           drug_name: str, as_of: datetime) -> str:
    """Pure: render the context block the synthesizer must ground on.

    Fails honest: with zero trials it states that plainly (no invented trials)."""
    stamp = as_of.date().isoformat()
    total = summary.get("total", 0)
    if total == 0:
        return (f"GROUNDED TRIAL DATA for {drug_name} (clinical_trials registry, "
                f"as of {stamp}): no trials on record for this drug. Do not invent "
                f"trials; say none are on record.")
    by = summary.get("by_phase", {})
    breakdown = ", ".join(f"{p}: {n}" for p, n in by.items())
    lines = [
        f"GROUNDED TRIAL DATA for {drug_name} (clinical_trials registry, as of {stamp}):",
        f"Total {total} trials on record — {breakdown}.",
        f"Phase 3 (incl. combined Phase 2/3): {summary.get('phase3_total', 0)}.",
    ]
    if notable:
        cites = "; ".join(
            f"{n.get('id')} ({_short_title(n.get('official_title'))}"
            + (f", {n['status']}" if n.get("status") else "")
            + (f", n={int(n['enrollment']):,}" if n.get("enrollment") else "")
            + ")"
            for n in notable
        )
        lines.append(f"Notable Phase-3 trials by enrollment: {cites}.")
    lines.append("Use these exact counts; do NOT under-report. Only the top "
                 f"{len(notable)} trials are listed — if a full list is asked, say so.")
    return "\n".join(lines)


def trial_grounding(db, drug_id: str, *, drug_name: str = "this drug",
                    top_n: int = 8, as_of: Optional[datetime] = None) -> dict:
    """Authoritative, citable trial grounding for ``drug_id``.

    Returns ``{summary, notable, block, as_of}``. ``block`` is the ready-to-inject
    LLM context string. Empty/zero-trial drugs yield an honest 'none on record'
    block rather than nothing."""
    as_of = as_of or datetime.now(timezone.utc)
    phase_rows = db.fetch_all(_PHASE_COUNT_SQL, [str(drug_id)])
    summary = summarize_phases(phase_rows)
    notable: list[dict] = []
    if summary["phase3_total"] > 0:
        notable = db.fetch_all(_NOTABLE_SQL, [str(drug_id), "%3%", int(top_n)])
    block = format_grounding_block(summary, notable, drug_name=drug_name, as_of=as_of)
    return {"summary": summary, "notable": notable, "block": block,
            "as_of": as_of.isoformat()}
