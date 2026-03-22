"""Extract biomarker mentions from trial outcome measures.

Pattern-matches the 12 seed biomarkers against 211K trial_outcomes records.
Creates entity_links: Trial -> HAS_PRIMARY_ENDPOINT / HAS_SECONDARY_ENDPOINT -> Biomarker.

Usage:
    python -m scripts.extract_biomarkers [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
import re
from datetime import datetime, timezone

from config import config
from db import Database

logger = logging.getLogger(__name__)

# Pattern groups for each biomarker — ordered by specificity (most specific first)
# Each tuple: (biomarker_name, [regex_patterns])
BIOMARKER_PATTERNS: list[tuple[str, list[re.Pattern]]] = [
    ("Glycated Hemoglobin", [
        re.compile(r"\bHbA1c\b", re.I),
        re.compile(r"\bA1[Cc]\b"),
        re.compile(r"\bglyc(?:at|osylat)ed\s+h[ae]moglobin\b", re.I),
        re.compile(r"\bglycoh[ae]moglobin\b", re.I),
        re.compile(r"\bhemoglobin\s+A1c\b", re.I),
    ]),
    ("Major Adverse Cardiovascular Events", [
        re.compile(r"\bMACE\b"),
        re.compile(r"\bmajor\s+adverse\s+cardiovascular\s+event", re.I),
        re.compile(r"\b(?:CV|cardiovascular)\s+death.*(?:MI|myocardial infarction).*stroke\b", re.I),
        re.compile(r"\b3[\s-]?point\s+MACE\b", re.I),
    ]),
    ("Estimated Glomerular Filtration Rate", [
        re.compile(r"\beGFR\b"),
        re.compile(r"\bestimated\s+glomerular\s+filtration\b", re.I),
        re.compile(r"\bglomerular\s+filtration\s+rate\b", re.I),
    ]),
    ("N-terminal pro-B-type Natriuretic Peptide", [
        re.compile(r"\bNT[\s-]?proBNP\b", re.I),
        re.compile(r"\bN[\s-]?terminal\s+pro[\s-]?(?:B[\s-]?type\s+)?(?:BNP|natriuretic)\b", re.I),
        re.compile(r"\bBNP\b"),
    ]),
    ("Left Ventricular Ejection Fraction", [
        re.compile(r"\bLVEF\b"),
        re.compile(r"\bleft\s+ventricular\s+ejection\s+fraction\b", re.I),
        re.compile(r"\bejection\s+fraction\b", re.I),
    ]),
    ("Urine Albumin-to-Creatinine Ratio", [
        re.compile(r"\bUACR\b"),
        re.compile(r"\burine\s+albumin[\s-]?(?:to[\s-]?)?creatinine\b", re.I),
        re.compile(r"\balbuminuria\b", re.I),
        re.compile(r"\balbumin[\s-]?creatinine\s+ratio\b", re.I),
    ]),
    ("Fasting Plasma Glucose", [
        re.compile(r"\bFPG\b"),
        re.compile(r"\bfasting\s+(?:plasma\s+)?glucose\b", re.I),
        re.compile(r"\bfasting\s+blood\s+(?:sugar|glucose)\b", re.I),
    ]),
    ("Blood Pressure", [
        re.compile(r"\b(?:systolic|diastolic)\s+blood\s+pressure\b", re.I),
        re.compile(r"\bSBP\b"),
        re.compile(r"\bDBP\b"),
        re.compile(r"\bblood\s+pressure\b", re.I),
    ]),
    ("Body Weight", [
        re.compile(r"\bbody\s+weight\b", re.I),
        re.compile(r"\bweight\s+(?:loss|change|reduction)\b", re.I),
        re.compile(r"\bpercent(?:age)?\s+(?:change\s+in\s+)?(?:body\s+)?weight\b", re.I),
    ]),
    ("Body Mass Index", [
        re.compile(r"\bBMI\b"),
        re.compile(r"\bbody\s+mass\s+index\b", re.I),
    ]),
    ("Waist Circumference", [
        re.compile(r"\bwaist\s+circumference\b", re.I),
    ]),
    ("Alanine Aminotransferase", [
        re.compile(r"\bALT\b"),
        re.compile(r"\balanine\s+(?:amino)?transferase\b", re.I),
        re.compile(r"\bSGPT\b"),
        re.compile(r"\bliver\s+fat\b", re.I),
    ]),
]

# Timepoint extraction pattern
TIMEPOINT_PATTERN = re.compile(
    r"(?:at|through|over|by|from baseline to)\s+"
    r"(?:week|wk|month|mo|day)\s*(\d+)",
    re.I,
)
WEEK_PATTERN = re.compile(r"\b(\d+)\s*(?:week|wk)s?\b", re.I)


def _extract_timepoint(text: str) -> str | None:
    """Extract timepoint from outcome measure text."""
    m = TIMEPOINT_PATTERN.search(text)
    if m:
        return m.group(0).strip()
    m = WEEK_PATTERN.search(text)
    if m:
        return f"Week {m.group(1)}"
    return None


def match_biomarkers(text: str) -> list[tuple[str, str | None]]:
    """Match biomarker patterns against outcome measure text.

    Returns list of (biomarker_name, timepoint) tuples.
    """
    if not text:
        return []

    matches = []
    matched_names = set()

    for biomarker_name, patterns in BIOMARKER_PATTERNS:
        if biomarker_name in matched_names:
            continue
        for pattern in patterns:
            if pattern.search(text):
                timepoint = _extract_timepoint(text)
                matches.append((biomarker_name, timepoint))
                matched_names.add(biomarker_name)
                break

    return matches


def run(dry_run: bool = False) -> dict:
    """Extract biomarker mentions from trial outcomes and create links."""
    db = Database(config.db.dsn)
    db.connect()

    try:
        # Load biomarker IDs
        biomarker_map = {}
        rows = db.fetch_all("SELECT id, name FROM biomarkers")
        for r in rows:
            biomarker_map[r["name"]] = str(r["id"])

        if not biomarker_map:
            logger.warning("No biomarkers in database — run migration 017 first")
            return {"error": "no biomarkers", "links_created": 0}

        logger.info("Loaded %d biomarkers", len(biomarker_map))

        # Process trial outcomes in batches
        total_outcomes = db.fetch_one("SELECT COUNT(*) AS cnt FROM trial_outcomes")["cnt"]
        logger.info("Processing %d trial outcomes", total_outcomes)

        batch_size = 5000
        offset = 0
        links_created = 0
        biomarker_counts: dict[str, int] = {}

        while offset < total_outcomes:
            outcomes = db.fetch_all(
                """
                SELECT trial_id, outcome_type, measure, description
                FROM trial_outcomes
                ORDER BY trial_id
                LIMIT %s OFFSET %s
                """,
                [batch_size, offset],
            )

            if not outcomes:
                break

            for outcome in outcomes:
                text = f"{outcome.get('measure', '')} {outcome.get('description', '')}"
                matches = match_biomarkers(text)

                for biomarker_name, timepoint in matches:
                    biomarker_id = biomarker_map.get(biomarker_name)
                    if not biomarker_id:
                        continue

                    trial_id = outcome["trial_id"]
                    outcome_type = outcome.get("outcome_type", "PRIMARY")
                    link_type = (
                        "HAS_PRIMARY_ENDPOINT"
                        if outcome_type == "PRIMARY"
                        else "HAS_SECONDARY_ENDPOINT"
                    )

                    biomarker_counts[biomarker_name] = biomarker_counts.get(biomarker_name, 0) + 1

                    if dry_run:
                        continue

                    # Create link (idempotent)
                    db.execute(
                        """
                        INSERT INTO entity_links
                            (source_entity_id, source_entity_type,
                             target_entity_id, target_entity_type,
                             link_type, link_via, confidence, provenance_source,
                             metadata)
                        VALUES (%s, 'trial', %s, 'biomarker', %s, %s, 0.85,
                                'biomarker_extraction',
                                %s::jsonb)
                        ON CONFLICT DO NOTHING
                        """,
                        [
                            trial_id, biomarker_id, link_type,
                            "pattern_match",
                            f'{{"timepoint": "{timepoint}"}}' if timepoint else "{}",
                        ],
                    )
                    links_created += 1

            offset += batch_size
            if offset % 50000 == 0:
                logger.info("  Processed %d/%d outcomes, %d links so far",
                            offset, total_outcomes, links_created)

        logger.info("Biomarker extraction complete: %d links created", links_created)
        logger.info("Biomarker distribution:")
        for name, count in sorted(biomarker_counts.items(), key=lambda x: -x[1]):
            logger.info("  %s: %d mentions", name, count)

        return {
            "links_created": links_created,
            "biomarker_counts": biomarker_counts,
            "outcomes_processed": total_outcomes,
        }

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Extract biomarkers from trial outcomes")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    results = run(dry_run=args.dry_run)
    print("\n=== Biomarker Extraction Results ===")
    print(f"  Outcomes processed: {results.get('outcomes_processed', 0)}")
    print(f"  Links created: {results.get('links_created', 0)}")
    if results.get("biomarker_counts"):
        print("\n  Biomarker mentions:")
        for name, count in sorted(results["biomarker_counts"].items(), key=lambda x: -x[1]):
            print(f"    {name}: {count}")
    if args.dry_run:
        print("  (dry run — no changes written)")


if __name__ == "__main__":
    main()
