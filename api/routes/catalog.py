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
    "nadac": {
        "display_name": "CMS NADAC Pricing",
        "description": "National Average Drug Acquisition Cost — Medicaid benchmark pricing for drugs.",
        "source_url": "https://data.medicaid.gov",
        "entity_types": ["drug"],
        "refresh_schedule": "Weekly on Saturday at 05:00 UTC",
        "collection_method": "API (Socrata JSON)",
        "fields_collected": [
            "NDC Code", "Drug Name", "NADAC Per Unit", "Pricing Unit",
            "Effective Date", "Classification",
        ],
        "coverage_notes": "Covers drugs reimbursed by Medicaid. Provides acquisition cost benchmark for US market pricing analysis.",
    },
    "pharma_news": {
        "display_name": "Pharma News & Events",
        "description": "Real-time competitive signals from FDA press releases and pharma news aggregators.",
        "source_url": "https://www.fda.gov/news-events",
        "entity_types": ["event"],
        "refresh_schedule": "Daily at 06:00 UTC",
        "collection_method": "RSS Feed (XML)",
        "fields_collected": [
            "Title", "Event Type", "Event Date", "Source", "URL",
            "Classification (approval/trial_readout/M&A/safety)",
        ],
        "coverage_notes": "FDA press releases + Google News pharma queries. Provides real-time event layer for competitive intelligence.",
    },
    "chembl": {
        "display_name": "ChEMBL Bioactivity",
        "description": "EBI ChEMBL database — molecular bioactivity data, drug-target interactions, and mechanism of action.",
        "source_url": "https://www.ebi.ac.uk/chembl/",
        "entity_types": ["drug", "target"],
        "refresh_schedule": "Weekly on Saturday at 05:30 UTC",
        "collection_method": "API (REST JSON)",
        "fields_collected": [
            "ChEMBL ID", "Molecule Type", "Max Phase", "Molecular Weight",
            "LogP", "SMILES", "Mechanism of Action", "Target Name",
            "Activity Type (IC50/Ki/EC50)", "pChEMBL Value", "Assay Type",
        ],
        "coverage_notes": "2.4M+ compounds, 15K+ targets, 20M+ bioactivity measurements. Enables target-based competitive analysis and SAR.",
    },
    "pubchem": {
        "display_name": "PubChem Compounds",
        "description": "NCBI PubChem — chemical identity, molecular properties, synonyms, and structure data.",
        "source_url": "https://pubchem.ncbi.nlm.nih.gov/",
        "entity_types": ["drug"],
        "refresh_schedule": "Weekly on Saturday at 06:00 UTC",
        "collection_method": "API (PUG REST JSON)",
        "fields_collected": [
            "PubChem CID", "Canonical SMILES", "InChI", "InChIKey",
            "Molecular Formula", "Molecular Weight", "XLogP",
            "H-Bond Donors/Acceptors", "TPSA", "Synonyms", "IUPAC Name",
        ],
        "coverage_notes": "116M+ compounds. Provides molecular identity layer connecting drug names to chemical structures.",
    },
    "open_targets": {
        "display_name": "Open Targets Genetics",
        "description": "EBI/Wellcome Open Targets Platform — genetic evidence for drug target validation and disease associations.",
        "source_url": "https://platform.opentargets.org/",
        "entity_types": ["target", "drug"],
        "refresh_schedule": "Weekly on Saturday at 06:30 UTC",
        "collection_method": "API (GraphQL)",
        "fields_collected": [
            "Target Gene Symbol", "Target Name", "Disease Associations",
            "Overall Association Score", "Genetic Evidence Score",
            "Known Drug Score", "Tractability", "Druggability",
        ],
        "coverage_notes": "Links drug targets to disease causality via GWAS, rare disease, and somatic mutation evidence. Strongest predictor of clinical trial success.",
    },
    "ema": {
        "display_name": "EMA (EU Medicines)",
        "description": "European Medicines Agency — EU-authorised medicines and EU Clinical Trials Register.",
        "source_url": "https://www.ema.europa.eu",
        "entity_types": ["trial", "drug"],
        "refresh_schedule": "Weekly on Friday at 04:30 UTC",
        "collection_method": "API (REST JSON + EUCTR)",
        "fields_collected": [
            "EudraCT Number", "Title", "Sponsor", "Phase", "Status",
            "Conditions", "Start Date", "Country", "Marketing Authorisation",
        ],
        "coverage_notes": "Covers EU-authorised medicines and trials registered in the EU Clinical Trials Register. Eliminates US-centric bias in trial coverage.",
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

    # Freshness label — relative to expected schedule
    freshness_label = "unknown"
    days_old = None
    if last_refreshed:
        try:
            from datetime import datetime as _dt, timezone as _tz
            latest_dt = _dt.fromisoformat(last_refreshed.replace("Z", "+00:00"))
            days_old = (_dt.now(_tz.utc) - latest_dt).days
            freshness_label = "fresh" if days_old <= 2 else "recent" if days_old <= 7 else "stale"
        except Exception:
            pass

    profile["records"] = records
    profile["quality_score"] = quality_score
    profile["last_refreshed"] = last_refreshed
    profile["freshness"] = freshness_label
    profile["days_since_refresh"] = days_old

    return profile


@router.get("/featured")
def featured_entities(db: Database = Depends(get_db)):
    """Return top 3 entities per type by pipeline score for showcase display."""
    drugs: list[dict] = []
    companies: list[dict] = []
    try:
        drugs = db.fetch_all("""
            SELECT d.id, d.generic_name AS name, d.brand_name, 'drug' AS entity_type,
                   m.name AS mechanism_name, c.name AS company_name,
                   COALESCE(mv.pipeline_score, 0) AS pipeline_score,
                   (SELECT COUNT(*) FROM clinical_trials ct WHERE ct.drug_id = d.id) AS trial_count,
                   d.quality_score
            FROM drugs d
            LEFT JOIN mechanisms_of_action m ON d.mechanism_id = m.id
            LEFT JOIN companies c ON d.company_id = c.id
            LEFT JOIN mv_drug_pipeline_strength mv ON mv.drug_id = d.id
            ORDER BY pipeline_score DESC NULLS LAST
            LIMIT 3
        """)
    except Exception:
        logger.debug("featured_entities: drug query failed (mv may not exist)")

    try:
        companies = db.fetch_all("""
            SELECT c.id, c.name, 'company' AS entity_type, c.ticker,
                   (SELECT COUNT(*) FROM drugs d WHERE d.company_id = c.id) AS drug_count,
                   (SELECT COUNT(*) FROM entity_links el
                    WHERE el.source_entity_id = c.id::text
                      AND el.link_type = 'SPONSORS') AS trial_count,
                   c.quality_score
            FROM companies c
            ORDER BY (
                SELECT COALESCE(SUM(mv.pipeline_score), 0)
                FROM mv_drug_pipeline_strength mv
                JOIN drugs d ON mv.drug_id = d.id
                WHERE d.company_id = c.id
            ) DESC
            LIMIT 3
        """)
    except Exception:
        logger.debug("featured_entities: company query failed (mv may not exist)")

    return {"featured": {"drugs": drugs, "companies": companies}}


# ── Sort parameter values ──
_VALID_SORT_VALUES = {"pipeline_score", "quality", "name", "recent"}


@router.get("/entities/{entity_type}")
def browse_entities(
    entity_type: str,
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="Filter by record_status"),
    quality_min: Optional[float] = Query(None, ge=0, le=1),
    sort: Optional[str] = Query(None, description="Sort mode: pipeline_score, quality, name, recent"),
    sort_by: Optional[str] = Query(None, description="(deprecated) Sort column"),
    sort_dir: Optional[str] = Query(None, pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_db),
):
    """Browse entities with rich joined metadata, search, filtering, and pagination."""
    if entity_type not in ENTITY_TABLES:
        raise HTTPException(400, f"Unknown entity type: {entity_type}. Valid: {list(ENTITY_TABLES.keys())}")

    meta = ENTITY_TABLES[entity_type]

    # ── Rich queries for drugs and companies; fallback for other types ──
    if entity_type == "drug":
        return _browse_drugs(search, status, quality_min, sort, sort_by, sort_dir, limit, offset, db, meta)
    elif entity_type == "company":
        return _browse_companies(search, status, quality_min, sort, sort_by, sort_dir, limit, offset, db, meta)
    else:
        return _browse_generic(entity_type, search, status, quality_min, sort, sort_by, sort_dir, limit, offset, db, meta)


def _resolve_sort(
    entity_type: str,
    sort: Optional[str],
    sort_by: Optional[str],
    sort_dir: Optional[str],
) -> tuple[str, str]:
    """Resolve sort column and direction from new `sort` or legacy `sort_by`/`sort_dir`.

    Returns (order_clause, direction) suitable for interpolation into SQL.
    """
    # New sort parameter takes precedence
    if sort and sort in _VALID_SORT_VALUES:
        if sort == "pipeline_score":
            return "pipeline_score", "DESC"
        elif sort == "quality":
            return "quality_score", "DESC"
        elif sort == "name":
            return "_label", "ASC"
        elif sort == "recent":
            if entity_type == "trial":
                return "start_date", "DESC"
            return "retrieved_at", "DESC"

    # Legacy sort_by support
    if sort_by:
        direction = "DESC" if sort_dir == "desc" else "ASC"
        if sort_by == "label":
            return "_label", direction
        elif sort_by == "quality":
            return "quality_score", direction
        elif sort_by == "updated":
            return "retrieved_at", direction
        elif sort_by == "status":
            return "record_status", direction
        return "_label", direction

    # Default sort per entity type
    if entity_type == "drug":
        return "pipeline_score", "DESC"
    elif entity_type == "company":
        return "pipeline_score", "DESC"
    elif entity_type == "trial":
        return "start_date", "DESC"
    else:
        return "quality_score", "DESC"


def _browse_drugs(
    search, status, quality_min, sort, sort_by, sort_dir,
    limit_val, offset_val, db, meta,
) -> dict:
    """Browse drugs with joined mechanism, company, TA, trial count, pipeline score."""
    conditions = []
    params: list = []

    if search:
        conditions.append("(d.generic_name ILIKE %s OR d.brand_name ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    if status:
        conditions.append("d.record_status = %s")
        params.append(status)
    else:
        # Default: hide merged and excluded records
        conditions.append("(d.record_status IS NULL OR d.record_status NOT IN ('excluded', 'merged'))")
    if quality_min is not None:
        conditions.append("d.quality_score >= %s")
        params.append(quality_min)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sort_col, direction = _resolve_sort("drug", sort, sort_by, sort_dir)

    # Count from base table with same filters
    count_params = list(params)
    count_row = db.fetch_one(
        f"SELECT COUNT(*) AS total FROM drugs d {where}", count_params,
    )
    total = count_row["total"] if count_row else 0

    # Subqueries to resolve company/mechanism/TA from entity_links when FK is NULL
    company_fallback = """
        COALESCE(c.name,
            (SELECT c2.name FROM entity_links el
             JOIN companies c2 ON c2.id::text = el.source_entity_id
             WHERE el.target_entity_id = d.id::text AND el.link_type = 'OWNS'
             LIMIT 1)
        ) AS company_name"""
    mechanism_fallback = """
        COALESCE(m.name,
            (SELECT m2.name FROM entity_links el
             JOIN mechanisms_of_action m2 ON m2.id::text = el.target_entity_id
             WHERE el.source_entity_id = d.id::text AND el.link_type = 'TARGETS_MECHANISM'
             LIMIT 1)
        ) AS mechanism_name"""
    ta_fallback = """
        COALESCE(ta.name,
            (SELECT ta2.name FROM entity_links el
             JOIN therapeutic_areas ta2 ON ta2.id::text = el.target_entity_id
             WHERE el.source_entity_id = d.id::text AND el.link_type = 'IN_THERAPEUTIC_AREA'
             LIMIT 1)
        ) AS therapeutic_area"""

    params.extend([limit_val, offset_val])
    try:
        rows = db.fetch_all(
            f"""
            SELECT d.id, d.generic_name AS _label, d.brand_name, d.approval_date,
                   d.supply_status, d.quality_score, d.record_status,
                   {mechanism_fallback},
                   {company_fallback},
                   {ta_fallback},
                   (SELECT COUNT(*) FROM clinical_trials ct WHERE ct.drug_id = d.id) AS trial_count,
                   COALESCE(mv.pipeline_score, 0) AS pipeline_score
            FROM drugs d
            LEFT JOIN mechanisms_of_action m ON d.mechanism_id = m.id
            LEFT JOIN companies c ON d.company_id = c.id
            LEFT JOIN therapeutic_areas ta ON d.therapeutic_area_id = ta.id
            LEFT JOIN mv_drug_pipeline_strength mv ON mv.drug_id = d.id
            {where}
            ORDER BY {sort_col} {direction} NULLS LAST
            LIMIT %s OFFSET %s
            """,
            params,
        )
    except Exception:
        # Fallback: mv_drug_pipeline_strength may not exist
        logger.debug("browse_drugs: rich query failed, falling back to simple join")
        fallback_sort = "d.quality_score" if sort_col == "pipeline_score" else sort_col
        if fallback_sort == "_label":
            fallback_sort = "d.generic_name"
        rows = db.fetch_all(
            f"""
            SELECT d.id, d.generic_name AS _label, d.brand_name, d.approval_date,
                   d.supply_status, d.quality_score, d.record_status,
                   {mechanism_fallback},
                   {company_fallback},
                   {ta_fallback},
                   (SELECT COUNT(*) FROM clinical_trials ct WHERE ct.drug_id = d.id) AS trial_count,
                   0 AS pipeline_score
            FROM drugs d
            LEFT JOIN mechanisms_of_action m ON d.mechanism_id = m.id
            LEFT JOIN companies c ON d.company_id = c.id
            LEFT JOIN therapeutic_areas ta ON d.therapeutic_area_id = ta.id
            {where}
            ORDER BY {fallback_sort} {direction} NULLS LAST
            LIMIT %s OFFSET %s
            """,
            params,
        )

    return {
        "entity_type": "drug",
        "results": rows,
        "total": total,
        "limit": limit_val,
        "offset": offset_val,
        "editable_fields": meta["editable_cols"],
    }


def _browse_companies(
    search, status, quality_min, sort, sort_by, sort_dir,
    limit_val, offset_val, db, meta,
) -> dict:
    """Browse companies with drug count, trial count, pipeline score."""
    conditions = []
    params: list = []

    if search:
        conditions.append("(c.name ILIKE %s OR c.ticker ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    if status:
        conditions.append("c.record_status = %s")
        params.append(status)
    else:
        conditions.append("(c.record_status IS NULL OR c.record_status NOT IN ('excluded', 'merged'))")
    if quality_min is not None:
        conditions.append("c.quality_score >= %s")
        params.append(quality_min)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sort_col, direction = _resolve_sort("company", sort, sort_by, sort_dir)

    count_params = list(params)
    count_row = db.fetch_one(
        f"SELECT COUNT(*) AS total FROM companies c {where}", count_params,
    )
    total = count_row["total"] if count_row else 0

    params.extend([limit_val, offset_val])
    try:
        rows = db.fetch_all(
            f"""
            SELECT c.id, c.name AS _label, c.ticker, c.cik, c.country,
                   c.quality_score, c.record_status,
                   (SELECT COUNT(*) FROM drugs d WHERE d.company_id = c.id) AS drug_count,
                   (SELECT COUNT(*) FROM entity_links el
                    WHERE el.source_entity_id = c.id::text
                      AND el.link_type = 'SPONSORS') AS trial_count,
                   COALESCE((
                       SELECT SUM(mv.pipeline_score)
                       FROM mv_drug_pipeline_strength mv
                       JOIN drugs d2 ON mv.drug_id = d2.id
                       WHERE d2.company_id = c.id
                   ), 0) AS pipeline_score
            FROM companies c
            {where}
            ORDER BY {sort_col} {direction} NULLS LAST
            LIMIT %s OFFSET %s
            """,
            params,
        )
    except Exception:
        # Fallback: mv_drug_pipeline_strength may not exist
        logger.debug("browse_companies: rich query failed, falling back to simple query")
        fallback_sort = "c.quality_score" if sort_col == "pipeline_score" else sort_col
        if fallback_sort == "_label":
            fallback_sort = "c.name"
        rows = db.fetch_all(
            f"""
            SELECT c.id, c.name AS _label, c.ticker, c.cik, c.country,
                   c.quality_score, c.record_status,
                   (SELECT COUNT(*) FROM drugs d WHERE d.company_id = c.id) AS drug_count,
                   (SELECT COUNT(*) FROM entity_links el
                    WHERE el.source_entity_id = c.id::text
                      AND el.link_type = 'SPONSORS') AS trial_count,
                   0 AS pipeline_score
            FROM companies c
            {where}
            ORDER BY {fallback_sort} {direction} NULLS LAST
            LIMIT %s OFFSET %s
            """,
            params,
        )

    return {
        "entity_type": "company",
        "results": rows,
        "total": total,
        "limit": limit_val,
        "offset": offset_val,
        "editable_fields": meta["editable_cols"],
    }


def _browse_generic(
    entity_type, search, status, quality_min, sort, sort_by, sort_dir,
    limit_val, offset_val, db, meta,
) -> dict:
    """Browse non-drug, non-company entity types with the original flat query."""
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
    elif "record_status" in meta["display_cols"]:
        conditions.append("(record_status IS NULL OR record_status NOT IN ('excluded', 'merged'))")

    if quality_min is not None and "quality_score" in meta["display_cols"]:
        conditions.append("quality_score >= %s")
        params.append(quality_min)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    sort_col, direction = _resolve_sort(entity_type, sort, sort_by, sort_dir)
    # Map abstract sort columns to actual table columns for generic types
    if sort_col == "pipeline_score":
        sort_col = "quality_score"  # no pipeline_score for generic types
    if sort_col == "_label":
        sort_col = label_expr

    # Legacy sort_dir override (only when using legacy sort_by)
    if sort_by and sort_dir:
        direction = "DESC" if sort_dir == "desc" else "ASC"

    count_params = list(params)
    count_row = db.fetch_one(
        f"SELECT COUNT(*) AS total FROM {meta['table']} {where}", count_params,
    )
    total = count_row["total"] if count_row else 0

    params.extend([limit_val, offset_val])
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
        "limit": limit_val,
        "offset": offset_val,
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
               el.link_type, el.confidence, el.provenance_source,
               COALESCE(vs.label, el.source_entity_id) AS source_label,
               COALESCE(vt.label, el.target_entity_id) AS target_label
        FROM entity_links el
        LEFT JOIN v_entity_labels vs ON vs.entity_id = el.source_entity_id AND vs.entity_type = el.source_entity_type
        LEFT JOIN v_entity_labels vt ON vt.entity_id = el.target_entity_id AND vt.entity_type = el.target_entity_type
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


@router.get("/graph-summary")
def graph_summary(db: Database = Depends(get_db)):
    """Knowledge graph connectivity summary — link types, entity coverage, density."""
    link_types = db.fetch_all(
        "SELECT link_type, COUNT(*) AS cnt FROM entity_links GROUP BY link_type ORDER BY cnt DESC"
    )

    # Entity linking completeness for drugs
    drug_stats = {}
    try:
        total = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM drugs WHERE record_status IS NULL OR record_status NOT IN ('excluded','merged')"
        )["cnt"]
        with_co = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM drugs WHERE company_id IS NOT NULL AND (record_status IS NULL OR record_status NOT IN ('excluded','merged'))"
        )["cnt"]
        with_mech = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM drugs WHERE mechanism_id IS NOT NULL AND (record_status IS NULL OR record_status NOT IN ('excluded','merged'))"
        )["cnt"]
        with_ta = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM drugs WHERE therapeutic_area_id IS NOT NULL AND (record_status IS NULL OR record_status NOT IN ('excluded','merged'))"
        )["cnt"]
        with_brand = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM drugs WHERE brand_name IS NOT NULL AND brand_name != '' AND LOWER(brand_name) != LOWER(generic_name) AND (record_status IS NULL OR record_status NOT IN ('excluded','merged'))"
        )["cnt"]
        drug_stats = {
            "total": total,
            "with_company": with_co,
            "with_mechanism": with_mech,
            "with_therapeutic_area": with_ta,
            "with_brand_name": with_brand,
        }
    except Exception:
        pass

    total_links = db.fetch_one("SELECT COUNT(*) AS cnt FROM entity_links")
    total_entities = db.fetch_one(
        "SELECT COUNT(*) AS cnt FROM v_entity_labels WHERE entity_type IN ('drug','company','trial','literature','mechanism','therapeutic_area')"
    )

    return {
        "link_types": [{"type": r["link_type"], "count": r["cnt"]} for r in link_types],
        "total_links": total_links["cnt"] if total_links else 0,
        "total_entities": total_entities["cnt"] if total_entities else 0,
        "drug_completeness": drug_stats,
    }


@router.get("/ta-coverage")
def ta_coverage(db: Database = Depends(get_db)):
    """Therapeutic area coverage — drug counts, trial counts, mechanism counts per TA."""
    rows = db.fetch_all(
        """
        SELECT ta.id, ta.name,
               (SELECT COUNT(*) FROM drugs d
                WHERE d.therapeutic_area_id = ta.id
                AND (d.record_status IS NULL OR d.record_status NOT IN ('excluded','merged'))) AS drug_count,
               (SELECT COUNT(*) FROM entity_links el
                WHERE el.target_entity_id = ta.id::text
                AND el.link_type = 'IN_THERAPEUTIC_AREA'
                AND el.source_entity_type = 'drug') AS linked_drug_count,
               (SELECT COUNT(*) FROM entity_links el
                WHERE el.target_entity_id = ta.id::text
                AND el.link_type = 'IN_THERAPEUTIC_AREA'
                AND el.source_entity_type = 'trial') AS trial_count
        FROM therapeutic_areas ta
        ORDER BY drug_count DESC, linked_drug_count DESC
        """
    )
    return {
        "therapeutic_areas": [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "drug_count": r["drug_count"],
                "linked_drug_count": r["linked_drug_count"],
                "trial_count": r["trial_count"],
            }
            for r in rows
        ]
    }


@router.get("/pipeline-status")
def pipeline_status(db: Database = Depends(get_db)):
    """Pipeline connector status — schedule, last run, next run."""
    from scheduler.config import CONNECTOR_SCHEDULES
    from connectors.base import SourceType

    result = []
    for st, sched in CONNECTOR_SCHEDULES.items():
        source_key = st.value
        cron = sched["cron"]

        # Determine schedule description
        if "day" in cron:
            schedule_desc = f"Monthly on day {cron['day']} at {cron.get('hour', 0):02d}:{cron.get('minute', 0):02d} UTC"
        elif "day_of_week" in cron:
            schedule_desc = f"Weekly ({cron['day_of_week']}) at {cron.get('hour', 0):02d}:{cron.get('minute', 0):02d} UTC"
        else:
            schedule_desc = f"Daily at {cron.get('hour', 0):02d}:{cron.get('minute', 0):02d} UTC"

        # Last run from source_coverage in health data
        last_run = None
        record_count = 0
        try:
            for table in ["drugs", "clinical_trials", "pubmed_articles", "companies", "market_events"]:
                row = db.fetch_one(
                    f"SELECT MAX(retrieved_at) AS latest, COUNT(*) AS cnt FROM {table} WHERE source_api = %s",
                    [source_key],
                )
                if row and row["latest"]:
                    ts = row["latest"].isoformat() if hasattr(row["latest"], "isoformat") else None
                    if ts and (last_run is None or ts > last_run):
                        last_run = ts
                    record_count += row["cnt"] or 0
        except Exception:
            pass

        days_since = None
        if last_run:
            try:
                from datetime import datetime as _dt, timezone as _tz
                latest_dt = _dt.fromisoformat(last_run.replace("Z", "+00:00"))
                days_since = (_dt.now(_tz.utc) - latest_dt).total_seconds() / 86400
            except Exception:
                pass

        result.append({
            "source_key": source_key,
            "label": sched["label"],
            "schedule": schedule_desc,
            "last_run": last_run,
            "days_since": round(days_since, 1) if days_since is not None else None,
            "records": record_count,
            "status": "fresh" if days_since is not None and days_since <= 2 else
                      "ok" if days_since is not None and days_since <= 7 else
                      "stale" if days_since is not None else "unknown",
        })

    return {"connectors": result}


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
