"""
Database wrapper for Market-Zero.

Provides a clean interface for the integration pipeline to interact with
PostgreSQL. Uses psycopg2 with RealDictCursor so all fetch results return
dicts with column names as keys.

Connection management:
- Uses a single connection per Database instance (not a pool).
- Transactions are auto-committed unless wrapped in a with_transaction() block.
- For the integration pipeline (sequential per-record processing), this is
  sufficient. Connection pooling is added in Phase 8 with the API layer.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Optional

logger = logging.getLogger(__name__)


class Database:
    """
    Thin wrapper around psycopg2 providing execute/fetch methods.

    Usage:
        db = Database(config.db.dsn)
        db.connect()
        row = db.fetch_one("SELECT id FROM drugs WHERE nda_number = %s", ["215256"])
        db.close()
    """

    def __init__(self, dsn: str):
        self.dsn = dsn
        self._conn = None

    def connect(self) -> None:
        """Open a connection to PostgreSQL."""
        if self._conn is not None:
            return

        try:
            import psycopg2
            import psycopg2.extras

            self._conn = psycopg2.connect(
                self.dsn,
                cursor_factory=psycopg2.extras.RealDictCursor,
            )
            self._conn.autocommit = True
            logger.info("Connected to database: %s", self._redact_dsn())
        except ImportError:
            raise RuntimeError(
                "psycopg2 not installed. Run: pip install psycopg2-binary"
            )
        except Exception as e:
            logger.error("Failed to connect to database: %s", e)
            raise

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.info("Database connection closed")

    @property
    def conn(self):
        """Get the active connection, connecting if needed."""
        if self._conn is None:
            self.connect()
        return self._conn

    def execute(self, query: str, params: Optional[list[Any]] = None) -> None:
        """Execute a query that doesn't return results (INSERT, UPDATE, DELETE)."""
        with self.conn.cursor() as cur:
            cur.execute(query, params)

    def fetch_one(self, query: str, params: Optional[list[Any]] = None) -> Optional[dict]:
        """Execute a query and return the first row as a dict, or None."""
        with self.conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
            return dict(row) if row else None

    def fetch_all(self, query: str, params: Optional[list[Any]] = None) -> list[dict]:
        """Execute a query and return all rows as a list of dicts."""
        with self.conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            return [dict(row) for row in rows]

    @contextmanager
    def transaction(self):
        """
        Context manager for explicit transactions.

        Usage:
            with db.transaction():
                db.execute("INSERT INTO ...")
                db.execute("UPDATE ...")
            # auto-commits on exit, rolls back on exception
        """
        old_autocommit = self._conn.autocommit
        self._conn.autocommit = False
        try:
            yield self
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            self._conn.autocommit = old_autocommit

    def execute_script(self, sql: str) -> None:
        """
        Execute a multi-statement SQL script (e.g., migration files).
        Runs in a single transaction.
        """
        old_autocommit = self._conn.autocommit
        self._conn.autocommit = False
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql)
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            self._conn.autocommit = old_autocommit

    def _redact_dsn(self) -> str:
        """Redact password from DSN for safe logging."""
        if "@" in self.dsn:
            prefix, rest = self.dsn.split("@", 1)
            if ":" in prefix:
                user_part = prefix.rsplit(":", 1)[0]
                return f"{user_part}:***@{rest}"
        return self.dsn
