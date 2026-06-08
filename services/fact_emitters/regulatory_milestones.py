"""DR — regulatory-milestone fact emitter.

Turns the already-ingested ``regulatory_milestones`` rows (24,505 on prod, the
FDA approval-timeline that lands but never surfaces) into governed facts. Each
milestone row (an ORIG/SUPPL submission with an AP/TA status on a dated event)
becomes one ``regulatory_milestone`` fact whose subject is the drug;
``route_predicate_to_domain`` lands it in the dossier's ``pipeline_and_macro``
domain (approval timeline / submission events). A regulatory submission record
is FDA-authoritative structured truth → ``corporate``-class, high reliability.

One fact per milestone row, keyed by the milestone row id for idempotency.
Rows with no ``drug_id`` (cannot attribute) or no status date (no timeline
anchor) are skipped and counted — never silently dropped (conservation #2).
"""

from __future__ import annotations

import logging
from typing import Optional

from services.fact_emitters.base import EmittedFact, FactEmitter, coerce_dt

logger = logging.getLogger(__name__)

# FDA Drugs@FDA controlled vocabulary → human-readable.
_SUBMISSION_TYPE = {
    "ORIG": "Original",
    "SUPPL": "Supplement",
    "EFFICACY_SUPPL": "Efficacy supplement",
}
_STATUS = {
    "AP": "approval",
    "TA": "tentative approval",
}
_PRIORITY = {
    "PRIORITY": "Priority review",
    "STANDARD": "Standard review",
}


def build_claim(row: dict) -> str:
    """Compact human claim, e.g.
    'Original approval (Priority review) — 2017-12-05'.

    Falls back gracefully when the controlled-vocab codes are unrecognized so an
    unexpected code still produces a readable, non-empty claim."""
    stype = (row.get("submission_type") or "").strip().upper()
    sub = _SUBMISSION_TYPE.get(stype, stype.title() or "Regulatory submission")

    status_code = (row.get("submission_status") or "").strip().upper()
    status = _STATUS.get(status_code)
    if status:
        head = f"{sub} {status}"
    else:
        # Unknown/empty status — keep the submission noun, append raw code.
        head = f"{sub} ({status_code})" if status_code else sub

    priority = _PRIORITY.get((row.get("review_priority") or "").strip().upper())
    if priority:
        head = f"{head} ({priority})"

    date_str = str(row.get("submission_status_date") or "").strip()
    if date_str:
        head = f"{head} — {date_str}"
    return head


class RegulatoryMilestoneEmitter(FactEmitter):
    name = "regulatory_milestones"

    _FETCH_SQL = """
        SELECT id, drug_id, submission_type, submission_number,
               submission_status, submission_status_date, review_priority,
               document_url, source_api, source_url
          FROM regulatory_milestones
         WHERE drug_id IS NOT NULL
           AND submission_status_date IS NOT NULL
         {drug_clause}
         ORDER BY submission_status_date DESC NULLS LAST
         {limit_clause}
    """

    def fetch_rows(self, db, *, drug_id: Optional[str] = None,
                   limit: Optional[int] = None) -> list[dict]:
        params: list = []
        drug_clause = ""
        if drug_id:
            drug_clause = "AND drug_id = %s"
            params.append(str(drug_id))
        limit_sql = ""
        if limit is not None:
            limit_sql = "LIMIT %s"
            params.append(int(limit))
        sql = self._FETCH_SQL.format(drug_clause=drug_clause, limit_clause=limit_sql)
        try:
            return db.fetch_all(sql, params)
        except Exception:
            logger.exception("regulatory_milestones fetch failed")
            return []

    def row_to_facts(self, row: dict) -> list[EmittedFact]:
        drug_id = row.get("drug_id")
        ms_id = row.get("id")
        # Conservation #2: skip — never drop silently. run_emitter only counts
        # rows that yield a fact, so these are visible as the fetch/scan gap.
        if not drug_id or not ms_id:
            return []
        valid_from = coerce_dt(row.get("submission_status_date"))
        if valid_from is None:
            return []

        claim = build_claim(row)
        source_url = row.get("source_url") or row.get("document_url")
        object_value = {
            "description": claim,
            "submission_type": row.get("submission_type"),
            "submission_number": row.get("submission_number"),
            "status": row.get("submission_status"),
            "review_priority": row.get("review_priority"),
            "milestone_date": str(row.get("submission_status_date") or ""),
            "source_url": source_url,
        }
        return [
            EmittedFact(
                predicate="regulatory_milestone",
                subject_entity_type="drug",
                subject_entity_id=str(drug_id),
                object_value=object_value,
                source_row_id=str(ms_id),
                kind="point",
                valid_from=valid_from,
                confidence=0.9,
                fact_class="corporate",
                evidence_text=claim,
                source_id=row.get("source_api") or "fda_drugsfda",
                source_url=source_url,
            )
        ]
