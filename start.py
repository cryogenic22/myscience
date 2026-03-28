"""Railway startup script — start uvicorn immediately.

Migrations and background tasks are handled by the app lifecycle events,
not at startup. This ensures the healthcheck endpoint is reachable ASAP.
"""

import os
import sys
import time
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("startup")

t0 = time.time()

# Validate critical environment
port = int(os.environ.get("PORT", 8020))
db_url = os.environ.get("DATABASE_URL", "")
logger.info("PORT=%d  DATABASE_URL=%s", port, "set" if db_url else "NOT SET")
logger.info("Python %s on %s", sys.version, sys.platform)

# Pre-import check — catch module errors before uvicorn
try:
    logger.info("Pre-import check: api.app ...")
    from api.app import create_app  # noqa: F401
    logger.info("Pre-import OK (%.1fs)", time.time() - t0)
except Exception as e:
    logger.error("FATAL: Cannot import api.app: %s", e)
    import traceback
    traceback.print_exc()
    sys.exit(1)

logger.info("Starting uvicorn on port %d...", port)

import uvicorn
uvicorn.run(
    "api.app:create_app",
    factory=True,
    host="0.0.0.0",
    port=port,
)
