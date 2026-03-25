"""Interactive Data Catalog API routes.

Provides browsing, searching, metadata inspection, traceable edits,
HITL review management, audit trail, and curation triggers.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.deps import get_db, get_metrics
from db import Database
from services.metrics import PharmaMetrics

logger = logging.getLogger(__name__)

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _is_uuid(value: str) -> bool:
    """Return True if value looks like a UUID (entity_tags/aliases use UUID PKs)."""
    return bool(_UUID_RE.match(value))


router = APIRouter(prefix="/catalog", tags=["catalog"])

# ── Table metadata for entity browsing ──

ENTITY_TABLES = {
    "drug": {
        "table": "drugs",
        "id_col": "id",
        "label_col": "generic_name",
        "search_cols": ["generic_name", "brand_name"],
        "display_cols": [
            "id", "generic_name", "brand_name", "company_id",
            "therapeutic_area_id", "mechanism_id", "approval_date",
            "patent_expiry_date", "supply_status", "source_authority",
            "source_api", "record_status", "quality_score",
            "content_hash", "last_verified_at", "retrieved_at",
        ],
        "editable_cols": ["brand_name", "supply_status", "record_status"],
    },
    "company": {
        "table": "companies",
        "id_col": "id",
        "label_col": "name",
        "search_cols": ["name", "ticker"],
        "display_cols": [
            "id", "name", "ticker", "cik", "region", "country",
            "market_cap_tier", "sic_code",
            "source_api", "record_status", "quality_score",
            "content_hash", "last_verified_at", "retrieved_at",
        ],
        "editable_cols": ["region", "country", "market_cap_tier", "record_status"],
    },
    "trial": {
        "table": "clinical_trials",
        "id_col": "id",
        "label_col": "COALESCE(official_title, id)",
        "search_cols": ["id", "sponsor_name"],
        "display_cols": [
            "id", "official_title", "drug_id",
            "sponsor_name", "status", "phase", "conditions",
            "enrollment_target", "start_date", "primary_completion_date",
            "study_type", "record_status", "quality_score",
            "source_api", "retrieved_at",
        ],
        "editable_cols": ["record_status"],
    },
    "therapeutic_area": {
        "table": "therapeutic_areas",
        "id_col": "id",
        "label_col": "name",
        "search_cols": ["name", "mesh_id"],
        "display_cols": [
            "id", "name", "mesh_id", "tree_numbers", "parent_mesh_id",
            "scope_note", "source_api", "retrieved_at",
        ],
        "editable_cols": [],
    },
    "mechanism": {
        "table": "mechanisms_of_action",
        "id_col": "id",
        "label_col": "name",
        "search_cols": ["name", "mesh_id"],
        "display_cols": [
            "id", "name", "mesh_id", "scope_note",
            "source_api", "retrieved_at",
        ],
        "editable_cols": [],
    },
    "article": {
        "table": "pubmed_articles",
        "id_col": "id",
        "label_col": "title",
        "search_cols": ["title", "pmid", "journal"],
        "display_cols": [
            "id", "pmid", "title", "journal", "publication_date",
            "authors", "mesh_terms", "drug_id", "doi",
            "record_status", "quality_score",
            "source_api", "retrieved_at",
        ],
        "editable_cols": ["record_status"],
    },
}


# ── Static dataset profile metadata ──
# Keyed by canonical source_api values (see connectors.base.SourceType).
# Runtime data (records, quality_score, last_refreshed) is augmented from the DB.

DATASET_PROFILES: dict[str, dict] = {
    "clinical_trials_gov": {
        "display_name": "ClinicalTrials.gov",
        "description": "Federally mandated registry of clinical studies conducted in the US and worldwide.",
        "source_url": "https://clinicaltrials.gov",
        "entity_types": ["trial", "investigator"],
        "refresh_schedule": "Daily at 02:00 UTC",
        "collection_method": "API (REST JSON)",
        "fields_collected": [
            "NCT ID", "Title", "Phase", "Status", "Sponsor", "Enrollment",
            "Start Date", "Completion Date", "Conditions", "Interventions",
            "Outcomes", "Locations",
        ],
        "coverage_notes": "Covers all US-registered trials. International coverage varies by reporting requirements.",
    },
    "pubmed": {
        "display_name": "PubMed",
        "description": "NCBI index of biomedical literature — abstracts, MeSH terms, and citation metadata.",
        "source_url": "https://pubmed.ncbi.nlm.nih.gov",
        "entity_types": ["literature"],
        "refresh_schedule": "Weekly on Monday at 03:00 UTC",
        "collection_method": "API (E-utilities XML)",
        "fields_collected": [
            "PMID", "Title", "Abstract", "Authors", "Journal", "Publication Date",
            "MeSH Terms", "Keywords", "DOI", "Publication Type",
        ],
        "coverage_notes": "Over 36 million citations. Drug-specific queries scoped by therapeutic area.",
    },
    "fda_orange_book": {
        "display_name": "FDA Orange Book",
        "description": "Approved drug products with therapeutic equivalence evaluations, patent, and exclusivity data.",
        "source_url": "https://www.fda.gov/drugs/drug-approvals-and-databases/approved-drug-products-therapeutic-equivalence-evaluations-orange-book",
        "entity_types": ["drug", "patent"],
        "refresh_schedule": "Monthly on 1st at 04:00 UTC",
        "collection_method": "API (openFDA JSON)",
        "fields_collected": [
            "NDA Number", "Generic Name", "Brand Name", "Dosage Form", "Route",
            "Marketing Status", "Applicant", "Approval Date", "Patent Number",
            "Patent Expiry", "Exclusivity Code", "Exclusivity Date",
        ],
        "coverage_notes": "Covers FDA-approved drugs with NDA/ANDA numbers. Does not include biologics (see Purple Book).",
    },
    "openfda_faers": {
        "display_name": "FDA Adverse Event Reports (FAERS)",
        "description": "Post-market safety surveillance — adverse event and medication error reports submitted to FDA.",
        "source_url": "https://open.fda.gov/apis/drug/event/",
        "entity_types": ["event"],
        "refresh_schedule": "Weekly on Wednesday at 03:00 UTC",
        "collection_method": "API (openFDA JSON)",
        "fields_collected": [
            "Report ID", "Event Date", "Drug Name", "Reaction", "Outcome",
            "Patient Age", "Patient Sex", "Reporter Type", "Seriousness",
        ],
        "coverage_notes": "Voluntary reporting — captures serious and unexpected adverse events. Under-reporting is common.",
    },
    "openfda_labels": {
        "display_name": "FDA Drug Labels",
        "description": "Structured product labeling (SPL) — prescribing information, indications, warnings, and dosage.",
        "source_url": "https://open.fda.gov/apis/drug/label/",
        "entity_types": ["drug"],
        "refresh_schedule": "Monthly on 1st at 05:00 UTC",
        "collection_method": "API (openFDA JSON)",
        "fields_collected": [
            "Set ID", "Brand Name", "Generic Name", "Indications",
            "Warnings", "Dosage", "Adverse Reactions", "Pharmacology",
            "Manufacturer", "Effective Date",
        ],
        "coverage_notes": "Comprehensive US drug labeling. Updated when labels are revised by manufacturers.",
    },
    "fda_shortages": {
        "display_name": "FDA Drug Shortages",
        "description": "Current and resolved drug shortages tracked by the FDA Drug Shortage Program.",
        "source_url": "https://www.fda.gov/drugs/drug-safety-and-availability/drug-shortages",
        "entity_types": ["drug", "event"],
        "refresh_schedule": "Daily at 06:00 UTC",
        "collection_method": "API (REST JSON)",
        "fields_collected": [
            "Drug Name", "Status", "Shortage Reason", "Expected Resolution",
            "Affected NDCs", "Therapeutic Category",
        ],
        "coverage_notes": "Covers active US drug shortages. Historical data available for resolved shortages.",
    },
    "sec_edgar": {
        "display_name": "SEC EDGAR",
        "description": "SEC corporate filings — 10-K, 10-Q, and 8-K filings from pharmaceutical companies.",
        "source_url": "https://www.sec.gov/cgi-bin/browse-edgar",
        "entity_types": ["company"],
        "refresh_schedule": "Weekly on Tuesday at 04:00 UTC",
        "collection_method": "API (EDGAR REST + XBRL)",
        "fields_collected": [
            "CIK", "Company Name", "Ticker", "SIC Code", "Filing Type",
            "Filing Date", "Revenue", "R&D Expense", "Market Cap Tier",
        ],
        "coverage_notes": "Covers publicly traded US companies. Non-US pharma companies may have limited coverage.",
    },
    "mesh_ontology": {
        "display_name": "MeSH Ontology",
        "description": "Medical Subject Headings — NLM controlled vocabulary for indexing biomedical literature.",
        "source_url": "https://meshb.nlm.nih.gov",
        "entity_types": ["therapeutic_area", "mechanism"],
        "refresh_schedule": "Annually (with supplementals quarterly)",
        "collection_method": "Bulk download (XML)",
        "fields_collected": [
            "MeSH ID", "Descriptor Name", "Tree Numbers", "Scope Note",
            "Parent Descriptors", "Entry Terms", "Pharmacological Actions",
        ],
        "coverage_notes": "Authoritative biomedical ontology. Hierarchical tree structure for therapeutic areas and mechanisms.",
    },
    "pmc": {
        "display_name": "PubMed Central",
        "description": "Full-text open-access biomedical articles from the NLM digital archive.",
        "source_url": "https://www.ncbi.nlm.nih.gov/pmc/",
        "entity_types": ["literature"],
        "refresh_schedule": "Weekly on Monday at 03:30 UTC",
        "collection_method": "API (OAI-PMH XML + E-utilities)",
        "fields_collected": [
            "PMC ID", "PMID", "Title", "Abstract", "Full Text", "Authors",
            "Journal", "Publication Date", "Figures", "Tables", "References",
        ],
        "coverage_notes": "Open-access subset of PubMed. Full-text available for approximately 8 million articles.",
    },
    "backfill": {
        "display_name": "Internal Enrichment",
        "description": "AI-assisted enrichment and cross-linking derived from existing knowledge base records.",
        "source_url": None,
        "entity_types": ["drug", "company", "trial", "mechanism", "therapeutic_area"],
        "refresh_schedule": "On-demand (triggered by curation pipeline)",
        "collection_method": "Internal (LLM + heuristic)",
        "fields_collected": [
            "Brand Name", "Company Link", "Mechanism Link", "TA Link",
            "Approval Date", "Competition Links", "Name Cleanup",
        ],
        "coverage_notes": "Fills gaps in external source data. Quality validated through HITL review queue.",
    },
}


# ── Request/Response models ──

class EntityUpdateRequest(BaseModel):
    fields: dict[str, str | int | float | bool | None]
    reason: str = ""


class HITLResolveRequest(BaseModel):
    action: str  # approved, rejected, deferred
    resolution_notes: str = ""


class EnrichmentRequest(BaseModel):
    entity_type: str
    scope: str  # e.g. "therapeutic_area:Oncology", "mechanism:GLP-1"
    description: str = ""


class EntityTagRequest(BaseModel):
    tag_name: str
    tag_value: str


# ── Endpoints ──


@router.get("/datasets")
def list_datasets(db: Database = Depends(get_db)):
    """List all datasets from the dataset catalog with quality metrics."""
    try:
        rows = db.fetch_all(
            """
            SELECT dataset_name, source_type, entity_type, table_name,
                   row_count, last_refreshed_at, refresh_frequency,
                   license_name, quality_score_avg, completeness_pct,
                   freshness_days, source_imbalance
            FROM dataset_catalog
            ORDER BY dataset_name
            """
        )
    except Exception:
        rows = []

    # Fall back to computed stats if dataset_catalog is empty
    if not rows:
        rows = _compute_dataset_stats(db)

    return {"datasets": rows, "count": len(rows)}


@router.get("/datasets/{source_key}/profile")
def dataset_profile(
    source_key: str,
    db: Database = Depends(get_db),
):
    """Rich profile card for a dataset — static metadata augmented with live DB stats."""
    if source_key not in DATASET_PROFILES:
        raise HTTPException(404, f"Unknown dataset: {source_key}. Known: {list(DATASET_PROFILES.keys())}")

    profile = {**DATASET_PROFILES[source_key], "source_key": source_key}

    # ── Live stats: records, quality, last_refreshed ──
    records = 0
    quality_score: float | None = None
    last_refreshed: str | None = None

    # Map source_key to the tables it populates
    source_tables = {
        "clinical_trials_gov": [("clinical_trials", "trial")],
        "pubmed": [("pubmed_articles", "article")],
        "fda_orange_book": [("drugs", "drug")],
        "openfda_faers": [("market_events", "event")],
        "openfda_labels": [("drugs", "drug")],
        "fda_shortages": [("drugs", "drug"), ("market_events", "event")],
        "sec_edgar": [("companies", "company")],
        "mesh_ontology": [("therapeutic_areas", "therapeutic_area"), ("mechanisms_of_action", "mechanism")],
        "pmc": [("pubmed_articles", "article")],
        "backfill": [("drugs", "drug"), ("companies", "company")],
    }

    for table, etype in source_tables.get(source_key, []):
        try:
            row = db.fetch_one(
                f"SELECT COUNT(*) AS cnt, MAX(retrieved_at) AS latest FROM {table} WHERE source_api = %s",
                [source_key],
            )
            if row:
                records += row["cnt"] or 0
                latest = row.get("latest")
                if latest and hasattr(latest, "isoformat"):
                    iso = latest.isoformat()
                    if last_refreshed is None or iso > last_refreshed:
                        last_refreshed = iso
        except Exception:
            pass

        # Quality score from data_quality_results
        if _table_exists(db, "data_quality_results"):
            try:
                qrow = db.fetch_one(
                    """
                    SELECT ROUND(AVG(r.score)::numeric, 3) AS avg_score
                    FROM data_quality_results r
                    JOIN (SELECT id FROM %s WHERE source_api = %%s) e ON e.id::text = r.entity_id
                    WHERE r.entity_type = %%s
                    """ % table,
                    [source_key, etype],
                )
                if qrow and qrow.get("avg_score") is not None:
                    quality_score = float(qrow["avg_score"])
            except Exception:
                pass

    # Freshness label
    freshness_label = "unknown"
    if last_refreshed:
        try:
            from datetime import datetime as _dt, timezone as _tz
            latest_dt = _dt.fromisoformat(last_refreshed.replace("Z", "+00:00"))
            days_old = (_dt.now(_tz.utc) - latest_dt).days
            freshness_label = "fresh" if days_old <= 7 else "recent" if days_old <= 30 else "stale"
        except Exception:
            pass

    profile["records"] = records
    profile["quality_score"] = quality_score
    profile["last_refreshed"] = last_refreshed
    profile["freshness"] = freshness_label

    return profile


@router.get("/entities/{entity_type}")
def browse_entities(
    entity_type: str,
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="Filter by record_status"),
    quality_min: Optional[float] = Query(None, ge=0, le=1),
    sort_by: Optional[str] = Query("label", description="Sort column"),
    sort_dir: Optional[str] = Query("asc", regex="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_db),
):
    """Browse entities with rich metadata, search, filtering, and pagination."""
    if entity_type not in ENTITY_TABLES:
        raise HTTPException(400, f"Unknown entity type: {entity_type}. Valid: {list(ENTITY_TABLES.keys())}")

    meta = ENTITY_TABLES[entity_type]
    cols = ", ".join(meta["display_cols"])
    label_expr = meta["label_col"]

    conditions = []
    params: list = []

    if search:
        search_clauses = [f"{col} ILIKE %s" for col in meta["search_cols"]]
        conditions.append(f"({' OR '.join(search_clauses)})")
        params.extend([f"%{search}%"] * len(meta["search_cols"]))

    if status and "record_status" in meta["display_cols"]:
        conditions.append("record_status = %s")
        params.append(status)

    if quality_min is not None and "quality_score" in meta["display_cols"]:
        conditions.append("quality_score >= %s")
        params.append(quality_min)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # Sort mapping
    sort_col = meta["id_col"]
    if sort_by == "label":
        sort_col = label_expr
    elif sort_by == "quality" and "quality_score" in meta["display_cols"]:
        sort_col = "quality_score"
    elif sort_by == "updated" and "retrieved_at" in meta["display_cols"]:
        sort_col = "retrieved_at"
    elif sort_by == "status" and "record_status" in meta["display_cols"]:
        sort_col = "record_status"

    direction = "DESC" if sort_dir == "desc" else "ASC"

    # Count
    count_row = db.fetch_one(f"SELECT COUNT(*) AS total FROM {meta['table']} {where}", params)
    total = count_row["total"] if count_row else 0

    # Fetch
    params.extend([limit, offset])
    rows = db.fetch_all(
        f"""
        SELECT {cols}, {label_expr} AS _label
        FROM {meta['table']}
        {where}
        ORDER BY {sort_col} {direction} NULLS LAST
        LIMIT %s OFFSET %s
        """,
        params,
    )

    return {
        "entity_type": entity_type,
        "results": rows,
        "total": total,
        "limit": limit,
        "offset": offset,
        "editable_fields": meta["editable_cols"],
    }


@router.get("/entities/{entity_type}/{entity_id}")
def entity_detail(
    entity_type: str,
    entity_id: str,
    db: Database = Depends(get_db),
):
    """Get full entity detail with quality results, change log, links, and tags."""
    if entity_type not in ENTITY_TABLES:
        raise HTTPException(400, f"Unknown entity type: {entity_type}")

    meta = ENTITY_TABLES[entity_type]
    cols = ", ".join(meta["display_cols"])

    row = db.fetch_one(
        f"SELECT {cols} FROM {meta['table']} WHERE {meta['id_col']} = %s",
        [entity_id],
    )
    if not row:
        raise HTTPException(404, "Entity not found")

    # Quality results
    quality = db.fetch_all(
        """
        SELECT r.rule_id, q.rule_name, q.rule_type, q.severity,
               r.passed, r.score, r.details
        FROM data_quality_results r
        JOIN data_quality_rules q ON q.id = r.rule_id
        WHERE r.entity_type = %s AND r.entity_id = %s
        ORDER BY r.passed ASC, q.severity DESC
        """,
        [entity_type, entity_id],
    ) if _table_exists(db, "data_quality_results") else []

    # Change log (recent 20)
    changes = db.fetch_all(
        """
        SELECT id, change_type, changed_fields, old_content_hash,
               new_content_hash, etl_run_id, changed_at
        FROM data_change_log
        WHERE entity_type = %s AND entity_id = %s
        ORDER BY changed_at DESC
        LIMIT 20
        """,
        [entity_type, entity_id],
    ) if _table_exists(db, "data_change_log") else []

    # Entity links
    links = db.fetch_all(
        """
        SELECT el.source_entity_id, el.source_entity_type,
               el.target_entity_id, el.target_entity_type,
               el.link_type, el.confidence, el.provenance_source
        FROM entity_links el
        WHERE (el.source_entity_id = %s AND el.source_entity_type = %s)
           OR (el.target_entity_id = %s AND el.target_entity_type = %s)
        ORDER BY el.confidence DESC
        LIMIT 50
        """,
        [entity_id, entity_type, entity_id, entity_type],
    )

    # Tags (entity_id is UUID in entity_tags — skip for text PK types like trial)
    tags = []
    if _table_exists(db, "entity_tags") and _is_uuid(entity_id):
        tags = db.fetch_all(
            """
            SELECT tag_name, tag_value, created_by, created_at
            FROM entity_tags
            WHERE entity_type = %s AND entity_id = %s::uuid
            ORDER BY tag_name
            """,
            [entity_type, entity_id],
        )

    # Aliases (entity_id is UUID in entity_aliases)
    aliases = []
    if _table_exists(db, "entity_aliases") and _is_uuid(entity_id):
        aliases = db.fetch_all(
            """
            SELECT alias_text, source_type, confidence, verified
            FROM entity_aliases
            WHERE entity_type = %s AND entity_id = %s::uuid
            ORDER BY confidence DESC
            """,
            [entity_type, entity_id],
        )

    return {
        "entity": row,
        "entity_type": entity_type,
        "quality_results": quality,
        "change_log": changes,
        "links": links,
        "tags": tags,
        "aliases": aliases,
        "editable_fields": meta["editable_cols"],
    }


@router.patch("/entities/{entity_type}/{entity_id}")
def update_entity(
    entity_type: str,
    entity_id: str,
    body: EntityUpdateRequest,
    db: Database = Depends(get_db),
):
    """Update allowed fields on an entity. Logs changes to data_change_log."""
    if entity_type not in ENTITY_TABLES:
        raise HTTPException(400, f"Unknown entity type: {entity_type}")

    meta = ENTITY_TABLES[entity_type]
    editable = set(meta["editable_cols"])

    invalid = set(body.fields.keys()) - editable
    if invalid:
        raise HTTPException(400, f"Non-editable fields: {invalid}. Editable: {editable}")

    if not body.fields:
        raise HTTPException(400, "No fields to update")

    # Build SET clause
    set_parts = []
    values = []
    changed_fields = []
    for col, val in body.fields.items():
        set_parts.append(f"{col} = %s")
        values.append(val)
        changed_fields.append(col)

    values.append(entity_id)
    set_clause = ", ".join(set_parts)

    db.execute(
        f"UPDATE {meta['table']} SET {set_clause} WHERE {meta['id_col']} = %s",
        values,
    )

    # Log the change
    if _table_exists(db, "data_change_log"):
        db.execute(
            """
            INSERT INTO data_change_log (entity_type, entity_id, change_type, changed_fields, changed_at)
            VALUES (%s, %s, 'manual_edit', %s, %s)
            """,
            [entity_type, entity_id, changed_fields, datetime.now(timezone.utc)],
        )

    return {"ok": True, "entity_id": entity_id, "updated_fields": changed_fields}


@router.post("/entities/{entity_type}/{entity_id}/tags")
def add_entity_tag(
    entity_type: str,
    entity_id: str,
    body: EntityTagRequest,
    db: Database = Depends(get_db),
):
    """Add or update a tag on an entity."""
    if entity_type not in ENTITY_TABLES:
        raise HTTPException(400, f"Unknown entity type: {entity_type}")

    if not _table_exists(db, "entity_tags"):
        raise HTTPException(501, "entity_tags table not available")

    db.execute(
        """
        INSERT INTO entity_tags (entity_type, entity_id, tag_name, tag_value, created_by, created_at)
        VALUES (%s, %s::uuid, %s, %s, 'user', NOW())
        ON CONFLICT (entity_type, entity_id, tag_name)
        DO UPDATE SET tag_value = EXCLUDED.tag_value, created_at = NOW()
        """,
        [entity_type, entity_id, body.tag_name, body.tag_value],
    )

    return {"ok": True, "tag": body.tag_name}


# ── Change Log / Audit Trail ──


@router.get("/changes")
def list_changes(
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    change_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_db),
):
    """Browse the data change audit trail with entity names resolved."""
    if not _table_exists(db, "data_change_log"):
        return {"changes": [], "total": 0, "summary": {}}

    conditions = []
    params: list = []

    if entity_type:
        conditions.append("entity_type = %s")
        params.append(entity_type)
    if entity_id:
        conditions.append("entity_id = %s")
        params.append(entity_id)
    if change_type:
        conditions.append("change_type = %s")
        params.append(change_type)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    count_row = db.fetch_one(f"SELECT COUNT(*) AS total FROM data_change_log {where}", params)
    total = count_row["total"] if count_row else 0

    # Summary breakdown by type and change_type
    summary = db.fetch_all(
        f"""
        SELECT entity_type, change_type, COUNT(*) AS cnt
        FROM data_change_log
        {where}
        GROUP BY entity_type, change_type
        ORDER BY cnt DESC
        """,
        params[:len(params)],  # reuse filter params without limit/offset
    )

    params.extend([limit, offset])
    rows = db.fetch_all(
        f"""
        SELECT cl.id, cl.entity_type, cl.entity_id, cl.change_type,
               cl.changed_fields, cl.etl_run_id, cl.changed_at,
               COALESCE(vl.label, cl.entity_id) AS entity_label
        FROM data_change_log cl
        LEFT JOIN v_entity_labels vl
          ON cl.entity_id = vl.entity_id AND cl.entity_type = vl.entity_type
        {where.replace('entity_type', 'cl.entity_type').replace('entity_id', 'cl.entity_id').replace('change_type', 'cl.change_type') if where else ''}
        ORDER BY cl.changed_at DESC
        LIMIT %s OFFSET %s
        """,
        params,
    )

    return {"changes": rows, "total": total, "limit": limit, "offset": offset, "summary": summary}


# ── HITL Review Queue ──


@router.get("/hitl")
def list_hitl_items(
    status_filter: Optional[str] = Query("pending"),
    entity_type: Optional[str] = Query(None),
    review_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_db),
):
    """List items in the HITL review queue with entity context."""
    if not _table_exists(db, "hitl_review_queue"):
        return {"items": [], "total": 0, "summary": {}}

    conditions = []
    params: list = []

    if status_filter:
        conditions.append("h.status = %s")
        params.append(status_filter)
    if entity_type:
        conditions.append("h.entity_type = %s")
        params.append(entity_type)
    if review_type:
        conditions.append("h.review_type = %s")
        params.append(review_type)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    bare_where = where.replace("h.", "")

    count_row = db.fetch_one(f"SELECT COUNT(*) AS total FROM hitl_review_queue h {where}", params)
    total = count_row["total"] if count_row else 0

    # Summary breakdown
    summary = db.fetch_all(
        f"""
        SELECT review_type, entity_type, COUNT(*) AS cnt
        FROM hitl_review_queue h
        {where}
        GROUP BY review_type, entity_type
        ORDER BY cnt DESC
        """,
        params[:len(params)],
    )

    params.extend([limit, offset])
    rows = db.fetch_all(
        f"""
        SELECT h.id, h.review_type, h.entity_type, h.entity_id, h.priority,
               h.status, h.payload, h.assigned_to, h.created_at, h.resolved_at,
               COALESCE(vl.label, h.entity_id) AS entity_label
        FROM hitl_review_queue h
        LEFT JOIN v_entity_labels vl
          ON h.entity_id = vl.entity_id AND h.entity_type = vl.entity_type
        {where}
        ORDER BY h.priority DESC, h.created_at ASC
        LIMIT %s OFFSET %s
        """,
        params,
    )

    # Add human-readable descriptions
    for row in rows:
        row["description"] = _hitl_description(row)

    return {"items": rows, "total": total, "limit": limit, "offset": offset, "summary": summary}


@router.post("/hitl/{review_id}/resolve")
def resolve_hitl(
    review_id: str,
    body: HITLResolveRequest,
    db: Database = Depends(get_db),
):
    """Resolve a HITL review item (approve, reject, defer)."""
    if body.action not in ("approved", "rejected", "deferred"):
        raise HTTPException(400, "action must be approved, rejected, or deferred")

    if not _table_exists(db, "hitl_review_queue"):
        raise HTTPException(501, "HITL queue not available")

    existing = db.fetch_one("SELECT id, status FROM hitl_review_queue WHERE id = %s", [review_id])
    if not existing:
        raise HTTPException(404, "Review item not found")

    db.execute(
        """
        UPDATE hitl_review_queue
        SET status = %s,
            resolution = %s::jsonb,
            resolved_at = NOW()
        WHERE id = %s
        """,
        [
            body.action,
            f'{{"notes": "{body.resolution_notes}", "resolved_by": "user", "resolved_at": "{datetime.now(timezone.utc).isoformat()}"}}',
            review_id,
        ],
    )

    return {"ok": True, "review_id": review_id, "new_status": body.action}


# ── Quality Overview ──


@router.get("/quality")
def quality_overview(
    entity_type: Optional[str] = Query(None),
    db: Database = Depends(get_db),
):
    """Quality overview with per-type scores, top failing rules, and worst entities."""
    if not _table_exists(db, "data_quality_results"):
        return {"summary": [], "rules": [], "top_failures": [], "worst_entities": []}

    # Per-type summary
    type_cond = "WHERE r.entity_type = %s" if entity_type else ""
    type_params = [entity_type] if entity_type else []

    summary = db.fetch_all(
        f"""
        SELECT r.entity_type,
               COUNT(DISTINCT r.entity_id) AS entities_assessed,
               ROUND(AVG(r.score)::numeric, 3) AS avg_score,
               COUNT(*) FILTER (WHERE r.passed) AS rules_passed,
               COUNT(*) FILTER (WHERE NOT r.passed) AS rules_failed
        FROM data_quality_results r
        {type_cond}
        GROUP BY r.entity_type
        ORDER BY avg_score ASC
        """,
        type_params,
    )

    # Rules with failure counts
    rules = db.fetch_all(
        """
        SELECT q.id, q.entity_type, q.rule_name, q.rule_type, q.severity, q.enabled,
               COUNT(r.id) FILTER (WHERE NOT r.passed) AS failure_count,
               COUNT(r.id) AS total_assessed
        FROM data_quality_rules q
        LEFT JOIN data_quality_results r ON r.rule_id = q.id
        GROUP BY q.id, q.entity_type, q.rule_name, q.rule_type, q.severity, q.enabled
        ORDER BY failure_count DESC
        """
    )

    # Top failing rules (actionable)
    top_failures = db.fetch_all(
        f"""
        SELECT q.rule_name, q.entity_type, q.severity, q.rule_type,
               COUNT(*) AS failure_count,
               ROUND(AVG(r.score)::numeric, 3) AS avg_score
        FROM data_quality_results r
        JOIN data_quality_rules q ON q.id = r.rule_id
        WHERE NOT r.passed
        {('AND r.entity_type = %s' if entity_type else '')}
        GROUP BY q.rule_name, q.entity_type, q.severity, q.rule_type
        ORDER BY failure_count DESC
        LIMIT 10
        """,
        [entity_type] if entity_type else [],
    )

    # Worst entities (lowest scores with names)
    worst_entities = db.fetch_all(
        f"""
        SELECT r.entity_type, r.entity_id,
               COALESCE(vl.label, r.entity_id) AS entity_label,
               ROUND(AVG(r.score)::numeric, 3) AS avg_score,
               COUNT(*) FILTER (WHERE NOT r.passed) AS failures,
               array_agg(DISTINCT q.rule_name) FILTER (WHERE NOT r.passed) AS failing_rules
        FROM data_quality_results r
        JOIN data_quality_rules q ON q.id = r.rule_id
        LEFT JOIN v_entity_labels vl ON vl.entity_id = r.entity_id AND vl.entity_type = r.entity_type
        {('WHERE r.entity_type = %s' if entity_type else '')}
        GROUP BY r.entity_type, r.entity_id, vl.label
        HAVING COUNT(*) FILTER (WHERE NOT r.passed) > 0
        ORDER BY avg_score ASC
        LIMIT 20
        """,
        [entity_type] if entity_type else [],
    )

    return {"summary": summary, "rules": rules, "top_failures": top_failures, "worst_entities": worst_entities}


# ── Enrichment / Curation ──


@router.post("/enrich")
def request_enrichment(
    body: EnrichmentRequest,
    db: Database = Depends(get_db),
):
    """Request data enrichment/curation for a scope (e.g., add a therapeutic area).

    Creates a HITL review item for tracking and can trigger pipeline connectors.
    """
    if not _table_exists(db, "hitl_review_queue"):
        raise HTTPException(501, "HITL queue not available for tracking enrichment requests")

    review_id = str(uuid.uuid4())
    db.execute(
        """
        INSERT INTO hitl_review_queue (id, review_type, entity_type, entity_id, priority, status, payload, created_at)
        VALUES (%s, 'enrichment_request', %s, %s, 5, 'pending', %s::jsonb, NOW())
        """,
        [
            review_id,
            body.entity_type,
            body.scope,
            f'{{"scope": "{body.scope}", "description": "{body.description}", "requested_by": "user"}}',
        ],
    )

    return {
        "ok": True,
        "review_id": review_id,
        "message": f"Enrichment request created for {body.entity_type}: {body.scope}",
    }


@router.get("/completeness")
def field_completeness(
    entity_type: Optional[str] = Query(None),
    db: Database = Depends(get_db),
):
    """Per-field completeness rates by entity type."""
    results = {}
    required_fields = {
        "drug": ["generic_name", "brand_name", "company_id", "therapeutic_area_id",
                 "mechanism_id", "approval_date"],
        "company": ["name", "ticker", "country", "region", "market_cap_tier"],
        "trial": ["official_title", "sponsor_name", "status", "phase",
                  "conditions", "start_date", "label"],
        "therapeutic_area": ["name", "mesh_id", "scope_note"],
        "mechanism": ["name", "mesh_id"],
        "article": ["title", "pmid", "journal", "publication_date", "mesh_terms"],
    }

    types_to_check = [entity_type] if entity_type else list(required_fields.keys())

    for etype in types_to_check:
        if etype not in ENTITY_TABLES or etype not in required_fields:
            continue
        meta = ENTITY_TABLES[etype]
        fields = required_fields[etype]
        total_row = db.fetch_one(f"SELECT COUNT(*) AS cnt FROM {meta['table']}")
        total = total_row["cnt"] if total_row else 0
        if total == 0:
            results[etype] = {"total": 0, "fields": {}, "overall": 0.0}
            continue

        field_scores = {}
        for field in fields:
            try:
                row = db.fetch_one(
                    f"SELECT COUNT(*) AS filled FROM {meta['table']} WHERE {field} IS NOT NULL AND {field}::text != ''"
                )
                field_scores[field] = round((row["filled"] if row else 0) / total, 3)
            except Exception:
                field_scores[field] = 0.0

        overall = sum(field_scores.values()) / len(field_scores) if field_scores else 0.0
        results[etype] = {"total": total, "fields": field_scores, "overall": round(overall, 3)}

    return {"completeness": results}


class BulkUpdateRequest(BaseModel):
    entity_ids: list[str]
    fields: dict[str, str | int | float | bool | None]
    reason: str = ""


@router.post("/bulk-update")
def bulk_update_entities(
    entity_type: str = Query(...),
    body: BulkUpdateRequest = ...,
    db: Database = Depends(get_db),
):
    """Batch update entities of the same type."""
    if entity_type not in ENTITY_TABLES:
        raise HTTPException(400, f"Unknown entity type: {entity_type}")

    meta = ENTITY_TABLES[entity_type]
    editable = set(meta["editable_cols"])
    invalid = set(body.fields.keys()) - editable
    if invalid:
        raise HTTPException(400, f"Non-editable fields: {invalid}")

    set_parts = [f"{col} = %s" for col in body.fields]
    base_values = list(body.fields.values())
    updated = 0

    for eid in body.entity_ids:
        db.execute(
            f"UPDATE {meta['table']} SET {', '.join(set_parts)} WHERE {meta['id_col']} = %s",
            base_values + [eid],
        )
        if _table_exists(db, "data_change_log"):
            db.execute(
                """
                INSERT INTO data_change_log (entity_type, entity_id, change_type, changed_fields, changed_at)
                VALUES (%s, %s, 'bulk_update', %s, %s)
                """,
                [entity_type, eid, list(body.fields.keys()), datetime.now(timezone.utc)],
            )
        updated += 1

    return {"ok": True, "updated": updated, "entity_type": entity_type}


class BulkResolveRequest(BaseModel):
    review_ids: list[str]
    action: str  # approved, rejected, deferred
    resolution_notes: str = ""


@router.post("/bulk-resolve")
def bulk_resolve_hitl(
    body: BulkResolveRequest,
    db: Database = Depends(get_db),
):
    """Batch resolve HITL review items."""
    if body.action not in ("approved", "rejected", "deferred"):
        raise HTTPException(400, "action must be approved, rejected, or deferred")

    if not _table_exists(db, "hitl_review_queue"):
        raise HTTPException(501, "HITL queue not available")

    resolved = 0
    for rid in body.review_ids:
        db.execute(
            """
            UPDATE hitl_review_queue
            SET status = %s,
                resolution = %s::jsonb,
                resolved_at = NOW()
            WHERE id = %s AND status = 'pending'
            """,
            [
                body.action,
                f'{{"notes": "{body.resolution_notes}", "resolved_by": "user", "resolved_at": "{datetime.now(timezone.utc).isoformat()}"}}',
                rid,
            ],
        )
        resolved += 1

    return {"ok": True, "resolved": resolved, "action": body.action}


@router.get("/freshness")
def source_freshness(db: Database = Depends(get_db)):
    """Per-source freshness report."""
    freshness = {}
    for etype, meta in ENTITY_TABLES.items():
        try:
            rows = db.fetch_all(
                f"""
                SELECT source_api,
                       COUNT(*) AS records,
                       MAX(retrieved_at) AS latest,
                       EXTRACT(EPOCH FROM (NOW() - MAX(retrieved_at))) / 86400 AS days_since
                FROM {meta['table']}
                WHERE source_api IS NOT NULL
                GROUP BY source_api
                ORDER BY days_since DESC
                """
            )
            for row in rows:
                source = row["source_api"]
                freshness[source] = {
                    "entity_type": etype,
                    "records": row["records"],
                    "latest": row["latest"].isoformat() if row.get("latest") and hasattr(row["latest"], "isoformat") else None,
                    "days_since": round(float(row["days_since"]), 1) if row.get("days_since") else None,
                    "stale": float(row["days_since"]) > 30 if row.get("days_since") else True,
                }
        except Exception:
            continue

    return {"freshness": freshness}


class RunEnrichmentRequest(BaseModel):
    entity_type: str = "drug"
    max_entities: int = 50


@router.post("/run-enrichment")
def run_enrichment(
    body: RunEnrichmentRequest,
    db: Database = Depends(get_db),
):
    """Trigger AI enrichment for an entity set."""
    try:
        from scripts.ai_enrich import run as run_ai_enrich
        results = run_ai_enrich(entity_type=body.entity_type, max_entities=body.max_entities)
        return {"ok": True, "results": results}
    except Exception as e:
        logger.error("AI enrichment failed: %s", e)
        raise HTTPException(500, f"Enrichment failed: {e}")


@router.post("/refresh-views")
def refresh_materialized_views(
    metrics_svc: PharmaMetrics = Depends(get_metrics),
):
    """Refresh all materialized views (pipeline, success rate, etc.)."""
    result = metrics_svc.refresh()
    return {"ok": True, "views": result}


# ── Stats summary (for the overview dashboard) ──


@router.get("/stats")
def catalog_stats(db: Database = Depends(get_db)):
    """Quick stats for the catalog overview header."""
    stats = {}

    for etype, meta in ENTITY_TABLES.items():
        try:
            row = db.fetch_one(f"SELECT COUNT(*) AS cnt FROM {meta['table']}")
            stats[etype] = row["cnt"] if row else 0
        except Exception:
            stats[etype] = 0

    # Quality stats
    quality_stats = {}
    if _table_exists(db, "data_quality_results"):
        qrow = db.fetch_one(
            """
            SELECT COUNT(DISTINCT entity_id) AS assessed,
                   ROUND(AVG(score)::numeric, 3) AS avg_score,
                   COUNT(*) FILTER (WHERE NOT passed) AS failures
            FROM data_quality_results
            """
        )
        if qrow:
            quality_stats = dict(qrow)

    # HITL stats
    hitl_stats = {}
    if _table_exists(db, "hitl_review_queue"):
        hrow = db.fetch_one(
            """
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                   COUNT(*) FILTER (WHERE status = 'approved') AS approved,
                   COUNT(*) FILTER (WHERE status = 'rejected') AS rejected
            FROM hitl_review_queue
            """
        )
        if hrow:
            hitl_stats = dict(hrow)

    # Change log stats
    change_stats = {}
    if _table_exists(db, "data_change_log"):
        crow = db.fetch_one(
            """
            SELECT COUNT(*) AS total_changes,
                   COUNT(*) FILTER (WHERE changed_at > NOW() - INTERVAL '7 days') AS recent_changes
            FROM data_change_log
            """
        )
        if crow:
            change_stats = dict(crow)

    return {
        "entity_counts": stats,
        "quality": quality_stats,
        "hitl": hitl_stats,
        "changes": change_stats,
    }


# ── Helpers ──


def _table_exists(db: Database, table_name: str) -> bool:
    """Check if a table exists in the database."""
    try:
        row = db.fetch_one(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s) AS exists_",
            [table_name],
        )
        return bool(row and row.get("exists_"))
    except Exception:
        return False


def _hitl_description(row: dict) -> str:
    """Generate a human-readable description for a HITL review item."""
    review_type = row.get("review_type", "")
    entity_type = row.get("entity_type", "")
    entity_label = row.get("entity_label", row.get("entity_id", ""))
    payload = row.get("payload") or {}

    if review_type == "entity_resolution":
        raw = payload.get("raw_value", "")
        confidence = payload.get("confidence", 0)
        source = payload.get("source_type", "")
        candidates = payload.get("candidates") or []
        if raw:
            desc = f'Could not auto-resolve "{raw}" from {source} to a known {entity_type}.'
            if candidates:
                desc += f" {len(candidates)} possible matches found."
            elif confidence == 0:
                desc += " No candidates found — may need manual creation."
            return desc
        return f"Unresolved {entity_type}: {entity_label}"

    if review_type == "quality_failure":
        rule = payload.get("rule_name", "")
        issue = payload.get("issue", "")
        return f'Quality check "{rule}" failed for {entity_type} "{entity_label}": {issue}'

    if review_type == "enrichment_request":
        scope = payload.get("scope", "")
        desc_text = payload.get("description", "")
        return f"Enrichment requested for {entity_type}: {scope}" + (f" — {desc_text}" if desc_text else "")

    if review_type == "duplicate_candidate":
        dup_of = payload.get("duplicate_of", "")
        return f'{entity_type} "{entity_label}" may be a duplicate of "{dup_of}"'

    return f"{review_type} review for {entity_type}: {entity_label}"


def _compute_dataset_stats(db: Database) -> list[dict]:
    """Compute dataset stats from actual tables when dataset_catalog is empty."""
    datasets = []
    table_map = {
        "drugs": ("drug", "Drugs from FDA Orange Book, ClinicalTrials.gov, and other sources"),
        "clinical_trials": ("trial", "Clinical trial records from ClinicalTrials.gov"),
        "pubmed_articles": ("article", "PubMed literature and abstracts"),
        "companies": ("company", "Pharmaceutical companies"),
        "market_events": ("event", "Market events and regulatory milestones"),
        "therapeutic_areas": ("therapeutic_area", "MeSH-based therapeutic area ontology"),
        "mechanisms_of_action": ("mechanism", "Drug mechanism of action ontology"),
        "entity_links": (None, "Cross-entity relationship graph"),
    }

    for table, (etype, desc) in table_map.items():
        try:
            row = db.fetch_one(f"SELECT COUNT(*) AS cnt FROM {table}")
            count = row["cnt"] if row else 0

            freshness_row = None
            if table not in ("entity_links", "therapeutic_areas", "mechanisms_of_action"):
                freshness_row = db.fetch_one(f"SELECT MAX(retrieved_at) AS latest FROM {table}")

            quality_row = None
            if etype and _table_exists(db, "data_quality_results"):
                quality_row = db.fetch_one(
                    "SELECT ROUND(AVG(score)::numeric, 3) AS avg_score FROM data_quality_results WHERE entity_type = %s",
                    [etype],
                )

            datasets.append({
                "dataset_name": table,
                "source_type": "database",
                "entity_type": etype,
                "table_name": table,
                "row_count": count,
                "last_refreshed_at": (
                    freshness_row["latest"].isoformat()
                    if freshness_row and freshness_row.get("latest") and hasattr(freshness_row["latest"], "isoformat")
                    else None
                ),
                "quality_score_avg": float(quality_row["avg_score"]) if quality_row and quality_row.get("avg_score") else None,
                "description": desc,
            })
        except Exception as e:
            logger.warning("Error computing stats for %s: %s", table, e)

    return datasets
