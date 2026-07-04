"""DataHub — serve the Croissant (JSON-LD) FAIR product descriptor.

The per-dataset Croissant metadata is generated + persisted into
``dataset_catalog.croissant_metadata`` by ``refresh_all()`` but was served by
NO route, so the machine-readable FAIR descriptor a consumer/agent binds to was
unreachable. These DB-free tests pin the two new read-only routes by calling the
route functions directly with a stub DB (no TestClient / no auth needed).
"""
from __future__ import annotations

import pytest

from api.routes.catalog import croissant_index, dataset_croissant


class _StubDB:
    """Answers only the two queries the croissant routes issue."""

    def __init__(self, by_name=None, primary=None, bundle_rows=None):
        self._by_name = by_name or {}      # dataset_name -> croissant_metadata dict
        self._primary = primary            # dataset_name resolved from a bare source_type
        self._bundle_rows = bundle_rows or []

    def fetch_one(self, sql, params=None):
        if "croissant_metadata FROM dataset_catalog WHERE dataset_name" in sql:
            meta = self._by_name.get(params[0])
            return {"croissant_metadata": meta} if meta is not None else None
        if "SELECT dataset_name FROM dataset_catalog WHERE source_type" in sql:
            return {"dataset_name": self._primary} if self._primary else None
        return None

    def fetch_all(self, sql, params=None):
        # export_croissant_bundle's sub-dataset scan
        return self._bundle_rows


def _croissant(name):
    return {"@type": "sc:Dataset", "name": name, "cr:recordSet": [{"field": "x"}]}


class TestDatasetCroissant:
    def test_serves_persisted_descriptor_by_dataset_name(self):
        db = _StubDB(by_name={"clinical_trials_gov.trials": _croissant("trials")})
        out = dataset_croissant(source_key="clinical_trials_gov.trials", db=db)
        assert out["@type"] == "sc:Dataset"
        assert out["name"] == "trials"
        assert out["cr:recordSet"]  # real content, not an empty descriptor

    def test_resolves_bare_source_type_to_primary_dataset(self):
        # A bare source_type has no exact dataset_name row → resolve to the
        # primary (largest-row_count) dataset instead of 404.
        db = _StubDB(
            by_name={"clinical_trials_gov.trials": _croissant("trials")},
            primary="clinical_trials_gov.trials",
        )
        out = dataset_croissant(source_key="clinical_trials_gov", db=db)
        assert out["name"] == "trials"

    def test_unknown_dataset_404s_honestly(self):
        from fastapi import HTTPException
        db = _StubDB(by_name={}, primary=None)
        with pytest.raises(HTTPException) as ei:
            dataset_croissant(source_key="no-such-dataset", db=db)
        assert ei.value.status_code == 404


class TestCroissantIndex:
    def test_discovery_index_returns_bundle_with_haspart(self):
        db = _StubDB(bundle_rows=[
            {"dataset_name": "a", "row_count": 10, "croissant_metadata": _croissant("a")},
            {"dataset_name": "b", "row_count": 20, "croissant_metadata": _croissant("b")},
        ])
        out = croissant_index(db=db)
        assert out["@type"] == "sc:Dataset"
        # the top-level descriptor must reference the sub-datasets (hasPart)
        assert "hasPart" in out
        assert len(out["hasPart"]) == 2
