"""BE-38 — tenant isolation middleware tests.

Covers the contextvar plumbing, the SQL fragment helper, and the
HybridSearch._build_where_clause + GraphTraversal._resolve_labels
integrations. Cross-tenant zero-leak tests against real query
shapes ship in BE-39.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ════════════════════════════════════════════════════════════════════
# Tenant context
# ════════════════════════════════════════════════════════════════════

class TestTenantContext:
    def test_default_is_public(self):
        from services.tenant_context import get_current_tenant
        # No setter has been called in this test → default
        assert get_current_tenant() == "public"

    def test_with_tenant_scoped(self):
        from services.tenant_context import get_current_tenant, with_tenant
        with with_tenant("pfizer"):
            assert get_current_tenant() == "pfizer"
        # Reset on exit
        assert get_current_tenant() == "public"

    def test_with_tenant_nested(self):
        from services.tenant_context import get_current_tenant, with_tenant
        with with_tenant("pfizer"):
            with with_tenant("roche"):
                assert get_current_tenant() == "roche"
            # Outer scope restored
            assert get_current_tenant() == "pfizer"
        assert get_current_tenant() == "public"

    def test_blank_tenant_falls_back_to_public(self):
        from services.tenant_context import get_current_tenant, with_tenant
        with with_tenant(""):
            assert get_current_tenant() == "public"
        with with_tenant("   "):
            assert get_current_tenant() == "public"

    def test_tables_with_tenant_set(self):
        from services.tenant_context import TABLES_WITH_TENANT
        # Must match exactly what BE-37 added the column to.
        assert TABLES_WITH_TENANT == frozenset({
            "drugs", "companies", "clinical_trials", "mechanisms_of_action"
        })


class TestTenantFilterClause:
    def test_public_tenant_returns_only_public(self):
        from services.tenant_context import tenant_filter_clause
        clause, params = tenant_filter_clause()
        assert "tenant_id = ANY(%s)" in clause
        assert params == [["public"]]

    def test_named_tenant_returns_public_plus_tenant(self):
        from services.tenant_context import tenant_filter_clause
        clause, params = tenant_filter_clause(tenant="pfizer")
        # Public stays visible from every tenant — that's intentional
        # so the shared knowledge base never disappears for a customer.
        assert clause == "tenant_id = ANY(%s)"
        assert params == [["public", "pfizer"]]

    def test_table_alias_qualifies_column(self):
        from services.tenant_context import tenant_filter_clause
        clause, _ = tenant_filter_clause(table_alias="d", tenant="pfizer")
        assert clause == "d.tenant_id = ANY(%s)"

    def test_uses_contextvar_when_no_explicit_tenant(self):
        from services.tenant_context import tenant_filter_clause, with_tenant
        with with_tenant("roche"):
            _, params = tenant_filter_clause()
        assert params == [["public", "roche"]]


# ════════════════════════════════════════════════════════════════════
# HybridSearch._build_where_clause integration
# ════════════════════════════════════════════════════════════════════

class TestSearchTenantFilter:
    def _hybrid(self, db):
        from services.search import HybridSearch
        cfg = MagicMock()
        return HybridSearch(db, cfg)

    def test_drug_search_appends_tenant_filter(self):
        from services.search import ENTITY_SEARCH_CONFIG, HybridSearch
        from services.tenant_context import with_tenant

        db = MagicMock()
        s = HybridSearch(db, MagicMock())

        with with_tenant("pfizer"):
            where, params = s._build_where_clause(
                entity_type="drug",
                cfg=ENTITY_SEARCH_CONFIG["drug"],
                filters=None, date_range=None, source_types=None,
            )

        assert "tenant_id = ANY(%s)" in where
        # The list of allowed tenants should include both public and pfizer
        tenant_param = next(p for p in params if isinstance(p, list)
                            and "public" in p)
        assert "public" in tenant_param
        assert "pfizer" in tenant_param

    def test_company_and_trial_also_get_tenant_filter(self):
        from services.search import ENTITY_SEARCH_CONFIG, HybridSearch
        from services.tenant_context import with_tenant

        db = MagicMock()
        s = HybridSearch(db, MagicMock())

        with with_tenant("roche"):
            for et in ("company", "trial"):
                where, _ = s._build_where_clause(
                    entity_type=et,
                    cfg=ENTITY_SEARCH_CONFIG[et],
                    filters=None, date_range=None, source_types=None,
                )
                assert "tenant_id = ANY(%s)" in where, f"{et} missing tenant filter"

    def test_literature_does_not_get_tenant_filter(self):
        """pubmed_articles has no tenant_id (BE-37 only added it to four
        tables). Filtering by it would crash the query."""
        from services.search import ENTITY_SEARCH_CONFIG, HybridSearch
        from services.tenant_context import with_tenant

        db = MagicMock()
        s = HybridSearch(db, MagicMock())

        with with_tenant("pfizer"):
            where, _ = s._build_where_clause(
                entity_type="literature",
                cfg=ENTITY_SEARCH_CONFIG["literature"],
                filters=None, date_range=None, source_types=None,
            )

        assert "tenant_id" not in where, (
            "literature must NOT get a tenant filter — its table has no such column"
        )

    def test_event_does_not_get_tenant_filter(self):
        from services.search import ENTITY_SEARCH_CONFIG, HybridSearch
        from services.tenant_context import with_tenant

        db = MagicMock()
        s = HybridSearch(db, MagicMock())

        with with_tenant("pfizer"):
            where, _ = s._build_where_clause(
                entity_type="event",
                cfg=ENTITY_SEARCH_CONFIG["event"],
                filters=None, date_range=None, source_types=None,
            )

        assert "tenant_id" not in where


# ════════════════════════════════════════════════════════════════════
# GraphTraversal._resolve_labels integration
# ════════════════════════════════════════════════════════════════════

class TestGraphTenantFilter:
    def _make_db(self, *, label_rows, drug_tenants):
        """label_rows: list of {entity_id, entity_type, label} from
        v_entity_labels. drug_tenants: id → tenant_id mapping."""
        db = MagicMock()

        def fake_fetch_all(sql, params=None):
            s = (sql or "").lower()
            if "v_entity_labels" in s:
                return label_rows
            if "select id::text as id, tenant_id from drugs" in s:
                ids_in = params[0] if params else []
                return [
                    {"id": k, "tenant_id": v}
                    for k, v in drug_tenants.items() if k in ids_in
                ]
            return []

        db.fetch_all.side_effect = fake_fetch_all
        return db

    def test_blocks_other_tenants_drug_node(self):
        from services.graph import GraphTraversal
        from services.tenant_context import with_tenant

        db = self._make_db(
            label_rows=[
                {"entity_id": "drug-a", "entity_type": "drug", "label": "Drug A (public)"},
                {"entity_id": "drug-b", "entity_type": "drug", "label": "Drug B (pfizer-only)"},
            ],
            drug_tenants={"drug-a": "public", "drug-b": "pfizer"},
        )
        g = GraphTraversal(db, MagicMock())

        # Active tenant: roche → should NOT see drug-b
        with with_tenant("roche"):
            nodes = g._resolve_labels({"drug-a", "drug-b"})

        # drug-a survives with its label; drug-b is reduced to 'unknown'
        # (no row in the now-filtered label_map → fallback branch)
        labels_by_id = {n.entity_id: n for n in nodes}
        assert "Drug A" in labels_by_id["drug-a"].label
        assert labels_by_id["drug-b"].entity_type == "unknown"

    def test_allows_active_tenant_node(self):
        from services.graph import GraphTraversal
        from services.tenant_context import with_tenant

        db = self._make_db(
            label_rows=[
                {"entity_id": "drug-c", "entity_type": "drug", "label": "Drug C (pfizer)"},
            ],
            drug_tenants={"drug-c": "pfizer"},
        )
        g = GraphTraversal(db, MagicMock())

        with with_tenant("pfizer"):
            nodes = g._resolve_labels({"drug-c"})

        assert nodes[0].label.startswith("Drug C")

    def test_public_tenant_only_sees_public(self):
        from services.graph import GraphTraversal
        from services.tenant_context import with_tenant

        db = self._make_db(
            label_rows=[
                {"entity_id": "drug-pub", "entity_type": "drug", "label": "Public Drug"},
                {"entity_id": "drug-priv", "entity_type": "drug", "label": "Private"},
            ],
            drug_tenants={"drug-pub": "public", "drug-priv": "pfizer"},
        )
        g = GraphTraversal(db, MagicMock())

        with with_tenant("public"):
            nodes = g._resolve_labels({"drug-pub", "drug-priv"})

        labels_by_id = {n.entity_id: n for n in nodes}
        assert labels_by_id["drug-pub"].label == "Public Drug"
        assert labels_by_id["drug-priv"].entity_type == "unknown"
