"""Therapeutic Areas API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import get_db
from db import Database

router = APIRouter(prefix="/therapeutic-areas", tags=["therapeutic-areas"])


@router.get("")
def list_therapeutic_areas(db: Database = Depends(get_db)):
    """List all therapeutic areas with drug and trial counts.

    Returns both direct FK counts and entity_link counts so the
    frontend can show the true multi-indication picture.
    """
    rows = db.fetch_all("""
        SELECT
            ta.id::text AS id,
            ta.name,
            ta.mesh_id,
            COUNT(DISTINCT d.id)  AS drug_count_fk,
            COUNT(DISTINCT ct.id) AS trial_count
        FROM therapeutic_areas ta
        LEFT JOIN drugs d ON d.therapeutic_area_id = ta.id
        LEFT JOIN clinical_trials ct ON ct.drug_id = d.id
        GROUP BY ta.id, ta.name, ta.mesh_id
        ORDER BY COUNT(DISTINCT d.id) DESC
    """)

    # Also get entity_link-based counts (many-to-many, more accurate for
    # multi-indication drugs like SGLT2i in both diabetes and heart failure).
    link_rows = db.fetch_all("""
        SELECT
            ta.id::text AS id,
            COUNT(DISTINCT el.source_entity_id) AS drug_count_links
        FROM therapeutic_areas ta
        JOIN entity_links el
            ON el.target_entity_id::uuid = ta.id
           AND el.link_type = 'IN_THERAPEUTIC_AREA'
        GROUP BY ta.id
    """)
    link_map = {r["id"]: r["drug_count_links"] for r in link_rows}

    results = []
    for r in rows:
        ta_id = r["id"]
        drug_fk = r["drug_count_fk"]
        drug_links = link_map.get(ta_id, 0)
        results.append({
            "id": ta_id,
            "name": r["name"],
            "mesh_id": r["mesh_id"],
            "drug_count": max(drug_fk, drug_links),
            "trial_count": r["trial_count"],
        })

    return {"therapeutic_areas": results, "total": len(results)}
