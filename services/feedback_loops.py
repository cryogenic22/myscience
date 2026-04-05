"""Feedback Loops — three closed loops connecting user behaviour to system improvement.

Loop 1: Query Patterns → Concept Weighting
    When users frequently ask about certain intents, the relevant concepts
    should be weighted higher in the ConceptRegistry.

Loop 2: Entity Resolution Failures → Ontology Expansion
    When entity resolution fails repeatedly for the same terms, propose
    ontology additions (aliases, new entity entries).

Loop 3: Answer Quality → Prompt Optimization
    Track which response patterns get low confidence and flag them for
    prompt improvement.

Usage:
    orch = FeedbackLoopOrchestrator(db)
    result = orch.run(since_days=7, dry_run=True)
    # result = {"actions": [...], "summary": {...}, "dry_run": True}
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from db import Database

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────

QUERY_COUNT_THRESHOLD = 10          # Minimum queries before weight adjustment
RESOLUTION_FAILURE_THRESHOLD = 5    # Minimum failures before alias proposal
CONFIDENCE_THRESHOLD = 0.5          # Below this → flag for prompt improvement


# ── Dataclass ─────────────────────────────────────────────────────────

@dataclass
class FeedbackAction:
    """A single proposed action from a feedback loop.

    Attributes:
        loop:         Which loop produced this ("query_pattern", "resolution_failure", "quality").
        action_type:  What kind of action ("adjust_weight", "propose_alias", "flag_pattern").
        description:  Human-readable explanation of the action.
        entity_name:  The entity involved, if any.
        metadata:     Structured details (intent, counts, suggestions, etc.).
    """

    loop: str
    action_type: str
    description: str
    entity_name: str | None = None
    metadata: dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════
# Loop 1: Query Patterns → Concept Weighting
# ═══════════════════════════════════════════════════════════════════════

class QueryPatternLoop:
    """Adjusts concept weights based on query frequency patterns.

    Reads query_telemetry, groups by intent, and for intents above the
    threshold produces FeedbackActions recommending weight boosts for
    concepts that match those intents.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def analyze(self, since_days: int = 7) -> list[FeedbackAction]:
        """Analyze recent query patterns and propose weight adjustments."""
        actions: list[FeedbackAction] = []

        try:
            rows = self.db.fetch_all(
                """
                SELECT intent, COUNT(*) AS query_count
                FROM query_telemetry
                WHERE intent IS NOT NULL AND intent != ''
                  AND created_at > NOW() - make_interval(days := %s)
                GROUP BY intent
                ORDER BY query_count DESC
                """,
                [since_days],
            )
        except Exception:
            logger.debug("QueryPatternLoop: failed to read telemetry", exc_info=True)
            return actions

        for row in rows:
            intent = row["intent"]
            count = row["query_count"]

            if count < QUERY_COUNT_THRESHOLD:
                continue

            # Boost factor: log-scaled so 10 queries → ~1.0, 100 → ~2.0
            boost_factor = round(math.log10(max(count, 1)), 2)

            actions.append(FeedbackAction(
                loop="query_pattern",
                action_type="adjust_weight",
                description=(
                    f"Intent '{intent}' received {count} queries in the last "
                    f"{since_days} days. Boost relevant concept weights by {boost_factor}x."
                ),
                entity_name=None,
                metadata={
                    "intent": intent,
                    "query_count": count,
                    "boost_factor": boost_factor,
                    "since_days": since_days,
                },
            ))

        return actions


# ═══════════════════════════════════════════════════════════════════════
# Loop 2: Entity Resolution Failures → Ontology Expansion
# ═══════════════════════════════════════════════════════════════════════

class ResolutionFailureLoop:
    """Proposes ontology additions from repeated resolution failures.

    Reads entity resolution failures, clusters by normalised term, and
    for terms above the threshold produces alias proposals.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def analyze(self, since_days: int = 7) -> list[FeedbackAction]:
        """Analyze resolution failures and propose ontology additions."""
        actions: list[FeedbackAction] = []

        try:
            rows = self.db.fetch_all(
                """
                SELECT failed_term, COUNT(*) AS failure_count
                FROM entity_resolution_failures
                WHERE created_at > NOW() - make_interval(days := %s)
                GROUP BY failed_term
                ORDER BY failure_count DESC
                LIMIT 50
                """,
                [since_days],
            )
        except Exception:
            logger.debug("ResolutionFailureLoop: failed to read failures", exc_info=True)
            return actions

        # Cluster by normalised (lowercased, stripped) form
        clusters: dict[str, dict] = {}
        for row in rows:
            term = row["failed_term"]
            count = row["failure_count"]
            normalised = term.lower().strip()

            if normalised not in clusters:
                clusters[normalised] = {
                    "canonical": term,
                    "total_failures": 0,
                    "variants": [],
                }
            clusters[normalised]["total_failures"] += count
            clusters[normalised]["variants"].append(term)

        for normalised, info in clusters.items():
            total = info["total_failures"]
            if total < RESOLUTION_FAILURE_THRESHOLD:
                continue

            actions.append(FeedbackAction(
                loop="resolution_failure",
                action_type="propose_alias",
                description=(
                    f"Entity '{info['canonical']}' failed resolution {total} times. "
                    f"Consider adding as an alias or new entity."
                ),
                entity_name=info["canonical"],
                metadata={
                    "normalised_term": normalised,
                    "failure_count": total,
                    "variants": info["variants"],
                    "since_days": since_days,
                },
            ))

        return actions


# ═══════════════════════════════════════════════════════════════════════
# Loop 3: Answer Quality → Prompt Optimization
# ═══════════════════════════════════════════════════════════════════════

# Prompt improvement suggestions by intent
_PROMPT_SUGGESTIONS: dict[str, str] = {
    "landscape": (
        "Landscape queries need stronger grounding. Add materialised view "
        "fallbacks and ensure competitive_landscape metrics are always included."
    ),
    "dossier": (
        "Dossier queries have low confidence. Verify entity resolution is "
        "finding the right entity and that evidence retrieval covers all sources."
    ),
    "pipeline": (
        "Pipeline queries underperform. Ensure trial phase data is fresh and "
        "pipeline_strength metrics are computed for the queried entity."
    ),
    "compare": (
        "Compare queries need both entities resolved. Add disambiguation "
        "prompts when entity resolution confidence is below 0.7."
    ),
    "general": (
        "General queries lack focus. Consider adding intent clarification "
        "in the system prompt to narrow scope before retrieval."
    ),
    "portfolio": (
        "Portfolio queries need comprehensive company data. Verify company "
        "entity has drug links and therapeutic area coverage populated."
    ),
}


class QualityLoop:
    """Identifies low-quality response patterns for prompt improvement.

    Reads query_telemetry, groups by intent, and flags intents where the
    average confidence is below the threshold.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    def analyze(self, since_days: int = 7) -> list[FeedbackAction]:
        """Analyze response quality and flag low-confidence patterns."""
        actions: list[FeedbackAction] = []

        try:
            rows = self.db.fetch_all(
                """
                SELECT
                    intent,
                    AVG(confidence) AS avg_confidence,
                    COUNT(*) AS query_count,
                    SUM(CASE WHEN confidence < %s THEN 1 ELSE 0 END) AS low_confidence_count
                FROM query_telemetry
                WHERE intent IS NOT NULL AND intent != ''
                  AND confidence IS NOT NULL
                  AND created_at > NOW() - make_interval(days := %s)
                GROUP BY intent
                HAVING COUNT(*) >= %s
                ORDER BY AVG(confidence) ASC
                """,
                [CONFIDENCE_THRESHOLD, since_days, QUERY_COUNT_THRESHOLD],
            )
        except Exception:
            logger.debug("QualityLoop: failed to read telemetry", exc_info=True)
            return actions

        for row in rows:
            intent = row["intent"]
            avg_conf = row["avg_confidence"]
            query_count = row["query_count"]
            low_count = row["low_confidence_count"]

            if avg_conf is not None and avg_conf >= CONFIDENCE_THRESHOLD:
                continue

            suggestion = _PROMPT_SUGGESTIONS.get(
                intent,
                f"Intent '{intent}' consistently produces low-confidence responses. "
                f"Review retrieval pipeline and system prompt for this intent.",
            )

            actions.append(FeedbackAction(
                loop="quality",
                action_type="flag_pattern",
                description=(
                    f"Intent '{intent}' has avg confidence {avg_conf:.2f} "
                    f"across {query_count} queries ({low_count} below threshold)."
                ),
                entity_name=None,
                metadata={
                    "intent": intent,
                    "avg_confidence": avg_conf,
                    "query_count": query_count,
                    "low_confidence_count": low_count,
                    "suggestion": suggestion,
                    "since_days": since_days,
                },
            ))

        return actions


# ═══════════════════════════════════════════════════════════════════════
# Orchestrator
# ═══════════════════════════════════════════════════════════════════════

class FeedbackLoopOrchestrator:
    """Runs all feedback loops and returns combined actions.

    Args:
        db: Database instance for reading telemetry and failures.
    """

    def __init__(self, db: Database) -> None:
        self.db = db
        self._loops = [
            QueryPatternLoop(db),
            ResolutionFailureLoop(db),
            QualityLoop(db),
        ]

    def run(self, since_days: int = 7, dry_run: bool = False) -> dict:
        """Execute all feedback loops and return combined results.

        Args:
            since_days: How far back to look for patterns.
            dry_run: If True, return proposed actions without persisting.

        Returns:
            dict with keys: actions, summary, dry_run.
        """
        all_actions: list[FeedbackAction] = []
        loop_errors: list[str] = []

        for loop in self._loops:
            try:
                actions = loop.analyze(since_days=since_days)
                all_actions.extend(actions)
            except Exception as exc:
                loop_name = loop.__class__.__name__
                logger.warning("Feedback loop %s failed: %s", loop_name, exc)
                loop_errors.append(f"{loop_name}: {exc}")

        # Persist actions unless dry_run
        if not dry_run:
            self._persist_actions(all_actions)

        # Build summary
        by_loop: dict[str, int] = {}
        by_type: dict[str, int] = {}
        for a in all_actions:
            by_loop[a.loop] = by_loop.get(a.loop, 0) + 1
            by_type[a.action_type] = by_type.get(a.action_type, 0) + 1

        return {
            "actions": [
                {
                    "loop": a.loop,
                    "action_type": a.action_type,
                    "description": a.description,
                    "entity_name": a.entity_name,
                    "metadata": a.metadata,
                }
                for a in all_actions
            ],
            "summary": {
                "loops_executed": len(self._loops),
                "total_actions": len(all_actions),
                "by_loop": by_loop,
                "by_action_type": by_type,
                "errors": loop_errors,
            },
            "dry_run": dry_run,
        }

    def _persist_actions(self, actions: list[FeedbackAction]) -> None:
        """Persist feedback loop actions to the database."""
        import json

        for action in actions:
            try:
                self.db.execute(
                    """INSERT INTO feedback_loop_actions
                       (loop, action_type, description, entity_name, metadata)
                       VALUES (%s, %s, %s, %s, %s)""",
                    [
                        action.loop,
                        action.action_type,
                        action.description,
                        action.entity_name,
                        json.dumps(action.metadata),
                    ],
                )
            except Exception:
                logger.debug(
                    "Failed to persist feedback action: %s", action.description,
                    exc_info=True,
                )
