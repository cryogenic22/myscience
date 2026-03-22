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

    def __init__(self, dsn: str, pool_size: int = 0):
        """Initialize database wrapper.

        Args:
            dsn: PostgreSQL connection string.
            pool_size: If >0, use a connection pool with this many connections.
                       If 0 (default), use a single persistent connection.
        """
        self.dsn = dsn
        self._conn = None
        self._pool = None
        self._pool_size = pool_size

    def connect(self) -> None:
        """Open a connection (or pool) to PostgreSQL."""
        try:
            import psycopg2
            import psycopg2.extras
            import psycopg2.pool

            if self._pool_size > 0:
                if self._pool is not None:
                    return
                self._pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=1,
                    maxconn=self._pool_size,
                    dsn=self.dsn,
                    cursor_factory=psycopg2.extras.RealDictCursor,
                )
                logger.info("Connection pool created (size=%d): %s",
                            self._pool_size, self._redact_dsn())
            else:
                if self._conn is not None:
                    return
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
        """Close the database connection or pool."""
        if self._pool is not None:
            self._pool.closeall()
            self._pool = None
            logger.info("Connection pool closed")
        elif self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.info("Database connection closed")

    @property
    def conn(self):
        """Get the active connection, connecting if needed.

        For pooled mode, gets a connection from the pool. Callers should
        use the fetch/execute methods instead of accessing conn directly.
        """
        if self._pool is not None:
            conn = self._pool.getconn()
            conn.autocommit = True
            return conn
        if self._conn is None:
            self.connect()
        return self._conn

    def _putconn(self, conn) -> None:
        """Return a connection to the pool (no-op for non-pooled mode)."""
        if self._pool is not None:
            self._pool.putconn(conn)

    def execute(self, query: str, params: Optional[list[Any]] = None) -> None:
        """Execute a query that doesn't return results (INSERT, UPDATE, DELETE)."""
        conn = self.conn
        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
        finally:
            self._putconn(conn)

    def fetch_one(self, query: str, params: Optional[list[Any]] = None) -> Optional[dict]:
        """Execute a query and return the first row as a dict, or None."""
        conn = self.conn
        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            self._putconn(conn)

    def fetch_all(self, query: str, params: Optional[list[Any]] = None) -> list[dict]:
        """Execute a query and return all rows as a list of dicts."""
        conn = self.conn
        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
                return [dict(row) for row in rows]
        finally:
            self._putconn(conn)

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
