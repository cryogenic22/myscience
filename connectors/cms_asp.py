"""CMS ASP (Average Sales Price) connector.

SPEC-016 §7 swimlane Cycle 12.

CMS publishes the ASP file quarterly at
https://www.cms.gov/medicare/medicare-part-b-drug-average-sales-price/asp-pricing-files

Each row is one HCPCS code with its quarterly Part B payment limit.
The file is XLS / CSV; this connector handles the CSV variant. The
caller passes the URL of the desired quarter's file, plus the
explicit period_start / period_end (since the URL itself doesn't
encode them in a stable format).

Pure parser exposed as parse_asp_csv() — testable without HTTP.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date
from typing import Optional

import requests

from services.extraction.pricing_observation import PricingObservation

logger = logging.getLogger(__name__)


_DEFAULT_TIMEOUT = 60
_DEFAULT_USER_AGENT = "market-zero/1.0 (pulseaction.ai)"


def _parse_amount(raw: Optional[str]) -> Optional[float]:
    if raw is None:
        return None
    cleaned = raw.strip().replace("$", "").replace(",", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _norm(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    s = value.strip()
    return s if s else None


def _row_to_obs(
    row: dict[str, str],
    *,
    period_start: date,
    period_end: date,
) -> Optional[PricingObservation]:
    hcpcs = _norm(row.get("HCPCS Code"))
    description = _norm(row.get("Short Description"))
    dosage = _norm(row.get("HCPCS Code Dosage"))
    payment_amount = _parse_amount(row.get("Payment Limit"))

    if not (hcpcs and description and dosage):
        return None
    if payment_amount is None or payment_amount <= 0:
        return None

    try:
        return PricingObservation(
            hcpcs_code=hcpcs,
            short_description=description,
            dosage_unit=dosage,
            payment_limit_usd=payment_amount,
            payment_basis="asp",
            source_program="medicare_part_b",
            period_start=period_start,
            period_end=period_end,
            notes=_norm(row.get("Notes")),
        )
    except Exception as exc:
        logger.debug("ASP row failed validation: %s", exc)
        return None


# ────────────────────────────────────────────────────────────────────
# Pure parser
# ────────────────────────────────────────────────────────────────────


def parse_asp_csv(
    csv_text: str,
    *,
    period_start: date,
    period_end: date,
) -> list[PricingObservation]:
    """Parse a CMS ASP CSV file into PricingObservation records.

    period_start / period_end describe the quarter the file covers.
    """
    if not csv_text or not csv_text.strip():
        return []
    reader = csv.DictReader(io.StringIO(csv_text))
    out: list[PricingObservation] = []
    for row in reader:
        obs = _row_to_obs(row, period_start=period_start, period_end=period_end)
        if obs is not None:
            out.append(obs)
    return out


# ────────────────────────────────────────────────────────────────────
# Connector
# ────────────────────────────────────────────────────────────────────


class CmsAspConnector:
    """Tiny client for CMS ASP quarterly CSV files."""

    def __init__(
        self,
        *,
        timeout: int = _DEFAULT_TIMEOUT,
        user_agent: str = _DEFAULT_USER_AGENT,
    ):
        self._timeout = timeout
        self._headers = {
            "User-Agent": user_agent,
            "Accept": "text/csv,application/octet-stream",
        }

    def fetch_quarter(
        self,
        *,
        quarter_url: str,
        period_start: date,
        period_end: date,
    ) -> list[PricingObservation]:
        """Download + parse one quarterly file.

        Returns empty list on 404 / network error.
        """
        if not quarter_url:
            return []
        try:
            resp = requests.get(
                quarter_url, timeout=self._timeout, headers=self._headers,
            )
        except requests.RequestException as exc:
            logger.warning("CMS ASP fetch failed (%s): %s",
                           quarter_url, exc)
            return []
        if resp.status_code != 200:
            logger.info("CMS ASP %s returned %s",
                        quarter_url, resp.status_code)
            return []
        return parse_asp_csv(
            resp.text,
            period_start=period_start, period_end=period_end,
        )
