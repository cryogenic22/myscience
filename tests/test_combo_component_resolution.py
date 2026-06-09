"""Tests for combo-component drug resolution (Loop 2: resolve-at-ingest hardening).

A drug searched by its mono component name (e.g. "sacubitril") or by a reordered
combo name (e.g. "sacubitril and valsartan") must resolve to the richest active
combo drug row that contains it (e.g. "valsartan/sacubitril", Entresto) instead of
silently orphaning the record.

This is the failure mode that left 93 legacy FAERS/label rows with NULL drug_id on
prod: the openFDA connectors search by mono generic_name, but the drug only exists
as combo rows, and trigram fuzzy cannot bridge "sacubitril" -> "valsartan/sacubitril".

All DB calls are mocked — no external dependencies.
Run with: pytest tests/test_combo_component_resolution.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from connectors.base import Provenance, RawRecord, RecordType, SourceType
from integration.entity_resolver import EntityResolver
from integration.normalizer import NormalizedRecord

from tests.test_entity_resolver_cascade import MockResolverDB, _make_config


# Candidate combo rows the DB returns for an ILIKE '%sacubitril%' combo prefilter.
# The richest active combo (valsartan/sacubitril, Entresto) must win.
_SACUBITRIL_COMBOS = [
    {"id": "rich-entresto", "generic_name": "valsartan/sacubitril", "richness": 227},
    {"id": "thin-entresto", "generic_name": "sacubitril/valsartan", "richness": 11},
    {"id": "allisartan", "generic_name": "sacubitril/allisartan", "richness": 4},
]


def _resolver(db) -> EntityResolver:
    return EntityResolver(db=db, config=_make_config(), openai_client=None)


def _record(generic_name: str, source: SourceType = SourceType.OPENFDA_FAERS) -> NormalizedRecord:
    prov = Provenance(
        source_type=source,
        api_endpoint="https://api.fda.gov/drug/event.json",
        query_params={},
        retrieved_at=None,
        raw_response_hash="h",
    )
    raw = RawRecord(
        record_type=RecordType.ADVERSE_EVENT,
        external_id="RPT-1",
        source_name="FDA FAERS (openFDA)",
        provenance=prov,
        data={"drug_name": generic_name},
        text_content="ae",
        identifiers={"generic_name": generic_name},
    )
    return NormalizedRecord(
        raw=raw,
        canonical_data={"drug_name": generic_name},
        identifiers={"generic_name": generic_name},
    )


# ============================================================
# _combo_component_lookup — the new fallback
# ============================================================

def test_mono_component_resolves_to_richest_combo():
    """'sacubitril' (mono, no own drug row) -> richest combo containing it."""
    db = MockResolverDB()
    db.add_fetch_all("richness", _SACUBITRIL_COMBOS)
    link = _resolver(db)._combo_component_lookup("generic_name", "sacubitril")
    assert link is not None
    assert link.entity_id == "rich-entresto"
    assert link.entity_type == "drug"
    assert link.matched_via == "combo_component"


def test_reordered_combo_name_resolves():
    """'sacubitril and valsartan' (combo, reordered/diff delimiter) -> same combo row."""
    db = MockResolverDB()
    db.add_fetch_all("richness", _SACUBITRIL_COMBOS)
    link = _resolver(db)._combo_component_lookup("generic_name", "sacubitril and valsartan")
    assert link is not None
    assert link.entity_id == "rich-entresto"


def test_value_not_a_subset_returns_none():
    """A value whose components are NOT all present in any candidate -> no match."""
    db = MockResolverDB()
    # candidates contain sacubitril/valsartan; querying an unrelated combo component set
    db.add_fetch_all("richness", _SACUBITRIL_COMBOS)
    link = _resolver(db)._combo_component_lookup("generic_name", "metformin and empagliflozin")
    assert link is None


def test_lone_component_with_existing_mono_row_does_not_combo_link():
    """Defense-in-depth: a bare mono name that HAS its own drug row must NOT be
    linked to a combo via single-element subset match (the metformin hazard)."""
    db = MockResolverDB()
    db.add_fetch_one("from drugs", {"?column?": 1})  # a standalone mono row exists
    db.add_fetch_all("richness", [
        {"id": "metformin-combo", "generic_name": "metformin/sitagliptin", "richness": 99},
    ])
    link = _resolver(db)._combo_component_lookup("generic_name", "metformin")
    assert link is None


def test_lone_component_without_mono_row_still_combo_links():
    """sacubitril (no standalone mono row -> fetch_one None) still resolves."""
    db = MockResolverDB()  # fetch_one default None == no mono row
    db.add_fetch_all("richness", _SACUBITRIL_COMBOS)
    link = _resolver(db)._combo_component_lookup("generic_name", "sacubitril")
    assert link is not None
    assert link.entity_id == "rich-entresto"


def test_brand_name_id_key_ignored():
    db = MockResolverDB()
    db.add_fetch_all("richness", _SACUBITRIL_COMBOS)
    assert _resolver(db)._combo_component_lookup("brand_name", "entresto") is None


def test_no_candidate_combos_returns_none():
    db = MockResolverDB()
    db.add_fetch_all("richness", [])
    link = _resolver(db)._combo_component_lookup("generic_name", "sacubitril")
    assert link is None


def test_non_drug_id_key_ignored():
    db = MockResolverDB()
    db.add_fetch_all("richness", _SACUBITRIL_COMBOS)
    assert _resolver(db)._combo_component_lookup("company_name", "sacubitril") is None


def test_too_short_value_ignored():
    db = MockResolverDB()
    db.add_fetch_all("richness", _SACUBITRIL_COMBOS)
    assert _resolver(db)._combo_component_lookup("generic_name", "ab") is None


# ============================================================
# resolve_drug_mention — DB-only cascade for backfills
# ============================================================

def test_resolve_drug_mention_prefers_fuzzy_mono_over_combo():
    """If a mono drug row exists (fuzzy hit), combo fallback must NOT fire."""
    db = MockResolverDB()
    # fuzzy returns a strong mono match for 'valsartan'
    db.add_fetch_all(
        "similarity",
        [{"id": "mono-valsartan", "name": "valsartan", "sim": 1.0}],
    )
    db.add_fetch_all("richness", _SACUBITRIL_COMBOS)  # would match if reached
    link = _resolver(db).resolve_drug_mention("valsartan", SourceType.OPENFDA_FAERS)
    assert link is not None
    assert link.entity_id == "mono-valsartan"
    assert link.matched_via == "fuzzy"


def test_resolve_drug_mention_falls_through_to_combo():
    """No alias, no fuzzy mono -> combo-component fallback resolves it."""
    db = MockResolverDB()
    # alias miss (fetch_one default None), fuzzy miss (no 'similarity' route -> [])
    db.add_fetch_all("richness", _SACUBITRIL_COMBOS)
    link = _resolver(db).resolve_drug_mention("sacubitril", SourceType.OPENFDA_FAERS)
    assert link is not None
    assert link.entity_id == "rich-entresto"
    assert link.matched_via == "combo_component"


def test_resolve_drug_mention_unresolved_returns_none():
    db = MockResolverDB()
    db.add_fetch_all("richness", [])
    link = _resolver(db).resolve_drug_mention("nonexistentdrug", SourceType.OPENFDA_FAERS)
    assert link is None


# ============================================================
# combo-component wired into the ingest cascade
# ============================================================

def test_combo_component_wired_into_resolve_for_faers():
    """resolve() on a FAERS record for 'sacubitril' resolves via combo fallback."""
    db = MockResolverDB()
    db.add_fetch_all("richness", _SACUBITRIL_COMBOS)
    resolved = _resolver(db).resolve(_record("sacubitril"))
    link = resolved.resolved_links.get("generic_name")
    assert link is not None
    assert link.entity_id == "rich-entresto"
    assert link.matched_via == "combo_component"
