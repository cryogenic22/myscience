"""Fetch WHO GPRM international drug pricing data and store in drug_pricing table.

The WHO Global Price Reporting Mechanism (GPRM) provides medicine
price data across 50+ countries. Data is typically distributed as
CSV downloads or JSON exports. This script parses GPRM records,
matches drugs to the existing drugs table, and stores international
pricing for cross-country comparison.

Usage:
    python -m scripts.fetch_who_gprm [--dry-run] [--data-path data.csv]
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from config import config
from db import Database

logger = logging.getLogger(__name__)

# Well-known ATC code -> drug name fallback mapping
# Used when medicine_name is missing but atc_code is present
ATC_DRUG_MAP: dict[str, str] = {
    "A10BA02": "Metformin",
    "A10BB01": "Glibenclamide",
    "A10BJ02": "Liraglutide",
    "A10BJ06": "Semaglutide",
    "B01AC06": "Aspirin",
    "C03CA01": "Furosemide",
    "C07AB03": "Atenolol",
    "C08CA01": "Amlodipine",
    "C09AA02": "Enalapril",
    "C09AA05": "Ramipril",
    "C10AA01": "Simvastatin",
    "C10AA05": "Atorvastatin",
    "C10AA07": "Rosuvastatin",
    "H02AB06": "Prednisolone",
    "H02AB07": "Prednisone",
    "J01CA04": "Amoxicillin",
    "J01CR02": "Amoxicillin/Clavulanic acid",
    "J01FA10": "Azithromycin",
    "J05AF07": "Tenofovir",
    "L01XE03": "Erlotinib",
    "L04AA06": "Mycophenolic acid",
    "L04AB02": "Infliximab",
    "M01AE01": "Ibuprofen",
    "N02AA01": "Morphine",
    "N02BE01": "Paracetamol",
    "N03AX09": "Lamotrigine",
    "N05AH03": "Olanzapine",
    "N06AB06": "Sertraline",
    "R03AC02": "Salbutamol",
    "R03BA02": "Budesonide",
}


# ── Parsing ──

def _resolve_drug_name(record: dict[str, Any]) -> str:
    """Resolve drug name from medicine_name, atc_description, or ATC code lookup."""
    name = (record.get("medicine_name") or "").strip()
    if name:
        return name.title() if name == name.upper() else name

    # Fallback 1: atc_description field
    desc = (record.get("atc_description") or "").strip()
    if desc:
        return desc.title() if desc == desc.upper() else desc

    # Fallback 2: ATC code lookup
    atc = (record.get("atc_code") or "").strip().upper()
    if atc and atc in ATC_DRUG_MAP:
        return ATC_DRUG_MAP[atc]

    return ""


def _parse_gprm_record(record: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Parse a single WHO GPRM record into a drug_pricing row.

    Returns None if the record has missing critical fields (no price or no drug name).
    """
    price = record.get("price_per_unit")
    if price is None:
        return None

    try:
        unit_price = float(price)
    except (ValueError, TypeError):
        return None

    if unit_price <= 0:
        return None

    drug_name = _resolve_drug_name(record)
    if not drug_name:
        return None

    country = (record.get("country") or "").strip()
    currency = (record.get("currency") or "").strip().upper()
    raw_price_type = (record.get("price_type") or "unknown").strip().lower()
    dosage_form = (record.get("dosage_form") or "").strip()
    strength = (record.get("strength") or "").strip()
    atc_code = (record.get("atc_code") or "").strip().upper()
    year = record.get("year")

    # Build effective date from year
    effective_date = None
    if year:
        try:
            effective_date = date(int(year), 1, 1)
        except (ValueError, TypeError):
            pass

    # Map unit from dosage form
    form_lower = dosage_form.lower()
    if "tablet" in form_lower or "capsule" in form_lower:
        unit = "per tablet"
    elif "ml" in form_lower or "solution" in form_lower or "injection" in form_lower:
        unit = "per ml"
    elif "vial" in form_lower:
        unit = "per vial"
    else:
        unit = "per unit"

    return {
        "drug_name": drug_name,
        "price_type": f"gprm_{raw_price_type}",
        "unit_price": unit_price,
        "unit": unit,
        "currency": currency,
        "country": country,
        "source_api": "who_gprm",
        "source_url": None,
        "effective_date": effective_date,
        "strength": strength,
        "dosage_form": dosage_form,
        "atc_code": atc_code,
    }


def parse_gprm_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse WHO GPRM records into drug_pricing format.

    Skips records with missing prices or unresolvable drug names.
    Returns structured dicts ready for drug matching and DB insertion.
    """
    parsed = []
    for record in records:
        result = _parse_gprm_record(record)
        if result is not None:
            parsed.append(result)
    return parsed


# ── Drug matching ──

def _match_drug_name(db: Database, drug_name: str) -> Optional[str]:
    """Match a drug name to an existing drug in the drugs table.

    Uses exact match on generic_name (case-insensitive), then
    tries ILIKE prefix match as fallback.
    Returns the drug UUID or None.
    """
    if not drug_name:
        return None

    clean = drug_name.strip().lower()

    # 1. Exact match on generic_name
    row = db.fetch_one(
        """
        SELECT id FROM drugs
        WHERE LOWER(generic_name) = %s
          AND record_status IS DISTINCT FROM 'excluded'
          AND record_status IS DISTINCT FROM 'merged'
        LIMIT 1
        """,
        [clean],
    )
    if row:
        return str(row["id"])

    # 2. ILIKE prefix match
    row = db.fetch_one(
        """
        SELECT id FROM drugs
        WHERE LOWER(generic_name) ILIKE %s
          AND record_status IS DISTINCT FROM 'excluded'
          AND record_status IS DISTINCT FROM 'merged'
        ORDER BY LENGTH(generic_name)
        LIMIT 1
        """,
        [f"{clean}%"],
    )
    if row:
        return str(row["id"])

    return None


def match_drugs(db: Database, pricing_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Match GPRM records to existing drugs in our DB.

    Adds a 'drug_id' field to each record (UUID string or None).
    Returns all records (matched and unmatched).
    """
    matched = []
    for record in pricing_records:
        drug_id = _match_drug_name(db, record["drug_name"])
        record_with_id = {**record, "drug_id": drug_id}
        matched.append(record_with_id)
    return matched


# ── Storage ──

def _store_one(db: Database, record: dict[str, Any]) -> None:
    """Insert a single GPRM pricing record into drug_pricing."""
    db.execute(
        """
        INSERT INTO drug_pricing
            (drug_id, drug_name, ndc_code, price_type, unit_price, unit,
             currency, country, source_api, source_url, effective_date)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            record.get("drug_id"),
            record["drug_name"],
            None,  # ndc_code is US-only, not applicable for GPRM
            record["price_type"],
            record["unit_price"],
            record["unit"],
            record["currency"],
            record["country"],
            record["source_api"],
            record.get("source_url"),
            record.get("effective_date"),
        ],
    )


def store_pricing(db: Database, matched_records: list[dict[str, Any]],
                  dry_run: bool = False) -> dict[str, Any]:
    """Store matched pricing records in drug_pricing table.

    Args:
        db: Database connection.
        matched_records: Records with drug_id already set.
        dry_run: If True, count but don't write to DB.

    Returns:
        Summary dict with stored count, country stats.
    """
    stored = 0
    countries_seen: set[str] = set()

    for record in matched_records:
        country = record.get("country", "")
        if country:
            countries_seen.add(country)

        if not dry_run:
            _store_one(db, record)
            stored += 1
        else:
            logger.debug(
                "[DRY RUN] Would store: %s (%s, %s %.4f, drug_id=%s)",
                record["drug_name"], record.get("country", "?"),
                record.get("currency", "?"), record["unit_price"],
                record.get("drug_id") or "NULL",
            )

    return {
        "stored": stored,
        "countries": len(countries_seen),
        "country_list": sorted(countries_seen),
    }


# ── Data loading ──

def _load_csv(path: str) -> list[dict[str, Any]]:
    """Load GPRM data from a CSV file.

    Expected columns: medicine_name, dosage_form, strength, country,
    price_per_unit, currency, price_type, year, atc_code
    """
    records = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Convert price_per_unit to float if present
            if "price_per_unit" in row and row["price_per_unit"]:
                try:
                    row["price_per_unit"] = float(row["price_per_unit"])
                except (ValueError, TypeError):
                    row["price_per_unit"] = None
            else:
                row["price_per_unit"] = None

            # Convert year to int if present
            if "year" in row and row["year"]:
                try:
                    row["year"] = int(row["year"])
                except (ValueError, TypeError):
                    row["year"] = None
            else:
                row["year"] = None

            records.append(row)
    return records


def _load_json(path: str) -> list[dict[str, Any]]:
    """Load GPRM data from a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Support both raw array and {"results": [...]} wrapper
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "results" in data:
        return data["results"]
    return []


def load_data(data_path: str) -> list[dict[str, Any]]:
    """Load GPRM data from a CSV or JSON file.

    Detects format by file extension.
    """
    path = Path(data_path)
    ext = path.suffix.lower()

    if ext == ".csv":
        return _load_csv(data_path)
    elif ext in (".json", ".jsonl"):
        return _load_json(data_path)
    else:
        raise ValueError(f"Unsupported file format: {ext} (use .csv or .json)")


# ── Main entry point ──

def run(dry_run: bool = False, data_path: str | None = None) -> dict[str, Any]:
    """Main entry point. If data_path provided, load from CSV/JSON file.

    Args:
        dry_run: If True, parse and match but don't write to DB.
        data_path: Path to CSV or JSON file with GPRM data.

    Returns:
        Summary dict with counts: fetched, parsed, matched, stored, countries.
    """
    if not data_path:
        raise ValueError("data_path is required — WHO GPRM data must be loaded from a file")

    db = Database(config.db.dsn)
    db.connect()

    try:
        raw_records = load_data(data_path)
        logger.info("Loaded %d raw GPRM records from %s", len(raw_records), data_path)

        parsed = parse_gprm_records(raw_records)
        logger.info("Parsed %d valid pricing records (%d skipped)",
                     len(parsed), len(raw_records) - len(parsed))

        matched = match_drugs(db, parsed)
        matched_count = sum(1 for r in matched if r.get("drug_id"))
        unmatched_count = len(matched) - matched_count

        store_stats = store_pricing(db, matched, dry_run=dry_run)

        stats = {
            "fetched": len(raw_records),
            "parsed": len(parsed),
            "matched": matched_count,
            "unmatched": unmatched_count,
            "stored": store_stats["stored"],
            "countries": store_stats["countries"],
            "country_list": store_stats["country_list"],
        }

        logger.info(
            "GPRM complete: %d fetched, %d parsed, %d matched, %d stored, %d countries",
            stats["fetched"], stats["parsed"], stats["matched"],
            stats["stored"], stats["countries"],
        )
        return stats
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Fetch WHO GPRM international drug pricing")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--data-path", required=True,
                        help="Path to CSV or JSON file with GPRM data")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    stats = run(dry_run=args.dry_run, data_path=args.data_path)
    print("\n=== WHO GPRM International Pricing Results ===")
    for k, v in stats.items():
        if k == "country_list":
            print(f"  {k}: {', '.join(v)}")
        else:
            print(f"  {k}: {v}")
    if args.dry_run:
        print("  (dry run -- no changes written)")


if __name__ == "__main__":
    main()
