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

# 1. Start uvicorn FIRST (healthcheck needs it ASAP)
# Migrations and scheduler run AFTER the app is serving.
port = int(os.environ.get("PORT", 8020))
logger.info("Starting uvicorn on port %d...", port)

import uvicorn
uvicorn.run(
    "api.app:create_app",
    factory=True,
    host="0.0.0.0",
    port=port,
)
