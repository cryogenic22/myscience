"""FDA Purple Book connector — biologics + biosimilars.

SPEC-016 §7 swimlane Cycle 11.

The Purple Book is the FDA's biologics analog of the Orange Book.
It's published as a downloadable CSV at:

  https://purplebooksearch.fda.gov/downloads

Each row covers one BLA-approved biologic, biosimilar, or
interchangeable. For biosimilars / interchangeables the row also
references the original branded biologic (Reference Product), which
is what makes biosimilar tracking possible — every new biosimilar
approval is a high-impact competitive threat to the reference brand.

Pure parser is exposed as parse_purple_book_csv(); the connector
wraps download + parse.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime
from typing import Optional

import requests

from services.extraction.biologic_product import (
    BiologicProduct,
    BlaType,
    LicenseStatus,
)

logger = logging.getLogger(__name__)


_DEFAULT_CSV_URL = (
    "https://purplebooksearch.fda.gov/files/2024Q1/purplebook-search-results.csv"
)
_DEFAULT_TIMEOUT = 60
_DEFAULT_USER_AGENT = "market-zero/1.0 (pulseaction.ai)"


_BLA_TYPE_MAP: dict[str, BlaType] = {
    "ORIGINAL": "original",
    "BIOSIMILAR": "biosimilar",
    "INTERCHANGEABLE": "interchangeable",
}

_LICENSE_STATUS_MAP: dict[str, LicenseStatus] = {
    "LICENSED": "licensed",
    "WITHDRAWN": "withdrawn",
    "PENDING": "pending",
}


def _parse_iso_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _norm(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _row_to_product(row: dict[str, str]) -> Optional[BiologicProduct]:
    bla_type = _BLA_TYPE_MAP.get(
        (row.get("BLA Type") or "").strip().upper())
    license_status = _LICENSE_STATUS_MAP.get(
        (row.get("License Status") or "").strip().upper())
    approval_date = _parse_iso_date(row.get("Approval Date"))

    if not (bla_type and license_status and approval_date):
        return None

    proprietary = _norm(row.get("Proprietary Name"))
    proper = _norm(row.get("Proper Name"))
    bla_no = _norm(row.get("BLA Number"))
    applicant = _norm(row.get("Application Holder"))

    if not (proprietary and proper and bla_no and applicant):
        return None

    try:
        return BiologicProduct(
            proprietary_name=proprietary,
            proper_name=proper,
            bla_number=bla_no,
            bla_type=bla_type,
            license_status=license_status,
            approval_date=approval_date,
            applicant=applicant,
            strength=_norm(row.get("Strength")),
            dosage_form=_norm(row.get("Dosage Form")),
            route_of_administration=_norm(row.get("Route of Administration")),
            product_presentation=_norm(row.get("Product Presentation")),
            ref_product_proprietary_name=_norm(
                row.get("Ref. Product Proprietary Name")),
            ref_product_proper_name=_norm(
                row.get("Ref. Product Proper Name")),
        )
    except Exception as exc:
        logger.debug("Purple Book row failed validation: %s", exc)
        return None


# ────────────────────────────────────────────────────────────────────
# Pure parser
# ────────────────────────────────────────────────────────────────────


def parse_purple_book_csv(csv_text: str) -> list[BiologicProduct]:
    """Parse a Purple Book CSV file into BiologicProduct records.

    Bad rows are dropped (logged at debug); a malformed row never
    sinks the batch.
    """
    if not csv_text or not csv_text.strip():
        return []
    reader = csv.DictReader(io.StringIO(csv_text))
    out: list[BiologicProduct] = []
    for row in reader:
        product = _row_to_product(row)
        if product is not None:
            out.append(product)
    return out


# ────────────────────────────────────────────────────────────────────
# Connector
# ────────────────────────────────────────────────────────────────────


class FdaPurpleBookConnector:
    """Tiny client for the FDA Purple Book CSV download."""

    def __init__(
        self,
        *,
        csv_url: str = _DEFAULT_CSV_URL,
        timeout: int = _DEFAULT_TIMEOUT,
        user_agent: str = _DEFAULT_USER_AGENT,
    ):
        self._csv_url = csv_url
        self._timeout = timeout
        self._headers = {
            "User-Agent": user_agent,
            "Accept": "text/csv,application/octet-stream",
        }

    def fetch_all(self) -> list[BiologicProduct]:
        """Download + parse the entire Purple Book CSV.

        Empty list on 404 / network error.
        """
        try:
            resp = requests.get(
                self._csv_url, timeout=self._timeout,
                headers=self._headers,
            )
        except requests.RequestException as exc:
            logger.warning("Purple Book fetch failed: %s", exc)
            return []
        if resp.status_code != 200:
            logger.info("Purple Book returned %s", resp.status_code)
            return []
        return parse_purple_book_csv(resp.text)

    def fetch_biosimilars_and_interchangeables(self) -> list[BiologicProduct]:
        """Convenience filter — only the threat-side rows."""
        return [
            r for r in self.fetch_all()
            if r.bla_type in {"biosimilar", "interchangeable"}
        ]
