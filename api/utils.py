"""Shared API utilities."""

from __future__ import annotations

import re


def normalize_provenance(provenance: dict, entity_type: str, entity_id: str) -> dict:
    """Convert raw API provenance into human-readable links.

    Stored source_url values are raw API endpoints (e.g. clinicaltrials.gov/api/v2/...).
    This converts them to human-readable URLs and cleans up 'backfill' placeholders.
    """
    prov = dict(provenance) if provenance else {}
    source_api = prov.get("source_api", "")
    source_url = prov.get("source_url", "")

    # ── Clinical trials: build proper study URL from NCT ID ──
    if source_api == "clinical_trials_gov" or entity_type == "trial":
        nct_id = entity_id if entity_id.startswith("NCT") else ""
        if not nct_id and isinstance(source_url, str):
            m = re.search(r'(NCT\d+)', source_url)
            if m:
                nct_id = m.group(1)
        if nct_id:
            prov["source_url"] = f"https://clinicaltrials.gov/study/{nct_id}"
            prov["source_api"] = "ClinicalTrials.gov"

    # ── PubMed: extract PMID from efetch URL and build article link ──
    elif source_api == "pubmed" or (isinstance(source_url, str) and "pubmed" in source_url):
        pmid = ""
        if isinstance(source_url, str):
            m = re.search(r'[?&]id=(\d+)', source_url)
            if m:
                pmid = m.group(1)
        if pmid:
            prov["source_url"] = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            prov["source_api"] = "PubMed"
        else:
            prov["source_api"] = "PubMed"

    # ── FDA: human-readable label ──
    elif source_api == "fda_orange_book":
        prov["source_api"] = "FDA Orange Book"
        if isinstance(source_url, str) and "api.fda.gov" in source_url:
            prov["source_url"] = "https://www.fda.gov/drugs"

    # ── Backfill: no real provenance available ──
    elif source_api == "backfill" or source_url == "backfill":
        prov["source_api"] = "Knowledge Base"
        prov.pop("source_url", None)

    # Clean up: title-case the source_api for display
    if prov.get("source_api"):
        api_val = prov["source_api"]
        # Only title-case if still in snake_case
        if "_" in api_val:
            prov["source_api"] = api_val.replace("_", " ").title()

    return prov
