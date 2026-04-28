"""A1.2 — drugs schema extension (TDD).

Adds modality classification + canonical drug identifiers (atc, ndc,
unii, chembl, drugbank) to drugs. Companions to the molecular fields
already added in migration 028 (pubchem_cid, smiles, inchi, …).

Tests: migration shape (always run), DB invariants (skip without DB),
modality classifier helper, and the existing schema isn't disturbed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATION = REPO_ROOT / "schema" / "migrations" / "038_drugs_modality_external_ids.sql"


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
    not _can_connect_to_db(), reason="No reachable database",
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
# Cat 1 — migration file
# ────────────────────────────────────────────────────────────────────

def test_migration_038_file_exists():
    assert MIGRATION.exists()


def test_migration_038_adds_modality_with_check():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert re.search(
        r"ALTER\s+TABLE\s+drugs\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+modality\s+TEXT",
        sql, re.IGNORECASE,
    )
    # CHECK constraint with all 10 values + null allowance
    for value in ["small_molecule", "mab", "adc", "bispecific", "gene_therapy",
                  "cell_therapy", "rna", "vaccine", "device", "other"]:
        assert f"'{value}'" in sql, f"modality enum missing value: {value}"


def test_migration_038_adds_array_columns():
    sql = MIGRATION.read_text(encoding="utf-8")
    for col in ("atc_codes", "ndc_codes"):
        assert re.search(
            rf"ALTER\s+TABLE\s+drugs\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+{col}\s+TEXT\[\]",
            sql, re.IGNORECASE,
        ), f"{col} text[] missing"
        assert re.search(
            rf"{col}[\s\S]{{0,80}}DEFAULT\s+'\{{}}'", sql, re.IGNORECASE,
        ) or re.search(
            rf"{col}[\s\S]{{0,80}}DEFAULT\s+ARRAY\[\]::TEXT\[\]", sql, re.IGNORECASE,
        ), f"{col} should default to empty array"


def test_migration_038_adds_external_id_columns():
    sql = MIGRATION.read_text(encoding="utf-8")
    for col in ("unii", "chembl_id", "drugbank_id"):
        assert re.search(
            rf"ALTER\s+TABLE\s+drugs\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+{col}\s+TEXT",
            sql, re.IGNORECASE,
        ), f"{col} TEXT missing"


def test_migration_038_creates_indexes():
    sql = MIGRATION.read_text(encoding="utf-8")
    for idx in ("idx_drugs_modality", "idx_drugs_atc", "idx_drugs_ndc",
                "idx_drugs_unii", "idx_drugs_chembl"):
        assert re.search(
            rf"CREATE\s+(?:UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS\s+{idx}",
            sql, re.IGNORECASE,
        ), f"index missing: {idx}"


def test_migration_038_idempotent():
    sql = MIGRATION.read_text(encoding="utf-8")
    no_comments = re.sub(r"--[^\n]*", "", sql)
    add_columns = re.findall(r"ADD\s+COLUMN\s+(\S+)", no_comments, re.IGNORECASE)
    if_not_exists = re.findall(r"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS", no_comments, re.IGNORECASE)
    assert len(add_columns) == len(if_not_exists)


# ────────────────────────────────────────────────────────────────────
# Cat 2 — live DB
# ────────────────────────────────────────────────────────────────────

@db_required
def test_drugs_modality_column(db):
    rows = db.fetch_all(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name='drugs' AND column_name='modality'"
    )
    assert len(rows) == 1


@db_required
def test_drugs_modality_enum_enforced(db):
    """Bad modality value should violate CHECK."""
    with pytest.raises(Exception):
        db.execute(
            "INSERT INTO drugs (generic_name, modality, source_api, source_url, retrieved_at) "
            "VALUES ('TestDrug A1.2', 'INVALID_MODALITY', 'test', 'http://t', NOW())"
        )
    # Cleanup any partial inserts (none expected, but be safe)
    db.execute("DELETE FROM drugs WHERE generic_name = 'TestDrug A1.2'")


@db_required
def test_drugs_array_columns_default_empty(db):
    db.execute(
        "INSERT INTO drugs (generic_name, source_api, source_url, retrieved_at) "
        "VALUES ('TestDrug A1.2 arr', 'test', 'http://t', NOW())"
    )
    try:
        row = db.fetch_one(
            "SELECT atc_codes, ndc_codes FROM drugs "
            "WHERE generic_name = 'TestDrug A1.2 arr'"
        )
        assert row["atc_codes"] == []
        assert row["ndc_codes"] == []
    finally:
        db.execute("DELETE FROM drugs WHERE generic_name = 'TestDrug A1.2 arr'")


# ────────────────────────────────────────────────────────────────────
# Cat 3 — modality classifier helper
# ────────────────────────────────────────────────────────────────────

def test_modality_classifier_module_exists():
    assert (REPO_ROOT / "domain" / "pharma" / "modality.py").exists()


def test_classify_modality_known_drugs():
    """Spot-check known drugs land on the right modality bucket."""
    from domain.pharma.modality import classify_modality

    # Small molecules
    assert classify_modality(
        generic_name="metformin",
        mechanism="biguanide",
    ) == "small_molecule"

    # mAb
    assert classify_modality(
        generic_name="pembrolizumab",
        mechanism="PD-1 inhibitor",
    ) == "mab"

    # ADC (suffix recognition)
    assert classify_modality(
        generic_name="trastuzumab emtansine",
        mechanism="HER2-directed antibody-drug conjugate",
    ) == "adc"

    # Gene therapy
    assert classify_modality(
        generic_name="onasemnogene abeparvovec",
        mechanism="AAV9 gene therapy for SMN1",
    ) == "gene_therapy"

    # mRNA vaccine
    assert classify_modality(
        generic_name="tozinameran",
        mechanism="mRNA encoding SARS-CoV-2 spike",
    ) == "vaccine"


def test_classify_modality_falls_back_to_other():
    """Unknown patterns return 'other', never None or '' or invalid value."""
    from domain.pharma.modality import classify_modality
    result = classify_modality(generic_name="zzzfakedrugname", mechanism=None)
    assert result == "other"


def test_classify_modality_returns_only_valid_enum_values():
    """Whatever signal classify_modality is given, output must be a valid
    CHECK enum value (so writes never violate the constraint)."""
    from domain.pharma.modality import classify_modality, MODALITY_VALUES

    samples = [
        ("zanubrutinib", "BTK inhibitor"),
        ("blinatumomab", "CD19 x CD3 BiTE"),
        ("imlifidase", "IgG-degrading enzyme"),
        ("idecabtagene vicleucel", "BCMA CAR-T"),
        ("voretigene neparvovec", "AAV2 gene therapy"),
        ("inclisiran", "small interfering RNA"),
        ("", ""),
        (None, None),
    ]
    for generic, mech in samples:
        out = classify_modality(generic_name=generic, mechanism=mech)
        assert out in MODALITY_VALUES, f"({generic!r}, {mech!r}) → {out!r} not in enum"
