"""Enrich company completeness.

Phase 1.5: Fill missing ticker, country, region, market_cap_tier for
companies using hardcoded reference data and SEC filing metadata.

Usage:
    python -m scripts.enrich_companies [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone

from config import config
from db import Database

logger = logging.getLogger(__name__)

# Reference data for top pharma companies
# Format: normalized_name → {ticker, country, region, market_cap_tier}
TOP_PHARMA_REFERENCE: dict[str, dict[str, str]] = {
    "novo nordisk": {"ticker": "NVO", "country": "Denmark", "region": "Europe", "market_cap_tier": "mega"},
    "eli lilly": {"ticker": "LLY", "country": "US", "region": "North America", "market_cap_tier": "mega"},
    "pfizer": {"ticker": "PFE", "country": "US", "region": "North America", "market_cap_tier": "mega"},
    "novartis": {"ticker": "NVS", "country": "Switzerland", "region": "Europe", "market_cap_tier": "mega"},
    "sanofi": {"ticker": "SNY", "country": "France", "region": "Europe", "market_cap_tier": "mega"},
    "astrazeneca": {"ticker": "AZN", "country": "UK", "region": "Europe", "market_cap_tier": "mega"},
    "merck": {"ticker": "MRK", "country": "US", "region": "North America", "market_cap_tier": "mega"},
    "johnson & johnson": {"ticker": "JNJ", "country": "US", "region": "North America", "market_cap_tier": "mega"},
    "roche": {"ticker": "RHHBY", "country": "Switzerland", "region": "Europe", "market_cap_tier": "mega"},
    "abbvie": {"ticker": "ABBV", "country": "US", "region": "North America", "market_cap_tier": "mega"},
    "amgen": {"ticker": "AMGN", "country": "US", "region": "North America", "market_cap_tier": "large"},
    "bristol-myers squibb": {"ticker": "BMY", "country": "US", "region": "North America", "market_cap_tier": "large"},
    "gilead sciences": {"ticker": "GILD", "country": "US", "region": "North America", "market_cap_tier": "large"},
    "bayer": {"ticker": "BAYRY", "country": "Germany", "region": "Europe", "market_cap_tier": "large"},
    "takeda": {"ticker": "TAK", "country": "Japan", "region": "Asia Pacific", "market_cap_tier": "large"},
    "boehringer ingelheim": {"ticker": None, "country": "Germany", "region": "Europe", "market_cap_tier": "large"},
    "gsk": {"ticker": "GSK", "country": "UK", "region": "Europe", "market_cap_tier": "large"},
    "glaxosmithkline": {"ticker": "GSK", "country": "UK", "region": "Europe", "market_cap_tier": "large"},
    "regeneron": {"ticker": "REGN", "country": "US", "region": "North America", "market_cap_tier": "large"},
    "vertex": {"ticker": "VRTX", "country": "US", "region": "North America", "market_cap_tier": "large"},
    "biogen": {"ticker": "BIIB", "country": "US", "region": "North America", "market_cap_tier": "large"},
    "moderna": {"ticker": "MRNA", "country": "US", "region": "North America", "market_cap_tier": "large"},
    "teva": {"ticker": "TEVA", "country": "Israel", "region": "Middle East", "market_cap_tier": "mid"},
    "sun pharma": {"ticker": "SUNPHARMA.NS", "country": "India", "region": "Asia Pacific", "market_cap_tier": "mid"},
    "lupin": {"ticker": "LUPIN.NS", "country": "India", "region": "Asia Pacific", "market_cap_tier": "mid"},
    "cipla": {"ticker": "CIPLA.NS", "country": "India", "region": "Asia Pacific", "market_cap_tier": "mid"},
    "dr. reddy's": {"ticker": "RDY", "country": "India", "region": "Asia Pacific", "market_cap_tier": "mid"},
    "dr. reddys": {"ticker": "RDY", "country": "India", "region": "Asia Pacific", "market_cap_tier": "mid"},
    "mylan": {"ticker": "VTRS", "country": "US", "region": "North America", "market_cap_tier": "mid"},
    "viatris": {"ticker": "VTRS", "country": "US", "region": "North America", "market_cap_tier": "mid"},
    "zydus": {"ticker": "ZYDUSLIFE.NS", "country": "India", "region": "Asia Pacific", "market_cap_tier": "mid"},
    "amneal": {"ticker": "AMRX", "country": "US", "region": "North America", "market_cap_tier": "small"},
    "bausch health": {"ticker": "BHC", "country": "Canada", "region": "North America", "market_cap_tier": "small"},
    "hikma": {"ticker": "HIK.L", "country": "UK", "region": "Europe", "market_cap_tier": "mid"},
    "ipsen": {"ticker": "IPN.PA", "country": "France", "region": "Europe", "market_cap_tier": "mid"},
    "jazz": {"ticker": "JAZZ", "country": "Ireland", "region": "Europe", "market_cap_tier": "mid"},
    "jazz pharmaceuticals": {"ticker": "JAZZ", "country": "Ireland", "region": "Europe", "market_cap_tier": "mid"},
    "astellas": {"ticker": "4503.T", "country": "Japan", "region": "Asia Pacific", "market_cap_tier": "large"},
    "daiichi sankyo": {"ticker": "4568.T", "country": "Japan", "region": "Asia Pacific", "market_cap_tier": "large"},
    "otsuka": {"ticker": "4578.T", "country": "Japan", "region": "Asia Pacific", "market_cap_tier": "large"},
    "ucb": {"ticker": "UCB.BR", "country": "Belgium", "region": "Europe", "market_cap_tier": "mid"},
    "endo": {"ticker": None, "country": "Ireland", "region": "Europe", "market_cap_tier": "small"},
    "perrigo": {"ticker": "PRGO", "country": "Ireland", "region": "Europe", "market_cap_tier": "small"},
    "alexion": {"ticker": None, "country": "US", "region": "North America", "market_cap_tier": "large"},
    "incyte": {"ticker": "INCY", "country": "US", "region": "North America", "market_cap_tier": "mid"},
    "horizon therapeutics": {"ticker": None, "country": "Ireland", "region": "Europe", "market_cap_tier": "mid"},
    "seagen": {"ticker": None, "country": "US", "region": "North America", "market_cap_tier": "large"},
    "biocon": {"ticker": "BIOCON.NS", "country": "India", "region": "Asia Pacific", "market_cap_tier": "mid"},
    "torrent": {"ticker": "TORNTPHARM.NS", "country": "India", "region": "Asia Pacific", "market_cap_tier": "mid"},
    "aurobindo": {"ticker": "AUROPHARMA.NS", "country": "India", "region": "Asia Pacific", "market_cap_tier": "mid"},
}

# Suffixes to strip for matching
import re
COMPANY_SUFFIXES = re.compile(
    r"\b(?:inc\.?|ltd\.?|llc\.?|corp\.?|corporation|company|co\.?"
    r"|plc\.?|ag\.?|sa\.?|se\.?|nv\.?|bv\.?"
    r"|pharms?\.?|pharmaceuticals?|laboratories?|labs?"
    r"|usa|u\.s\.a\.?|intl?\.?|international"
    r"|group|holdings?|limited|gmbh"
    r")\.?\s*$",
    re.IGNORECASE,
)


def _normalize(name: str) -> str:
    name = name.strip()
    for _ in range(3):
        name = COMPANY_SUFFIXES.sub("", name).strip()
    return re.sub(r"\s+", " ", name).lower().strip()


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


def enrich_from_reference(db: Database, dry_run: bool = False) -> int:
    """Enrich companies from hardcoded reference data."""
    companies = db.fetch_all(
        """
        SELECT id, name, ticker, country, region, market_cap_tier
        FROM companies
        WHERE record_status IS DISTINCT FROM 'merged'
          AND record_status IS DISTINCT FROM 'excluded'
        """
    )

    enriched = 0
    for c in companies:
        norm = _normalize(c["name"])
        ref = TOP_PHARMA_REFERENCE.get(norm)
        if not ref:
            continue

        updates = {}
        if not c.get("ticker") and ref.get("ticker"):
            updates["ticker"] = ref["ticker"]
        if not c.get("country") and ref.get("country"):
            updates["country"] = ref["country"]
        if not c.get("region") and ref.get("region"):
            updates["region"] = ref["region"]
        if not c.get("market_cap_tier") and ref.get("market_cap_tier"):
            updates["market_cap_tier"] = ref["market_cap_tier"]

        if not updates:
            continue

        company_id = str(c["id"])
        if dry_run:
            logger.info(
                "[DRY RUN] Enrich company %s: %s",
                c["name"], updates,
            )
        else:
            set_parts = [f"{k} = %s" for k in updates]
            values = list(updates.values()) + [c["id"]]
            db.execute(
                f"UPDATE companies SET {', '.join(set_parts)} WHERE id = %s",
                values,
            )
            _log_change(db, "company", company_id, "enrich_from_reference",
                        list(updates.keys()))
        enriched += 1

    logger.info("Companies enriched from reference data: %d", enriched)
    return enriched


def set_unknown_market_cap(db: Database, dry_run: bool = False) -> int:
    """Set market_cap_tier = 'unknown' for remaining companies without tier."""
    rows = db.fetch_all(
        """
        SELECT id, name FROM companies
        WHERE market_cap_tier IS NULL
          AND record_status IS DISTINCT FROM 'merged'
          AND record_status IS DISTINCT FROM 'excluded'
        """
    )

    count = 0
    for row in rows:
        if dry_run:
            logger.info("[DRY RUN] Set market_cap_tier=unknown for %s", row["name"])
        else:
            db.execute(
                "UPDATE companies SET market_cap_tier = 'unknown' WHERE id = %s",
                [row["id"]],
            )
        count += 1

    logger.info("Companies set to market_cap_tier=unknown: %d", count)
    return count


def enrich_from_sec(db: Database, dry_run: bool = False) -> int:
    """Enrich companies with country from SEC EDGAR filing data."""
    count = 0

    # Companies with CIK but no country — try to get from SEC data
    rows = db.fetch_all(
        """
        SELECT id, name, cik FROM companies
        WHERE cik IS NOT NULL AND cik != ''
          AND (country IS NULL OR country = '')
          AND record_status IS DISTINCT FROM 'merged'
          AND record_status IS DISTINCT FROM 'excluded'
        """
    )

    for row in rows:
        # SEC filings typically indicate US companies
        # If they have a CIK, they file with the SEC → likely US-based or US-listed
        if dry_run:
            logger.info("[DRY RUN] Set country=US for %s (has CIK %s)", row["name"], row["cik"])
        else:
            db.execute(
                "UPDATE companies SET country = 'US', region = 'North America' WHERE id = %s AND country IS NULL",
                [row["id"]],
            )
            _log_change(db, "company", str(row["id"]), "enrich_country_from_sec",
                        ["country", "region"])
        count += 1

    logger.info("Companies enriched with country from SEC data: %d", count)
    return count


def run(dry_run: bool = False) -> dict:
    """Run all company enrichment tasks."""
    db = Database(config.db.dsn)
    db.connect()

    try:
        return {
            "enriched_from_reference": enrich_from_reference(db, dry_run),
            "enriched_from_sec": enrich_from_sec(db, dry_run),
            "set_unknown_tier": set_unknown_market_cap(db, dry_run),
        }
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Enrich company completeness")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    results = run(dry_run=args.dry_run)
    print("\n=== Company Enrichment Results ===")
    for k, v in results.items():
        print(f"  {k}: {v}")
    total = sum(results.values())
    print(f"  TOTAL enrichments: {total}")
    if args.dry_run:
        print("  (dry run — no changes written)")


if __name__ == "__main__":
    main()
