"""SQL query tool with validation and safety guards."""

from __future__ import annotations

import logging
import re
import time
from typing import Optional

from db import Database
from services.agent.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# DML / DDL patterns that must never be executed
_BLOCKED_PATTERNS = re.compile(
    r'(?:^|\s)(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|'
    r'COPY|EXECUTE|CALL|DO\s|RESET|DISCARD|VACUUM|CLUSTER|'
    r'REINDEX|LOCK|COMMENT|SECURITY|LOAD|IMPORT)\b',
    re.IGNORECASE,
)

# Max rows to return
DEFAULT_MAX_ROWS = 100

# Query timeout in seconds
DEFAULT_TIMEOUT_SECONDS = 10


class SQLQueryTool(BaseTool):
    """Executes read-only SQL queries against the database.

    Safety measures:
    - DML/DDL regex block
    - Table whitelist from domain pack
    - LIMIT enforcement
    - READ ONLY transaction with timeout
    """

    def __init__(self, db: Database, allowed_tables: set[str], max_rows: int = DEFAULT_MAX_ROWS):
        self._db = db
        self._allowed_tables = {t.lower() for t in allowed_tables}
        self._max_rows = max_rows

    @property
    def name(self) -> str:
        return "sql"

    def execute(self, action: str, params: dict, prior_results: Optional[dict] = None) -> ToolResult:
        """Execute a SQL query.

        params:
            sql: str — the SQL query to execute
            query_params: list — optional parameterized values
        """
        sql = params.get("sql", "").strip()
        query_params = params.get("query_params", [])

        if not sql:
            return ToolResult(tool="sql", success=False, error="No SQL query provided")

        # Normalize known enum values in the SQL (LLM non-determinism fix)
        sql = self._normalize_enums(sql)

        # Validate: block DML/DDL
        error = self._validate_sql(sql)
        if error:
            return ToolResult(tool="sql", success=False, error=error)

        # Enforce LIMIT
        sql = self._enforce_limit(sql)

        logger.info("SQL tool executing: %s | params=%s", sql[:300], query_params)
        start = time.time()
        try:
            rows = self._execute_readonly(sql, query_params)
            elapsed = time.time() - start
            logger.info("SQL tool success: %d rows in %.2fs", len(rows), elapsed)

            columns = list(rows[0].keys()) if rows else []
            return ToolResult(
                tool="sql",
                success=True,
                data=rows,
                columns=columns,
                row_count=len(rows),
                metadata={
                    "sql": sql,
                    "params": query_params,
                    "elapsed_seconds": round(elapsed, 3),
                },
            )
        except Exception as e:
            elapsed = time.time() - start
            logger.warning("SQL tool error (%.2fs): %s — %s", elapsed, sql[:200], e)
            return ToolResult(
                tool="sql",
                success=False,
                error=f"SQL execution error: {str(e)[:300]}",
                metadata={"sql": sql, "elapsed_seconds": round(elapsed, 3)},
            )

    def _validate_sql(self, sql: str) -> Optional[str]:
        """Return an error message if the SQL is not safe, else None."""
        # Block DML/DDL
        if _BLOCKED_PATTERNS.search(sql):
            return "Query contains blocked SQL keywords (DML/DDL not allowed)"

        # Must be a SELECT or WITH (CTE)
        stripped = sql.lstrip().upper()
        if not (stripped.startswith("SELECT") or stripped.startswith("WITH")):
            return "Only SELECT and WITH (CTE) queries are allowed"

        # Table whitelist check
        tables_in_query = self._extract_table_references(sql)
        unauthorized = tables_in_query - self._allowed_tables
        if unauthorized:
            return f"Unauthorized table access: {', '.join(sorted(unauthorized))}"

        return None

    def _extract_table_references(self, sql: str) -> set[str]:
        """Extract table names from FROM and JOIN clauses (best-effort)."""
        tables = set()
        # Match FROM/JOIN table_name patterns
        pattern = re.compile(
            r'(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)',
            re.IGNORECASE,
        )
        for match in pattern.finditer(sql):
            tables.add(match.group(1).lower())
        return tables

    # Known clinical_trials.status enum mappings (mixed-case → correct UPPERCASE)
    _STATUS_NORMALIZATIONS = {
        "'recruiting'": "'RECRUITING'",
        "'active, not recruiting'": "'ACTIVE_NOT_RECRUITING'",
        "'active'": "'RECRUITING'",  # common LLM mistake
        "'completed'": "'COMPLETED'",
        "'terminated'": "'TERMINATED'",
        "'withdrawn'": "'WITHDRAWN'",
        "'not yet recruiting'": "'NOT_YET_RECRUITING'",
        "'suspended'": "'SUSPENDED'",
        "'enrolling by invitation'": "'ENROLLING_BY_INVITATION'",
        # Mixed case variants
        "'Recruiting'": "'RECRUITING'",
        "'Active, not recruiting'": "'ACTIVE_NOT_RECRUITING'",
        "'Active, Not Recruiting'": "'ACTIVE_NOT_RECRUITING'",
        "'Completed'": "'COMPLETED'",
        "'Terminated'": "'TERMINATED'",
        "'Withdrawn'": "'WITHDRAWN'",
        "'Not yet recruiting'": "'NOT_YET_RECRUITING'",
        "'Suspended'": "'SUSPENDED'",
    }

    def _normalize_enums(self, sql: str) -> str:
        """Post-process SQL to fix known enum value casing issues."""
        normalized = sql
        for wrong, correct in self._STATUS_NORMALIZATIONS.items():
            if wrong in normalized:
                normalized = normalized.replace(wrong, correct)
                logger.debug("Normalized enum: %s → %s", wrong, correct)
        return normalized

    def _enforce_limit(self, sql: str) -> str:
        """Add or replace LIMIT to enforce max_rows."""
        # Check if there's already a LIMIT clause
        if re.search(r'\bLIMIT\s+\d+', sql, re.IGNORECASE):
            # Replace existing LIMIT if it exceeds max_rows
            def clamp_limit(m):
                val = int(m.group(1))
                return f"LIMIT {min(val, self._max_rows)}"
            return re.sub(r'\bLIMIT\s+(\d+)', clamp_limit, sql, flags=re.IGNORECASE)
        # Add LIMIT at the end (before trailing semicolon if present)
        sql = sql.rstrip().rstrip(";")
        return f"{sql} LIMIT {self._max_rows}"

    def _execute_readonly(self, sql: str, params: list) -> list[dict]:
        """Execute SQL in a READ ONLY transaction with timeout."""
        conn = self._db.conn
        old_autocommit = conn.autocommit
        try:
            # Start a fresh transaction block
            conn.autocommit = False
            with conn.cursor() as cur:
                # BEGIN a new transaction, then set it read-only with a timeout
                cur.execute("BEGIN")
                cur.execute(f"SET LOCAL statement_timeout = '{DEFAULT_TIMEOUT_SECONDS * 1000}'")
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute(sql, params or None)
                columns = [desc[0] for desc in cur.description] if cur.description else []
                raw_rows = cur.fetchall()
                conn.rollback()  # READ ONLY, so rollback is fine
                # Convert to list of dicts
                if raw_rows and isinstance(raw_rows[0], dict):
                    return raw_rows
                return [dict(zip(columns, row)) for row in raw_rows]
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            conn.autocommit = old_autocommit
