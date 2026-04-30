"""USPTO PatentsView connector.

SPEC-016 §7 swimlane A5.1 (Cycle 10).

PatentsView is the USPTO's free patent-search API. The newer v1
endpoint accepts a JSON POST with `q`, `f`, `o`, `s` fields.

Pure parser is exposed as parse_patentsview_response() so tests
can validate without HTTP. The connector wraps fetching with two
common search modes: by assignee organization name (most pharma
patents are owned by named entities) and by abstract text query
(useful for compound / mechanism searches).
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional

import requests

from services.extraction.patent import PatentRecord

logger = logging.getLogger(__name__)


_PATENTSVIEW_BASE = "https://search.patentsview.org/api/v1/patent"
_DEFAULT_TIMEOUT = 30
_DEFAULT_USER_AGENT = "market-zero/1.0 (pulseaction.ai)"


# Fields we want PatentsView to return. Stable across queries.
_DEFAULT_FIELDS = [
    "patent_number",
    "patent_title",
    "patent_abstract",
    "patent_date",
    "patent_num_claims",
    "assignees",
    "inventors",
    "cpcs",
    "application_number",
    "filing_date",
]


def _parse_iso_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None


def _flatten_inventors(inventors_raw: Any) -> list[str]:
    out: list[str] = []
    if not isinstance(inventors_raw, list):
        return out
    for inv in inventors_raw:
        if not isinstance(inv, dict):
            continue
        first = (inv.get("inventor_first_name") or "").strip()
        last = (inv.get("inventor_last_name") or "").strip()
        full = f"{first} {last}".strip()
        if full:
            out.append(full)
    return out


def _flatten_cpcs(cpcs_raw: Any) -> list[str]:
    out: list[str] = []
    if not isinstance(cpcs_raw, list):
        return out
    for cpc in cpcs_raw:
        if not isinstance(cpc, dict):
            continue
        gid = cpc.get("cpc_group_id")
        if gid:
            out.append(str(gid))
    return out


def _resolve_assignee(assignees_raw: Any) -> tuple[str, Optional[str]]:
    """Return (org_name, country) for the first listed assignee."""
    if not isinstance(assignees_raw, list) or not assignees_raw:
        return "", None
    first = assignees_raw[0]
    if not isinstance(first, dict):
        return "", None
    return (
        str(first.get("assignee_organization") or ""),
        first.get("assignee_country"),
    )


# ────────────────────────────────────────────────────────────────────
# Pure parser
# ────────────────────────────────────────────────────────────────────


def parse_patentsview_response(
    payload: dict[str, Any],
) -> list[PatentRecord]:
    if not isinstance(payload, dict):
        return []
    patents = payload.get("patents")
    if not isinstance(patents, list):
        return []

    out: list[PatentRecord] = []
    for raw in patents:
        if not isinstance(raw, dict):
            continue

        assignee_name, assignee_country = _resolve_assignee(
            raw.get("assignees"))
        title = (raw.get("patent_title") or "").strip()
        patent_number = (raw.get("patent_number") or "").strip()
        grant_date = _parse_iso_date(raw.get("patent_date"))

        if not (patent_number and title and assignee_name and grant_date):
            continue

        try:
            out.append(PatentRecord(
                patent_number=patent_number,
                title=title,
                assignee_name=assignee_name,
                grant_date=grant_date,
                abstract=raw.get("patent_abstract"),
                filing_date=_parse_iso_date(raw.get("filing_date")),
                application_number=raw.get("application_number"),
                inventors=_flatten_inventors(raw.get("inventors")),
                num_claims=raw.get("patent_num_claims"),
                cpc_groups=_flatten_cpcs(raw.get("cpcs")),
                assignee_country=assignee_country,
            ))
        except Exception as exc:
            logger.debug("PatentsView row failed validation: %s", exc)

    return out


# ────────────────────────────────────────────────────────────────────
# Connector
# ────────────────────────────────────────────────────────────────────


class PatentsViewConnector:
    """Tiny client around the PatentsView v1 API."""

    def __init__(
        self,
        *,
        base_url: str = _PATENTSVIEW_BASE,
        timeout: int = _DEFAULT_TIMEOUT,
        user_agent: str = _DEFAULT_USER_AGENT,
        api_key: Optional[str] = None,
    ):
        self._base_url = base_url
        self._timeout = timeout
        self._headers = {
            "User-Agent": user_agent,
            "Content-Type": "application/json",
        }
        if api_key:
            self._headers["X-Api-Key"] = api_key

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = requests.post(
                self._base_url, json=body,
                timeout=self._timeout, headers=self._headers,
            )
        except requests.RequestException as exc:
            logger.warning("PatentsView fetch failed: %s", exc)
            return {}
        if resp.status_code != 200:
            return {}
        try:
            return resp.json() or {}
        except ValueError:
            return {}

    def search_by_assignee(
        self,
        *,
        assignee_name: str,
        limit: int = 100,
    ) -> list[PatentRecord]:
        if not assignee_name:
            return []
        body = {
            "q": {"assignees.assignee_organization": assignee_name},
            "f": _DEFAULT_FIELDS,
            "o": {"size": limit},
            "s": [{"patent_date": "desc"}],
        }
        return parse_patentsview_response(self._post(body))

    def search_by_text(
        self,
        *,
        text_query: str,
        limit: int = 100,
    ) -> list[PatentRecord]:
        if not text_query:
            return []
        body = {
            "q": {
                "_or": [
                    {"_text_phrase": {"patent_title": text_query}},
                    {"_text_phrase": {"patent_abstract": text_query}},
                ],
            },
            "f": _DEFAULT_FIELDS,
            "o": {"size": limit},
            "s": [{"patent_date": "desc"}],
        }
        return parse_patentsview_response(self._post(body))
