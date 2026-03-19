"""
Dataset catalog and Croissant metadata generator for Market-Zero.

Implements ODI AI-readiness framework requirements:
  - 2a) Machine-readable metadata format (Croissant JSON-LD)
  - 2b) Dataset served with attached metadata
  - 2c) Technical specifications (modality, dimensions, bias, stats)
  - 2d) Supply chain information (collection, preprocessing)
  - 2e) Legal and sociotechnical information (licenses)
  - 3c) Version control infrastructure (change log integration)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


# ─── Dataset registry (static metadata per source) ────────

DATASET_DEFINITIONS = [
    {
        "dataset_name": "mesh_ontology.therapeutic_areas",
        "source_type": "mesh_ontology",
        "entity_type": "ontology_term",
        "table_name": "therapeutic_areas",
        "description": "MeSH ontology terms for therapeutic areas (Diabetes, Obesity).",
        "license_name": "Public Domain",
        "license_url": "https://www.nlm.nih.gov/databases/download/terms_and_conditions.html",
        "api_base_url": "https://id.nlm.nih.gov/mesh",
        "refresh_frequency": "monthly",
    },
    {
        "dataset_name": "mesh_ontology.mechanisms_of_action",
        "source_type": "mesh_ontology",
        "entity_type": "ontology_term",
        "table_name": "mechanisms_of_action",
        "description": "MeSH ontology terms for drug mechanisms of action (DPP-4, GLP-1, SGLT2, etc.).",
        "license_name": "Public Domain",
        "license_url": "https://www.nlm.nih.gov/databases/download/terms_and_conditions.html",
        "api_base_url": "https://id.nlm.nih.gov/mesh",
        "refresh_frequency": "monthly",
    },
    {
        "dataset_name": "fda_orange_book.drugs",
        "source_type": "fda_orange_book",
        "entity_type": "drug",
        "table_name": "drugs",
        "description": "FDA-approved drugs from the Orange Book. Includes NDA numbers, approval dates, dosage forms. Filtered to diabetes/obesity therapeutic areas.",
        "license_name": "Public Domain (US Government)",
        "license_url": "https://open.fda.gov/license/",
        "api_base_url": "https://api.fda.gov/drug",
        "refresh_frequency": "weekly",
    },
    {
        "dataset_name": "fda_orange_book.patents",
        "source_type": "fda_orange_book",
        "entity_type": "patent",
        "table_name": "patents",
        "description": "Patent protections for FDA-approved drugs from the Orange Book.",
        "license_name": "Public Domain (US Government)",
        "license_url": "https://open.fda.gov/license/",
        "api_base_url": "https://api.fda.gov/drug",
        "refresh_frequency": "weekly",
    },
    {
        "dataset_name": "fda_orange_book.regulatory_milestones",
        "source_type": "fda_orange_book",
        "entity_type": "regulatory_milestone",
        "table_name": "regulatory_milestones",
        "description": "FDA submission and approval history for drugs (NDA, ANDA, BLA filings).",
        "license_name": "Public Domain (US Government)",
        "license_url": "https://open.fda.gov/license/",
        "api_base_url": "https://api.fda.gov/drug",
        "refresh_frequency": "weekly",
    },
    {
        "dataset_name": "clinical_trials_gov.trials",
        "source_type": "clinical_trials_gov",
        "entity_type": "trial",
        "table_name": "clinical_trials",
        "description": "Clinical trial protocols from ClinicalTrials.gov for diabetes/obesity conditions. Includes phase, status, enrollment, outcomes, and sites.",
        "license_name": "Public Domain (US Government)",
        "license_url": "https://clinicaltrials.gov/data-api/about-api#terms",
        "api_base_url": "https://clinicaltrials.gov/api/v2",
        "refresh_frequency": "daily",
    },
    {
        "dataset_name": "clinical_trials_gov.outcomes",
        "source_type": "clinical_trials_gov",
        "entity_type": "trial_outcome",
        "table_name": "trial_outcomes",
        "description": "Primary, secondary, and other outcome measures from clinical trials.",
        "license_name": "Public Domain (US Government)",
        "license_url": "https://clinicaltrials.gov/data-api/about-api#terms",
        "api_base_url": "https://clinicaltrials.gov/api/v2",
        "refresh_frequency": "daily",
    },
    {
        "dataset_name": "clinical_trials_gov.locations",
        "source_type": "clinical_trials_gov",
        "entity_type": "trial_location",
        "table_name": "trial_locations",
        "description": "Clinical trial site locations worldwide.",
        "license_name": "Public Domain (US Government)",
        "license_url": "https://clinicaltrials.gov/data-api/about-api#terms",
        "api_base_url": "https://clinicaltrials.gov/api/v2",
        "refresh_frequency": "daily",
    },
    {
        "dataset_name": "clinical_trials_gov.investigators",
        "source_type": "clinical_trials_gov",
        "entity_type": "investigator",
        "table_name": "investigators",
        "description": "Principal investigators and study contacts from clinical trials and PubMed publications.",
        "license_name": "Public Domain (US Government)",
        "license_url": "https://clinicaltrials.gov/data-api/about-api#terms",
        "api_base_url": "https://clinicaltrials.gov/api/v2",
        "refresh_frequency": "daily",
    },
    {
        "dataset_name": "fda_shortages.events",
        "source_type": "fda_shortages",
        "entity_type": "event",
        "table_name": "market_events",
        "description": "FDA drug shortage and enforcement events impacting diabetes/obesity drugs.",
        "license_name": "Public Domain (US Government)",
        "license_url": "https://open.fda.gov/license/",
        "api_base_url": "https://api.fda.gov/drug",
        "refresh_frequency": "weekly",
    },
    {
        "dataset_name": "pubmed.articles",
        "source_type": "pubmed",
        "entity_type": "literature",
        "table_name": "pubmed_articles",
        "description": "Biomedical literature from PubMed/MEDLINE related to diabetes and obesity drug research.",
        "license_name": "NLM Terms of Use",
        "license_url": "https://www.nlm.nih.gov/databases/download/terms_and_conditions.html",
        "api_base_url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
        "refresh_frequency": "weekly",
    },
    {
        "dataset_name": "sec_edgar.filings",
        "source_type": "sec_edgar",
        "entity_type": "company",
        "table_name": "companies",
        "description": "SEC EDGAR company filings (10-K, 10-Q) for target pharma companies.",
        "license_name": "Public Domain (US Government)",
        "license_url": "https://www.sec.gov/privacy#dissemination",
        "api_base_url": "https://efts.sec.gov/LATEST",
        "refresh_frequency": "quarterly",
    },
]


# ─── Table schema metadata for Croissant fields ────

TABLE_FIELD_SCHEMAS = {
    "drugs": [
        ("id", "sc:Text", "Unique drug identifier (UUID)"),
        ("generic_name", "sc:Text", "International nonproprietary name"),
        ("brand_name", "sc:Text", "Marketed brand name"),
        ("nda_number", "sc:Text", "FDA New Drug Application number"),
        ("approval_date", "sc:Date", "FDA approval date"),
        ("dosage_form", "sc:Text", "Pharmaceutical dosage form"),
        ("route", "sc:Text", "Route of administration"),
        ("molecule_embedding", "cr:Vector", "1536-dim text-embedding-3-small vector"),
        ("quality_score", "sc:Float", "Composite quality score 0.0-1.0"),
    ],
    "clinical_trials": [
        ("id", "sc:Text", "ClinicalTrials.gov NCT ID"),
        ("drug_id", "sc:Text", "Linked drug UUID"),
        ("status", "sc:Text", "Trial status (Recruiting, Completed, etc.)"),
        ("phase", "sc:Text", "Trial phase (Phase 1-4)"),
        ("sponsor_name", "sc:Text", "Lead sponsor organization"),
        ("conditions", "sc:ItemList", "Target medical conditions"),
        ("interventions", "sc:ItemList", "Drug/biological interventions"),
        ("enrollment_target", "sc:Integer", "Target enrollment count"),
        ("protocol_embedding", "cr:Vector", "1536-dim protocol embedding"),
    ],
    "pubmed_articles": [
        ("id", "sc:Text", "Unique article identifier (UUID)"),
        ("pmid", "sc:Text", "PubMed ID"),
        ("title", "sc:Text", "Article title"),
        ("abstract", "sc:Text", "Article abstract"),
        ("journal", "sc:Text", "Journal name"),
        ("publication_date", "sc:Date", "Publication date"),
        ("abstract_embedding", "cr:Vector", "1536-dim abstract embedding"),
    ],
    "companies": [
        ("id", "sc:Text", "Unique company identifier (UUID)"),
        ("name", "sc:Text", "Company legal name"),
        ("cik", "sc:Text", "SEC CIK number"),
        ("ticker", "sc:Text", "Stock ticker symbol"),
        ("country", "sc:Text", "Country of incorporation"),
    ],
    "market_events": [
        ("id", "sc:Text", "Unique event identifier (UUID)"),
        ("drug_id", "sc:Text", "Linked drug UUID"),
        ("event_type", "sc:Text", "Event type (shortage, enforcement, etc.)"),
        ("event_date", "sc:Date", "Event date"),
        ("description", "sc:Text", "Event description"),
    ],
}


class DatasetCatalog:
    """
    Generates and maintains dataset catalog with Croissant JSON-LD metadata.

    Usage:
        catalog = DatasetCatalog(db, config)
        catalog.refresh_all()
        croissant = catalog.get_croissant("clinical_trials_gov.trials")
    """

    def __init__(self, db, config):
        self.db = db
        self.config = config

    def refresh_all(self):
        """Refresh all catalog entries with current stats and metadata."""
        for defn in DATASET_DEFINITIONS:
            try:
                self._refresh_entry(defn)
            except Exception as e:
                logger.error("Failed to refresh catalog entry '%s': %s", defn["dataset_name"], e)

        logger.info("Dataset catalog refreshed (%d entries)", len(DATASET_DEFINITIONS))

    def _refresh_entry(self, defn: dict):
        """Refresh a single catalog entry."""
        table = defn["table_name"]

        # Row count
        row_count = self.db.fetch_one(f"SELECT count(*) as c FROM {table}")["c"]

        # Quality stats
        quality_row = self.db.fetch_one(
            f"SELECT avg(quality_score) as avg_q, "
            f"count(CASE WHEN quality_score IS NOT NULL THEN 1 END) as assessed "
            f"FROM {table}"
        ) if self._table_has_column(table, "quality_score") else {"avg_q": None, "assessed": 0}

        avg_quality = round(quality_row["avg_q"], 3) if quality_row.get("avg_q") else None

        # Completeness (% non-NULL for key columns)
        completeness = self._compute_completeness(table)

        # Freshness (avg days since last verified)
        freshness = self._compute_freshness(table)

        # Source imbalance stats
        imbalance = self._compute_imbalance(table, defn["entity_type"])

        # Last ETL run for this source
        last_run = self.db.fetch_one(
            "SELECT completed_at FROM etl_runs WHERE source_name = %s AND status IN ('SUCCESS','PARTIAL') ORDER BY completed_at DESC LIMIT 1",
            [defn["source_type"]],
        )
        last_refreshed = last_run["completed_at"] if last_run else None

        # Generate Croissant JSON-LD
        croissant = self._generate_croissant(defn, row_count, completeness, imbalance)

        # Upsert catalog entry
        self.db.execute(
            """
            INSERT INTO dataset_catalog
                (dataset_name, source_type, entity_type, description, table_name,
                 row_count, last_refreshed_at, refresh_frequency,
                 license_name, license_url, api_base_url,
                 quality_score_avg, completeness_pct, freshness_days,
                 source_imbalance, croissant_metadata, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, NOW())
            ON CONFLICT (dataset_name) DO UPDATE SET
                row_count = EXCLUDED.row_count,
                last_refreshed_at = EXCLUDED.last_refreshed_at,
                quality_score_avg = EXCLUDED.quality_score_avg,
                completeness_pct = EXCLUDED.completeness_pct,
                freshness_days = EXCLUDED.freshness_days,
                source_imbalance = EXCLUDED.source_imbalance,
                croissant_metadata = EXCLUDED.croissant_metadata,
                updated_at = NOW()
            """,
            [
                defn["dataset_name"], defn["source_type"], defn["entity_type"],
                defn["description"], table,
                row_count, last_refreshed, defn.get("refresh_frequency"),
                defn.get("license_name"), defn.get("license_url"), defn.get("api_base_url"),
                avg_quality, completeness, freshness,
                json.dumps(imbalance), json.dumps(croissant),
            ],
        )

    def get_croissant(self, dataset_name: str) -> Optional[dict]:
        """Get Croissant JSON-LD metadata for a dataset."""
        row = self.db.fetch_one(
            "SELECT croissant_metadata FROM dataset_catalog WHERE dataset_name = %s",
            [dataset_name],
        )
        if row and row["croissant_metadata"]:
            meta = row["croissant_metadata"]
            return meta if isinstance(meta, dict) else json.loads(meta)
        return None

    def get_full_catalog(self) -> list[dict]:
        """Get all catalog entries."""
        rows = self.db.fetch_all(
            "SELECT * FROM dataset_catalog ORDER BY dataset_name"
        )
        return [dict(r) for r in rows]

    def export_croissant_bundle(self) -> dict:
        """
        Export complete Croissant metadata for the entire Market-Zero knowledge layer.
        This is the top-level dataset descriptor that references all sub-datasets.
        """
        sub_datasets = self.db.fetch_all(
            "SELECT dataset_name, row_count, croissant_metadata FROM dataset_catalog ORDER BY dataset_name"
        )

        total_rows = sum(r["row_count"] or 0 for r in sub_datasets)

        return {
            "@context": {
                "@vocab": "https://schema.org/",
                "sc": "https://schema.org/",
                "cr": "http://mlcommons.org/croissant/",
            },
            "@type": "sc:Dataset",
            "name": "Market-Zero Pharma Knowledge Layer",
            "description": (
                "Integrated pharmaceutical intelligence dataset combining clinical trials, "
                "FDA regulatory data, patent filings, biomedical literature, SEC company filings, "
                "and drug shortage events. Focused on diabetes and obesity therapeutic areas."
            ),
            "dateModified": datetime.utcnow().strftime("%Y-%m-%d"),
            "version": "1.0.0",
            "license": "https://creativecommons.org/licenses/by-nc/4.0/",
            "creator": {"@type": "Organization", "name": "Market-Zero"},
            "keywords": [
                "pharmaceutical", "clinical trials", "FDA", "diabetes", "obesity",
                "drug development", "patent analytics", "biomedical literature",
            ],
            "measurementTechnique": "Automated ETL pipeline with multi-source entity resolution",
            "totalSize": f"{total_rows} records across {len(sub_datasets)} datasets",
            "cr:rai": {
                "dataCollection": (
                    "Automated ETL pipelines fetching from 6 public APIs: "
                    "MeSH (NLM), FDA Orange Book, ClinicalTrials.gov, FDA Drug Shortages, "
                    "PubMed/MEDLINE, and SEC EDGAR. No human subjects data."
                ),
                "personalSensitiveInformation": (
                    "None. All data is from public government APIs and registries. "
                    "Investigator names are from public trial registrations and publications."
                ),
                "knownBias": (
                    "1) Limited to diabetes/obesity therapeutic areas. "
                    "2) English-language bias in PubMed literature. "
                    "3) US-centric regulatory data (FDA). "
                    "4) Company coverage limited to 5 target CIKs (Novo Nordisk, Eli Lilly, Sanofi, AstraZeneca, Pfizer). "
                    "5) Trial data skewed toward later phases with published results."
                ),
                "preprocessingSteps": [
                    "1. Raw API fetch with provenance hashing (SHA-256)",
                    "2. Field normalization to canonical schema",
                    "3. 6-strategy entity resolution cascade (exact ID, alias, fuzzy, embedding, LLM, auto-create)",
                    "4. Vector embedding (OpenAI text-embedding-3-small, 1536 dims)",
                    "5. Upsert with content hash change detection",
                    "6. Cross-source entity linking",
                    "7. Quality scoring (completeness, freshness, consistency, cross-source, embedding coverage)",
                ],
            },
            "hasPart": [
                {"@type": "sc:Dataset", "name": r["dataset_name"], "size": r["row_count"]}
                for r in sub_datasets
            ],
        }

    # ─── Internal helpers ─────────────────────────

    def _generate_croissant(self, defn: dict, row_count: int, completeness: float, imbalance: dict) -> dict:
        """Generate Croissant JSON-LD for a single dataset."""
        table = defn["table_name"]
        fields_schema = TABLE_FIELD_SCHEMAS.get(table, [])

        record_fields = [
            {
                "@type": "cr:Field",
                "name": name,
                "dataType": dtype,
                "description": desc,
            }
            for name, dtype, desc in fields_schema
        ]

        return {
            "@context": {
                "@vocab": "https://schema.org/",
                "sc": "https://schema.org/",
                "cr": "http://mlcommons.org/croissant/",
            },
            "@type": "sc:Dataset",
            "name": defn["dataset_name"],
            "description": defn["description"],
            "license": defn.get("license_url", ""),
            "url": defn.get("api_base_url", ""),
            "dateModified": datetime.utcnow().strftime("%Y-%m-%d"),
            "size": f"{row_count} records",
            "cr:recordSet": [
                {
                    "@type": "cr:RecordSet",
                    "name": table,
                    "numRecords": row_count,
                    "field": record_fields,
                }
            ] if record_fields else [],
            "distribution": [
                {
                    "@type": "sc:DataDownload",
                    "encodingFormat": "application/sql",
                    "contentUrl": f"postgresql://localhost:5488/market_zero#{table}",
                }
            ],
            "cr:rai": {
                "dataCollection": f"Automated ETL from {defn.get('api_base_url', 'N/A')}",
                "personalSensitiveInformation": "None - public data only",
                "completeness": f"{completeness}%",
                "knownBias": imbalance if imbalance else "Not assessed",
            },
            "measurementTechnique": "API fetch with entity resolution and quality scoring",
        }

    def _table_has_column(self, table: str, column: str) -> bool:
        row = self.db.fetch_one(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
            """,
            [table, column],
        )
        return row is not None

    def _compute_completeness(self, table: str) -> float:
        """Compute overall non-NULL percentage for key columns."""
        cols = self.db.fetch_all(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = %s AND data_type NOT IN ('uuid', 'timestamp without time zone', 'timestamp with time zone')
            AND column_name NOT LIKE '%%embedding%%'
            AND column_name NOT IN ('created_at', 'updated_at', 'retrieved_at', 'content_hash', 'last_verified_at', 'record_status', 'quality_score')
            """,
            [table],
        )
        if not cols:
            return 100.0

        total_row = self.db.fetch_one(f"SELECT count(*) as c FROM {table}")
        total = total_row["c"]
        if total == 0:
            return 100.0

        non_null_sum = 0
        col_count = len(cols)
        for c in cols:
            col_name = c["column_name"]
            nn = self.db.fetch_one(
                f"SELECT count(*) as c FROM {table} WHERE {col_name} IS NOT NULL"
            )
            non_null_sum += nn["c"]

        pct = (non_null_sum / (total * col_count)) * 100 if col_count > 0 else 100.0
        return round(pct, 1)

    def _compute_freshness(self, table: str) -> Optional[float]:
        """Average age in days since last verification."""
        if not self._table_has_column(table, "last_verified_at"):
            # Fall back to retrieved_at
            if not self._table_has_column(table, "retrieved_at"):
                return None
            row = self.db.fetch_one(
                f"SELECT avg(EXTRACT(EPOCH FROM (NOW() - retrieved_at))/86400) as avg_days FROM {table} WHERE retrieved_at IS NOT NULL"
            )
        else:
            row = self.db.fetch_one(
                f"""
                SELECT avg(EXTRACT(EPOCH FROM (NOW() - COALESCE(last_verified_at, retrieved_at)))/86400) as avg_days
                FROM {table}
                WHERE COALESCE(last_verified_at, retrieved_at) IS NOT NULL
                """
            )
        return round(row["avg_days"], 1) if row and row.get("avg_days") else None

    def _compute_imbalance(self, table: str, entity_type: str) -> dict:
        """Compute source/class distribution stats for bias reporting."""
        imbalance = {}

        # Source distribution (if source_api column exists)
        if self._table_has_column(table, "source_api"):
            rows = self.db.fetch_all(
                f"SELECT source_api, count(*) as c FROM {table} GROUP BY source_api ORDER BY c DESC"
            )
            imbalance["by_source"] = {r["source_api"]: r["c"] for r in rows}

        # Entity-specific distributions
        if entity_type == "trial" and self._table_has_column(table, "phase"):
            rows = self.db.fetch_all(
                f"SELECT phase, count(*) as c FROM {table} GROUP BY phase ORDER BY c DESC"
            )
            imbalance["by_phase"] = {(r["phase"] or "N/A"): r["c"] for r in rows}

        if entity_type == "trial" and self._table_has_column(table, "status"):
            rows = self.db.fetch_all(
                f"SELECT status, count(*) as c FROM {table} GROUP BY status ORDER BY c DESC LIMIT 10"
            )
            imbalance["by_status"] = {(r["status"] or "N/A"): r["c"] for r in rows}

        if entity_type == "trial_location" and self._table_has_column(table, "country"):
            rows = self.db.fetch_all(
                f"SELECT country, count(*) as c FROM {table} GROUP BY country ORDER BY c DESC LIMIT 15"
            )
            imbalance["by_country"] = {(r["country"] or "Unknown"): r["c"] for r in rows}

        if entity_type == "drug" and self._table_has_column(table, "source_authority"):
            rows = self.db.fetch_all(
                f"SELECT source_authority, count(*) as c FROM {table} GROUP BY source_authority ORDER BY c DESC"
            )
            imbalance["by_authority"] = {(r["source_authority"] or "NULL"): r["c"] for r in rows}

        return imbalance
