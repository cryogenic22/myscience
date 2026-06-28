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

    # Hours an etl_runs row may stay RUNNING before the reaper treats it as an
    # orphan from a killed process and marks it FAILED. The pipeline always
    # sets a terminal status in its try/except, so a row older than this that is
    # still RUNNING means the process died mid-run (Railway restart / proxy
    # drop). Mirrors scripts.connector_health.STUCK_RUNNING_HOURS.
    STUCK_RUNNING_HOURS = 12

    def reap_stuck_runs(self, db: "Database", hours: int | None = None) -> int:
        """Mark orphaned RUNNING etl_runs (older than `hours`) as FAILED.

        Idempotent + additive: only touches rows still RUNNING past the
        threshold, so re-running is a no-op once they're reaped. Without this a
        process kill leaves a permanent RUNNING row that makes the source look
        perpetually stuck in the health scorecard and can mislead the
        incremental-since cursor. Returns the number reaped.
        """
        hours = hours or self.STUCK_RUNNING_HOURS
        try:
            rows = db.fetch_all(
                """
                UPDATE etl_runs
                SET status = 'FAILED',
                    completed_at = NOW(),
                    error_message = COALESCE(error_message,
                        'reaped: stuck RUNNING >' || %s || 'h (process killed mid-run)')
                WHERE status = 'RUNNING'
                  AND started_at < NOW() - (%s || ' hours')::interval
                RETURNING id
                """,
                [hours, hours],
            )
            n = len(rows) if rows else 0
            if n:
                logger.warning("Reaped %d stuck-RUNNING etl_runs (>%dh)", n, hours)
            return n
        except Exception:
            logger.exception("reap_stuck_runs failed")
            return 0

    def run_now(self) -> dict[str, str]:
        """Run all connectors once in order, then post-run tasks. Returns source -> status map."""
        results = {}
        # Clear orphaned RUNNING rows from prior killed processes first so the
        # incremental-since cursor and the health scorecard see clean state.
        reap_db = Database(app_config.db.dsn)
        reap_db.connect()
        try:
            reaped = self.reap_stuck_runs(reap_db)
            if reaped:
                results["reaped_stuck_runs"] = str(reaped)
        finally:
            reap_db.close()
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

        # 2b. NADAC pricing — load the current weekly CMS snapshot into drug_pricing
        # (idempotent ON CONFLICT, so re-running each cycle accumulates price history
        # without dupes). NADAC is a pricing source, not an entity source, so it loads
        # here rather than through the entity pipeline.
        try:
            t0 = time.time()
            mod = importlib.import_module("scripts.fetch_nadac_pricing")
            stats = mod.run()
            results["fetch_nadac_pricing"] = (
                f"OK stored={stats.get('stored', 0)} matched={stats.get('matched', 0)} "
                f"({time.time()-t0:.1f}s)"
            )
            logger.info("Post-task: fetch_nadac_pricing completed: %s", stats)
        except Exception as e:
            logger.exception("Post-task fetch_nadac_pricing failed")
            results["fetch_nadac_pricing"] = f"ERROR: {e}"

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

        # 6b. Auto-curate v2 (SEC enrichment, orphan linking, resolution sweep,
        # HITL, FAIR). Factored into _run_auto_curate_v2 so the LIVE scheduler can
        # run it on a cadence (see _register_jobs) and so it gets its OWN
        # connection — the prior inline call passed self.db, which this class never
        # sets, so step 6b raised AttributeError every cycle and v2 ran on NO
        # scheduler path (only on a manual /enrichment POST).
        try:
            t0 = time.time()
            results["auto_curate_v2"] = (
                self._run_auto_curate_v2() + f" ({time.time()-t0:.1f}s)"
            )
            logger.info("Post-task: auto_curate_v2 — %s", results["auto_curate_v2"])
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

        # 8. Sensing promotion (events→signals + facts→signals + signal entity
        # resolve). Factored into _run_sensing_promotion so the LIVE scheduler can
        # run it on its own cadence (see _register_jobs) — the live app drives
        # _register_jobs() but never the manual run_now() that holds this block, so
        # without the scheduled job the signal feed stalls. Reuses the existing
        # promote_events / mint_signals_from_facts / relink_market_signals
        # functions in ONE place — no duplication, no third post-task path.
        self._run_sensing_promotion(results)

        # 9+10. Ledger convergence — events → facts (PB-H17) + entity-tables →
        # facts (DR-8 / Epic E19). Factored into _run_ledger_convergence so the
        # LIVE scheduler can run it on its own cadence (see _register_jobs) — the
        # live app drives _register_jobs() but never this run_now() block, so
        # without the scheduled job the facts + evidence ledgers froze (27-Jun
        # probe: 0 new in 12 days while ingest stayed fresh). Same defect + fix
        # shape as the sensing promotion above. Writes results["fact_convergence"]
        # + results["fact_emitters"] exactly as before — no behaviour change here.
        self._run_ledger_convergence(results)

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

        # 14. Reground market_events (drug_id/free-text → primary_entity_*) — D2.
        # Keeps the event spine grounded so the dossier/feed can cite them.
        # Additive + idempotent (only NULL-primary rows). The drug_id-derive
        # pass is set-based and cheap; the free-text pass is bounded. Own
        # connection (the derive UPDATE can touch many rows).
        try:
            t0 = time.time()
            results["event_reground"] = (
                self._run_event_reground() + f" ({time.time()-t0:.1f}s)"
            )
            logger.info("Post-task: event_reground — %s", results["event_reground"])
        except Exception as e:
            logger.exception("Post-task event_reground failed")
            results["event_reground"] = f"ERROR: {e}"

        logger.info("--- Post-pipeline data curation complete ---")

    def _run_sensing_promotion(self, results: Optional[dict] = None) -> dict:
        """Turn landed events + facts into entity-resolved signals — the SENSE
        conversion. "The signal is a lens, not a store" (sensing-layer spec): a
        signal is a fact/event the sense layer scored + surfaced. These three
        idempotent functions are the ONLY events→signals / facts→signals /
        signal-entity-resolve path, and were reachable only via the on-demand
        run_now() (promote), document upload (mint), or CLI (relink) — so the live
        feed stalled (15-Jun gap analysis: signals 11d stale). _register_jobs
        schedules this so it runs on a cadence in prod (the live app drives
        _register_jobs, not run_now). Each function gets its own short-lived
        connection (long sweeps risk a Railway proxy drop), mirroring the other
        post-tasks. Safe standalone (results defaults to a fresh dict)."""
        import time
        out = results if results is not None else {}

        # events → candidate signals. event_types restricts to the signal-worthy
        # set so the pass targets the ~1.4k high-significance events, NOT the 96%
        # RECALL_CLASS_I flood (an unfiltered promote burns its limit on recall
        # noise before reaching trial readouts/approvals — 15-Jun gap analysis).
        try:
            t0 = time.time()
            from services.signal_promoter import promote_events, HIGH_SIGNIFICANCE_EVENT_TYPES
            db = Database(app_config.db.dsn)
            db.connect()
            try:
                promo = promote_events(db, limit=2000,
                                       event_types=list(HIGH_SIGNIFICANCE_EVENT_TYPES))
                out["signal_promotion"] = (
                    f"OK: {promo.promoted} promoted, {promo.skipped_existing} existing, "
                    f"{promo.skipped_no_entity} no-entity ({time.time()-t0:.1f}s)"
                )
            finally:
                db.close()
            logger.info("Sensing: signal_promotion — %s", out["signal_promotion"])
        except Exception as e:
            logger.exception("Sensing signal_promotion failed")
            out["signal_promotion"] = f"ERROR: {e}"

        # facts → signals (signal-worthy, evidence-backed facts; links via signal_facts)
        try:
            t0 = time.time()
            from services.fact_signals import mint_signals_from_facts
            db = Database(app_config.db.dsn)
            db.connect()
            try:
                mint = mint_signals_from_facts(db)
                out["fact_signal_mint"] = (
                    f"OK: {mint.minted} minted / {mint.scanned} scanned ({time.time()-t0:.1f}s)"
                )
            finally:
                db.close()
            logger.info("Sensing: fact_signal_mint — %s", out["fact_signal_mint"])
        except Exception as e:
            logger.exception("Sensing fact_signal_mint failed")
            out["fact_signal_mint"] = f"ERROR: {e}"

        # resolve 'market'-bucketed signals to canonical entities (unblocks Watchlist/KBQ)
        try:
            t0 = time.time()
            from services.signal_promoter import relink_market_signals
            db = Database(app_config.db.dsn)
            db.connect()
            try:
                relinked = relink_market_signals(db)
                out["signal_relink"] = f"OK: {relinked} ({time.time()-t0:.1f}s)"
            finally:
                db.close()
            logger.info("Sensing: signal_relink — %s", out["signal_relink"])
        except Exception as e:
            logger.exception("Sensing signal_relink failed")
            out["signal_relink"] = f"ERROR: {e}"

        return out

    def _run_ledger_convergence(self, results: Optional[dict] = None) -> dict:
        """Converge fresh ingest into the FACTS LEDGER on a cadence — the spine's
        refresh. Two idempotent, bounded steps: market_events → facts
        (_run_fact_convergence) and entity-tables → facts (_run_fact_emitters).
        Reachable before this only via the on-demand run_now() post-task block,
        which the live app never calls (it drives _register_jobs, not run_now) —
        so on prod the facts + evidence ledgers froze (27-Jun probe: 0 new in 12
        days while ingest stayed fresh). _register_jobs schedules this so the
        ledger every "lens over the store" reads stays current. Identical defect
        + fix shape as _run_sensing_promotion (15-Jun). Each step is independently
        try/except'd (one failure must not abort the other); the underlying
        methods open their own short-lived connection. Safe standalone (results
        defaults to a fresh dict), and run_now threads its own dict through so its
        output is unchanged."""
        import time
        out = results if results is not None else {}

        # market_events → facts ledger (PB-H17)
        try:
            t0 = time.time()
            out["fact_convergence"] = (
                self._run_fact_convergence(since_days=7) + f" ({time.time()-t0:.1f}s)"
            )
            logger.info("Ledger: fact_convergence — %s", out["fact_convergence"])
        except Exception as e:
            logger.exception("Ledger fact_convergence failed")
            out["fact_convergence"] = f"ERROR: {e}"

        # entity tables → facts ledger (DR-8 / Epic E19)
        try:
            t0 = time.time()
            out["fact_emitters"] = (
                self._run_fact_emitters(limit=200) + f" ({time.time()-t0:.1f}s)"
            )
            logger.info("Ledger: fact_emitters — %s", out["fact_emitters"])
        except Exception as e:
            logger.exception("Ledger fact_emitters failed")
            out["fact_emitters"] = f"ERROR: {e}"

        # facts → evidence link (D5). CONSERVATION-CRITICAL: fact_convergence
        # asserts event-derived facts with source_doc_id NULL (provenance lives in
        # object_value.source_url/description until an evidence_record is written).
        # Evidence-linking was historically a manual one-off — so emitting facts on
        # a cadence WITHOUT this step degrades the ≥0.98 evidence floor every cycle
        # (proven on prod: a bare convergence run dropped it 99.99%→97.04%). This
        # additive+idempotent step writes the evidence_record + sets source_doc_id,
        # keeping the floor green and un-freezing the evidence ledger in lockstep.
        try:
            t0 = time.time()
            out["evidence_backfill"] = (
                self._run_evidence_backfill(limit=2000) + f" ({time.time()-t0:.1f}s)"
            )
            logger.info("Ledger: evidence_backfill — %s", out["evidence_backfill"])
        except Exception as e:
            logger.exception("Ledger evidence_backfill failed")
            out["evidence_backfill"] = f"ERROR: {e}"

        return out

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

    def _run_event_reground(self) -> str:
        """Reground orphaned market_events to the entity spine (D2). Own
        connection; additive + idempotent."""
        from scripts.reground_market_events import reground

        db = Database(app_config.db.dsn)
        db.connect()
        try:
            stats = reground(db, text_limit=500)
            return (
                f"OK: {stats['derived_from_drug_id']} from drug_id, "
                f"{stats['resolved_from_text']} from text, "
                f"NULL-primary {stats['null_primary_before']}→{stats['null_primary_after']}"
            )
        finally:
            db.close()

    def _run_auto_curate_v2(self) -> str:
        """Run auto-curation v2's five deterministic passes — SEC EDGAR
        enrichment, orphan-company linking, resolution sweep, HITL auto-resolve,
        FAIR score (scripts.auto_curate_v2.run_all_curation). Own short-lived
        connection: the prior inline call passed self.db, which
        DataPipelineScheduler never sets, so the step raised AttributeError every
        cycle and v2 ran on NO scheduler path (only on a manual /enrichment POST).
        Idempotent (the passes dedup), so the scheduled cadence and run_now share
        this one path. Returns an OK summary; the caller times + records it."""
        from scripts.auto_curate_v2 import run_all_curation

        db = Database(app_config.db.dsn)
        db.connect()
        try:
            v2_results = run_all_curation(db)
            total = sum(
                r.get("enriched", r.get("resolved", r.get("linked", 0)))
                for r in v2_results
            )
            return f"OK — {total} items across {len(v2_results)} passes"
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

    def _run_evidence_backfill(self, limit: int = 2000) -> str:
        """Link NULL-source_doc_id facts to evidence (D5). The conservation
        completion of fact emission: fact_convergence asserts event-facts whose
        provenance sits in object_value (source_url/description) but with
        source_doc_id NULL; this writes the dedup'd evidence_record and sets
        source_doc_id, so the ledger holds the ≥0.98 evidence floor. Additive +
        idempotent (skips already-linked / genuinely-sourceless facts); bounded by
        the NULL backlog (steady-state tiny). Own connection."""
        from scripts.backfill_evidence import run as backfill_evidence

        db = Database(app_config.db.dsn)
        db.connect()
        try:
            stats = backfill_evidence(db, limit=limit)
            return (
                f"OK: {stats['linked']} linked, "
                f"{stats['skipped_no_text']} sourceless, "
                f"{stats['evidence_failed']} failed"
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

        # Sensing promotion — events+facts → entity-resolved signals, on a cadence.
        # The live app drives _register_jobs() (api/app.py) but never the manual
        # run_now() that holds the post-task block, so the signal feed otherwise
        # only updates on manual endpoint hits / document uploads (15-Jun gap
        # analysis: signals 11d stale). Idempotent; every 6h. No api/app.py edit
        # needed — registering here means the live scheduler picks it up.
        self._scheduler.add_job(
            self._run_sensing_promotion,
            trigger=CronTrigger(hour="*/6"),
            id="sensing_promotion",
            name="Sensing promotion (events+facts → signals)",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info("Registered: Sensing promotion → cron every 6h")

        # Ledger convergence — events+entities → FACTS ledger, on a cadence. Same
        # defect as sensing: the converters (fact_convergence + fact_emitters)
        # lived only in the run_now() post-task block, which the live app never
        # calls, so facts + evidence froze on prod (27-Jun probe: 0 new in 12d
        # while ingest stayed fresh). Idempotent + bounded; every 6h, minute 20 to
        # stagger off sensing (minute 0) and the connector window. Eventual-
        # consistent with the fact→signal mint — the next sensing cycle picks up
        # facts asserted here. The Lane-2 freshness watch over this (wiring
        # LEDGER_FRESHNESS_SLA_DAYS into connector_health) is a follow-up — see
        # that constant's note.
        self._scheduler.add_job(
            self._run_ledger_convergence,
            trigger=CronTrigger(hour="*/6", minute=20),
            id="ledger_convergence",
            name="Ledger convergence (events+entities → facts)",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info("Registered: Ledger convergence → cron every 6h")

        # Auto-curate v2 — SEC enrichment + orphan linking + resolution sweep +
        # HITL + FAIR, on a cadence. Same defect class as sensing/ledger: the five
        # passes lived only in run_now()'s post-task block (and there crashed on
        # self.db — see _run_auto_curate_v2), so v2 ran on NO automatic path, only
        # on a manual /enrichment POST. Heaviest of the periodic jobs (external SEC
        # fetch + a 1000-row resolution sweep), so DAILY rather than 6-hourly, and
        # off-peak (04:40 UTC) to stagger off sensing (minute 0) + ledger (minute
        # 20) + the connector windows. Idempotent; the next sensing/ledger cycle
        # eventual-consistently picks up entities it resolves/enriches.
        self._scheduler.add_job(
            self._run_auto_curate_v2,
            trigger=CronTrigger(hour=4, minute=40),
            id="auto_curate_v2",
            name="Auto-curate v2 (SEC enrich + orphan link + resolution sweep + FAIR)",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info("Registered: Auto-curate v2 → cron daily 04:40 UTC")

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
