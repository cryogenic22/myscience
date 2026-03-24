"""Fetch CMS NADAC drug pricing data and store in drug_pricing table.

The CMS National Average Drug Acquisition Cost (NADAC) provides
per-unit pricing for drugs reimbursed by Medicaid. This script
fetches the latest NADAC data, matches drugs to the existing drugs
table by generic name, and stores pricing records.

Usage:
    python -m scripts.fetch_nadac_pricing [--dry-run] [--limit 5000]
"""

from __future__ import annotations

import argparse
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

from config import config
from db import Database

logger = logging.getLogger(__name__)

NADAC_API_URL = "https://data.medicaid.gov/resource/4j6z-xnwq.json"
DEFAULT_PAGE_SIZE = 1000
DEFAULT_LIMIT = 5000


# ── Parsing helpers ──

def extract_drug_name(ndc_description: str) -> str:
    """Extract clean drug name from NDC description.

    NDC descriptions follow the pattern:
        "METFORMIN HCL 500MG TABLETS"
        "ATORVASTATIN CALCIUM 10MG TAB"
        "LISINOPRIL 20 MG TABLETS"

    We strip dosage forms, strengths, and common suffixes.
    """
    if not ndc_description:
        return ""

    text = ndc_description.strip().upper()

    # Remove common dosage forms at end
    dosage_forms = [
        r"\s+TABLETS?$", r"\s+CAPS?(ULES?)?$", r"\s+TAB$",
        r"\s+SOLN?$", r"\s+SOLUTION$", r"\s+INJECTABLE$",
        r"\s+INJ$", r"\s+ORAL$", r"\s+SUSPENSION$",
        r"\s+SUSP$", r"\s+CREAM$", r"\s+OINTMENT$",
        r"\s+GEL$", r"\s+PATCH(ES)?$", r"\s+SPRAY$",
        r"\s+DROPS?$", r"\s+SYRUP$", r"\s+POWDER$",
        r"\s+VIAL$", r"\s+PEN$", r"\s+INHALATION$",
        r"\s+INHALER$", r"\s+SUPPOSITORY$", r"\s+LIQUID$",
        r"\s+ELIXIR$", r"\s+LOTION$", r"\s+OPHTHALMIC$",
        r"\s+NASAL$", r"\s+TOPICAL$", r"\s+RECTAL$",
        r"\s+CHEWABLE$", r"\s+ER$", r"\s+DR$", r"\s+XR$",
        r"\s+SR$", r"\s+CR$", r"\s+IR$", r"\s+LA$",
        r"\s+EXTENDED[- ]RELEASE$",
    ]
    for pattern in dosage_forms:
        text = re.sub(pattern, "", text)

    # Remove strength patterns (e.g., "500MG", "10 MG", "0.5MG/ML", "20MG/5ML")
    text = re.sub(r"\s+\d+[\.\d]*\s*(MG|MCG|ML|G|%|UNIT|IU)(/\d*\s*(MG|MCG|ML|G))?.*$", "", text)
    # Also handle leading strength like "500MG METFORMIN"
    text = re.sub(r"^\d+[\.\d]*\s*(MG|MCG|ML|G|%|UNIT|IU)\s+", "", text)

    # Remove trailing HCL, SODIUM, CALCIUM etc. salt forms (keep for matching)
    # Actually, keep salt forms as they help matching — only strip trailing whitespace
    name = text.strip()

    # Title case for consistency
    if name:
        name = name.title()

    return name


def parse_nadac_record(record: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Parse a single NADAC API record into a drug_pricing row.

    Returns None if the record has missing critical fields (no price).
    """
    ndc = record.get("ndc", "")
    description = record.get("ndc_description", "")
    price_str = record.get("nadac_per_unit")
    as_of_date = record.get("as_of_date", "")
    pricing_unit = record.get("pricing_unit", "EA")
    classification = record.get("classification_for_rate_setting", "")

    # Skip records without price
    if not price_str:
        return None

    try:
        unit_price = float(price_str)
    except (ValueError, TypeError):
        return None

    # Parse effective date
    effective_date = None
    if as_of_date:
        try:
            # API returns ISO format: "2026-03-15T00:00:00.000"
            effective_date = datetime.fromisoformat(as_of_date.replace("T00:00:00.000", "")).date()
        except (ValueError, AttributeError):
            try:
                effective_date = datetime.strptime(as_of_date[:10], "%Y-%m-%d").date()
            except (ValueError, AttributeError):
                pass

    # Map pricing unit
    unit_map = {"EA": "per unit", "GM": "per gram", "ML": "per ml"}
    unit = unit_map.get(pricing_unit, f"per {pricing_unit.lower()}" if pricing_unit else "per unit")

    drug_name = extract_drug_name(description)

    return {
        "drug_name": drug_name or description,
        "ndc_code": ndc,
        "price_type": "nadac",
        "unit_price": unit_price,
        "unit": unit,
        "currency": "USD",
        "country": "US",
        "source_api": "cms_nadac",
        "source_url": NADAC_API_URL,
        "effective_date": effective_date,
        "ndc_description": description,
        "classification": classification,
    }


def parse_nadac_response(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse a list of raw NADAC API records.

    Skips records with missing prices. Returns structured dicts
    ready for drug matching and DB insertion.
    """
    parsed = []
    for record in records:
        result = parse_nadac_record(record)
        if result is not None:
            parsed.append(result)
    return parsed


def match_drug_name(db: Database, drug_name: str) -> Optional[str]:
    """Match a drug name to an existing drug in the drugs table.

    Uses exact match on generic_name first, then ILIKE prefix match.
    Returns the drug UUID or None.
    """
    if not drug_name:
        return None

    clean = drug_name.strip().lower()

    # 1. Exact match on generic_name (case-insensitive)
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

    # 2. Prefix match — NADAC names often have salt forms
    # e.g., "Metformin Hcl" should match "metformin"
    # Try stripping common salt suffixes
    salt_suffixes = [
        " hcl", " hydrochloride", " sodium", " potassium",
        " calcium", " maleate", " fumarate", " mesylate",
        " besylate", " tartrate", " succinate", " phosphate",
        " acetate", " sulfate", " nitrate", " citrate",
        " bromide", " chloride",
    ]
    base_name = clean
    for suffix in salt_suffixes:
        if base_name.endswith(suffix):
            base_name = base_name[: -len(suffix)].strip()
            break

    if base_name != clean:
        row = db.fetch_one(
            """
            SELECT id FROM drugs
            WHERE LOWER(generic_name) = %s
              AND record_status IS DISTINCT FROM 'excluded'
              AND record_status IS DISTINCT FROM 'merged'
            LIMIT 1
            """,
            [base_name],
        )
        if row:
            return str(row["id"])

    # 3. ILIKE prefix match as last resort
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


def fetch_nadac_page(offset: int = 0, page_size: int = DEFAULT_PAGE_SIZE,
                     since_date: str = "2026-01-01") -> list[dict]:
    """Fetch one page of NADAC data from the CMS API."""
    import requests

    params = {
        "$where": f"as_of_date > '{since_date}'",
        "$limit": str(page_size),
        "$offset": str(offset),
        "$order": "as_of_date DESC",
    }

    resp = requests.get(NADAC_API_URL, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def store_pricing_record(db: Database, record: dict[str, Any], drug_id: Optional[str]) -> None:
    """Insert a single pricing record into drug_pricing."""
    db.execute(
        """
        INSERT INTO drug_pricing
            (drug_id, drug_name, ndc_code, price_type, unit_price, unit,
             currency, country, source_api, source_url, effective_date)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            drug_id,
            record["drug_name"],
            record["ndc_code"],
            record["price_type"],
            record["unit_price"],
            record["unit"],
            record["currency"],
            record["country"],
            record["source_api"],
            record["source_url"],
            record["effective_date"],
        ],
    )


def fetch_nadac(db: Database, limit: int = DEFAULT_LIMIT,
                dry_run: bool = False, since_date: str = "2026-01-01") -> dict:
    """Fetch latest NADAC prices and store in drug_pricing table.

    Args:
        db: Database connection.
        limit: Maximum total records to fetch.
        dry_run: If True, parse and match but don't write to DB.
        since_date: Only fetch prices after this date.

    Returns:
        Summary dict with counts of fetched, matched, stored, skipped records.
    """
    stats = {
        "pages_fetched": 0,
        "raw_records": 0,
        "parsed": 0,
        "matched": 0,
        "unmatched": 0,
        "stored": 0,
        "skipped_no_price": 0,
    }

    offset = 0
    all_parsed: list[dict] = []

    while offset < limit:
        page_size = min(DEFAULT_PAGE_SIZE, limit - offset)
        try:
            raw_records = fetch_nadac_page(offset=offset, page_size=page_size,
                                           since_date=since_date)
        except Exception as e:
            logger.error("Failed to fetch NADAC page at offset %d: %s", offset, e)
            break

        stats["pages_fetched"] += 1
        stats["raw_records"] += len(raw_records)

        if not raw_records:
            break

        parsed = parse_nadac_response(raw_records)
        stats["parsed"] += len(parsed)
        stats["skipped_no_price"] += len(raw_records) - len(parsed)
        all_parsed.extend(parsed)

        offset += page_size

        if len(raw_records) < page_size:
            break  # Last page

    # Match and store
    for record in all_parsed:
        drug_id = match_drug_name(db, record["drug_name"])

        if drug_id:
            stats["matched"] += 1
        else:
            stats["unmatched"] += 1

        if not dry_run:
            store_pricing_record(db, record, drug_id)
            stats["stored"] += 1
        else:
            logger.debug(
                "[DRY RUN] Would store: %s (NDC=%s, price=$%.4f, drug_id=%s)",
                record["drug_name"], record["ndc_code"],
                record["unit_price"], drug_id or "NULL",
            )

    return stats


def run(dry_run: bool = False, limit: int = DEFAULT_LIMIT) -> dict:
    """Main entry point for auto_curate integration."""
    db = Database(config.db.dsn)
    db.connect()

    try:
        stats = fetch_nadac(db, limit=limit, dry_run=dry_run)
        logger.info(
            "NADAC fetch complete: %d raw, %d parsed, %d matched, %d stored",
            stats["raw_records"], stats["parsed"], stats["matched"], stats["stored"],
        )
        return stats
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Fetch CMS NADAC drug pricing")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Max records to fetch")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    stats = run(dry_run=args.dry_run, limit=args.limit)
    print("\n=== NADAC Pricing Fetch Results ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    if args.dry_run:
        print("  (dry run -- no changes written)")


if __name__ == "__main__":
    main()
