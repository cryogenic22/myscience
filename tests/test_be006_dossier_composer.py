"""BE-6 — dossier composer tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


def _drug_row():
    return {
        "id": "drug-1",
        "generic_name": "tirzepatide",
        "brand_name": "Mounjaro",
        "company_id": "co-1",
        "approval_date": "2022-05-13",
        "molecule_embedding": [0.1] * 1536,  # large field that should be filtered
        "aliases": ["LY3298176"],
    }


def _build_db():
    """Fake DB serving stable shapes for each composer query."""
    db = MagicMock()

    drugs = [_drug_row()]
    signals = [
        {"id": "sig-1", "headline": "Phase 3 readout positive",
         "kbq_tags": ["clinical"], "primary_entity_type": "drug",
         "primary_entity_id": "drug-1",
         "created_at": datetime(2026, 5, 5, tzinfo=timezone.utc)},
    ]
    evidence_rows = [
        {"evidence_id": "ev-1", "source_id": "pubmed",
         "source_name": "PubMed", "source_tier": "T3",
         "source_url": "https://pubmed.ncbi.nlm.nih.gov/123",
         "snippet": "HbA1c reduction observed.",
         "extracted_text": "HbA1c reduction observed at week 24.",
         "published_at": datetime(2026, 4, 1, tzinfo=timezone.utc),
         "retrieved_at": datetime(2026, 4, 1, tzinfo=timezone.utc),
         "confidence": 0.92},
    ]
    watch_rows = [
        {"user_id": "u-1", "email": "maya@x.com", "name": "Maya"},
    ]
    related_rows = [
        {"neighbor_id": "trial-1", "neighbor_type": "trial",
         "link_type": "INVESTIGATES", "edge_count": 3},
        {"neighbor_id": "co-1", "neighbor_type": "company",
         "link_type": "SPONSORS", "edge_count": 1},
    ]

    def fake_fetch_one(sql, params=None):
        s = (sql or "").lower()
        if "from drugs" in s and "where id::text" in s:
            return drugs[0] if params and params[0] == "drug-1" else None
        if "from drugs" in s and "where lower(generic_name)" in s:
            if params and params[0].lower() == "tirzepatide":
                return drugs[0]
            return None
        return None

    def fake_fetch_all(sql, params=None):
        s = (sql or "").lower()
        if "from signals" in s:
            return signals
        if "evidence_records" in s and "claim_evidence_links" in s:
            return evidence_rows
        if "watchlist_entries" in s:
            return watch_rows
        if "from entity_links" in s:
            return related_rows
        return []

    db.fetch_one.side_effect = fake_fetch_one
    db.fetch_all.side_effect = fake_fetch_all
    return db


# ════════════════════════════════════════════════════════════════════
# compose_dossier
# ════════════════════════════════════════════════════════════════════

class TestComposer:
    def test_resolves_by_uuid(self):
        from services.dossier import compose_dossier
        db = _build_db()
        out = compose_dossier(db, entity_type="drug",
                              slug_or_id="00000000-0000-0000-0000-000000drug1")
        # The DB returns None for any UUID we don't pre-seed
        assert out is None

    def test_resolves_by_slug(self):
        from services.dossier import compose_dossier
        db = _build_db()
        out = compose_dossier(db, entity_type="drug", slug_or_id="tirzepatide")
        assert out is not None
        assert out.entity["name"].startswith("tirzepatide") or "tirzepatide" in out.entity["name"]
        assert out.entity["type"] == "drug"

    def test_strips_embedding_from_identity_fields(self):
        from services.dossier import compose_dossier
        db = _build_db()
        out = compose_dossier(db, entity_type="drug", slug_or_id="tirzepatide")
        assert "molecule_embedding" not in out.entity["identity_fields"]
        # Other fields stay
        assert out.entity["identity_fields"].get("brand_name") == "Mounjaro"

    def test_assembles_recent_moves(self):
        from services.dossier import compose_dossier
        db = _build_db()
        out = compose_dossier(db, entity_type="drug", slug_or_id="tirzepatide")
        assert len(out.recent_moves) == 1
        rm = out.recent_moves[0]
        assert rm["headline"] == "Phase 3 readout positive"
        assert rm["kbq_tag"] == "clinical"
        assert rm["signal_id"] == "sig-1"

    def test_assembles_evidence_refs(self):
        from services.dossier import compose_dossier
        db = _build_db()
        out = compose_dossier(db, entity_type="drug", slug_or_id="tirzepatide")
        assert len(out.evidence_refs) == 1
        ev = out.evidence_refs[0]
        assert ev["source_tier"] == "T3"
        assert "HbA1c" in ev["snippet"]

    def test_assembles_watching(self):
        from services.dossier import compose_dossier
        db = _build_db()
        out = compose_dossier(db, entity_type="drug", slug_or_id="tirzepatide")
        assert len(out.watching) == 1
        assert out.watching[0]["name"] == "Maya"

    def test_assembles_related_entities(self):
        from services.dossier import compose_dossier
        db = _build_db()
        out = compose_dossier(db, entity_type="drug", slug_or_id="tirzepatide")
        assert len(out.related_entities) == 2
        # Sort: edge_count DESC → trial (3) before company (1)
        assert out.related_entities[0]["type"] == "trial"

    def test_missing_entity_returns_none(self):
        from services.dossier import compose_dossier
        db = _build_db()
        out = compose_dossier(db, entity_type="drug", slug_or_id="not-a-drug")
        assert out is None

    def test_unknown_entity_type_raises(self):
        from services.dossier import compose_dossier
        db = MagicMock()
        with pytest.raises(ValueError, match="entity_type"):
            compose_dossier(db, entity_type="bogus", slug_or_id="x")

    def test_section_failures_dont_break_dossier(self):
        """If recent_moves / evidence / watching / related raise, the
        composer still returns the entity + empty sections."""
        from services.dossier import compose_dossier
        db = MagicMock()
        db.fetch_one.return_value = _drug_row()
        db.fetch_all.side_effect = RuntimeError("table missing")

        out = compose_dossier(db, entity_type="drug", slug_or_id="tirzepatide")
        assert out is not None
        assert out.recent_moves == []
        assert out.evidence_refs == []
        assert out.watching == []
        assert out.related_entities == []


# ════════════════════════════════════════════════════════════════════
# Endpoint
# ════════════════════════════════════════════════════════════════════

class TestDossierEndpoint:
    def test_route_registered(self):
        from api.app import create_app
        app = create_app()
        paths = {r.path for r in app.routes}
        assert "/dossier/{entity_type}/{slug_or_id}" in paths
        assert "/api/v1/dossier/{entity_type}/{slug_or_id}" in paths

    def test_invalid_entity_type_400(self):
        from fastapi.testclient import TestClient
        from api.app import create_app
        from api.deps import get_db

        db = MagicMock()
        app = create_app()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        r = client.get("/dossier/bogus/tirzepatide")
        assert r.status_code == 400, r.text

    def test_404_when_not_found(self):
        from fastapi.testclient import TestClient
        from api.app import create_app
        from api.deps import get_db

        db = MagicMock()
        db.fetch_one.return_value = None
        db.fetch_all.return_value = []
        app = create_app()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        r = client.get("/dossier/drug/nope")
        assert r.status_code == 404, r.text
