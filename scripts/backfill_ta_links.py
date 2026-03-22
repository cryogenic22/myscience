"""Backfill therapeutic-area links and trial labels.

Phase 1.1 + 1.6: Fix 12/18 empty TAs and fill blank trial labels.

Strategy:
  - Match drugs to child TAs via clinical trial condition text
  - Use MeSH hierarchy (parent TA → child TA keywords)
  - Fill empty trial labels from brief_title / official_title / nct_id

Usage:
    python -m scripts.backfill_ta_links [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

from config import config
from db import Database

logger = logging.getLogger(__name__)

# ── TA keyword mappings ──
# Maps child TA name → list of condition keyword patterns (case-insensitive).
# Used to match clinical_trials.conditions against child TAs.
TA_CONDITION_KEYWORDS: dict[str, list[str]] = {
    "Diabetes Mellitus, Type 1": [
        "type 1 diabetes", "t1dm", "type i diabetes",
        "insulin-dependent diabetes", "juvenile diabetes",
    ],
    "Diabetes Mellitus, Type 2": [
        "type 2 diabetes", "t2dm", "type ii diabetes",
        "non-insulin-dependent diabetes", "niddm",
    ],
    "Diabetic Nephropathies": [
        "diabetic nephropathy", "diabetic kidney",
        "diabetic renal", "dkd",
    ],
    "Metabolic Syndrome": [
        "metabolic syndrome", "syndrome x",
        "insulin resistance syndrome",
    ],
    "Coronary Artery Disease": [
        "coronary artery disease", "cad", "coronary heart disease",
        "ischemic heart disease", "myocardial infarction",
        "acute coronary syndrome", "angina",
    ],
    "Atrial Fibrillation": [
        "atrial fibrillation", "afib", "a-fib", "af ",
        "atrial flutter",
    ],
    "Cardiomyopathies": [
        "cardiomyopathy", "cardiomyopathies",
        "dilated cardiomyopathy", "hypertrophic cardiomyopathy",
    ],
    "Heart Failure, Diastolic": [
        "diastolic heart failure", "hfpef",
        "heart failure with preserved ejection fraction",
        "preserved ejection fraction",
    ],
    "Heart Failure, Systolic": [
        "systolic heart failure", "hfref",
        "heart failure with reduced ejection fraction",
        "reduced ejection fraction",
    ],
    "Hypertension": [
        "hypertension", "high blood pressure",
        "elevated blood pressure", "resistant hypertension",
    ],
    "Renal Insufficiency, Chronic": [
        "chronic kidney disease", "ckd", "chronic renal",
        "renal insufficiency", "end-stage renal",
        "esrd", "egfr",
    ],
    "Heart Failure": [
        "heart failure", "cardiac failure",
        "congestive heart failure", "chf",
    ],
}

# Drug mechanism → TA overrides.  SGLT2i drugs with HF trials also link to HF TAs, etc.
MECHANISM_TA_OVERRIDES: dict[str, list[str]] = {
    "SGLT2 Inhibitors": [
        "Heart Failure",
        "Heart Failure, Diastolic",
        "Heart Failure, Systolic",
        "Renal Insufficiency, Chronic",
    ],
    "GLP-1 Receptor Agonists": [
        "Cardiovascular Diseases",
        "Obesity",
    ],
}


def _log_change(db: Database, entity_type: str, entity_id: str,
                change_type: str, fields: list[str]) -> None:
    db.execute(
        """
        INSERT INTO data_change_log
            (entity_type, entity_id, change_type, changed_fields, changed_at)
        VALUES (%s, %s, %s, %s, %s)
        """,
        [entity_type, entity_id, change_type, fields, datetime.now(timezone.utc)],
    )


def fill_trial_labels(db: Database, dry_run: bool = False) -> int:
    """Fill empty trial labels from title fields.

    Note: clinical_trials table uses 'official_title' (no brief_title or label column).
    If a 'label' column doesn't exist, this is a no-op.
    """
    # Check if label column exists
    col_check = db.fetch_one(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'clinical_trials' AND column_name = 'label'
        """
    )
    if not col_check:
        logger.info("No 'label' column in clinical_trials — skipping trial label fill")
        return 0

    rows = db.fetch_all(
        """
        SELECT id, official_title
        FROM clinical_trials
        WHERE label IS NULL OR label = ''
        """
    )
    count = 0
    for row in rows:
        label = (
            row.get("official_title")
            or row["id"]
        )
        if not label:
            continue
        # Truncate long titles
        if len(label) > 300:
            label = label[:297] + "..."
        if dry_run:
            logger.info("[DRY RUN] Trial %s → label: %s", row["id"], label[:80])
        else:
            db.execute(
                "UPDATE clinical_trials SET label = %s WHERE id = %s",
                [label, row["id"]],
            )
            _log_change(db, "trial", row["id"], "backfill_label", ["label"])
        count += 1

    logger.info("Trial labels filled: %d", count)
    return count


def _get_ta_id_map(db: Database) -> dict[str, str]:
    """Return mapping of TA name (lowercase) → TA id."""
    rows = db.fetch_all("SELECT id, name FROM therapeutic_areas")
    return {r["name"].lower(): str(r["id"]) for r in rows}


def _get_mechanism_id_map(db: Database) -> dict[str, str]:
    """Return mapping of mechanism name (lowercase) → mechanism id."""
    rows = db.fetch_all("SELECT id, name FROM mechanisms_of_action")
    return {r["name"].lower(): str(r["id"]) for r in rows}


def _link_exists(db: Database, source_id: str, source_type: str,
                 target_id: str, target_type: str, link_type: str) -> bool:
    row = db.fetch_one(
        """
        SELECT 1 FROM entity_links
        WHERE source_entity_id = %s AND source_entity_type = %s
          AND target_entity_id = %s AND target_entity_type = %s
          AND link_type = %s
        """,
        [source_id, source_type, target_id, target_type, link_type],
    )
    return row is not None


def _create_link(db: Database, source_id: str, source_type: str,
                 target_id: str, target_type: str, link_type: str,
                 confidence: float = 0.8, provenance: str = "backfill_ta_links",
                 link_via: str = "condition_keyword_match") -> None:
    if _link_exists(db, source_id, source_type, target_id, target_type, link_type):
        return
    db.execute(
        """
        INSERT INTO entity_links
            (source_entity_id, source_entity_type,
             target_entity_id, target_entity_type,
             link_type, link_via, confidence, provenance_source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
        """,
        [source_id, source_type, target_id, target_type,
         link_type, link_via, confidence, provenance],
    )


def backfill_ta_links_from_trials(db: Database, dry_run: bool = False) -> int:
    """Link drugs to child TAs based on their trial condition text."""
    ta_map = _get_ta_id_map(db)
    links_created = 0

    # Get all drugs with at least one trial
    drugs = db.fetch_all(
        """
        SELECT DISTINCT d.id AS drug_id, d.generic_name
        FROM drugs d
        JOIN entity_links el ON el.target_entity_id = d.id::text
          AND el.target_entity_type = 'drug'
          AND el.link_type = 'INVESTIGATES'
        WHERE d.generic_name IS NOT NULL
        """
    )

    for drug in drugs:
        drug_id = str(drug["drug_id"])

        # Get all conditions from trials linked to this drug
        trials = db.fetch_all(
            """
            SELECT ct.id, ct.conditions
            FROM clinical_trials ct
            JOIN entity_links el ON el.source_entity_id = ct.id
              AND el.source_entity_type = 'trial'
              AND el.link_type = 'INVESTIGATES'
              AND el.target_entity_id = %s
            WHERE ct.conditions IS NOT NULL
            """,
            [drug_id],
        )

        # Collect all condition text
        all_conditions = []
        for trial in trials:
            conds = trial.get("conditions")
            if isinstance(conds, list):
                all_conditions.extend([c.lower() for c in conds if c])
            elif isinstance(conds, str):
                all_conditions.append(conds.lower())

        conditions_text = " ".join(all_conditions)
        if not conditions_text:
            continue

        # Match against TA keyword patterns
        for ta_name, keywords in TA_CONDITION_KEYWORDS.items():
            ta_id = ta_map.get(ta_name.lower())
            if not ta_id:
                continue

            matched = any(kw in conditions_text for kw in keywords)
            if matched:
                if dry_run:
                    logger.info(
                        "[DRY RUN] Link drug %s (%s) → TA %s",
                        drug["generic_name"], drug_id, ta_name,
                    )
                else:
                    _create_link(
                        db, drug_id, "drug", ta_id, "therapeutic_area",
                        "IN_THERAPEUTIC_AREA", confidence=0.75,
                    )
                    _log_change(db, "drug", drug_id, "backfill_ta_link",
                                [f"ta:{ta_name}"])
                links_created += 1

    logger.info("TA links created from trial conditions: %d", links_created)
    return links_created


def backfill_ta_links_from_mechanism(db: Database, dry_run: bool = False) -> int:
    """Link drugs to TAs based on mechanism class → TA overrides."""
    ta_map = _get_ta_id_map(db)
    mechanism_map = _get_mechanism_id_map(db)
    links_created = 0

    for mech_name, ta_names in MECHANISM_TA_OVERRIDES.items():
        mech_id = mechanism_map.get(mech_name.lower())
        if not mech_id:
            continue

        # Find drugs with this mechanism
        drugs = db.fetch_all(
            """
            SELECT d.id, d.generic_name
            FROM drugs d
            JOIN entity_links el ON el.source_entity_id = d.id::text
              AND el.source_entity_type = 'drug'
              AND el.link_type = 'TARGETS_MECHANISM'
              AND el.target_entity_id = %s
            """,
            [mech_id],
        )

        for drug in drugs:
            drug_id = str(drug["id"])
            for ta_name in ta_names:
                ta_id = ta_map.get(ta_name.lower())
                if not ta_id:
                    continue

                if dry_run:
                    logger.info(
                        "[DRY RUN] Link drug %s (%s) → TA %s (via mechanism %s)",
                        drug["generic_name"], drug_id, ta_name, mech_name,
                    )
                else:
                    _create_link(
                        db, drug_id, "drug", ta_id, "therapeutic_area",
                        "IN_THERAPEUTIC_AREA", confidence=0.7,
                    )
                    _log_change(db, "drug", drug_id, "backfill_ta_link",
                                [f"ta:{ta_name}", f"via_mechanism:{mech_name}"])
                links_created += 1

    logger.info("TA links created from mechanism overrides: %d", links_created)
    return links_created


def backfill_trial_ta_links(db: Database, dry_run: bool = False) -> int:
    """Link trials directly to TAs based on their condition text."""
    ta_map = _get_ta_id_map(db)
    links_created = 0

    trials = db.fetch_all(
        """
        SELECT id, conditions
        FROM clinical_trials
        WHERE conditions IS NOT NULL
        """
    )

    for trial in trials:
        conds = trial.get("conditions")
        if isinstance(conds, list):
            conditions_text = " ".join([c.lower() for c in conds if c])
        elif isinstance(conds, str):
            conditions_text = conds.lower()
        else:
            continue

        if not conditions_text:
            continue

        for ta_name, keywords in TA_CONDITION_KEYWORDS.items():
            ta_id = ta_map.get(ta_name.lower())
            if not ta_id:
                continue

            matched = any(kw in conditions_text for kw in keywords)
            if matched:
                if dry_run:
                    logger.info(
                        "[DRY RUN] Link trial %s → TA %s",
                        trial["id"], ta_name,
                    )
                else:
                    _create_link(
                        db, trial["id"], "trial", ta_id, "therapeutic_area",
                        "IN_THERAPEUTIC_AREA", confidence=0.75,
                    )
                links_created += 1

    logger.info("Trial→TA links created: %d", links_created)
    return links_created


def run(dry_run: bool = False) -> dict:
    """Run all backfill tasks. Returns summary dict."""
    db = Database(config.db.dsn)
    db.connect()

    try:
        results = {
            "trial_labels_filled": fill_trial_labels(db, dry_run),
            "drug_ta_links_from_trials": backfill_ta_links_from_trials(db, dry_run),
            "drug_ta_links_from_mechanisms": backfill_ta_links_from_mechanism(db, dry_run),
            "trial_ta_links": backfill_trial_ta_links(db, dry_run),
        }
        total = sum(results.values())
        logger.info("Backfill complete. Total changes: %d", total)
        return results
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Backfill TA links and trial labels")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    results = run(dry_run=args.dry_run)
    print("\n=== Backfill Results ===")
    for k, v in results.items():
        print(f"  {k}: {v}")
    print(f"  TOTAL: {sum(results.values())}")
    if args.dry_run:
        print("  (dry run — no changes written)")


if __name__ == "__main__":
    main()
