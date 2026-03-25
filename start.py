"""Railway startup script — run migrations then start uvicorn.

Migrations are non-blocking: if they fail, the app still starts.
This prevents a broken migration from taking down the production API.
"""

import os
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("startup")

# 1. Run migrations (non-blocking)
try:
    logger.info("Running database migrations...")
    from migrate import main as run_migrations
    run_migrations()
    logger.info("Migrations complete.")
except Exception as e:
    logger.warning("Migration failed (app will start anyway): %s", e)

# 2. Start data pipeline scheduler (background daemon)
if os.environ.get("MZ_SCHEDULER", "true").lower() != "false":
    try:
        from scheduler import DataPipelineScheduler
        scheduler = DataPipelineScheduler()
        scheduler.start()
        logger.info("Data pipeline scheduler started (background daemon).")
    except Exception as e:
        logger.warning("Scheduler failed to start (app will run without it): %s", e)

# 3. Start uvicorn
port = int(os.environ.get("PORT", 8020))
logger.info("Starting uvicorn on port %d...", port)

import uvicorn
uvicorn.run(
    "api.app:create_app",
    factory=True,
    host="0.0.0.0",
    port=port,
)
