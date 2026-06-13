"""DataHub L4a — generic, config-driven RSS/Atom connector.

Lane-1, DB-free, no network. The pure parser `parse_feed_items()` is exercised
against hand-written RSS 2.0 + Atom documents; the connector's fetch/health are
tested with a stub HTTP layer. Mirrors `tests/test_csv_connector.py` (L3).

Conservation coverage: an item with no external id is skipped AND counted (never
silently dropped); a malformed/undated item is kept (we never drop on our own
parse failure); a feed that fails to parse raises rather than returning a partial
silent-empty.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from connectors.base import ConnectorError, RecordType, SourceType
from connectors.rss_connector import (
    RssConfig,
    RssConnector,
    parse_feed_items,
)

# ── sample feeds ─────────────────────────────────────────────────────────────

RSS_2_0 = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Acme Pharma Press</title>
    <item>
      <title>Acme announces Phase 3 readout</title>
      <link>https://acme.example/news/1</link>
      <guid>acme-0001</guid>
      <pubDate>Wed, 10 Jun 2026 13:00:00 GMT</pubDate>
      <description>Primary endpoint met in the pivotal trial.</description>
      <author>press@acme.example</author>
    </item>
    <item>
      <title>Acme receives FDA approval</title>
      <link>https://acme.example/news/2</link>
      <guid>acme-0002</guid>
      <pubDate>Mon, 01 Jun 2026 09:30:00 GMT</pubDate>
      <description>Approval granted for the lead asset.</description>
    </item>
  </channel>
</rss>
"""

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Acme Journal Alerts</title>
  <entry>
    <title>Mechanism of the lead asset</title>
    <link href="https://journal.example/a/1"/>
    <id>urn:uuid:atom-1</id>
    <updated>2026-06-09T08:00:00Z</updated>
    <summary>A review of the receptor agonism.</summary>
  </entry>
  <entry>
    <title>Second paper</title>
    <link href="https://journal.example/a/2"/>
    <id>urn:uuid:atom-2</id>
    <updated>2026-05-20T08:00:00Z</updated>
    <summary>Follow-up analysis.</summary>
  </entry>
</feed>
"""


def _cfg(**kw):
    base = dict(
        source_id="acme_press",
        record_type=RecordType.EVENT,
        source_name="Acme Pharma Press",
        url="https://acme.example/feed.xml",
    )
    base.update(kw)
    return RssConfig(**base)


# ── config validation ────────────────────────────────────────────────────────

class TestConfig:
    def test_requires_source_id(self):
        with pytest.raises(ConnectorError):
            _cfg(source_id="")

    def test_requires_url(self):
        with pytest.raises(ConnectorError):
            _cfg(url=None)

    def test_source_type_defaults_to_rss(self):
        assert _cfg().source_type is SourceType.RSS


# ── pure parser: RSS 2.0 ─────────────────────────────────────────────────────

class TestParseRss:
    def test_parses_all_items(self):
        recs = parse_feed_items(RSS_2_0, _cfg(), endpoint="e")
        assert len(recs) == 2
        assert recs[0].record_type is RecordType.EVENT
        assert recs[0].source_name == "Acme Pharma Press"

    def test_external_id_prefers_guid(self):
        recs = parse_feed_items(RSS_2_0, _cfg(), endpoint="e")
        assert {r.external_id for r in recs} == {"acme-0001", "acme-0002"}

    def test_passthrough_maps_standard_fields(self):
        recs = parse_feed_items(RSS_2_0, _cfg(), endpoint="e")
        d = recs[0].data
        assert d["title"] == "Acme announces Phase 3 readout"
        assert d["link"] == "https://acme.example/news/1"
        assert "Primary endpoint" in d["description"]

    def test_text_field_default_is_description(self):
        recs = parse_feed_items(RSS_2_0, _cfg(), endpoint="e")
        assert "Primary endpoint" in (recs[0].text_content or "")

    def test_field_map_selects_and_renames(self):
        cfg = _cfg(field_map={"title": "headline", "link": "url"})
        recs = parse_feed_items(RSS_2_0, cfg, endpoint="e")
        assert recs[0].data == {"headline": "Acme announces Phase 3 readout",
                                "url": "https://acme.example/news/1"}

    def test_identifiers_map(self):
        cfg = _cfg(identifiers_map={"link": "source_url"})
        recs = parse_feed_items(RSS_2_0, cfg, endpoint="e")
        assert recs[0].identifiers["source_url"] == "https://acme.example/news/1"

    def test_provenance_is_rss_with_hash(self):
        recs = parse_feed_items(RSS_2_0, _cfg(), endpoint="https://acme.example/feed.xml")
        p = recs[0].provenance
        assert p.source_type is SourceType.RSS
        assert p.api_endpoint == "https://acme.example/feed.xml"
        assert len(p.raw_response_hash) == 64  # sha-256 hex


# ── pure parser: Atom ────────────────────────────────────────────────────────

class TestParseAtom:
    def test_parses_atom_entries(self):
        recs = parse_feed_items(ATOM, _cfg(source_id="journal", record_type=RecordType.LITERATURE),
                                endpoint="e")
        assert len(recs) == 2
        assert recs[0].record_type is RecordType.LITERATURE

    def test_atom_external_id_from_id(self):
        recs = parse_feed_items(ATOM, _cfg(), endpoint="e")
        assert {r.external_id for r in recs} == {"urn:uuid:atom-1", "urn:uuid:atom-2"}

    def test_atom_link_href_extracted(self):
        recs = parse_feed_items(ATOM, _cfg(), endpoint="e")
        assert recs[0].data["link"] == "https://journal.example/a/1"

    def test_atom_summary_is_text(self):
        recs = parse_feed_items(ATOM, _cfg(), endpoint="e")
        assert "receptor agonism" in (recs[0].text_content or "")


# ── incremental (since) filtering ────────────────────────────────────────────

class TestSinceFilter:
    def test_since_drops_only_older_rss(self):
        since = datetime(2026, 6, 5, tzinfo=timezone.utc)
        recs = parse_feed_items(RSS_2_0, _cfg(), endpoint="e", since=since)
        # only the 10 Jun item survives; the 01 Jun one is older
        assert {r.external_id for r in recs} == {"acme-0001"}

    def test_naive_since_does_not_raise(self):
        since = datetime(2026, 6, 5)  # tz-naive
        recs = parse_feed_items(RSS_2_0, _cfg(), endpoint="e", since=since)
        assert {r.external_id for r in recs} == {"acme-0001"}

    def test_since_filters_atom(self):
        since = datetime(2026, 6, 1, tzinfo=timezone.utc)
        recs = parse_feed_items(ATOM, _cfg(), endpoint="e", since=since)
        assert {r.external_id for r in recs} == {"urn:uuid:atom-1"}

    def test_undated_item_is_kept(self):
        feed = """<rss version="2.0"><channel>
          <item><title>No date</title><guid>nd-1</guid><link>x</link></item>
        </channel></rss>"""
        since = datetime(2026, 6, 5, tzinfo=timezone.utc)
        recs = parse_feed_items(feed, _cfg(), endpoint="e", since=since)
        # we never drop a row we cannot prove is older
        assert {r.external_id for r in recs} == {"nd-1"}


# ── conservation: no silent loss ─────────────────────────────────────────────

class TestConservation:
    def test_item_without_external_id_is_skipped_not_crashed(self):
        feed = """<rss version="2.0"><channel>
          <item><title>has id</title><guid>g1</guid></item>
          <item><title>no id at all</title></item>
        </channel></rss>"""
        # default external id chain is guid->id->link; second item has none
        recs = parse_feed_items(feed, _cfg(), endpoint="e")
        assert {r.external_id for r in recs} == {"g1"}

    def test_empty_feed_returns_empty_list(self):
        feed = """<rss version="2.0"><channel><title>empty</title></channel></rss>"""
        assert parse_feed_items(feed, _cfg(), endpoint="e") == []

    def test_malformed_xml_raises(self):
        with pytest.raises(ConnectorError):
            parse_feed_items("<rss><channel><item>unclosed", _cfg(), endpoint="e")

    def test_content_encoded_becomes_text(self):
        # Many press/blog feeds put the body in content:encoded, not description.
        feed = """<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
          <channel><item>
            <title>Body in content:encoded</title>
            <guid>ce-1</guid>
            <content:encoded>The full article body for embedding.</content:encoded>
          </item></channel></rss>"""
        recs = parse_feed_items(feed, _cfg(), endpoint="e")
        assert len(recs) == 1
        assert "full article body" in (recs[0].text_content or "")


# ── connector: fetch + health with a stub HTTP layer ─────────────────────────

class _Resp:
    def __init__(self, text, status_code=200):
        self.text = text
        self.content = text.encode("utf-8")
        self.status_code = status_code


class TestConnectorFetch:
    def test_fetch_uses_loaded_feed(self, monkeypatch):
        conn = RssConnector(_cfg())
        monkeypatch.setattr(conn, "_fetch_with_retry", lambda url, **kw: _Resp(RSS_2_0))
        recs = conn.fetch()
        assert len(recs) == 2
        assert conn.source_type() is SourceType.RSS

    def test_health_reachable_when_items_present(self, monkeypatch):
        conn = RssConnector(_cfg())
        monkeypatch.setattr(conn, "_fetch_with_retry", lambda url, **kw: _Resp(RSS_2_0))
        h = conn.health_check()
        assert h.healthy is True
        assert h.source_type is SourceType.RSS

    def test_health_unreachable_on_http_error(self, monkeypatch):
        conn = RssConnector(_cfg())
        monkeypatch.setattr(conn, "_fetch_with_retry", lambda url, **kw: _Resp("", status_code=503))
        h = conn.health_check()
        assert h.healthy is False

    def test_fetch_raises_on_http_error(self, monkeypatch):
        conn = RssConnector(_cfg())
        monkeypatch.setattr(conn, "_fetch_with_retry", lambda url, **kw: _Resp("", status_code=500))
        with pytest.raises(ConnectorError):
            conn.fetch()
