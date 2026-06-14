"""DataHub L4b (generic connectors) — config-driven REST / JSON connector.

The third generic connector after L3's `CsvConnector` (`connectors/csv_connector.py`)
and L4a's `RssConnector` (`connectors/rss_connector.py`): point a `RestConfig` at a
JSON HTTP endpoint, declare which key is the external id, which `RecordType` the
rows represent, and an optional field/identifier mapping — and it emits the
universal `RawRecord` with full `Provenance`, exactly like every bespoke
connector. Zero pipeline/schema change (the `BaseConnector` contract is the whole
integration seam). REST is the *most common* source kind, so this is the connector
that turns "onboard any JSON API" into a config rather than an engineering project.

It handles the three things a bespoke REST connector always re-implements:
  • **auth** — none / bearer / basic / api-key (header or query param);
  • **pagination** — page-number / offset-limit / opaque-cursor, with a hard
    `max_pages` cap so a misbehaving API cannot loop forever;
  • **shape** — a dotted `records_path` to dig the record list out of an envelope
    (`{"data": {"results": [...]}}`), dotted field extraction, and incremental
    `since` filtering.

This borrows the auth-type + JSON-normalisation *concepts* from the owner's reSCApe
`services/hub/connectors/rest_api.py` and `veeva_vault.py` (session-auth REST), but
is re-authored in the market_zero connector idiom — it reuses
`BaseConnector._fetch_with_retry` (retry/backoff) and emits `RawRecord`/`Provenance`
rather than reproducing any of that machinery.

Conservation: a record with no resolvable external id is **skipped and counted**
(never silently dropped); a non-dict list item is **skipped and counted**; a record
we cannot date is **kept** (we never drop on our own parse failure); a failed HTTP
response, a non-JSON body, a missing `records_path`, or a `max_pages` truncation are
all made **loud** (raise / log) rather than returned as a silent partial. The pure
parser `parse_rest_records()` is testable without HTTP.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from connectors.base import (
    BaseConnector,
    ConnectorError,
    HealthCheckResult,
    Provenance,
    RawRecord,
    RecordType,
    SourceType,
)

logger = logging.getLogger(__name__)

_DEFAULT_USER_AGENT = "market-zero/1.0 (pulseaction.ai)"
_DEFAULT_TIMEOUT = 60

_AUTH_TYPES = {"none", "bearer", "basic", "api_key"}
_PAGINATION_MODES = {"none", "page", "offset", "cursor"}


# ────────────────────────────────────────────────────────────────────
# Config (declarative — this is what makes an API a config, not code)
# ────────────────────────────────────────────────────────────────────

@dataclass
class RestConfig:
    source_id: str                       # string-keyed registry id (L2)
    record_type: RecordType              # what kind of entity the rows are
    source_name: str                     # human-readable display name
    url: str                             # endpoint URL (required)
    external_id_field: str               # record key (dotted) → external_id

    # shape
    records_path: Optional[str] = None   # dotted path to the list; None ⇒ body IS the list (or a single object)
    field_map: Optional[dict[str, str]] = None        # record key (dotted) → data key; None = passthrough top-level
    text_field: Optional[str] = None                  # record key (dotted) → text_content
    identifiers_map: Optional[dict[str, str]] = None  # record key (dotted) → identifiers key (resolver keys)
    since_field: Optional[str] = None                 # record key for incremental filtering
    since_format: Optional[str] = None                # strptime fmt; None ⇒ ISO-8601

    # request shaping
    query_params: Optional[dict[str, Any]] = None     # static params on every request
    headers: Optional[dict[str, str]] = None          # static extra headers
    since_param: Optional[str] = None                 # query param to pass `since` to the API
    since_param_format: str = "%Y-%m-%d"

    # auth
    auth_type: str = "none"              # none | bearer | basic | api_key
    auth_token: Optional[str] = None     # bearer
    auth_username: Optional[str] = None  # basic
    auth_password: Optional[str] = None  # basic
    api_key: Optional[str] = None
    api_key_header: Optional[str] = None  # send api_key as this header
    api_key_param: Optional[str] = None   # …or as this query param

    # pagination
    pagination: str = "none"             # none | page | offset | cursor
    page_param: str = "page"
    page_size_param: Optional[str] = None
    page_size: int = 100
    start_page: int = 1
    offset_param: str = "offset"
    limit_param: str = "limit"
    cursor_param: str = "cursor"         # query param carrying the cursor
    cursor_path: Optional[str] = None    # dotted path in the body → next cursor
    max_pages: int = 50

    source_type: SourceType = SourceType.REST

    def __post_init__(self):
        if not self.source_id or not self.source_id.strip():
            raise ConnectorError(self.source_type, "RestConfig.source_id is required")
        if not self.url or not self.url.strip():
            raise ConnectorError(self.source_type, "RestConfig.url is required")
        if not self.external_id_field:
            raise ConnectorError(self.source_type, "RestConfig.external_id_field is required")
        if self.auth_type not in _AUTH_TYPES:
            raise ConnectorError(
                self.source_type,
                f"RestConfig.auth_type {self.auth_type!r} must be one of {sorted(_AUTH_TYPES)}",
            )
        if self.pagination not in _PAGINATION_MODES:
            raise ConnectorError(
                self.source_type,
                f"RestConfig.pagination {self.pagination!r} must be one of {sorted(_PAGINATION_MODES)}",
            )
        if self.auth_type == "api_key" and not (self.api_key_header or self.api_key_param):
            raise ConnectorError(
                self.source_type,
                "RestConfig: api_key auth needs either api_key_header or api_key_param",
            )
        if self.pagination == "cursor" and not self.cursor_path:
            raise ConnectorError(
                self.source_type,
                "RestConfig: cursor pagination needs cursor_path (where the next cursor lives)",
            )


# ────────────────────────────────────────────────────────────────────
# Pure helpers (no HTTP — testable in isolation)
# ────────────────────────────────────────────────────────────────────

def _dig(obj: Any, dotted: Optional[str]) -> Any:
    """Navigate a nested mapping via a dotted path ("a.b.c"). Returns None if any
    hop is missing or a non-mapping. An empty/None path returns the object itself."""
    if not dotted:
        return obj
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _clean(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


def _parse_date(raw: Any, fmt: Optional[str]) -> Optional[datetime]:
    """Parse a record date. `fmt` is a strptime format; None ⇒ ISO-8601. Returns
    None (never raises) so an unparseable date keeps the row rather than dropping it."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    text = str(raw).strip()
    try:
        if fmt:
            dt = datetime.strptime(text, fmt)
        else:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _extract_list(payload: Any, config: RestConfig) -> list:
    """Dig the record list out of a JSON body per `config.records_path`.

    - `records_path` set, present, and a list ⇒ that list.
    - `records_path` set but missing ⇒ ConnectorError (loud: a shape mismatch is
      not the same as an empty result).
    - `records_path` None ⇒ the body itself if a list, else a single object wrapped.
    """
    if config.records_path:
        found = _dig(payload, config.records_path)
        if found is None:
            raise ConnectorError(
                config.source_type,
                f"records_path {config.records_path!r} not found in response "
                f"(top-level keys: {list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__})",
            )
        if not isinstance(found, list):
            raise ConnectorError(
                config.source_type,
                f"records_path {config.records_path!r} is {type(found).__name__}, expected a list",
            )
        return found
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return [payload]
    raise ConnectorError(
        config.source_type,
        f"response is {type(payload).__name__}; expected a list or object (set records_path)",
    )


def _records_from_list(
    items: list,
    config: RestConfig,
    *,
    endpoint: str,
    since: Optional[datetime],
    retrieved_at: datetime,
) -> list[RawRecord]:
    if since is not None and since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)

    records: list[RawRecord] = []
    skipped_no_id = 0
    skipped_non_dict = 0
    for item in items:
        if not isinstance(item, dict):
            skipped_non_dict += 1
            continue

        raw_id = _dig(item, config.external_id_field)
        external_id = str(raw_id).strip() if raw_id is not None else ""
        if not external_id:
            skipped_no_id += 1
            continue

        # Incremental filter — drop only a row we can BOTH parse AND prove is older.
        if since is not None and config.since_field:
            row_dt = _parse_date(_dig(item, config.since_field), config.since_format)
            if row_dt is not None and row_dt < since:
                continue

        # data payload
        if config.field_map is None:
            data = {k: _clean(v) for k, v in item.items()}
        else:
            data = {}
            for src_key, data_key in config.field_map.items():
                val = _dig(item, src_key)
                if val is not None:
                    data[data_key] = _clean(val)

        identifiers: dict[str, Any] = {}
        for src_key, id_key in (config.identifiers_map or {}).items():
            val = _dig(item, src_key)
            if val is not None and str(val).strip():
                identifiers[id_key] = str(val).strip()

        text_content = None
        if config.text_field:
            tc = _dig(item, config.text_field)
            text_content = tc.strip() if isinstance(tc, str) and tc.strip() else None

        prov = Provenance(
            source_type=config.source_type,
            api_endpoint=endpoint,
            query_params={},
            retrieved_at=retrieved_at,
            raw_response_hash=Provenance.hash_response(
                json.dumps(item, sort_keys=True, default=str).encode("utf-8")
            ),
        )
        records.append(RawRecord(
            record_type=config.record_type,
            external_id=external_id,
            source_name=config.source_name,
            provenance=prov,
            data=data,
            text_content=text_content,
            identifiers=identifiers,
        ))

    if skipped_no_id:
        logger.warning(
            "RestConnector(%s): skipped %d record(s) with empty %r — not dropped silently",
            config.source_id, skipped_no_id, config.external_id_field,
        )
    if skipped_non_dict:
        logger.warning(
            "RestConnector(%s): skipped %d non-dict / malformed list item(s) — not dropped silently",
            config.source_id, skipped_non_dict,
        )
    return records


def parse_rest_records(
    payload: Any,
    config: RestConfig,
    *,
    endpoint: str,
    since: Optional[datetime] = None,
    retrieved_at: Optional[datetime] = None,
) -> list[RawRecord]:
    """Map one JSON body → RawRecords per `config`. Pure: no network, no clock
    unless `retrieved_at` is omitted (then `now`)."""
    retrieved_at = retrieved_at or datetime.now(timezone.utc)
    items = _extract_list(payload, config)
    return _records_from_list(items, config, endpoint=endpoint, since=since, retrieved_at=retrieved_at)


# ────────────────────────────────────────────────────────────────────
# Connector
# ────────────────────────────────────────────────────────────────────

class RestConnector(BaseConnector):
    """Config-driven REST/JSON connector. Implements the three BaseConnector
    methods; everything source-specific lives in the `RestConfig`."""

    def __init__(self, config: RestConfig, *, timeout: int = _DEFAULT_TIMEOUT,
                 user_agent: Optional[str] = None):
        self.config = config
        self.timeout = timeout
        auth_headers, self._auth_params = self._build_auth()
        self.headers = {
            "User-Agent": user_agent or _DEFAULT_USER_AGENT,
            "Accept": "application/json",
            **(config.headers or {}),
            **auth_headers,
        }

    def source_type(self) -> SourceType:
        return self.config.source_type

    # ── auth ──────────────────────────────────────────────────────────────────
    def _build_auth(self) -> tuple[dict[str, str], dict[str, Any]]:
        """Return (headers, params) carrying the configured credentials. Pure —
        derives only from config, so it is safe to call repeatedly."""
        c = self.config
        headers: dict[str, str] = {}
        params: dict[str, Any] = {}
        if c.auth_type == "bearer":
            headers["Authorization"] = f"Bearer {c.auth_token or ''}"
        elif c.auth_type == "basic":
            raw = f"{c.auth_username or ''}:{c.auth_password or ''}".encode("utf-8")
            headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
        elif c.auth_type == "api_key":
            if c.api_key_header:
                headers[c.api_key_header] = c.api_key or ""
            elif c.api_key_param:
                params[c.api_key_param] = c.api_key or ""
        return headers, params

    # ── request building (pure-ish; clock only via `since` formatting) ─────────
    def _base_params(self, since: Optional[datetime]) -> dict[str, Any]:
        params: dict[str, Any] = {}
        params.update(self.config.query_params or {})
        params.update(self._auth_params)
        if self.config.since_param and since is not None:
            params[self.config.since_param] = since.strftime(self.config.since_param_format)
        return params

    def _read_json(self, resp) -> Any:
        if resp is None:
            raise ConnectorError(self.config.source_type, f"no response from {self.config.url}")
        if getattr(resp, "status_code", 0) >= 400:
            raise ConnectorError(
                self.config.source_type,
                f"REST fetch failed ({resp.status_code}): {self.config.url}",
            )
        try:
            return resp.json()
        except (ValueError, json.JSONDecodeError) as e:
            raise ConnectorError(self.config.source_type, f"non-JSON response from {self.config.url}: {e}")

    def fetch(self, since: Optional[datetime] = None) -> list[RawRecord]:
        cfg = self.config
        retrieved_at = datetime.now(timezone.utc)
        base_params = self._base_params(since)

        records: list[RawRecord] = []
        page = cfg.start_page
        offset = 0
        cursor: Optional[str] = None
        pages_fetched = 0
        truncated = False

        while True:
            params = dict(base_params)
            if cfg.pagination == "page":
                params[cfg.page_param] = page
                if cfg.page_size_param:
                    params[cfg.page_size_param] = cfg.page_size
            elif cfg.pagination == "offset":
                params[cfg.offset_param] = offset
                params[cfg.limit_param] = cfg.page_size
            elif cfg.pagination == "cursor" and cursor is not None:
                params[cfg.cursor_param] = cursor

            resp = self._fetch_with_retry(cfg.url, params=params)
            payload = self._read_json(resp)
            raw_list = _extract_list(payload, cfg)
            records.extend(_records_from_list(
                raw_list, cfg, endpoint=cfg.url, since=since, retrieved_at=retrieved_at,
            ))
            pages_fetched += 1

            if cfg.pagination == "none" or not raw_list:
                break
            if pages_fetched >= cfg.max_pages:
                truncated = True
                logger.warning(
                    "RestConnector(%s): hit max_pages cap (%d) — results may be truncated; "
                    "raise max_pages or narrow the query",
                    cfg.source_id, cfg.max_pages,
                )
                break

            if cfg.pagination == "page":
                page += 1
            elif cfg.pagination == "offset":
                offset += cfg.page_size
            elif cfg.pagination == "cursor":
                next_cursor = _dig(payload, cfg.cursor_path)
                if not next_cursor:
                    break
                # Stuck-cursor guard: a buggy API that keeps returning the SAME
                # cursor would otherwise re-fetch + double-count up to max_pages.
                # Stop loud rather than rely on the cap (reviewer hardening).
                if next_cursor == cursor:
                    truncated = True
                    logger.warning(
                        "RestConnector(%s): API returned an unchanged cursor %r — stopping "
                        "to avoid a stuck-cursor loop", cfg.source_id, next_cursor,
                    )
                    break
                cursor = next_cursor

        # Per-fetch observability — the operational lane should see a generic
        # connector's shape (pages, volume, truncation), not just a binary SUCCESS.
        logger.info(
            "RestConnector(%s): fetched %d page(s), emitted %d record(s)%s",
            cfg.source_id, pages_fetched, len(records),
            " [TRUNCATED]" if truncated else "",
        )
        return records

    def health_check(self) -> HealthCheckResult:
        started = datetime.now(timezone.utc)
        try:
            params = dict(self._base_params(None))
            if self.config.pagination == "page":
                params[self.config.page_param] = self.config.start_page
            elif self.config.pagination == "offset":
                params[self.config.offset_param] = 0
                params[self.config.limit_param] = self.config.page_size
            resp = self._fetch_with_retry(self.config.url, params=params)
            self._read_json(resp)  # raises on http error / non-JSON
            elapsed_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
            return HealthCheckResult(
                healthy=True,
                source_type=self.config.source_type,
                message="reachable",
                response_time_ms=elapsed_ms,
            )
        except Exception as e:  # noqa: BLE001 — health check reports, never raises
            elapsed_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
            return HealthCheckResult(
                healthy=False,
                source_type=self.config.source_type,
                message=f"unreachable: {e}",
                response_time_ms=elapsed_ms,
            )
