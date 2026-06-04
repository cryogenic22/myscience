"""L6 — competition fact emitter (fills KBQ-2 / competitive domain).

Lifts ``COMPETES_WITH`` entity_links (drug↔drug — 11,747 on prod, 4 Jun 2026)
into the facts ledger as ``competitor`` facts, so the dossier's *competitive*
domain AND KBQ-2 (Competitors) carry real, cited rivals from the entity graph —
not just the read-time related-entity scan.

The ``competitor`` predicate already routes to the competitive domain via the
dossier's prefix rule; KBQ-2 mapping is added in ``services/kbq_views.py``.
Junk targets (placebo / dosage-arm / trial-arm rows) are dropped via the shared
``_is_junk_competitor_name`` filter so the spine's un-consolidated variant rows
don't masquerade as rivals. ``fact_class='inferred'`` (a derived graph edge);
confidence carried from the link. Idempotency (DR-0 contract):
``source_row_id`` = entity_link id. Pure ``row_to_facts``; only ``fetch_rows``
touches the DB.
"""
from __future__ import annotations

import logging
from typing import Optional

from services.dossier_kb import _is_junk_competitor_name
from services.fact_emitters.base import EmittedFact, FactEmitter

logger = logging.getLogger(__name__)


class CompetitionEmitter(FactEmitter):
    name = "competition"

    _FETCH_SQL = """
        SELECT el.id              AS link_id,
               el.source_entity_id AS drug_id,
               el.target_entity_id AS competitor_id,
               el.confidence       AS confidence,
               el.provenance_source AS provenance_source,
               COALESCE(t.brand_name, t.generic_name) AS competitor_name,
               COALESCE(s.brand_name, s.generic_name) AS subject_name
          FROM entity_links el
          JOIN drugs s ON s.id = el.source_entity_id::uuid
          JOIN drugs t ON t.id = el.target_entity_id::uuid
         WHERE el.link_type = 'COMPETES_WITH'
           AND el.source_entity_type = 'drug'
           AND el.target_entity_type = 'drug'
           AND COALESCE(s.record_status, '') NOT IN ('merged', 'superseded')
           AND COALESCE(t.record_status, '') NOT IN ('merged', 'superseded')
           {drug_clause}
         ORDER BY el.source_entity_id
         {limit_clause}
    """

    def fetch_rows(self, db, *, drug_id: Optional[str] = None,
                   limit: Optional[int] = None) -> list[dict]:
        clauses = ""
        params: list = []
        if drug_id:
            clauses = "AND el.source_entity_id = %s"
            params.append(str(drug_id))
        limit_sql = ""
        if limit is not None:
            limit_sql = "LIMIT %s"
            params.append(int(limit))
        sql = self._FETCH_SQL.format(drug_clause=clauses, limit_clause=limit_sql)
        try:
            return db.fetch_all(sql, params)
        except Exception:
            logger.exception("competition fetch failed")
            return []

    def row_to_facts(self, row: dict) -> list[EmittedFact]:
        drug_id = row.get("drug_id")
        comp_id = row.get("competitor_id")
        comp_name = (row.get("competitor_name") or "").strip()
        if not drug_id or not comp_id or not comp_name:
            return []
        # Drop variant/placebo/arm rows masquerading as rivals.
        if _is_junk_competitor_name(comp_name, row.get("subject_name")):
            return []

        conf = row.get("confidence")
        try:
            conf = float(conf) if conf is not None else 0.6
        except (TypeError, ValueError):
            conf = 0.6
        conf = max(0.3, min(conf, 0.95))

        claim = f"Competes with {comp_name}"
        return [
            EmittedFact(
                predicate="competitor",
                subject_entity_type="drug",
                subject_entity_id=str(drug_id),
                object_value={
                    "description": claim,
                    "competitor": comp_name,
                    "competitor_id": str(comp_id),
                },
                source_row_id=str(row.get("link_id")),
                kind="point",
                confidence=conf,
                fact_class="inferred",        # derived graph edge
                evidence_text=claim,
                source_id=row.get("provenance_source") or "entity_graph",
                source_url=None,
            )
        ]
