"""WS-1 (SPEC_015) — Entity Canonicalisation TDD test contract.

Tests the EntityCanonicalizer service + downstream consumers (resolve_entity,
fuzzy_match for brand_name, alias seed migration). All must FAIL before
implementation per TDD discipline.

Categories:
1. Static checks — module/class existence, migration file presence
2. EntityCanonicalizer unit tests — pure logic, mocked DB
3. Live DB tests — require DATABASE_URL; auto-skip otherwise
4. Integration — chat route, formatting.resolve_entity, fuzzy resolver
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────

def _can_connect_to_db() -> bool:
    try:
        from db import Database
        from config import config
        d = Database(config.db.dsn)
        d.connect()
        d.close()
        return True
    except Exception:
        return False


db_required = pytest.mark.skipif(
    not _can_connect_to_db(),
    reason="No reachable database — skipping live DB checks",
)


@pytest.fixture(scope="module")
def db():
    if not _can_connect_to_db():
        pytest.skip("No reachable database")
    from db import Database
    from config import config
    d = Database(config.db.dsn)
    d.connect()
    yield d
    d.close()


# ────────────────────────────────────────────────────────────────────
# Category 1: Static existence checks
# ────────────────────────────────────────────────────────────────────

def test_entity_canonicalizer_module_exists():
    """SPEC_015 §3.3.2: services/entity_canonicalizer.py must exist."""
    p = REPO_ROOT / "services" / "entity_canonicalizer.py"
    assert p.exists(), "Create services/entity_canonicalizer.py per SPEC_015 §3.3.2"


def test_canonical_result_dataclass_exists():
    from services.entity_canonicalizer import CanonicalResult
    # Must be a frozen dataclass with required fields
    fields = {f for f in CanonicalResult.__dataclass_fields__}
    required = {"entity_id", "canonical_name", "entity_type",
                "confidence", "method", "original_input"}
    assert required.issubset(fields), f"missing fields: {required - fields}"


def test_entity_canonicalizer_class_exists():
    from services.entity_canonicalizer import EntityCanonicalizer
    # Must expose canonicalize and canonicalize_batch
    assert hasattr(EntityCanonicalizer, "canonicalize")
    assert hasattr(EntityCanonicalizer, "canonicalize_batch")


def test_migration_033_seed_brand_aliases_exists():
    p = REPO_ROOT / "schema" / "migrations" / "033_seed_brand_aliases.sql"
    assert p.exists(), (
        "Create migration 033_seed_brand_aliases.sql per SPEC_015 §3.3.1. "
        "(Migration 032 is taken — used 033.)"
    )
    sql = p.read_text(encoding="utf-8")
    assert "entity_aliases" in sql.lower()
    assert "brand_name" in sql.lower()
    # Must be idempotent
    assert "ON CONFLICT" in sql.upper() or "IF NOT EXISTS" in sql.upper()


def test_get_entity_canonicalizer_dep_exists():
    """SPEC_015 §3.3.3: api/deps.py must expose get_entity_canonicalizer."""
    src = (REPO_ROOT / "api" / "deps.py").read_text(encoding="utf-8")
    assert re.search(r"def\s+get_entity_canonicalizer\s*\(", src), (
        "api/deps.py must define get_entity_canonicalizer()"
    )


def test_pack_drug_fuzzy_match_includes_brand_name():
    """SPEC_015 §3.3.6: pack.py drug schema must add brand_name to fuzzy_match_fields."""
    src = (REPO_ROOT / "domain" / "pharma" / "pack.py").read_text(encoding="utf-8")
    # Find the drug EntitySchema fuzzy_match_fields block
    drug_block_match = re.search(
        r"name=\"drug\"[\s\S]+?fuzzy_match_fields\s*=\s*\{([^}]+)\}",
        src,
    )
    assert drug_block_match, "could not find drug schema fuzzy_match_fields"
    fuzzy_block = drug_block_match.group(1)
    assert "brand_name" in fuzzy_block, (
        "drug schema fuzzy_match_fields must include 'brand_name'"
    )


def test_entity_resolver_fuzzy_fields_include_brand_name():
    """SPEC_015 §3.3.5: integration/entity_resolver.py FUZZY_MATCH_FIELDS
    must include 'brand_name' entry."""
    src = (REPO_ROOT / "integration" / "entity_resolver.py").read_text(encoding="utf-8")
    # Look for "brand_name" inside FUZZY_MATCH_FIELDS dict
    fields_match = re.search(
        r"FUZZY_MATCH_FIELDS[\s\S]+?\{([\s\S]+?)\}",
        src,
    )
    assert fields_match
    block = fields_match.group(1)
    assert "brand_name" in block, (
        "FUZZY_MATCH_FIELDS must include 'brand_name' entry"
    )


def test_resolve_entity_searches_brand_name():
    """SPEC_015 §3.3.4: formatting.resolve_entity must search drugs.brand_name."""
    src = (REPO_ROOT / "services" / "chat_handlers" / "formatting.py").read_text(encoding="utf-8")
    # Look for brand_name in the table_map for drug
    has_brand = re.search(
        r"\"drug\"[\s\S]{0,400}brand_name",
        src,
    )
    assert has_brand, (
        "resolve_entity table_map for 'drug' must include brand_name search path"
    )


# ────────────────────────────────────────────────────────────────────
# Category 2: EntityCanonicalizer unit tests (mocked DB)
# ────────────────────────────────────────────────────────────────────

def _fake_db_with_drugs(rows: list[dict]):
    """Build a minimal fake DB that returns canned rows for fetchers."""
    db = MagicMock()
    db.fetch_one.side_effect = lambda sql, params=None: _select_one(rows, sql, params)
    db.fetch_all.side_effect = lambda sql, params=None: _select_all(rows, sql, params)
    return db


def _select_one(rows, sql, params):
    """Pick first row matching the SQL pattern.

    Distinguishes by the presence of literal column names + LOWER() calls
    in the SQL (case-insensitive). Order matters: brand check before generic
    so the more specific match wins when both clauses are present.
    """
    sql_lower = sql.lower()
    needle = ((params[0] if params else "") or "").lower()

    # alias_lookup
    if "entity_aliases" in sql_lower:
        for r in rows:
            if r.get("alias_text", "").lower() == needle:
                return {"entity_id": r["id"], "alias_text": r["alias_text"]}
        return None

    # alias_lookup → second SQL: SELECT id, generic_name FROM drugs WHERE id::text = %s
    if "where id::text" in sql_lower:
        for r in rows:
            if str(r["id"]) == params[0]:
                return {"id": r["id"], "generic_name": r["generic_name"]}
        return None

    # _exact_brand: SQL contains lower(brand_name) (note: "is not null" may sit between)
    if "lower(brand_name)" in sql_lower:
        for r in rows:
            bn = (r.get("brand_name") or "").lower()
            if bn and bn == needle:
                return {"id": r["id"], "generic_name": r["generic_name"]}
        return None

    # _exact_generic
    if "lower(generic_name)" in sql_lower:
        for r in rows:
            if r.get("generic_name", "").lower() == needle:
                return {"id": r["id"], "generic_name": r["generic_name"]}
        return None

    return None


def _select_all(rows, sql, params):
    """Fuzzy similarity queries return ranked matches above threshold."""
    sql_lower = sql.lower()
    needle = ((params[0] if params else "") or "").lower()

    if "similarity" not in sql_lower:
        return []

    # Brand fuzzy uses similarity(LOWER(brand_name), ...)
    if "brand_name" in sql_lower and "lower(brand_name)" in sql_lower:
        out = []
        for r in rows:
            bn = (r.get("brand_name") or "").lower()
            if not bn:
                continue
            sim = _trigram_sim(needle, bn)
            if sim > 0.4:
                out.append({"id": r["id"], "generic_name": r["generic_name"], "sim": sim})
        return sorted(out, key=lambda x: -x["sim"])

    # Generic fuzzy uses similarity(LOWER(generic_name), ...)
    if "generic_name" in sql_lower and "lower(generic_name)" in sql_lower:
        out = []
        for r in rows:
            gn = r.get("generic_name", "").lower()
            sim = _trigram_sim(needle, gn)
            if sim > 0.4:
                out.append({"id": r["id"], "generic_name": r["generic_name"], "sim": sim})
        return sorted(out, key=lambda x: -x["sim"])

    return []


def _trigram_sim(a: str, b: str) -> float:
    """Cheap trigram similarity for tests (not pg_trgm exact, just monotonic)."""
    if not a or not b:
        return 0.0
    a3 = {a[i:i+3] for i in range(len(a) - 2)} if len(a) >= 3 else {a}
    b3 = {b[i:i+3] for i in range(len(b) - 2)} if len(b) >= 3 else {b}
    if not a3 or not b3:
        return 0.0
    return len(a3 & b3) / len(a3 | b3)


SAMPLE_DRUGS = [
    {"id": "uuid-sema", "generic_name": "semaglutide", "brand_name": "Ozempic"},
    {"id": "uuid-tirz", "generic_name": "tirzepatide", "brand_name": "Mounjaro"},
    {"id": "uuid-empa", "generic_name": "empagliflozin", "brand_name": "Jardiance"},
]


def test_canonicalize_exact_generic_name():
    """SPEC_015 §3.3.2: exact match on generic_name returns canonical."""
    from services.entity_canonicalizer import EntityCanonicalizer
    db = _fake_db_with_drugs(SAMPLE_DRUGS)
    canon = EntityCanonicalizer(db)
    result = canon.canonicalize("semaglutide", hint_type="drug")
    assert result is not None
    assert result.canonical_name == "semaglutide"
    assert result.entity_id == "uuid-sema"
    assert result.confidence == 1.0
    assert result.method == "exact_generic"
    assert result.original_input == "semaglutide"


def test_canonicalize_exact_brand_name_returns_generic_as_canonical():
    """SPEC_015: brand match must return GENERIC name as canonical_name."""
    from services.entity_canonicalizer import EntityCanonicalizer
    db = _fake_db_with_drugs(SAMPLE_DRUGS)
    canon = EntityCanonicalizer(db)
    result = canon.canonicalize("Ozempic", hint_type="drug")
    assert result is not None
    assert result.canonical_name == "semaglutide", (
        "brand match must return generic name (not the brand) as canonical"
    )
    assert result.entity_id == "uuid-sema"
    assert result.method == "exact_brand"


def test_canonicalize_brand_case_insensitive():
    from services.entity_canonicalizer import EntityCanonicalizer
    db = _fake_db_with_drugs(SAMPLE_DRUGS)
    canon = EntityCanonicalizer(db)
    for variant in ("ozempic", "OZEMPIC", "Ozempic", "OzEmPiC"):
        result = canon.canonicalize(variant, hint_type="drug")
        assert result is not None, f"failed to resolve {variant!r}"
        assert result.canonical_name == "semaglutide"


def test_canonicalize_unknown_returns_none():
    """Unknown name must not auto-create — returns None."""
    from services.entity_canonicalizer import EntityCanonicalizer
    db = _fake_db_with_drugs(SAMPLE_DRUGS)
    canon = EntityCanonicalizer(db)
    result = canon.canonicalize("xyznonexistent", hint_type="drug")
    assert result is None


def test_canonicalize_misspelling_via_fuzzy():
    """Misspelling resolves via fuzzy generic match with confidence < 1.0."""
    from services.entity_canonicalizer import EntityCanonicalizer
    db = _fake_db_with_drugs(SAMPLE_DRUGS)
    canon = EntityCanonicalizer(db)
    # "semaglutid" — missing trailing 'e'. Trigram sim ~0.89 vs "semaglutide".
    result = canon.canonicalize("semaglutid", hint_type="drug")
    assert result is not None, "fuzzy match should resolve misspelling"
    assert result.canonical_name == "semaglutide"
    assert result.confidence < 1.0
    assert "fuzzy" in result.method


def test_canonicalize_batch():
    """Batch resolution works on multiple names."""
    from services.entity_canonicalizer import EntityCanonicalizer
    db = _fake_db_with_drugs(SAMPLE_DRUGS)
    canon = EntityCanonicalizer(db)
    results = canon.canonicalize_batch(["Ozempic", "tirzepatide", "xyz"])
    assert isinstance(results, dict)
    assert results["Ozempic"].canonical_name == "semaglutide"
    assert results["tirzepatide"].canonical_name == "tirzepatide"
    assert results["xyz"] is None


def test_canonicalize_cache_hit_avoids_db():
    """Second call for same name uses cache, no second DB query."""
    from services.entity_canonicalizer import EntityCanonicalizer
    db = _fake_db_with_drugs(SAMPLE_DRUGS)
    canon = EntityCanonicalizer(db)
    r1 = canon.canonicalize("Ozempic", hint_type="drug")
    call_count_after_first = db.fetch_one.call_count
    r2 = canon.canonicalize("Ozempic", hint_type="drug")
    call_count_after_second = db.fetch_one.call_count
    assert r1 == r2
    assert call_count_after_second == call_count_after_first, (
        "second call should hit cache, not DB"
    )


def test_canonicalize_empty_or_short_name_returns_none():
    from services.entity_canonicalizer import EntityCanonicalizer
    db = _fake_db_with_drugs(SAMPLE_DRUGS)
    canon = EntityCanonicalizer(db)
    assert canon.canonicalize("", hint_type="drug") is None
    assert canon.canonicalize("a", hint_type="drug") is None


# ────────────────────────────────────────────────────────────────────
# Category 3: resolve_entity (formatting.py) brand fallback
# ────────────────────────────────────────────────────────────────────

def test_resolve_entity_finds_drug_by_brand_name():
    """SPEC_015 §3.3.4: resolve_entity must find a drug when only brand name given.
    Returns the entity with label = generic_name (canonical form)."""
    from services.chat_handlers.formatting import resolve_entity
    db = MagicMock()
    # First call (generic_name lookup) misses
    # Second call (brand_name lookup) hits
    def fetch_one_side_effect(sql, params=None):
        sql_lower = sql.lower()
        if "lower(generic_name)" in sql_lower and params and params[0].lower() == "ozempic":
            return None  # not in generic_name
        if "lower(brand_name)" in sql_lower and params and params[0].lower() == "ozempic":
            return {"entity_id": "uuid-sema", "label": "semaglutide"}
        return None
    db.fetch_one = fetch_one_side_effect
    result = resolve_entity("ozempic", "drug", db)
    assert result is not None, "resolve_entity must find drug by brand_name"
    assert result["label"] == "semaglutide", (
        "label must be canonical generic_name, not the brand"
    )
    assert result["entity_id"] == "uuid-sema"


def test_resolve_entity_still_works_for_generic_name():
    """No regression: existing generic_name path still works."""
    from services.chat_handlers.formatting import resolve_entity
    db = MagicMock()
    def fetch_one_side_effect(sql, params=None):
        sql_lower = sql.lower()
        if "lower(generic_name)" in sql_lower and params and params[0].lower() == "semaglutide":
            return {"entity_id": "uuid-sema", "label": "semaglutide"}
        return None
    db.fetch_one = fetch_one_side_effect
    result = resolve_entity("semaglutide", "drug", db)
    assert result is not None
    assert result["label"] == "semaglutide"


# ────────────────────────────────────────────────────────────────────
# Category 4: Live DB tests (skip if no DB)
# ────────────────────────────────────────────────────────────────────

@db_required
def test_entity_aliases_seeded_after_migration_033(db):
    """After migration 033 runs, entity_aliases must have rows for drugs with brand_name."""
    rows = db.fetch_all(
        "SELECT COUNT(*) AS n FROM entity_aliases WHERE entity_type = 'drug'"
    )
    assert rows and rows[0]["n"] > 0, (
        "entity_aliases must have at least one drug row after migration 033"
    )


@db_required
def test_drugs_with_brand_name_have_alias_entry(db):
    """Every drug with non-null brand_name should have a corresponding alias row."""
    missing = db.fetch_all(
        """
        SELECT d.id, d.generic_name, d.brand_name
        FROM drugs d
        LEFT JOIN entity_aliases a
          ON a.entity_id = d.id
         AND a.entity_type = 'drug'
         AND LOWER(a.alias_text) = LOWER(TRIM(d.brand_name))
        WHERE d.brand_name IS NOT NULL
          AND TRIM(d.brand_name) != ''
          AND LOWER(d.brand_name) != LOWER(d.generic_name)
          AND a.id IS NULL
        LIMIT 10
        """
    )
    assert missing == [], (
        f"drugs with brand_name but no alias entry: {[m['generic_name'] for m in missing]}"
    )


# ────────────────────────────────────────────────────────────────────
# Category 5: chat route wiring
# ────────────────────────────────────────────────────────────────────

def test_chat_route_imports_canonicalizer():
    """SPEC_015 §3.3.3: chat.py must import EntityCanonicalizer or use get_entity_canonicalizer."""
    src = (REPO_ROOT / "api" / "routes" / "chat.py").read_text(encoding="utf-8")
    has_import = (
        "get_entity_canonicalizer" in src
        or "EntityCanonicalizer" in src
        or "_canonicalize_question" in src
    )
    assert has_import, (
        "chat.py must wire in the EntityCanonicalizer (via get_entity_canonicalizer "
        "from api.deps, or _canonicalize_question helper)"
    )


def test_chat_route_canonicalises_before_intent_detection():
    """The canonicalisation call must happen BEFORE detect_intent in the chat handler."""
    src = (REPO_ROOT / "api" / "routes" / "chat.py").read_text(encoding="utf-8")
    # Find the position of detect_intent and the canonicalisation call
    canon_pos = -1
    for marker in ("_canonicalize_question", "canonicalizer.canonicalize", "get_entity_canonicalizer"):
        m = re.search(re.escape(marker), src)
        if m:
            canon_pos = m.start()
            break
    intent_pos = src.find("detect_intent(")
    assert canon_pos != -1, "canonicalisation must be called somewhere in chat.py"
    assert intent_pos != -1, "detect_intent() call expected"
    assert canon_pos < intent_pos, (
        "canonicalisation must happen BEFORE detect_intent so brand names get "
        "replaced before slot extraction"
    )
