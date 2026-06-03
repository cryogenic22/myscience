"""PB-SL09 — market_events ingest dedup (stop the recall re-insert flood)."""
from __future__ import annotations

from integration.knowledge_store import KnowledgeStore


def test_event_hash_is_stable_for_same_event():
    h1 = KnowledgeStore._event_hash("drug-1", "RECALL_CLASS_I", "Carcinogen impurity", "2026-01-01")
    h2 = KnowledgeStore._event_hash("drug-1", "RECALL_CLASS_I", "Carcinogen impurity", "2026-01-01")
    assert h1 == h2 and len(h1) == 64


def test_event_hash_normalizes_case_and_whitespace():
    # the same recall text with trailing space / case variation must collide
    a = KnowledgeStore._event_hash("d", "RECALL", "Carcinogen impurity detected", "2026-01-01")
    b = KnowledgeStore._event_hash("d", "RECALL", "  carcinogen impurity detected ", "2026-01-01")
    assert a == b


def test_event_hash_differs_on_distinct_events():
    base = KnowledgeStore._event_hash("d", "RECALL", "impurity", "2026-01-01")
    assert base != KnowledgeStore._event_hash("d", "RECALL", "impurity", "2026-02-01")  # date
    assert base != KnowledgeStore._event_hash("d", "SHORTAGE", "impurity", "2026-01-01")  # type
    assert base != KnowledgeStore._event_hash("d2", "RECALL", "impurity", "2026-01-01")  # drug


def test_event_hash_handles_nulls():
    # no drug / no date must still produce a stable hash (shortages w/o a drug)
    h = KnowledgeStore._event_hash(None, "SHORTAGE", "supply disruption", None)
    assert len(h) == 64
