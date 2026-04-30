"""FDA Drug Discontinuation connector.

SPEC-016 §7 swimlane A4.4 (Cycle 9).

Source: OpenFDA drugsfda.json — `products[].marketing_status` field.
Filters server-side via search query when possible, otherwise
filters client-side after fetch.

Pure parser exposed as parse_openfda_results() so tests can verify
without HTTP. The connector wraps fetching.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

import requests

from services.extraction.drug_discontinuation import (
    DrugDiscontinuation,
    MarketingStatus,
)

logger = logging.getLogger(__name__)


_OPENFDA_BASE = "https://api.fda.gov/drug/drugsfda.json"
_DEFAULT_TIMEOUT = 30
_DEFAULT_USER_AGENT = "market-zero/1.0 (pulseaction.ai)"


# ────────────────────────────────────────────────────────────────────
# Status mapping
# ────────────────────────────────────────────────────────────────────


_STATUS_MAP: dict[str, MarketingStatus] = {
    "DISCONTINUED": "discontinued",
    "WITHDRAWN FOR SALE": "withdrawn",
    "WITHDRAWN": "withdrawn",
}


def _normalise_status(raw: Optional[str]) -> Optional[MarketingStatus]:
    if not raw:
        return None
    return _STATUS_MAP.get(raw.strip().upper())


def _resolve_drug_name(record: dict[str, Any]) -> Optional[str]:
    openfda = record.get("openfda") or {}
    for key in ("generic_name", "brand_name", "substance_name"):
        val = openfda.get(key)
        if isinstance(val, list) and val:
            return str(val[0])
    return None


def _strength_from_product(product: dict[str, Any]) -> Optional[str]:
    active = product.get("active_ingredients") or []
    if active and isinstance(active[0], dict):
        s = active[0].get("strength")
        if s:
            return str(s)
    return None


# ────────────────────────────────────────────────────────────────────
# Pure parser
# ────────────────────────────────────────────────────────────────────


def parse_openfda_results(
    payload: dict[str, Any],
    *,
    observed_date: date,
) -> list[DrugDiscontinuation]:
    """Parse an OpenFDA drugsfda.json response into discontinuation
    records. Only products with marketing_status in {Discontinued,
    Withdrawn for Sale} are returned."""
    if not isinstance(payload, dict):
        return []
    results = payload.get("results")
    if not isinstance(results, list):
        return []

    out: list[DrugDiscontinuation] = []
    for record in results:
        if not isinstance(record, dict):
            continue
        drug_name = _resolve_drug_name(record)
        sponsor = record.get("sponsor_name")
        application_number = record.get("application_number")
        if not (drug_name and sponsor and application_number):
            continue
        for product in record.get("products") or []:
            if not isinstance(product, dict):
                continue
            status = _normalise_status(product.get("marketing_status"))
            if status is None:
                continue
            try:
                out.append(DrugDiscontinuation(
                    drug_name=str(drug_name),
                    sponsor_name=str(sponsor),
                    application_number=str(application_number),
                    product_number=str(product.get("product_number") or ""),
                    marketing_status=status,
                    observed_date=observed_date,
                    dosage_form=product.get("dosage_form"),
                    strength=_strength_from_product(product),
                    route=product.get("route"),
                ))
            except Exception as exc:
                logger.debug("Discontinuation row failed validation: %s", exc)
    return out


# ────────────────────────────────────────────────────────────────────
# Connector
# ────────────────────────────────────────────────────────────────────


class FdaDiscontinuationsConnector:
    """Tiny client around the OpenFDA drugsfda endpoint."""

    def __init__(
        self,
        *,
        base_url: str = _OPENFDA_BASE,
        timeout: int = _DEFAULT_TIMEOUT,
        user_agent: str = _DEFAULT_USER_AGENT,
        api_key: Optional[str] = None,
    ):
        self._base_url = base_url
        self._timeout = timeout
        self._headers = {"User-Agent": user_agent}
        self._api_key = api_key

    def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        if self._api_key:
            params["api_key"] = self._api_key
        try:
            resp = requests.get(
                self._base_url, params=params,
                timeout=self._timeout, headers=self._headers,
            )
        except requests.RequestException as exc:
            logger.warning("FDA discontinuations fetch failed: %s", exc)
            return {}
        if resp.status_code != 200:
            return {}
        try:
            return resp.json() or {}
        except ValueError:
            return {}

    def fetch_recent(
        self,
        *,
        observed_date: date,
        limit: int = 100,
    ) -> list[DrugDiscontinuation]:
        """Fetch products in Discontinued / Withdrawn marketing status.

        Server-side filter via search expression. Records returned
        reflect the OpenFDA snapshot at fetch time; observed_date is
        the date of fetch.
        """
        params: dict[str, Any] = {
            "search": (
                'products.marketing_status:"Discontinued" '
                'OR products.marketing_status:"Withdrawn for Sale"'
            ),
            "limit": limit,
        }
        payload = self._get(params)
        return parse_openfda_results(payload, observed_date=observed_date)

    def fetch_for_drug_name(
        self,
        *,
        drug_name: str,
        observed_date: date,
        limit: int = 100,
    ) -> list[DrugDiscontinuation]:
        if not drug_name:
            return []
        params: dict[str, Any] = {
            "search": (
                f'(openfda.generic_name:"{drug_name}" '
                f'+OR+ openfda.brand_name:"{drug_name}")'
            ),
            "limit": limit,
        }
        payload = self._get(params)
        return parse_openfda_results(payload, observed_date=observed_date)
