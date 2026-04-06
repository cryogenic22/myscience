"""Proactive Insight Engine — detects actionable intelligence signals.

Scans materialized views and recent data changes to surface:
1. Safety signals — disproportionality spikes (PRR > 2.0) from FAERS data
2. Pipeline milestones — phase advancements and trial completions
3. Competitive shifts — new entrants and HHI concentration changes

Usage:
    engine = InsightEngine(db)
    insights = engine.scan(since_days=7)
    # → list[Insight] sorted by severity (critical first)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from db import Database

logger = logging.getLogger(__name__)


# ── Data types ────────────────────────────────────────────────────

@dataclass
class Insight:
    """A proactive intelligence signal."""
    type: str                   # "safety_signal", "pipeline_milestone", "competitive_shift"
    severity: str               # "critical", "high", "medium", "low"
    title: str                  # human-readable headline
    description: str            # detail paragraph
    entity_name: str | None     # affected drug/company
    entity_type: str | None
    metric_value: float | None  # e.g., PRR score, HHI delta
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ── Severity ranking ─────────────────────────────────────────────

_SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def _severity_rank(severity: str) -> int:
    """Return numeric rank for sorting (higher = more severe)."""
    return _SEVERITY_ORDER.get(severity, 0)


# ── Engine ────────────────────────────────────────────────────────

class InsightEngine:
    """Detects proactive intelligence signals from data changes."""

    def __init__(self, db: Database):
        self.db = db

    def scan(self, since_days: int = 7) -> list[Insight]:
        """Scan for all types of actionable signals.

        Returns insights sorted by severity (critical first).
        """
        insights: list[Insight] = []
        insights.extend(self._detect_safety_signals())
        insights.extend(self._detect_pipeline_milestones(since_days))
        insights.extend(self._detect_competitive_shifts())
        insights.extend(self._detect_resolution_queue_overflow())
        return sorted(insights, key=lambda x: _severity_rank(x.severity), reverse=True)

    # ── Safety signals ────────────────────────────────────────────

    def _detect_safety_signals(self) -> list[Insight]:
        """Check mv_safety_signals for high PRR/ROR disproportionality signals.

        Only surfaces signals where PRR > 2.0, which is the standard
        pharmacovigilance threshold for a meaningful signal.
        """
        insights: list[Insight] = []
        try:
            rows = self.db.fetch_all(
                """
                SELECT drug_name, drug_id, reaction, prr, ror, ror_lower_ci,
                       a AS case_count, drug_total
                FROM mv_safety_signals
                WHERE prr > 2.0
                ORDER BY prr DESC
                LIMIT 20
                """
            )
            for row in rows:
                prr = row.get("prr") or 0
                ror_lower = row.get("ror_lower_ci") or 0
                case_count = row.get("case_count") or row.get("a") or 0
                drug_name = row.get("drug_name", "Unknown")
                reaction = row.get("reaction", "Unknown reaction")

                # Severity based on PRR magnitude and CI significance
                if prr > 5.0 and ror_lower > 1.0:
                    severity = "critical"
                elif prr > 3.0:
                    severity = "high"
                elif prr > 2.0:
                    severity = "medium"
                else:
                    continue  # shouldn't happen given WHERE clause

                insights.append(Insight(
                    type="safety_signal",
                    severity=severity,
                    title=f"Safety signal: {drug_name} — {reaction}",
                    description=(
                        f"{drug_name} shows disproportionate reporting for {reaction} "
                        f"(PRR={prr:.1f}, {case_count} cases out of {row.get('drug_total', '?')} total reports). "
                        f"ROR lower 95% CI: {ror_lower:.2f}."
                    ),
                    entity_name=drug_name,
                    entity_type="drug",
                    metric_value=prr,
                ))
        except Exception:
            logger.debug("Failed to detect safety signals", exc_info=True)

        return insights

    # ── Pipeline milestones ───────────────────────────────────────

    def _detect_pipeline_milestones(self, since_days: int) -> list[Insight]:
        """Detect phase advancements and trial completions.

        Queries clinical_trials joined with drugs for recently updated
        trials that have reached notable status changes.
        """
        insights: list[Insight] = []
        try:
            rows = self.db.fetch_all(
                """
                SELECT d.generic_name, d.id::text AS drug_id,
                       ct.id AS trial_id, ct.phase, ct.status,
                       ct.updated_at,
                       lag(ct.phase) OVER (
                           PARTITION BY ct.drug_id ORDER BY ct.start_date
                       ) AS previous_phase
                FROM clinical_trials ct
                JOIN drugs d ON ct.drug_id = d.id
                WHERE ct.updated_at > NOW() - make_interval(days := %s)
                  AND ct.status IN ('COMPLETED', 'ACTIVE_NOT_RECRUITING', 'RECRUITING')
                  AND d.record_status IS DISTINCT FROM 'excluded'
                ORDER BY ct.updated_at DESC
                LIMIT 50
                """,
                [since_days],
            )
            for row in rows:
                drug_name = row.get("generic_name") or "Unknown drug"
                phase = row.get("phase") or "Unknown"
                status = row.get("status") or ""
                trial_id = row.get("trial_id") or ""
                prev_phase = row.get("previous_phase")

                if status == "COMPLETED":
                    insights.append(Insight(
                        type="pipeline_milestone",
                        severity="high" if "3" in phase else "medium",
                        title=f"Trial completed: {drug_name} ({phase})",
                        description=(
                            f"{drug_name} trial {trial_id} has completed {phase}. "
                            f"This may indicate progression toward regulatory filing."
                        ),
                        entity_name=drug_name,
                        entity_type="drug",
                        metric_value=_phase_numeric(phase),
                    ))
                elif prev_phase and _phase_numeric(phase) > _phase_numeric(prev_phase):
                    insights.append(Insight(
                        type="pipeline_milestone",
                        severity="high" if "3" in phase else "medium",
                        title=f"Phase advancement: {drug_name} → {phase}",
                        description=(
                            f"{drug_name} has advanced from {prev_phase} to {phase} "
                            f"(trial {trial_id}). Pipeline progression signals growing confidence."
                        ),
                        entity_name=drug_name,
                        entity_type="drug",
                        metric_value=_phase_numeric(phase),
                    ))
        except Exception:
            logger.debug("Failed to detect pipeline milestones", exc_info=True)

        return insights

    # ── Competitive shifts ────────────────────────────────────────

    def _detect_competitive_shifts(self) -> list[Insight]:
        """Detect new market entrants and HHI concentration changes.

        Checks for:
        1. New drugs (created recently) in existing mechanism+TA segments
        2. Significant HHI index changes across segments
        """
        insights: list[Insight] = []

        # 1. New entrants
        try:
            rows = self.db.fetch_all(
                """
                SELECT d.generic_name AS drug_name, d.id::text AS drug_id,
                       m.name AS mechanism_name,
                       ta.name AS therapeutic_area,
                       d.created_at,
                       COUNT(*) OVER (PARTITION BY m.id, ta.id) AS segment_drug_count
                FROM drugs d
                JOIN mechanisms_of_action m ON d.mechanism_id = m.id
                JOIN therapeutic_areas ta ON d.therapeutic_area_id = ta.id
                WHERE d.created_at > NOW() - INTERVAL '30 days'
                  AND d.record_status IS DISTINCT FROM 'excluded'
                  AND d.record_status IS DISTINCT FROM 'merged'
                ORDER BY d.created_at DESC
                LIMIT 20
                """
            )
            for row in rows:
                drug_name = row.get("drug_name") or "Unknown"
                mechanism = row.get("mechanism_name") or "Unknown"
                ta = row.get("therapeutic_area") or "Unknown"
                seg_count = row.get("segment_drug_count") or 1

                insights.append(Insight(
                    type="competitive_shift",
                    severity="high" if seg_count <= 3 else "medium",
                    title=f"New entrant: {drug_name} in {mechanism}",
                    description=(
                        f"{drug_name} has entered the {mechanism} segment "
                        f"({ta}). There are now {seg_count} drugs in this segment."
                    ),
                    entity_name=drug_name,
                    entity_type="drug",
                    metric_value=float(seg_count),
                ))
        except Exception:
            logger.debug("Failed to detect new entrants", exc_info=True)

        # 2. HHI concentration shifts
        try:
            rows = self.db.fetch_all(
                """
                WITH segment_counts AS (
                    SELECT
                        m.name AS mechanism_name,
                        ta.name AS therapeutic_area,
                        COUNT(DISTINCT d.id) AS current_drug_count,
                        COUNT(DISTINCT d.id) FILTER (
                            WHERE d.created_at < NOW() - INTERVAL '30 days'
                        ) AS previous_drug_count
                    FROM drugs d
                    JOIN mechanisms_of_action m ON d.mechanism_id = m.id
                    JOIN therapeutic_areas ta ON d.therapeutic_area_id = ta.id
                    WHERE d.record_status IS DISTINCT FROM 'excluded'
                      AND d.record_status IS DISTINCT FROM 'merged'
                    GROUP BY m.name, ta.name
                    HAVING COUNT(DISTINCT d.id) >= 3
                )
                SELECT mechanism_name, therapeutic_area,
                       current_drug_count, previous_drug_count,
                       -- Simplified HHI: (10000 / N) approximation for equal shares
                       CASE WHEN current_drug_count > 0
                            THEN (10000.0 / current_drug_count)
                            ELSE 10000 END AS hhi_current,
                       CASE WHEN previous_drug_count > 0
                            THEN (10000.0 / previous_drug_count)
                            ELSE 10000 END AS hhi_previous,
                       CASE WHEN previous_drug_count > 0
                            THEN (10000.0 / current_drug_count) - (10000.0 / previous_drug_count)
                            ELSE 0 END AS hhi_delta
                FROM segment_counts
                WHERE previous_drug_count > 0
                  AND ABS(
                      (10000.0 / current_drug_count) - (10000.0 / previous_drug_count)
                  ) > 200
                ORDER BY ABS(
                    (10000.0 / current_drug_count) - (10000.0 / previous_drug_count)
                ) DESC
                LIMIT 10
                """
            )
            for row in rows:
                mechanism = row.get("mechanism_name") or "Unknown"
                ta = row.get("therapeutic_area") or "Unknown"
                hhi_delta = row.get("hhi_delta") or 0
                current_count = row.get("current_drug_count") or 0
                prev_count = row.get("previous_drug_count") or 0

                direction = "decreased" if hhi_delta < 0 else "increased"
                severity = "high" if abs(hhi_delta) > 500 else "medium"

                insights.append(Insight(
                    type="competitive_shift",
                    severity=severity,
                    title=f"Market concentration {direction}: {mechanism} ({ta})",
                    description=(
                        f"The {mechanism} segment in {ta} saw market concentration "
                        f"{direction} by {abs(hhi_delta):.0f} HHI points "
                        f"(drug count: {prev_count} → {current_count})."
                    ),
                    entity_name=mechanism,
                    entity_type="mechanism",
                    metric_value=hhi_delta,
                ))
        except Exception:
            logger.debug("Failed to detect HHI shifts", exc_info=True)

        return insights

    # ── Resolution queue overflow ────────────────────────────────

    def _detect_resolution_queue_overflow(self) -> list[Insight]:
        """Check the HITL review queue for pending unresolved entities.

        Fires a signal when the pending count exceeds 50 items,
        indicating the entity resolution pipeline needs attention.
        """
        try:
            row = self.db.fetch_one(
                "SELECT COUNT(*) AS cnt FROM hitl_reviews WHERE status = 'pending'"
            )
            count = row["cnt"] if row else 0

            if count <= 50:
                return []

            severity = "high" if count > 100 else "medium"

            return [Insight(
                type="resolution_queue_overflow",
                severity=severity,
                title=f"Entity resolution queue has {count} pending items",
                description=(
                    f"Entity resolution queue has {count} pending items — review needed. "
                    f"Visit /catalog/hitl to triage unresolved entities."
                ),
                entity_name=None,
                entity_type=None,
                metric_value=float(count),
            )]
        except Exception:
            logger.debug("Failed to detect resolution queue overflow", exc_info=True)
            return []


# ── Helpers ───────────────────────────────────────────────────────

def _phase_numeric(phase: str | None) -> float:
    """Convert trial phase string to numeric for comparison.

    Phase 1 → 1, Phase 2 → 2, Phase 3 → 3, Phase 4 → 4.
    Intermediate phases (e.g., Phase 1/Phase 2) map to 1.5.
    """
    if not phase:
        return 0
    phase = phase.lower()
    if "1/phase 2" in phase or "1/2" in phase:
        return 1.5
    if "2/phase 3" in phase or "2/3" in phase:
        return 2.5
    if "4" in phase:
        return 4.0
    if "3" in phase:
        return 3.0
    if "2" in phase:
        return 2.0
    if "1" in phase:
        return 1.0
    return 0.5  # Early Phase 1, Not Applicable, etc.
