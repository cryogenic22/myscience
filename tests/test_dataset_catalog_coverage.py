"""Dataset-catalog coverage + shared-table source_api scoping (PR2).

Guards two invariants that were previously untested and silently wrong:

  1. COVERAGE — every registered connector (`CONNECTOR_REGISTRY`) is a catalog
     product. Before this change `DATASET_DEFINITIONS` hand-listed only 6 of the
     15 sources, so 9 real ingested datasets were invisible in the catalog.

  2. NO DOUBLE-COUNT — when two dataset products share a physical table
     (drugs, clinical_trials, market_events, therapeutic_areas are each written
     by >1 source), each product's row_count / completeness / freshness /
     imbalance must be scoped `WHERE source_api = <that source>`. Without it,
     `count(*) FROM {table}` attributes the WHOLE table to BOTH products — the
     dominant silent-degradation failure the conservation gates exist to catch.

Grounded against a 2026-07-06 prod probe of the shared-table `source_api`
distribution:
  drugs           = {backfill:1014, clinical_trials_gov:651, fda_orange_book:122,
                     chembl:31, pubchem:22}
  clinical_trials = {clinical_trials_gov:5578, ema:310}
  market_events   = {fda_shortages:44591, pharma_news:1858}
  therapeutic_areas = {mesh_ontology:96, open_targets:56}
  drug_pricing    = {cms_nadac:290}   ← NADAC source_api is 'cms_nadac', NOT 'nadac'

DB is faked; no live Postgres needed.
"""

from __future__ import annotations

import pytest


# ────────────────────────────────────────────────────────────────────
# (1) COVERAGE — all registered sources become catalog products
# ────────────────────────────────────────────────────────────────────

def test_all_registered_sources_have_a_dataset_product():
    """Every SourceType in CONNECTOR_REGISTRY must have >=1 dataset definition."""
    from integration.dataset_catalog import build_dataset_definitions
    from connectors import CONNECTOR_REGISTRY

    defs = build_dataset_definitions()
    covered = {d["source_type"] for d in defs}
    expected = {st.value for st in CONNECTOR_REGISTRY.keys()}
    missing = expected - covered
    assert not missing, f"registered sources with no catalog product: {sorted(missing)}"


def test_every_definition_carries_the_required_refresh_keys():
    """`_refresh_entry` accesses these five keys with hard `defn[...]`; a derived
    entry missing any would be silently dropped by refresh_all's try/except."""
    from integration.dataset_catalog import build_dataset_definitions

    required = {"dataset_name", "source_type", "entity_type", "table_name", "description"}
    for d in build_dataset_definitions():
        missing = required - set(d)
        assert not missing, f"{d.get('dataset_name')} missing required keys {missing}"
        for k in required:
            assert d[k], f"{d.get('dataset_name')} has empty required key '{k}'"


def test_dataset_names_are_unique():
    """dataset_catalog.dataset_name is UNIQUE — two definitions must not collide
    (a shared table gets two products distinguished by dataset_name, not one)."""
    from integration.dataset_catalog import build_dataset_definitions

    names = [d["dataset_name"] for d in build_dataset_definitions()]
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, f"duplicate dataset_name(s): {sorted(dupes)}"


# ────────────────────────────────────────────────────────────────────
# (2) NO DOUBLE-COUNT — shared-table products must be source-scoped
# ────────────────────────────────────────────────────────────────────

def test_every_product_is_source_scoped():
    """Every product must declare a source_api. A product is one source's
    contribution to a table; an unscoped product reports the WHOLE table, which
    misattributes on ANY multi-source table — even one with a single catalog
    product (e.g. `companies` is written by SEC EDGAR *and* the entity resolver's
    auto-created trial sponsors; an unscoped `sec_edgar.filings` would claim all
    ~1.5k companies as SEC's). Being single-*product* is not the same as being
    single-*source*: scope by source_api, always."""
    from integration.dataset_catalog import build_dataset_definitions

    unscoped = [d["dataset_name"] for d in build_dataset_definitions() if not d.get("source_api")]
    assert not unscoped, f"products with no source_api scope (would report whole table): {unscoped}"


def test_products_sharing_a_table_all_declare_source_api():
    """The double-count case, called out explicitly: when two products point at
    the same table_name, every product on that table must be source-scoped."""
    from integration.dataset_catalog import build_dataset_definitions

    defs = build_dataset_definitions()
    by_table: dict[str, list[dict]] = {}
    for d in defs:
        by_table.setdefault(d["table_name"], []).append(d)

    offenders = {}
    for table, group in by_table.items():
        if len(group) < 2:
            continue
        unscoped = [g["dataset_name"] for g in group if not g.get("source_api")]
        if unscoped:
            offenders[table] = unscoped
    assert not offenders, (
        "shared tables with an unscoped product (would double-count): " + repr(offenders)
    )


def test_nadac_scopes_by_real_source_api_not_source_type_value():
    """Regression guard for the one source whose stored source_api ('cms_nadac')
    differs from its SourceType.value ('nadac'). Scoping by 'nadac' would zero it."""
    from integration.dataset_catalog import build_dataset_definitions

    nadac = [d for d in build_dataset_definitions() if d["source_type"] == "nadac"]
    assert nadac, "nadac must be a catalog product"
    assert nadac[0].get("source_api") == "cms_nadac", (
        f"nadac must scope by the real source_api 'cms_nadac', got "
        f"{nadac[0].get('source_api')!r}"
    )


# ── behavioral: _refresh_entry actually applies the source_api predicate ──

class _CaptureDB:
    """Fake DB that records every (sql, params) and returns benign shapes.

    columns: which columns _table_has_column should report as existing.
    """

    def __init__(self, columns=("source_api", "retrieved_at")):
        self.columns = set(columns)
        self.queries: list[tuple[str, object]] = []

    def fetch_one(self, sql, params=None):
        self.queries.append((sql, params))
        s = sql.lower()
        if "information_schema.columns" in s and "column_name = %s" in s:
            col = params[1] if params and len(params) > 1 else None
            return {"ok": 1} if col in self.columns else None
        if "count(*) as c" in s:
            return {"c": 7}
        if "avg(quality_score)" in s:
            return {"avg_q": None, "assessed": 0}
        if "avg(extract" in s:
            return {"avg_days": 2.0}
        if "from etl_runs" in s:
            return None
        return {}

    def fetch_all(self, sql, params=None):
        self.queries.append((sql, params))
        s = sql.lower()
        if "information_schema.columns" in s:
            return []  # no key columns -> completeness short-circuits
        if "group by source_api" in s:
            return [{"source_api": "pubchem", "c": 7}]
        return []

    def execute(self, sql, params=None):
        self.queries.append((sql, params))

    # convenience
    def row_count_queries(self, table):
        return [
            (sql, p) for (sql, p) in self.queries
            if f"count(*) as c from {table}" in sql.lower()
        ]


def _scoped_defn():
    return {
        "dataset_name": "pubchem.compounds", "source_type": "pubchem",
        "entity_type": "drug", "table_name": "drugs", "description": "x",
        "source_api": "pubchem",
    }


def _unscoped_defn():
    return {
        "dataset_name": "pubmed.articles", "source_type": "pubmed",
        "entity_type": "literature", "table_name": "pubmed_articles",
        "description": "x",
    }


def test_refresh_entry_scopes_row_count_when_source_api_declared():
    from integration.dataset_catalog import DatasetCatalog

    db = _CaptureDB(columns=("source_api",))
    DatasetCatalog(db, config=None)._refresh_entry(_scoped_defn())

    rc = db.row_count_queries("drugs")
    assert rc, "expected a row-count query against drugs"
    sql, params = rc[0]
    assert "where source_api = %s" in sql.lower(), f"row count not scoped: {sql}"
    assert params == ["pubchem"], f"wrong scope param: {params}"


def test_refresh_entry_does_not_scope_without_source_api():
    from integration.dataset_catalog import DatasetCatalog

    db = _CaptureDB(columns=("source_api", "retrieved_at"))
    DatasetCatalog(db, config=None)._refresh_entry(_unscoped_defn())

    rc = db.row_count_queries("pubmed_articles")
    assert rc, "expected a row-count query against pubmed_articles"
    sql, params = rc[0]
    assert "source_api" not in sql.lower(), (
        f"unscoped product must not filter by source_api: {sql}"
    )
