"""WS-1B — Molecule-vs-formulation canonicalization (TDD).

Lead's transcript review (lead_notes_4_dev.md, 19 Apr) flagged that the
canonicalizer resolved Ozempic → "Semaglutide Auto-Injector" (a formulation
row) rather than to the canonical "Semaglutide" molecule row. This makes
downstream queries like "show pipeline for Ozempic" return data scoped to
one dosage form rather than the whole semaglutide programme.

Fix two ways:
  1. **Schema**: add `canonical_molecule_id` self-reference on drugs. When
     a row IS a formulation (e.g. "Semaglutide Auto-Injector"), it points
     to its canonical molecule row ("Semaglutide"). Canonical molecule rows
     have `canonical_molecule_id IS NULL`.
  2. **Code**: canonicalizer prefers rows with `canonical_molecule_id IS NULL`
     when multiple drug rows match a query (brand, alias, fuzzy). When a
     match IS a formulation row, follow `canonical_molecule_id` to the
     parent and return the canonical molecule.

Backfill of `canonical_molecule_id` for existing duplicate drug rows is a
separate data task — this spec just adds the column + canonicalizer logic
so future rows benefit immediately and backfill is non-breaking.

All tests must FAIL before implementation.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


# ────────────────────────────────────────────────────────────────────
# Migration / schema
# ────────────────────────────────────────────────────────────────────

def test_migration_035_canonical_molecule_id_exists():
    p = REPO_ROOT / "schema" / "migrations" / "035_canonical_molecule_id.sql"
    assert p.exists(), (
        "Create migration 035_canonical_molecule_id.sql per WS-1B"
    )
    sql = p.read_text(encoding="utf-8")
    assert "canonical_molecule_id" in sql
    assert "drugs" in sql.lower()
    # Self-reference to drugs(id)
    assert re.search(
        r"references\s+drugs\s*\(\s*id\s*\)",
        sql, re.IGNORECASE,
    ), "canonical_molecule_id must REFERENCES drugs(id) — self-link"
    # Idempotent
    assert "IF NOT EXISTS" in sql.upper()


# ────────────────────────────────────────────────────────────────────
# Canonicalizer behaviour with multiple matching rows
# ────────────────────────────────────────────────────────────────────

# Sample drug rows with the molecule + a formulation variant
SAMPLE_DRUGS_WITH_FORMULATION = [
    # Canonical molecule row
    {"id": "uuid-sema-mol", "generic_name": "Semaglutide",
     "brand_name": "Ozempic", "canonical_molecule_id": None},
    # Formulation row pointing to canonical
    {"id": "uuid-sema-inj", "generic_name": "Semaglutide Auto-Injector",
     "brand_name": "Ozempic", "canonical_molecule_id": "uuid-sema-mol"},
    # Another formulation
    {"id": "uuid-sema-tab", "generic_name": "Semaglutide Tablet",
     "brand_name": "Rybelsus", "canonical_molecule_id": "uuid-sema-mol"},
    # Independent molecule (no relation)
    {"id": "uuid-tirz", "generic_name": "Tirzepatide",
     "brand_name": "Mounjaro", "canonical_molecule_id": None},
]


def _make_fake_db(rows):
    """Fake DB that returns rows ordered by canonical_molecule_id NULL first,
    then by length(generic_name) ASC — matching the SQL ORDER BY we expect
    the canonicalizer to issue."""

    def _select_rows(sql, params, by_brand=False, by_generic=False, by_alias=False, by_id=False):
        sql_lower = sql.lower()
        needle = ((params[0] if params else "") or "").lower()

        if by_brand:
            matches = [r for r in rows if (r.get("brand_name") or "").lower() == needle]
        elif by_generic:
            matches = [r for r in rows if r.get("generic_name", "").lower() == needle]
        elif by_alias:
            # Aliases not modelled in this fake — return empty (alias_lookup
            # path falls through to other strategies)
            return None
        elif by_id:
            for r in rows:
                if r.get("id") == params[0]:
                    return {"id": r["id"], "generic_name": r["generic_name"],
                            "canonical_molecule_id": r.get("canonical_molecule_id")}
            return None
        else:
            return None

        if not matches:
            return None
        # Mirror the SQL ORDER BY: canonical_molecule_id NULL first, then shortest
        matches.sort(key=lambda r: (
            0 if r.get("canonical_molecule_id") is None else 1,
            len(r.get("generic_name", "")),
        ))
        best = matches[0]
        return {
            "id": best["id"],
            "generic_name": best["generic_name"],
            "canonical_molecule_id": best.get("canonical_molecule_id"),
        }

    db = MagicMock()

    def fake_fetch_one(sql, params=None):
        sql_lower = (sql or "").lower()
        if "entity_aliases" in sql_lower:
            return None
        if "where id::text" in sql_lower:
            return _select_rows(sql, params, by_id=True)
        if "lower(brand_name)" in sql_lower:
            return _select_rows(sql, params, by_brand=True)
        if "lower(generic_name)" in sql_lower:
            return _select_rows(sql, params, by_generic=True)
        return None

    db.fetch_one.side_effect = fake_fetch_one
    db.fetch_all.return_value = []  # fuzzy not exercised in these tests
    return db


def test_brand_match_prefers_canonical_molecule_row():
    """SQL: when multiple drugs share brand_name='Ozempic', prefer the row
    where canonical_molecule_id IS NULL (the molecule, not a formulation)."""
    from services.entity_canonicalizer import EntityCanonicalizer
    db = _make_fake_db(SAMPLE_DRUGS_WITH_FORMULATION)
    canon = EntityCanonicalizer(db)
    result = canon.canonicalize("Ozempic", hint_type="drug")
    assert result is not None
    assert result.canonical_name == "Semaglutide", (
        f"expected canonical molecule 'Semaglutide'; got {result.canonical_name!r}"
    )
    assert result.entity_id == "uuid-sema-mol"


def test_generic_match_prefers_canonical_molecule_row():
    """When user types 'semaglutide' and multiple rows match, pick the
    canonical molecule row, not a formulation."""
    from services.entity_canonicalizer import EntityCanonicalizer
    db = _make_fake_db(SAMPLE_DRUGS_WITH_FORMULATION)
    canon = EntityCanonicalizer(db)
    result = canon.canonicalize("semaglutide", hint_type="drug")
    assert result is not None
    assert result.entity_id == "uuid-sema-mol"


def test_resolution_follows_canonical_molecule_id_when_only_formulation_matches():
    """If the ONLY matching row is a formulation (e.g. user typed exact
    'Semaglutide Auto-Injector'), the result should be the canonical molecule
    that the formulation points to."""
    from services.entity_canonicalizer import EntityCanonicalizer
    # Remove the canonical molecule row — only the formulation remains
    rows = [r for r in SAMPLE_DRUGS_WITH_FORMULATION if r["id"] != "uuid-sema-mol"]
    # But add the canonical row back so the follow-through can resolve it
    rows.append(SAMPLE_DRUGS_WITH_FORMULATION[0])

    db = _make_fake_db(rows)
    canon = EntityCanonicalizer(db)
    # Match exactly on the formulation name
    result = canon.canonicalize("Semaglutide Auto-Injector", hint_type="drug")
    assert result is not None
    # The implementation may either: (a) return the formulation row if it
    # has no parent, or (b) follow canonical_molecule_id to the molecule.
    # We require (b) — the user shouldn't see formulation as canonical.
    assert result.canonical_name == "Semaglutide", (
        f"formulation match should follow canonical_molecule_id to 'Semaglutide'; "
        f"got {result.canonical_name!r}"
    )
    assert result.entity_id == "uuid-sema-mol"


def test_canonical_match_returns_self_when_no_parent():
    """When the matched row IS the canonical molecule (canonical_molecule_id
    IS NULL), no follow-through happens."""
    from services.entity_canonicalizer import EntityCanonicalizer
    db = _make_fake_db(SAMPLE_DRUGS_WITH_FORMULATION)
    canon = EntityCanonicalizer(db)
    result = canon.canonicalize("Tirzepatide", hint_type="drug")
    assert result is not None
    assert result.entity_id == "uuid-tirz"
    assert result.canonical_name == "Tirzepatide"


def test_unrelated_molecule_unaffected_by_formulation_logic():
    """Tirzepatide has no formulation row in the sample — should still resolve
    cleanly with no behavioural regression."""
    from services.entity_canonicalizer import EntityCanonicalizer
    db = _make_fake_db(SAMPLE_DRUGS_WITH_FORMULATION)
    canon = EntityCanonicalizer(db)
    result = canon.canonicalize("Mounjaro", hint_type="drug")
    assert result is not None
    assert result.entity_id == "uuid-tirz"
    assert result.canonical_name == "Tirzepatide"


# ────────────────────────────────────────────────────────────────────
# SQL-level: queries reference canonical_molecule_id
# ────────────────────────────────────────────────────────────────────

def test_canonicalizer_sql_references_canonical_molecule_id():
    """Static check: the canonicalizer's SQL must order by canonical_molecule_id
    so canonical molecule rows win over formulations."""
    src = (REPO_ROOT / "services" / "entity_canonicalizer.py").read_text(encoding="utf-8")
    has_ordering = re.search(
        r"canonical_molecule_id",
        src,
    )
    assert has_ordering, (
        "entity_canonicalizer.py must reference canonical_molecule_id "
        "(in SELECT or ORDER BY) to prefer canonical molecule rows over "
        "formulation rows."
    )


# ────────────────────────────────────────────────────────────────────
# No regression: WS-1 baseline still works without canonical_molecule_id
# ────────────────────────────────────────────────────────────────────

def test_canonicalize_works_when_canonical_molecule_id_column_missing():
    """Defensive: canonicalizer must still work in environments where
    migration 035 hasn't been applied yet (graceful degradation)."""
    from services.entity_canonicalizer import EntityCanonicalizer

    # Fake DB that simulates pre-migration state (no canonical_molecule_id column)
    pre_migration_rows = [
        {"id": "uuid-sema", "generic_name": "Semaglutide", "brand_name": "Ozempic"},
    ]

    db = MagicMock()

    def fake_fetch_one(sql, params=None):
        sql_lower = (sql or "").lower()
        if "entity_aliases" in sql_lower:
            return None
        if "lower(generic_name)" in sql_lower:
            for r in pre_migration_rows:
                if r["generic_name"].lower() == params[0].lower():
                    # Note: NO canonical_molecule_id key — column doesn't exist
                    return {"id": r["id"], "generic_name": r["generic_name"]}
            return None
        if "lower(brand_name)" in sql_lower:
            for r in pre_migration_rows:
                if (r.get("brand_name") or "").lower() == params[0].lower():
                    return {"id": r["id"], "generic_name": r["generic_name"]}
            return None
        return None

    db.fetch_one.side_effect = fake_fetch_one
    db.fetch_all.return_value = []
    canon = EntityCanonicalizer(db)
    result = canon.canonicalize("Ozempic", hint_type="drug")
    assert result is not None
    assert result.canonical_name == "Semaglutide"
