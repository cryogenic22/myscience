"""Data Pipeline Scheduler — runs connectors on cron schedules.

Usage:
    from scheduler import DataPipelineScheduler
    sched = DataPipelineScheduler()
    sched.start()           # daemon mode
    sched.run_now()         # one-shot all connectors
    sched.run_one("pubmed") # one-shot single connector
"""

from __future__ import annotations

import logging
import signal
import threading
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config import config as app_config
from connectors import get_connector, CONNECTOR_REGISTRY
from connectors.base import SourceType
from connectors.base import SourceType
from db import Database
from integration.pipeline import IntegrationPipeline
from scheduler.config import CONNECTOR_SCHEDULES, RUN_ORDER

logger = logging.getLogger(__name__)


class DataPipelineScheduler:
    """Wraps APScheduler to periodically run ETL connectors."""

    def __init__(self):
        self._scheduler = BackgroundScheduler(timezone="UTC")
        self._stop_event = threading.Event()
        # Batch counters for chunked connectors (persists across runs within one process)
        self._batch_counters: dict[str, int] = {}

    # ── Public API ──

    def start(self) -> None:
        """Start the scheduler in daemon mode. Blocks until SIGINT/SIGTERM."""
        self._register_jobs()
        self._scheduler.start()
        logger.info("Pipeline scheduler started. Press Ctrl+C to stop.")

        # Handle graceful shutdown
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        self._stop_event.wait()
        self._scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped.")

    def stop(self) -> None:
        """Signal the scheduler to stop."""
        self._stop_event.set()

    def run_now(self) -> dict[str, str]:
        """Run all connectors once in order, then post-run tasks. Returns source -> status map."""
        results = {}
        for source_type in RUN_ORDER:
            name = source_type.value
            try:
                self._run_connector(source_type)
                results[name] = "OK"
            except Exception as e:
                logger.exception("Failed: %s", name)
                results[name] = f"ERROR: {e}"

        # Post-run: cross-source linkage and quality fixes
        self._run_post_tasks(results)
        return results

    def _run_post_tasks(self, results: dict[str, str]) -> None:
        """Run post-pipeline tasks: backfill linkage, quality fixes, view refresh."""
        import importlib
        import time

        logger.info("--- Running post-pipeline data curation ---")

        # 1. Backfill linkage (OWNS, IN_THERAPEUTIC_AREA, TARGETS_MECHANISM, SPONSORS)
        try:
            t0 = time.time()
            mod = importlib.import_module("backfill_data_linkage")
            mod.run()
            results["backfill_linkage"] = f"OK ({time.time()-t0:.1f}s)"
            logger.info("Post-task: backfill_linkage completed")
        except Exception as e:
            logger.exception("Post-task backfill_linkage failed")
            results["backfill_linkage"] = f"ERROR: {e}"

        # 2. Data quality fix (literature-drug match, CV/HF TA, quality scores, view refresh)
        try:
            t0 = time.time()
            mod = importlib.import_module("fix_data_quality")
            mod.run()
            results["fix_data_quality"] = f"OK ({time.time()-t0:.1f}s)"
            logger.info("Post-task: fix_data_quality completed")
        except Exception as e:
            logger.exception("Post-task fix_data_quality failed")
            results["fix_data_quality"] = f"ERROR: {e}"

        # 3. TA linkage backfill
        try:
            t0 = time.time()
            mod = importlib.import_module("scripts.backfill_ta_links")
            mod.run()
            results["backfill_ta_links"] = f"OK ({time.time()-t0:.1f}s)"
            logger.info("Post-task: backfill_ta_links completed")
        except Exception as e:
            logger.exception("Post-task backfill_ta_links failed")
            results["backfill_ta_links"] = f"ERROR: {e}"

        # 4. Company dedup
        try:
            t0 = time.time()
            mod = importlib.import_module("scripts.dedup_companies")
            mod.run()
            results["dedup_companies"] = f"OK ({time.time()-t0:.1f}s)"
            logger.info("Post-task: dedup_companies completed")
        except Exception as e:
            logger.exception("Post-task dedup_companies failed")
            results["dedup_companies"] = f"ERROR: {e}"

        # 5. Quality scorecard
        try:
            t0 = time.time()
            mod = importlib.import_module("scripts.quality_scorecard")
            mod.run(output_path="reports/quality_scorecard.md")
            results["quality_scorecard"] = f"OK ({time.time()-t0:.1f}s)"
            logger.info("Post-task: quality_scorecard completed")
        except Exception as e:
            logger.exception("Post-task quality_scorecard failed")
            results["quality_scorecard"] = f"ERROR: {e}"

        # 6. Auto-curate pipeline (mechanism backfill, competition derivation, etc.)
        try:
            t0 = time.time()
            mod = importlib.import_module("scripts.auto_curate")
            curate_result = mod.run(dry_run=False, skip_ai=True)
            results["auto_curate"] = f"OK ({time.time()-t0:.1f}s)"
            logger.info("Post-task: auto_curate completed")
        except Exception as e:
            logger.exception("Post-task auto_curate failed")
            results["auto_curate"] = f"ERROR: {e}"

        # 6b. Auto-curate v2 (SEC enrichment, orphan linking, resolution sweep, HITL, FAIR)
        try:
            t0 = time.time()
            mod = importlib.import_module("scripts.auto_curate_v2")
            v2_results = mod.run_all_curation(self.db)
            total = sum(r.get('enriched', r.get('resolved', r.get('linked', 0))) for r in v2_results)
            results["auto_curate_v2"] = f"OK — {total} items ({time.time()-t0:.1f}s)"
            logger.info("Post-task: auto_curate_v2 completed — %d items", total)
        except Exception as e:
            logger.exception("Post-task auto_curate_v2 failed")
            results["auto_curate_v2"] = f"ERROR: {e}"

        # 7. Data Steward loop (signal-driven autonomous curation)
        try:
            t0 = time.time()
            from services.steward_signals import StewardSignalCollector
            from services.data_steward import DataSteward, StewardConfig

            steward_db = Database(app_config.db.dsn)
            steward_db.connect()
            try:
                collector = StewardSignalCollector(steward_db)
                steward = DataSteward(
                    steward_db, collector,
                    StewardConfig(max_iterations=10, skip_ai=True),
                )
                summary = steward.run_loop()
                results["data_steward"] = (
                    f"OK: {summary.completed} completed, "
                    f"{summary.feedback_resolved} feedback resolved "
                    f"({time.time()-t0:.1f}s)"
                )
                logger.info("Post-task: data_steward completed — %s", results["data_steward"])
            finally:
                steward_db.close()
        except Exception as e:
            logger.exception("Post-task data_steward failed")
            results["data_steward"] = f"ERROR: {e}"

        # 8. Signal promotion (market_events → candidate signals)
        try:
            t0 = time.time()
            from services.signal_promoter import promote_events

            promo_db = Database(app_config.db.dsn)
            promo_db.connect()
            try:
                promo = promote_events(promo_db, limit=2000)
                results["signal_promotion"] = (
                    f"OK: {promo.promoted} promoted, "
                    f"{promo.skipped_existing} existing, "
                    f"{promo.skipped_no_entity} no-entity "
                    f"({time.time()-t0:.1f}s)"
                )
                logger.info("Post-task: signal_promotion — %s", results["signal_promotion"])
            finally:
                promo_db.close()
        except Exception as e:
            logger.exception("Post-task signal_promotion failed")
            results["signal_promotion"] = f"ERROR: {e}"

        # 9. Fact convergence (market_events → facts ledger) — PB-H17. The
        # scheduler already converges events → signals (task 8); this is the
        # missing events → facts step that keeps the spine's ledger current so
        # dossiers + scenarios stay grounded in fresh facts. Reuses the proven,
        # idempotent backfill (services/fact_ingest); bounded to recent events.
        try:
            t0 = time.time()
            results["fact_convergence"] = (
                self._run_fact_convergence(since_days=7) + f" ({time.time()-t0:.1f}s)"
            )
            logger.info("Post-task: fact_convergence — %s", results["fact_convergence"])
        except Exception as e:
            logger.exception("Post-task fact_convergence failed")
            results["fact_convergence"] = f"ERROR: {e}"

        # 10. Fact emitters (entity tables → facts ledger) — DR-8 / Epic E19.
        # Lifts clinical_trials / adverse_events / drug_labels into the ledger
        # so dossiers carry granular clinical evidence, not just the
        # market_event monoculture. Bounded + idempotent (skips on
        # source_row_id), so each cycle only asserts genuinely new rows. Reuses
        # services.fact_emitters; own connection (long sweeps risk a Railway
        # proxy drop). For a full cross-drug catch-up run
        # scripts/backfill_fact_emitters instead.
        try:
            t0 = time.time()
            results["fact_emitters"] = (
                self._run_fact_emitters(limit=200) + f" ({time.time()-t0:.1f}s)"
            )
            logger.info("Post-task: fact_emitters — %s", results["fact_emitters"])
        except Exception as e:
            logger.exception("Post-task fact_emitters failed")
            results["fact_emitters"] = f"ERROR: {e}"

        # 11. Scenario calibration (signals → scenario current_prob) — PB-H14.
        # The Learn-loop vertebra: re-weights each live scenario's structural
        # prior into a current probability from fresh signals about its focal
        # entity, recording a calibration_note. Idempotent (recomputes from
        # prior each cycle). Own connection.
        try:
            t0 = time.time()
            results["scenario_calibration"] = (
                self._run_scenario_calibration() + f" ({time.time()-t0:.1f}s)"
            )
            logger.info("Post-task: scenario_calibration — %s", results["scenario_calibration"])
        except Exception as e:
            logger.exception("Post-task scenario_calibration failed")
            results["scenario_calibration"] = f"ERROR: {e}"

        # 12. Learning service (decisions → source accuracy + prompt flags) —
        # C4 / SPEC-032. EWMA-updates sources.predictive_accuracy from
        # decision calibration scores and flags low-calibration prompt
        # versions. Idempotent via a since-cursor (advances per successful
        # run); writes a learning_service_runs row every cycle. Own connection.
        try:
            t0 = time.time()
            results["learning_service"] = (
                self._run_learning_service() + f" ({time.time()-t0:.1f}s)"
            )
            logger.info("Post-task: learning_service — %s", results["learning_service"])
        except Exception as e:
            logger.exception("Post-task learning_service failed")
            results["learning_service"] = f"ERROR: {e}"

        # 13. Concept-weight adjuster (query telemetry → concept weights) —
        # C5. Correlates per-intent answer quality (confidence + evidence)
        # with concept activations and nudges concept weights ±10%/cycle.
        # Conservative + clamped; no-op when telemetry is thin. Own connection.
        try:
            t0 = time.time()
            results["concept_weight_adjuster"] = (
                self._run_concept_weight_adjuster() + f" ({time.time()-t0:.1f}s)"
            )
            logger.info(
                "Post-task: concept_weight_adjuster — %s",
                results["concept_weight_adjuster"],
            )
        except Exception as e:
            logger.exception("Post-task concept_weight_adjuster failed")
            results["concept_weight_adjuster"] = f"ERROR: {e}"

        logger.info("--- Post-pipeline data curation complete ---")

    def _run_learning_service(self) -> str:
        """Run the EWMA source-accuracy + prompt-flag learning loop (C4).
        Writes a learning_service_runs row. Own connection."""
        from services.learning_service import LearningService

        db = Database(app_config.db.dsn)
        db.connect()
        try:
            result = LearningService().run(db, started_by_user_id=None)
            return (
                f"OK: run {result.run_id} status={result.status}, "
                f"{result.decisions_processed} decisions, "
                f"{result.sources_updated} sources, "
                f"{result.prompts_flagged} prompts flagged"
            )
        finally:
            db.close()

    def _run_concept_weight_adjuster(self) -> str:
        """Tune concept weights from query telemetry (C5). Own connection."""
        from services.concept_weight_adjuster import ConceptWeightAdjuster
        from services.concept_registry import ConceptRegistry

        db = Database(app_config.db.dsn)
        db.connect()
        try:
            registry = ConceptRegistry(db=db)
            report = ConceptWeightAdjuster(db, registry).analyze_and_adjust(lookback_days=7)
            return (
                f"OK: analyzed {report.analyzed_queries} queries, "
                f"{report.concepts_adjusted} concepts adjusted"
            )
        finally:
            db.close()

    def _run_scenario_calibration(self) -> str:
        """Re-weight live scenarios from new signals (PB-H14). Own connection."""
        from services.scenario_calibration import calibrate_all_engagements

        db = Database(app_config.db.dsn)
        db.connect()
        try:
            stats = calibrate_all_engagements(db, limit=200)
            return f"OK: {stats['scenarios_updated']} updated across {stats['engagements']} engagements"
        finally:
            db.close()

    def _run_fact_emitters(self, limit: int = 200) -> str:
        """Converge recent entity rows into the facts ledger (DR-8). Mirrors
        fact_convergence; bounded per emitter, idempotent. Own connection."""
        from services.fact_emitters.base import run_all_emitters

        db = Database(app_config.db.dsn)
        db.connect()
        try:
            stats = run_all_emitters(db, limit=limit)
            return "OK: " + ", ".join(
                f"{name}={s.asserted}a/{s.skipped_existing}e"
                for name, s in stats.items()
            )
        finally:
            db.close()

    def _run_fact_convergence(self, since_days: int = 7) -> str:
        """Converge recent market_events into the facts ledger (PB-H17).
        Mirrors signal promotion (events → signals); this is events → facts.
        Reuses services.fact_ingest.backfill_facts_from_events — idempotent, so
        re-runs only assert genuinely new facts. Own connection (long sweeps on
        the shared one risk the Railway proxy dropping it)."""
        from services.fact_ingest import backfill_facts_from_events

        db = Database(app_config.db.dsn)
        db.connect()
        try:
            stats = backfill_facts_from_events(db, since_days=since_days)
            return (
                f"OK: {stats.asserted} asserted, "
                f"{stats.skipped_existing} existing, "
                f"{stats.skipped_no_subject} no-subject"
            )
        finally:
            db.close()

    def run_one(self, source_name: str) -> str:
        """Run a single connector by name (e.g. 'pubmed', 'clinical_trials_gov')."""
        source_type = self._resolve_source(source_name)
        if not source_type:
            return f"Unknown connector: {source_name}. Available: {[s.value for s in CONNECTOR_REGISTRY]}"
        try:
            self._run_connector(source_type)
            return "OK"
        except Exception as e:
            logger.exception("Failed: %s", source_name)
            return f"ERROR: {e}"

    def status(self) -> list[dict]:
        """Return last run info for each connector from etl_runs."""
        db = Database(app_config.db.dsn)
        db.connect()
        try:
            rows = db.fetch_all("""
                SELECT DISTINCT ON (source_name)
                    source_name,
                    status,
                    started_at,
                    completed_at,
                    records_processed,
                    records_inserted,
                    records_updated,
                    error_message
                FROM etl_runs
                ORDER BY source_name, started_at DESC
            """)
            return [dict(r) for r in rows] if rows else []
        finally:
            db.close()

    # ── Internals ──

    def _register_jobs(self) -> None:
        """Add a cron job for each connector."""
        for source_type, schedule in CONNECTOR_SCHEDULES.items():
            trigger = CronTrigger(**schedule["cron"])
            self._scheduler.add_job(
                self._run_connector,
                trigger=trigger,
                args=[source_type],
                id=source_type.value,
                name=schedule["label"],
                replace_existing=True,
                misfire_grace_time=3600,  # 1 hour grace for misfires
            )
            logger.info(
                "Registered: %s → cron %s",
                schedule["label"],
                schedule["cron"],
            )

    def _run_connector(self, source_type: SourceType) -> None:
        """Execute a single connector through the full pipeline."""
        name = source_type.value
        logger.info("--- Starting %s ---", name)

        db = Database(app_config.db.dsn)
        db.connect()

        try:
            # Determine incremental start time
            since = self._get_last_success(db, name)
            if since:
                logger.info("Incremental mode: since %s", since.isoformat())
            else:
                logger.info("Full mode (no prior successful run found)")

            # Instantiate connector — chunked connectors get batch_index,
            # molecular connectors get dynamic drug list from DB
            chunked_sources = {SourceType.OPENFDA_FAERS, SourceType.OPENFDA_LABELS}
            molecular_sources = {SourceType.CHEMBL, SourceType.PUBCHEM, SourceType.OPEN_TARGETS}
            target_overrides = None
            if source_type in chunked_sources:
                batch_key = source_type.value
                batch_idx = self._batch_counters.get(batch_key, 0)
                target_overrides = {"batch_index": batch_idx}
                self._batch_counters[batch_key] = batch_idx + 1
                logger.info("Chunked mode: batch_index=%d for %s", batch_idx, name)
            elif source_type in molecular_sources:
                # Fetch top drugs by pipeline_score for molecular enrichment
                try:
                    top_drugs = db.fetch_all(
                        """SELECT d.generic_name, COUNT(el.id) AS link_count
                           FROM drugs d
                           JOIN entity_links el ON el.source_entity_id = d.id::text
                              OR el.target_entity_id = d.id::text
                           WHERE d.generic_name IS NOT NULL
                             AND LENGTH(d.generic_name) BETWEEN 4 AND 30
                             AND d.generic_name ~ %s
                             AND (d.record_status IS NULL OR d.record_status NOT IN ('excluded', 'merged'))
                           GROUP BY d.generic_name
                           ORDER BY link_count DESC
                           LIMIT 50""",
                        [r'^[a-zA-Z]'],
                    )
                    drug_names = [r["generic_name"] for r in top_drugs if r["generic_name"]]
                    if drug_names:
                        target_overrides = {"drugs": drug_names}
                        logger.info("Dynamic drug list: %d drugs for %s", len(drug_names), name)
                except Exception:
                    logger.debug("Could not fetch dynamic drug list for %s", name)
            try:
                if target_overrides:
                    connector = get_connector(source_type, config=app_config, target_overrides=target_overrides)
                else:
                    connector = get_connector(source_type, config=app_config)
            except TypeError:
                # Some connectors (e.g. MeSH) don't accept config kwarg
                connector = get_connector(source_type)
            pipeline = IntegrationPipeline(db, app_config)
            result = pipeline.run(connector, since=since)

            logger.info(
                "--- Completed %s: processed=%d inserted=%d updated=%d unchanged=%d failed=%d ---",
                name,
                result.records_processed,
                result.records_inserted,
                result.records_updated,
                result.records_unchanged,
                result.records_failed,
            )
            if result.errors:
                for err in result.errors[:5]:
                    logger.warning("  error: %s", err)
        finally:
            db.close()

    def _get_last_success(self, db: Database, source_name: str) -> Optional[datetime]:
        """Query etl_runs for the last successful completion timestamp."""
        row = db.fetch_one(
            """
            SELECT completed_at
            FROM etl_runs
            WHERE source_name = %s AND status = 'SUCCESS'
            ORDER BY completed_at DESC
            LIMIT 1
            """,
            [source_name],
        )
        if row and row.get("completed_at"):
            ts = row["completed_at"]
            # Ensure timezone-aware
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return ts
        return None

    def _resolve_source(self, name: str) -> Optional[SourceType]:
        """Resolve a string name to a SourceType enum."""
        name_lower = name.lower().strip()
        for st in SourceType:
            if st.value == name_lower:
                return st
        # Also try partial match
        for st in SourceType:
            if name_lower in st.value:
                return st
        return None

    def _handle_signal(self, signum, frame):
        logger.info("Received signal %s, shutting down...", signum)
        self.stop()
