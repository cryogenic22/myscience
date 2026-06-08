"""DR-2 — pricing fact emitter (NADAC / drug_pricing → facts ledger).

Lifts ``drug_pricing`` rows (CMS NADAC acquisition cost, per migration 022)
into the facts ledger as ``nadac_per_unit`` facts, which
``route_predicate_to_domain`` lands in the dossier's ``pricing_and_access``
domain — the one domain that was empty because no source ever populated
``drug_pricing``. One fact per pricing row; the subject is the row's
``drug_id``. A surveyed acquisition cost from CMS is ``corporate``-class
structured truth (a published figure), not peer-reviewed ``reference`` nor
synthesized ``inferred``.

Conservation (#2 — no silent loss): a ``drug_pricing`` row whose NADAC name
never resolved to the drug spine (``drug_id IS NULL``) is NOT dropped. The
emitter still produces a fact, but with an empty subject, so ``emit_one``
records it as ``skipped_no_subject`` (counted in EmitStats) instead of
discarding it. The row also remains in ``drug_pricing`` for later relinking.
"""

from __future__ import annotations

import logging
from typing import Optional

from services.fact_emitters.base import (
    EmittedFact,
    FactEmitter,
    coerce_dt,
)

logger = logging.getLogger(__name__)


def _fmt_price(value) -> Optional[str]:
    """Render a unit price without trailing-zero noise, or None if unusable."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    # Strip trailing zeros but keep at least the significant figures NADAC ships
    # (per-unit prices are often sub-cent, e.g. 0.02345).
    s = f"{f:.4f}".rstrip("0").rstrip(".")
    return s or "0"


def build_claim(row: dict) -> str:
    """Compact human claim, e.g. 'NADAC 89.1234 USD per unit (NDC 00169-4150-13)'.

    Rendered by the dossier as the pricing fact's description."""
    price = _fmt_price(row.get("unit_price"))
    currency = (row.get("currency") or "USD").strip() or "USD"
    unit = (row.get("unit") or "per unit").strip() or "per unit"
    price_type = (row.get("price_type") or "nadac").strip().upper() or "NADAC"
    head = f"{price_type} {price} {currency} {unit}"
    ndc = (row.get("ndc_code") or "").strip()
    if ndc:
        head = f"{head} (NDC {ndc})"
    return head


def _evidence_text(row: dict, claim: str) -> str:
    """Best human snippet to attest (DR-5). Prefer the drug name + claim."""
    name = (row.get("drug_name") or "").strip()
    return f"{name}: {claim}" if name else claim


class PricingEmitter(FactEmitter):
    name = "pricing"

    _FETCH_SQL = """
        SELECT id, drug_id, drug_name, ndc_code, price_type, unit_price, unit,
               currency, country, source_api, source_url, effective_date
          FROM drug_pricing
         WHERE unit_price IS NOT NULL
         {drug_clause}
         ORDER BY effective_date DESC NULLS LAST
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
            logger.exception("drug_pricing fetch failed")
            return []

    def row_to_facts(self, row: dict) -> list[EmittedFact]:
        price_id = row.get("id")
        if price_id is None:
            return []
        # No usable price → nothing to assert (mirrors the connector's skip).
        if _fmt_price(row.get("unit_price")) is None:
            return []

        claim = build_claim(row)
        # Conservation #2: keep unlinked rows — empty subject → counted as
        # skipped_no_subject by emit_one, never silently dropped.
        drug_id = row.get("drug_id")
        subject_id = str(drug_id) if drug_id else ""

        object_value = {
            "description": claim,
            "unit_price": row.get("unit_price"),
            "unit": row.get("unit"),
            "currency": row.get("currency") or "USD",
            "country": row.get("country") or "US",
            "price_type": row.get("price_type") or "nadac",
            "ndc_code": row.get("ndc_code"),
            "drug_name": row.get("drug_name"),
            "source_url": row.get("source_url"),
        }
        return [
            EmittedFact(
                predicate="nadac_per_unit",
                subject_entity_type="drug",
                subject_entity_id=subject_id,
                object_value=object_value,
                source_row_id=str(price_id),
                kind="point",
                valid_from=coerce_dt(row.get("effective_date")),
                confidence=0.85,
                fact_class="corporate",
                evidence_text=_evidence_text(row, claim),
                source_id=row.get("source_api") or "cms_nadac",
                source_url=row.get("source_url"),
            )
        ]
