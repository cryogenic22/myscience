"""DataHub L4b (generic connectors) — config-driven REST/JSON connector.

Lane-1, DB-free, no network. The pure parser is exercised against JSON payload
fixtures; the connector's auth/pagination paths use a stub that replaces
`_fetch_with_retry` (so no socket is opened). Asserts the universal
RawRecord/Provenance contract, the field/identifier mapping, dotted-path
extraction, the incremental `since` filter, the four auth modes, the three
pagination strategies, and the conservation rules (no-id rows skipped+counted,
non-dict items skipped+counted, unparseable `since` kept not dropped, a
non-JSON / failed response raises rather than returning a silent partial).

Borrows the auth-type + JSON-normalisation *concepts* from the owner's reSCApe
`services/hub/connectors/rest_api.py`/`veeva_vault.py`; re-authored in the
market_zero connector idiom (reuses `BaseConnector._fetch_with_retry`, emits
`RawRecord`/`Provenance`) rather than copied.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from connectors.base import ConnectorError, RecordType, SourceType
from connectors.rest_connector import (
    RestConfig,
    RestConnector,
    parse_rest_records,
)


# ── fixtures ──────────────────────────────────────────────────────────────────

_PAYLOAD = {
    "results": [
        {"id": "D1", "name": "semaglutide", "maker": "Novo Nordisk",
         "updated": "2026-06-10", "abstract": "GLP-1 agonist", "ndc": "0169-4060"},
        {"id": "D2", "name": "tirzepatide", "maker": "Eli Lilly",
         "updated": "2026-05-01", "abstract": "dual GIP/GLP-1"},
        {"name": "orphan-no-id", "maker": "Nobody", "updated": "2026-06-01"},
        {"id": "D3", "name": "finerenone", "maker": "Bayer",
         "updated": "not-a-date", "abstract": "MR antagonist"},
    ]
}


def _cfg(**kw):
    base = dict(
        source_id="acme_api",
        record_type=RecordType.DRUG,
        source_name="ACME Drug API",
        url="https://example.test/v1/drugs",
        external_id_field="id",
        records_path="results",
    )
    base.update(kw)
    return RestConfig(**base)


class _StubResp:
    """Minimal requests.Response stand-in."""

    def __init__(self, payload, status_code=200, *, raise_json=False):
        self._payload = payload
        self.status_code = status_code
        self._raise_json = raise_json
        self.text = "" if raise_json else json.dumps(payload)

    def json(self):
        if self._raise_json:
            raise ValueError("not json")
        return self._payload


def _stub_fetch(pages):
    """Return a fake `_fetch_with_retry` that yields `pages` in order, recording
    the (url, params) it was called with."""
    calls = []
    seq = list(pages)

    def _fetch(self, url, params=None, max_retries=3):
        calls.append((url, dict(params or {})))
        return seq[len(calls) - 1] if len(calls) <= len(seq) else seq[-1]

    _fetch.calls = calls
    return _fetch


# ── config validation ─────────────────────────────────────────────────────────

class TestConfig:
    def test_requires_source_id_url_external_id(self):
        with pytest.raises(ConnectorError):
            RestConfig(source_id="", record_type=RecordType.DRUG,
                       source_name="x", url="u", external_id_field="id")
        with pytest.raises(ConnectorError):
            RestConfig(source_id="s", record_type=RecordType.DRUG,
                       source_name="x", url="", external_id_field="id")
        with pytest.raises(ConnectorError):
            RestConfig(source_id="s", record_type=RecordType.DRUG,
                       source_name="x", url="u", external_id_field="")

    def test_rejects_unknown_auth_and_pagination(self):
        with pytest.raises(ConnectorError):
            _cfg(auth_type="oauth-magic")
        with pytest.raises(ConnectorError):
            _cfg(pagination="infinite-scroll")


# ── pure parser ─────────────────────────────────────────────────────────────--

class TestParse:
    def test_maps_records_with_provenance(self):
        recs = parse_rest_records(_PAYLOAD, _cfg(), endpoint="https://example.test/v1/drugs")
        assert [r.external_id for r in recs] == ["D1", "D2", "D3"]  # orphan skipped
        r = recs[0]
        assert r.record_type == RecordType.DRUG
        assert r.source_name == "ACME Drug API"
        assert r.data["name"] == "semaglutide"            # passthrough keys
        assert r.provenance.source_type == SourceType.REST
        assert r.provenance.api_endpoint == "https://example.test/v1/drugs"
        assert len(r.provenance.raw_response_hash) == 64   # sha-256 hex

    def test_field_map_and_identifiers_and_text(self):
        cfg = _cfg(
            field_map={"name": "generic_name", "maker": "company"},
            identifiers_map={"name": "generic_name", "ndc": "ndc"},
            text_field="abstract",
        )
        recs = parse_rest_records(_PAYLOAD, cfg, endpoint="e")
        r = recs[0]
        assert r.data == {"generic_name": "semaglutide", "company": "Novo Nordisk"}
        assert r.identifiers == {"generic_name": "semaglutide", "ndc": "0169-4060"}
        assert r.text_content == "GLP-1 agonist"
        # D2 has no ndc → identifier omitted, not blank
        assert "ndc" not in recs[1].identifiers

    def test_dotted_external_id_and_records_path(self):
        payload = {"data": {"items": [{"meta": {"key": "X1"}, "name": "a"}]}}
        cfg = _cfg(records_path="data.items", external_id_field="meta.key")
        recs = parse_rest_records(payload, cfg, endpoint="e")
        assert recs[0].external_id == "X1"

    def test_top_level_list_payload(self):
        cfg = _cfg(records_path=None)
        recs = parse_rest_records([{"id": "A"}, {"id": "B"}], cfg, endpoint="e")
        assert [r.external_id for r in recs] == ["A", "B"]

    def test_single_object_payload_is_wrapped(self):
        cfg = _cfg(records_path=None)
        recs = parse_rest_records({"id": "solo", "name": "x"}, cfg, endpoint="e")
        assert [r.external_id for r in recs] == ["solo"]

    def test_no_id_row_skipped_not_dropped_silently(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING):
            recs = parse_rest_records(_PAYLOAD, _cfg(), endpoint="e")
        assert all(r.external_id for r in recs)
        assert any("skipped" in m.lower() for m in caplog.messages)

    def test_non_dict_item_skipped_and_counted(self, caplog):
        import logging
        payload = {"results": [{"id": "ok"}, "i-am-a-string", 42]}
        with caplog.at_level(logging.WARNING):
            recs = parse_rest_records(payload, _cfg(), endpoint="e")
        assert [r.external_id for r in recs] == ["ok"]
        assert any("non-dict" in m.lower() or "malformed" in m.lower()
                   for m in caplog.messages)

    def test_records_path_missing_raises(self):
        with pytest.raises(ConnectorError):
            parse_rest_records({"oops": []}, _cfg(records_path="results"), endpoint="e")

    def test_since_filter_drops_only_provably_older(self):
        cfg = _cfg(since_field="updated", since_format="%Y-%m-%d")
        since = datetime(2026, 6, 1, tzinfo=timezone.utc)
        recs = parse_rest_records(_PAYLOAD, cfg, endpoint="e", since=since)
        ids = [r.external_id for r in recs]
        assert "D1" in ids          # 2026-06-10 ≥ since
        assert "D2" not in ids      # 2026-05-01 < since → dropped
        assert "D3" in ids          # unparseable date → KEPT (never drop on our parse failure)

    def test_since_iso8601_default_format(self):
        payload = {"results": [
            {"id": "new", "updated": "2026-06-10T08:00:00Z"},
            {"id": "old", "updated": "2026-01-01T08:00:00Z"},
        ]}
        cfg = _cfg(since_field="updated")  # since_format None ⇒ ISO-8601
        since = datetime(2026, 6, 1, tzinfo=timezone.utc)
        recs = parse_rest_records(payload, cfg, endpoint="e", since=since)
        assert [r.external_id for r in recs] == ["new"]


# ── auth ──────────────────────────────────────────────────────────────────────

class TestAuth:
    def test_bearer(self):
        c = RestConnector(_cfg(auth_type="bearer", auth_token="t0k"))
        headers, params = c._build_auth()
        assert headers["Authorization"] == "Bearer t0k"
        assert "token" not in params

    def test_basic(self):
        c = RestConnector(_cfg(auth_type="basic", auth_username="u", auth_password="p"))
        headers, _ = c._build_auth()
        assert headers["Authorization"].startswith("Basic ")

    def test_api_key_header(self):
        c = RestConnector(_cfg(auth_type="api_key", api_key="K", api_key_header="X-Api-Key"))
        headers, params = c._build_auth()
        assert headers["X-Api-Key"] == "K"
        assert "X-Api-Key" not in params

    def test_api_key_param(self):
        c = RestConnector(_cfg(auth_type="api_key", api_key="K", api_key_param="apikey"))
        headers, params = c._build_auth()
        assert params["apikey"] == "K"

    def test_api_key_requires_placement(self):
        with pytest.raises(ConnectorError):
            _cfg(auth_type="api_key", api_key="K")  # neither header nor param


# ── pagination (HTTP path, stubbed transport) ─────────────────────────────────

class TestPagination:
    def test_page_mode_accumulates_until_empty(self, monkeypatch):
        cfg = _cfg(pagination="page", page_param="page", page_size=2, max_pages=10)
        pages = [
            _StubResp({"results": [{"id": "A"}, {"id": "B"}]}),
            _StubResp({"results": [{"id": "C"}]}),
            _StubResp({"results": []}),   # empty ⇒ stop
        ]
        fetch = _stub_fetch(pages)
        monkeypatch.setattr(RestConnector, "_fetch_with_retry", fetch)
        recs = RestConnector(cfg).fetch()
        assert [r.external_id for r in recs] == ["A", "B", "C"]
        # page numbers advanced
        assert fetch.calls[0][1].get("page") == 1
        assert fetch.calls[1][1].get("page") == 2

    def test_offset_mode(self, monkeypatch):
        cfg = _cfg(pagination="offset", offset_param="offset", limit_param="limit",
                   page_size=2, max_pages=10)
        pages = [
            _StubResp({"results": [{"id": "A"}, {"id": "B"}]}),
            _StubResp({"results": []}),
        ]
        fetch = _stub_fetch(pages)
        monkeypatch.setattr(RestConnector, "_fetch_with_retry", fetch)
        recs = RestConnector(cfg).fetch()
        assert [r.external_id for r in recs] == ["A", "B"]
        assert fetch.calls[0][1].get("offset") == 0
        assert fetch.calls[1][1].get("offset") == 2

    def test_cursor_mode_follows_then_stops(self, monkeypatch):
        cfg = _cfg(pagination="cursor", cursor_param="cursor",
                   cursor_path="next_cursor", max_pages=10)
        pages = [
            _StubResp({"results": [{"id": "A"}], "next_cursor": "c2"}),
            _StubResp({"results": [{"id": "B"}], "next_cursor": None}),  # no cursor ⇒ stop
        ]
        fetch = _stub_fetch(pages)
        monkeypatch.setattr(RestConnector, "_fetch_with_retry", fetch)
        recs = RestConnector(cfg).fetch()
        assert [r.external_id for r in recs] == ["A", "B"]
        assert "cursor" not in fetch.calls[0][1]       # first call has no cursor
        assert fetch.calls[1][1].get("cursor") == "c2"  # second uses returned cursor

    def test_cursor_stuck_guard_stops_loud(self, monkeypatch, caplog):
        import logging
        cfg = _cfg(pagination="cursor", cursor_param="cursor",
                   cursor_path="next_cursor", max_pages=10)
        # API bug: returns the SAME non-empty cursor every page. Without the guard
        # this re-fetches + double-counts up to max_pages.
        pages = [
            _StubResp({"results": [{"id": "A"}], "next_cursor": "STUCK"}),
            _StubResp({"results": [{"id": "B"}], "next_cursor": "STUCK"}),
            _StubResp({"results": [{"id": "C"}], "next_cursor": "STUCK"}),
        ]
        fetch = _stub_fetch(pages)
        monkeypatch.setattr(RestConnector, "_fetch_with_retry", fetch)
        with caplog.at_level(logging.WARNING):
            recs = RestConnector(cfg).fetch()
        # page 1 (cursor None->STUCK), page 2 (cursor STUCK, sees STUCK again -> stop)
        assert [r.external_id for r in recs] == ["A", "B"]
        assert any("unchanged cursor" in m.lower() or "stuck" in m.lower()
                   for m in caplog.messages)

    def test_max_pages_cap_is_logged(self, monkeypatch, caplog):
        import logging
        cfg = _cfg(pagination="page", page_size=1, max_pages=2)
        # always-full page ⇒ would loop forever without the cap
        full = _StubResp({"results": [{"id": "Z"}]})
        monkeypatch.setattr(RestConnector, "_fetch_with_retry",
                            _stub_fetch([full, full, full, full]))
        with caplog.at_level(logging.WARNING):
            recs = RestConnector(cfg).fetch()
        assert len(recs) == 2  # exactly max_pages pages fetched
        assert any("max_pages" in m.lower() or "cap" in m.lower() for m in caplog.messages)

    def test_single_request_when_no_pagination(self, monkeypatch):
        fetch = _stub_fetch([_StubResp(_PAYLOAD)])
        monkeypatch.setattr(RestConnector, "_fetch_with_retry", fetch)
        recs = RestConnector(_cfg()).fetch()
        assert len(fetch.calls) == 1
        assert [r.external_id for r in recs] == ["D1", "D2", "D3"]


# ── failure modes (fail loud, never silent-empty) ─────────────────────────────

class TestFailures:
    def test_http_error_raises(self, monkeypatch):
        monkeypatch.setattr(RestConnector, "_fetch_with_retry",
                            _stub_fetch([_StubResp({}, status_code=500)]))
        with pytest.raises(ConnectorError):
            RestConnector(_cfg()).fetch()

    def test_non_json_raises(self, monkeypatch):
        monkeypatch.setattr(RestConnector, "_fetch_with_retry",
                            _stub_fetch([_StubResp(None, raise_json=True)]))
        with pytest.raises(ConnectorError):
            RestConnector(_cfg()).fetch()

    def test_none_response_raises(self, monkeypatch):
        monkeypatch.setattr(RestConnector, "_fetch_with_retry", _stub_fetch([None]))
        with pytest.raises(ConnectorError):
            RestConnector(_cfg()).fetch()


# ── source_type + health_check ────────────────────────────────────────────────

class TestConnectorMeta:
    def test_source_type(self):
        assert RestConnector(_cfg()).source_type() == SourceType.REST

    def test_health_check_ok(self, monkeypatch):
        monkeypatch.setattr(RestConnector, "_fetch_with_retry",
                            _stub_fetch([_StubResp(_PAYLOAD)]))
        hc = RestConnector(_cfg()).health_check()
        assert hc.healthy is True
        assert hc.source_type == SourceType.REST

    def test_health_check_reports_unreachable(self, monkeypatch):
        monkeypatch.setattr(RestConnector, "_fetch_with_retry",
                            _stub_fetch([_StubResp({}, status_code=503)]))
        hc = RestConnector(_cfg()).health_check()
        assert hc.healthy is False
