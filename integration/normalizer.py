"""
Step 1: Normalize source-specific field names to the unified schema.

Each source has a field mapping config (dict, not code). Adding a new
source's normalization = adding one dict entry.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from connectors.base import RawRecord, RecordType, SourceType

logger = logging.getLogger(__name__)

# Canonical source names — maps variant spellings to the authoritative form.
# Every record passing through normalize() gets its source fields canonicalized.
SOURCE_CANONICAL: dict[str, str] = {
    "clinicaltrials_gov": "clinical_trials_gov",
    "clinicaltrials": "clinical_trials_gov",
    "ct_gov": "clinical_trials_gov",
    "orange_book": "fda_orange_book",
    "orangebook": "fda_orange_book",
    "fda_drugsfda": "fda_orange_book",
    "fda_shortage": "fda_shortages",
    "edgar": "sec_edgar",
    "pubmed_central": "pmc",
}

# The set of allowed canonical source names (for validation)
CANONICAL_SOURCES = {
    "clinical_trials_gov",
    "fda_orange_book",
    "fda_shortages",
    "sec_edgar",
    "pubmed",
    "mesh_ontology",
    "openfda_faers",
    "openfda_labels",
    "pmc",
    "user_document",
    "user_url",
    "backfill",
}


def _canonicalize_source(value: str | None) -> str | None:
    """Map a source name to its canonical form, or return as-is if already canonical."""
    if value is None:
        return None
    normalized = value.strip().lower()
    return SOURCE_CANONICAL.get(normalized, normalized)


@dataclass
class NormalizedRecord:
    """A RawRecord with its data dict translated to canonical field names."""

    raw: RawRecord
    canonical_data: dict[str, Any]
    text_content: Optional[str] = None
    identifiers: dict[str, Any] = field(default_factory=dict)


# ============================================================
# Field mappings per source
#
# Format: source_field_path → canonical_field_name
# Nested paths use dot notation: "a.b.c" accesses data["a"]["b"]["c"]
# ============================================================

FIELD_MAPS: dict[SourceType, dict[str, str]] = {
    SourceType.MESH_ONTOLOGY: {
        "name": "name",
        "mesh_id": "mesh_id",
        "tree_numbers": "tree_numbers",
        "scope_note": "scope_note",
        "parent_mesh_id": "parent_mesh_id",
        "ontology_type": "term_type",  # "therapeutic_area" or "mechanism_of_action"
    },
    SourceType.FDA_ORANGE_BOOK: {
        "brand_name": "brand_name",
        "generic_name": "generic_name",
        "application_number": "nda_number",
        "approval_date": "approval_date",
        "patent_number": "patent_number",
        "patent_expiry_date": "patent_expiry_date",
        "patent_type": "patent_type",
        "applicant_holder": "applicant_holder",
        "company_name": "company_name",
        "pharm_class": "pharm_class",
        "dosage_form": "dosage_form",
        "route": "route",
        "marketing_status": "marketing_status",
        "rxcui": "rxcui",
        # Regulatory milestone fields
        "submission_type": "submission_type",
        "submission_number": "submission_number",
        "submission_status": "submission_status",
        "submission_status_date": "submission_status_date",
        "review_priority": "review_priority",
        "document_url": "document_url",
    },
    SourceType.CLINICAL_TRIALS_GOV: {
        "nct_id": "nct_id",
        "brief_title": "title",
        "overall_status": "status",
        "phase": "phase",
        "lead_sponsor_name": "sponsor_name",
        "conditions": "conditions",
        "interventions": "interventions",
        "start_date": "start_date",
        "completion_date": "completion_date",
        "enrollment_target": "enrollment_target",
        "actual_enrollment": "actual_enrollment",
        "why_stopped": "failure_reason",
        "detailed_description": "detailed_description",
        "study_type": "study_type",
        "official_title": "official_title",
        "eligibility_criteria": "eligibility_criteria",
        "primary_completion_date": "primary_completion_date",
        "collaborator_names": "collaborator_names",
        # Trial outcome fields
        "outcome_type": "outcome_type",
        "measure": "measure",
        "time_frame": "time_frame",
        "description": "description",
        # Trial location fields
        "facility_name": "facility_name",
        "city": "city",
        "state": "state",
        "country": "country",
        "location_status": "status",
        # Investigator fields
        "investigator_name": "name",
        "investigator_affiliation": "affiliation",
        "investigator_country": "affiliation_country",
        "trial_nct_id": "trial_nct_id",
    },
    SourceType.FDA_SHORTAGES: {
        "generic_name": "generic_name",
        "proprietary_name": "brand_name",
        "company_name": "company_name",
        "status": "shortage_status",
        "shortage_reason": "shortage_reason",
        "update_date": "event_date",
        "initial_posting_date": "initial_date",
        "therapeutic_category": "therapeutic_category",
        "event_type": "event_type",
        "description": "description",
        "impact_score": "impact_score",
    },
    SourceType.PUBMED: {
        "pmid": "pmid",
        "title": "title",
        "abstract": "abstract",
        "authors": "authors",
        "journal": "journal",
        "publication_date": "publication_date",
        "mesh_descriptor_ids": "mesh_descriptor_ids",
        "mesh_terms": "mesh_terms",
        "doi": "doi",
        "publication_type": "publication_type",
        "grant_agencies": "grant_agencies",
        "keywords": "keywords",
        # Author/investigator fields
        "author_name": "name",
        "author_affiliation": "affiliation",
        "author_country": "affiliation_country",
        "author_orcid": "orcid",
        "source_pmid": "source_pmid",
    },
    SourceType.SEC_EDGAR: {
        "accession_number": "accession_number",
        "company_name": "company_name",
        "cik": "cik",
        "ticker": "ticker",
        "filing_type": "filing_type",
        "filing_date": "filing_date",
        "section_name": "section_name",
        "chunk_text": "chunk_text",
        "chunk_index": "chunk_index",
        "sic_code": "sic_code",
        "country": "country",
        "fiscal_year_end": "fiscal_year_end",
        "region": "region",
    },
    SourceType.USER_DOCUMENT: {
        "filename": "filename",
        "chunk_text": "chunk_text",
        "chunk_index": "chunk_index",
        "user_tags": "user_tags",
        "extracted_entities": "extracted_entities",
    },
    SourceType.USER_URL: {
        "url": "url",
        "page_title": "page_title",
        "chunk_text": "chunk_text",
        "chunk_index": "chunk_index",
        "extracted_entities": "extracted_entities",
    },
    # OpenFDA connectors — identity maps
    SourceType.OPENFDA_FAERS: {
        "drug_name": "drug_name",
        "reaction": "reaction",
        "reaction_meddra_pt": "reaction_meddra_pt",
        "outcome": "outcome",
        "severity": "severity",
        "report_id": "report_id",
        "report_date": "report_date",
    },
    SourceType.OPENFDA_LABELS: {
        "drug_name": "drug_name",
        "set_id": "set_id",
        "spl_version": "spl_version",
        "indications": "indications",
        "manufacturer": "manufacturer",
    },
    # New connectors — identity maps (data already uses canonical field names)
    SourceType.EMA: {
        "eudract_number": "eudract_number",
        "official_title": "official_title",
        "sponsor_name": "sponsor_name",
        "status": "status",
        "phase": "phase",
        "conditions": "conditions",
        "drug_name": "drug_name",
        "start_date": "start_date",
        "country": "country",
    },
    SourceType.NADAC: {
        "generic_name": "generic_name",
        "ndc_code": "ndc_code",
        "unit_price": "unit_price",
        "unit": "unit",
        "currency": "currency",
        "price_type": "price_type",
        "effective_date": "effective_date",
    },
    SourceType.NEWS: {
        "description": "description",
        "event_type": "event_type",
        "event_date": "event_date",
        "source_url": "source_url",
        "source_feed": "source_feed",
    },
    SourceType.CHEMBL: {
        "generic_name": "generic_name",
        "chembl_id": "chembl_id",
        "molecule_type": "molecule_type",
        "max_phase": "max_phase",
        "molecular_weight": "molecular_weight",
        "smiles": "smiles",
        "mechanism_of_action": "mechanism_of_action",
        "target_name": "target_name",
        "activity_type": "activity_type",
        "activity_value": "activity_value",
        "pchembl_value": "pchembl_value",
    },
    SourceType.PUBCHEM: {
        "generic_name": "generic_name",
        "pubchem_cid": "pubchem_cid",
        "molecular_formula": "molecular_formula",
        "molecular_weight": "molecular_weight",
        "canonical_smiles": "canonical_smiles",
        "inchi": "inchi",
        "inchi_key": "inchi_key",
        "xlogp": "xlogp",
        "synonyms": "synonyms",
    },
    SourceType.OPEN_TARGETS: {
        "drug_name": "drug_name",
        "target_symbol": "target_symbol",
        "target_name": "target_name",
        "target_biotype": "target_biotype",
        "disease_associations": "disease_associations",
        "tractability": "tractability",
    },
}


def _get_nested(data: dict, path: str) -> Any:
    """Retrieve a value from a nested dict using dot notation."""
    keys = path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return None
        if current is None:
            return None
    return current


class Normalizer:
    """
    Translates source-specific RawRecord.data dicts into canonical field names.
    Config-driven: adding a new source = adding one entry to FIELD_MAPS,
    or providing field mappings via a domain pack.
    """

    def __init__(self, domain_pack=None):
        self.domain_pack = domain_pack

    def normalize(self, record: RawRecord) -> NormalizedRecord:
        source_type = record.provenance.source_type

        # Try domain pack field mappings first, fall back to hardcoded FIELD_MAPS
        field_map = None
        if self.domain_pack:
            fm = self.domain_pack.field_mappings.get(source_type.value)
            if fm:
                field_map = fm.mappings
        if field_map is None:
            field_map = FIELD_MAPS.get(source_type)

        if field_map is None:
            logger.warning(
                "No field map for source %s, passing data through unchanged",
                source_type.value,
            )
            return NormalizedRecord(
                raw=record,
                canonical_data=record.data.copy(),
                text_content=record.text_content,
                identifiers=record.identifiers.copy(),
            )

        canonical = {}
        for source_path, canonical_name in field_map.items():
            value = _get_nested(record.data, source_path)
            if value is not None:
                canonical[canonical_name] = value

        # Canonicalize source naming fields so every record uses consistent values
        canonicalize_fn = _canonicalize_source
        if self.domain_pack:
            pack_canonical = self.domain_pack.source_canonical
            def _pack_canonicalize(value):
                if value is None:
                    return None
                normalized = value.strip().lower()
                return pack_canonical.get(normalized, normalized)
            canonicalize_fn = _pack_canonicalize

        for source_field in ("source_api", "source_authority"):
            if source_field in canonical:
                canonical[source_field] = canonicalize_fn(canonical[source_field])

        return NormalizedRecord(
            raw=record,
            canonical_data=canonical,
            text_content=record.text_content,
            identifiers=record.identifiers.copy(),
        )
