"""DR-1 — clinical-trials fact emitter.

Lifts ``clinical_trials`` rows (5,177 with a resolved drug on prod, 2 Jun 2026)
into the facts ledger as ``clinical_trial`` facts, which
``route_predicate_to_domain`` lands in the dossier's ``clinical_profile``
domain — the single biggest gap-fill from data we already hold. One fact per
trial; the subject is the trial's ``drug_id``. The trial *record* (phase /
status / enrollment from a registry) is ``corporate``-class structured truth,
not peer-reviewed ``reference`` and not synthesized ``inferred``.
"""

from __future__ import annotations

import logging
from typing import Optional

from services.fact_emitters.base import (
    EmittedFact,
    FactEmitter,
    clamp_confidence,
    coerce_dt,
)

logger = logging.getLogger(__name__)


def _first(seq) -> Optional[str]:
    if isinstance(seq, (list, tuple)) and seq:
        return str(seq[0])
    return None


def _humanize_status(status: Optional[str]) -> str:
    if not status:
        return ""
    return status.replace("_", " ").strip().title()


def build_claim(row: dict) -> str:
    """Compact human claim. Rendered by the dossier as 'Clinical trial: <claim>',
    so the word 'trial' is intentionally omitted here to avoid redundancy, e.g.
    'Phase 3, Completed, in Obesity (NCT05646706) — enrollment 1,961'."""
    bits = []
    phase = (row.get("phase") or "").strip()
    if phase and phase.lower() != "n/a":
        bits.append(phase)
    status = _humanize_status(row.get("status"))
    if status:
        bits.append(status)
    cond = _first(row.get("conditions"))
    if cond:
        bits.append(f"in {cond}")
    head = ", ".join(bits) if bits else "Registered study"
    nct = row.get("id")
    if nct:
        head = f"{head} ({nct})"
    enrollment = row.get("actual_enrollment") or row.get("enrollment_target")
    if enrollment:
        try:
            head = f"{head} — enrollment {int(enrollment):,}"
        except (TypeError, ValueError):
            pass
    return head


def _evidence_text(row: dict, claim: str) -> str:
    """Best available human snippet to attest (DR-5). Prefer the official
    title; append a failure reason for terminated/withdrawn trials."""
    title = (row.get("official_title") or "").strip()
    base = title or claim
    reason = (row.get("failure_reason") or "").strip()
    if reason:
        base = f"{base} — {reason}"
    return base


class ClinicalTrialEmitter(FactEmitter):
    name = "clinical_trials"

    _FETCH_SQL = """
        SELECT id, drug_id, phase, status, conditions, official_title,
               enrollment_target, actual_enrollment,
               start_date, completion_date, primary_completion_date,
               failure_reason, source_api, source_url, quality_score
          FROM clinical_trials
         WHERE drug_id IS NOT NULL
         {drug_clause}
         ORDER BY completion_date DESC NULLS LAST, start_date DESC NULLS LAST
         {limit_clause}
    """

    def fetch_rows(self, db, *, drug_id: Optional[str] = None,
                   limit: Optional[int] = None) -> list[dict]:
        clauses = ""
        params: list = []
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
            logger.exception("clinical_trials fetch failed")
            return []

    def row_to_facts(self, row: dict) -> list[EmittedFact]:
        drug_id = row.get("drug_id")
        trial_id = row.get("id")
        if not drug_id or not trial_id:
            return []
        claim = build_claim(row)
        valid_from = (
            coerce_dt(row.get("completion_date"))
            or coerce_dt(row.get("primary_completion_date"))
            or coerce_dt(row.get("start_date"))
        )
        object_value = {
            "description": claim,
            "trial_id": str(trial_id),
            "phase": row.get("phase"),
            "status": row.get("status"),
            "condition": _first(row.get("conditions")),
            "enrollment": row.get("actual_enrollment") or row.get("enrollment_target"),
            "title": row.get("official_title"),
            "source_url": row.get("source_url"),
        }
        return [
            EmittedFact(
                predicate="clinical_trial",
                subject_entity_type="drug",
                subject_entity_id=str(drug_id),
                object_value=object_value,
                source_row_id=str(trial_id),
                kind="point",
                valid_from=valid_from,
                confidence=clamp_confidence(row.get("quality_score"), default=0.8),
                fact_class="corporate",
                evidence_text=_evidence_text(row, claim),
                source_id=row.get("source_api") or "clinical_trials_gov",
                source_url=row.get("source_url"),
            )
        ]
