#!/usr/bin/env python
"""Read-only probe for Loop 2 (resolve-at-ingest): adverse_events / drug_labels
drug_id orphan share, chembl_id coverage, and whether orphans are legacy vs recent.

Usage: DATABASE_URL=... python scripts/probe_resolve_at_ingest.py
Read-only: SELECTs only. Safe against prod.
"""
import os
import sys
import psycopg2
import psycopg2.extras


def main():
    url = os.environ.get("DATABASE_URL") or (sys.argv[1] if len(sys.argv) > 1 else None)
    if not url:
        sys.exit("Set DATABASE_URL or pass url as argv[1].")
    conn = psycopg2.connect(url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def q(label, sql):
        cur.execute(sql)
        rows = cur.fetchall()
        print(f"\n=== {label} ===")
        for r in rows:
            print("  " + " | ".join(f"{k}={v}" for k, v in r.items()))
        return rows

    # 1. Orphan share on the two target tables
    for tbl in ("adverse_events", "drug_labels"):
        q(f"{tbl}: drug_id orphan share", f"""
            SELECT count(*) AS total,
                   count(*) FILTER (WHERE drug_id IS NULL) AS null_drug_id,
                   round(100.0 * count(*) FILTER (WHERE drug_id IS NULL) / NULLIF(count(*),0), 1) AS pct_null,
                   count(*) FILTER (WHERE record_status = 'active' OR record_status IS NULL) AS active_rows
            FROM {tbl}
        """)

    # 2. Are orphans legacy (old retrieved_at) or ongoing? Bucket by recency.
    for tbl in ("adverse_events", "drug_labels"):
        q(f"{tbl}: orphans by ingest recency", f"""
            SELECT
              CASE WHEN retrieved_at > now() - interval '30 days' THEN 'last_30d'
                   WHEN retrieved_at > now() - interval '180 days' THEN '30-180d'
                   ELSE 'older_or_null' END AS bucket,
              count(*) AS rows,
              count(*) FILTER (WHERE drug_id IS NULL) AS null_drug_id
            FROM {tbl}
            GROUP BY 1 ORDER BY 1
        """)

    # 3. Which drug_names fail to resolve (the actual unresolved targets)
    for tbl in ("adverse_events", "drug_labels"):
        q(f"{tbl}: top unresolved drug_name", f"""
            SELECT lower(drug_name) AS drug_name, count(*) AS orphan_rows
            FROM {tbl}
            WHERE drug_id IS NULL AND drug_name IS NOT NULL
            GROUP BY 1 ORDER BY 2 DESC LIMIT 15
        """)

    # 4. Of those unresolved names, how many ACTUALLY exist in drugs (so resolvable)?
    q("orphan drug_names that DO exist in drugs (active)", """
        WITH orphan_names AS (
            SELECT DISTINCT lower(drug_name) AS dn FROM adverse_events WHERE drug_id IS NULL AND drug_name IS NOT NULL
            UNION
            SELECT DISTINCT lower(drug_name) FROM drug_labels WHERE drug_id IS NULL AND drug_name IS NOT NULL
        )
        SELECT count(*) AS distinct_orphan_names,
               count(*) FILTER (WHERE EXISTS (
                   SELECT 1 FROM drugs d
                   WHERE lower(d.generic_name) = o.dn
                     AND (d.record_status IS NULL OR d.record_status NOT IN ('merged','superseded','excluded'))
               )) AS resolvable_by_exact_name
        FROM orphan_names o
    """)

    # 5. chembl_id coverage on drugs
    q("drugs.chembl_id coverage", """
        SELECT count(*) AS total_active,
               count(chembl_id) AS with_chembl_id,
               round(100.0*count(chembl_id)/NULLIF(count(*),0),2) AS pct
        FROM drugs
        WHERE record_status IS NULL OR record_status NOT IN ('merged','superseded','excluded')
    """)

    # 6. bioactivities linkage (the inert relink)
    q("bioactivities drug linkage", """
        SELECT count(*) AS total,
               count(drug_id) AS with_drug_id,
               count(molecule_chembl_id) AS with_molecule_chembl_id
        FROM bioactivities
    """)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
