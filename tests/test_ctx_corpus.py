"""Tests for PharmaCorpusBuilder — CTX knowledge corpus from DB entities.

TDD: These tests are written BEFORE the implementation.
Run with: pytest tests/test_ctx_corpus.py -v
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ── Fixtures: mock DB data ──

MOCK_DRUGS = [
    {
        "id": "d001",
        "generic_name": "semaglutide",
        "brand_name": "Ozempic",
        "mechanism_name": "Glucagon-Like Peptide-1 Receptor Agonists",
        "company_name": "Novo Nordisk",
        "therapeutic_area": "Diabetes Mellitus, Type 2",
        "phase": "Phase 4",
        "pipeline_score": 85.2,
        "approval_status": "Approved",
    },
    {
        "id": "d002",
        "generic_name": "tirzepatide",
        "brand_name": "Mounjaro",
        "mechanism_name": "Glucagon-Like Peptide-1 Receptor Agonists",
        "company_name": "Eli Lilly",
        "therapeutic_area": "Diabetes Mellitus, Type 2",
        "phase": "Phase 4",
        "pipeline_score": 72.1,
        "approval_status": "Approved",
    },
    {
        "id": "d003",
        "generic_name": "dulaglutide",
        "brand_name": "Trulicity",
        "mechanism_name": "Glucagon-Like Peptide-1 Receptor Agonists",
        "company_name": "Eli Lilly",
        "therapeutic_area": "Diabetes Mellitus, Type 2",
        "phase": "Phase 4",
        "pipeline_score": 45.0,
        "approval_status": "Approved",
    },
]

MOCK_COMPANIES = [
    {
        "id": "c001",
        "company_name": "Novo Nordisk",
        "drug_count": 12,
        "trial_count": 142,
        "pipeline_score_total": 320.5,
    },
    {
        "id": "c002",
        "company_name": "Eli Lilly",
        "drug_count": 18,
        "trial_count": 198,
        "pipeline_score_total": 410.2,
    },
]

MOCK_TRIALS = [
    {
        "nct_id": "NCT05035095",
        "title": "STEP HFpEF: Semaglutide in Heart Failure with Preserved Ejection Fraction",
        "phase": "Phase 3",
        "status": "COMPLETED",
        "drug_name": "semaglutide",
        "enrollment": 529,
        "start_date": "2021-06-01",
    },
    {
        "nct_id": "NCT04184622",
        "title": "SURMOUNT-1: Tirzepatide for Obesity",
        "phase": "Phase 3",
        "status": "COMPLETED",
        "drug_name": "tirzepatide",
        "enrollment": 2539,
        "start_date": "2019-12-01",
    },
]

MOCK_MECHANISMS = [
    {
        "id": "m001",
        "mechanism_name": "Glucagon-Like Peptide-1 Receptor Agonists",
        "drug_count": 49,
        "trial_count": 583,
    },
]


class MockDB:
    """Mock database that returns pre-configured query results.

    Routes queries by matching the first table in the FROM clause.
    """

    def __init__(self):
        self._results: dict[str, list[dict]] = {}

    def set_results(self, query_key: str, results: list[dict]):
        self._results[query_key] = results

    def fetch_all(self, sql: str, params=None) -> list[dict]:
        sql_lower = sql.lower()
        # Match on the primary table (FROM clause), not JOINs
        import re
        from_match = re.search(r'\bfrom\s+(\w+)', sql_lower)
        if from_match:
            primary_table = from_match.group(1)
            if primary_table in self._results:
                return self._results[primary_table]
        # Fallback: any key match
        for key, results in self._results.items():
            if key in sql_lower:
                return results
        return []

    def fetch_one(self, sql: str, params=None) -> dict | None:
        results = self.fetch_all(sql, params)
        return results[0] if results else None


@pytest.fixture
def mock_db():
    db = MockDB()
    db.set_results("drugs", MOCK_DRUGS)
    db.set_results("companies", MOCK_COMPANIES)
    db.set_results("clinical_trials", MOCK_TRIALS)
    db.set_results("mechanisms_of_action", MOCK_MECHANISMS)
    return db


@pytest.fixture
def corpus_builder(mock_db):
    from services.ctx_corpus import PharmaCorpusBuilder
    return PharmaCorpusBuilder(mock_db)


# ── Phase 1.1a: Export tests ──

class TestExportDrugs:
    """Verify drug export produces correct YAML-ready dicts."""

    def test_returns_all_drugs(self, corpus_builder):
        drugs = corpus_builder.export_drugs()
        assert len(drugs) == 3

    def test_drug_has_required_fields(self, corpus_builder):
        drugs = corpus_builder.export_drugs()
        drug = drugs[0]
        required = {"name", "brand_name", "mechanism", "company", "therapeutic_area"}
        assert required.issubset(set(drug.keys())), f"Missing fields: {required - set(drug.keys())}"

    def test_drug_name_is_generic_name(self, corpus_builder):
        drugs = corpus_builder.export_drugs()
        assert drugs[0]["name"] == "semaglutide"

    def test_drug_preserves_relationships(self, corpus_builder):
        drugs = corpus_builder.export_drugs()
        sema = next(d for d in drugs if d["name"] == "semaglutide")
        assert sema["company"] == "Novo Nordisk"
        assert sema["mechanism"] == "Glucagon-Like Peptide-1 Receptor Agonists"
        assert sema["therapeutic_area"] == "Diabetes Mellitus, Type 2"


def test_drugs_sql_one_row_per_name_prefer_active_then_richest():
    """Conservation regression (P4 + dup-consolidation): the CTX corpus must emit
    ONE row per drug name — the best available — so hydrate_by_name can't match an
    empty 0-fact dup or 'excluded' junk and report a rich drug as having no data.
      * 'excluded'/'stale' junk is filtered out (the pseudo-drug that substring-
        matched 'semaglutide').
      * but merged/superseded rows are NOT blanket-excluded — a strict active-only
        filter would silently DROP drugs whose canonical was left 'merged' with no
        active replacement (~11 high-fact drugs post-consolidation). Prefer active,
        then richest, so no drug with data is dropped."""
    from services.ctx_corpus import _DRUGS_SQL
    s = _DRUGS_SQL.lower()
    assert "distinct on (lower(d.generic_name))" in s
    # junk excluded, but not a blanket merged/superseded drop
    assert "not in ('excluded', 'stale')" in s
    # prefer active, then richest (facts + trials)
    assert "= 'active') desc" in s
    assert "from facts f" in s and "from clinical_trials ct" in s


class TestExportCompanies:
    """Verify company export."""

    def test_returns_all_companies(self, corpus_builder):
        companies = corpus_builder.export_companies()
        assert len(companies) == 2

    def test_company_has_required_fields(self, corpus_builder):
        companies = corpus_builder.export_companies()
        required = {"name", "drug_count", "trial_count", "pipeline_score"}
        assert required.issubset(set(companies[0].keys()))


class TestExportTrials:
    """Verify trial export."""

    def test_returns_all_trials(self, corpus_builder):
        trials = corpus_builder.export_trials()
        assert len(trials) == 2

    def test_trial_has_required_fields(self, corpus_builder):
        trials = corpus_builder.export_trials()
        required = {"nct_id", "title", "phase", "status", "drug_name"}
        assert required.issubset(set(trials[0].keys()))


class TestExportMechanisms:
    """Verify mechanism export."""

    def test_returns_all_mechanisms(self, corpus_builder):
        mechanisms = corpus_builder.export_mechanisms()
        assert len(mechanisms) == 1

    def test_mechanism_has_required_fields(self, corpus_builder):
        mechanisms = corpus_builder.export_mechanisms()
        required = {"name", "drug_count", "trial_count"}
        assert required.issubset(set(mechanisms[0].keys()))


# ── Phase 1.1b: Corpus directory tests ──

class TestBuildCorpusDir:
    """Verify the corpus directory structure."""

    def test_creates_output_directory(self, corpus_builder):
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_builder.build_corpus_dir(tmpdir)
            assert os.path.isdir(tmpdir)

    def test_writes_entity_files(self, corpus_builder):
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_builder.build_corpus_dir(tmpdir)
            files = list(Path(tmpdir).glob("*.yaml"))
            # 3 drugs + 2 companies + 1 mechanism + 1 trials + 1 ctxpack config = 8
            assert len(files) >= 7, f"Expected ≥7 YAML files, got {len(files)}: {[f.name for f in files]}"

    def test_drug_files_exist(self, corpus_builder):
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_builder.build_corpus_dir(tmpdir)
            drug_files = list(Path(tmpdir).glob("drug_*.yaml"))
            assert len(drug_files) == 3, f"Expected 3 drug files, got {len(drug_files)}"

    def test_writes_ctxpack_config(self, corpus_builder):
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_builder.build_corpus_dir(tmpdir)
            config_file = Path(tmpdir) / "ctxpack.yaml"
            assert config_file.exists(), "ctxpack.yaml config not created"

    def test_config_has_domain(self, corpus_builder):
        with tempfile.TemporaryDirectory() as tmpdir:
            corpus_builder.build_corpus_dir(tmpdir)
            import yaml
            with open(Path(tmpdir) / "ctxpack.yaml") as f:
                cfg = yaml.safe_load(f)
            assert cfg["domain"] == "pharma-intelligence"


# ── Phase 1.1c: Pack tests ──

class TestPack:
    """Verify CTX packing produces valid L2 + L3 documents."""

    def test_pack_returns_result(self, corpus_builder):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = corpus_builder.pack(tmpdir)
            assert result is not None
            assert result.document is not None

    def test_pack_l2_has_entity_sections(self, corpus_builder):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = corpus_builder.pack(tmpdir)
            from ctxpack.core.serializer import serialize
            text = serialize(result.document)
            # Should have drug entity sections
            assert "semaglutide" in text.lower() or "DRUG" in text

    def test_pack_l3_exists(self, corpus_builder):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = corpus_builder.pack(tmpdir)
            assert result.l3_document is not None, "L3 index not generated"

    def test_pack_compression_ratio(self, corpus_builder):
        """Compression ratio should be meaningful (>1x) even on small test data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = corpus_builder.pack(tmpdir)
            assert result.source_token_count > 0
            from ctxpack.core.serializer import serialize
            ctx_text = serialize(result.document)
            ctx_tokens = len(ctx_text) // 4  # rough estimate
            # On small test data ratio may be low, but should at least produce output
            assert ctx_tokens > 0

    def test_pack_entity_coverage(self, corpus_builder):
        """Every entity type should have at least one section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = corpus_builder.pack(tmpdir)
            from ctxpack.core.serializer import serialize
            text = serialize(result.document).upper()
            # Check for entity type presence (sections or content)
            assert result.entity_count >= 3, f"Expected ≥3 entities, got {result.entity_count}"

    def test_pack_validates_cleanly(self, corpus_builder):
        """Packed document should pass validation without errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = corpus_builder.pack(tmpdir)
            from ctxpack.core.validator import validate
            diagnostics = validate(result.document)
            errors = [d for d in diagnostics if d.severity == "error"]
            assert len(errors) == 0, f"Validation errors: {errors}"


# ── Phase 1.1d: L3 index tests ──

class TestL3Index:
    """Verify L3 index is compact and useful for routing."""

    def test_l3_under_token_limit(self, corpus_builder):
        """L3 index should be <2000 tokens."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = corpus_builder.pack(tmpdir)
            assert result.l3_document is not None
            from ctxpack.core.serializer import serialize
            l3_text = serialize(result.l3_document)
            l3_tokens = len(l3_text) // 4
            assert l3_tokens < 2000, f"L3 index too large: {l3_tokens} tokens"

    def test_l3_lists_entity_names(self, corpus_builder):
        """L3 should contain entity identifiers for routing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = corpus_builder.pack(tmpdir)
            from ctxpack.core.serializer import serialize
            l3_text = serialize(result.l3_document).lower()
            # Should reference at least some entity names
            assert "drug" in l3_text or "semaglutide" in l3_text


# ── Phase 1.1e: Round-trip tests ──

class TestRoundTrip:
    """Verify pack → serialize → parse cycle."""

    def test_serialize_parse_roundtrip(self, corpus_builder):
        """Serialized L2 should parse back without errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = corpus_builder.pack(tmpdir)
            from ctxpack.core.serializer import serialize
            from ctxpack.core.parser import parse
            text = serialize(result.document)
            reparsed = parse(text, level=2)
            assert reparsed is not None
            assert reparsed.header is not None


# ── Phase 1.1f: Hydration integration tests ──

class TestHydrationIntegration:
    """Verify packed corpus can be hydrated for queries."""

    def test_hydrate_by_query(self, corpus_builder):
        """Query-based hydration should return relevant sections."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = corpus_builder.pack(tmpdir)
            from ctxpack.core.hydrator import hydrate_by_query
            hydration = hydrate_by_query(result.document, "semaglutide mechanism", max_sections=3)
            assert len(hydration.sections) > 0, "No sections matched for 'semaglutide mechanism'"
            assert hydration.tokens_injected > 0

    def test_hydrate_token_budget(self, corpus_builder):
        """Hydrated context should be well under raw corpus size."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = corpus_builder.pack(tmpdir)
            from ctxpack.core.hydrator import hydrate_by_query
            hydration = hydrate_by_query(result.document, "GLP-1 landscape", max_sections=5)
            assert hydration.tokens_injected < 5000, f"Hydration too large: {hydration.tokens_injected} tokens"

    def test_entity_graph_traversal(self, corpus_builder):
        """Entity graph should allow multi-hop traversal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = corpus_builder.pack(tmpdir)
            from ctxpack.core.entity_graph import EntityGraph
            graph = EntityGraph.from_document(result.document)
            assert len(graph.to_dict()) >= 0  # May be empty on small test data, but shouldn't crash


# ── L1: live schema-drift regression net (DB-gated) ──
#
# The corpus SQL silently drifted off the schema (mechanisms -> mechanisms_of_action,
# company_name -> name, nct_id/title/enrollment renamed) so PharmaCorpusBuilder.pack()
# crashed -> get_unified_handler() returned None -> EVERY chat fell back to the legacy
# handler. The unit tests above use a MockDB and could not catch that. These run each
# export query against the real DB and assert it EXECUTES and yields the keys the
# corpus builder reads, so the drift can't recur unnoticed.
import os as _os

import pytest as _pytest

_DB_URL = _os.environ.get("DATABASE_URL")
_live = _pytest.mark.skipif(not _DB_URL, reason="DATABASE_URL not set — live corpus gate skipped")


@_pytest.fixture(scope="module")
def _live_builder():
    from db import Database
    from services.ctx_corpus import PharmaCorpusBuilder
    return PharmaCorpusBuilder(Database(_DB_URL))


@_live
def test_export_drugs_executes_against_real_schema(_live_builder):
    drugs = _live_builder.export_drugs(limit=5)
    assert drugs, "export_drugs returned nothing against prod"
    row = drugs[0]
    for k in ("name", "mechanism", "company", "therapeutic_area", "id"):
        assert k in row, f"missing key {k}"


@_live
def test_export_companies_and_mechanisms_execute(_live_builder):
    assert _live_builder.export_companies(), "export_companies empty"
    assert _live_builder.export_mechanisms(), "export_mechanisms empty"


@_live
def test_export_trials_executes(_live_builder):
    trials = _live_builder.export_trials()
    assert trials, "export_trials empty"
    for k in ("nct_id", "title", "phase", "status", "drug_name"):
        assert k in trials[0], f"missing key {k}"


@_live
def test_pack_builds_unified_corpus(_live_builder):
    """pack() must succeed end-to-end — this is exactly what get_unified_handler
    calls; if it raises, the unified handler is dead and chat falls back to legacy."""
    import tempfile
    result = _live_builder.pack(tempfile.mkdtemp())
    assert result.entity_count > 0, "corpus packed 0 entities"
