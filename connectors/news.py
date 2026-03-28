"""Pharma news and press release connector.

Fetches real-time competitive signals from pharma news sources:
- FDA press announcements (approvals, CRLs, safety alerts)
- BioSpace / FiercePharma style aggregation via Google News RSS

Per lead assessment: "Your market_events table is currently limited to
FDA shortages. The competitive landscape changes on news — an FDA
approval, a Phase 3 readout, an M&A announcement."
"""

from __future__ import annotations

import logging
import re
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional
from xml.etree import ElementTree

from connectors.base import (
    BaseConnector,
    HealthCheckResult,
    RawRecord,
    Provenance,
    RecordType,
    SourceType,
)

logger = logging.getLogger(__name__)

# FDA press announcements (public RSS)
FDA_PRESS_RSS = "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-releases/rss.xml"

# Google News RSS for pharma-specific queries (no API key needed)
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"

# Pharma news queries
NEWS_QUERIES = [
    "FDA drug approval",
    "pharmaceutical acquisition merger",
    "clinical trial phase 3 results",
    "FDA complete response letter",
    "drug shortage pharmaceutical",
    "EMA approval CHMP",
]


class PharmaNewsConnector(BaseConnector):
    """Connector for pharma news and regulatory press releases.

    Uses public RSS feeds — no API keys required.
    """

    def __init__(self, config=None, target_overrides: dict | None = None):
        self._config = config
        self._queries = (target_overrides or {}).get("queries", NEWS_QUERIES)
        self._max_per_query = (target_overrides or {}).get("max_per_query", 20)

    @property
    def source_type(self) -> SourceType:
        return SourceType.NEWS

    def health_check(self) -> HealthCheckResult:
        import requests
        try:
            resp = requests.get(FDA_PRESS_RSS, timeout=10)
            return HealthCheckResult(
                source_type=self.source_type,
                available=resp.status_code == 200,
                latency_ms=0,
                message=f"FDA RSS: HTTP {resp.status_code}",
            )
        except Exception as e:
            return HealthCheckResult(
                source_type=self.source_type,
                available=False,
                latency_ms=0,
                message=str(e),
            )

    def fetch(self, since: Optional[datetime] = None) -> list[RawRecord]:
        """Fetch pharma news from RSS feeds."""
        records: list[RawRecord] = []

        # 1. FDA press releases
        try:
            fda_records = self._fetch_fda_press(since)
            records.extend(fda_records)
            logger.info("FDA press releases: %d records", len(fda_records))
        except Exception as e:
            logger.warning("FDA press RSS failed: %s", e)

        # 2. Google News pharma queries
        for query in self._queries:
            try:
                news = self._fetch_google_news(query, since)
                records.extend(news)
            except Exception as e:
                logger.debug("Google News query '%s' failed: %s", query, e)

        logger.info("News connector fetched %d total records", len(records))
        return records

    def _fetch_fda_press(self, since: Optional[datetime]) -> list[RawRecord]:
        """Parse FDA press release RSS feed."""
        records = []
        try:
            resp = self._fetch_with_retry(FDA_PRESS_RSS)
            if resp.status_code != 200:
                return records

            root = ElementTree.fromstring(resp.content)
            items = root.findall(".//item")

            for item in items[:50]:
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                pub_date = item.findtext("pubDate", "")
                description = item.findtext("description", "")

                # Parse date
                event_date = self._parse_rss_date(pub_date)
                if since and event_date and event_date < since:
                    continue

                # Classify event type
                event_type = self._classify_event(title, description)

                record = RawRecord(
                    record_type=RecordType.EVENT,
                    external_id=hashlib.md5(link.encode()).hexdigest()[:16],
                    source_name="FDA Press Releases",
                    provenance=Provenance(
                        source_type=self.source_type,
                        api_endpoint=FDA_PRESS_RSS,
                        query_params={},
                        retrieved_at=datetime.now(timezone.utc),
                        raw_response_hash=hashlib.sha256(title.encode()).hexdigest(),
                    ),
                    data={
                        "description": title,
                        "event_type": event_type,
                        "event_date": event_date.isoformat() if event_date else pub_date,
                        "source_url": link,
                        "detail": description[:500] if description else "",
                        "source_feed": "fda_press",
                    },
                    identifiers={},
                )
                records.append(record)
        except Exception as e:
            logger.warning("FDA RSS parse error: %s", e)

        return records

    def _fetch_google_news(self, query: str, since: Optional[datetime]) -> list[RawRecord]:
        """Fetch Google News RSS for a pharma query."""
        records = []
        params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}

        try:
            resp = self._fetch_with_retry(GOOGLE_NEWS_RSS, params=params)
            if resp.status_code != 200:
                return records

            root = ElementTree.fromstring(resp.content)
            items = root.findall(".//item")

            for item in items[:self._max_per_query]:
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                pub_date = item.findtext("pubDate", "")
                source = item.findtext("source", "")

                event_date = self._parse_rss_date(pub_date)
                if since and event_date and event_date < since:
                    continue

                event_type = self._classify_event(title, "")

                record = RawRecord(
                    record_type=RecordType.EVENT,
                    external_id=hashlib.md5(link.encode()).hexdigest()[:16],
                    source_name=f"News: {source}" if source else "Pharma News",
                    provenance=Provenance(
                        source_type=self.source_type,
                        api_endpoint=GOOGLE_NEWS_RSS,
                        query_params=params,
                        retrieved_at=datetime.now(timezone.utc),
                        raw_response_hash=hashlib.sha256(title.encode()).hexdigest(),
                    ),
                    data={
                        "description": title,
                        "event_type": event_type,
                        "event_date": event_date.isoformat() if event_date else pub_date,
                        "source_url": link,
                        "source_name": source,
                        "query": query,
                        "source_feed": "google_news",
                    },
                    identifiers={},
                )
                records.append(record)
        except Exception as e:
            logger.debug("Google News parse error for '%s': %s", query, e)

        return records

    @staticmethod
    def _parse_rss_date(date_str: str) -> Optional[datetime]:
        """Parse RSS date format (RFC 822)."""
        if not date_str:
            return None
        formats = [
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S GMT",
            "%Y-%m-%dT%H:%M:%S%z",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None

    @staticmethod
    def _classify_event(title: str, description: str) -> str:
        """Classify a news event by type based on keywords."""
        text = (title + " " + description).lower()
        if any(w in text for w in ["approv", "fda approv", "ema approv", "chmp"]):
            return "approval"
        if any(w in text for w in ["complete response", "crl", "refuse to file"]):
            return "regulatory_setback"
        if any(w in text for w in ["phase 3", "phase iii", "pivotal", "primary endpoint"]):
            return "trial_readout"
        if any(w in text for w in ["acqui", "merger", "m&a", "buyout", "takeover"]):
            return "ma_deal"
        if any(w in text for w in ["shortage", "supply", "recall"]):
            return "supply_disruption"
        if any(w in text for w in ["safety", "warning", "adverse", "black box"]):
            return "safety_signal"
        if any(w in text for w in ["patent", "generic", "paragraph iv", "biosimilar"]):
            return "patent_ip"
        if any(w in text for w in ["pricing", "rebate", "cost", "ira", "negotiat"]):
            return "pricing"
        return "general"
