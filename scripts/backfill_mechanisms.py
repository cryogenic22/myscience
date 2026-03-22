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

# Drug name → mechanism name (known pharmacology)
DRUG_MECHANISM_MAP = {
    # GLP-1 Receptor Agonists
    "semaglutide": "Glucagon-Like Peptide-1 Receptor Agonists",
    "liraglutide": "Glucagon-Like Peptide-1 Receptor Agonists",
    "dulaglutide": "Glucagon-Like Peptide-1 Receptor Agonists",
    "exenatide": "Glucagon-Like Peptide-1 Receptor Agonists",
    "lixisenatide": "Glucagon-Like Peptide-1 Receptor Agonists",
    "orforglipron": "Glucagon-Like Peptide-1 Receptor Agonists",
    "tirzepatide": "Glucagon-Like Peptide-1 Receptor Agonists",
    "survodutide": "Glucagon-Like Peptide-1 Receptor Agonists",
    "retatrutide": "Glucagon-Like Peptide-1 Receptor Agonists",
    "cotadutide": "Glucagon-Like Peptide-1 Receptor Agonists",
    "pemvidutide": "Glucagon-Like Peptide-1 Receptor Agonists",
    "mazdutide": "Glucagon-Like Peptide-1 Receptor Agonists",
    "efinopegdutide": "Glucagon-Like Peptide-1 Receptor Agonists",
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


def run(dry_run: bool = False) -> dict:
    db = Database(config.db.dsn)
    db.connect()

    try:
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

            # 1. Try exact name match
            mech_name = DRUG_MECHANISM_MAP.get(name)

            # 2. Try INN suffix pattern
            if not mech_name:
                for suffix, mn in INN_SUFFIX_PATTERNS:
                    if suffix in name:
                        mech_name = mn
                        break

            # 3. Try insulin prefix
            if not mech_name and name.startswith("insulin"):
                mech_name = "Insulin"

            # 4. Try metformin anywhere in name (combo drugs)
            if not mech_name and "metformin" in name:
                mech_name = "Metformin"

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
