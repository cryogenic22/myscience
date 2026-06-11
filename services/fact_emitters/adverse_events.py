"""DR-3 — adverse-event (FAERS) fact emitter.

Lifts ``adverse_events`` rows into the facts ledger as ``adverse_event`` safety
facts routed to the ``clinical_profile`` domain. Individual FAERS case reports
are noise in a dossier (1,992 rows, mostly singletons), so we AGGREGATE per
(drug, reaction): one ``signal``-class fact per reaction with its report count
and how many were serious/fatal. Singletons are dropped (min_reports).

The framework is per-row, so ``fetch_rows`` returns the GROUP BY result and
``row_to_facts`` maps each aggregated reaction → one fact. Idempotency key is
synthetic: ``<drug_id>:<reaction>`` (an aggregate has no single source row).

FAERS hygiene (raw_notes.md / eval PV-01)
-----------------------------------------
FAERS preferred terms are *not all* adverse drug reactions. A large share are
MedDRA terms from the SOCs "Injury, poisoning and procedural complications"
(medication errors: wrong/extra/omitted dose, dispensing errors, off-label use,
overdose) and "General disorders" lack-of-efficacy terms ("Drug ineffective").
On prod these dominate the GLP-1 reaction counts ("Incorrect dose administered"
35x, "Drug ineffective" 49x). Lifting them raw makes the dossier imply a drug
carries serious *harms* when the report is really a use error. ``is_non_adr_term``
filters them out of the safety emitter; the underlying ``adverse_events`` rows
are untouched (full source conservation). Every surviving fact also carries an
explicit spontaneous-reporting caveat so synthesis cannot present a raw count as
a causal safety property.
"""

from __future__ import annotations

import logging
from typing import Optional

from services.fact_emitters.base import EmittedFact, FactEmitter, clamp_confidence

logger = logging.getLogger(__name__)

# MedDRA terms that are NOT adverse drug reactions. Substrings are matched
# case-insensitively against the preferred term; exact terms cover lack-of-
# efficacy / uninformative PTs that have no medication-error substring. Grounded
# in the terms actually present on prod (read-only FAERS probe, Jun 2026) plus
# the MedDRA SOC families they belong to — extend here, not at the call site.
_NON_ADR_SUBSTRINGS: tuple[str, ...] = (
    "dose administered",        # incorrect/extra/increased dose administered (+ by device)
    "dose omission",            # product/drug/intentional dose omission
    "dispensing error",         # product dispensing error (+ intercepted)
    "medication error",         # incl. "...capable of leading to medication error"
    "administration error",
    "preparation error",
    "off label",                # off label use
    "off-label",
    "unapproved indication",    # product use / drug ineffective in unapproved indication
    "product use issue",
    "product use in",
    "wrong technique",          # wrong technique in product usage process
    "wrong product",            # wrong product administered
    "wrong patient",            # wrong patient received product
    "wrong drug",
    "product dose",             # product dose omission ...
    "overdose",                 # accidental/intentional overdose (circumstance, not ADR)
    "underdose",
    "by device",                # incorrect dose administered / drug dose omission by device
    "expired product",
    "product storage",
    "circumstance or information",
    "product quality issue",
)

_NON_ADR_EXACT: frozenset[str] = frozenset({
    "drug ineffective",
    "illness",
    "therapeutic response decreased",
    "therapeutic response unexpected",
    "therapeutic product effect incomplete",
    "drug effect decreased",
    "no adverse event",
})

# Standing caveat stamped on every FAERS safety fact so downstream synthesis
# renders spontaneous-reporting limits instead of treating a count as causal.
REPORTING_CAVEAT = (
    "FAERS spontaneous report — no denominator; subject to reporting and "
    "notoriety bias; not evidence of causation."
)


def is_non_adr_term(term: str) -> bool:
    """True when ``term`` is a MedDRA medication-error / lack-of-efficacy PT
    rather than a genuine adverse drug reaction. Pure + case-insensitive."""
    t = (term or "").strip().lower()
    if not t:
        return False
    if t in _NON_ADR_EXACT:
        return True
    return any(sub in t for sub in _NON_ADR_SUBSTRINGS)


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
        # FAERS hygiene: medication-error / lack-of-efficacy PTs are not ADRs.
        # Drop them from the safety emitter (source rows are conserved).
        if is_non_adr_term(reaction):
            logger.debug("adverse_events: dropping non-ADR term %r", reaction)
            return []
        serious = int(row.get("serious_count") or 0)
        fatal = int(row.get("fatal_count") or 0)
        claim = build_claim(reaction, report_count, serious, fatal)
        drug_name = row.get("drug_name") or "the drug"
        evidence = (
            f"FAERS: {reaction} reported {report_count}x for {drug_name}; "
            f"{serious} serious, {fatal} fatal. {REPORTING_CAVEAT}"
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
                    "reporting_basis": "spontaneous",
                    "reporting_caveat": REPORTING_CAVEAT,
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
