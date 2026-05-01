"""FastAPI application factory for Market-Zero."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from api.deps import get_db
from db import Database
from api.routes import search, metrics, graph, query, entities, chat, therapeutic_areas, catalog, enrichment, pricing, scenarios

logger = logging.getLogger(__name__)

# New routers — import with fallback to avoid blocking startup
try:
    from api.routes import feedback, steward, literature, intelligence, agent
    _NEW_ROUTERS_OK = True
except Exception as _e:
    logger.error("Failed to import new routers (feedback/steward/literature/intelligence/agent): %s", _e)
    _NEW_ROUTERS_OK = False

# SPEC_014 upload router — separate try block so other routers stay live if
# document deps (pdfplumber/python-docx) are missing in some envs.
try:
    from api.routes import upload as upload_route
    _UPLOAD_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import upload router (SPEC_014): %s", _e)
    _UPLOAD_ROUTER_OK = False

# SPEC_018 auth router (login + me)
try:
    from api.routes import auth as auth_route
    _AUTH_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import auth router (SPEC_018): %s", _e)
    _AUTH_ROUTER_OK = False

# SPEC_019 connectors router (list, dossier, health-check, config, run)
try:
    from api.routes import connectors as connectors_route
    _CONNECTORS_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import connectors router (SPEC_019): %s", _e)
    _CONNECTORS_ROUTER_OK = False

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Market-Zero",
        description="Pharmaceutical intelligence API: search, graph, metrics, and GraphRAG queries.",
        version="0.1.0",
    )

    allowed_origins = [
        "http://localhost:5090",
        "http://localhost:5091",
        "http://localhost:5173",
        os.getenv("MZ_FRONTEND_URL", ""),
    ]
    # Railway injects RAILWAY_PUBLIC_DOMAIN
    railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
    if railway_domain:
        allowed_origins.append(f"https://{railway_domain}")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o for o in allowed_origins if o],
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Session-ID"],
        allow_credentials=True,
    )

    # Register API routers — mount at both root (backwards compat) and /api/v1
    all_routers = [
        search.router, metrics.router, graph.router, query.router,
        entities.router, chat.router, therapeutic_areas.router,
        catalog.router, enrichment.router, pricing.router, scenarios.router,
    ]
    if _NEW_ROUTERS_OK:
        all_routers.extend([feedback.router, steward.router, literature.router, intelligence.router, agent.router])
    if _UPLOAD_ROUTER_OK:
        all_routers.append(upload_route.router)
    if _AUTH_ROUTER_OK:
        all_routers.append(auth_route.router)
    if _CONNECTORS_ROUTER_OK:
        all_routers.append(connectors_route.router)
    for r in all_routers:
        app.include_router(r)                      # /chat, /search, etc. (legacy)
        app.include_router(r, prefix="/api/v1")    # /api/v1/chat, /api/v1/search, etc.

    @app.post("/debug/migrate")
    def debug_migrate():
        """Debug: run pending migrations and report result."""
        try:
            from config import config as cfg
            from db import Database as MigrateDB
            from migrate import run_migrations
            mdb = MigrateDB(cfg.db.dsn)
            mdb.connect()
            try:
                count = run_migrations(mdb)
                return {"ok": True, "migrations_applied": count}
            finally:
                mdb.close()
        except Exception as e:
            import traceback
            return {"ok": False, "error": str(e), "traceback": traceback.format_exc()}

    @app.get("/debug/routes")
    def debug_routes():
        """Debug: show registered route count and new router status."""
        import os
        route_count = len([r for r in app.routes if hasattr(r, 'path')])
        steward_routes = [r.path for r in app.routes if hasattr(r, 'path') and 'steward' in r.path]
        return {
            "total_routes": route_count,
            "new_routers_ok": _NEW_ROUTERS_OK,
            "steward_routes": steward_routes,
            "python_version": os.popen("python --version").read().strip(),
            "feedback_file_exists": os.path.exists("api/routes/feedback.py"),
            "steward_file_exists": os.path.exists("api/routes/steward.py"),
            "literature_file_exists": os.path.exists("api/routes/literature.py"),
        }

    @app.get("/healthz")
    def healthz():
        """Lightweight liveness probe — no DB, instant 200."""
        return {"status": "ok"}

    @app.get("/health")
    def health():
        """Rich health check with DB stats — always returns 200.

        Database details are best-effort; if the DB is unreachable the
        endpoint still responds with status=degraded instead of crashing.
        """
        db_status = "unknown"
        tables: dict = {}
        total_records = 0
        source_coverage: list = []

        try:
            db = get_db()
        except Exception as e:
            db_status = f"connection_error: {e}"
            return {
                "status": "degraded",
                "database": db_status,
                "tables": {},
                "services": ["search", "graph", "metrics", "query_engine"],
                "total_records": 0,
                "source_coverage": [],
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }

        try:
            row = db.fetch_one("SELECT 1 AS ok")
            db_status = "connected" if row else "error"
        except Exception as e:
            db_status = f"error: {e}"

        tracked_tables = [
            "drugs",
            "clinical_trials",
            "pubmed_articles",
            "companies",
            "market_events",
            "entity_links",
        ]
        for table in tracked_tables:
            try:
                count_row = db.fetch_one(f"SELECT COUNT(*) AS cnt FROM {table}")
                tables[table] = count_row["cnt"] if count_row else 0
            except Exception:
                tables[table] = "error"

        total_records = sum(int(v) for v in tables.values() if isinstance(v, int))

        try:
            source_rows = db.fetch_all(
                """
                SELECT
                    source_api AS source,
                    COUNT(*)::int AS records,
                    MAX(retrieved_at) AS last_retrieved
                FROM (
                    SELECT source_api, retrieved_at FROM drugs
                    UNION ALL
                    SELECT source_api, retrieved_at FROM clinical_trials
                    UNION ALL
                    SELECT source_api, retrieved_at FROM pubmed_articles
                    UNION ALL
                    SELECT source_api, retrieved_at FROM companies
                    UNION ALL
                    SELECT source_api, retrieved_at FROM market_events
                ) AS all_sources
                WHERE source_api IS NOT NULL AND source_api <> ''
                GROUP BY source_api
                ORDER BY records DESC
                """
            )
            for row in source_rows:
                last_retrieved = row.get("last_retrieved")
                source_coverage.append(
                    {
                        "source": row["source"],
                        "records": row["records"],
                        "total_records": row["records"],
                        "last_pull_records": None,
                        "last_retrieved": last_retrieved.isoformat() if hasattr(last_retrieved, "isoformat") else None,
                    }
                )
        except Exception:
            pass

        return {
            "status": "ok" if db_status == "connected" else "degraded",
            "database": db_status,
            "tables": tables,
            "services": ["search", "graph", "metrics", "query_engine"],
            "total_records": total_records,
            "source_coverage": source_coverage,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    # ── Background Pipeline Scheduler + Data Steward ──

    def _run_stale_connectors():
        """Check each connector's last run and re-run if stale."""
        from scheduler.config import CONNECTOR_SCHEDULES, RUN_ORDER
        from connectors.base import SourceType
        from datetime import timedelta

        db = get_db()
        now = datetime.now(timezone.utc)

        # Calculate staleness thresholds per schedule type
        for source_type in RUN_ORDER:
            sched = CONNECTOR_SCHEDULES.get(source_type)
            if not sched:
                continue

            cron = sched["cron"]
            # Determine expected freshness: daily → 2 days, weekly → 10 days, monthly → 45 days
            if "day" in cron:  # monthly
                max_age = timedelta(days=45)
            elif "day_of_week" in cron:  # weekly
                max_age = timedelta(days=10)
            else:  # daily
                max_age = timedelta(days=2)

            try:
                last = db.fetch_one(
                    """SELECT MAX(retrieved_at) AS last_run
                       FROM (
                           SELECT retrieved_at FROM drugs WHERE source_api = %s
                           UNION ALL SELECT retrieved_at FROM clinical_trials WHERE source_api = %s
                           UNION ALL SELECT retrieved_at FROM pubmed_articles WHERE source_api = %s
                           UNION ALL SELECT retrieved_at FROM companies WHERE source_api = %s
                           UNION ALL SELECT retrieved_at FROM market_events WHERE source_api = %s
                       ) AS t""",
                    [source_type.value] * 5,
                )
                last_run = last["last_run"] if last else None

                if last_run and (now - last_run) < max_age:
                    continue  # not stale

                logger.info(
                    "Stale connector: %s (last=%s, max_age=%s) — running catch-up",
                    source_type.value, last_run, max_age,
                )
                if _scheduler:
                    _scheduler._run_connector(source_type)
                    logger.info("Catch-up complete: %s", source_type.value)
            except Exception as e:
                logger.warning("Catch-up failed for %s: %s", source_type.value, e)

    _scheduler = None

    @app.on_event("startup")
    def start_background_agents():
        """Start the pipeline scheduler and data steward as background agents.

        Delayed 30s after startup so the app can pass healthcheck first.
        Only starts if MZ_SCHEDULER env var is not 'false'.
        """
        if os.environ.get("MZ_SCHEDULER", "true").lower() == "false":
            logger.info("Background agents disabled (MZ_SCHEDULER=false)")
            return

        import threading

        def _delayed_start():
            import time as _time
            _time.sleep(30)  # let app stabilize and pass healthcheck

            # 1. Start APScheduler for data collection
            try:
                from scheduler.runner import DataPipelineScheduler
                nonlocal _scheduler
                _scheduler = DataPipelineScheduler()
                _scheduler._register_jobs()
                _scheduler._scheduler.start()
                logger.info("Pipeline scheduler started (cron jobs registered)")
            except Exception:
                logger.exception("Pipeline scheduler failed to start")

            # 2. Run auto-curate once on startup (catches up any missed curation)
            try:
                from scripts.auto_curate import run as auto_curate_run
                result = auto_curate_run(dry_run=False, skip_ai=True)
                logger.info("Startup auto-curate: %s", result)
            except Exception:
                logger.exception("Startup auto-curate failed")

            # 3. Catch-up: run any stale connectors (>2x their schedule interval)
            try:
                _run_stale_connectors()
            except Exception:
                logger.exception("Stale connector catch-up failed")

            # 4. Continuous agent loop — steward + auto-curate + FAIR scoring
            # Runs every 2 hours to keep data quality high
            steward_interval = 2 * 3600  # 2 hours (was 6)
            cycle = 0
            while True:
                cycle += 1
                logger.info("=== Background agent cycle %d starting ===", cycle)

                # 4a. Data Steward — signal-driven curation (routed through harness)
                try:
                    from api.deps import get_harness

                    harness = get_harness()
                    harness_result = harness.run(
                        agent_type="data_steward",
                        goal=f"Periodic curation cycle {cycle}",
                        steps=[
                            ("steward_curate", {"max_iterations": 20, "skip_ai": True}),
                        ],
                    )
                    step_out = (
                        harness_result.step_results[0].output
                        if harness_result.step_results
                        else {}
                    )
                    logger.info(
                        "Data Steward [cycle %d] via harness: %s (session=%s)",
                        cycle,
                        {k: step_out.get(k) for k in ("completed", "failed", "feedback_resolved") if k in (step_out or {})},
                        harness_result.session_id,
                    )
                except Exception:
                    logger.exception("Data Steward error [cycle %d]", cycle)

                # 4b. Auto-curate every 4th cycle (~8 hours)
                if cycle % 4 == 0:
                    try:
                        from scripts.auto_curate import run as _curate
                        result = _curate(dry_run=False, skip_ai=True)
                        logger.info("Auto-curate [cycle %d]: %s", cycle, result)
                    except Exception:
                        logger.exception("Auto-curate error [cycle %d]", cycle)

                # 4c. FAIR scoring every 6th cycle (~12 hours)
                if cycle % 6 == 0:
                    try:
                        from services.fair_scorer import FAIRScorer
                        from config import config as _cfg2
                        fdb = Database(_cfg2.db.dsn)
                        fdb.connect()
                        try:
                            scorer = FAIRScorer(fdb)
                            fair = scorer.compute()
                            scorer.persist(fair)
                            logger.info("FAIR score [cycle %d]: %.3f", cycle, fair.overall)
                        finally:
                            fdb.close()
                    except Exception:
                        logger.exception("FAIR scoring error [cycle %d]", cycle)

                # 4d. Concept weight adjustment every 12th cycle (~24 hours)
                if cycle % 12 == 0:
                    try:
                        from services.concept_weight_adjuster import ConceptWeightAdjuster
                        from api.deps import get_concept_registry

                        cw_db = get_db()
                        cw_registry = get_concept_registry()
                        adjuster = ConceptWeightAdjuster(cw_db, cw_registry)
                        adj_report = adjuster.analyze_and_adjust(lookback_days=7)
                        logger.info(
                            "Concept weight adjustment [cycle %d]: %d queries analyzed, "
                            "%d concepts adjusted",
                            cycle, adj_report.analyzed_queries, adj_report.concepts_adjusted,
                        )
                    except Exception:
                        logger.exception("Concept weight adjustment error [cycle %d]", cycle)

                # 4e. Stale connector catch-up every 3rd cycle (~6 hours)
                if cycle % 3 == 0:
                    try:
                        _run_stale_connectors()
                        logger.info("Stale connector catch-up [cycle %d] complete", cycle)
                    except Exception:
                        logger.exception("Stale connector catch-up error [cycle %d]", cycle)

                # 4f. Intelligence event collection every cycle
                try:
                    from services.event_collector import EventCollector
                    edb = Database(_cfg.db.dsn)
                    edb.connect()
                    try:
                        ec = EventCollector(edb)
                        # Collect from news connector
                        from connectors.news import PharmaNewsConnector
                        news = PharmaNewsConnector()
                        from services.event_collector import EventCandidate
                        candidates = []
                        for record in news.fetch()[:20]:
                            candidates.append(EventCandidate(
                                source_feed=record.data.get("source_feed", "news"),
                                source_tier="tier_3",
                                event_type=record.data.get("event_type", "general"),
                                description=record.data.get("description", ""),
                                event_date=None,
                                source_url=record.data.get("source_url", ""),
                                entity_hint=record.data.get("drug_name"),
                                entity_type_hint="drug",
                                raw_data=record.data,
                            ))
                        if candidates:
                            result = ec.collect(candidates)
                            logger.info(
                                "Event collection [cycle %d]: %d new, %d dupes",
                                cycle, result.new_events, result.duplicates_skipped,
                            )
                    finally:
                        edb.close()
                except Exception:
                    logger.exception("Event collection error [cycle %d]", cycle)

                logger.info("=== Background agent cycle %d complete, sleeping %ds ===", cycle, steward_interval)
                _time.sleep(steward_interval)

        t = threading.Thread(target=_delayed_start, daemon=True, name="bg-agents")
        t.start()
        logger.info("Background agents thread started (30s delayed)")

    @app.on_event("shutdown")
    def shutdown():
        try:
            get_db().close()
        except Exception:
            pass

    # Serve frontend static files (must come after API routes)
    if FRONTEND_DIR.exists():
        @app.middleware("http")
        async def spa_fallback(request: Request, call_next):
            """Serve SPA for frontend routes, let API routes pass through."""
            response = await call_next(request)
            # If the API returned 404 and the path looks like a frontend route,
            # serve index.html instead. API paths return proper 404 JSON.
            if response.status_code == 404:
                path = request.url.path.lstrip("/")
                is_api = any(path.startswith(p) for p in (
                    "api/", "chat", "search/", "graph/", "query", "entities",
                    "catalog/", "metrics", "enrichment", "health",
                    "therapeutic-areas", "feedback", "scenarios", "steward",
                    "literature", "pricing", "intelligence", "agent",
                    "auth/", "upload", "connectors/",
                    "openapi.json", "docs", "redoc",
                ))
                if not is_api and not path.startswith("assets/"):
                    return FileResponse(str(FRONTEND_DIR / "index.html"))
            return response

        # Serve static assets
        @app.get("/assets/{file_path:path}")
        async def serve_asset(file_path: str):
            asset = FRONTEND_DIR / "assets" / file_path
            if asset.exists() and asset.is_file():
                return FileResponse(str(asset))
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "not_found"}, status_code=404)

        # Root → index.html
        @app.get("/")
        async def serve_root():
            return FileResponse(str(FRONTEND_DIR / "index.html"))

        # Frontend routes (workspace, search) → index.html
        @app.get("/workspace")
        @app.get("/search")
        @app.get("/newui")
        @app.get("/connectors")
        async def serve_frontend_routes():
            return FileResponse(str(FRONTEND_DIR / "index.html"))

    return app
