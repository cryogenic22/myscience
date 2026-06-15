"""DR-pricing — drug-pricing fact emitter.

`drug_pricing` rows land from the NADAC connector (290 rows on prod, source_api=
'cms_nadac') but never become facts — there is no emitter from drug_pricing, so
the pricing playbook's price routes are empty and the planner reports a pricing
gap (gap analysis 15-Jun, COORDINATION §7.5a / D-Q2). This emitter bridges that:
one representative price fact per linked drug.

NADAC = National Average Drug Acquisition Cost — the average price pharmacies pay
to *acquire* a drug (a Medicaid survey of actual transaction cost). It is NOT the
list price (WAC) and NOT the manufacturer net (post-rebate ASP). It is closest to
a net/acquisition price, so it is emitted as a ``net_price`` fact (which the
dossier pricing domain routes), with the precise basis carried transparently in
``object_value`` (``price_type='nadac'``, ``basis='medicaid_acquisition_cost'``)
so it can never be mistaken for list price. CMS is an authoritative public source
→ ``reference`` class.

Same framework + governance as the DR-1.. emitters: ``row_to_facts`` is pure and
DB-free; idempotency stamps the drug_pricing row id as ``source_row_id``.
"""

from __future__ import annotations

import logging
from typing import Optional

from services.fact_emitters.base import EmittedFact, FactEmitter, clamp_confidence, coerce_dt

logger = logging.getLogger(__name__)


def _fmt_price(value, unit: Optional[str]) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ""
    # NADAC unit prices are per-unit and often sub-dollar; show enough precision.
    price = f"${v:,.4f}".rstrip("0").rstrip(".") if v < 1 else f"${v:,.2f}"
    return f"{price} {unit}".strip() if unit else price


def build_claim(row: dict) -> str:
    price = _fmt_price(row.get("unit_price"), row.get("unit"))
    as_of = row.get("effective_date")
    head = f"NADAC acquisition cost {price}" if price else "NADAC acquisition cost"
    if as_of:
        head = f"{head} (as of {as_of})"
    return head


class DrugPricingEmitter(FactEmitter):
    name = "drug_pricing"

    # One representative (latest, highest) priced row per linked drug — drug_pricing
    # carries many NDC/strength rows per drug; DISTINCT ON collapses to one fact.
    _FETCH_SQL = """
        SELECT DISTINCT ON (drug_id)
               id, drug_id, drug_name, ndc_code, price_type, unit_price, unit,
               currency, source_api, source_url, effective_date
          FROM drug_pricing
         WHERE drug_id IS NOT NULL AND unit_price IS NOT NULL
         {drug_clause}
         ORDER BY drug_id, effective_date DESC NULLS LAST, unit_price DESC NULLS LAST
         {limit_clause}
    """

    def fetch_rows(self, db, *, drug_id: Optional[str] = None,
                   limit: Optional[int] = None) -> list[dict]:
        clauses, params = "", []
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
        drug_id = row.get("drug_id")
        price_id = row.get("id")
        unit_price = row.get("unit_price")
        if not drug_id or not price_id or unit_price is None:
            return []
        claim = build_claim(row)
        object_value = {
            "description": claim,
            "value": float(unit_price),
            "currency": (row.get("currency") or "USD"),
            "unit": row.get("unit"),
            # carry the exact basis so a net_price fact from NADAC is never read
            # as list price (WAC): NADAC = Medicaid acquisition cost.
            "price_type": row.get("price_type") or "nadac",
            "basis": "medicaid_acquisition_cost",
            "ndc_code": row.get("ndc_code"),
            "as_of": str(row.get("effective_date") or ""),
            "source_url": row.get("source_url"),
        }
        return [
            EmittedFact(
                predicate="net_price",
                subject_entity_type="drug",
                subject_entity_id=str(drug_id),
                object_value=object_value,
                source_row_id=str(price_id),
                kind="point",
                valid_from=coerce_dt(row.get("effective_date")),
                confidence=clamp_confidence(0.9, default=0.9),
                # CMS NADAC is an authoritative public source → reference-class.
                fact_class="reference",
                evidence_text=claim,
                source_id=row.get("source_api") or "cms_nadac",
                source_url=row.get("source_url"),
            )
        ]
