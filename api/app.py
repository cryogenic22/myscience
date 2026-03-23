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
from api.routes import search, metrics, graph, query, entities, chat, therapeutic_areas, catalog, enrichment

logger = logging.getLogger(__name__)

# New routers — import with fallback to avoid blocking startup
try:
    from api.routes import feedback, steward, literature
    _NEW_ROUTERS_OK = True
except Exception as _e:
    logger.error("Failed to import new routers (feedback/steward/literature): %s", _e)
    _NEW_ROUTERS_OK = False

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
        catalog.router, enrichment.router,
    ]
    if _NEW_ROUTERS_OK:
        all_routers.extend([feedback.router, steward.router, literature.router])
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

    @app.get("/health")
    def health():
        """Health check: database connectivity + table counts."""
        db = get_db()
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
        tables = {}
        for table in tracked_tables:
            try:
                count_row = db.fetch_one(f"SELECT COUNT(*) AS cnt FROM {table}")
                tables[table] = count_row["cnt"] if count_row else 0
            except Exception:
                tables[table] = "error"

        total_records = sum(int(v) for v in tables.values() if isinstance(v, int))

        source_coverage = []
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
            source_coverage = []

        return {
            "status": "ok" if db_status == "connected" else "degraded",
            "database": db_status,
            "tables": tables,
            "services": ["search", "graph", "metrics", "query_engine"],
            "total_records": total_records,
            "source_coverage": source_coverage,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    # ── Background Data Steward (runs every 6 hours) ──

    _steward_thread = None

    @app.on_event("startup")
    def start_steward_loop():
        import threading

        def _steward_worker():
            import time as _time
            interval = 6 * 3600  # 6 hours
            _time.sleep(60)  # wait for app to stabilize
            while True:
                try:
                    logger.info("Data Steward background loop starting")
                    from services.steward_signals import StewardSignalCollector
                    from services.data_steward import DataSteward, StewardConfig
                    from config import config as _cfg

                    sdb = Database(_cfg.db.dsn)
                    sdb.connect()
                    try:
                        collector = StewardSignalCollector(sdb)
                        steward = DataSteward(
                            sdb, collector,
                            StewardConfig(max_iterations=10, skip_ai=True),
                        )
                        summary = steward.run_loop()
                        logger.info(
                            "Data Steward complete: %d completed, %d feedback resolved",
                            summary.completed, summary.feedback_resolved,
                        )
                    finally:
                        sdb.close()
                except Exception:
                    logger.exception("Data Steward background loop error")
                _time.sleep(interval)

        nonlocal _steward_thread
        _steward_thread = threading.Thread(target=_steward_worker, daemon=True, name="data-steward")
        _steward_thread.start()
        logger.info("Data Steward background thread started (6h interval)")

    @app.on_event("shutdown")
    def shutdown():
        try:
            get_db().close()
        except Exception:
            pass

    # Serve frontend static files (must come after API routes)
    if FRONTEND_DIR.exists():
        app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="static")

        @app.get("/{full_path:path}")
        async def serve_spa(request: Request, full_path: str):
            """Serve the React SPA for all non-API routes."""
            # Try to serve exact file first
            file_path = FRONTEND_DIR / full_path
            if full_path and file_path.exists() and file_path.is_file():
                return FileResponse(str(file_path))
            # Fallback to index.html for SPA routing
            return FileResponse(str(FRONTEND_DIR / "index.html"))

    return app
