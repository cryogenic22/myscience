"""DataHub L3 (docs/SPEC_DATA_HUB.md §4) — generic, config-driven CSV connector.

The first of the generic connectors that make "onboard any source" a product
rather than a per-source engineering project. A `CsvConnector` is configured (not
coded): point it at a CSV URL or file, declare which column is the external id,
which `RecordType` the rows represent, and an optional field/identifier mapping —
and it emits the universal `RawRecord` with full `Provenance`, exactly like every
bespoke connector. Zero changes to the pipeline/schema (the `BaseConnector`
contract is the whole integration seam).

Conservation: a row with no external id is skipped and **counted/logged** (never
silently dropped); a row whose `since` column is unparseable is **kept** (we never
drop on our own parse failure). The pure parser `parse_csv_records()` is testable
without HTTP.
"""

from __future__ import annotations

import csv
import io
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

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


# ────────────────────────────────────────────────────────────────────
# Config (declarative — this is what makes a source a config, not code)
# ────────────────────────────────────────────────────────────────────

@dataclass
class CsvConfig:
    source_id: str                       # string-keyed registry id (L2)
    record_type: RecordType              # what kind of entity the rows are
    external_id_field: str               # column → RawRecord.external_id
    source_name: str                     # human-readable display name
    url: Optional[str] = None            # one of url / path is required
    path: Optional[str] = None
    field_map: Optional[dict[str, str]] = None     # source col → data key; None = passthrough all
    text_field: Optional[str] = None               # column → text_content (for embedding)
    identifiers_map: Optional[dict[str, str]] = None  # source col → identifiers key (resolver keys)
    since_field: Optional[str] = None              # column used for incremental filtering
    since_format: str = "%Y-%m-%d"
    delimiter: str = ","
    source_type: SourceType = SourceType.CSV_FILE

    def __post_init__(self):
        if not self.source_id or not self.source_id.strip():
            raise ConnectorError(self.source_type, "CsvConfig.source_id is required")
        if not self.external_id_field:
            raise ConnectorError(self.source_type, "CsvConfig.external_id_field is required")
        if bool(self.url) == bool(self.path):
            raise ConnectorError(self.source_type, "CsvConfig: provide exactly one of url / path")


# ────────────────────────────────────────────────────────────────────
# Pure parser (no HTTP — testable in isolation)
# ────────────────────────────────────────────────────────────────────

def _parse_date(raw: Optional[str], fmt: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = datetime.strptime(raw.strip(), fmt)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except (ValueError, TypeError):
        return None


def _map_row(row: dict, field_map: Optional[dict[str, str]]) -> dict:
    if field_map is None:
        # Passthrough: keep every column, stripped.
        return {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k is not None}
    out: dict = {}
    for src_col, data_key in field_map.items():
        if src_col in row:
            v = row[src_col]
            out[data_key] = v.strip() if isinstance(v, str) else v
    return out


def parse_csv_records(
    text: str,
    config: CsvConfig,
    *,
    endpoint: str,
    since: Optional[datetime] = None,
    retrieved_at: Optional[datetime] = None,
) -> list[RawRecord]:
    """Map CSV text → RawRecords per `config`. Pure: no network, no clock unless
    `retrieved_at` is omitted (then `now`)."""
    retrieved_at = retrieved_at or datetime.now(timezone.utc)
    reader = csv.DictReader(io.StringIO(text), delimiter=config.delimiter)

    records: list[RawRecord] = []
    skipped_no_id = 0
    for row in reader:
        external_id = (row.get(config.external_id_field) or "").strip()
        if not external_id:
            skipped_no_id += 1
            continue

        # Incremental filter — only drop a row we can BOTH parse AND prove is older.
        if since is not None and config.since_field:
            row_dt = _parse_date(row.get(config.since_field), config.since_format)
            if row_dt is not None and row_dt < since:
                continue

        data = _map_row(row, config.field_map)
        identifiers = {}
        for src_col, id_key in (config.identifiers_map or {}).items():
            val = row.get(src_col)
            if val and str(val).strip():
                identifiers[id_key] = str(val).strip()
        text_content = None
        if config.text_field:
            tc = row.get(config.text_field)
            text_content = tc.strip() if isinstance(tc, str) and tc.strip() else None

        prov = Provenance(
            source_type=config.source_type,
            api_endpoint=endpoint,
            query_params={},
            retrieved_at=retrieved_at,
            raw_response_hash=Provenance.hash_response(
                repr(sorted(row.items())).encode("utf-8")
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
            "CsvConnector(%s): skipped %d row(s) with empty %r — not dropped silently",
            config.source_id, skipped_no_id, config.external_id_field,
        )
    return records


# ────────────────────────────────────────────────────────────────────
# Connector
# ────────────────────────────────────────────────────────────────────

class CsvConnector(BaseConnector):
    """Config-driven CSV connector. Implements the three BaseConnector methods;
    everything source-specific lives in the `CsvConfig`."""

    def __init__(self, config: CsvConfig, *, timeout: int = _DEFAULT_TIMEOUT,
                 user_agent: Optional[str] = None):
        self.config = config
        self.timeout = timeout
        self.headers = {"User-Agent": user_agent or _DEFAULT_USER_AGENT}

    def source_type(self) -> SourceType:
        return self.config.source_type

    def _load_text(self) -> tuple[str, str]:
        """Return (csv_text, endpoint). Reads a local path or fetches a URL."""
        if self.config.path:
            if not os.path.exists(self.config.path):
                raise ConnectorError(self.config.source_type, f"CSV path not found: {self.config.path}")
            with open(self.config.path, "r", encoding="utf-8", newline="") as f:
                return f.read(), self.config.path
        resp = self._fetch_with_retry(self.config.url)
        if resp is None or resp.status_code >= 400:
            code = getattr(resp, "status_code", "no response")
            raise ConnectorError(self.config.source_type, f"CSV fetch failed ({code}): {self.config.url}")
        return resp.text, self.config.url

    def fetch(self, since: Optional[datetime] = None) -> list[RawRecord]:
        text, endpoint = self._load_text()
        return parse_csv_records(text, self.config, endpoint=endpoint, since=since)

    def health_check(self) -> HealthCheckResult:
        started = datetime.now(timezone.utc)
        try:
            text, _ = self._load_text()
            has_header = bool(text.strip())
            elapsed_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
            return HealthCheckResult(
                healthy=has_header,
                source_type=self.config.source_type,
                message=("reachable" if has_header else "empty CSV"),
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
