"""Automated data curation pipeline v2 — 5-pass deterministic quality fixer.

Fixes the 5 biggest quality gaps:
  Pass 1: Company enrichment via SEC EDGAR (ticker, CIK)
  Pass 2: Orphan company linking (find trial sponsors)
  Pass 3: Resolution sweep with MentionNormalizer
  Pass 4: HITL auto-resolve (substring heuristic, no LLM)
  Pass 5: Compute and persist FAIR score

All operations are deterministic (no LLM cost) and idempotent.
Safe to run multiple times without creating duplicates.

Usage:
    python -m scripts.auto_curate_v2                 # CLI
    POST /enrichment/curate                          # API
"""

from __future__ import annotations

import argparse
import logging
import re
import time

import requests

from services.fair_scorer import FAIRScorer

logger = logging.getLogger(__name__)

# SEC EDGAR endpoint (free, ~2MB JSON, no API key required)
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_USER_AGENT = "MarketZero research@marketzero.ai"

# Company suffix pattern for name cleaning
_COMPANY_SUFFIX_RE = re.compile(
    r'\s*[,.]?\s*\b(inc\.?|corp\.?|corporation|ltd\.?|limited|plc|'
    r'co\.?|company|llc|l\.l\.c\.|gmbh|ag|sa|s\.a\.|nv|n\.v\.|'
    r'bv|b\.v\.|ab|a/s|se|pty|pvt|holdings|group)\b[,.\s]*$',
    re.IGNORECASE,
)


def _clean_company_name(name: str) -> str:
    """Strip company suffixes for matching. 'Pfizer Inc.' -> 'pfizer'."""
    cleaned = name.strip().lower()
    # Apply suffix stripping repeatedly to handle stacked suffixes
    for _ in range(3):
        prev = cleaned
        cleaned = _COMPANY_SUFFIX_RE.sub('', cleaned).strip()
        if cleaned == prev:
            break
    return cleaned.strip().rstrip(',. ')


# ═══════════════════════════════════════════════════════════════════════
# Pass 1: Company enrichment via SEC EDGAR
# ═══════════════════════════════════════════════════════════════════════


def enrich_companies_from_sec(db) -> dict:
    """Download SEC company_tickers.json and match against companies table.

    Updates ticker and cik fields for companies matched by cleaned name.
    Returns dict with total, enriched, pass keys.
    """
    try:
        resp = requests.get(
            SEC_TICKERS_URL,
            headers={"User-Agent": SEC_USER_AGENT},
            timeout=30,
        )
        resp.raise_for_status()
        tickers = resp.json()
    except Exception as e:
        logger.error("SEC EDGAR fetch failed: %s", e)
        return {"total": 0, "enriched": 0, "error": str(e), "pass": "company_sec"}

    # Build lookup: cleaned name -> {cik, ticker}
    ticker_map: dict[str, dict] = {}
    for entry in tickers.values():
        title = entry.get("title", "")
        if not title:
            continue
        name = _clean_company_name(title)
        if name:
            ticker_map[name] = {
                "cik": str(entry.get("cik_str", "")),
                "ticker": entry.get("ticker", ""),
            }

    companies = db.fetch_all(
        "SELECT id, name FROM companies WHERE (ticker IS NULL OR ticker = '') LIMIT 1000"
    )

    matched = 0
    for c in companies:
        clean = _clean_company_name(c["name"])
        if not clean:
            continue
        match = ticker_map.get(clean)
        if match and match["cik"]:
            db.execute(
                "UPDATE companies SET ticker=%s, cik=%s "
                "WHERE id=%s AND (ticker IS NULL OR ticker='')",
                [match["ticker"], match["cik"], c["id"]],
            )
            matched += 1

    logger.info("Pass 1 (SEC enrichment): %d/%d companies enriched", matched, len(companies))
    return {"total": len(companies), "enriched": matched, "pass": "company_sec"}


# ═══════════════════════════════════════════════════════════════════════
# Pass 2: Orphan company linking
# ═══════════════════════════════════════════════════════════════════════


def link_orphan_companies(db) -> dict:
    """Find companies with 0 entity_links and try to match as trial sponsors.

    Creates SPONSORS links with ON CONFLICT DO NOTHING for idempotency.
    """
    orphans = db.fetch_all("""
        SELECT c.id, c.name FROM companies c
        WHERE NOT EXISTS (
            SELECT 1 FROM entity_links
            WHERE source_entity_id = c.id::text OR target_entity_id = c.id::text
        )
    """)

    linked = 0
    for c in orphans:
        clean = _clean_company_name(c["name"])
        if len(clean) < 4:
            continue

        trials = db.fetch_all(
            "SELECT id FROM clinical_trials WHERE LOWER(sponsor_name) LIKE LOWER(%s) LIMIT 10",
            [f"%{clean}%"],
        )
        for t in trials:
            db.execute(
                """INSERT INTO entity_links
                   (source_entity_id, source_entity_type, target_entity_id,
                    target_entity_type, link_type, confidence, link_via, provenance_source)
                   VALUES (%s, 'company', %s, 'trial', 'SPONSORS', 0.8, %s, 'auto_curate_orphan')
                   ON CONFLICT DO NOTHING""",
                [c["id"], t["id"], f'orphan link: {c["name"]}'],
            )
            linked += 1

    logger.info("Pass 2 (orphan linking): %d links for %d orphan companies", linked, len(orphans))
    return {"orphans": len(orphans), "linked": linked, "pass": "orphan_companies"}


# ═══════════════════════════════════════════════════════════════════════
# Pass 3: Resolution sweep with MentionNormalizer
# ═══════════════════════════════════════════════════════════════════════


def resolution_sweep(db, batch_size: int = 500) -> dict:
    """Process pending unresolved entities using normalized name matching.

    Uses the existing MentionNormalizer to clean raw values, then matches
    against the drugs or companies table by normalized name.
    """
    from domain.pharma.mention_normalizer import (
        normalize_company_mention,
        normalize_drug_mention,
    )

    pending = db.fetch_all(
        """SELECT id, entity_type, raw_value FROM unresolved_entities
           WHERE status = 'pending' ORDER BY created_at LIMIT %s""",
        [batch_size],
    )

    resolved = 0
    for entry in pending:
        raw = entry["raw_value"]
        etype = entry.get("entity_type") or "drug"

        if etype == "company":
            cleaned = normalize_company_mention(raw)
        else:
            cleaned = normalize_drug_mention(raw)

        if not cleaned or len(cleaned) < 3:
            continue

        # Look up in the appropriate table
        if etype == "company":
            match = db.fetch_one(
                "SELECT id FROM companies WHERE LOWER(name) = LOWER(%s)",
                [cleaned],
            )
        else:
            match = db.fetch_one(
                "SELECT id FROM drugs WHERE LOWER(generic_name) = LOWER(%s)",
                [cleaned],
            )

        if match:
            db.execute(
                """UPDATE unresolved_entities
                   SET status='resolved', resolved=true, resolved_entity_id=%s,
                       resolved_at=NOW(), resolved_by='auto_curate_sweep'
                   WHERE id=%s""",
                [match["id"], entry["id"]],
            )
            resolved += 1

    logger.info("Pass 3 (resolution sweep): %d/%d resolved", resolved, len(pending))
    return {"processed": len(pending), "resolved": resolved, "pass": "resolution_sweep"}


# ═══════════════════════════════════════════════════════════════════════
# Pass 4: HITL auto-resolve (substring heuristic)
# ═══════════════════════════════════════════════════════════════════════


def hitl_auto_resolve(db, batch_size: int = 500) -> dict:
    """Auto-approve HITL items where suggested_match_name is a substring of raw_value (or vice versa).

    Only processes items with suggested_confidence in [0.5, 0.9).
    No LLM calls — pure string matching.
    """
    items = db.fetch_all(
        """SELECT id, raw_value, suggested_match_id, suggested_match_name, suggested_confidence
           FROM unresolved_entities
           WHERE status = 'hitl_queued' AND suggested_match_id IS NOT NULL
             AND suggested_confidence >= 0.5 AND suggested_confidence < 0.9
           LIMIT %s""",
        [batch_size],
    )

    resolved = 0
    for item in items:
        raw = (item.get("raw_value") or "").lower().strip()
        suggested = (item.get("suggested_match_name") or "").lower().strip()
        if not raw or not suggested:
            continue

        # Substring match in either direction = auto-approve
        if raw in suggested or suggested in raw:
            db.execute(
                """UPDATE unresolved_entities
                   SET status='resolved', resolved=true, resolved_entity_id=%s,
                       resolved_at=NOW(), resolved_by='auto_curate_hitl'
                   WHERE id=%s""",
                [item["suggested_match_id"], item["id"]],
            )
            resolved += 1

    logger.info("Pass 4 (HITL auto-resolve): %d/%d resolved", resolved, len(items))
    return {"processed": len(items), "resolved": resolved, "pass": "hitl_auto"}


# ═══════════════════════════════════════════════════════════════════════
# Pass 5: Compute and persist FAIR score
# ═══════════════════════════════════════════════════════════════════════


def compute_fair(db) -> dict:
    """Compute FAIR data quality snapshot and persist to data_quality_snapshots."""
    try:
        scorer = FAIRScorer(db)
        snapshot = scorer.compute()
        scorer.persist(snapshot)
        logger.info("Pass 5 (FAIR score): %.4f", snapshot["overall_score"])
        return {"fair_score": snapshot["overall_score"], "pass": "fair_score"}
    except Exception as e:
        logger.error("FAIR score computation failed: %s", e)
        return {"error": str(e), "pass": "fair_score"}


# ═══════════════════════════════════════════════════════════════════════
# Master runner
# ═══════════════════════════════════════════════════════════════════════


def run_all_curation(db) -> list[dict]:
    """Execute all 5 curation passes in sequence.

    Each pass is independent and safe to run individually.
    The full pipeline is idempotent — running twice produces no duplicates.

    Returns:
        List of 5 result dicts, one per pass.
    """
    results: list[dict] = []
    total_start = time.time()

    logger.info("Starting auto-curation v2 (5 passes)")

    # Pass 1: SEC EDGAR enrichment
    t0 = time.time()
    r = enrich_companies_from_sec(db)
    r["elapsed_s"] = round(time.time() - t0, 1)
    results.append(r)

    # Pass 2: Orphan company linking
    t0 = time.time()
    r = link_orphan_companies(db)
    r["elapsed_s"] = round(time.time() - t0, 1)
    results.append(r)

    # Pass 3: Resolution sweep
    t0 = time.time()
    r = resolution_sweep(db, batch_size=1000)
    r["elapsed_s"] = round(time.time() - t0, 1)
    results.append(r)

    # Pass 4: HITL auto-resolve
    t0 = time.time()
    r = hitl_auto_resolve(db, batch_size=1000)
    r["elapsed_s"] = round(time.time() - t0, 1)
    results.append(r)

    # Pass 5: FAIR score
    t0 = time.time()
    r = compute_fair(db)
    r["elapsed_s"] = round(time.time() - t0, 1)
    results.append(r)

    total_elapsed = round(time.time() - total_start, 1)
    logger.info("Auto-curation v2 complete in %.1fs", total_elapsed)

    return results


# ═══════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════


def main():
    """CLI entry point for auto_curate_v2."""
    parser = argparse.ArgumentParser(description="Run 5-pass deterministic data curation")
    parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    from config import config
    from db import Database

    db = Database(config.db.dsn)
    db.connect()

    try:
        results = run_all_curation(db)
        print("\n=== Auto-Curation v2 Results ===")
        total_enriched = 0
        for r in results:
            pass_name = r.get("pass", "unknown")
            enriched = r.get("enriched", r.get("resolved", r.get("linked", 0)))
            elapsed = r.get("elapsed_s", "")
            error = r.get("error")
            if error:
                print(f"  {pass_name}: ERROR - {error}")
            else:
                print(f"  {pass_name}: {enriched} items" + (f" ({elapsed}s)" if elapsed else ""))
            total_enriched += enriched if isinstance(enriched, int) else 0

        fair_score = next((r.get("fair_score") for r in results if r.get("pass") == "fair_score"), None)
        print(f"\n  Total enriched: {total_enriched}")
        if fair_score is not None:
            print(f"  FAIR score: {fair_score:.4f}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
