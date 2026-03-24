"""Entity-level specialized agents for domain-specific data curation.

Each agent focuses on one entity type (pricing, trial, drug, company)
and manages the scripts and data sources relevant to that type.

The EntityAgentOrchestrator creates and runs all agents, providing
a higher-level API than invoking scripts individually.

No LangChain. Deterministic execution, dynamic import of scripts.
"""

from __future__ import annotations

import importlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from db import Database

logger = logging.getLogger(__name__)


# ── Configuration ──────────────────────────────────────────────────


@dataclass
class EntityAgentConfig:
    """Configuration for a specialized entity-level agent."""
    name: str                       # "price_agent", "trial_agent", etc.
    entity_type: str                # "pricing", "trial", "drug", "company"
    description: str
    sources: list[str]              # data sources this agent manages
    scripts: list[tuple[str, str]]  # [(module_path, function_name)]
    schedule_hours: int             # how often to run (hours)
    enabled: bool = True
    use_scheduler: bool = False     # if True, uses scheduler.run_one() instead of scripts


# ── Entity Agent ───────────────────────────────────────────────────


class EntityAgent:
    """A specialized agent focused on one entity type."""

    def __init__(self, config: EntityAgentConfig, db: Database):
        self.config = config
        self.db = db

    def run(self, dry_run: bool = False) -> dict:
        """Execute all scripts for this entity type.

        Returns dict with status, scripts_run count, and per-script results.
        """
        t0 = time.monotonic()
        results = []
        scripts_run = 0
        errors = 0

        if self.config.use_scheduler:
            # Trial agent: delegate to scheduler
            result = self._run_scheduler(dry_run=dry_run)
            results.append(result)
            if result.get("status") == "completed":
                scripts_run += 1
            elif result.get("status") == "failed":
                errors += 1
        else:
            for module_path, func_name in self.config.scripts:
                if dry_run:
                    logger.info(
                        "[DRY RUN] %s would run %s.%s",
                        self.config.name, module_path, func_name,
                    )
                    results.append({
                        "script": module_path,
                        "status": "skipped",
                        "detail": "dry run",
                    })
                    continue

                try:
                    result_data = self._execute_script(module_path, func_name)
                    self._record_action(module_path, "completed", str(result_data)[:500])
                    results.append({
                        "script": module_path,
                        "status": "completed",
                        "detail": result_data,
                    })
                    scripts_run += 1
                except Exception as e:
                    logger.warning(
                        "%s script %s failed: %s",
                        self.config.name, module_path, e,
                    )
                    self._record_action(module_path, "failed", str(e)[:500])
                    results.append({
                        "script": module_path,
                        "status": "failed",
                        "error": str(e)[:500],
                    })
                    errors += 1

        elapsed = round(time.monotonic() - t0, 2)
        return {
            "agent": self.config.name,
            "entity_type": self.config.entity_type,
            "status": "completed" if errors == 0 else "partial",
            "scripts_run": scripts_run,
            "errors": errors,
            "dry_run": dry_run,
            "elapsed_s": elapsed,
            "results": results,
        }

    def _execute_script(self, module_path: str, func_name: str) -> dict | None:
        """Dynamically import and execute a curation script."""
        mod = importlib.import_module(module_path)
        func = getattr(mod, func_name)
        return func(dry_run=False)

    def _run_scheduler(self, dry_run: bool = False) -> dict:
        """Run data sources via the pipeline scheduler."""
        if dry_run:
            logger.info(
                "[DRY RUN] %s would run scheduler for %s",
                self.config.name, self.config.sources,
            )
            return {"status": "skipped", "detail": "dry run"}

        try:
            from scheduler.runner import DataPipelineScheduler
            sched = DataPipelineScheduler()
            for source in self.config.sources:
                sched.run_one(source)
            self._record_action("scheduler", "completed", f"sources={self.config.sources}")
            return {"status": "completed", "sources": self.config.sources}
        except Exception as e:
            logger.warning("%s scheduler run failed: %s", self.config.name, e)
            self._record_action("scheduler", "failed", str(e)[:500])
            return {"status": "failed", "error": str(e)[:500]}

    def _record_action(self, script_name: str, status: str, details: str = "") -> None:
        """Log action to steward_actions table."""
        try:
            self.db.execute(
                """
                INSERT INTO steward_actions
                    (signal_source, signal_id, entity_type, entity_name,
                     action_type, status, error_message)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    "entity_agent",
                    f"{self.config.name}:{script_name}",
                    self.config.entity_type,
                    self.config.name,
                    f"agent:{script_name}",
                    status,
                    details if status == "failed" else None,
                ],
            )
        except Exception:
            logger.debug(
                "Failed to record entity agent action for %s", self.config.name,
                exc_info=True,
            )


# ── Orchestrator ───────────────────────────────────────────────────


class EntityAgentOrchestrator:
    """Manages and runs all entity-level agents."""

    AGENT_CONFIGS = [
        EntityAgentConfig(
            name="price_agent",
            entity_type="pricing",
            description="Maintains drug pricing data from CMS NADAC",
            sources=["cms_nadac"],
            scripts=[
                ("scripts.fetch_nadac_pricing", "run"),
            ],
            schedule_hours=168,  # weekly
        ),
        EntityAgentConfig(
            name="trial_agent",
            entity_type="trial",
            description="Monitors ClinicalTrials.gov for new and updated trials",
            sources=["clinical_trials_gov"],
            scripts=[],  # uses scheduler.run_one() instead
            schedule_hours=24,  # daily
            use_scheduler=True,
        ),
        EntityAgentConfig(
            name="drug_agent",
            entity_type="drug",
            description="Maintains drug completeness — mechanism, approval_date, brand_name",
            sources=["fda_orange_book", "openfda_labels"],
            scripts=[
                ("scripts.enrich_drugs", "run"),
                ("scripts.backfill_mechanisms", "run"),
                ("scripts.clean_drug_names", "run"),
            ],
            schedule_hours=24,
        ),
        EntityAgentConfig(
            name="company_agent",
            entity_type="company",
            description="Maintains company data — dedup, enrichment, SEC filings",
            sources=["sec_edgar"],
            scripts=[
                ("scripts.dedup_companies", "run"),
                ("scripts.enrich_companies", "run"),
            ],
            schedule_hours=168,  # weekly
        ),
    ]

    def __init__(self, db: Database):
        self.db = db
        self.agents = [EntityAgent(cfg, db) for cfg in self.AGENT_CONFIGS]

    def run_all(self, dry_run: bool = False) -> dict:
        """Run all enabled agents. Returns combined summary."""
        t0 = time.monotonic()
        agent_results = []
        completed = 0
        failed = 0

        for agent in self.agents:
            if not agent.config.enabled:
                agent_results.append({
                    "agent": agent.config.name,
                    "status": "disabled",
                })
                continue

            try:
                result = agent.run(dry_run=dry_run)
                agent_results.append(result)
                if result.get("errors", 0) == 0:
                    completed += 1
                else:
                    # Partial success still counts as completed
                    completed += 1
            except Exception as e:
                logger.warning("Agent %s failed: %s", agent.config.name, e)
                agent_results.append({
                    "agent": agent.config.name,
                    "status": "failed",
                    "error": str(e)[:500],
                })
                failed += 1

        elapsed = round(time.monotonic() - t0, 2)
        return {
            "agents": agent_results,
            "completed": completed,
            "failed": failed,
            "total_elapsed_s": elapsed,
        }

    def run_one(self, agent_name: str, dry_run: bool = False) -> dict:
        """Run a single agent by name."""
        for agent in self.agents:
            if agent.config.name == agent_name:
                return agent.run(dry_run=dry_run)
        raise ValueError(f"Unknown agent: {agent_name}")

    def list_agents(self) -> list[dict]:
        """Return agent configs as dicts for API."""
        return [
            {
                "name": cfg.name,
                "entity_type": cfg.entity_type,
                "description": cfg.description,
                "sources": cfg.sources,
                "scripts": [s[0] for s in cfg.scripts],
                "schedule_hours": cfg.schedule_hours,
                "enabled": cfg.enabled,
                "use_scheduler": cfg.use_scheduler,
            }
            for cfg in self.AGENT_CONFIGS
        ]
