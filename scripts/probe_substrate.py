#!/usr/bin/env python
"""Read-only substrate freshness / linkage / ledger probe.

The one command the data squad runs first (see docs/data-agent-playbook.md §3).
Measures: per-table freshness, FK-orphan share, fact ledger composition, curation
backlog, and market_events duplication — the signals behind data-sense-layer-status.html.

Usage:
    python scripts/probe_substrate.py "<postgres url>"
    # or set DATABASE_URL and run with no args
    DATABASE_URL=... python scripts/probe_substrate.py

Read-only: issues only SELECTs. Safe to run against prod.
"""
import os
import sys
from datetime import datetime, timezone

import psycopg2


def get_db_url() -> str:
    if len(sys.argv) > 1 and sys.argv[1].startswith("postgres"):
        return sys.argv[1]
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("Pass a postgres URL as argv[1] or set DATABASE_URL.")
    return url


# table -> ordered recency-column candidates (prefer ingestion time over created_at)
FRESHNESS = {
    "drugs": ["updated_at", "created_at"],
    "companies": ["updated_at", "created_at"],
    "clinical_trials": ["last_verified_at", "retrieved_at", "created_at"],
    "pubmed_articles": ["last_verified_at", "retrieved_at", "created_at"],
    "pmc_articles": ["retrieved_at", "created_at"],
    "market_events": ["retrieved_at", "created_at", "event_date"],
    "drug_labels": ["retrieved_at", "created_at"],
    "adverse_events": ["retrieved_at", "created_at", "report_date"],
    "patents": ["retrieved_at", "created_at"],
    "regulatory_milestones": ["retrieved_at", "created_at"],
    "molecular_targets": ["retrieved_at", "created_at"],
    "bioactivities": ["retrieved_at", "created_at"],
    "drug_pricing": ["created_at"],
    "facts": ["asserted_at"],
    "signals": ["created_at"],
    "evidence_records": ["created_at"],
    "entity_links": ["created_at"],
}

# label -> SQL returning (null_count, total)
ORPHANS = {
    "bioactivities.drug_id": "SELECT count(*) FILTER (WHERE drug_id IS NULL), count(*) FROM bioactivities",
    "clinical_trials.drug_id": "SELECT count(*) FILTER (WHERE drug_id IS NULL), count(*) FROM clinical_trials",
    "pubmed_articles.drug_id": "SELECT count(*) FILTER (WHERE drug_id IS NULL), count(*) FROM pubmed_articles",
    "adverse_events.drug_id": "SELECT count(*) FILTER (WHERE drug_id IS NULL), count(*) FROM adverse_events",
    "market_events.primary_entity_id": "SELECT count(*) FILTER (WHERE primary_entity_id IS NULL), count(*) FROM market_events",
    "facts.source_doc_id": "SELECT count(*) FILTER (WHERE source_doc_id IS NULL), count(*) FROM facts WHERE superseded_by IS NULL",
}


def main() -> None:
    conn = psycopg2.connect(get_db_url())
    cur = conn.cursor()
    now = datetime.now(timezone.utc)

    def q(sql):
        try:
            cur.execute(sql)
            return cur.fetchall()
        except Exception as exc:  # noqa: BLE001 - probe is best-effort per table
            conn.rollback()
            return [("ERR", str(exc)[:100])]

    def age(d):
        if not d:
            return ""
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return f"{(now - d).days}d ago"

    print("=== FRESHNESS (count · newest · age) ===")
    for table, cols in FRESHNESS.items():
        cnt = q(f"SELECT count(*) FROM {table}")
        count = cnt[0][0] if cnt and cnt[0][0] != "ERR" else "?"
        newest_col, newest = None, None
        for c in cols:
            r = q(f"SELECT max({c}) FROM {table}")
            if r and r[0][0] not in ("ERR", None):
                newest_col, newest = c, r[0][0]
                break
        print(f"  {table:24} count={str(count):>10}  newest[{newest_col or '?'}]={newest} {age(newest)}")

    print("\n=== ORPHAN / LINKAGE (NULL fk / total) ===")
    for label, sql in ORPHANS.items():
        r = q(sql)
        if r and r[0][0] != "ERR":
            nul, tot = r[0]
            pct = f"{100 * nul / tot:.1f}%" if tot else "n/a"
            print(f"  {label:34} {nul:>8} / {tot:<8} ({pct})")
        else:
            print(f"  {label:34} {r}")

    print("\n=== FACT LEDGER ===")
    for r in q("SELECT predicate, count(*) FROM facts WHERE superseded_by IS NULL GROUP BY predicate ORDER BY 2 DESC"):
        print("  predicate", r)
    for r in q("SELECT fact_class, count(*) FROM facts WHERE superseded_by IS NULL GROUP BY fact_class ORDER BY 2 DESC"):
        print("  class    ", r)

    print("\n=== CURATION BACKLOG ===")
    for t in ("hitl_review_queue", "unresolved_entities", "steward_actions"):
        print(f"  {t:24}", q(f"SELECT count(*) FROM {t}"))

    print("\n=== market_events TOP DUP GROUPS ===")
    for r in q(
        "SELECT count(*) c FROM market_events "
        "GROUP BY primary_entity_id, event_type, description ORDER BY c DESC LIMIT 5"
    ):
        print("  dup group size:", r)

    cur.close()
    conn.close()
    print("\nDONE")


if __name__ == "__main__":
    main()
