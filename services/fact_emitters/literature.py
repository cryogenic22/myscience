"""DR-7 — literature fact emitter (PubMed → ledger).

Lifts ``pubmed_articles`` rows (4,315 on prod; 1,118 on active drugs across 68
drugs, 3 Jun 2026) into the facts ledger. Each drug-linked article becomes one
peer-reviewed (``reference``-class) fact:

* epidemiology-flavoured articles (MeSH terms mention prevalence / incidence /
  epidemiology) → ``disease_evidence`` → fills the thin ``disease_and_patient``
  domain.
* everything else → ``key_publication`` → ``clinical_profile`` (evidence about
  the focal asset).

High-value publication types (systematic review, RCT, phase III/IV) are
confidence-boosted so they rank above generic journal articles. Pure
``row_to_facts`` (DB-free); only ``fetch_rows`` touches the DB. Idempotency key
= the article's pmid (falls back to row id).
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

# MeSH-term substrings that mark an article as disease-epidemiology evidence.
_EPI_MARKERS = ("epidemiol", "prevalence", "incidence", "disease burden",
                "mortality", "morbidity")

# Publication types that carry more decision weight → confidence boost.
_HIGH_VALUE_TYPES = ("systematic review", "meta-analysis", "phase iii",
                     "phase iv", "randomized controlled trial",
                     "comparative study", "clinical trial")


def _is_epidemiology(mesh_terms) -> bool:
    if not mesh_terms:
        return False
    for mt in mesh_terms:
        low = str(mt).lower()
        if any(marker in low for marker in _EPI_MARKERS):
            return True
    return False


def _pub_year(row: dict) -> Optional[int]:
    dt = coerce_dt(row.get("publication_date"))
    return dt.year if dt else None


def build_publication_claim(row: dict) -> str:
    """e.g. 'Systematic Review, NEJM (2025): Semaglutide and cardiovascular
    outcomes'. Rendered by the dossier as 'Key publication: <claim>' /
    'Disease evidence: <claim>'."""
    bits = []
    ptype = (row.get("publication_type") or "").strip()
    if ptype and ptype.lower() != "journal article":
        bits.append(ptype)
    journal = (row.get("journal") or "").strip()
    year = _pub_year(row)
    head = ", ".join(bits)
    venue = journal
    if year:
        venue = f"{journal} ({year})" if journal else f"({year})"
    prefix = ", ".join([b for b in [head, venue] if b])
    title = (row.get("title") or "").strip().rstrip(".")
    if prefix and title:
        return f"{prefix}: {title}"
    return title or prefix or "Publication"


def _confidence(row: dict) -> float:
    base = clamp_confidence(row.get("quality_score"), default=0.7)
    ptype = (row.get("publication_type") or "").lower()
    if any(t in ptype for t in _HIGH_VALUE_TYPES):
        base = min(1.0, base + 0.15)
    return base


class LiteratureEmitter(FactEmitter):
    name = "literature"

    _FETCH_SQL = """
        SELECT p.id, p.pmid, p.drug_id, p.title, p.abstract, p.journal,
               p.publication_date, p.publication_type, p.mesh_terms,
               p.doi, p.source_url, p.source_api, p.quality_score
          FROM pubmed_articles p
          JOIN drugs d ON d.id = p.drug_id
         WHERE p.drug_id IS NOT NULL
           AND COALESCE(d.record_status, '') NOT IN ('merged', 'superseded')
           {drug_clause}
         ORDER BY p.publication_date DESC NULLS LAST
         {limit_clause}
    """

    def fetch_rows(self, db, *, drug_id: Optional[str] = None,
                   limit: Optional[int] = None) -> list[dict]:
        clauses = ""
        params: list = []
        if drug_id:
            clauses = "AND p.drug_id = %s"
            params.append(str(drug_id))
        limit_sql = ""
        if limit is not None:
            limit_sql = "LIMIT %s"
            params.append(int(limit))
        sql = self._FETCH_SQL.format(drug_clause=clauses, limit_clause=limit_sql)
        try:
            return db.fetch_all(sql, params)
        except Exception:
            logger.exception("literature fetch failed")
            return []

    def row_to_facts(self, row: dict) -> list[EmittedFact]:
        drug_id = row.get("drug_id")
        if not drug_id or not (row.get("title") or "").strip():
            return []
        epi = _is_epidemiology(row.get("mesh_terms"))
        predicate = "disease_evidence" if epi else "key_publication"
        claim = build_publication_claim(row)
        url = row.get("source_url")
        if not url and row.get("doi"):
            url = f"https://doi.org/{row['doi']}"
        object_value = {
            "description": claim,
            "pmid": row.get("pmid"),
            "journal": row.get("journal"),
            "year": _pub_year(row),
            "publication_type": row.get("publication_type"),
            "doi": row.get("doi"),
            "source_url": url,
        }
        abstract = (row.get("abstract") or "").strip()
        return [
            EmittedFact(
                predicate=predicate,
                subject_entity_type="drug",
                subject_entity_id=str(drug_id),
                object_value=object_value,
                source_row_id=str(row.get("pmid") or row.get("id")),
                kind="point",
                valid_from=coerce_dt(row.get("publication_date")),
                confidence=_confidence(row),
                fact_class="reference",          # peer-reviewed literature
                evidence_text=abstract or claim,
                source_id=row.get("source_api") or "pubmed",
                source_url=url,
            )
        ]
