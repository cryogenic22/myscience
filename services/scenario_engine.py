"""ScenarioEngine: Deterministic what-if operations on the knowledge graph.

Provides scenario primitives that let decision-makers ask "what if" questions
without modifying the database. All operations are pure calculations over
existing metrics data.

Usage:
    engine = ScenarioEngine(db=db, metrics=metrics)
    result = engine.landscape_without_entity("m1", "mechanism", topic="Diabetes")
    result = engine.pipeline_excluding_inactive("Diabetes", inactive_years=2)
    alerts = engine.threshold_alert("pipeline_score", 50.0, "drug")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ScenarioResult:
    """Result of a what-if scenario computation."""

    scenario_type: str
    description: str
    baseline: dict = field(default_factory=dict)
    modified: dict = field(default_factory=dict)
    delta: dict = field(default_factory=dict)
    entities_affected: int = 0


class ScenarioEngine:
    """Deterministic what-if operations on the knowledge graph.

    All operations are read-only: they fetch baseline data from PharmaMetrics,
    apply in-memory filters/transforms, and return before/after comparisons.
    No database mutations are performed.
    """

    def __init__(self, db, metrics):
        self.db = db
        self.metrics = metrics

    # ── Orchestrator ──

    def run(self, scenario_type: str, params: dict) -> ScenarioResult:
        """Route a named scenario to the appropriate handler.

        Args:
            scenario_type: One of "landscape_without_entity",
                "pipeline_without_entity", "pipeline_excluding_inactive",
                "landscape_without_company", "landscape_single_mechanism",
                "threshold_alert".
            params: Dict of keyword arguments for the handler.

        Returns:
            ScenarioResult with baseline, modified, delta.

        Raises:
            ValueError: If scenario_type is not recognized.
        """
        dispatch = {
            "landscape_without_entity": self.landscape_without_entity,
            "pipeline_without_entity": self.pipeline_without_entity,
            "pipeline_excluding_inactive": self.pipeline_excluding_inactive,
            "landscape_without_company": self.landscape_without_company,
            "landscape_single_mechanism": self.landscape_single_mechanism,
        }

        handler = dispatch.get(scenario_type)
        if handler is None:
            raise ValueError(f"Unknown scenario type: {scenario_type}")

        return handler(**params)

    # ── Entity Removal ──

    def landscape_without_entity(
        self,
        entity_id: str,
        entity_type: str,
        topic: Optional[str] = None,
    ) -> ScenarioResult:
        """Recalculate competitive landscape excluding an entity.

        Fetches the full landscape from PharmaMetrics, then removes rows
        matching the entity_id (by mechanism_id, therapeutic_area_id, etc.)
        and recomputes derived fields (market_share_pct, totals).
        """
        baseline_rows = self.metrics.competitive_landscape(topic=topic)

        # Determine which field to filter on based on entity_type
        filter_field = _entity_type_to_landscape_field(entity_type)
        modified_rows = [r for r in baseline_rows if r.get(filter_field) != entity_id]

        # Recompute market share percentages
        _recompute_market_share(modified_rows)

        # Compute delta
        baseline_total_score = sum(
            r.get("total_pipeline_score", 0) or 0 for r in baseline_rows
        )
        modified_total_score = sum(
            r.get("total_pipeline_score", 0) or 0 for r in modified_rows
        )
        entities_removed = len(baseline_rows) - len(modified_rows)

        return ScenarioResult(
            scenario_type="entity_removal",
            description=(
                f"Competitive landscape excluding {entity_type} '{entity_id}'"
                + (f" for topic '{topic}'" if topic else "")
            ),
            baseline={"rows": baseline_rows, "row_count": len(baseline_rows)},
            modified={"rows": modified_rows, "row_count": len(modified_rows)},
            delta={
                "row_count_change": -entities_removed,
                "total_pipeline_score_change": modified_total_score - baseline_total_score,
            },
            entities_affected=entities_removed,
        )

    def pipeline_without_entity(
        self,
        entity_id: str,
        therapeutic_area: Optional[str] = None,
    ) -> ScenarioResult:
        """Recalculate pipeline strength excluding a specific drug.

        Fetches pipeline data from PharmaMetrics, removes the target drug,
        and recomputes rankings.
        """
        baseline_rows = self.metrics.drug_pipeline_strength(
            therapeutic_area=therapeutic_area,
        )

        modified_rows = [r for r in baseline_rows if r.get("drug_id") != entity_id]

        entities_removed = len(baseline_rows) - len(modified_rows)
        baseline_total = sum(r.get("pipeline_score", 0) or 0 for r in baseline_rows)
        modified_total = sum(r.get("pipeline_score", 0) or 0 for r in modified_rows)

        return ScenarioResult(
            scenario_type="entity_removal",
            description=f"Pipeline strength excluding drug '{entity_id}'",
            baseline={"rows": baseline_rows, "row_count": len(baseline_rows)},
            modified={"rows": modified_rows, "row_count": len(modified_rows)},
            delta={
                "row_count_change": -(entities_removed),
                "total_pipeline_score_change": modified_total - baseline_total,
            },
            entities_affected=entities_removed,
        )

    # ── Temporal Filtering ──

    def pipeline_excluding_inactive(
        self,
        therapeutic_area: str,
        inactive_years: int = 2,
    ) -> ScenarioResult:
        """Pipeline strength excluding drugs with no recent trial activity.

        Filters out drugs whose last_trial_start is older than inactive_years
        from today.
        """
        baseline_rows = self.metrics.drug_pipeline_strength(
            therapeutic_area=therapeutic_area,
        )

        cutoff = datetime.now() - timedelta(days=inactive_years * 365)
        modified_rows = []
        filtered_count = 0

        for row in baseline_rows:
            last_start = row.get("last_trial_start")
            if last_start is None:
                # No trial date — treat as inactive
                filtered_count += 1
                continue
            # Handle both datetime objects and strings
            if isinstance(last_start, str):
                try:
                    last_start = datetime.fromisoformat(last_start)
                except (ValueError, TypeError):
                    filtered_count += 1
                    continue
            if last_start >= cutoff:
                modified_rows.append(row)
            else:
                filtered_count += 1

        baseline_total = sum(r.get("pipeline_score", 0) or 0 for r in baseline_rows)
        modified_total = sum(r.get("pipeline_score", 0) or 0 for r in modified_rows)

        return ScenarioResult(
            scenario_type="temporal_filter",
            description=(
                f"Pipeline for '{therapeutic_area}' excluding drugs "
                f"inactive for {inactive_years}+ years"
            ),
            baseline={"rows": baseline_rows, "row_count": len(baseline_rows)},
            modified={"rows": modified_rows, "row_count": len(modified_rows)},
            delta={
                "row_count_change": -(filtered_count),
                "total_pipeline_score_change": modified_total - baseline_total,
            },
            entities_affected=filtered_count,
        )

    # ── Segment Isolation ──

    def landscape_without_company(
        self,
        company_id: str,
        topic: Optional[str] = None,
    ) -> ScenarioResult:
        """Competitive landscape excluding all drugs from a specific company.

        Queries the DB to find drugs owned by the company, then removes
        those drugs' contributions from the landscape.
        """
        # Find drugs belonging to this company
        company_drug_rows = self.db.fetch_all(
            """
            SELECT d.id::text AS drug_id, d.generic_name AS drug_name,
                   d.company_id::text AS company_id
            FROM drugs d
            WHERE d.company_id::text = %s
               OR d.id::text IN (
                   SELECT el.target_entity_id FROM entity_links el
                   WHERE el.source_entity_id = %s
                     AND el.link_type IN ('OWNS', 'SPONSORS')
               )
            """,
            [company_id, company_id],
        )
        excluded_drug_ids = {r["drug_id"] for r in company_drug_rows}

        baseline_rows = self.metrics.competitive_landscape(topic=topic)
        # We cannot remove individual drugs from landscape rows (which are
        # mechanism-level aggregates), so we annotate which mechanisms are
        # affected. For a full re-aggregation we would need raw data.
        # Pragmatic approach: flag rows where the top_drug is from the excluded company.
        modified_rows = []
        for row in baseline_rows:
            top_drug = row.get("top_drug", "")
            drug_names_excluded = {r["drug_name"] for r in company_drug_rows}
            if top_drug in drug_names_excluded:
                # Reduce drug_count by number of excluded drugs (approximate)
                new_row = dict(row)
                new_row["drug_count"] = max(0, row.get("drug_count", 0) - len(excluded_drug_ids))
                new_row["company_excluded"] = company_id
                modified_rows.append(new_row)
            else:
                modified_rows.append(dict(row))

        _recompute_market_share(modified_rows)

        return ScenarioResult(
            scenario_type="segment_isolation",
            description=f"Landscape excluding company '{company_id}' drugs",
            baseline={"rows": baseline_rows, "row_count": len(baseline_rows)},
            modified={"rows": modified_rows, "row_count": len(modified_rows)},
            delta={
                "excluded_drug_ids": list(excluded_drug_ids),
                "excluded_drug_count": len(excluded_drug_ids),
            },
            entities_affected=len(excluded_drug_ids),
        )

    def landscape_single_mechanism(
        self,
        mechanism_id: str,
        topic: Optional[str] = None,
    ) -> ScenarioResult:
        """Isolate competitive landscape to a single mechanism.

        Filters the landscape to show only the target mechanism,
        useful for deep-dive analysis.
        """
        baseline_rows = self.metrics.competitive_landscape(topic=topic)
        modified_rows = [
            r for r in baseline_rows if r.get("mechanism_id") == mechanism_id
        ]

        _recompute_market_share(modified_rows)

        return ScenarioResult(
            scenario_type="segment_isolation",
            description=f"Landscape isolated to mechanism '{mechanism_id}'",
            baseline={"rows": baseline_rows, "row_count": len(baseline_rows)},
            modified={"rows": modified_rows, "row_count": len(modified_rows)},
            delta={
                "row_count_change": len(modified_rows) - len(baseline_rows),
                "mechanisms_isolated": 1,
            },
            entities_affected=len(baseline_rows) - len(modified_rows),
        )

    # ── Threshold Alerts ──

    def threshold_alert(
        self,
        metric: str,
        threshold: float,
        entity_type: str = "drug",
    ) -> list[dict]:
        """Flag entities whose metric value exceeds a threshold.

        Currently supports drug pipeline metrics. Returns a list of
        entities that exceed the threshold, sorted by the metric descending.
        """
        if entity_type == "drug":
            rows = self.metrics.drug_pipeline_strength()
        else:
            logger.warning("threshold_alert: unsupported entity_type '%s'", entity_type)
            return []

        alerts = []
        for row in rows:
            value = row.get(metric)
            if value is not None and value > threshold:
                alerts.append({
                    **row,
                    "alert_metric": metric,
                    "alert_threshold": threshold,
                    "alert_value": value,
                    "alert_exceeded_by": round(value - threshold, 4),
                })

        # Sort by the metric descending
        alerts.sort(key=lambda a: a.get("alert_value", 0), reverse=True)
        return alerts


# ── Module-level helpers ──


def _entity_type_to_landscape_field(entity_type: str) -> str:
    """Map entity type to the corresponding field in landscape rows."""
    mapping = {
        "mechanism": "mechanism_id",
        "therapeutic_area": "therapeutic_area_id",
        "drug": "top_drug",
    }
    return mapping.get(entity_type, "mechanism_id")


def _recompute_market_share(rows: list[dict]) -> None:
    """Recompute market_share_pct in-place after filtering rows."""
    total_drugs = sum(r.get("drug_count", 0) or 0 for r in rows)
    if total_drugs > 0:
        for row in rows:
            dc = row.get("drug_count", 0) or 0
            row["market_share_pct"] = round((dc / total_drugs) * 100, 1)
    else:
        for row in rows:
            row["market_share_pct"] = 0.0
