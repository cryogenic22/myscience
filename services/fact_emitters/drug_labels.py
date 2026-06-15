"""DR-4 — drug-label (SPL) fact emitter.

Lifts ``drug_labels`` rows into the facts ledger. Each label yields up to two
facts, both routed to ``clinical_profile``:
  • a ``label_indication`` fact (the approved indication text), and
  • a ``safety_signal`` fact when the label carries a boxed warning.
Both are FDA-approved structured truth: the emitter declares the ``corporate``
default, but ``emit_one`` resolves it to ``reference`` by SOURCE (D-Q1 §8.2). A drug can have
several versioned/brand labels (Ozempic + Wegovy share a generic); each label
row emits its own fact, keyed by ``<label_id>:<field>`` for idempotency, so the
versions stay distinguishable.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from services.fact_emitters.base import EmittedFact, FactEmitter, coerce_dt

logger = logging.getLogger(__name__)

# SPL indications text is prefixed with section boilerplate, e.g.
# "1 INDICATIONS AND USAGE OZEMPIC is indicated: …". Strip it for a clean claim.
_INDICATION_PREFIX = re.compile(r"^\s*\d+(\.\d+)?\s*INDICATIONS\s+AND\s+USAGE\s*",
                                re.IGNORECASE)
_WS = re.compile(r"\s+")


def clean_indication(text: Optional[str]) -> str:
    if not text:
        return ""
    cleaned = _INDICATION_PREFIX.sub("", text)
    cleaned = cleaned.replace("�", " ")  # mojibake bullet noise in source
    return _WS.sub(" ", cleaned).strip()


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


class DrugLabelEmitter(FactEmitter):
    name = "drug_labels"

    _FETCH_SQL = """
        SELECT id, drug_id, drug_name, indications, boxed_warning,
               manufacturer, effective_date, source_api, source_url
          FROM drug_labels
         WHERE drug_id IS NOT NULL
         {drug_clause}
         ORDER BY effective_date DESC NULLS LAST
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
            logger.exception("drug_labels fetch failed")
            return []

    def row_to_facts(self, row: dict) -> list[EmittedFact]:
        drug_id = row.get("drug_id")
        label_id = row.get("id")
        if not drug_id or not label_id:
            return []
        facts: list[EmittedFact] = []
        valid_from = coerce_dt(row.get("effective_date"))
        source_id = row.get("source_api") or "fda_spl"
        source_url = row.get("source_url")

        indication = clean_indication(row.get("indications"))
        if indication:
            facts.append(
                EmittedFact(
                    predicate="label_indication",
                    subject_entity_type="drug",
                    subject_entity_id=str(drug_id),
                    object_value={
                        "description": _truncate(indication, 240),
                        "effective_date": str(row.get("effective_date") or ""),
                        "source_url": source_url,
                    },
                    source_row_id=f"{label_id}:indication",
                    kind="point",
                    valid_from=valid_from,
                    confidence=0.9,
                    fact_class="corporate",
                    evidence_text=_truncate(indication, 4000),
                    source_id=source_id,
                    source_url=source_url,
                )
            )

        boxed = (row.get("boxed_warning") or "").strip()
        if boxed:
            boxed = _WS.sub(" ", boxed.replace("�", " ")).strip()
            facts.append(
                EmittedFact(
                    predicate="safety_signal",
                    subject_entity_type="drug",
                    subject_entity_id=str(drug_id),
                    object_value={
                        "description": "Boxed warning: " + _truncate(boxed, 220),
                        "effective_date": str(row.get("effective_date") or ""),
                        "source_url": source_url,
                    },
                    source_row_id=f"{label_id}:boxed",
                    kind="point",
                    valid_from=valid_from,
                    confidence=0.95,
                    fact_class="corporate",
                    evidence_text=_truncate(boxed, 4000),
                    source_id=source_id,
                    source_url=source_url,
                )
            )
        return facts
