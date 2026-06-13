"""D1 — regulatory-milestone fact emitter.

`regulatory_milestones` (FDA Orange Book / submission records) lands on prod but
is UNREACHABLE from chat/dossier — it never becomes a fact. This emitter converts
each approved submission into a governed ``regulatory_approval`` fact (already
routed to the pipeline_and_macro domain), so the regulatory lens stops rendering
empty for drugs that actually carry approval history.

General substrate enrichment (CI dossier, chat, future launch) — keyed off the
table, not any TA. Same framework/governance as the other emitters: ``row_to_facts``
is pure and DB-free; idempotency stamps the milestone id as ``source_row_id``.

Status vocabulary (Orange Book): AP = approved, TA = tentative approval. Other
statuses (or missing status) are skipped — we only assert an approval we can see.
"""

from __future__ import annotations

import logging
from typing import Optional

from services.fact_emitters.base import EmittedFact, FactEmitter, coerce_dt

logger = logging.getLogger(__name__)

# submission_status → human label. Only these are emitted (a real approval event).
_APPROVAL_STATUS = {
    "ap": "approved",
    "ta": "tentatively approved",
}

# submission_type → phrasing for the claim.
_SUBMISSION_LABEL = {
    "orig": "original application",
    "suppl": "supplement",
    "efficacy_suppl": "efficacy supplement",
}


def _submission_phrase(submission_type: Optional[str]) -> str:
    return _SUBMISSION_LABEL.get((submission_type or "").strip().lower(), "submission")


class RegulatoryMilestoneEmitter(FactEmitter):
    name = "regulatory_milestones"

    _FETCH_SQL = """
        SELECT id, drug_id, submission_type, submission_number, submission_status,
               submission_status_date, review_priority, document_url,
               source_api, source_url
          FROM regulatory_milestones
         WHERE drug_id IS NOT NULL
         {drug_clause}
         {limit_clause}
    """

    def fetch_rows(self, db, *, drug_id: Optional[str] = None,
                   limit: Optional[int] = None) -> list[dict]:
        clauses, params = "", []
        if drug_id:
            clauses = "AND drug_id = %s"
            params.append(str(drug_id))
        limit_sql = ""
        if limit is not None:
            limit_sql = "LIMIT %s"
            params.append(int(limit))
        sql = self._FETCH_SQL.format(drug_clause=clauses, limit_clause=limit_sql)
        try:
            return db.fetch_all(sql, params)
        except Exception:
            logger.exception("regulatory_milestones fetch failed")
            return []

    def row_to_facts(self, row: dict) -> list[EmittedFact]:
        drug_id = row.get("drug_id")
        mid = row.get("id")
        status = (row.get("submission_status") or "").strip().lower()
        if not drug_id or not mid or status not in _APPROVAL_STATUS:
            return []
        drug_id = str(drug_id)

        status_label = _APPROVAL_STATUS[status]
        sub_phrase = _submission_phrase(row.get("submission_type"))
        priority = (row.get("review_priority") or "").strip()
        number = (row.get("submission_number") or "").strip()
        claim = f"FDA {status_label} ({sub_phrase}"
        if number:
            claim += f" {number}"
        claim += ")"
        if priority and priority.lower() == "priority":
            claim += " — priority review"

        return [EmittedFact(
            predicate="regulatory_approval",
            subject_entity_type="drug",
            subject_entity_id=drug_id,
            object_value={
                "description": claim,
                "submission_type": row.get("submission_type"),
                "submission_number": number or None,
                "submission_status": row.get("submission_status"),
                "review_priority": priority or None,
                "document_url": row.get("document_url"),
                "source_url": row.get("source_url"),
            },
            source_row_id=str(mid),
            kind="point",
            valid_from=coerce_dt(row.get("submission_status_date")),
            # Orange Book is an authoritative regulatory record → corporate (a
            # documented institutional event), high confidence.
            confidence=0.9,
            fact_class="corporate",
            evidence_text=claim,
            source_id=row.get("source_api") or "fda_orange_book",
            source_url=row.get("source_url"),
        )]
