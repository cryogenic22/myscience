"""Lightweight web research helper used by Deep Research mode."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Optional
from urllib.parse import parse_qs, urlparse

import requests

logger = logging.getLogger(__name__)


@dataclass
class WebResearchItem:
    title: str
    url: str
    snippet: str
    source: str


class WebResearchService:
    """Fetch supplemental public web results for analyst research mode."""

    def __init__(self, config):
        self.config = config

    @property
    def enabled(self) -> bool:
        research_cfg = getattr(self.config, "research", None)
        return bool(research_cfg and getattr(research_cfg, "web_enabled", False))

    def search(self, query: str, limit: Optional[int] = None) -> list[dict]:
        clean_query = query.strip()
        if not clean_query or not self.enabled:
            return []

        research_cfg = getattr(self.config, "research", None)
        configured_limit = int(getattr(research_cfg, "max_web_results", 6))
        max_results = max(1, min(limit or configured_limit, 12))

        serpapi_key = str(getattr(research_cfg, "serpapi_key", "")).strip()
        if serpapi_key:
            serp_items = self._search_serpapi(clean_query, max_results, serpapi_key)
            if serp_items:
                return [asdict(item) for item in serp_items]

        ddg_items = self._search_duckduckgo(clean_query, max_results)
        return [asdict(item) for item in ddg_items]

    def _search_serpapi(self, query: str, limit: int, api_key: str) -> list[WebResearchItem]:
        research_cfg = getattr(self.config, "research", None)
        timeout_seconds = float(getattr(research_cfg, "web_timeout_seconds", 8.0))
        try:
            response = requests.get(
                "https://serpapi.com/search.json",
                params={
                    "engine": "google",
                    "q": query,
                    "num": limit,
                    "api_key": api_key,
                },
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.warning("SERPAPI web research failed: %s", exc)
            return []

        seen: set[str] = set()
        items: list[WebResearchItem] = []
        for entry in payload.get("organic_results", []):
            title = str(entry.get("title") or "").strip()
            url = str(entry.get("link") or "").strip()
            snippet = str(entry.get("snippet") or "").strip()
            if not title or not url:
                continue
            if url in seen:
                continue
            seen.add(url)
            items.append(
                WebResearchItem(
                    title=title,
                    url=url,
                    snippet=snippet,
                    source="google",
                )
            )
            if len(items) >= limit:
                break
        return items

    def _search_duckduckgo(self, query: str, limit: int) -> list[WebResearchItem]:
        research_cfg = getattr(self.config, "research", None)
        timeout_seconds = float(getattr(research_cfg, "web_timeout_seconds", 8.0))
        try:
            response = requests.get(
                "https://duckduckgo.com/html/",
                params={"q": query},
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/123.0.0.0 Safari/537.36"
                    )
                },
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            html = response.text
        except Exception as exc:
            logger.warning("DuckDuckGo web research failed: %s", exc)
            return []

        try:
            from bs4 import BeautifulSoup
        except Exception as exc:
            logger.warning("BeautifulSoup unavailable for web parsing: %s", exc)
            return []

        soup = BeautifulSoup(html, "html.parser")
        seen: set[str] = set()
        items: list[WebResearchItem] = []
        for block in soup.select("div.result"):
            anchor = block.select_one("a.result__a")
            if not anchor:
                continue
            title = anchor.get_text(" ", strip=True)
            raw_url = str(anchor.get("href") or "").strip()
            url = _normalize_duckduckgo_url(raw_url)
            if not title or not url or url in seen:
                continue

            snippet_node = block.select_one(".result__snippet")
            snippet = snippet_node.get_text(" ", strip=True) if snippet_node else ""

            seen.add(url)
            items.append(
                WebResearchItem(
                    title=title,
                    url=url,
                    snippet=snippet,
                    source="duckduckgo",
                )
            )
            if len(items) >= limit:
                break

        return items


def _normalize_duckduckgo_url(raw_url: str) -> str:
    """Unwrap DuckDuckGo redirect URLs when present."""
    if not raw_url:
        return ""
    parsed = urlparse(raw_url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        query = parse_qs(parsed.query)
        redirected = query.get("uddg", [])
        if redirected:
            return redirected[0]
    return raw_url
