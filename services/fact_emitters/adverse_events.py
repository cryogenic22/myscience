"""DR-3 — adverse-event (FAERS) fact emitter.

Lifts ``adverse_events`` rows into the facts ledger as ``adverse_event`` safety
facts routed to the ``clinical_profile`` domain. Individual FAERS case reports
are noise in a dossier (1,992 rows, mostly singletons), so we AGGREGATE per
(drug, reaction): one ``signal``-class fact per reaction with its report count
and how many were serious/fatal. Singletons are dropped (min_reports).

The framework is per-row, so ``fetch_rows`` returns the GROUP BY result and
``row_to_facts`` maps each aggregated reaction → one fact. Idempotency key is
synthetic: ``<drug_id>:<reaction>`` (an aggregate has no single source row).
"""

from __future__ import annotations

import logging
from typing import Optional

from services.fact_emitters.base import EmittedFact, FactEmitter, clamp_confidence

logger = logging.getLogger(__name__)


def build_claim(reaction: str, report_count: int, serious: int, fatal: int) -> str:
    """e.g. 'Nausea — 12 reports (8 serious, 1 fatal)'."""
    noun = "report" if report_count == 1 else "reports"
    claim = f"{reaction} — {report_count} {noun}"
    extras = []
    if serious:
        extras.append(f"{serious} serious")
    if fatal:
        extras.append(f"{fatal} fatal")
    if extras:
        claim += f" ({', '.join(extras)})"
    return claim


class AdverseEventEmitter(FactEmitter):
    name = "adverse_events"
    min_reports = 2  # drop single-report reactions (FAERS noise)

    _FETCH_SQL = """
        SELECT drug_id,
               COALESCE(reaction_meddra_pt, reaction) AS reaction,
               count(*)                                            AS report_count,
               count(*) FILTER (WHERE severity = 'serious')        AS serious_count,
               count(*) FILTER (WHERE outcome ILIKE '%%death%%')   AS fatal_count,
               max(drug_name)  AS drug_name,
               max(source_api) AS source_api,
               max(source_url) AS source_url
          FROM adverse_events
         WHERE drug_id IS NOT NULL
           AND COALESCE(reaction_meddra_pt, reaction) IS NOT NULL
         {drug_clause}
         GROUP BY drug_id, COALESCE(reaction_meddra_pt, reaction)
        HAVING count(*) >= %s
         ORDER BY report_count DESC
         {limit_clause}
    """

    def fetch_rows(self, db, *, drug_id: Optional[str] = None,
                   limit: Optional[int] = None) -> list[dict]:
        params: list = []
        drug_clause = ""
        if drug_id:
            drug_clause = "AND drug_id = %s"
            params.append(str(drug_id))
        params.append(int(self.min_reports))
        limit_sql = ""
        if limit is not None:
            limit_sql = "LIMIT %s"
            params.append(int(limit))
        sql = self._FETCH_SQL.format(drug_clause=drug_clause, limit_clause=limit_sql)
        try:
            return db.fetch_all(sql, params)
        except Exception:
            logger.exception("adverse_events fetch failed")
            return []

    def row_to_facts(self, row: dict) -> list[EmittedFact]:
        drug_id = row.get("drug_id")
        reaction = (row.get("reaction") or "").strip()
        report_count = int(row.get("report_count") or 0)
        if not drug_id or not reaction or report_count <= 0:
            return []
        serious = int(row.get("serious_count") or 0)
        fatal = int(row.get("fatal_count") or 0)
        claim = build_claim(reaction, report_count, serious, fatal)
        drug_name = row.get("drug_name") or "the drug"
        evidence = (
            f"FAERS: {reaction} reported {report_count}x for {drug_name}; "
            f"{serious} serious, {fatal} fatal."
        )
        # Confidence rises with corroboration (more reports), capped — these are
        # observed signals, not confirmed causal facts.
        confidence = clamp_confidence(min(0.85, 0.5 + 0.02 * report_count), default=0.5)
        return [
            EmittedFact(
                predicate="adverse_event",
                subject_entity_type="drug",
                subject_entity_id=str(drug_id),
                object_value={
                    "description": claim,
                    "reaction": reaction,
                    "report_count": report_count,
                    "serious_count": serious,
                    "fatal_count": fatal,
                    "source_url": row.get("source_url"),
                },
                source_row_id=f"{drug_id}:{reaction.lower()}",
                kind="point",
                confidence=confidence,
                fact_class="signal",
                evidence_text=evidence,
                source_id=row.get("source_api") or "fda_faers",
                source_url=row.get("source_url"),
            )
        ]
