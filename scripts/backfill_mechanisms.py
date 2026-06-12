"""Backfill mechanism_id for drugs using name matching + INN suffix patterns.

Maps drugs to their mechanism of action using:
1. Exact name → mechanism lookup table (known pharmacology)
2. INN suffix patterns (-gliptin → DPP-4i, -gliflozin → SGLT2i, etc.)

Usage:
    python -m scripts.backfill_mechanisms [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone

from config import config
from db import Database

logger = logging.getLogger(__name__)

# ── Incretin CO-AGONIST mechanisms (curated) ────────────────────────────────
# Coarse MeSH collapses these clinically-distinct pharmacologies into the pure
# GLP-1 class (D000097789). That is WRONG and is exactly the CLIN-02 eval
# failure: tirzepatide is the first GIP/GLP-1 "twincretin", NOT a GLP-1 RA. The
# rows are created (source_api='curated_sme') by scripts/correct_drug_mechanisms.py.
MECH_GLP1 = "Glucagon-Like Peptide-1 Receptor Agonists"
MECH_GIP_GLP1 = (
    "Glucose-Dependent Insulinotropic Polypeptide and "
    "Glucagon-Like Peptide-1 Receptor Agonists"
)
MECH_GCG_GLP1 = "Glucagon and Glucagon-Like Peptide-1 Receptor Agonists"
MECH_TRIPLE = (
    "Glucagon, Glucose-Dependent Insulinotropic Polypeptide, and "
    "Glucagon-Like Peptide-1 Receptor Agonists"
)

CURATED_CO_AGONIST_MECHANISMS = [
    {"name": MECH_GIP_GLP1, "mechanism_class": "incretin_based",
     "scope_note": "Dual incretin receptor agonist ('twincretin'): agonist of "
                   "BOTH the glucose-dependent insulinotropic polypeptide (GIP) "
                   "and glucagon-like peptide-1 (GLP-1) receptors. Distinct from "
                   "pure GLP-1 receptor agonists. First-in-class: tirzepatide "
                   "(Mounjaro, T2D 2022; Zepbound, obesity 2023)."},
    {"name": MECH_GCG_GLP1, "mechanism_class": "incretin_based",
     "scope_note": "Dual agonist of the glucagon and GLP-1 receptors "
                   "(oxyntomodulin class). Distinct from pure GLP-1 receptor agonists."},
    {"name": MECH_TRIPLE, "mechanism_class": "incretin_based",
     "scope_note": "Triple agonist of the glucagon, GIP and GLP-1 receptors "
                   "(e.g. retatrutide). Distinct from pure GLP-1 receptor agonists."},
]

# generic_name → correct curated mechanism, for the co-agonists that the old map
# mis-tagged as pure GLP-1. This is the authoritative scope of the correction.
CO_AGONIST_CORRECTIONS = {
    "tirzepatide": MECH_GIP_GLP1,
    "retatrutide": MECH_TRIPLE,
    "survodutide": MECH_GCG_GLP1,
    "cotadutide": MECH_GCG_GLP1,
    "pemvidutide": MECH_GCG_GLP1,
    "mazdutide": MECH_GCG_GLP1,
    "efinopegdutide": MECH_GCG_GLP1,
}

# Drug name → mechanism name (known pharmacology)
DRUG_MECHANISM_MAP = {
    # GLP-1 Receptor Agonists (pure)
    "semaglutide": MECH_GLP1,
    "liraglutide": MECH_GLP1,
    "dulaglutide": MECH_GLP1,
    "exenatide": MECH_GLP1,
    "lixisenatide": MECH_GLP1,
    "orforglipron": MECH_GLP1,
    # Incretin co-agonists — NOT pure GLP-1 (see CO_AGONIST_CORRECTIONS)
    "tirzepatide": MECH_GIP_GLP1,
    "survodutide": MECH_GCG_GLP1,
    "retatrutide": MECH_TRIPLE,
    "cotadutide": MECH_GCG_GLP1,
    "pemvidutide": MECH_GCG_GLP1,
    "mazdutide": MECH_GCG_GLP1,
    "efinopegdutide": MECH_GCG_GLP1,
    "cagrilintide": "Appetite Depressants",
    # SGLT2i
    "empagliflozin": "Sodium-Glucose Transporter 2 Inhibitors",
    "dapagliflozin": "Sodium-Glucose Transporter 2 Inhibitors",
    "canagliflozin": "Sodium-Glucose Transporter 2 Inhibitors",
    "ertugliflozin": "Sodium-Glucose Transporter 2 Inhibitors",
    # DPP-4i
    "sitagliptin": "Dipeptidyl-Peptidase IV Inhibitors",
    "linagliptin": "Dipeptidyl-Peptidase IV Inhibitors",
    "saxagliptin": "Dipeptidyl-Peptidase IV Inhibitors",
    "alogliptin": "Dipeptidyl-Peptidase IV Inhibitors",
    # Insulin
    "insulin glargine": "Insulin",
    "insulin lispro": "Insulin",
    "insulin aspart": "Insulin",
    "insulin degludec": "Insulin",
    "insulin detemir": "Insulin",
    "human insulin": "Insulin",
    # Biguanide / TZD
    "metformin": "Metformin",
    "pioglitazone": "Thiazolidinediones",
    "rosiglitazone": "Thiazolidinediones",
    "acarbose": "Hypoglycemic Agents",
    "miglitol": "Hypoglycemic Agents",
    # ACE Inhibitors
    "enalapril": "Angiotensin-Converting Enzyme Inhibitors",
    "lisinopril": "Angiotensin-Converting Enzyme Inhibitors",
    "ramipril": "Angiotensin-Converting Enzyme Inhibitors",
    "captopril": "Angiotensin-Converting Enzyme Inhibitors",
    "perindopril": "Angiotensin-Converting Enzyme Inhibitors",
    # ARBs
    "losartan": "Angiotensin II Type 1 Receptor Blockers",
    "valsartan": "Angiotensin II Type 1 Receptor Blockers",
    "irbesartan": "Angiotensin II Type 1 Receptor Blockers",
    "candesartan": "Angiotensin II Type 1 Receptor Blockers",
    "telmisartan": "Angiotensin II Type 1 Receptor Blockers",
    "olmesartan": "Angiotensin II Type 1 Receptor Blockers",
    "sacubitril": "Angiotensin II Type 1 Receptor Blockers",
    # Beta-blockers
    "carvedilol": "Adrenergic beta-Antagonists",
    "metoprolol": "Adrenergic beta-Antagonists",
    "bisoprolol": "Adrenergic beta-Antagonists",
    "nebivolol": "Adrenergic beta-Antagonists",
    "atenolol": "Adrenergic beta-Antagonists",
    # MRAs
    "spironolactone": "Mineralocorticoid Receptor Antagonists",
    "eplerenone": "Mineralocorticoid Receptor Antagonists",
    "finerenone": "Mineralocorticoid Receptor Antagonists",
    # Other CV
    "ivabradine": "Calcium Channel Blockers",
    "vericiguat": "Vasodilator Agents",
    "amlodipine": "Calcium Channel Blockers",
    "nifedipine": "Calcium Channel Blockers",
    "diltiazem": "Calcium Channel Blockers",
    "furosemide": "Diuretics",
    "hydrochlorothiazide": "Diuretics",
}

# INN suffix → mechanism (catches drugs not in the explicit map)
INN_SUFFIX_PATTERNS = [
    ("gliptin", "Dipeptidyl-Peptidase IV Inhibitors"),
    ("gliflozin", "Sodium-Glucose Transporter 2 Inhibitors"),
    ("glutide", "Glucagon-Like Peptide-1 Receptor Agonists"),
    ("glitazone", "Thiazolidinediones"),
    ("sartan", "Angiotensin II Type 1 Receptor Blockers"),
    ("olol", "Adrenergic beta-Antagonists"),
    ("dipine", "Calcium Channel Blockers"),
    ("pril", "Angiotensin-Converting Enzyme Inhibitors"),
    ("semide", "Diuretics"),
    ("thiazide", "Diuretics"),
    ("lactone", "Mineralocorticoid Receptor Antagonists"),
]


def match_mechanism(drug_name: str) -> str | None:
    """Return mechanism name for a drug, or None if unrecognized.

    Matching cascade:
    1. Exact name lookup in DRUG_MECHANISM_MAP
    2. INN suffix pattern (-gliptin, -gliflozin, etc.)
    3. Insulin prefix
    4. Metformin anywhere in name (combo drugs)
    """
    name = drug_name.strip().lower()

    # 1. Exact name match
    mech_name = DRUG_MECHANISM_MAP.get(name)
    if mech_name:
        return mech_name

    # 2. INN suffix pattern
    for suffix, mn in INN_SUFFIX_PATTERNS:
        if suffix in name:
            return mn

    # 3. Insulin prefix
    if name.startswith("insulin"):
        return "Insulin"

    # 4. Metformin anywhere in name (combo drugs)
    if "metformin" in name:
        return "Metformin"

    return None


def backfill_mechanisms(db, dry_run: bool = False) -> dict:
    """Run mechanism backfill against a given DB connection."""
    # Load mechanism IDs
    mechs = db.fetch_all("SELECT id, name FROM mechanisms_of_action")
    mech_map = {r["name"]: str(r["id"]) for r in mechs}

    # Get all drugs without mechanism
    drugs = db.fetch_all("""
        SELECT id, generic_name FROM drugs
        WHERE mechanism_id IS NULL
          AND (record_status IS NULL OR record_status = 'active')
          AND generic_name IS NOT NULL
    """)
    logger.info("Drugs without mechanism: %d", len(drugs))

    direct_count = 0
    suffix_count = 0

    for drug in drugs:
        name = drug["generic_name"].strip().lower()
        drug_id = str(drug["id"])

        mech_name = match_mechanism(drug["generic_name"])
        if not mech_name:
            continue

        mech_id = mech_map.get(mech_name)
        if not mech_id:
            logger.warning("Mechanism '%s' not in DB", mech_name)
            continue

        if dry_run:
            logger.info("[DRY RUN] %s -> %s", drug["generic_name"], mech_name)
        else:
            db.execute(
                "UPDATE drugs SET mechanism_id = %s WHERE id = %s",
                [mech_id, drug["id"]],
            )

        if name in DRUG_MECHANISM_MAP:
            direct_count += 1
        else:
            suffix_count += 1

    # Final stats
    final = db.fetch_one(
        "SELECT COUNT(*) AS cnt FROM drugs WHERE mechanism_id IS NOT NULL "
        "AND (record_status IS NULL OR record_status = 'active')"
    )
    total = db.fetch_one(
        "SELECT COUNT(*) AS cnt FROM drugs WHERE record_status IS NULL OR record_status = 'active'"
    )

    result = {
        "direct_matches": direct_count,
        "suffix_matches": suffix_count,
        "total_updated": direct_count + suffix_count,
        "mechanism_coverage": f"{final['cnt']}/{total['cnt']} ({final['cnt']/total['cnt']*100:.1f}%)",
    }
    logger.info("Mechanism backfill: %s", result)
    return result


def run(dry_run: bool = False) -> dict:
    """Run mechanism backfill (creates own DB connection)."""
    db = Database(config.db.dsn)
    db.connect()
    try:
        return backfill_mechanisms(db, dry_run)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Backfill drug mechanism_id")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    result = run(dry_run=args.dry_run)
    print(f"\n=== Mechanism Backfill ===")
    for k, v in result.items():
        print(f"  {k}: {v}")
    if args.dry_run:
        print("  (dry run)")


if __name__ == "__main__":
    main()
