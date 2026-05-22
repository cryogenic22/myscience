"""Loop ② — tests for per-entity KBQ living views.

A KBQ view is built from the entity's KBQ-tagged signals. v1 mapping of the
8 KBQs to signal kbq_tags is documented in services/kbq_views.py and needs
Riya sign-off (strategy-doc input #2).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from services.kbq_views import build_entity_kbqs, KBQ_CATALOG, kbq_tags_for


def _sig(sid, tags, headline, impact="high", conf="confirmed"):
    return {
        "id": sid,
        "kbq_tags": tags,
        "headline": headline,
        "impact_tier": impact,
        "impact_score": 0.9,
        "confidence_tier": conf,
        "evidence_document_ids": [sid],
        "created_at": "2026-05-20T00:00:00Z",
        "status": "shipped",
    }


def _make_db(signals):
    def fetch_all(sql, params=None):
        if "from signals" in (sql or "").lower():
            return signals
        return []
    db = MagicMock()
    db.fetch_all = MagicMock(side_effect=fetch_all)
    return db


class TestCatalog:
    def test_eight_kbqs(self):
        assert len(KBQ_CATALOG) == 8
        ids = [k["kbq"] for k in KBQ_CATALOG]
        assert ids == [1, 2, 3, 4, 5, 6, 7, 8]
        for k in KBQ_CATALOG:
            assert k["title"]

    def test_kbq_tags_for_known(self):
        # KBQ-3 Clinical maps to the 'clinical' signal tag
        assert "clinical" in kbq_tags_for(3)
        # KBQ-7 Pricing maps to pricing_access
        assert "pricing_access" in kbq_tags_for(7)


class TestBuildEntityKbqs:
    def test_returns_all_eight_slots_with_parity(self):
        db = _make_db([])
        out = build_entity_kbqs(db, "company", "co-lilly")
        assert len(out["kbqs"]) == 8
        # parity: every slot present even with no data
        for v in out["kbqs"]:
            assert "kbq" in v and "title" in v and "status" in v and "items" in v
            if not v["items"]:
                assert v["status"] == "insufficient"

    def test_routes_signals_into_matching_kbq(self):
        signals = [
            _sig("s1", ["clinical"], "Phase 3 readout positive"),
            _sig("s2", ["pricing_access"], "WAC cut announced"),
            _sig("s3", ["m_and_a", "strategic"], "Acquires biotech"),
        ]
        out = build_entity_kbqs(_make_db(signals), "company", "co-lilly")
        by_id = {v["kbq"]: v for v in out["kbqs"]}
        # KBQ-3 Clinical gets s1
        assert any(it["signal_id"] == "s1" for it in by_id[3]["items"])
        # KBQ-7 Pricing gets s2
        assert any(it["signal_id"] == "s2" for it in by_id[7]["items"])
        # KBQ-2 Competitors gets the m_and_a/strategic signal
        assert any(it["signal_id"] == "s3" for it in by_id[2]["items"])

    def test_items_carry_evidence_and_metadata(self):
        signals = [_sig("s1", ["clinical"], "Phase 3 readout positive")]
        out = build_entity_kbqs(_make_db(signals), "company", "co-lilly")
        clinical = next(v for v in out["kbqs"] if v["kbq"] == 3)
        item = clinical["items"][0]
        assert item["claim"] == "Phase 3 readout positive"
        assert item["evidence_ids"] == ["s1"]
        assert item["impact_tier"] == "high"
        assert item["confidence_tier"] == "confirmed"

    def test_completeness_is_fraction_of_filled_slots(self):
        signals = [
            _sig("s1", ["clinical"], "A"),
            _sig("s2", ["pricing_access"], "B"),
        ]
        out = build_entity_kbqs(_make_db(signals), "company", "co-lilly")
        # 2 of 8 KBQs filled (clinical→3, pricing_access→7) → 0.25
        assert 0.0 < out["completeness"] <= 1.0
        filled = sum(1 for v in out["kbqs"] if v["items"])
        assert abs(out["completeness"] - filled / 8) < 1e-6

    def test_entity_echoed_in_payload(self):
        out = build_entity_kbqs(_make_db([]), "company", "co-lilly")
        assert out["entity"]["id"] == "co-lilly"
        assert out["entity"]["type"] == "company"

    def test_items_capped_per_kbq(self):
        # 30 clinical signals → KBQ-3 caps the list (don't dump everything)
        signals = [_sig(f"s{i}", ["clinical"], f"readout {i}") for i in range(30)]
        out = build_entity_kbqs(_make_db(signals), "company", "co-lilly")
        clinical = next(v for v in out["kbqs"] if v["kbq"] == 3)
        assert len(clinical["items"]) <= 10
