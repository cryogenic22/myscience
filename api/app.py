"""FastAPI application factory for Market-Zero."""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
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

# SPEC_019 connectors router
try:
    from api.routes import connectors as connectors_route
    _CONNECTORS_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import connectors router (SPEC_019): %s", _e)
    _CONNECTORS_ROUTER_OK = False

# SPEC_020 signals + watchlist routers
try:
    from api.routes import signals as signals_route
    _SIGNALS_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import signals router (SPEC_020): %s", _e)
    _SIGNALS_ROUTER_OK = False

try:
    from api.routes import watchlist as watchlist_route
    _WATCHLIST_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import watchlist router (SPEC_020): %s", _e)
    _WATCHLIST_ROUTER_OK = False

# SPEC_021 war room router (decision flywheel Phase A)
try:
    from api.routes import war_room as war_room_route
    _WAR_ROOM_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import war_room router (SPEC_021): %s", _e)
    _WAR_ROOM_ROUTER_OK = False

# SPEC_021 decisions ledger router (Phase C)
try:
    from api.routes import decisions as decisions_route
    _DECISIONS_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import decisions router (SPEC_021 C): %s", _e)
    _DECISIONS_ROUTER_OK = False

# SPEC_021 inbox aggregator (Phase E)
try:
    from api.routes import inbox as inbox_route
    _INBOX_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import inbox router (SPEC_021 E): %s", _e)
    _INBOX_ROUTER_OK = False

# SPEC_023 decision briefs router
try:
    from api.routes import decision_briefs as decision_briefs_route
    _DECISION_BRIEFS_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import decision_briefs router (SPEC_023): %s", _e)
    _DECISION_BRIEFS_ROUTER_OK = False

# SPEC_024 evidence ledger router (claims + evidence + snapshots)
try:
    from api.routes import evidence_ledger as evidence_ledger_route
    _EVIDENCE_LEDGER_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import evidence_ledger router (SPEC_024): %s", _e)
    _EVIDENCE_LEDGER_ROUTER_OK = False
# SPEC_026 LLM Gateway router (prompt registry + PII filter + cost summary)
try:
    from api.routes import llm_gateway as llm_gateway_route
    _LLM_GATEWAY_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import llm_gateway router (SPEC_026): %s", _e)
    _LLM_GATEWAY_ROUTER_OK = False

# SPEC_027 Source Registry router
try:
    from api.routes import sources as sources_route
    _SOURCES_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import sources router (SPEC_027): %s", _e)
    _SOURCES_ROUTER_OK = False

# SPEC_035 /ask graph traversal router
try:
    from api.routes import ask as ask_route
    _ASK_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import ask router (SPEC_035): %s", _e)
    _ASK_ROUTER_OK = False
# SPEC_034 Decision Signing router
try:
    from api.routes import decision_signing as decision_signing_route
    _DECISION_SIGNING_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import decision_signing router (SPEC_034): %s", _e)
    _DECISION_SIGNING_ROUTER_OK = False
# SPEC_033 Counter-Recommendation router
try:
    from api.routes import recommendations as recommendations_route
    _RECOMMENDATIONS_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import recommendations router (SPEC_033): %s", _e)
    _RECOMMENDATIONS_ROUTER_OK = False
# SPEC_032 Learning Service router
try:
    from api.routes import learning as learning_route
    _LEARNING_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import learning router (SPEC_032): %s", _e)
    _LEARNING_ROUTER_OK = False
# SPEC_031 Materiality Scoring router
try:
    from api.routes import materiality as materiality_route
    _MATERIALITY_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import materiality router (SPEC_031): %s", _e)
    _MATERIALITY_ROUTER_OK = False
# SPEC_029 Framing Triggers router
try:
    from api.routes import framing_triggers as framing_triggers_route
    _FRAMING_TRIGGERS_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import framing_triggers router (SPEC_029): %s", _e)
    _FRAMING_TRIGGERS_ROUTER_OK = False
# SPEC_028 War-Game Adversaries router
try:
    from api.routes import war_games as war_games_route
    _WAR_GAMES_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import war_games router (SPEC_028): %s", _e)
    _WAR_GAMES_ROUTER_OK = False
# SPEC_025 Game-Theoretic Simulation router
try:
    from api.routes import game_theory as game_theory_route
    _GAME_THEORY_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import game_theory router (SPEC_025): %s", _e)
    _GAME_THEORY_ROUTER_OK = False

# BE-6 — Dossier composer
try:
    from api.routes import dossier as dossier_route
    _DOSSIER_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import dossier router (BE-6): %s", _e)
    _DOSSIER_ROUTER_OK = False

# Loop #17 — Helix Bridge
try:
    from api.routes import bridge as bridge_route
    _BRIDGE_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import bridge router (Loop #17): %s", _e)
    _BRIDGE_ROUTER_OK = False

# Loop #19 — Batch evidence resolver
try:
    from api.routes import evidence_batch as evidence_batch_route
    _EVIDENCE_BATCH_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import evidence_batch router (Loop #19): %s", _e)
    _EVIDENCE_BATCH_ROUTER_OK = False

# Loop #21 — Agent activity feed
try:
    from api.routes import agents_activity as agents_activity_route
    _AGENTS_ACTIVITY_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import agents_activity router (Loop #21): %s", _e)
    _AGENTS_ACTIVITY_ROUTER_OK = False

# Loop ② — KBQ living views
try:
    from api.routes import kbq as kbq_route
    _KBQ_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import kbq router (Loop 2): %s", _e)
    _KBQ_ROUTER_OK = False

# PB-1307 — facts ledger
try:
    from api.routes import facts as facts_route
    _FACTS_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import facts router (PB-1307): %s", _e)
    _FACTS_ROUTER_OK = False

# DI-5 — SME playbook authoring (Domain Intelligence)
try:
    from api.routes import playbooks as playbooks_route
    _PLAYBOOKS_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import playbooks router (DI-5): %s", _e)
    _PLAYBOOKS_ROUTER_OK = False

# DF-1/DF-2 — Domain Forge: playable SME elicitation round (own /forge prefix)
try:
    from api.routes import forge as forge_route
    _FORGE_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import forge router (DF-1/DF-2): %s", _e)
    _FORGE_ROUTER_OK = False

# Track I — Eval Harness: scores the system vs the Forge gold set (own /eval prefix)
try:
    from api.routes import eval as eval_route
    _EVAL_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import eval router (Track I): %s", _e)
    _EVAL_ROUTER_OK = False

# DataHub D-API-1 — connector-taxonomy + onboarding lifecycle REST (own /hub prefix)
try:
    from api.routes import hub as hub_route
    _HUB_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import hub router (DataHub D-API-1): %s", _e)
    _HUB_ROUTER_OK = False

# Password-gated standalone ZS Future State page (own /zs prefix, HTTP Basic auth)
try:
    from api.routes import zs as zs_route
    _ZS_ROUTER_OK = True
except Exception as _e:
    logger.error("Failed to import zs router: %s", _e)
    _ZS_ROUTER_OK = False

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup callbacks are registered onto app.state by the
        # remainder of create_app(); we just invoke them here so we get
        # the modern lifespan API without restructuring 200 lines.
        for fn in getattr(app.state, "_startup_fns", []):
            try:
                fn()
            except Exception:
                logger.exception("startup callback failed")
        yield
        for fn in getattr(app.state, "_shutdown_fns", []):
            try:
                fn()
            except Exception:
                logger.exception("shutdown callback failed")

    app = FastAPI(
        title="Market-Zero",
        description="Pharmaceutical intelligence API: search, graph, metrics, and GraphRAG queries.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state._startup_fns = []
    app.state._shutdown_fns = []

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
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=["Content-Type", "Authorization", "X-Session-ID"],
        allow_credentials=True,
    )

    # SPEC-021 D2 — per-user rate limiting on LLM-heavy endpoints
    try:
        from api.middleware.rate_limit import rate_limit_middleware
        app.middleware("http")(rate_limit_middleware)
        logger.info("Rate limit middleware registered (SPEC-021 D2)")
    except Exception as _e:
        logger.warning("Rate limit middleware NOT registered: %s", _e)

    # SPEC-021 D2 — standard error envelope for HTTPException + ValidationError
    try:
        from api.exception_handlers import install_exception_handlers
        install_exception_handlers(app)
        logger.info("Standard error envelope handlers installed (SPEC-021 D2)")
    except Exception as _e:
        logger.warning("Error envelope handlers NOT installed: %s", _e)

    # Register API routers — mount at both root (backwards compat) and /api/v1
    all_routers = [
        search.router, metrics.router, graph.router, query.router,
        entities.router, chat.router, therapeutic_areas.router,
        catalog.router, enrichment.router, pricing.router, scenarios.router,
    ]
    # Loop A — engagements CRUD (Z3 + Z4 + Z5 service modules over HTTP)
    try:
        from api.routes import engagements as engagements_route
        all_routers.append(engagements_route.router)
    except Exception as _e:
        logger.error("Failed to import engagements router (Loop A): %s", _e)
    try:
        from api.routes import comments as comments_route   # UX02 generic entity comments
        all_routers.append(comments_route.router)
    except Exception as _e:
        logger.error("Failed to import comments router (UX02): %s", _e)
    if _NEW_ROUTERS_OK:
        all_routers.extend([feedback.router, steward.router, literature.router, intelligence.router, agent.router])
    if _UPLOAD_ROUTER_OK:
        all_routers.append(upload_route.router)
    if _AUTH_ROUTER_OK:
        all_routers.append(auth_route.router)
    if _CONNECTORS_ROUTER_OK:
        all_routers.append(connectors_route.router)
    if _SIGNALS_ROUTER_OK:
        all_routers.append(signals_route.router)
    if _WATCHLIST_ROUTER_OK:
        all_routers.append(watchlist_route.router)
    if _WAR_ROOM_ROUTER_OK:
        all_routers.append(war_room_route.router)
    if _DECISIONS_ROUTER_OK:
        all_routers.append(decisions_route.router)
    if _INBOX_ROUTER_OK:
        all_routers.append(inbox_route.router)
        # Phase E — insights surface lives in the same module
        if hasattr(inbox_route, "insights_router"):
            all_routers.append(inbox_route.insights_router)
    if _DECISION_BRIEFS_ROUTER_OK:
        all_routers.append(decision_briefs_route.router)
    if _EVIDENCE_LEDGER_ROUTER_OK:
        all_routers.append(evidence_ledger_route.claims_router)
        all_routers.append(evidence_ledger_route.snapshots_router)
    if _LLM_GATEWAY_ROUTER_OK:
        all_routers.append(llm_gateway_route.router)
    if _SOURCES_ROUTER_OK:
        all_routers.append(sources_route.router)
    if _ASK_ROUTER_OK:
        all_routers.append(ask_route.router)
    if _DECISION_SIGNING_ROUTER_OK:
        all_routers.append(decision_signing_route.router)
    if _RECOMMENDATIONS_ROUTER_OK:
        all_routers.append(recommendations_route.router)
    if _LEARNING_ROUTER_OK:
        all_routers.append(learning_route.router)
    if _MATERIALITY_ROUTER_OK:
        all_routers.append(materiality_route.router)
    if _FRAMING_TRIGGERS_ROUTER_OK:
        all_routers.append(framing_triggers_route.router)
    if _WAR_GAMES_ROUTER_OK:
        all_routers.append(war_games_route.router)
    if _GAME_THEORY_ROUTER_OK:
        all_routers.append(game_theory_route.router)
    if _DOSSIER_ROUTER_OK:
        all_routers.append(dossier_route.router)
    if _BRIDGE_ROUTER_OK:
        all_routers.append(bridge_route.router)
    if _EVIDENCE_BATCH_ROUTER_OK:
        all_routers.append(evidence_batch_route.router)
    if _AGENTS_ACTIVITY_ROUTER_OK:
        all_routers.append(agents_activity_route.router)
    if _KBQ_ROUTER_OK:
        all_routers.append(kbq_route.router)
        all_routers.append(kbq_route.asset_router)  # PB-SL10 — /kbq?asset= (unshadowed)
    if _FACTS_ROUTER_OK:
        all_routers.append(facts_route.router)
    if _PLAYBOOKS_ROUTER_OK:
        all_routers.append(playbooks_route.router)   # DI-5 — /playbooks (own prefix)
    if _FORGE_ROUTER_OK:
        all_routers.append(forge_route.router)       # DF-1/DF-2 — /forge (own prefix)
    if _EVAL_ROUTER_OK:
        all_routers.append(eval_route.router)        # Track I — /eval (own prefix)
    if _HUB_ROUTER_OK:
        all_routers.append(hub_route.router)         # DataHub D-API-1 — /hub (own prefix)
    if _ZS_ROUTER_OK:
        all_routers.append(zs_route.router)          # password-gated /zs static page
    for r in all_routers:
        app.include_router(r)                      # /chat, /search, etc. (legacy)
        app.include_router(r, prefix="/api/v1")    # /api/v1/chat, /api/v1/search, etc.

    def _require_debug_token(
        x_debug_token: str | None = Header(default=None, alias="X-Debug-Token"),
    ) -> None:
        """SEC-001a: gate /debug/* behind a deploy secret; fail closed.

        Unset ``MZ_DEBUG_TOKEN``, or a missing/wrong token -> 404 (do not confirm
        the endpoint exists). A user-JWT gate is deliberately NOT used:
        ``/debug/seed-users`` bootstraps the first users, so a role check would
        deadlock. Operators set ``MZ_DEBUG_TOKEN`` and pass it as the
        ``X-Debug-Token`` header (e.g. the post-deploy migrate step).
        """
        expected = os.getenv("MZ_DEBUG_TOKEN")
        # Compare on bytes: secrets.compare_digest raises TypeError on a str with
        # a non-ASCII code point, and Starlette latin-1-decodes header values.
        # The short-circuit guarantees both are truthy before .encode().
        if (
            not expected
            or not x_debug_token
            or not secrets.compare_digest(
                x_debug_token.encode("utf-8"), expected.encode("utf-8")
            )
        ):
            raise HTTPException(status_code=404, detail="Not Found")

    @app.post("/debug/migrate")
    def debug_migrate(_: None = Depends(_require_debug_token)):
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

    @app.post("/debug/seed-users")
    def debug_seed_users(_: None = Depends(_require_debug_token)):
        """SPEC_018 — Seed the 3 demo users. Idempotent (ON CONFLICT updates).

        Safe to call repeatedly: the seed script does ON CONFLICT (email)
        DO UPDATE so re-runs just refresh the password hash to the current
        MZ_DEMO_PASSWORD value. Low blast radius — demo accounts are
        intentionally well-known.
        """
        try:
            from scripts.seed_demo_users import main as seed_main
            exit_code = seed_main()
            db = get_db()
            row = db.fetch_one(
                "SELECT COUNT(*) AS n FROM users WHERE email LIKE %s",
                ["%@demo.market-zero.io"],
            )
            users = db.fetch_all(
                "SELECT email, role, is_active FROM users "
                "WHERE email LIKE %s ORDER BY role",
                ["%@demo.market-zero.io"],
            )
            return {
                "ok": exit_code == 0,
                "demo_users_in_db": row["n"] if row else 0,
                "users": [dict(u) for u in users],
                "jwt_secret_set": bool(
                    os.getenv("MZ_JWT_SECRET") or os.getenv("SECRET_KEY")
                ),
            }
        except Exception as e:
            import traceback
            return {"ok": False, "error": str(e), "traceback": traceback.format_exc()}

    @app.get("/debug/routes")
    def debug_routes(_: None = Depends(_require_debug_token)):
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
        """Lightweight liveness probe — no DB, instant 200.

        Reports the deployed commit so a deploy is verifiable with one curl
        (Railway/Nixpacks builds without .git, so the SHA comes from the
        platform-injected env, not `git`). ``unknown`` when not set locally.
        """
        import os as _os
        sha = (
            _os.environ.get("RAILWAY_GIT_COMMIT_SHA")
            or _os.environ.get("GIT_COMMIT_SHA")
            or _os.environ.get("SOURCE_COMMIT")
            or "unknown"
        )
        return {"status": "ok", "commit": sha[:12]}

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

    def _shutdown():
        try:
            get_db().close()
        except Exception:
            pass

    # Auto-apply pending SQL migrations on startup.
    #
    # Migrations are idempotent (every file uses IF NOT EXISTS / ON CONFLICT
    # and is recorded in schema_migrations), so re-running is a no-op. This
    # closes the recurring footgun where a new migration shipped in a deploy
    # but the table never existed in prod until someone manually POSTed
    # /debug/migrate — the cause of "relation ... does not exist" 500s.
    #
    # Disable with MZ_AUTO_MIGRATE=false (e.g. if migrations are gated to a
    # separate release step). Best-effort: failures are logged, never fatal,
    # so a bad migration can't take down the healthcheck.
    def _run_pending_migrations():
        if os.environ.get("MZ_AUTO_MIGRATE", "true").lower() == "false":
            logger.info("Auto-migrate disabled (MZ_AUTO_MIGRATE=false)")
            return
        try:
            from config import config as _cfg
            from db import Database as _MigrateDB
            from migrate import run_migrations as _run_migrations

            mdb = _MigrateDB(_cfg.db.dsn)
            mdb.connect()
            try:
                count = _run_migrations(mdb)
                logger.info("Auto-migrate: %d migration(s) applied", count)
            finally:
                mdb.close()
        except Exception:
            logger.exception("Auto-migrate failed (continuing startup)")

    # Register the lifespan callbacks. Migrations run FIRST so dependent
    # services find their tables present.
    app.state._startup_fns.insert(0, _run_pending_migrations)
    app.state._startup_fns.append(start_background_agents)
    app.state._shutdown_fns.append(_shutdown)

    # SPEC-021 D2 — autonomous outcome detection job
    def _start_outcome_scheduler():
        if os.environ.get("MZ_OUTCOME_SCHEDULER_DISABLED", "").lower() in ("1", "true", "yes"):
            logger.info("outcome scheduler disabled via env")
            return
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from services.outcome_scheduler import register_outcome_scheduler

            sched = BackgroundScheduler(timezone="UTC")
            register_outcome_scheduler(sched, db_factory=get_db, interval_hours=1)
            sched.start()
            app.state.outcome_scheduler = sched
            logger.info("Outcome scheduler started (SPEC-021 D2)")
        except Exception:
            logger.exception("Outcome scheduler failed to start")

    def _stop_outcome_scheduler():
        sched = getattr(app.state, "outcome_scheduler", None)
        if sched is not None:
            try:
                sched.shutdown(wait=False)
            except Exception:
                pass

    app.state._startup_fns.append(_start_outcome_scheduler)
    app.state._shutdown_fns.append(_stop_outcome_scheduler)

    # Auto-collected API prefix registry — replaces the hand-maintained
    # list. Walks registered routes and extracts the first path segment
    # (the unique top-level prefix) into a frozenset. Eliminates the
    # category of bugs where a new router shipped without being added
    # to the SPA fallback's allowlist (cause of the C-launch incident).
    def _collect_api_prefixes(app_obj: FastAPI) -> frozenset[str]:
        prefixes: set[str] = set()
        for route in app_obj.routes:
            path = getattr(route, "path", "") or ""
            if not path.startswith("/"):
                continue
            # Strip /api/v1 prefix if present, then take first segment
            stripped = path[len("/api/v1"):] if path.startswith("/api/v1") else path
            stripped = stripped.lstrip("/")
            if not stripped:
                continue
            seg = stripped.split("/", 1)[0]
            if seg:
                prefixes.add(seg)
        # Always include the universally needed ones
        prefixes.update({"api", "openapi.json", "docs", "redoc", "debug"})
        return frozenset(prefixes)

    # Serve frontend static files (must come after API routes)
    if FRONTEND_DIR.exists():
        # Computed once at startup — routes don't change at runtime
        _api_prefixes = _collect_api_prefixes(app)
        logger.info("SPA fallback API prefixes (auto-collected): %s",
                    sorted(_api_prefixes))

        @app.middleware("http")
        async def spa_fallback(request: Request, call_next):
            """Serve SPA for frontend routes, let API routes pass through.

            Uses the auto-collected prefix registry (SPEC-021 D2). Adding
            a new router automatically protects its 404s from being
            replaced with index.html.
            """
            response = await call_next(request)
            if response.status_code == 404:
                path = request.url.path.lstrip("/")
                first_seg = path.split("/", 1)[0] if path else ""
                is_api = first_seg in _api_prefixes
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

        # Frontend routes — explicit handlers take precedence over the
        # auto-collected API prefix middleware. Required for any React
        # route whose first path segment also belongs to a backend router
        # (e.g. /bridge collides with POST /bridge/moments).
        @app.get("/workspace")
        @app.get("/search")
        @app.get("/newui")
        @app.get("/connectors")
        @app.get("/ci")
        @app.get("/bridge")
        @app.get("/briefs")
        @app.get("/briefs/new")
        # DataHub React routes. Their first segment ('hub') is auto-collected as an
        # API prefix (the /hub router is mounted), so without these explicit
        # handlers a hard-refresh / deep-link of /hub/catalog or /hub/connect hit
        # the /hub router's 404 instead of the SPA. Same collision as /bridge.
        @app.get("/hub/catalog")
        @app.get("/hub/connect")
        async def serve_frontend_routes():
            return FileResponse(str(FRONTEND_DIR / "index.html"))

        # Parameterized React routes. /dossier/... is intentionally omitted
        # because /dossier/{entity_type}/{slug_or_id} is also a backend API
        # route (mounted at root for backward-compat) — the API wins by
        # registration order, so a SPA shim here would never be reached.
        @app.get("/ci/decisions/{decision_id}")
        async def serve_ci_decision(decision_id: str):
            return FileResponse(str(FRONTEND_DIR / "index.html"))

        @app.get("/ci/legacy-decisions/{decision_id}")
        async def serve_ci_legacy_decision(decision_id: str):
            return FileResponse(str(FRONTEND_DIR / "index.html"))

        @app.get("/ci/dossier/{entity_type}/{entity_id}")
        async def serve_ci_dossier(entity_type: str, entity_id: str):
            return FileResponse(str(FRONTEND_DIR / "index.html"))

    return app
