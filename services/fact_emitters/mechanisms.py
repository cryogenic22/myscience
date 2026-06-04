"""DR-6 — mechanism / target fact emitters.

Lifts molecular intelligence we already hold (populated by the ChEMBL + MeSH
connectors) into the facts ledger so the dossier's ``clinical_profile`` domain
carries *how the drug works*, not just trial counts.

Two emitters:

* ``MechanismEmitter`` — the high-value path. Each active drug whose
  ``mechanism_id`` resolves to a ``mechanisms_of_action`` row (curated MeSH
  pharmacological class, e.g. "Glucagon-Like Peptide-1 Receptor Agonists")
  becomes one ``mechanism_of_action`` fact. 621 drugs covered on prod
  (2 Jun 2026). MeSH is curated ontology → ``reference``-class, high confidence.
* ``BioactivityEmitter`` — per-row ``target_activity`` facts from
  ``bioactivities`` (IC50/Ki/EC50/pCHEMBL). Gated on having *some* measurement
  (``pchembl_value`` or ``activity_value`` non-null). NOTE: currently DORMANT on
  prod — all 628 ``bioactivities`` rows have ``drug_id = NULL`` (the ChEMBL
  connector never linked them to the drug spine), so the JOIN to ``drugs``
  yields nothing. The emitter is correct and will activate once the connector
  populates ``bioactivities.drug_id`` (a connector-level fix, tracked
  separately). ``molecular_targets`` is also empty, so target *names* are absent
  until Open Targets ingest. ``reference``-class.

Both route to ``clinical_profile`` via ``route_predicate_to_domain``. Pure
``row_to_facts`` (DB-free, unit-testable); only ``fetch_rows`` touches the DB.
Idempotency follows the DR-0 contract: ``source_row_id`` = mechanism row id
(per drug) / bioactivity row id.
"""

from __future__ import annotations

import logging
from typing import Optional

from services.fact_emitters.base import (
    EmittedFact,
    FactEmitter,
)

logger = logging.getLogger(__name__)

# Active = not consolidated away. Matches resolve_asset_to_subject's filter so
# emitted facts land on the same canonical drug rows the dossier resolves to.
_INACTIVE_STATUSES = ("merged", "superseded")


def build_mechanism_claim(row: dict) -> str:
    """Compact human claim, e.g. 'Glucagon-Like Peptide-1 Receptor Agonists
    (appetite_suppressant)'. Rendered by the dossier as
    'Mechanism of action: <claim>'."""
    name = (row.get("mechanism_name") or "").strip()
    cls = (row.get("mechanism_class") or "").strip()
    if name and cls and cls.lower() not in name.lower():
        return f"{name} ({cls})"
    return name or cls or "Mechanism class"


class MechanismEmitter(FactEmitter):
    name = "mechanisms"

    _FETCH_SQL = """
        SELECT d.id AS drug_id,
               m.id AS mechanism_id,
               m.name AS mechanism_name,
               m.mechanism_class AS mechanism_class,
               m.mesh_id AS mesh_id,
               m.scope_note AS scope_note,
               m.source_url AS source_url,
               m.source_api AS source_api
          FROM drugs d
          JOIN mechanisms_of_action m ON m.id = d.mechanism_id
         WHERE d.mechanism_id IS NOT NULL
           AND COALESCE(d.record_status, '') NOT IN ('merged', 'superseded')
           {drug_clause}
         ORDER BY d.id
         {limit_clause}
    """

    def fetch_rows(self, db, *, drug_id: Optional[str] = None,
                   limit: Optional[int] = None) -> list[dict]:
        clauses = ""
        params: list = []
        if drug_id:
            clauses = "AND d.id = %s"
            params.append(str(drug_id))
        limit_sql = ""
        if limit is not None:
            limit_sql = "LIMIT %s"
            params.append(int(limit))
        sql = self._FETCH_SQL.format(drug_clause=clauses, limit_clause=limit_sql)
        try:
            return db.fetch_all(sql, params)
        except Exception:
            logger.exception("mechanisms fetch failed")
            return []

    def row_to_facts(self, row: dict) -> list[EmittedFact]:
        drug_id = row.get("drug_id")
        mech_id = row.get("mechanism_id")
        if not drug_id or not mech_id:
            return []
        claim = build_mechanism_claim(row)
        scope = (row.get("scope_note") or "").strip()
        object_value = {
            "description": claim,
            "mechanism": row.get("mechanism_name"),
            "mechanism_class": row.get("mechanism_class"),
            "mesh_id": row.get("mesh_id"),
            "source_url": row.get("source_url"),
        }
        return [
            EmittedFact(
                predicate="mechanism_of_action",
                subject_entity_type="drug",
                subject_entity_id=str(drug_id),
                object_value=object_value,
                source_row_id=str(mech_id),
                kind="point",
                confidence=0.9,            # curated MeSH ontology
                fact_class="reference",
                evidence_text=scope or claim,
                source_id=row.get("source_api") or "mesh_ontology",
                source_url=row.get("source_url"),
            )
        ]


def build_activity_claim(row: dict) -> str:
    """e.g. 'IC50 = 12.0 nM (pCHEMBL 7.9) vs GLP-1 receptor' — target name
    omitted when unknown. Rendered as 'Target activity: <claim>'."""
    atype = (row.get("activity_type") or "activity").strip()
    rel = (row.get("activity_relation") or "=").strip()
    val = row.get("activity_value")
    units = (row.get("activity_units") or "").strip()
    bits = []
    if val is not None:
        try:
            bits.append(f"{atype} {rel} {float(val):g} {units}".strip())
        except (TypeError, ValueError):
            bits.append(atype)
    else:
        bits.append(atype)
    pchembl = row.get("pchembl_value")
    if pchembl is not None:
        try:
            bits.append(f"pCHEMBL {float(pchembl):g}")
        except (TypeError, ValueError):
            pass
    head = " ".join(bits) if len(bits) == 1 else f"{bits[0]} ({bits[1]})"
    target = (row.get("target_name") or "").strip()
    if target:
        head = f"{head} vs {target}"
    return head


class BioactivityEmitter(FactEmitter):
    name = "bioactivities"

    _FETCH_SQL = """
        SELECT b.id AS activity_id,
               b.drug_id AS drug_id,
               b.activity_type, b.activity_value, b.activity_units,
               b.activity_relation, b.pchembl_value,
               b.assay_type, b.assay_description,
               b.source_url, b.source_api,
               t.name AS target_name, t.gene_symbol AS gene_symbol
          FROM bioactivities b
          JOIN drugs d ON d.id = b.drug_id
          LEFT JOIN molecular_targets t ON t.id = b.target_id
         WHERE b.drug_id IS NOT NULL
           AND (b.pchembl_value IS NOT NULL OR b.activity_value IS NOT NULL)
           AND COALESCE(d.record_status, '') NOT IN ('merged', 'superseded')
           {drug_clause}
         ORDER BY b.pchembl_value DESC NULLS LAST
         {limit_clause}
    """

    def fetch_rows(self, db, *, drug_id: Optional[str] = None,
                   limit: Optional[int] = None) -> list[dict]:
        clauses = ""
        params: list = []
        if drug_id:
            clauses = "AND b.drug_id = %s"
            params.append(str(drug_id))
        limit_sql = ""
        if limit is not None:
            limit_sql = "LIMIT %s"
            params.append(int(limit))
        sql = self._FETCH_SQL.format(drug_clause=clauses, limit_clause=limit_sql)
        try:
            return db.fetch_all(sql, params)
        except Exception:
            logger.exception("bioactivities fetch failed")
            return []

    def row_to_facts(self, row: dict) -> list[EmittedFact]:
        drug_id = row.get("drug_id")
        activity_id = row.get("activity_id")
        if not drug_id or not activity_id:
            return []
        claim = build_activity_claim(row)
        object_value = {
            "description": claim,
            "activity_type": row.get("activity_type"),
            "activity_value": row.get("activity_value"),
            "activity_units": row.get("activity_units"),
            "pchembl_value": row.get("pchembl_value"),
            "target": row.get("target_name"),
            "gene_symbol": row.get("gene_symbol"),
            "source_url": row.get("source_url"),
        }
        evidence = (row.get("assay_description") or "").strip() or claim
        return [
            EmittedFact(
                predicate="target_activity",
                subject_entity_type="drug",
                subject_entity_id=str(drug_id),
                object_value=object_value,
                source_row_id=str(activity_id),
                kind="point",
                confidence=0.8,            # curated ChEMBL measurement
                fact_class="reference",
                evidence_text=evidence,
                source_id=row.get("source_api") or "chembl",
                source_url=row.get("source_url"),
            )
        ]
