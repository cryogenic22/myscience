"""DataHub L3 — generic config-driven CSV connector.

Lane-1, DB-free, no network. The pure parser is exercised against CSV text
fixtures; the connector's file path + health-check paths use a tmp file. Asserts
the universal RawRecord/Provenance contract, the field/identifier mapping, the
incremental `since` filter, and the conservation rules (no-id rows skipped+
counted, unparseable `since` kept not dropped).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from connectors.base import ConnectorError, RecordType, SourceType
from connectors.csv_connector import CsvConfig, CsvConnector, parse_csv_records

_CSV = (
    "id,name,company,updated,abstract\n"
    "D1,semaglutide,Novo Nordisk,2026-06-10,GLP-1 agonist\n"
    "D2,tirzepatide,Eli Lilly,2026-05-01,dual GIP/GLP-1\n"
    ",orphan-no-id,Nobody,2026-06-01,should be skipped\n"
    "D3,finerenone,Bayer,not-a-date,MR antagonist\n"
)


def _cfg(**kw):
    base = dict(
        source_id="acme_drugs",
        record_type=RecordType.DRUG,
        external_id_field="id",
        source_name="ACME Drug CSV",
        url="https://example.test/drugs.csv",
    )
    base.update(kw)
    return CsvConfig(**base)


# ── config validation ────────────────────────────────────────────────────────

class TestConfig:
    def test_requires_exactly_one_source(self):
        with pytest.raises(ConnectorError):
            CsvConfig(source_id="s", record_type=RecordType.DRUG,
                      external_id_field="id", source_name="x")  # neither url nor path
        with pytest.raises(ConnectorError):
            CsvConfig(source_id="s", record_type=RecordType.DRUG, external_id_field="id",
                      source_name="x", url="u", path="p")        # both

    def test_requires_external_id_field(self):
        with pytest.raises(ConnectorError):
            CsvConfig(source_id="s", record_type=RecordType.DRUG,
                      external_id_field="", source_name="x", url="u")


# ── pure parser ──────────────────────────────────────────────────────────────

class TestParse:
    def test_maps_rows_to_records_with_provenance(self):
        recs = parse_csv_records(_CSV, _cfg(), endpoint="https://example.test/drugs.csv")
        assert [r.external_id for r in recs] == ["D1", "D2", "D3"]  # orphan skipped
        r = recs[0]
        assert r.record_type == RecordType.DRUG
        assert r.source_name == "ACME Drug CSV"
        assert r.data["name"] == "semaglutide"            # passthrough columns
        assert r.provenance.source_type == SourceType.CSV_FILE
        assert r.provenance.api_endpoint == "https://example.test/drugs.csv"
        assert len(r.provenance.raw_response_hash) == 64   # sha-256 hex

    def test_no_id_row_is_skipped_not_dropped_silently(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING):
            recs = parse_csv_records(_CSV, _cfg(), endpoint="e")
        assert all(r.external_id for r in recs)
        assert "skipped 1 row" in caplog.text   # counted + logged

    def test_field_map_and_identifiers_and_text(self):
        cfg = _cfg(
            field_map={"name": "generic_name", "company": "sponsor"},
            identifiers_map={"name": "generic_name", "company": "company_name"},
            text_field="abstract",
        )
        recs = parse_csv_records(_CSV, cfg, endpoint="e")
        r = recs[0]
        assert r.data == {"generic_name": "semaglutide", "sponsor": "Novo Nordisk"}
        assert r.identifiers == {"generic_name": "semaglutide", "company_name": "Novo Nordisk"}
        assert r.text_content == "GLP-1 agonist"

    def test_since_filters_older_but_keeps_unparseable(self):
        since = datetime(2026, 6, 1, tzinfo=timezone.utc)
        recs = parse_csv_records(_CSV, _cfg(since_field="updated"),
                                 endpoint="e", since=since)
        ids = [r.external_id for r in recs]
        assert "D1" in ids       # 2026-06-10 >= since → kept
        assert "D2" not in ids   # 2026-05-01 < since → dropped
        assert "D3" in ids       # 'not-a-date' unparseable → KEPT (no silent drop)

    def test_retrieved_at_is_injectable(self):
        ts = datetime(2026, 6, 13, tzinfo=timezone.utc)
        recs = parse_csv_records(_CSV, _cfg(), endpoint="e", retrieved_at=ts)
        assert recs[0].provenance.retrieved_at == ts


# ── connector (file path + health check, no network) ─────────────────────────

class TestConnectorFile:
    def _write(self, tmp_path):
        p = tmp_path / "drugs.csv"
        p.write_text(_CSV, encoding="utf-8")
        return str(p)

    def test_fetch_from_path(self, tmp_path):
        conn = CsvConnector(_cfg(url=None, path=self._write(tmp_path)))
        recs = conn.fetch()
        assert [r.external_id for r in recs] == ["D1", "D2", "D3"]
        assert recs[0].provenance.api_endpoint == self._write(tmp_path)

    def test_source_type(self, tmp_path):
        conn = CsvConnector(_cfg(url=None, path=self._write(tmp_path)))
        assert conn.source_type() == SourceType.CSV_FILE

    def test_health_check_healthy(self, tmp_path):
        conn = CsvConnector(_cfg(url=None, path=self._write(tmp_path)))
        hc = conn.health_check()
        assert hc.healthy is True and hc.source_type == SourceType.CSV_FILE

    def test_health_check_missing_path(self):
        conn = CsvConnector(_cfg(url=None, path="/no/such/file.csv"))
        hc = conn.health_check()
        assert hc.healthy is False and "unreachable" in hc.message
