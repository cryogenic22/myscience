"""News-feed reliability — Google News RSS 404s the default python-requests
User-Agent (and Railway egress), so the pharma news feed silently degraded in
prod. The connector must send a browser UA, and failed queries must be VISIBLE
(not swallowed at debug) so coverage loss surfaces instead of reading as "all
fresh". General sensing reliability — feeds CI, chat, and future use-cases alike.
"""

from __future__ import annotations

import logging

from connectors.news import PharmaNewsConnector


def test_connector_sends_browser_user_agent():
    c = PharmaNewsConnector()
    headers = getattr(c, "headers", None)
    assert headers and "User-Agent" in headers
    # A real browser UA — not the default python-requests UA Google News 404s.
    assert "Mozilla" in headers["User-Agent"]
    assert "python-requests" not in headers["User-Agent"].lower()


def test_failed_google_queries_are_surfaced_not_swallowed(caplog, monkeypatch):
    c = PharmaNewsConnector(target_overrides={"queries": ["q1", "q2"]})
    monkeypatch.setattr(c, "_fetch_fda_press", lambda since: [])

    def _boom(query, since):
        raise RuntimeError("HTTP 404")

    monkeypatch.setattr(c, "_fetch_google_news", _boom)
    with caplog.at_level(logging.WARNING):
        c.fetch()
    # A degraded feed must produce a WARNING that names how many queries failed,
    # not a silent debug line.
    assert any(
        "google news" in r.message.lower() and ("fail" in r.message.lower() or "404" in r.message)
        for r in caplog.records
        if r.levelno >= logging.WARNING
    ), "failed news queries were not surfaced at WARNING"
