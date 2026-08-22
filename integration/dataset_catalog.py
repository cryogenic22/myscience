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
        # therapeutic_areas is shared with open_targets (disease terms); scope so
        # the two products don't each report the whole table.
        "source_api": "mesh_ontology",
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
        # shared with a handful of curated_sme rows; scope to the MeSH terms.
        "source_api": "mesh_ontology",
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
        # drugs is shared (pubchem/chembl/CT.gov also write it via resolution);
        # scope to Orange Book's own rows. NB drugs.source_api is last-writer-wins
        # (_store_drug UPDATE overwrites it non-COALESCE), so this counts rows most
        # recently touched by Orange Book — the best available per-source split.
        "source_api": "fda_orange_book",
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
        "source_api": "fda_orange_book",
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
        "source_api": "fda_orange_book",
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
        # clinical_trials is shared with EMA (EU CTIS trials); scope to CT.gov rows.
        "source_api": "clinical_trials_gov",
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
        "source_api": "clinical_trials_gov",
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
        "source_api": "clinical_trials_gov",
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
        # investigators is shared with PubMed (authors); scope to CT.gov's rows.
        # PubMed's contribution is its own product below (pubmed.investigators).
        "source_api": "clinical_trials_gov",
        "description": "Principal investigators and study contacts registered on ClinicalTrials.gov trials.",
        "license_name": "Public Domain (US Government)",
        "license_url": "https://clinicaltrials.gov/data-api/about-api#terms",
        "api_base_url": "https://clinicaltrials.gov/api/v2",
        "refresh_frequency": "daily",
    },
    {
        "dataset_name": "pubmed.investigators",
        "source_type": "pubmed",
        "entity_type": "investigator",
        "table_name": "investigators",
        # PubMed's share of the shared investigators table (publication authors).
        "source_api": "pubmed",
        "description": "Study investigators and authors extracted from PubMed publications (the PubMed share of the investigators table).",
        "license_name": "NLM Terms of Use",
        "license_url": "https://www.nlm.nih.gov/databases/download/terms_and_conditions.html",
        "api_base_url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
        "refresh_frequency": "weekly",
    },
    {
        "dataset_name": "fda_shortages.events",
        "source_type": "fda_shortages",
        "entity_type": "event",
        "table_name": "market_events",
        # market_events is shared with pharma_news (and SEC-8K event emitters);
        # scope to FDA-shortage rows so the news events aren't counted here too.
        "source_api": "fda_shortages",
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
        "source_api": "pubmed",
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
        # companies is multi-source: the entity resolver auto-creates a company
        # for every trial sponsor / news mention (stamped with the triggering
        # source_api), so the whole table (~1.5k) is NOT SEC EDGAR's. Scope to
        # the rows SEC EDGAR actually sourced; the auto-created sponsor companies
        # are derived rows with no dedicated dataset product (like the backfill
        # drugs) — still in the DB, just not attributed here.
        "source_api": "sec_edgar",
        "description": "SEC EDGAR company filings (10-K, 10-Q) for target pharma companies.",
        "license_name": "Public Domain (US Government)",
        "license_url": "https://www.sec.gov/privacy#dissemination",
        "api_base_url": "https://efts.sec.gov/LATEST",
        "refresh_frequency": "quarterly",
    },
]


# ─── Derived products for the sources not hand-authored above ──────────
#
# DATASET_DEFINITIONS above hand-lists only 6 of the 15 registered connectors
# (CONNECTOR_REGISTRY). The other 9 sources ingest real data every day but were
# invisible in the catalog. This table supplies the per-source metadata that is
# NOT derivable from the registries (license, url, human description, the entity
# table + its scoping source_api) so `build_dataset_definitions()` can emit a
# product for every registered source. Structural bits (refresh cadence) are
# derived from scheduler.config; the rest is authored reference data.
#
# `source_api` is the value physically stamped on the source's rows (verified
# against a 2026-07-06 prod probe of each shared table). It is REQUIRED whenever
# the table is written by more than one source, so `_refresh_entry` can scope
# `count(*)` and avoid double-counting. Two gotchas the probe caught:
#   - nadac lands in drug_pricing as source_api='cms_nadac' (NOT 'nadac'); the
#     registered NadacConnector→drugs path is the dead Socrata endpoint.
#   - open_targets ONTOLOGY_TERM rows land in therapeutic_areas (source_api=
#     'open_targets'), not the molecular_targets its FRESHNESS_SLA_DAYS entry
#     names (that table is 100% chembl) — so we catalog DB reality.
_DERIVED_SOURCE_META: dict[str, dict] = {
    "openfda_faers": {
        "dataset_name": "openfda_faers.adverse_events",
        "entity_type": "adverse_event",
        "table_name": "adverse_events",
        "source_api": "openfda_faers",
        "description": "FDA FAERS adverse-event reports (openFDA drug/event) for diabetes/obesity and cardiometabolic drugs — one record per safety report with the primary MedDRA reaction, outcome, severity, and patient demographics.",
        "license_name": "Public Domain (US Government)",
        "license_url": "https://open.fda.gov/license/",
        "api_base_url": "https://api.fda.gov/drug/event.json",
    },
    "openfda_labels": {
        "dataset_name": "openfda_labels.drug_labels",
        "entity_type": "drug_label",
        "table_name": "drug_labels",
        "source_api": "openfda_labels",
        "description": "FDA structured product labels (openFDA drug/label) — indications, contraindications, boxed/other warnings, dosing, and adverse reactions — for a curated set of diabetes/obesity and cardiovascular drugs, deduplicated by SPL set_id.",
        "license_name": "Public Domain (US Government)",
        "license_url": "https://open.fda.gov/license/",
        "api_base_url": "https://api.fda.gov/drug/label.json",
    },
    "pmc": {
        "dataset_name": "pmc.articles",
        "entity_type": "pmc_article",
        "table_name": "pmc_articles",
        "source_api": "pmc",
        "description": "Open-access full-text biomedical articles from PubMed Central for the platform's diabetes, obesity, and cardiometabolic target drugs, with protocol and systematic-review flags.",
        "license_name": "NLM Terms of Use (PMC Open Access Subset — per-article Creative Commons licenses)",
        "license_url": "https://www.ncbi.nlm.nih.gov/pmc/about/copyright/",
        "api_base_url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
    },
    "ema": {
        "dataset_name": "ema.trials",
        "entity_type": "trial",
        "table_name": "clinical_trials",
        "source_api": "ema",
        "description": "European Union clinical trials (EU CTIS) for diabetes/obesity target drugs, ingested into the shared clinical_trials table to counter the US-centric bias of the trial corpus.",
        "license_name": "EMA / EU CTIS — free reuse with attribution (EU Commission Decision 2011/833/EU)",
        "license_url": "https://www.ema.europa.eu/en/about-us/about-website/legal-notice",
        "api_base_url": "https://euclinicaltrials.eu/ctis-public-api/search",
    },
    "nadac": {
        "dataset_name": "nadac.drug_prices",
        "entity_type": "drug_pricing",
        "table_name": "drug_pricing",
        # NB: stored source_api is 'cms_nadac', not the SourceType.value 'nadac'.
        "source_api": "cms_nadac",
        "description": "CMS National Average Drug Acquisition Cost (NADAC) per-unit Medicaid drug acquisition prices from the weekly CMS snapshot, matched to known drugs by generic name.",
        "license_name": "Public Domain (US Government)",
        "license_url": "https://data.medicaid.gov/",
        "api_base_url": "https://data.medicaid.gov/resource/4j6z-xnwq.json",
    },
    "pharma_news": {
        "dataset_name": "pharma_news.events",
        "entity_type": "event",
        "table_name": "market_events",
        "source_api": "pharma_news",
        "description": "Pharma competitive-signal events — approvals, M&A, Phase 3 readouts, regulatory setbacks, and safety/supply signals — classified from FDA press-release and Google News RSS feeds and landed in the shared market_events timeline.",
        "license_name": "Mixed (FDA press releases: Public Domain; Google News headlines: publisher copyright / Google ToS — no open data license)",
        "license_url": "https://www.fda.gov/about-fda/about-website/website-policies",
        "api_base_url": "https://news.google.com/rss/search",
    },
    "chembl": {
        "dataset_name": "chembl.bioactivities",
        "entity_type": "bioactivity",
        "table_name": "bioactivities",
        "source_api": "chembl",
        "description": "EBI ChEMBL molecular bioactivity measurements (IC50/Ki/EC50/pChEMBL) for the diabetes/obesity drug set (GLP-1, SGLT2, DPP-4 agents), powering target-based binding-affinity analysis.",
        "license_name": "ChEMBL: CC BY-SA 3.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/3.0/",
        "api_base_url": "https://www.ebi.ac.uk/chembl/api/data",
    },
    "pubchem": {
        "dataset_name": "pubchem.compounds",
        "entity_type": "drug",
        "table_name": "drugs",
        "source_api": "pubchem",
        "description": "NCBI PubChem chemical-identity and molecular-property enrichment (CID, canonical SMILES, InChI, molecular formula/weight, XLogP, TPSA, H-bond counts) for the target-drug list, adding a structure-based identity layer onto the shared drugs table.",
        "license_name": "Public Domain (US Government - NCBI/NLM)",
        "license_url": "https://www.ncbi.nlm.nih.gov/home/about/policies/",
        "api_base_url": "https://pubchem.ncbi.nlm.nih.gov/rest/pug",
    },
    "open_targets": {
        "dataset_name": "open_targets.disease_associations",
        "entity_type": "ontology_term",
        "table_name": "therapeutic_areas",
        "source_api": "open_targets",
        "description": "Open Targets Platform target–disease genetic-association terms for the diabetes/obesity portfolio, landed as disease ontology terms in the shared therapeutic_areas table.",
        "license_name": "Open Targets: CC0 1.0",
        "license_url": "https://platform-docs.opentargets.org/licence",
        "api_base_url": "https://api.platform.opentargets.org/api/v4/graphql",
    },
}


def _cadence_word(source_type_value: str) -> str:
    """Coarse refresh cadence (daily/weekly/monthly) derived from the connector's
    cron in scheduler.config. Falls back to 'weekly' when a source has no cron
    entry (e.g. NADAC, which loads via the weekly post-run pricing task)."""
    try:
        from connectors.base import SourceType
        from scheduler.config import CONNECTOR_SCHEDULES

        entry = CONNECTOR_SCHEDULES.get(SourceType(source_type_value))
    except Exception:
        return "weekly"
    if not entry:
        return "weekly"
    cron = entry.get("cron", {})
    if "day" in cron:
        return "monthly"
    if "day_of_week" in cron:
        return "weekly"
    return "daily"


def build_dataset_definitions() -> list[dict]:
    """The complete per-source catalog: the hand-authored fine-grained entries
    (DATASET_DEFINITIONS) UNION one derived entry for every registered connector
    (CONNECTOR_REGISTRY) not already covered by an authored entry.

    Before this existed the catalog hand-listed 6 of 15 sources; the other 9 were
    invisible. Derived entries carry a `source_api` scope (see _DERIVED_SOURCE_META)
    so shared-table row counts don't double-count. This is the canonical set the
    catalog refresh and the connectors UI read; `DATASET_DEFINITIONS` remains the
    authored seed.
    """
    from connectors import CONNECTOR_REGISTRY

    defs = [dict(d) for d in DATASET_DEFINITIONS]
    covered = {d["source_type"] for d in defs}
    for source_type in CONNECTOR_REGISTRY:
        sid = source_type.value
        if sid in covered:
            continue
        meta = _DERIVED_SOURCE_META.get(sid)
        if not meta:
            # Fail loud (not silent): a registered source with no catalog metadata
            # is a gap to close, not a row to drop quietly.
            logger.warning(
                "build_dataset_definitions: registered source '%s' has no catalog "
                "metadata — omitted from the dataset catalog", sid,
            )
            continue
        entry = dict(meta)
        entry["source_type"] = sid
        entry.setdefault("refresh_frequency", _cadence_word(sid))
        defs.append(entry)
    return defs


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
    "adverse_events": [
        ("id", "sc:Text", "Unique report identifier (UUID)"),
        ("report_id", "sc:Text", "FAERS safety-report case number"),
        ("drug_id", "sc:Text", "Linked drug UUID"),
        ("reaction_meddra_pt", "sc:Text", "Primary MedDRA preferred-term reaction"),
        ("outcome", "sc:Text", "Reported outcome (hospitalization, death, etc.)"),
        ("severity", "sc:Text", "Report severity classification"),
        ("report_date", "sc:Date", "Date the report was received"),
    ],
    "drug_labels": [
        ("id", "sc:Text", "Unique label identifier (UUID)"),
        ("drug_id", "sc:Text", "Linked drug UUID"),
        ("set_id", "sc:Text", "SPL set identifier (dedup key)"),
        ("indications", "sc:Text", "Indications and usage section"),
        ("boxed_warning", "sc:Text", "Boxed warning text"),
        ("effective_date", "sc:Date", "Label effective date"),
        ("label_embedding", "cr:Vector", "1536-dim label embedding"),
    ],
    "pmc_articles": [
        ("id", "sc:Text", "Unique article identifier (UUID)"),
        ("pmc_id", "sc:Text", "PubMed Central ID"),
        ("pmid", "sc:Text", "PubMed ID"),
        ("title", "sc:Text", "Article title"),
        ("full_text", "sc:Text", "Open-access full-text body"),
        ("is_systematic_review", "sc:Boolean", "Systematic-review/meta-analysis flag"),
        ("full_text_embedding", "cr:Vector", "1536-dim full-text embedding"),
    ],
    "bioactivities": [
        ("id", "sc:Text", "Unique bioactivity identifier (UUID)"),
        ("drug_id", "sc:Text", "Linked drug UUID"),
        ("target_id", "sc:Text", "Linked molecular target UUID"),
        ("activity_type", "sc:Text", "Assay endpoint (IC50, Ki, EC50, ...)"),
        ("activity_value", "sc:Float", "Measured activity value"),
        ("activity_units", "sc:Text", "Activity units (nM, etc.)"),
        ("pchembl_value", "sc:Float", "Normalized pChEMBL potency"),
    ],
    "drug_pricing": [
        ("id", "sc:Text", "Unique pricing record identifier (UUID)"),
        ("drug_id", "sc:Text", "Linked drug UUID"),
        ("ndc_code", "sc:Text", "National Drug Code"),
        ("price_type", "sc:Text", "Price basis (NADAC, ASP, ...)"),
        ("unit_price", "sc:Float", "Per-unit acquisition cost"),
        ("currency", "sc:Text", "Currency code"),
        ("effective_date", "sc:Date", "Price effective date"),
    ],
    "therapeutic_areas": [
        ("id", "sc:Text", "Unique term identifier (UUID)"),
        ("name", "sc:Text", "Therapeutic-area / disease term name"),
        ("mesh_id", "sc:Text", "MeSH descriptor identifier"),
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
        definitions = build_dataset_definitions()
        for defn in definitions:
            try:
                self._refresh_entry(defn)
            except Exception as e:
                logger.error("Failed to refresh catalog entry '%s': %s", defn["dataset_name"], e)

        logger.info("Dataset catalog refreshed (%d entries)", len(definitions))

    def _refresh_entry(self, defn: dict):
        """Refresh a single catalog entry.

        When the definition declares a ``source_api`` (its table is shared by
        more than one source), every stat is scoped ``WHERE source_api = %s`` so
        two products on the same table report their own rows instead of each
        claiming the whole table — the silent double-count the conservation
        gates exist to prevent.
        """
        table = defn["table_name"]
        source_api = defn.get("source_api")
        scoped = bool(source_api) and self._table_has_column(table, "source_api")
        where, params = (" WHERE source_api = %s", [source_api]) if scoped else ("", [])

        # Row count (scoped to this source's rows when a source_api is declared)
        row_count = self.db.fetch_one(f"SELECT count(*) as c FROM {table}{where}", params)["c"]

        # Quality stats
        quality_row = self.db.fetch_one(
            f"SELECT avg(quality_score) as avg_q, "
            f"count(CASE WHEN quality_score IS NOT NULL THEN 1 END) as assessed "
            f"FROM {table}{where}", params
        ) if self._table_has_column(table, "quality_score") else {"avg_q": None, "assessed": 0}

        avg_quality = round(quality_row["avg_q"], 3) if quality_row.get("avg_q") else None

        scope = source_api if scoped else None

        # Completeness (% non-NULL for key columns)
        completeness = self._compute_completeness(table, source_api=scope)

        # Freshness (avg days since last verified)
        freshness = self._compute_freshness(table, source_api=scope)

        # Source imbalance stats
        imbalance = self._compute_imbalance(table, defn["entity_type"], source_api=scope)

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
        n_sources = len({d["source_type"] for d in build_dataset_definitions()})

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
                    f"Automated ETL pipelines fetching from {n_sources} registered public "
                    "data sources: MeSH (NLM), FDA Orange Book & openFDA (labels, FAERS, "
                    "shortages), ClinicalTrials.gov, EMA EU-CTIS, PubMed/MEDLINE & PubMed "
                    "Central, SEC EDGAR, ChEMBL, PubChem, Open Targets, and CMS NADAC "
                    "pricing, plus classified pharma news events. No human subjects data."
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

    def _compute_completeness(self, table: str, source_api: Optional[str] = None) -> float:
        """Compute overall non-NULL percentage for key columns, scoped to one
        source's rows when ``source_api`` is given."""
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

        scoped = bool(source_api) and self._table_has_column(table, "source_api")
        where = " WHERE source_api = %s" if scoped else ""
        params = [source_api] if scoped else []

        total_row = self.db.fetch_one(f"SELECT count(*) as c FROM {table}{where}", params)
        total = total_row["c"]
        if total == 0:
            return 100.0

        non_null_sum = 0
        col_count = len(cols)
        for c in cols:
            col_name = c["column_name"]
            col_where = f" WHERE {col_name} IS NOT NULL" + (" AND source_api = %s" if scoped else "")
            nn = self.db.fetch_one(
                f"SELECT count(*) as c FROM {table}{col_where}", params
            )
            non_null_sum += nn["c"]

        pct = (non_null_sum / (total * col_count)) * 100 if col_count > 0 else 100.0
        return round(pct, 1)

    def _compute_freshness(self, table: str, source_api: Optional[str] = None) -> Optional[float]:
        """Average age in days since last verification, scoped to one source's
        rows when ``source_api`` is given."""
        scoped = bool(source_api) and self._table_has_column(table, "source_api")
        src_and = " AND source_api = %s" if scoped else ""
        params = [source_api] if scoped else []

        if not self._table_has_column(table, "last_verified_at"):
            # Fall back to retrieved_at
            if not self._table_has_column(table, "retrieved_at"):
                return None
            row = self.db.fetch_one(
                f"SELECT avg(EXTRACT(EPOCH FROM (NOW() - retrieved_at))/86400) as avg_days "
                f"FROM {table} WHERE retrieved_at IS NOT NULL{src_and}",
                params,
            )
        else:
            row = self.db.fetch_one(
                f"""
                SELECT avg(EXTRACT(EPOCH FROM (NOW() - COALESCE(last_verified_at, retrieved_at)))/86400) as avg_days
                FROM {table}
                WHERE COALESCE(last_verified_at, retrieved_at) IS NOT NULL{src_and}
                """,
                params,
            )
        return round(row["avg_days"], 1) if row and row.get("avg_days") else None

    def _compute_imbalance(self, table: str, entity_type: str, source_api: Optional[str] = None) -> dict:
        """Compute source/class distribution stats for bias reporting, scoped to
        one source's rows when ``source_api`` is given."""
        imbalance = {}

        scoped = bool(source_api) and self._table_has_column(table, "source_api")
        where = " WHERE source_api = %s" if scoped else ""
        params = [source_api] if scoped else []

        # Source distribution (if source_api column exists)
        if self._table_has_column(table, "source_api"):
            rows = self.db.fetch_all(
                f"SELECT source_api, count(*) as c FROM {table}{where} GROUP BY source_api ORDER BY c DESC",
                params,
            )
            imbalance["by_source"] = {r["source_api"]: r["c"] for r in rows}

        # Entity-specific distributions
        if entity_type == "trial" and self._table_has_column(table, "phase"):
            rows = self.db.fetch_all(
                f"SELECT phase, count(*) as c FROM {table}{where} GROUP BY phase ORDER BY c DESC",
                params,
            )
            imbalance["by_phase"] = {(r["phase"] or "N/A"): r["c"] for r in rows}

        if entity_type == "trial" and self._table_has_column(table, "status"):
            rows = self.db.fetch_all(
                f"SELECT status, count(*) as c FROM {table}{where} GROUP BY status ORDER BY c DESC LIMIT 10",
                params,
            )
            imbalance["by_status"] = {(r["status"] or "N/A"): r["c"] for r in rows}

        if entity_type == "trial_location" and self._table_has_column(table, "country"):
            rows = self.db.fetch_all(
                f"SELECT country, count(*) as c FROM {table}{where} GROUP BY country ORDER BY c DESC LIMIT 15",
                params,
            )
            imbalance["by_country"] = {(r["country"] or "Unknown"): r["c"] for r in rows}

        if entity_type == "drug" and self._table_has_column(table, "source_authority"):
            rows = self.db.fetch_all(
                f"SELECT source_authority, count(*) as c FROM {table}{where} GROUP BY source_authority ORDER BY c DESC",
                params,
            )
            imbalance["by_authority"] = {(r["source_authority"] or "NULL"): r["c"] for r in rows}

        return imbalance
