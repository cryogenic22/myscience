"""Loop ② — tests for per-entity KBQ living views.

A KBQ view is built from the entity's KBQ-tagged signals. v1 mapping of the
8 KBQs to signal kbq_tags is documented in services/kbq_views.py and needs
Riya sign-off (strategy-doc input #2).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from services.kbq_views import (
    build_entity_kbqs,
    build_entity_kbqs_for_asset,
    KBQ_CATALOG,
    kbq_tags_for,
)


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
        "primary_entity_name": "Eli Lilly",
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

    def test_entity_name_derived_from_signals(self):
        out = build_entity_kbqs(_make_db([_sig("s1", ["clinical"], "x")]), "company", "co-lilly")
        assert out["entity"]["name"] == "Eli Lilly"

    def test_items_capped_per_kbq(self):
        # 30 clinical signals → KBQ-3 caps the list (don't dump everything)
        signals = [_sig(f"s{i}", ["clinical"], f"readout {i}") for i in range(30)]
        out = build_entity_kbqs(_make_db(signals), "company", "co-lilly")
        clinical = next(v for v in out["kbqs"] if v["kbq"] == 3)
        assert len(clinical["items"]) <= 10


def _fact(fid, predicate, claim, fact_class="corporate"):
    return {
        "id": fid, "predicate": predicate, "fact_class": fact_class, "claim": claim,
        "confidence": 0.8, "valid_from": "2026-05-01",
        "source_id": "fda", "source_url": f"https://src/{fid}",
    }


def _make_db2(signals, facts):
    """DB mock that serves both the signals and the facts queries (PB-SL11)."""
    def fetch_all(sql, params=None):
        s = (sql or "").lower()
        if "from signals" in s:
            return signals
        if "from facts" in s:
            return facts
        return []
    db = MagicMock()
    db.fetch_all = MagicMock(side_effect=fetch_all)
    db.fetch_one = MagicMock(return_value=None)
    return db


class TestFactBackedKbqs:
    """PB-SL11 — the KBQ surface is a lens over the FACT LEDGER, not just signals."""

    def test_facts_route_into_their_kbq(self):
        facts = [
            _fact("f1", "label_indication", "Indicated for chronic weight management"),
            _fact("f2", "clinical_trial", "STEP 1 trial — 68 weeks"),
            _fact("f3", "wac_usd", "WAC $1349/mo"),
        ]
        out = build_entity_kbqs(_make_db2([], facts), "drug", "d1")
        by = {v["kbq"]: v for v in out["kbqs"]}
        assert any(it["fact_id"] == "f1" for it in by[1]["items"])  # Indications
        assert any(it["fact_id"] == "f2" for it in by[3]["items"])  # Clinical
        assert any(it["fact_id"] == "f3" for it in by[7]["items"])  # Pricing

    def test_fact_item_shape_carries_class_and_source(self):
        facts = [_fact("f1", "safety_signal", "Boxed warning: thyroid C-cell tumors", "corporate")]
        out = build_entity_kbqs(_make_db2([], facts), "drug", "d1")
        clinical = next(v for v in out["kbqs"] if v["kbq"] == 3)
        item = next(it for it in clinical["items"] if it["fact_id"] == "f1")
        assert item["source"] == "fact"
        assert item["fact_class"] == "corporate"
        assert item["source_url"] == "https://src/f1"
        assert item["signal_id"] is None

    def test_market_event_facts_are_skipped(self):
        facts = [_fact("f1", "market_event", "Routine recall lot 42")]
        out = build_entity_kbqs(_make_db2([], facts), "drug", "d1")
        # No KBQ should surface the unmapped market_event fact.
        all_ids = [it.get("fact_id") for v in out["kbqs"] for it in v["items"]]
        assert "f1" not in all_ids

    def test_facts_raise_completeness_for_signal_less_entity(self):
        facts = [_fact("f1", "label_indication", "Indicated for X"),
                 _fact("f2", "clinical_trial", "Phase 3")]
        out = build_entity_kbqs(_make_db2([], facts), "drug", "d1")
        assert out["completeness"] > 0.0  # facts alone make KBQs fresh

    def test_fact_duplicating_a_signal_is_deduped(self):
        # A safety_signal fact minted into a signal (SL07) must not appear twice.
        sig = _sig("s1", ["clinical"], "Boxed warning: thyroid tumors")
        fact = _fact("f1", "safety_signal", "Boxed warning: thyroid tumors")
        out = build_entity_kbqs(_make_db2([sig], [fact]), "drug", "d1")
        clinical = next(v for v in out["kbqs"] if v["kbq"] == 3)
        claims = [it["claim"] for it in clinical["items"]]
        assert claims.count("Boxed warning: thyroid tumors") == 1
        # the surviving one is the signal (curated leads)
        kept = next(it for it in clinical["items"] if it["claim"] == "Boxed warning: thyroid tumors")
        assert kept["source"] == "signal"

    def test_clinical_kbq_diversifies_by_predicate(self):
        # 20 trials + 1 adverse_event: the AE must still surface within the cap
        # (round-robin), not be buried behind 10 trials.
        facts = [_fact(f"t{i}", "clinical_trial", f"Trial {i}") for i in range(20)]
        facts.append(_fact("ae1", "adverse_event", "Nausea reported"))
        out = build_entity_kbqs(_make_db2([], facts), "drug", "d1")
        clinical = next(v for v in out["kbqs"] if v["kbq"] == 3)
        preds_present = {it["fact_id"] for it in clinical["items"]}
        assert "ae1" in preds_present  # diversification surfaced the lone AE

    def test_signals_lead_then_facts_fill(self):
        sig = _sig("s1", ["clinical"], "Curated clinical signal")
        facts = [_fact("f1", "clinical_trial", "A trial")]
        out = build_entity_kbqs(_make_db2([sig], facts), "drug", "d1")
        clinical = next(v for v in out["kbqs"] if v["kbq"] == 3)
        assert clinical["items"][0]["source"] == "signal"
        assert any(it["source"] == "fact" for it in clinical["items"])


class TestBuildForAsset:
    """PB-SL10 — KBQ-as-query-surface: resolve a typed asset → 8 KBQs."""

    def test_resolves_asset_then_builds(self, monkeypatch):
        # 'semaglutide' resolves to (drug, <uuid>) then the KBQ view is built
        # against the resolved id (the one the signals are keyed by).
        import services.kbq_views as kv

        monkeypatch.setattr(
            kv, "resolve_asset_to_subject",
            lambda db, asset: ("drug", "drug-uuid-123"),
        )
        signals = [_sig("s1", ["clinical"], "Phase 3 readout positive")]
        # signals carry the resolved id as primary_entity_id
        for s in signals:
            s["primary_entity_id"] = "drug-uuid-123"
        out = build_entity_kbqs_for_asset(_make_db(signals), "semaglutide")
        assert out["entity"]["type"] == "drug"
        assert out["entity"]["id"] == "drug-uuid-123"
        assert out["asset"] == "semaglutide"
        clinical = next(v for v in out["kbqs"] if v["kbq"] == 3)
        assert any(it["signal_id"] == "s1" for it in clinical["items"])

    def test_bare_company_name_falls_back_to_company(self, monkeypatch):
        # 'Novo Nordisk' is a company; parse_asset_ref would default it to a
        # drug. The bare-name fallback must retry it as a company and use the
        # company's signal-bearing entity.
        import services.kbq_views as kv

        def resolve(db, asset):
            if asset.startswith("company:"):
                return ("company", "co-novo")
            return ("drug", "novo nordisk")  # unresolved drug (raw slug)
        monkeypatch.setattr(kv, "resolve_asset_to_subject", resolve)

        # Entity-aware mock: signals exist only for the company id, so the drug
        # path is empty (completeness 0) and the company fallback must fire.
        sig = _sig("s1", ["clinical"], "Novo pipeline readout")
        sig["primary_entity_id"] = "co-novo"
        sig["primary_entity_name"] = "Novo Nordisk"

        db = MagicMock()
        def fetch_all(sql, params=None):
            if "from signals" in (sql or "").lower():
                return [sig] if params and "co-novo" in params else []
            return []
        db.fetch_all = MagicMock(side_effect=fetch_all)
        db.fetch_one = MagicMock(return_value=None)

        out = build_entity_kbqs_for_asset(db, "Novo Nordisk")
        assert out["entity"]["type"] == "company"
        assert out["entity"]["id"] == "co-novo"
        assert out["completeness"] > 0.0

    def test_unresolved_asset_returns_parity_skeleton(self, monkeypatch):
        import services.kbq_views as kv

        monkeypatch.setattr(
            kv, "resolve_asset_to_subject",
            lambda db, asset: ("drug", "unknown-slug"),
        )
        out = build_entity_kbqs_for_asset(_make_db([]), "nonexistent-drug")
        assert len(out["kbqs"]) == 8
        assert out["completeness"] == 0.0
        assert out["asset"] == "nonexistent-drug"
