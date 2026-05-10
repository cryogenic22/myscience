"""BE-6 — Dossier composer.

Single composer that joins existing service-layer reads into one
``DossierResult`` payload PB-301..PB-305 render without further
backend calls. The composer is intentionally tolerant: when an
underlying service raises (DB hiccup / table missing / partial
deploy), the relevant section comes back empty rather than
collapsing the whole dossier.

Output shape (per AGENT_BACKLOG#BE-6)::

    {
      "entity":           {id, type, name, aliases[], identity_fields},
      "synthesis":        {text_with_citation_marks, last_synthesised_at, owner_user_id},
      "recent_moves":     [{ts, kbq_tag, headline, signal_id?, transition?}],
      "evidence_refs":    [EvidenceItemResponse, ...],   # up to 50, by relevance
      "watching":         [{user_id, name, avatar_url}, ...up to 10],
      "related_entities": [{id, type, name, relation, edge_count}, ...]
    }
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


VALID_ENTITY_TYPES = ("drug", "company", "mechanism", "trial", "therapeutic_area")

DOSSIER_MAX_EVIDENCE = 50
DOSSIER_MAX_WATCHING = 10
DOSSIER_RECENT_MOVES_DAYS = 30
DOSSIER_RELATED_LIMIT = 25


@dataclass
class DossierResult:
    entity: dict
    synthesis: Optional[dict]
    recent_moves: list[dict] = field(default_factory=list)
    evidence_refs: list[dict] = field(default_factory=list)
    watching: list[dict] = field(default_factory=list)
    related_entities: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "entity":           dict(self.entity),
            "synthesis":        dict(self.synthesis) if self.synthesis else None,
            "recent_moves":     list(self.recent_moves),
            "evidence_refs":    list(self.evidence_refs),
            "watching":         list(self.watching),
            "related_entities": list(self.related_entities),
        }


_TYPE_TO_TABLE: dict[str, tuple[str, str, str]] = {
    "drug":             ("drugs",                 "id",  "generic_name"),
    "company":          ("companies",             "id",  "name"),
    "mechanism":        ("mechanisms_of_action",  "id",  "name"),
    "trial":            ("clinical_trials",       "id",  "official_title"),
    "therapeutic_area": ("therapeutic_areas",     "id",  "name"),
}


def _looks_like_uuid(s: str) -> bool:
    return len(s) == 36 and s.count("-") == 4


def _resolve_entity(db: Any, entity_type: str, slug_or_id: str) -> Optional[dict]:
    """Look up an entity row by UUID or by name slug. Returns the
    canonical {id, type, name, aliases, identity_fields} shape."""
    if entity_type not in _TYPE_TO_TABLE:
        return None
    table, id_col, name_col = _TYPE_TO_TABLE[entity_type]

    if _looks_like_uuid(slug_or_id):
        sql = f"SELECT id::text AS id, * FROM {table} WHERE id::text = %s LIMIT 1"
    else:
        sql = (
            f"SELECT id::text AS id, * FROM {table} "
            f"WHERE LOWER({name_col}) = LOWER(%s) LIMIT 1"
        )
    try:
        row = db.fetch_one(sql, [slug_or_id])
    except Exception:
        logger.exception("dossier: entity lookup failed (%s/%s)", entity_type, slug_or_id)
        return None
    if not row:
        return None

    name = row.get(name_col) or row.get("name") or row.get("generic_name") or str(row["id"])
    aliases: list[str] = []
    raw_aliases = row.get("aliases") or row.get("alias_names") or []
    if isinstance(raw_aliases, list):
        aliases = [str(a) for a in raw_aliases if a]

    # Identity fields = the row minus large vector columns.
    identity_fields = {
        k: v for k, v in dict(row).items()
        if k not in {"id", name_col} and not k.endswith("_embedding") and v is not None
    }
    return {
        "id":              str(row["id"]),
        "type":            entity_type,
        "name":            name,
        "aliases":         aliases,
        "identity_fields": identity_fields,
    }


def _recent_moves(db: Any, entity_type: str, entity_id: str) -> list[dict]:
    """30-day reverse-chrono signals + state transitions for an entity."""
    out: list[dict] = []
    try:
        rows = db.fetch_all(
            """
            SELECT id, headline, kbq_tags, primary_entity_type,
                   primary_entity_id, created_at
              FROM signals
             WHERE primary_entity_type = %s
               AND primary_entity_id   = %s
               AND created_at > NOW() - INTERVAL '%s days'
             ORDER BY created_at DESC
             LIMIT 50
            """ % ("%s", "%s", int(DOSSIER_RECENT_MOVES_DAYS)),
            [entity_type, entity_id],
        ) or []
        for r in rows:
            out.append({
                "ts":         r["created_at"].isoformat()
                              if r.get("created_at") and hasattr(r["created_at"], "isoformat")
                              else None,
                "kbq_tag":    (r.get("kbq_tags") or [None])[0] if r.get("kbq_tags") else None,
                "headline":   r.get("headline"),
                "signal_id":  str(r.get("id")) if r.get("id") else None,
                "transition": None,
            })
    except Exception:
        logger.debug("dossier: recent_moves lookup failed (table missing or DB)", exc_info=True)
    return out


def _evidence_refs(db: Any, entity_type: str, entity_id: str) -> list[dict]:
    """Most recent evidence_records that mention the entity (up to 50)."""
    out: list[dict] = []
    try:
        rows = db.fetch_all(
            """
            SELECT e.evidence_id, e.source_id, e.source_url,
                   e.source_name, e.source_tier,
                   e.published_at, e.snippet, e.extracted_text,
                   e.retrieved_at, e.confidence
              FROM evidence_records e
              JOIN claim_evidence_links l ON l.evidence_id = e.evidence_id
              JOIN claims c ON c.claim_id = l.claim_id
             WHERE c.entity_type = %s AND c.entity_id::text = %s
             ORDER BY COALESCE(e.published_at, e.retrieved_at) DESC NULLS LAST
             LIMIT %s
            """,
            [entity_type, entity_id, DOSSIER_MAX_EVIDENCE],
        ) or []
        for r in rows:
            ts = r.get("published_at") or r.get("retrieved_at")
            out.append({
                "evidence_id": str(r["evidence_id"]),
                "source_id":   r.get("source_id"),
                "source_name": r.get("source_name"),
                "source_tier": r.get("source_tier"),
                "source_url":  r.get("source_url"),
                "snippet":     r.get("snippet") or (
                    (r.get("extracted_text") or "")[:200] if r.get("extracted_text") else None
                ),
                "published_at": ts.isoformat() if ts and hasattr(ts, "isoformat") else None,
                "confidence":   r.get("confidence"),
            })
    except Exception:
        logger.debug("dossier: evidence_refs lookup failed", exc_info=True)
    return out


def _watching(db: Any, entity_type: str, entity_id: str) -> list[dict]:
    """Up to 10 analyst face-stack avatars (PB-305)."""
    out: list[dict] = []
    try:
        rows = db.fetch_all(
            """
            SELECT u.id::text AS user_id, u.email,
                   COALESCE(u.display_name, u.email) AS name
              FROM watchlist_entries w
              JOIN users u ON u.id = w.user_id
             WHERE w.entity_type = %s AND w.entity_id::text = %s
             ORDER BY w.added_at DESC
             LIMIT %s
            """,
            [entity_type, entity_id, DOSSIER_MAX_WATCHING],
        ) or []
        for r in rows:
            out.append({
                "user_id": r.get("user_id"),
                "name":    r.get("name"),
                "avatar_url": None,  # FE renders initials from name
            })
    except Exception:
        logger.debug("dossier: watching lookup failed", exc_info=True)
    return out


def _related_entities(db: Any, entity_type: str, entity_id: str) -> list[dict]:
    """Entity neighborhood from entity_links, up to 25 ranked by edge count."""
    out: list[dict] = []
    try:
        rows = db.fetch_all(
            """
            SELECT
              CASE WHEN source_entity_id::text = %s
                   THEN target_entity_id::text ELSE source_entity_id::text END
                  AS neighbor_id,
              CASE WHEN source_entity_id::text = %s
                   THEN target_entity_type ELSE source_entity_type END
                  AS neighbor_type,
              link_type,
              COUNT(*)::int AS edge_count
            FROM entity_links
            WHERE source_entity_id::text = %s OR target_entity_id::text = %s
            GROUP BY neighbor_id, neighbor_type, link_type
            ORDER BY edge_count DESC
            LIMIT %s
            """,
            [entity_id, entity_id, entity_id, entity_id, DOSSIER_RELATED_LIMIT],
        ) or []
        for r in rows:
            out.append({
                "id":         r.get("neighbor_id"),
                "type":       r.get("neighbor_type"),
                "name":       None,  # backend sends id+type; FE resolves label
                "relation":   r.get("link_type"),
                "edge_count": int(r.get("edge_count") or 0),
            })
    except Exception:
        logger.debug("dossier: related_entities lookup failed", exc_info=True)
    return out


def compose_dossier(db: Any, *, entity_type: str, slug_or_id: str) -> Optional[DossierResult]:
    """Top-level composer. Returns None if the entity itself can't be
    resolved; otherwise a DossierResult with whichever sections succeeded."""
    if entity_type not in VALID_ENTITY_TYPES:
        raise ValueError(
            f"entity_type must be one of {VALID_ENTITY_TYPES}, got {entity_type!r}"
        )
    entity = _resolve_entity(db, entity_type, slug_or_id)
    if entity is None:
        return None

    eid = entity["id"]
    return DossierResult(
        entity=entity,
        synthesis=None,  # Frontend hits services.llm.synthesize_dossier separately
        recent_moves=_recent_moves(db, entity_type, eid),
        evidence_refs=_evidence_refs(db, entity_type, eid),
        watching=_watching(db, entity_type, eid),
        related_entities=_related_entities(db, entity_type, eid),
    )
