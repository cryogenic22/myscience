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

# Legacy Socrata endpoint (DEAD — CMS migrated to the DKAN portal in 2025/26).
# Kept only as a back-compat label; live data now comes from the DKAN CSV below.
NADAC_API_URL = "https://data.medicaid.gov/resource/4j6z-xnwq.json"

# DKAN metastore: NADAC is published as one dataset per year ("NADAC (National
# Average Drug Acquisition Cost) <year>"); each year's distribution is the latest
# WEEKLY CSV snapshot. We resolve the current-year CSV download URL dynamically —
# the filename carries the week's date and changes weekly, so never hardcode it.
NADAC_DKAN_SEARCH = "https://data.medicaid.gov/api/1/search/"
NADAC_DATASET_PREFIX = "NADAC (National Average Drug Acquisition Cost)"
# medicaid.gov bot-blocks default UAs (same lesson as the news feed, #229).
_BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
DEFAULT_PAGE_SIZE = 1000
# A weekly NADAC snapshot is ~28k NDCs; default high enough to ingest the full
# current price list (the scheduled post-task pulls all of it, idempotently).
DEFAULT_LIMIT = 50000


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


def _norm_keys(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize a NADAC record's keys to canonical lowercase_underscore, so the
    same parser handles BOTH the DKAN CSV headers ("NDC", "NADAC Per Unit",
    "Effective Date", "Pricing Unit", "As of Date") and the legacy Socrata JSON
    keys (already lowercase_underscore). Back-compat: a Socrata record passes
    through unchanged."""
    return {k.strip().lower().replace(" ", "_"): v for k, v in record.items()}


def _parse_nadac_date(value: Any) -> Optional["date"]:
    """Parse a NADAC date from any of the formats the source uses:
    ISO ("2026-03-15T00:00:00.000" / "2026-03-15", legacy Socrata) or
    US "MM/DD/YYYY" (DKAN CSV). Returns None if unparseable (never raises)."""
    if not value:
        return None
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(s[:10] if fmt == "%Y-%m-%d" else s, fmt).date()
        except (ValueError, AttributeError):
            continue
    try:
        return datetime.fromisoformat(s.replace("T00:00:00.000", "")).date()
    except (ValueError, AttributeError):
        return None


def parse_nadac_record(record: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Parse a single NADAC record (DKAN CSV row OR legacy Socrata JSON) into a
    drug_pricing row. Returns None if the record has no usable price.

    The effective date is the price's "Effective Date" (when this NDC's price
    last changed) — the right history key. Legacy Socrata records carry only
    "as_of_date" (publication date), so we fall back to it for back-compat.
    """
    r = _norm_keys(record)
    ndc = r.get("ndc", "")
    description = r.get("ndc_description", "")
    price_str = r.get("nadac_per_unit")
    pricing_unit = r.get("pricing_unit") or "EA"
    classification = r.get("classification_for_rate_setting", "")

    # Skip records without price
    if price_str in (None, "", "N/A"):
        return None

    try:
        unit_price = float(price_str)
    except (ValueError, TypeError):
        return None

    # Effective Date (price validity) is the history key; fall back to As of Date
    # (publication) for legacy Socrata records that lack an effective_date column.
    effective_date = _parse_nadac_date(r.get("effective_date") or r.get("as_of_date"))

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


def resolve_current_nadac_csv_url(year: Optional[int] = None,
                                  *, session=None) -> Optional[str]:
    """Resolve the current-year NADAC dataset's latest CSV download URL from the
    CMS DKAN metastore. The weekly filename changes, so we never hardcode it.

    Returns None if no dataset/CSV is found (caller treats as a soft no-data run,
    not a crash). Falls back to the previous year (handles early January, before
    the new year's first weekly file is published)."""
    import requests
    session = session or requests
    target_year = year or datetime.now(timezone.utc).year
    for candidate_year in (target_year, target_year - 1):
        title = f"{NADAC_DATASET_PREFIX} {candidate_year}"
        try:
            resp = session.get(
                NADAC_DKAN_SEARCH,
                params={"fulltext": f"NADAC {candidate_year}", "page-size": 30},
                headers={"User-Agent": _BROWSER_UA}, timeout=30,
            )
            resp.raise_for_status()
            results = resp.json().get("results") or {}
            items = results.values() if isinstance(results, dict) else results
        except Exception as e:
            logger.warning("NADAC DKAN search failed for %s: %s", candidate_year, e)
            continue
        for item in items:
            if (item.get("title") or "").strip() != title:
                continue
            for dist in item.get("distribution") or []:
                d = dist.get("data", dist)
                url = d.get("downloadURL") or d.get("accessURL")
                if url and str(url).lower().endswith(".csv"):
                    logger.info("NADAC current CSV (%s): %s", candidate_year, url)
                    return url
    logger.warning("NADAC: no current-year CSV distribution found via DKAN")
    return None


def fetch_nadac_rows(since: Optional[datetime] = None, *,
                     limit: int = DEFAULT_LIMIT, session=None) -> list[dict]:
    """Download the current weekly NADAC CSV snapshot and return raw row dicts
    (CSV headers preserved; parse_nadac_record normalizes them). Bounded by
    `limit`; `since` keeps only rows whose Effective Date is on/after it."""
    import csv
    import requests
    session = session or requests

    url = resolve_current_nadac_csv_url(session=session)
    if not url:
        return []
    try:
        # Stream + stop at `limit`: the weekly CSV is ~28k rows / multi-MB, so we
        # avoid loading it all into memory and close the connection once we have
        # enough (a bounded pull downloads only what it reads).
        resp = session.get(url, headers={"User-Agent": _BROWSER_UA},
                           timeout=120, stream=True)
        resp.raise_for_status()
        # iter_lines(decode_unicode=True) yields bytes unless an encoding is set
        # (the server often omits the charset) — pin UTF-8 so csv gets str.
        resp.encoding = resp.encoding or "utf-8"
        lines = resp.iter_lines(decode_unicode=True)
    except Exception as e:
        logger.error("NADAC CSV download failed (%s): %s", url, e)
        return []

    rows: list[dict] = []
    try:
        reader = csv.DictReader(lines)
        for raw in reader:
            if since is not None:
                eff = _parse_nadac_date(raw.get("Effective Date") or raw.get("effective_date"))
                if eff is not None and eff < since.date():
                    continue
            rows.append(raw)
            if len(rows) >= limit:
                break
    finally:
        resp.close()
    logger.info("NADAC: read %d rows from %s", len(rows), url)
    return rows


def store_pricing_record(db: Database, record: dict[str, Any], drug_id: Optional[str]) -> None:
    """Insert a pricing record into drug_pricing, idempotently.

    ON CONFLICT on the history key (ndc_code, price_type, effective_date,
    source_api) DO NOTHING — re-pulling an unchanged weekly snapshot is a no-op;
    only a genuinely new (NDC, effective_date) lands a new history row (mig 095)."""
    db.execute(
        """
        INSERT INTO drug_pricing
            (drug_id, drug_name, ndc_code, price_type, unit_price, unit,
             currency, country, source_api, source_url, effective_date)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (ndc_code, price_type, effective_date, source_api) DO NOTHING
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
                dry_run: bool = False, since_date: Optional[str] = None) -> dict:
    """Fetch the current weekly NADAC snapshot and store in drug_pricing.

    Args:
        db: Database connection.
        limit: Maximum total records to fetch.
        dry_run: If True, parse and match but don't write to DB.
        since_date: Optional 'YYYY-MM-DD'. The NADAC file is a SNAPSHOT of all
            current prices, so by default (None) we ingest the full snapshot and
            let the idempotent upsert dedupe — filtering by Effective Date would
            wrongly drop prices that are current but last changed before the date.

    Returns:
        Summary dict with counts of fetched, matched, stored, skipped records.
    """
    stats = {
        "raw_records": 0,
        "parsed": 0,
        "matched": 0,
        "unmatched": 0,
        "stored": 0,
        "skipped_no_price": 0,
    }

    since_dt = None
    if since_date:
        try:
            since_dt = datetime.strptime(since_date[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            since_dt = None

    raw_records = fetch_nadac_rows(since=since_dt, limit=limit)
    stats["raw_records"] = len(raw_records)
    all_parsed = parse_nadac_response(raw_records)
    stats["parsed"] = len(all_parsed)
    stats["skipped_no_price"] = len(raw_records) - len(all_parsed)

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
