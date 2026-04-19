"""Seed demo users for SPEC_018 role-gated demos.

Usage:
    python scripts/seed_demo_users.py
    railway run python scripts/seed_demo_users.py    # production

Demo accounts (all use password "demo" by default; override via MZ_DEMO_PASSWORD):
    viewer@demo.market-zero.io     → role=viewer
    uploader@demo.market-zero.io   → role=uploader
    enterprise@demo.market-zero.io → role=enterprise

Idempotent — re-running updates the password hash but does not duplicate rows.
"""

from __future__ import annotations

import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_demo_users")


DEMO_USERS = [
    ("viewer@demo.market-zero.io", "viewer"),
    ("uploader@demo.market-zero.io", "uploader"),
    ("enterprise@demo.market-zero.io", "enterprise"),
]


def main() -> int:
    from config import config
    from db import Database
    from services.auth import hash_password

    password = os.getenv("MZ_DEMO_PASSWORD", "demo")

    db = Database(config.db.dsn)
    db.connect()
    try:
        for email, role in DEMO_USERS:
            pw_hash = hash_password(password)
            db.execute(
                """
                INSERT INTO users (email, password_hash, role, is_active)
                VALUES (%s, %s, %s, TRUE)
                ON CONFLICT (email) DO UPDATE
                  SET password_hash = EXCLUDED.password_hash,
                      role          = EXCLUDED.role,
                      is_active     = TRUE
                """,
                [email.lower(), pw_hash, role],
            )
            logger.info("seeded %s (role=%s)", email, role)
        logger.info("demo users seeded successfully")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
