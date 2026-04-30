"""EMA CHMP meeting-highlights HTML parser.

SPEC-016 §7 swimlane A6.1 (Cycle 7).

Parses an EMA CHMP meeting-highlights HTML page into structured
ChmpOpinion records. The pages have a stable shape:

  <h2>Positive opinions on new medicines</h2>
  <table>
    <thead><tr><th>Name</th><th>INN</th><th>Applicant</th><th>Indication</th></tr></thead>
    <tbody>...</tbody>
  </table>

  <h2>Negative opinions on new medicines</h2>
  <table>...</table>

  <h2>Withdrawals of new applications</h2>
  <table>...</table>

  <h2>Recommendations on extensions of therapeutic indication</h2>
  <table>...</table>

Pure function — accepts HTML text, returns list[ChmpOpinion]. The
connector handles the HTTP fetching.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from services.extraction.ema_chmp_opinion import ChmpOpinion

logger = logging.getLogger(__name__)


# Map normalised section heading → opinion_type
_SECTION_PATTERNS = [
    (re.compile(r"positive\s+opinions?\s+on\s+new", re.I), "positive"),
    (re.compile(r"new\s+medicines?\s+recommended", re.I), "positive"),
    (re.compile(r"negative\s+opinions?\s+on\s+new", re.I), "negative"),
    (re.compile(r"withdrawals?\s+of\s+new", re.I), "withdrawn"),
    (re.compile(r"extensions?\s+of\s+therapeutic\s+indication", re.I),
     "extension"),
]


def _classify_heading(text: str) -> Optional[str]:
    for pattern, label in _SECTION_PATTERNS:
        if pattern.search(text):
            return label
    return None


def _column_index_for(headers: list[str], *names: str) -> Optional[int]:
    """Find the index of a header that matches any of `names`
    (case-insensitive, substring)."""
    for needle in names:
        for i, h in enumerate(headers):
            if needle.lower() in h.lower():
                return i
    return None


def _row_to_opinion(
    cells: list[str],
    *,
    name_idx: Optional[int],
    inn_idx: Optional[int],
    applicant_idx: Optional[int],
    indication_idx: Optional[int],
    opinion_type: str,
    opinion_date: date,
) -> Optional[ChmpOpinion]:
    """Build one ChmpOpinion from a parsed table row, or None if invalid."""
    def safe(idx: Optional[int]) -> str:
        if idx is None or idx >= len(cells):
            return ""
        return cells[idx].strip()

    inn = safe(inn_idx)
    name = safe(name_idx) or inn
    applicant = safe(applicant_idx)
    indication = safe(indication_idx)

    if not inn or not name or not applicant or not indication:
        return None
    try:
        return ChmpOpinion(
            inn=inn,
            brand_name=name,
            applicant=applicant,
            opinion_type=opinion_type,  # type: ignore[arg-type]
            opinion_date=opinion_date,
            indication=indication,
        )
    except Exception as exc:
        logger.debug("CHMP row failed validation: %s — cells=%s", exc, cells)
        return None


def _parse_table(
    table_el,
    *,
    opinion_type: str,
    opinion_date: date,
) -> list[ChmpOpinion]:
    headers: list[str] = []
    thead = table_el.find("thead")
    if thead:
        headers = [th.get_text(strip=True) for th in thead.find_all("th")]
    if not headers:
        # Fall back: first <tr>'s <th> cells
        first_tr = table_el.find("tr")
        if first_tr:
            headers = [th.get_text(strip=True) for th in first_tr.find_all("th")]

    if not headers:
        return []

    name_idx = _column_index_for(headers, "Name", "Brand")
    inn_idx = _column_index_for(headers, "INN", "Active substance")
    applicant_idx = _column_index_for(headers, "Applicant", "MAH", "Marketing authorisation holder")
    indication_idx = _column_index_for(headers, "Indication", "Therapeutic")

    if inn_idx is None or applicant_idx is None or indication_idx is None:
        return []

    body = table_el.find("tbody") or table_el
    out: list[ChmpOpinion] = []
    for row in body.find_all("tr"):
        cells = [td.get_text(strip=True) for td in row.find_all("td")]
        if not cells:
            continue
        op = _row_to_opinion(
            cells,
            name_idx=name_idx,
            inn_idx=inn_idx,
            applicant_idx=applicant_idx,
            indication_idx=indication_idx,
            opinion_type=opinion_type,
            opinion_date=opinion_date,
        )
        if op is not None:
            out.append(op)
    return out


def parse_highlights(html: str, *, opinion_date: date) -> list[ChmpOpinion]:
    """Parse a CHMP meeting-highlights page into ChmpOpinion records.

    Skips tables that are not under a recognised section heading.
    """
    soup = BeautifulSoup(html, "html.parser")

    opinions: list[ChmpOpinion] = []
    for heading in soup.find_all(["h2", "h3"]):
        opinion_type = _classify_heading(heading.get_text(strip=True))
        if opinion_type is None:
            continue
        # Find the next <table> that is a sibling of this heading
        next_el = heading.find_next("table")
        if next_el is None:
            continue
        opinions.extend(_parse_table(
            next_el,
            opinion_type=opinion_type,
            opinion_date=opinion_date,
        ))
    return opinions
