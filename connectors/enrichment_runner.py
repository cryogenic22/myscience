"""
Enrichment Runner — lightweight orchestrator for deterministic data enrichment.

Runs enrichment modules in priority order with zero LLM cost:
  1. Resolution sweep — re-match unresolved entities against current DB
  2. Company enrichment — backfill CIK/ticker from SEC EDGAR public JSON

Each module returns an EnrichmentResult with counts and diagnostics.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class EnrichmentResult:
    total: int
    matched: int
    source: str
    errors: int = 0
    details: str = ""


class EnrichmentRunner:
    """Orchestrates deterministic data enrichment with zero LLM cost."""

    def __init__(self, db):
        self.db = db

    def run_resolution_sweep(self, batch_size: int = 500) -> EnrichmentResult:
        """Re-process unresolved entities against current DB."""
        try:
            unresolved = self.db.fetch_all("""
                SELECT id, entity_type, raw_value, suggested_match_id, similarity_score
                FROM unresolved_entities
                WHERE status = 'pending'
                ORDER BY similarity_score DESC NULLS LAST
                LIMIT %s
            """, [batch_size])
        except Exception as e:
            return EnrichmentResult(total=0, matched=0, source="resolution_sweep", errors=1, details=str(e))

        resolved = 0
        for entry in unresolved:
            try:
                from domain.pharma.mention_normalizer import normalize_drug_mention, normalize_company_mention

                raw = entry["raw_value"]
                etype = entry["entity_type"]

                if etype == "drug":
                    cleaned = normalize_drug_mention(raw)
                elif etype == "company":
                    cleaned = normalize_company_mention(raw)
                else:
                    cleaned = raw.strip().lower()

                if not cleaned:
                    continue

                # Map entity type to table/column for lookup
                table = {"drug": "drugs", "company": "companies"}.get(etype)
                name_col = {"drug": "generic_name", "company": "company_name"}.get(etype)
                if not table or not name_col:
                    continue

                match = self.db.fetch_one(
                    f"SELECT id FROM {table} WHERE LOWER({name_col}) = LOWER(%s)",
                    [cleaned],
                )

                if match:
                    self.db.execute("""
                        UPDATE unresolved_entities
                        SET status = 'resolved', resolved_entity_id = %s, resolved_at = NOW()
                        WHERE id = %s
                    """, [match["id"], entry["id"]])
                    resolved += 1
            except Exception:
                continue

        return EnrichmentResult(
            total=len(unresolved),
            matched=resolved,
            source="resolution_sweep",
            details=f"Processed {len(unresolved)} unresolved, resolved {resolved}",
        )

    def run_company_enrichment(self) -> EnrichmentResult:
        """Enrich companies with SEC EDGAR CIK/ticker from public JSON."""
        import requests

        try:
            resp = requests.get(
                "https://www.sec.gov/files/company_tickers.json",
                headers={"User-Agent": "MarketZero research@marketzero.ai"},
                timeout=30,
            )
            resp.raise_for_status()
            tickers_raw = resp.json()

            # Build lookup: lowercase company name -> {cik, ticker}
            ticker_map = {}
            for entry in tickers_raw.values():
                name = entry.get("title", "").lower().strip()
                if name:
                    ticker_map[name] = {
                        "cik": str(entry.get("cik_str", "")),
                        "ticker": entry.get("ticker", ""),
                    }
        except Exception as e:
            return EnrichmentResult(total=0, matched=0, source="sec_edgar_tickers", errors=1, details=str(e))

        companies = self.db.fetch_all(
            "SELECT id, company_name FROM companies WHERE (cik IS NULL OR cik = '') LIMIT 500"
        )

        matched = 0
        for company in companies:
            name = company["company_name"].lower().strip()
            match = ticker_map.get(name)
            if not match:
                # Strip common suffixes and retry
                cleaned = re.sub(
                    r"\s*(inc\.?|corp\.?|ltd\.?|plc|co\.?|llc|a/s|ag|sa|se)\s*$",
                    "",
                    name,
                    flags=re.I,
                ).strip()
                match = ticker_map.get(cleaned)
            if match and match["cik"]:
                try:
                    self.db.execute(
                        "UPDATE companies SET cik = %s, ticker = %s WHERE id = %s AND (cik IS NULL OR cik = '')",
                        [match["cik"], match["ticker"], company["id"]],
                    )
                    matched += 1
                except Exception:
                    continue

        return EnrichmentResult(
            total=len(companies),
            matched=matched,
            source="sec_edgar_tickers",
            details=f"Checked {len(companies)} companies, enriched {matched}",
        )

    def run_all(self) -> list[EnrichmentResult]:
        """Run all enrichment modules in priority order."""
        results = []

        logger.info("Starting enrichment run...")

        # Priority 1: Resolution sweep
        r = self.run_resolution_sweep(batch_size=500)
        results.append(r)
        logger.info("Resolution sweep: %d/%d resolved", r.matched, r.total)

        # Priority 2: Company CIK/ticker
        r = self.run_company_enrichment()
        results.append(r)
        logger.info("Company enrichment: %d/%d matched", r.matched, r.total)

        logger.info("Enrichment complete: %d total enriched", sum(r.matched for r in results))
        return results
