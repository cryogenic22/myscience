"""BE-39 — per-tenant query audit log.

Append-only record of reads against tenant-scoped tables. Stewards
use it to verify customer isolation after the fact; CI uses it as
one signal that the BE-38 middleware is firing on every read.

Backed by ``tenant_query_audit_log`` (migration 067). 90-day
retention is enforced by ``cleanup_older_than`` which a cron /
steward invokes — we don't use a DB-side trigger to keep the
migration narrow.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from services.tenant_context import get_current_tenant

logger = logging.getLogger(__name__)


_VALID_QUERY_KINDS = frozenset({
    "search", "graph", "dossier", "catalog", "metrics",
    "ask", "synthesis", "other",
})


def record_query(
    db: Any,
    *,
    query_kind: str,
    table_name: str,
    row_count: int,
    tenant_id: Optional[str] = None,
) -> None:
    """Fire-and-forget INSERT of one audit row.

    Failures are logged at DEBUG and swallowed — audit must never
    break a user-facing read. ``tenant_id`` overrides the contextvar
    when supplied (used by tests).
    """
    if query_kind not in _VALID_QUERY_KINDS:
        logger.debug("tenant_audit: ignoring unknown query_kind=%r", query_kind)
        return
    if not isinstance(row_count, int) or row_count < 0:
        logger.debug("tenant_audit: ignoring non-positive row_count=%r", row_count)
        return
    eff_tenant = tenant_id if tenant_id is not None else get_current_tenant()
    try:
        db.execute(
            """
            INSERT INTO tenant_query_audit_log
                (tenant_id, query_kind, table_name, row_count)
            VALUES (%s, %s, %s, %s)
            """,
            [eff_tenant, query_kind, table_name, row_count],
        )
    except Exception as exc:
        logger.debug("tenant_audit.record_query failed (non-fatal): %s", exc)


def cleanup_older_than(db: Any, days: int = 90) -> int:
    """Drop audit rows older than ``days``. Returns the deleted count.

    Default 90 matches the BE-39 spec retention window.
    """
    if days <= 0:
        raise ValueError("days must be positive")
    try:
        row = db.fetch_one(
            f"""
            WITH deleted AS (
                DELETE FROM tenant_query_audit_log
                 WHERE created_at < NOW() - INTERVAL '{int(days)} days'
                RETURNING 1
            )
            SELECT COUNT(*) AS n FROM deleted
            """
        )
        return int((row or {}).get("n") or 0)
    except Exception:
        logger.exception("tenant_audit.cleanup_older_than failed")
        return 0


def read_audit(
    db: Any,
    *,
    tenant_id: str,
    since: Optional[str] = None,
    limit: int = 200,
) -> list[dict]:
    """Return recent audit events for ``tenant_id``.

    ``since`` is an ISO-8601 timestamp; if omitted the last 24h are
    returned. ``limit`` capped at 1000 server-side.
    """
    limit = max(1, min(int(limit), 1000))
    if since:
        sql = """
            SELECT id, tenant_id, query_kind, table_name, row_count, created_at
              FROM tenant_query_audit_log
             WHERE tenant_id = %s AND created_at >= %s
             ORDER BY created_at DESC
             LIMIT %s
        """
        params = [tenant_id, since, limit]
    else:
        sql = """
            SELECT id, tenant_id, query_kind, table_name, row_count, created_at
              FROM tenant_query_audit_log
             WHERE tenant_id = %s
               AND created_at > NOW() - INTERVAL '24 hours'
             ORDER BY created_at DESC
             LIMIT %s
        """
        params = [tenant_id, limit]
    try:
        return db.fetch_all(sql, params) or []
    except Exception:
        logger.exception("tenant_audit.read_audit failed")
        return []
