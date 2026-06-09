"""L2 — phase-transition / development-lens fact emitter.

The ``development_success`` playbook dimension routes to four predicates —
``phase_transition``, ``discontinuation``, ``approval_event``, ``clinical_trial``
— but only the last one existed in the ledger, so the lens rendered PARTIAL
(the coverage analyzer's majority-missing rule: a single catch-all predicate must
not mask that the lens-specific ones don't exist). This emitter derives the other
three from data we already hold, flipping the lens to COVERED and making the
headline ``ask_success_rate`` question answerable from the substrate.

``clinical_trials`` is a current-snapshot table (one phase + status per trial),
not a per-trial time-series, so transitions are derived *across a drug's trial
set*: the distinct phases its trials reached describe the development trajectory.

  * ``phase_transition`` — for each upward step between consecutive phases the
    drug actually reached (e.g. it has both Phase 2 and Phase 3 trials), one
    fact dated at the earliest start of the higher phase. ``corporate`` class:
    the registry records each trial's phase directly; the "advanced" framing is
    a light, faithful aggregation.
  * ``approval_event`` — a Phase 4 (post-marketing) trial implies the drug
    reached market in at least one jurisdiction. That is an *inference*, so the
    fact is ``inferred`` class at lower confidence — never asserted as a
    ground-truth regulatory approval (that belongs to the regulatory tables).
  * ``discontinuation`` — one fact per TERMINATED / WITHDRAWN / SUSPENDED trial
    (registry status is authoritative → ``corporate``). A terminated trial is a
    development setback signal, not necessarily a discontinued *drug* — the claim
    is phrased at the trial level to avoid over-claiming.

Same framework + governance as the DR-1.. emitters: ``row_to_facts`` is pure and
DB-free; idempotency stamps a stable ``source_row_id`` (the trial id for
discontinuations, a synthetic ``<drug>:to_phase_<n>`` / ``<drug>:approval`` key
for the per-drug aggregates).
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from services.fact_emitters.base import (
    EmittedFact,
    FactEmitter,
    coerce_dt,
)

logger = logging.getLogger(__name__)

DISCONTINUED_STATUSES = {"terminated", "withdrawn", "suspended"}
PHASE_LABEL = {1: "Phase 1", 2: "Phase 2", 3: "Phase 3", 4: "Phase 4"}
_PHASE_RE = re.compile(r"phase\s*([1-4])", re.IGNORECASE)


def phase_ordinal(phase: Optional[str]) -> Optional[int]:
    """The highest phase number 1–4 named in ``phase``, or None.

    Handles the real prod vocabulary: 'Phase 3', 'EARLY_Phase 1' (→1),
    combined 'Phase 2, Phase 3' (→ the max, 3), and 'N/A' / 'None' (→ None)."""
    if not phase:
        return None
    nums = _PHASE_RE.findall(str(phase))
    if not nums:
        return None
    return max(int(n) for n in nums)


def _first(seq) -> Optional[str]:
    if isinstance(seq, (list, tuple)) and seq:
        return str(seq[0])
    return None


def _earliest_trial_dt(trial: dict) -> Optional[object]:
    return (
        coerce_dt(trial.get("start_date"))
        or coerce_dt(trial.get("primary_completion_date"))
        or coerce_dt(trial.get("completion_date"))
    )


class PhaseTransitionEmitter(FactEmitter):
    name = "phase_transitions"

    # One row per drug, with its trials aggregated into a json array. Aggregating
    # in SQL keeps ``row_to_facts`` pure (no per-drug fan-out queries) and lets the
    # development trajectory be derived from the whole trial set at once.
    _FETCH_SQL = """
        SELECT drug_id,
               json_agg(json_build_object(
                   'id', id,
                   'phase', phase,
                   'status', status,
                   'conditions', conditions,
                   'official_title', official_title,
                   'failure_reason', failure_reason,
                   'start_date', start_date,
                   'completion_date', completion_date,
                   'primary_completion_date', primary_completion_date,
                   'source_api', source_api,
                   'source_url', source_url
               )) AS trials
          FROM clinical_trials
         WHERE drug_id IS NOT NULL
         {drug_clause}
         GROUP BY drug_id
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
            logger.exception("phase_transitions fetch failed")
            return []

    def row_to_facts(self, row: dict) -> list[EmittedFact]:
        drug_id = row.get("drug_id")
        trials = row.get("trials") or []
        if not drug_id or not trials:
            return []
        drug_id = str(drug_id)
        facts: list[EmittedFact] = []

        # Earliest-starting representative trial per phase ordinal reached.
        phase_first: dict[int, tuple[Optional[object], dict]] = {}
        for t in trials:
            ordn = phase_ordinal(t.get("phase"))
            if ordn is None:
                continue
            start = _earliest_trial_dt(t)
            cur = phase_first.get(ordn)
            if cur is None:
                phase_first[ordn] = (start, t)
            else:
                cur_start, _ = cur
                if start is not None and (cur_start is None or start < cur_start):
                    phase_first[ordn] = (start, t)

        reached = sorted(phase_first)

        # ── phase_transition: each upward step between reached phases ──
        for i in range(1, len(reached)):
            prev, n = reached[i - 1], reached[i]
            start, t = phase_first[n]
            claim = f"Advanced from {PHASE_LABEL[prev]} to {PHASE_LABEL[n]}"
            facts.append(EmittedFact(
                predicate="phase_transition",
                subject_entity_type="drug",
                subject_entity_id=drug_id,
                object_value={
                    "description": claim,
                    "from_phase": prev,
                    "to_phase": n,
                    "representative_trial_id": str(t.get("id")) if t.get("id") else None,
                    "condition": _first(t.get("conditions")),
                    "source_url": t.get("source_url"),
                },
                source_row_id=f"{drug_id}:to_phase_{n}",
                kind="point",
                valid_from=start,
                confidence=0.8,
                fact_class="corporate",
                evidence_text=(t.get("official_title") or claim),
                source_id=t.get("source_api") or "clinical_trials_gov",
                source_url=t.get("source_url"),
            ))

        # ── approval_event: reached Phase 4 (post-marketing) → inferred ──
        if 4 in phase_first:
            start, t = phase_first[4]
            n4 = sum(1 for tt in trials if phase_ordinal(tt.get("phase")) == 4)
            claim = (
                f"Reached post-marketing studies (Phase 4) — "
                f"{n4} trial{'s' if n4 != 1 else ''}"
            )
            facts.append(EmittedFact(
                predicate="approval_event",
                subject_entity_type="drug",
                subject_entity_id=drug_id,
                object_value={
                    "description": claim,
                    "phase4_trials": n4,
                    "representative_trial_id": str(t.get("id")) if t.get("id") else None,
                    "condition": _first(t.get("conditions")),
                    "source_url": t.get("source_url"),
                },
                source_row_id=f"{drug_id}:approval",
                kind="point",
                valid_from=start,
                confidence=0.7,
                fact_class="inferred",
                evidence_text=(t.get("official_title") or claim),
                source_id=t.get("source_api") or "clinical_trials_gov",
                source_url=t.get("source_url"),
            ))

        # ── discontinuation: one per terminated / withdrawn / suspended trial ──
        for t in trials:
            status = (t.get("status") or "").strip()
            if status.lower() not in DISCONTINUED_STATUSES:
                continue
            tid = t.get("id")
            if not tid:
                continue
            reason = (t.get("failure_reason") or "").strip()
            ordn = phase_ordinal(t.get("phase"))
            phase_lbl = PHASE_LABEL.get(ordn)
            head = f"{phase_lbl} trial" if phase_lbl else "Trial"
            claim = f"{head} {status.title()}"
            if reason:
                claim = f"{claim} — {reason}"
            title = (t.get("official_title") or "").strip()
            evidence = title or claim
            if reason and reason not in evidence:
                evidence = f"{evidence} — {reason}"
            facts.append(EmittedFact(
                predicate="discontinuation",
                subject_entity_type="drug",
                subject_entity_id=drug_id,
                object_value={
                    "description": claim,
                    "trial_id": str(tid),
                    "status": status,
                    "phase": t.get("phase"),
                    "failure_reason": reason or None,
                    "condition": _first(t.get("conditions")),
                    "source_url": t.get("source_url"),
                },
                source_row_id=str(tid),
                kind="point",
                valid_from=(coerce_dt(t.get("completion_date"))
                            or coerce_dt(t.get("start_date"))),
                confidence=0.85,
                fact_class="corporate",
                evidence_text=evidence,
                source_id=t.get("source_api") or "clinical_trials_gov",
                source_url=t.get("source_url"),
            ))

        return facts
