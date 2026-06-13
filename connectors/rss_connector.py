"""DataHub L4a (generic connectors) — config-driven RSS / Atom connector.

The second generic connector after L3's `CsvConnector` (`connectors/csv_connector.py`):
point an `RssConfig` at a feed URL, declare the `RecordType` the items represent
and an optional element→field map, and it emits the universal `RawRecord` with
full `Provenance` — zero pipeline/schema change (the `BaseConnector` contract is
the whole integration seam).

This is the GENERIC, any-feed→any-type connector, NOT a replacement for the
bespoke `connectors/news.py` (which hardcodes the FDA + Google-News feeds and
classifies them into EVENT records). Same relationship as `CsvConnector` vs a
bespoke CSV ingest. Built on stdlib `xml.etree.ElementTree` (no new dependency;
`feedparser` is not installed) and handles both RSS 2.0/1.0 (`<item>`) and Atom
(`<entry>`) by matching item local-names, normalising Atom's `summary`/`content`/
`id` onto the RSS-shaped `description`/`guid` so config + the rest of the pipeline
stay format-agnostic.

Conservation: an item with no resolvable external id is **skipped and counted**
(never silently dropped); an item we cannot date is **kept** (we never drop on our
own parse failure); a feed that will not parse **raises** `ConnectorError` rather
than returning a partial silent-empty. The pure parser `parse_feed_items()` is
testable without HTTP.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
from xml.etree import ElementTree

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
_DEFAULT_TIMEOUT = 30

# Default lookup chains (used when the config leaves a field unset). Atom keys are
# normalised onto these during extraction, so one chain covers both formats.
_EXTERNAL_ID_CHAIN = ("guid", "id", "link")
# `encoded` is RSS's `content:encoded` (the full-body convention used by many
# press/blog feeds) after namespace-stripping — include it so a feed whose body
# lives there still produces text_content for embedding.
_TEXT_CHAIN = ("description", "summary", "content", "encoded")
_DATE_CHAIN = ("pubDate", "updated", "published", "date")


# ────────────────────────────────────────────────────────────────────
# Config (declarative — this is what makes a feed a config, not code)
# ────────────────────────────────────────────────────────────────────

@dataclass
class RssConfig:
    source_id: str                       # string-keyed registry id (L2)
    record_type: RecordType              # what kind of entity the items are
    source_name: str                     # human-readable display name
    url: Optional[str] = None            # feed URL (required)
    external_id_field: Optional[str] = None   # item element → external_id; None ⇒ guid→id→link
    field_map: Optional[dict[str, str]] = None     # element → data key; None = passthrough all
    text_field: Optional[str] = None               # element → text_content; None ⇒ description→summary→content
    identifiers_map: Optional[dict[str, str]] = None  # element → identifiers key (resolver keys)
    since_field: Optional[str] = None              # date element for incremental; None ⇒ pubDate→updated→…
    source_type: SourceType = SourceType.RSS

    def __post_init__(self):
        if not self.source_id or not self.source_id.strip():
            raise ConnectorError(self.source_type, "RssConfig.source_id is required")
        if not self.url or not self.url.strip():
            raise ConnectorError(self.source_type, "RssConfig.url is required")


# ────────────────────────────────────────────────────────────────────
# Pure helpers (no HTTP — testable in isolation)
# ────────────────────────────────────────────────────────────────────

def _local(tag: str) -> str:
    """Strip an ElementTree `{namespace}local` tag down to its local name."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _parse_feed_date(raw: Optional[str]) -> Optional[datetime]:
    """Parse an RSS (RFC-822) or Atom (ISO-8601) date → tz-aware UTC, or None.

    Never raises — an undated/unparseable item must stay in the feed, not crash it.
    """
    if not raw or not raw.strip():
        return None
    s = raw.strip()
    # RFC-822 (RSS pubDate): "Wed, 10 Jun 2026 13:00:00 GMT"
    try:
        dt = parsedate_to_datetime(s)
        if dt is not None:
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        pass
    # ISO-8601 (Atom updated/published): "2026-06-09T08:00:00Z"
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _link_value(child) -> Optional[str]:
    """An RSS <link>text</link> carries the URL as text; an Atom <link href=…/>
    carries it on the attribute (prefer the alternate/no-rel link)."""
    href = child.get("href")
    if href:
        rel = child.get("rel")
        return href if rel in (None, "", "alternate") else None
    return (child.text or "").strip() or None


def _item_fields(item) -> dict[str, str]:
    """Flatten one <item>/<entry> into {local_name: value}, normalising Atom's
    `summary`/`content`/`id` onto the RSS-shaped `description`/`guid` so config
    stays format-agnostic. Empty values are dropped (not stored as '')."""
    fields: dict[str, str] = {}
    for child in item:
        name = _local(child.tag)
        if name == "link":
            val = _link_value(child)
            if val and "link" not in fields:
                fields["link"] = val
            continue
        text = (child.text or "").strip()
        if text:
            fields[name] = text
    # Atom/RSS body → RSS-shaped `description` alias (only when absent): Atom's
    # `summary`/`content` and RSS's `content:encoded` (→ local name `encoded`).
    if "description" not in fields:
        for alt in ("summary", "content", "encoded"):
            if fields.get(alt):
                fields["description"] = fields[alt]
                break
    if "guid" not in fields and fields.get("id"):
        fields["guid"] = fields["id"]
    return fields


def _resolve_external_id(fields: dict, config: RssConfig) -> str:
    if config.external_id_field:
        return (fields.get(config.external_id_field) or "").strip()
    for key in _EXTERNAL_ID_CHAIN:
        v = fields.get(key)
        if v and v.strip():
            return v.strip()
    return ""


def _resolve_text(fields: dict, config: RssConfig) -> Optional[str]:
    if config.text_field:
        v = fields.get(config.text_field)
        return v.strip() if isinstance(v, str) and v.strip() else None
    for key in _TEXT_CHAIN:
        v = fields.get(key)
        if v and v.strip():
            return v.strip()
    return None


def _resolve_date(fields: dict, config: RssConfig) -> Optional[datetime]:
    if config.since_field:
        return _parse_feed_date(fields.get(config.since_field))
    for key in _DATE_CHAIN:
        if fields.get(key):
            dt = _parse_feed_date(fields[key])
            if dt is not None:
                return dt
    return None


def _map_data(fields: dict, field_map: Optional[dict[str, str]]) -> dict:
    if field_map is None:
        return dict(fields)  # passthrough — keep every non-empty element
    out: dict = {}
    for src, key in field_map.items():
        if src in fields:
            out[key] = fields[src]
    return out


def parse_feed_items(
    text: str,
    config: RssConfig,
    *,
    endpoint: str,
    since: Optional[datetime] = None,
    retrieved_at: Optional[datetime] = None,
) -> list[RawRecord]:
    """Map an RSS/Atom document → RawRecords per `config`. Pure: no network, and
    no clock unless `retrieved_at` is omitted (then `now`)."""
    retrieved_at = retrieved_at or datetime.now(timezone.utc)
    if since is not None and since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)

    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as e:
        raise ConnectorError(config.source_type, f"unparseable feed: {e}") from e

    items = [el for el in root.iter() if _local(el.tag) in ("item", "entry")]

    records: list[RawRecord] = []
    skipped_no_id = 0
    for item in items:
        fields = _item_fields(item)
        external_id = _resolve_external_id(fields, config)
        if not external_id:
            skipped_no_id += 1
            continue

        # Incremental filter — only drop an item we can BOTH parse AND prove older.
        if since is not None:
            item_dt = _resolve_date(fields, config)
            if item_dt is not None and item_dt < since:
                continue

        data = _map_data(fields, config.field_map)
        identifiers = {}
        for src, id_key in (config.identifiers_map or {}).items():
            v = fields.get(src)
            if v and str(v).strip():
                identifiers[id_key] = str(v).strip()

        prov = Provenance(
            source_type=config.source_type,
            api_endpoint=endpoint,
            query_params={},
            retrieved_at=retrieved_at,
            raw_response_hash=Provenance.hash_response(
                repr(sorted(fields.items())).encode("utf-8")
            ),
        )
        records.append(RawRecord(
            record_type=config.record_type,
            external_id=external_id,
            source_name=config.source_name,
            provenance=prov,
            data=data,
            text_content=_resolve_text(fields, config),
            identifiers=identifiers,
        ))

    if skipped_no_id:
        logger.warning(
            "RssConnector(%s): skipped %d item(s) with no resolvable external id "
            "(%s) — not dropped silently",
            config.source_id, skipped_no_id,
            config.external_id_field or "/".join(_EXTERNAL_ID_CHAIN),
        )
    return records


# ────────────────────────────────────────────────────────────────────
# Connector
# ────────────────────────────────────────────────────────────────────

class RssConnector(BaseConnector):
    """Config-driven RSS/Atom connector. Implements the three BaseConnector
    methods; everything feed-specific lives in the `RssConfig`."""

    def __init__(self, config: RssConfig, *, timeout: int = _DEFAULT_TIMEOUT,
                 user_agent: Optional[str] = None):
        self.config = config
        self.timeout = timeout
        self.headers = {
            "User-Agent": user_agent or _DEFAULT_USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.5",
        }

    def source_type(self) -> SourceType:
        return self.config.source_type

    def _load_text(self) -> str:
        resp = self._fetch_with_retry(self.config.url)
        if resp is None or getattr(resp, "status_code", 500) >= 400:
            code = getattr(resp, "status_code", "no response")
            raise ConnectorError(self.config.source_type, f"feed fetch failed ({code}): {self.config.url}")
        return resp.text

    def fetch(self, since: Optional[datetime] = None) -> list[RawRecord]:
        text = self._load_text()
        return parse_feed_items(text, self.config, endpoint=self.config.url, since=since)

    def health_check(self) -> HealthCheckResult:
        started = datetime.now(timezone.utc)
        try:
            text = self._load_text()
            items = parse_feed_items(text, self.config, endpoint=self.config.url)
            elapsed_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
            return HealthCheckResult(
                healthy=bool(items),
                source_type=self.config.source_type,
                message=(f"reachable ({len(items)} items)" if items else "reachable but no items"),
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
