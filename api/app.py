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
    for r in all_routers:
        app.include_router(r)                      # /chat, /search, etc. (legacy)
        app.include_router(r, prefix="/api/v1")    # /api/v1/chat, /api/v1/search, etc.

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
