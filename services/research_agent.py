"""
Autonomous Research Agent for Market-Zero.

Inspired by karpathy/autoresearch pattern:
  identify target -> plan enrichment -> execute -> evaluate -> keep or revert -> log

Runs in background to find and fill knowledge gaps in the pharma intelligence
knowledge base. Each iteration:
  1. Identify the entity with the lowest quality/FAIR score
  2. Plan enrichment actions based on detected gaps
  3. Execute enrichment (mock for now, real connectors later)
  4. Evaluate whether quality improved
  5. Commit improvements or revert regressions
  6. Log the iteration result

Key constraints (research protocol):
  - Max 1 entity per iteration
  - Never delete existing data
  - Respect API call budgets
  - Flag uncertain enrichments for HITL review
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ── Data classes ──

@dataclass
class ResearchTarget:
    """An entity identified for enrichment."""
    entity_id: str
    entity_type: str
    entity_name: str
    quality_score: float
    connection_count: int
    enrichment_count: int  # how many times already enriched
    gaps: list[str]  # what's missing (e.g., ["mechanism", "company"])


@dataclass
class EnrichmentPlan:
    """A plan of actions to enrich a target entity."""
    target: ResearchTarget
    actions: list[dict]  # [{"type": "pubmed_search", "query": "..."}, ...]
    estimated_api_calls: int
    reason: str


@dataclass
class EvalResult:
    """Result of evaluating an enrichment attempt."""
    improved: bool
    fair_before: float
    fair_after: float
    delta: float
    false_links: int
    details: str


@dataclass
class LoopSummary:
    """Summary of a complete research loop run."""
    iterations: int
    improvements: int
    rejections: int
    hitl_flagged: int
    total_api_calls: int
    mean_fair_delta: float


# ── Gap detection helpers ──

def _detect_gaps(entity_data: dict) -> list[str]:
    """Detect knowledge gaps for an entity based on its data completeness."""
    gaps = []
    if not entity_data.get("mechanism_name"):
        gaps.append("mechanism")
    if not entity_data.get("company_name"):
        gaps.append("company")
    trial_count = entity_data.get("trial_count")
    if trial_count is None or trial_count == 0:
        gaps.append("trials")
    return gaps


# ── Gap -> action mapping ──

_GAP_ACTION_MAP = {
    "mechanism": lambda name: {
        "type": "pubmed_search",
        "query": f"{name} mechanism of action",
        "api_calls": 1,
    },
    "company": lambda name: {
        "type": "company_lookup",
        "query": f"{name} manufacturer developer",
        "api_calls": 1,
    },
    "trials": lambda name: {
        "type": "clinical_trials_search",
        "query": f"{name} clinical trial",
        "api_calls": 1,
    },
    "stale_data": lambda name: {
        "type": "refetch",
        "query": f"{name} latest data",
        "api_calls": 2,
    },
}


class AutonomousResearchAgent:
    """
    Autonomous agent that identifies knowledge gaps and enriches entities.

    Uses a quality scorer to evaluate entity completeness and plans
    enrichment actions for the weakest entities. Operates in a loop
    with configurable iteration and API call budgets.
    """

    def __init__(
        self,
        db,
        quality_scorer=None,
        entity_data: list[dict] | None = None,
        max_api_calls_per_iteration: int = 5,
        max_enrichments_per_entity: int = 3,
        max_total_api_calls: int = 1000,
        quality_threshold: float = 6.0,
        protocol_path: str | None = None,
    ):
        self.db = db
        self.quality_scorer = quality_scorer
        self._entity_data = list(entity_data) if entity_data else []
        self.max_api_calls_per_iteration = max_api_calls_per_iteration
        self.max_enrichments_per_entity = max_enrichments_per_entity
        self.max_total_api_calls = max_total_api_calls
        self.quality_threshold = quality_threshold

        # Internal tracking state
        self._enrichment_history: set[str] = set()  # entity IDs enriched this cycle
        self._deleted_count: int = 0  # must always remain 0 (never delete)
        self.iteration_log: list[dict] = []
        self._total_api_calls_used: int = 0

        # Load protocol if provided
        self.protocol: str | None = None
        if protocol_path:
            path = Path(protocol_path)
            if path.exists():
                self.protocol = path.read_text(encoding="utf-8")

    # ── 1. Target identification ──

    def identify_target(self) -> ResearchTarget | None:
        """
        Find the entity most in need of enrichment.

        Selection criteria (priority order):
          1. Quality score below threshold
          2. Not already enriched this cycle
          3. Not already enriched max times
          4. Higher connection count = higher impact priority
          5. Lower quality score = more urgent

        Returns None if all entities are above threshold or exhausted.
        """
        candidates = []
        for entity in self._entity_data:
            eid = entity["entity_id"]
            score = entity.get("quality_score", 10.0)
            enrichment_count = entity.get("enrichment_count", 0)

            # Skip if above quality threshold
            if score >= self.quality_threshold:
                continue

            # Skip if already enriched this cycle
            if eid in self._enrichment_history:
                continue

            # Skip if already enriched max times
            if enrichment_count >= self.max_enrichments_per_entity:
                continue

            gaps = _detect_gaps(entity)
            connection_count = entity.get("connection_count", 0)

            candidates.append({
                "entity": entity,
                "score": score,
                "connection_count": connection_count,
                "gaps": gaps,
                "enrichment_count": enrichment_count,
            })

        if not candidates:
            return None

        # Sort by: lowest score first, then highest connection count (for impact)
        # Use a composite priority: lower score is better, higher connections is better
        # Priority = score - (connection_count * 0.01) so that connections break ties
        candidates.sort(key=lambda c: (c["score"], -c["connection_count"]))

        best = candidates[0]
        entity = best["entity"]

        return ResearchTarget(
            entity_id=entity["entity_id"],
            entity_type=entity["entity_type"],
            entity_name=entity["entity_name"],
            quality_score=best["score"],
            connection_count=best["connection_count"],
            enrichment_count=best["enrichment_count"],
            gaps=best["gaps"],
        )

    # ── 2. Enrichment planning ──

    def plan_enrichment(self, target: ResearchTarget) -> EnrichmentPlan:
        """
        Generate an enrichment plan based on the target's gaps.

        Each gap maps to a specific action type. The plan is capped at
        max_api_calls_per_iteration total API calls.
        """
        actions = []
        total_api_calls = 0

        for gap in target.gaps:
            if total_api_calls >= self.max_api_calls_per_iteration:
                break

            action_fn = _GAP_ACTION_MAP.get(gap)
            if action_fn:
                action = action_fn(target.entity_name)
                api_cost = action.pop("api_calls", 1)

                # Check if adding this action would exceed budget
                if total_api_calls + api_cost > self.max_api_calls_per_iteration:
                    break

                actions.append(action)
                total_api_calls += api_cost

        # If no gap-based actions, plan a generic quality improvement action
        if not actions:
            actions.append({
                "type": "quality_check",
                "query": f"{target.entity_name} data verification",
            })
            total_api_calls = 1

        reason_parts = [f"fill {g} gap" for g in target.gaps] if target.gaps else ["verify data quality"]
        reason = f"Enrich {target.entity_name}: " + ", ".join(reason_parts)

        return EnrichmentPlan(
            target=target,
            actions=actions,
            estimated_api_calls=total_api_calls,
            reason=reason,
        )

    # ── 3. Enrichment execution ──

    def execute_enrichment(self, plan: EnrichmentPlan) -> dict:
        """Execute an enrichment plan using real connectors.

        Calls PubMed, ClinicalTrials.gov, and DB lookups to fill
        knowledge gaps for the target entity.
        """
        enrichment_data = {}
        api_calls_used = 0
        entity_name = plan.target.entity_name

        for action in plan.actions:
            action_type = action["type"]
            try:
                if action_type == "pubmed_search":
                    enrichment_data.update(
                        self._enrich_from_pubmed(entity_name)
                    )
                    api_calls_used += 1

                elif action_type == "company_lookup":
                    enrichment_data.update(
                        self._enrich_company(entity_name)
                    )
                    api_calls_used += 1

                elif action_type == "clinical_trials_search":
                    enrichment_data.update(
                        self._enrich_from_trials(entity_name)
                    )
                    api_calls_used += 1

                elif action_type == "refetch":
                    enrichment_data["refreshed"] = True
                    api_calls_used += 2

                elif action_type == "quality_check":
                    api_calls_used += 1

            except Exception as e:
                logger.warning("Enrichment action %s failed for %s: %s",
                               action_type, entity_name, e)

        self._total_api_calls_used += api_calls_used
        return enrichment_data

    def _enrich_from_pubmed(self, drug_name: str) -> dict:
        """Search PubMed for mechanism/literature evidence."""
        result: dict = {}
        try:
            rows = self.db.fetch_all(
                """SELECT title, mesh_terms FROM pubmed_articles
                   WHERE title ILIKE %s OR abstract ILIKE %s
                   LIMIT 10""",
                [f"%{drug_name}%", f"%{drug_name}%"],
            )
            if rows:
                result["literature_count"] = len(rows)
                # Extract mechanism from MeSH terms
                for r in rows:
                    mesh = r.get("mesh_terms") or ""
                    if isinstance(mesh, list):
                        mesh = " ".join(mesh)
                    mech = self.db.fetch_one(
                        "SELECT name FROM mechanisms_of_action WHERE name ILIKE ANY(%s) LIMIT 1",
                        [[f"%{t.strip()}%" for t in mesh.split(",")[:5]]],
                    ) if mesh else None
                    if mech:
                        result["mechanism_name"] = mech["name"]
                        break
        except Exception as e:
            logger.debug("PubMed enrichment lookup failed: %s", e)
        return result

    def _enrich_company(self, drug_name: str) -> dict:
        """Look up drug manufacturer from existing data."""
        result: dict = {}
        try:
            # Check trial sponsors for this drug
            row = self.db.fetch_one(
                """SELECT ct.sponsor_name FROM clinical_trials ct
                   JOIN entity_links el ON el.source_entity_id = ct.id
                   AND el.link_type = 'INVESTIGATES'
                   JOIN drugs d ON d.id::text = el.target_entity_id
                   WHERE LOWER(d.generic_name) ILIKE %s
                   AND ct.sponsor_name IS NOT NULL
                   LIMIT 1""",
                [f"%{drug_name.lower()}%"],
            )
            if row and row["sponsor_name"]:
                co = self.db.fetch_one(
                    "SELECT name FROM companies WHERE name ILIKE %s LIMIT 1",
                    [f"%{row['sponsor_name']}%"],
                )
                if co:
                    result["company_name"] = co["name"]
        except Exception as e:
            logger.debug("Company enrichment lookup failed: %s", e)
        return result

    def _enrich_from_trials(self, drug_name: str) -> dict:
        """Count trials and find new trial data."""
        result: dict = {}
        try:
            rows = self.db.fetch_all(
                """SELECT id, official_title, phase, status
                   FROM clinical_trials
                   WHERE official_title ILIKE %s OR conditions ILIKE %s
                   ORDER BY start_date DESC NULLS LAST
                   LIMIT 20""",
                [f"%{drug_name}%", f"%{drug_name}%"],
            )
            if rows:
                result["trial_count"] = len(rows)
                result["new_trials"] = [
                    {"nct_id": str(r["id"]), "phase": r.get("phase", ""), "status": r.get("status", "")}
                    for r in rows[:5]
                ]
        except Exception as e:
            logger.debug("Trial enrichment lookup failed: %s", e)
        return result

    # ── 4. Evaluation ──

    def evaluate(self, target: ResearchTarget, enrichment_data: dict) -> EvalResult:
        """
        Evaluate whether an enrichment improved the entity's quality.

        Computes FAIR score before and after applying enrichment data.
        Uses the quality scorer to measure improvement.
        """
        # Build the "before" entity data from current state
        before_data = self._get_entity_data(target.entity_id)
        fair_before = self.quality_scorer.compute_fair_score(before_data) if before_data else target.quality_score

        # Check for explicit regression signal
        if enrichment_data.get("_regression"):
            return EvalResult(
                improved=False,
                fair_before=fair_before,
                fair_after=fair_before - 0.5,
                delta=-0.5,
                false_links=0,
                details="Regression detected in enrichment data",
            )

        # Check for false links
        false_links = 0
        false_link_entries = enrichment_data.get("_false_links", [])
        false_links = len(false_link_entries)

        # Build the "after" entity data by merging enrichment
        after_data = dict(before_data) if before_data else {}
        for key, value in enrichment_data.items():
            if not key.startswith("_"):  # skip internal flags
                after_data[key] = value

        fair_after = self.quality_scorer.compute_fair_score(after_data)
        delta = round(fair_after - fair_before, 4)

        # Conservative: only count as improved if delta > 0
        improved = delta > 0 and false_links == 0

        return EvalResult(
            improved=improved,
            fair_before=fair_before,
            fair_after=fair_after,
            delta=delta,
            false_links=false_links,
            details=f"FAIR: {fair_before:.1f} -> {fair_after:.1f} (delta={delta:+.1f})",
        )

    # ── 5. Commit or revert ──

    def commit_or_revert(self, eval_result: EvalResult) -> bool:
        """
        Commit enrichment if improved, revert if not.

        NEVER deletes existing data. Revert simply means not applying
        the new enrichment data to the persistent store.

        Returns True if committed, False if reverted.
        """
        # Protocol: never delete data
        # self._deleted_count stays at 0

        if eval_result.improved:
            logger.info("Committing enrichment: %s", eval_result.details)
            return True
        else:
            logger.info("Reverting enrichment: %s", eval_result.details)
            return False

    # ── 6. Logging ──

    def log_iteration(
        self,
        target: ResearchTarget,
        action: str,
        eval_result: EvalResult,
    ):
        """Log a single iteration of the research loop."""
        if eval_result.improved:
            status = "improved"
        elif eval_result.false_links > 0:
            status = "rejected_false_links"
        else:
            status = "rejected"

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "target": target.entity_name,
            "entity_id": target.entity_id,
            "entity_type": target.entity_type,
            "action": action,
            "fair_before": eval_result.fair_before,
            "fair_after": eval_result.fair_after,
            "delta": eval_result.delta,
            "false_links": eval_result.false_links,
            "status": status,
            "details": eval_result.details,
        }
        self.iteration_log.append(entry)

    def persist_log(self, path: str):
        """Write the iteration log to a TSV file."""
        if not self.iteration_log:
            return

        fieldnames = [
            "timestamp", "target", "entity_id", "entity_type",
            "action", "fair_before", "fair_after", "delta",
            "false_links", "status", "details",
        ]

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
            writer.writeheader()
            for entry in self.iteration_log:
                writer.writerow(entry)

    def get_cumulative_stats(self) -> dict:
        """Return running count of improvements, rejections, total iterations."""
        improvements = sum(1 for e in self.iteration_log if e["status"] == "improved")
        rejections = sum(1 for e in self.iteration_log if e["status"].startswith("rejected"))
        return {
            "total_iterations": len(self.iteration_log),
            "improvements": improvements,
            "rejections": rejections,
        }

    # ── 7. Main loop ──

    def run_loop(self, max_iterations: int = 10) -> LoopSummary:
        """
        Run the autonomous research loop.

        Each iteration:
          1. identify_target() -> best entity to enrich
          2. plan_enrichment() -> actions to take
          3. execute_enrichment() -> get enrichment data
          4. evaluate() -> did quality improve?
          5. commit_or_revert() -> apply or discard
          6. log_iteration() -> record result

        Stops when:
          - max_iterations reached
          - No more targets below threshold
          - Total API budget exhausted
        """
        iterations = 0
        improvements = 0
        rejections = 0
        hitl_flagged = 0
        deltas = []

        for i in range(max_iterations):
            # Check total API budget
            if self._total_api_calls_used >= self.max_total_api_calls:
                logger.info("API budget exhausted after %d iterations", iterations)
                break

            # Step 1: Identify target
            target = self.identify_target()
            if target is None:
                logger.info("No more targets below threshold after %d iterations", iterations)
                break

            # Step 2: Plan enrichment
            plan = self.plan_enrichment(target)

            # Check if plan would exceed remaining API budget
            remaining_budget = self.max_total_api_calls - self._total_api_calls_used
            if plan.estimated_api_calls > remaining_budget:
                logger.info("Plan exceeds remaining API budget, stopping")
                break

            # Step 3: Execute enrichment
            enrichment_data = self.execute_enrichment(plan)

            # Step 4: Evaluate
            eval_result = self.evaluate(target, enrichment_data)

            # Step 5: Commit or revert
            committed = self.commit_or_revert(eval_result)

            # Step 6: Determine if HITL flagging is needed
            # Flag for HITL if: false links detected, or very small improvement
            needs_hitl = False
            if eval_result.false_links > 0:
                needs_hitl = True
            elif 0 < eval_result.delta < 0.3:
                needs_hitl = True

            if needs_hitl:
                hitl_flagged += 1
                status_action = "hitl_flagged"
            elif committed:
                improvements += 1
                status_action = "improved"
            else:
                rejections += 1
                status_action = "rejected"

            # Step 7: Log
            primary_action = plan.actions[0]["type"] if plan.actions else "none"
            self.log_iteration(target, primary_action, eval_result)

            # Mark entity as enriched this cycle
            self._enrichment_history.add(target.entity_id)

            iterations += 1
            deltas.append(eval_result.delta)

        mean_delta = sum(deltas) / len(deltas) if deltas else 0.0

        return LoopSummary(
            iterations=iterations,
            improvements=improvements,
            rejections=rejections,
            hitl_flagged=hitl_flagged,
            total_api_calls=self._total_api_calls_used,
            mean_fair_delta=round(mean_delta, 4),
        )

    # ── Internal helpers ──

    def _get_entity_data(self, entity_id: str) -> dict:
        """Get entity data by ID from the in-memory entity list."""
        for entity in self._entity_data:
            if entity["entity_id"] == entity_id:
                return dict(entity)
        return {}
