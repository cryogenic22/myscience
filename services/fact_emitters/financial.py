"""DR-Financial — financial / commercial fact emitter.

The commercial domain in dossiers (and KBQ "Sales"/commercial) is empty: we
hold structured financials in ``company_financials`` (XBRL from SEC EDGAR —
revenue / R&D / profit / cash …) and corporate transactions in ``deals``
(M&A, licenses, collaborations), yet none of it ever becomes a domain fact.
This is plumbing, not sourcing: a thin layer mapping each row → one or more
``EmittedFact`` whose predicate ``route_predicate_to_domain()`` lands in the
right ZS dossier domain.

Two emitters:

* ``FinancialEmitter`` — one ``financial_metric`` fact per ``company_financials``
  row, subject = the reporting company. ``financial_metric`` routes to
  ``commercial_operational``. A reported XBRL number is structured corporate
  truth → ``corporate``-class. Idempotency key = the row id.
* ``DealEmitter`` — one ``deal_announced`` fact per *party* to a ``deals`` row
  (acquirer, target, licensor, licensee), so the deal shows up on every
  company's dossier. ``deal_announced`` routes to ``competitive`` (the "deal"
  prefix rule). ``corporate``-class. Idempotency key = ``<deal_id>:<role>:<cid>``
  so each side is a distinct, re-runnable fact.

Pure ``row_to_facts`` (DB-free, unit-testable); only ``fetch_rows`` touches the
DB. Mirrors clinical_trials.py / literature.py exactly.
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


# ── financial-metric helpers ────────────────────────────────────────

# Human labels for the canonical metric_name vocabulary (migration 027 +
# services/extraction/financial_disclosure.py). Unknown names are title-cased.
_METRIC_LABELS = {
    "revenue": "Revenue",
    "net_sales": "Net sales",
    "rd": "R&D expense",
    "rd_expense": "R&D expense",
    "sga": "SG&A expense",
    "profit": "Net income",
    "net_income": "Net income",
    "operating_income": "Operating income",
    "cost_of_sales": "Cost of sales",
    "gross_margin": "Gross margin",
    "margin": "Operating margin",
    "free_cash_flow": "Free cash flow",
    "cash": "Cash & equivalents",
    "total_assets": "Total assets",
    "eps": "EPS",
    "employees": "Employees",
}

# Metrics that are USD currency amounts (→ humanised with $ + magnitude) vs
# ratios / per-share / counts (rendered as a plain number).
_NON_CURRENCY_METRICS = {"eps", "employees", "margin", "gross_margin"}


def _metric_label(name: Optional[str]) -> str:
    key = (name or "").strip().lower()
    if key in _METRIC_LABELS:
        return _METRIC_LABELS[key]
    return key.replace("_", " ").title() if key else "Metric"


def _humanize_money(value: float, currency: str = "USD") -> str:
    """'$42.0B', '$310.0M', '$1.2K'. Full-dollar inputs (not millions)."""
    sym = "$" if (currency or "USD").upper() == "USD" else f"{currency} "
    av = abs(value)
    if av >= 1e9:
        return f"{sym}{value / 1e9:.1f}B"
    if av >= 1e6:
        return f"{sym}{value / 1e6:.1f}M"
    if av >= 1e3:
        return f"{sym}{value / 1e3:.1f}K"
    return f"{sym}{value:,.0f}"


def _period_label(row: dict) -> str:
    """'FY2025', 'Q1 2026'."""
    period = (row.get("fiscal_period") or "FY").strip()
    year = row.get("fiscal_year")
    if not year:
        return period
    if period.upper() == "FY":
        return f"FY{year}"
    return f"{period} {year}"


def build_financial_claim(row: dict) -> str:
    """Compact human claim, e.g. 'Revenue FY2025: $42.0B' or 'EPS Q1 2026:
    2.95'. Rendered by the dossier as the fact claim directly."""
    label = _metric_label(row.get("metric_name"))
    period = _period_label(row)
    value = row.get("metric_value")
    name_key = (row.get("metric_name") or "").strip().lower()
    if value is None:
        return f"{label} {period}".strip()
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{label} {period}".strip()
    if name_key in _NON_CURRENCY_METRICS:
        rendered = f"{v:,.2f}".rstrip("0").rstrip(".")
    else:
        rendered = _humanize_money(v, row.get("currency") or "USD")
    return f"{label} {period}: {rendered}"


class FinancialEmitter(FactEmitter):
    name = "financial"

    _FETCH_SQL = """
        SELECT cf.id, cf.company_id, cf.cik, cf.fiscal_year, cf.fiscal_period,
               cf.metric_name, cf.metric_value, cf.currency, cf.filed_date,
               cf.source_api,
               c.name AS company_name
          FROM company_financials cf
          JOIN companies c ON c.id = cf.company_id
         WHERE cf.company_id IS NOT NULL
           AND cf.metric_value IS NOT NULL
           AND COALESCE(c.record_status, '') NOT IN ('merged', 'superseded')
           {company_clause}
         ORDER BY cf.fiscal_year DESC, cf.fiscal_period
         {limit_clause}
    """

    def fetch_rows(self, db, *, drug_id: Optional[str] = None,
                   company_id: Optional[str] = None,
                   limit: Optional[int] = None) -> list[dict]:
        # ``drug_id`` is accepted for the shared run_emitter signature but is a
        # no-op here (financials are company-keyed). ``company_id`` scopes it.
        clauses = ""
        params: list = []
        if company_id:
            clauses = "AND cf.company_id = %s"
            params.append(str(company_id))
        limit_sql = ""
        if limit is not None:
            limit_sql = "LIMIT %s"
            params.append(int(limit))
        sql = self._FETCH_SQL.format(company_clause=clauses, limit_clause=limit_sql)
        try:
            return db.fetch_all(sql, params)
        except Exception:
            logger.exception("company_financials fetch failed")
            return []

    def row_to_facts(self, row: dict) -> list[EmittedFact]:
        company_id = row.get("company_id")
        row_id = row.get("id")
        value = row.get("metric_value")
        if not company_id or not row_id or value is None:
            return []
        claim = build_financial_claim(row)
        company = (row.get("company_name") or "").strip()
        object_value = {
            "description": claim,
            "metric_name": row.get("metric_name"),
            "metric_value": value,
            "currency": row.get("currency") or "USD",
            "fiscal_year": row.get("fiscal_year"),
            "fiscal_period": row.get("fiscal_period"),
            "company": company,
            "cik": row.get("cik"),
        }
        evidence = claim
        if company:
            evidence = f"{company} — {claim}"
        return [
            EmittedFact(
                predicate="financial_metric",
                subject_entity_type="company",
                subject_entity_id=str(company_id),
                object_value=object_value,
                source_row_id=str(row_id),
                kind="point",
                valid_from=coerce_dt(row.get("filed_date")),
                confidence=0.9,          # reported XBRL figure
                fact_class="corporate",
                evidence_text=evidence,
                source_id=row.get("source_api") or "sec_edgar",
                source_url=None,
            )
        ]


# ── deal helpers ────────────────────────────────────────────────────

def _deal_type_label(deal_types) -> str:
    if not deal_types:
        return "Deal"
    pretty = [str(t).replace("_", " ") for t in deal_types]
    return " / ".join(pretty)


def build_deal_claim(row: dict) -> str:
    """e.g. 'Acquisition: Pfizer → Arena Pharmaceuticals ($6.7B), announced
    2021-12-13'. Rendered by the dossier as the fact claim."""
    types = _deal_type_label(row.get("deal_types"))
    acquirer = (row.get("acquirer_name") or row.get("licensee_name") or "").strip()
    target = (row.get("target_name") or row.get("licensor_name") or "").strip()
    parties = ""
    if acquirer and target:
        parties = f"{acquirer} → {target}"
    elif acquirer or target:
        parties = acquirer or target
    head = f"{types.title()}"
    if parties:
        head = f"{head}: {parties}"
    value = row.get("total_potential_usd") or row.get("upfront_value_usd")
    if value is not None:
        try:
            head = f"{head} ({_humanize_money(float(value), row.get('currency') or 'USD')})"
        except (TypeError, ValueError):
            pass
    announced = row.get("announced_date")
    if announced:
        head = f"{head}, announced {announced}"
    return head


# (role, id-col, name-col) for each side of a deal.
_DEAL_PARTIES = (
    ("acquirer", "acquirer_id", "acquirer_name"),
    ("target", "target_id", "target_name"),
    ("licensor", "licensor_id", "licensor_name"),
    ("licensee", "licensee_id", "licensee_name"),
)


class DealEmitter(FactEmitter):
    name = "deals"

    _FETCH_SQL = """
        SELECT d.id, d.deal_types,
               d.acquirer_id, d.target_id, d.licensor_id, d.licensee_id,
               d.currency, d.upfront_value_usd, d.milestones_total_usd,
               d.total_potential_usd, d.announced_date, d.closing_date,
               d.status, d.press_release_url, d.filing_url, d.notes,
               ca.name AS acquirer_name, ct.name AS target_name,
               cl.name AS licensor_name, ce.name AS licensee_name
          FROM deals d
          LEFT JOIN companies ca ON ca.id = d.acquirer_id
          LEFT JOIN companies ct ON ct.id = d.target_id
          LEFT JOIN companies cl ON cl.id = d.licensor_id
          LEFT JOIN companies ce ON ce.id = d.licensee_id
         WHERE (d.acquirer_id IS NOT NULL OR d.target_id IS NOT NULL
                OR d.licensor_id IS NOT NULL OR d.licensee_id IS NOT NULL)
         ORDER BY d.announced_date DESC NULLS LAST
         {limit_clause}
    """

    def fetch_rows(self, db, *, drug_id: Optional[str] = None,
                   limit: Optional[int] = None) -> list[dict]:
        params: list = []
        limit_sql = ""
        if limit is not None:
            limit_sql = "LIMIT %s"
            params.append(int(limit))
        sql = self._FETCH_SQL.format(limit_clause=limit_sql)
        try:
            return db.fetch_all(sql, params)
        except Exception:
            logger.exception("deals fetch failed")
            return []

    def row_to_facts(self, row: dict) -> list[EmittedFact]:
        deal_id = row.get("id")
        if not deal_id:
            return []
        claim = build_deal_claim(row)
        url = row.get("press_release_url") or row.get("filing_url")
        evidence = (row.get("notes") or "").strip() or claim
        facts: list[EmittedFact] = []
        seen_companies: set[str] = set()
        for role, id_col, name_col in _DEAL_PARTIES:
            cid = row.get(id_col)
            if not cid:
                continue
            cid = str(cid)
            # A company can be on at most one side of a given deal; dedup keeps
            # the first role and a stable idempotency key.
            if cid in seen_companies:
                continue
            seen_companies.add(cid)
            object_value = {
                "description": claim,
                "deal_id": str(deal_id),
                "role": role,
                "counterparty": (row.get(name_col) or "").strip(),
                "deal_types": row.get("deal_types"),
                "upfront_value_usd": _as_float(row.get("upfront_value_usd")),
                "total_potential_usd": _as_float(row.get("total_potential_usd")),
                "currency": row.get("currency") or "USD",
                "status": row.get("status"),
                "source_url": url,
            }
            facts.append(
                EmittedFact(
                    predicate="deal_announced",
                    subject_entity_type="company",
                    subject_entity_id=cid,
                    object_value=object_value,
                    source_row_id=f"{deal_id}:{role}:{cid}",
                    kind="point",
                    valid_from=coerce_dt(row.get("announced_date")),
                    confidence=0.85,
                    fact_class="corporate",
                    evidence_text=evidence,
                    source_id="deals",
                    source_url=url,
                )
            )
        return facts


def _as_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
