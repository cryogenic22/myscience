"""Gap remediation persistence (UX05b / PB-UX05b).

A thin store over the gap_remediations table (migration 075): the analyst's
chosen remediation per dossier gap (primary_research / accept_uncertainty /
descope), durable + auditable, keyed by (engagement_id, gap_domain). Upsert —
the latest choice wins. Read returns a {gap_domain: {...}} map the gaps stage
overlays onto its derived gaps.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

VALID_REMEDIATIONS = {"primary_research", "accept_uncertainty", "descope", "pending"}

_UPSERT_SQL = """
    INSERT INTO gap_remediations (engagement_id, gap_domain, remediation, note, created_by)
    VALUES (%(engagement_id)s, %(gap_domain)s, %(remediation)s, %(note)s, %(created_by)s)
    ON CONFLICT (engagement_id, gap_domain) DO UPDATE
        SET remediation = EXCLUDED.remediation,
            note        = EXCLUDED.note,
            created_by  = EXCLUDED.created_by,
            updated_at  = NOW()
    RETURNING gap_domain, remediation, note, created_by, updated_at
"""

_LIST_SQL = """
    SELECT gap_domain, remediation, note, created_by, updated_at
      FROM gap_remediations
     WHERE engagement_id = %s
"""


def set_remediation(
    db,
    engagement_id: str,
    gap_domain: str,
    remediation: str,
    *,
    note: Optional[str] = None,
    created_by: str = "system",
) -> dict:
    """Upsert the remediation for one gap. Raises ValueError on a bad value."""
    if remediation not in VALID_REMEDIATIONS:
        raise ValueError(
            f"remediation must be one of {sorted(VALID_REMEDIATIONS)}, got {remediation!r}")
    row = db.fetch_one(_UPSERT_SQL, {
        "engagement_id": str(engagement_id),
        "gap_domain": gap_domain,
        "remediation": remediation,
        "note": note,
        "created_by": created_by,
    })
    return _row_to_dict(row) if row else {
        "gap_domain": gap_domain, "remediation": remediation, "note": note,
    }


def list_remediations(db, engagement_id: str) -> dict[str, dict]:
    """Return {gap_domain: {remediation, note, created_by, updated_at}} for the
    engagement — the overlay the gaps stage applies onto its derived gaps."""
    try:
        rows = db.fetch_all(_LIST_SQL, [str(engagement_id)]) or []
    except Exception:
        logger.exception("list_remediations failed for %s", engagement_id)
        return {}
    return {r["gap_domain"]: _row_to_dict(r) for r in rows}


def _row_to_dict(r) -> dict:
    updated = r.get("updated_at")
    return {
        "gap_domain": r.get("gap_domain"),
        "remediation": r.get("remediation"),
        "note": r.get("note"),
        "created_by": r.get("created_by"),
        "updated_at": updated.isoformat() if hasattr(updated, "isoformat") else updated,
    }
