"""Concept Weight Adjuster — telemetry-driven feedback loop for concept weights.

Analyzes query_telemetry to correlate concept activations (via intent)
with response quality metrics (confidence, evidence count).  High-quality
intents boost the weights of their associated concepts; low-quality
intents dampen them.

Designed to run as a scheduled background job (~24h cadence) to
gradually tune the ConceptRegistry without operator intervention.

Usage:
    adjuster = ConceptWeightAdjuster(db, concept_registry)
    report = adjuster.analyze_and_adjust(lookback_days=7)
    logger.info("Adjusted %d concepts", report.concepts_adjusted)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from db import Database
    from services.concept_registry import ConceptRegistry

logger = logging.getLogger(__name__)

# ── Configuration constants ───────────────────────────────────────────

MIN_ACTIVATIONS = 10        # Minimum queries for an intent before adjusting
BOOST_FACTOR = 0.10         # +10% per cycle for high-quality concepts
DAMPEN_FACTOR = 0.10        # -10% per cycle for low-quality concepts
QUALITY_HIGH_THRESHOLD = 0.6   # Above this → "high quality"
QUALITY_LOW_THRESHOLD = 0.4    # Below this → "low quality"
WEIGHT_MIN = 0.1
WEIGHT_MAX = 5.0


# ── Report dataclass ─────────────────────────────────────────────────

@dataclass
class AdjustmentReport:
    """Summary of a single analyze_and_adjust() run.

    Attributes:
        analyzed_queries:   Total query activations analyzed across all intents.
        concepts_adjusted:  Number of concepts whose weights were changed.
        adjustments:        Per-concept detail: name, old_weight, new_weight, reason.
        timestamp:          ISO-8601 timestamp of the run.
    """

    analyzed_queries: int = 0
    concepts_adjusted: int = 0
    adjustments: list[dict] = field(default_factory=list)
    timestamp: str = ""


# ── Main class ────────────────────────────────────────────────────────

class ConceptWeightAdjuster:
    """Analyzes query telemetry and adjusts concept weights accordingly.

    For each intent recorded in query_telemetry over the lookback window:
      1. Compute a quality score from avg confidence and evidence count.
      2. Look up all concepts that match that intent.
      3. If quality is high, boost the concept weight by 10%.
      4. If quality is low, dampen the concept weight by 10%.
      5. Clamp to [0.1, 5.0] and persist via ConceptRegistry.update_weight().

    Adjustments are conservative (10% per cycle) to prevent oscillation.
    A minimum of 10 activations per intent is required for statistical
    significance before any adjustment is made.
    """

    def __init__(self, db: "Database", concept_registry: "ConceptRegistry") -> None:
        self._db = db
        self._registry = concept_registry

    def analyze_and_adjust(self, lookback_days: int = 7) -> AdjustmentReport:
        """Analyze recent query telemetry and adjust concept weights.

        Returns an AdjustmentReport summarizing what was changed.
        """
        report = AdjustmentReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # Step 1: Fetch aggregated telemetry per intent
        intent_stats = self._fetch_intent_stats(lookback_days)
        if not intent_stats:
            return report

        # Step 2: Sum up total analyzed queries
        report.analyzed_queries = sum(row["activation_count"] for row in intent_stats)

        # Step 3: For each intent, evaluate quality and adjust matching concepts
        # Track which concepts have already been adjusted (avoid double-adjusting
        # a concept that matches multiple intents — use the first/strongest signal)
        adjusted_concepts: set[str] = set()

        for row in intent_stats:
            intent = row["intent"]
            activation_count = row["activation_count"]
            avg_confidence = row.get("avg_confidence") or 0.0
            avg_evidence = row.get("avg_evidence_count") or 0.0

            # Skip intents with insufficient data
            if activation_count < MIN_ACTIVATIONS:
                continue

            # Compute quality score: weighted blend of confidence and evidence
            quality = self._compute_quality(avg_confidence, avg_evidence)

            # Determine direction
            if quality >= QUALITY_HIGH_THRESHOLD:
                direction = "boost"
                factor = BOOST_FACTOR
            elif quality <= QUALITY_LOW_THRESHOLD:
                direction = "dampen"
                factor = -DAMPEN_FACTOR
            else:
                # In the neutral zone — no adjustment
                continue

            # Find all concepts matching this intent
            matching = self._registry.list_for_intent(intent)
            for concept in matching:
                if concept.name in adjusted_concepts:
                    continue

                old_weight = concept.weight
                new_weight = old_weight * (1.0 + factor)
                new_weight = max(WEIGHT_MIN, min(WEIGHT_MAX, new_weight))

                # Skip if no meaningful change (e.g. already at boundary)
                if abs(new_weight - old_weight) < 1e-6:
                    continue

                # Apply the adjustment
                self._registry.update_weight(concept.name, round(new_weight, 4))
                adjusted_concepts.add(concept.name)

                report.adjustments.append({
                    "name": concept.name,
                    "old_weight": old_weight,
                    "new_weight": round(new_weight, 4),
                    "reason": (
                        f"{direction} — intent '{intent}' has {activation_count} "
                        f"activations with quality={quality:.2f}"
                    ),
                })

        report.concepts_adjusted = len(report.adjustments)
        return report

    # ── Internal helpers ──────────────────────────────────────────────

    def _fetch_intent_stats(self, lookback_days: int) -> list[dict]:
        """Fetch per-intent aggregated stats from query_telemetry.

        Returns list of dicts with: intent, activation_count,
        avg_confidence, avg_evidence_count.
        """
        try:
            rows = self._db.fetch_all(
                """
                SELECT
                    intent,
                    COUNT(*)::int AS activation_count,
                    AVG(confidence) AS avg_confidence,
                    AVG(evidence_count) AS avg_evidence_count
                FROM query_telemetry
                WHERE intent IS NOT NULL AND intent != ''
                  AND created_at > NOW() - make_interval(days := %s)
                GROUP BY intent
                ORDER BY activation_count DESC
                """,
                [lookback_days],
            )
            return rows or []
        except Exception:
            logger.debug(
                "ConceptWeightAdjuster: failed to fetch telemetry "
                "(table may not exist)",
                exc_info=True,
            )
            return []

    @staticmethod
    def _compute_quality(avg_confidence: float, avg_evidence: float) -> float:
        """Blend confidence and evidence count into a single quality score [0, 1].

        Confidence contributes 70%, evidence saturation contributes 30%.
        Evidence is capped at 10 items for normalization (10+ items = 1.0).
        """
        evidence_norm = min(avg_evidence / 10.0, 1.0) if avg_evidence > 0 else 0.0
        return 0.7 * avg_confidence + 0.3 * evidence_norm
