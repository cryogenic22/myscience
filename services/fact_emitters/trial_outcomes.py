"""TrialOutcomeEmitter — selective lift of registry endpoints into facts.

``trial_outcomes`` holds ~3M ClinicalTrials.gov endpoint rows (PRIMARY /
SECONDARY / OTHER measures with a protocol ``description`` + ``time_frame``)
that never become facts. Row-dumping all 3M would bury every dossier, so we
emit SELECTIVELY — the same discipline AdverseEventEmitter applies to FAERS:

  SELECTION POLICY (governance, quality over volume)
  --------------------------------------------------
  A row is emitted only when ALL hold:
    1. it belongs to a trial resolvable to a drug
       (JOIN clinical_trials.drug_id NOT NULL) — no orphan endpoints; AND
    2. it has a non-empty ``measure`` (the endpoint name); AND
    3. it is a PRIMARY endpoint  OR  carries an actual ``description``
       (a real protocol/result blurb, not an empty placeholder row).
  Everything else is SKIPPED and COUNTED (skipped_no_subject / scanned), never
  silently dropped — see conservation principle #2.

These rows are the *endpoint definitions* a registry reports for a trial — the
RESULT/READOUT a trial is designed to produce — so they COMPLEMENT
ClinicalTrialEmitter (one fact per trial *record*) rather than duplicate it:
one fact per (trial, endpoint), subject = the trial's drug, predicate
``efficacy_endpoint`` → ``clinical_profile``. They are registry-reported
structured truth, so ``corporate``-class. Idempotency key = the outcome row id.

The fetch is BOUNDED (limit / drug_id like every emitter) so a single run is
safe; a full cross-drug backfill is bounded + resumable via
``scripts/backfill_fact_emitters.py`` (which iterates drugs), and the run is
owner-gated — 3M rows must never be emitted unbounded.
"""

from __future__ import annotations

import logging
from typing import Optional

from services.fact_emitters.base import EmittedFact, FactEmitter

logger = logging.getLogger(__name__)

_PRIMARY = "PRIMARY"


def _endpoint_label(outcome_type: Optional[str]) -> str:
    t = (outcome_type or "").strip().upper()
    if t == _PRIMARY:
        return "Primary endpoint"
    if t == "SECONDARY":
        return "Secondary endpoint"
    return "Endpoint"


def build_claim(row: dict) -> str:
    """e.g. 'Primary endpoint: Change in body weight (%) (Week 68) — NCT05646706'."""
    label = _endpoint_label(row.get("outcome_type"))
    measure = (row.get("measure") or "").strip()
    head = f"{label}: {measure}"
    time_frame = (row.get("time_frame") or "").strip()
    if time_frame:
        head = f"{head} ({time_frame})"
    nct = row.get("trial_id")
    if nct:
        head = f"{head} — {nct}"
    return head


class TrialOutcomeEmitter(FactEmitter):
    name = "trial_outcomes"

    # Selective fetch: JOIN to the drug spine + apply the selection policy in
    # SQL so the DB does the filtering (3M rows must never be pulled into
    # Python). PRIMARY endpoints OR any endpoint with an actual description.
    _FETCH_SQL = """
        SELECT o.id, o.trial_id, ct.drug_id,
               o.outcome_type, o.measure, o.time_frame, o.description,
               ct.phase, ct.conditions,
               o.source_api, o.source_url
          FROM trial_outcomes o
          JOIN clinical_trials ct ON ct.id = o.trial_id
         WHERE ct.drug_id IS NOT NULL
           AND o.measure IS NOT NULL AND btrim(o.measure) <> ''
           AND (
                upper(btrim(o.outcome_type)) = 'PRIMARY'
                OR (o.description IS NOT NULL AND btrim(o.description) <> '')
           )
         {drug_clause}
         ORDER BY (upper(btrim(o.outcome_type)) = 'PRIMARY') DESC,
                  o.retrieved_at DESC NULLS LAST
         {limit_clause}
    """

    def fetch_rows(self, db, *, drug_id: Optional[str] = None,
                   limit: Optional[int] = None) -> list[dict]:
        params: list = []
        drug_clause = ""
        if drug_id:
            drug_clause = "AND ct.drug_id = %s"
            params.append(str(drug_id))
        limit_sql = ""
        if limit is not None:
            limit_sql = "LIMIT %s"
            params.append(int(limit))
        sql = self._FETCH_SQL.format(drug_clause=drug_clause, limit_clause=limit_sql)
        try:
            return db.fetch_all(sql, params)
        except Exception:
            logger.exception("trial_outcomes fetch failed")
            return []

    def _qualifies(self, row: dict) -> bool:
        """The selection policy, also enforced in Python so ``row_to_facts``
        stays governed even if a caller hands it an unfiltered row."""
        if not row.get("drug_id"):
            return False
        if not (row.get("measure") or "").strip():
            return False
        is_primary = (row.get("outcome_type") or "").strip().upper() == _PRIMARY
        has_desc = bool((row.get("description") or "").strip())
        return is_primary or has_desc

    def row_to_facts(self, row: dict) -> list[EmittedFact]:
        if not self._qualifies(row):
            return []
        drug_id = row.get("drug_id")
        outcome_id = row.get("id")
        if not drug_id or not outcome_id:
            return []
        outcome_type = (row.get("outcome_type") or "").strip().upper() or "OTHER"
        claim = build_claim(row)
        measure = (row.get("measure") or "").strip()
        description = (row.get("description") or "").strip()
        # Evidence: the registry's protocol description if present, else the
        # endpoint claim itself — always something attestable (DR-5).
        evidence = description or claim
        # PRIMARY endpoints are the trial's read-out hypothesis → higher
        # confidence than secondary/other measures. Registry-reported, so
        # corporate-class structured truth, not peer-reviewed reference.
        confidence = 0.8 if outcome_type == _PRIMARY else 0.7

        def _first(seq):
            if isinstance(seq, (list, tuple)) and seq:
                return str(seq[0])
            return None

        object_value = {
            "description": claim,
            "trial_id": str(row.get("trial_id")) if row.get("trial_id") else None,
            "outcome_type": outcome_type,
            "measure": measure,
            "time_frame": row.get("time_frame"),
            "phase": row.get("phase"),
            "condition": _first(row.get("conditions")),
            "source_url": row.get("source_url"),
        }
        return [
            EmittedFact(
                predicate="efficacy_endpoint",
                subject_entity_type="drug",
                subject_entity_id=str(drug_id),
                object_value=object_value,
                source_row_id=str(outcome_id),
                kind="point",
                confidence=confidence,
                fact_class="corporate",
                evidence_text=evidence,
                source_id=row.get("source_api") or "clinical_trials_gov",
                source_url=row.get("source_url"),
            )
        ]
