"""
Step 4: Store resolved, embedded records in the knowledge layer.

Routes each record to the correct table based on RecordType.
Handles upserts (insert or update) with full provenance preservation.
Includes content hashing for change detection and lifecycle tracking.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

from connectors.base import RecordType
from integration.embedder import EmbeddedRecord

logger = logging.getLogger(__name__)


class KnowledgeStore:
    """
    Writes records to the appropriate Postgres tables.
    Every write includes provenance columns. No row is stored without them.
    Computes content hashes for change detection and updates lifecycle timestamps.
    """

    def __init__(self, db):
        self.db = db

    @staticmethod
    def compute_content_hash(data: dict) -> str:
        """Deterministic SHA-256 of canonical payload (excludes embeddings/timestamps)."""
        skip_keys = {
            "molecule_embedding", "strategy_embedding", "abstract_embedding",
            "protocol_embedding", "scope_note_embedding", "embedding",
            "retrieved_at", "created_at", "updated_at", "last_verified_at",
            "content_hash", "quality_score", "record_status",
        }
        filtered = {k: v for k, v in data.items() if k not in skip_keys and v is not None}
        canonical = json.dumps(filtered, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def store(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """
        Route the record to the correct table and upsert.

        Returns:
            (stored_id, was_insert): The UUID of the stored row and whether
            it was a new insert (True) or an update (False).
            May return (stored_id, None) when content is unchanged (skip).
        """
        record_type = record.resolved.normalized.raw.record_type

        router = {
            RecordType.ONTOLOGY_TERM: self._store_ontology_term,
            RecordType.DRUG: self._store_drug,
            RecordType.COMPANY: self._store_company,
            RecordType.TRIAL: self._store_trial,
            RecordType.EVENT: self._store_event,
            RecordType.LITERATURE: self._store_literature,
            RecordType.ADVERSE_EVENT: self._store_adverse_event,
            RecordType.DRUG_LABEL: self._store_drug_label,
            RecordType.PMC_ARTICLE: self._store_pmc_article,
            RecordType.DOCUMENT_CHUNK: self._store_chunk,
            RecordType.PATENT: self._store_patent,
            RecordType.REGULATORY_MILESTONE: self._store_regulatory_milestone,
            RecordType.TRIAL_OUTCOME: self._store_trial_outcome,
            RecordType.TRIAL_LOCATION: self._store_trial_location,
            RecordType.INVESTIGATOR: self._store_investigator,
        }

        handler = router.get(record_type)
        if handler is None:
            raise ValueError(f"No store handler for record type: {record_type}")

        return handler(record, etl_run_id)

    # ---- Handlers per record type ----

    def _store_ontology_term(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store a MeSH therapeutic area or mechanism of action."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance
        term_type = data.get("term_type", "therapeutic_area")

        table = (
            "therapeutic_areas"
            if term_type == "therapeutic_area"
            else "mechanisms_of_action"
        )

        row = self.db.fetch_one(
            f"SELECT id FROM {table} WHERE mesh_id = %s",
            [data.get("mesh_id")],
        )

        if row:
            self.db.execute(
                f"""
                UPDATE {table}
                SET name = %s, tree_numbers = %s, parent_mesh_id = %s,
                    scope_note = %s, scope_note_embedding = %s,
                    source_api = %s, source_url = %s, retrieved_at = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                [
                    data.get("name"),
                    data.get("tree_numbers"),
                    data.get("parent_mesh_id"),
                    data.get("scope_note"),
                    record.embedding,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                    row["id"],
                ],
            )
            return str(row["id"]), False
        else:
            new_row = self.db.fetch_one(
                f"""
                INSERT INTO {table}
                    (name, mesh_id, tree_numbers, parent_mesh_id, scope_note,
                     scope_note_embedding, source_api, source_url, retrieved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                [
                    data.get("name"),
                    data.get("mesh_id"),
                    data.get("tree_numbers"),
                    data.get("parent_mesh_id"),
                    data.get("scope_note"),
                    record.embedding,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                ],
            )
            return str(new_row["id"]), True

    def _store_drug(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store a drug from Orange Book."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance
        links = record.resolved.resolved_links

        # Resolve FK references
        company_id = links.get("company_name", None)
        company_id = company_id.entity_id if company_id else None

        ta_id = links.get("therapeutic_area", None)
        ta_id = ta_id.entity_id if ta_id else None

        mech_id = links.get("mechanism", None)
        mech_id = mech_id.entity_id if mech_id else None

        # NDA-first lookup; fall back to case-insensitive generic_name
        # (auto-created drugs from ClinicalTrials.gov have no NDA).
        nda = data.get("nda_number")
        gname = data.get("generic_name")
        row = None
        if nda:
            row = self.db.fetch_one(
                "SELECT id FROM drugs WHERE nda_number = %s", [nda]
            )
        if not row and gname:
            row = self.db.fetch_one(
                "SELECT id FROM drugs WHERE LOWER(generic_name) = LOWER(%s)", [gname]
            )

        content_hash = self.compute_content_hash(data)

        if row:
            self.db.execute(
                """
                UPDATE drugs
                SET brand_name = COALESCE(%s, brand_name),
                    generic_name = COALESCE(%s, generic_name),
                    company_id = COALESCE(%s, company_id),
                    therapeutic_area_id = COALESCE(%s, therapeutic_area_id),
                    mechanism_id = COALESCE(%s, mechanism_id),
                    approval_date = COALESCE(%s, approval_date),
                    patent_expiry_date = COALESCE(%s, patent_expiry_date),
                    patent_number = COALESCE(%s, patent_number),
                    dosage_form = COALESCE(%s, dosage_form),
                    route = COALESCE(%s, route),
                    marketing_status = COALESCE(%s, marketing_status),
                    rxcui = COALESCE(%s, rxcui),
                    molecule_embedding = CASE WHEN %s IS NOT NULL THEN %s::vector ELSE molecule_embedding END,
                    source_api = %s, source_url = %s, retrieved_at = %s,
                    content_hash = %s, last_verified_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                [
                    data.get("brand_name"),
                    data.get("generic_name"),
                    company_id,
                    ta_id,
                    mech_id,
                    data.get("approval_date"),
                    data.get("patent_expiry_date"),
                    data.get("patent_number"),
                    data.get("dosage_form"),
                    data.get("route"),
                    data.get("marketing_status"),
                    data.get("rxcui"),
                    record.embedding,
                    record.embedding,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                    content_hash,
                    row["id"],
                ],
            )
            return str(row["id"]), False
        else:
            new_row = self.db.fetch_one(
                """
                INSERT INTO drugs
                    (brand_name, generic_name, nda_number, company_id,
                     therapeutic_area_id, mechanism_id, approval_date,
                     patent_expiry_date, patent_number,
                     dosage_form, route, marketing_status, rxcui,
                     molecule_embedding, content_hash, last_verified_at,
                     source_api, source_url, retrieved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s)
                RETURNING id
                """,
                [
                    data.get("brand_name"),
                    data.get("generic_name"),
                    data.get("nda_number"),
                    company_id,
                    ta_id,
                    mech_id,
                    data.get("approval_date"),
                    data.get("patent_expiry_date"),
                    data.get("patent_number"),
                    data.get("dosage_form"),
                    data.get("route"),
                    data.get("marketing_status"),
                    data.get("rxcui"),
                    record.embedding,
                    content_hash,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                ],
            )
            return str(new_row["id"]), True

    def _store_company(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store a company (typically from EDGAR or entity resolution)."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance

        name = data.get("company_name", data.get("name"))
        cik = data.get("cik")

        # CIK-first lookup (authoritative); fall back to exact name match.
        # Never use OR — it caused Novo Nordisk to match NOVAVAX.
        row = None
        if cik:
            row = self.db.fetch_one(
                "SELECT id FROM companies WHERE cik = %s", [cik]
            )
        if not row and name:
            row = self.db.fetch_one(
                "SELECT id FROM companies WHERE name = %s", [name]
            )

        content_hash = self.compute_content_hash(data)

        if row:
            self.db.execute(
                """
                UPDATE companies
                SET name = CASE WHEN %s IS NOT NULL THEN COALESCE(%s, name) ELSE name END,
                    ticker = COALESCE(%s, ticker),
                    cik = COALESCE(%s, cik),
                    region = COALESCE(%s, region),
                    sic_code = COALESCE(%s, sic_code),
                    country = COALESCE(%s, country),
                    fiscal_year_end = COALESCE(%s, fiscal_year_end),
                    strategy_embedding = CASE WHEN %s IS NOT NULL THEN %s::vector ELSE strategy_embedding END,
                    source_api = %s, source_url = %s, retrieved_at = %s,
                    content_hash = %s, last_verified_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                [
                    cik,    # if CIK provided, update name from authoritative source
                    name,
                    data.get("ticker"),
                    cik,
                    data.get("region"),
                    data.get("sic_code"),
                    data.get("country"),
                    data.get("fiscal_year_end"),
                    record.embedding,
                    record.embedding,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                    content_hash,
                    row["id"],
                ],
            )
            return str(row["id"]), False
        else:
            new_row = self.db.fetch_one(
                """
                INSERT INTO companies
                    (name, ticker, cik, region,
                     sic_code, country, fiscal_year_end,
                     strategy_embedding, content_hash, last_verified_at,
                     source_api, source_url, retrieved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s)
                RETURNING id
                """,
                [
                    name,
                    data.get("ticker"),
                    data.get("cik"),
                    data.get("region"),
                    data.get("sic_code"),
                    data.get("country"),
                    data.get("fiscal_year_end"),
                    record.embedding,
                    content_hash,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                ],
            )
            return str(new_row["id"]), True

    def _store_trial(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store a clinical trial from ClinicalTrials.gov."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance
        links = record.resolved.resolved_links

        drug_id = links.get("generic_name", None)
        drug_id = drug_id.entity_id if drug_id else None

        nct_id = data.get("nct_id", record.resolved.normalized.raw.external_id)

        # TEXT[] columns — ensure Python lists
        conditions = self._to_pg_array(data.get("conditions"))
        interventions = self._to_pg_array(data.get("interventions"))
        collaborators = self._to_pg_array(data.get("collaborator_names"))

        # Date columns — parse flexible date strings to DATE or None
        start_date = self._parse_date(data.get("start_date"))
        completion_date = self._parse_date(data.get("completion_date"))
        primary_comp_date = self._parse_date(data.get("primary_completion_date"))

        content_hash = self.compute_content_hash(data)

        row = self.db.fetch_one(
            "SELECT id FROM clinical_trials WHERE id = %s",
            [nct_id],
        )

        if row:
            self.db.execute(
                """
                UPDATE clinical_trials
                SET status = %s, phase = %s, sponsor_name = %s,
                    conditions = %s, interventions = %s,
                    start_date = %s, completion_date = %s,
                    enrollment_target = %s, actual_enrollment = %s,
                    failure_reason = %s, detailed_description = %s,
                    study_type = COALESCE(%s, study_type),
                    official_title = COALESCE(%s, official_title),
                    eligibility_criteria = COALESCE(%s, eligibility_criteria),
                    primary_completion_date = COALESCE(%s, primary_completion_date),
                    collaborator_names = COALESCE(%s, collaborator_names),
                    protocol_embedding = %s, drug_id = COALESCE(%s, drug_id),
                    content_hash = %s, last_verified_at = NOW(),
                    source_url = %s, retrieved_at = %s, updated_at = NOW()
                WHERE id = %s
                """,
                [
                    data.get("status") or data.get("overall_status"),
                    data.get("phase"),
                    data.get("sponsor_name") or data.get("lead_sponsor_name"),
                    conditions,
                    interventions,
                    start_date,
                    completion_date,
                    data.get("enrollment_target"),
                    data.get("actual_enrollment"),
                    data.get("failure_reason") or data.get("why_stopped"),
                    data.get("detailed_description"),
                    data.get("study_type"),
                    data.get("official_title"),
                    data.get("eligibility_criteria"),
                    primary_comp_date,
                    collaborators,
                    record.embedding,
                    drug_id,
                    content_hash,
                    prov.api_endpoint,
                    prov.retrieved_at,
                    nct_id,
                ],
            )
            return nct_id, False
        else:
            self.db.execute(
                """
                INSERT INTO clinical_trials
                    (id, drug_id, sponsor_name, status, phase,
                     conditions, interventions, start_date, completion_date,
                     enrollment_target, actual_enrollment, failure_reason,
                     detailed_description,
                     study_type, official_title, eligibility_criteria,
                     primary_completion_date, collaborator_names,
                     protocol_embedding, content_hash, last_verified_at,
                     source_api, source_url, retrieved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s)
                """,
                [
                    nct_id,
                    drug_id,
                    data.get("sponsor_name") or data.get("lead_sponsor_name"),
                    data.get("status") or data.get("overall_status"),
                    data.get("phase"),
                    conditions,
                    interventions,
                    start_date,
                    completion_date,
                    data.get("enrollment_target"),
                    data.get("actual_enrollment"),
                    data.get("failure_reason") or data.get("why_stopped"),
                    data.get("detailed_description"),
                    data.get("study_type"),
                    data.get("official_title"),
                    data.get("eligibility_criteria"),
                    primary_comp_date,
                    collaborators,
                    record.embedding,
                    content_hash,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                ],
            )
            return nct_id, True

    def _store_event(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store a market event (shortage, guidance, etc.)."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance
        links = record.resolved.resolved_links

        drug_link = links.get("generic_name", None)
        drug_id = drug_link.entity_id if drug_link else None

        # event_date is NOT NULL — use retrieved_at as fallback
        event_date = data.get("event_date") or prov.retrieved_at.strftime("%Y-%m-%d")
        content_hash = self.compute_content_hash(data)

        new_row = self.db.fetch_one(
            """
            INSERT INTO market_events
                (drug_id, event_type, event_date, description, impact_score,
                 content_hash, last_verified_at,
                 source_api, source_url, etl_run_id, retrieved_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s)
            RETURNING id
            """,
            [
                drug_id,
                data.get("event_type"),
                event_date,
                data.get("description"),
                data.get("impact_score"),
                content_hash,
                prov.source_type.value,
                prov.api_endpoint,
                etl_run_id,
                prov.retrieved_at,
            ],
        )
        return str(new_row["id"]), True

    @staticmethod
    def _to_pg_array(val):
        """Ensure a value is a list (for TEXT[] columns) or None."""
        if val is None:
            return None
        if isinstance(val, list):
            return val
        if isinstance(val, str) and val:
            # Split comma-separated string back into list
            return [v.strip() for v in val.split(", ") if v.strip()]
        return None

    @staticmethod
    def _parse_date(val):
        """Parse flexible date strings into YYYY-MM-DD or None."""
        if val is None:
            return None
        if isinstance(val, str):
            val = val.strip()
            if not val:
                return None
            # Already ISO format
            if len(val) == 10 and val[4] == "-":
                return val
            # YYYYMMDD
            if len(val) == 8 and val.isdigit():
                return f"{val[:4]}-{val[4:6]}-{val[6:8]}"
            # "YYYY-MM" partial date — set to first of month
            if len(val) == 7 and val[4] == "-":
                return f"{val}-01"
            # "Month YYYY" format from CT.gov
            from datetime import datetime as _dt
            for fmt in ("%B %Y", "%b %Y", "%B %d, %Y", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return _dt.strptime(val, fmt).strftime("%Y-%m-%d")
                except ValueError:
                    continue
        return None

    def _store_literature(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store a PubMed article."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance
        links = record.resolved.resolved_links

        drug_link = links.get("generic_name", None)
        drug_id = drug_link.entity_id if drug_link else None

        pmid = data.get("pmid", record.resolved.normalized.raw.external_id)

        # Ensure array fields are actual lists for TEXT[] columns
        authors = self._to_pg_array(data.get("authors"))
        mesh_terms = self._to_pg_array(data.get("mesh_terms"))
        mesh_ids = self._to_pg_array(data.get("mesh_descriptor_ids"))
        grant_agencies = self._to_pg_array(data.get("grant_agencies"))
        keywords = self._to_pg_array(data.get("keywords"))

        content_hash = self.compute_content_hash(data)

        row = self.db.fetch_one(
            "SELECT id FROM pubmed_articles WHERE pmid = %s",
            [pmid],
        )

        if row:
            self.db.execute(
                """
                UPDATE pubmed_articles
                SET title = %s, abstract = %s, authors = %s,
                    journal = %s, publication_date = %s,
                    mesh_terms = %s, mesh_descriptor_ids = %s,
                    doi = COALESCE(%s, doi),
                    publication_type = COALESCE(%s, publication_type),
                    grant_agencies = COALESCE(%s, grant_agencies),
                    keywords = COALESCE(%s, keywords),
                    drug_id = COALESCE(%s, drug_id),
                    abstract_embedding = CASE WHEN %s IS NOT NULL THEN %s::vector ELSE abstract_embedding END,
                    content_hash = %s, last_verified_at = NOW(),
                    source_url = %s, retrieved_at = %s
                WHERE id = %s
                """,
                [
                    data.get("title"),
                    data.get("abstract"),
                    authors,
                    data.get("journal"),
                    data.get("publication_date"),
                    mesh_terms,
                    mesh_ids,
                    data.get("doi"),
                    data.get("publication_type"),
                    grant_agencies,
                    keywords,
                    drug_id,
                    record.embedding,
                    record.embedding,
                    content_hash,
                    prov.api_endpoint,
                    prov.retrieved_at,
                    row["id"],
                ],
            )
            return str(row["id"]), False
        else:
            new_row = self.db.fetch_one(
                """
                INSERT INTO pubmed_articles
                    (pmid, title, abstract, authors, journal,
                     publication_date, mesh_terms, mesh_descriptor_ids,
                     doi, publication_type, grant_agencies, keywords,
                     drug_id, abstract_embedding, content_hash, last_verified_at,
                     source_api, source_url, retrieved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s)
                RETURNING id
                """,
                [
                    pmid,
                    data.get("title"),
                    data.get("abstract"),
                    authors,
                    data.get("journal"),
                    data.get("publication_date"),
                    mesh_terms,
                    mesh_ids,
                    data.get("doi"),
                    data.get("publication_type"),
                    grant_agencies,
                    keywords,
                    drug_id,
                    record.embedding,
                    content_hash,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                ],
            )
            return str(new_row["id"]), True

    def _store_adverse_event(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store an FDA FAERS adverse event report."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance
        links = record.resolved.resolved_links

        drug_link = links.get("generic_name", None)
        drug_id = drug_link.entity_id if drug_link else None

        report_id = data.get("report_id", record.resolved.normalized.raw.external_id)
        content_hash = self.compute_content_hash(data)

        row = self.db.fetch_one(
            "SELECT id FROM adverse_events WHERE report_id = %s",
            [report_id],
        )

        if row:
            self.db.execute(
                """
                UPDATE adverse_events
                SET drug_id = COALESCE(%s, drug_id),
                    drug_name = COALESCE(%s, drug_name),
                    reaction = %s, reaction_meddra_pt = %s,
                    outcome = %s, severity = %s,
                    report_date = %s, patient_age = %s,
                    patient_sex = %s, reporter_type = %s,
                    source_api = %s, source_url = %s, retrieved_at = %s,
                    content_hash = %s, last_verified_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                [
                    drug_id,
                    data.get("drug_name"),
                    data.get("reaction"),
                    data.get("reaction_meddra_pt"),
                    data.get("outcome"),
                    data.get("severity"),
                    data.get("report_date"),
                    data.get("patient_age"),
                    data.get("patient_sex"),
                    data.get("reporter_type"),
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                    content_hash,
                    row["id"],
                ],
            )
            return str(row["id"]), False
        else:
            new_row = self.db.fetch_one(
                """
                INSERT INTO adverse_events
                    (report_id, drug_id, drug_name, reaction,
                     reaction_meddra_pt, outcome, severity,
                     report_date, patient_age, patient_sex,
                     reporter_type, content_hash, last_verified_at,
                     source_api, source_url, retrieved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s)
                RETURNING id
                """,
                [
                    report_id,
                    drug_id,
                    data.get("drug_name"),
                    data.get("reaction"),
                    data.get("reaction_meddra_pt"),
                    data.get("outcome"),
                    data.get("severity"),
                    data.get("report_date"),
                    data.get("patient_age"),
                    data.get("patient_sex"),
                    data.get("reporter_type"),
                    content_hash,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                ],
            )
            return str(new_row["id"]), True

    def _store_drug_label(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store an FDA drug label from openFDA."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance
        links = record.resolved.resolved_links

        drug_link = links.get("generic_name", None)
        drug_id = drug_link.entity_id if drug_link else None

        set_id = data.get("set_id", record.resolved.normalized.raw.external_id)
        content_hash = self.compute_content_hash(data)

        row = self.db.fetch_one(
            "SELECT id FROM drug_labels WHERE set_id = %s",
            [set_id],
        )

        if row:
            self.db.execute(
                """
                UPDATE drug_labels
                SET drug_id = COALESCE(%s, drug_id),
                    drug_name = COALESCE(%s, drug_name),
                    spl_version = COALESCE(%s, spl_version),
                    indications = %s, contraindications = %s,
                    warnings_and_precautions = %s, boxed_warning = %s,
                    dosage_and_administration = %s,
                    adverse_reactions_text = %s,
                    drug_interactions_text = %s,
                    clinical_pharmacology = %s,
                    effective_date = COALESCE(%s, effective_date),
                    manufacturer = COALESCE(%s, manufacturer),
                    label_embedding = CASE WHEN %s IS NOT NULL THEN %s::vector ELSE label_embedding END,
                    source_api = %s, source_url = %s, retrieved_at = %s,
                    content_hash = %s, last_verified_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                [
                    drug_id,
                    data.get("drug_name"),
                    data.get("spl_version"),
                    data.get("indications"),
                    data.get("contraindications"),
                    data.get("warnings_and_precautions"),
                    data.get("boxed_warning"),
                    data.get("dosage_and_administration"),
                    data.get("adverse_reactions_text"),
                    data.get("drug_interactions_text"),
                    data.get("clinical_pharmacology"),
                    data.get("effective_date"),
                    data.get("manufacturer"),
                    record.embedding,
                    record.embedding,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                    content_hash,
                    row["id"],
                ],
            )
            return str(row["id"]), False
        else:
            new_row = self.db.fetch_one(
                """
                INSERT INTO drug_labels
                    (set_id, drug_id, drug_name, spl_version,
                     indications, contraindications,
                     warnings_and_precautions, boxed_warning,
                     dosage_and_administration,
                     adverse_reactions_text, drug_interactions_text,
                     clinical_pharmacology,
                     effective_date, manufacturer,
                     label_embedding, content_hash, last_verified_at,
                     source_api, source_url, retrieved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s)
                RETURNING id
                """,
                [
                    set_id,
                    drug_id,
                    data.get("drug_name"),
                    data.get("spl_version"),
                    data.get("indications"),
                    data.get("contraindications"),
                    data.get("warnings_and_precautions"),
                    data.get("boxed_warning"),
                    data.get("dosage_and_administration"),
                    data.get("adverse_reactions_text"),
                    data.get("drug_interactions_text"),
                    data.get("clinical_pharmacology"),
                    data.get("effective_date"),
                    data.get("manufacturer"),
                    record.embedding,
                    content_hash,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                ],
            )
            return str(new_row["id"]), True

    def _store_pmc_article(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store a PubMed Central full-text article."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance
        links = record.resolved.resolved_links

        drug_link = links.get("generic_name", None)
        drug_id = drug_link.entity_id if drug_link else None

        pmc_id = data.get("pmc_id", record.resolved.normalized.raw.external_id)
        pmid = data.get("pmid")

        # Try to resolve pubmed_article_id from linked PMID
        pubmed_article_id = None
        if pmid:
            pm_row = self.db.fetch_one(
                "SELECT id FROM pubmed_articles WHERE pmid = %s",
                [pmid],
            )
            if pm_row:
                pubmed_article_id = pm_row["id"]

        content_hash = self.compute_content_hash(data)

        row = self.db.fetch_one(
            "SELECT id FROM pmc_articles WHERE pmc_id = %s",
            [pmc_id],
        )

        if row:
            self.db.execute(
                """
                UPDATE pmc_articles
                SET pmid = COALESCE(%s, pmid),
                    pubmed_article_id = COALESCE(%s, pubmed_article_id),
                    drug_id = COALESCE(%s, drug_id),
                    title = COALESCE(%s, title),
                    full_text = %s,
                    article_type = COALESCE(%s, article_type),
                    is_protocol = %s, is_systematic_review = %s,
                    license = COALESCE(%s, license),
                    full_text_embedding = CASE WHEN %s IS NOT NULL THEN %s::vector ELSE full_text_embedding END,
                    source_api = %s, source_url = %s, retrieved_at = %s,
                    content_hash = %s, last_verified_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                [
                    pmid,
                    pubmed_article_id,
                    drug_id,
                    data.get("title"),
                    data.get("full_text"),
                    data.get("article_type"),
                    data.get("is_protocol", False),
                    data.get("is_systematic_review", False),
                    data.get("license"),
                    record.embedding,
                    record.embedding,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                    content_hash,
                    row["id"],
                ],
            )
            return str(row["id"]), False
        else:
            new_row = self.db.fetch_one(
                """
                INSERT INTO pmc_articles
                    (pmc_id, pmid, pubmed_article_id, drug_id,
                     title, full_text, article_type,
                     is_protocol, is_systematic_review, license,
                     full_text_embedding, content_hash, last_verified_at,
                     source_api, source_url, retrieved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s)
                RETURNING id
                """,
                [
                    pmc_id,
                    pmid,
                    pubmed_article_id,
                    drug_id,
                    data.get("title"),
                    data.get("full_text"),
                    data.get("article_type"),
                    data.get("is_protocol", False),
                    data.get("is_systematic_review", False),
                    data.get("license"),
                    record.embedding,
                    content_hash,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                ],
            )
            return str(new_row["id"]), True

    def _store_chunk(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store a knowledge chunk (SEC filing section, user document, etc.)."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance
        links = record.resolved.resolved_links

        # Determine entity link
        entity_type = "company"
        entity_id = None
        for link_key in ("company_name", "cik", "generic_name"):
            if link_key in links:
                entity_type = links[link_key].entity_type
                entity_id = links[link_key].entity_id
                break

        new_row = self.db.fetch_one(
            """
            INSERT INTO knowledge_chunks
                (entity_type, entity_id, source_type, source_reference,
                 source_url, chunk_text, embedding, etl_run_id, retrieved_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            [
                entity_type,
                entity_id,
                data.get("filing_type", data.get("source_type", prov.source_type.value)),
                data.get("section_name", data.get("source_reference", "")),
                prov.api_endpoint,
                data.get("chunk_text", record.resolved.normalized.text_content),
                record.embedding,
                etl_run_id,
                prov.retrieved_at,
            ],
        )
        return str(new_row["id"]), True

    def _store_patent(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store a patent record from Orange Book."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance
        links = record.resolved.resolved_links

        drug_link = links.get("nda_number")
        drug_id = drug_link.entity_id if drug_link else None

        row = self.db.fetch_one(
            "SELECT id FROM patents WHERE drug_id = %s AND patent_number = %s",
            [drug_id, data.get("patent_number")],
        )

        if row:
            self.db.execute(
                """
                UPDATE patents
                SET patent_expiry_date = COALESCE(%s, patent_expiry_date),
                    patent_type = COALESCE(%s, patent_type),
                    applicant_holder = COALESCE(%s, applicant_holder),
                    source_api = %s, source_url = %s, retrieved_at = %s
                WHERE id = %s
                """,
                [
                    data.get("patent_expiry_date"),
                    data.get("patent_type"),
                    data.get("applicant_holder"),
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                    row["id"],
                ],
            )
            return str(row["id"]), False
        else:
            new_row = self.db.fetch_one(
                """
                INSERT INTO patents
                    (drug_id, patent_number, patent_expiry_date, patent_type,
                     applicant_holder, source_api, source_url, retrieved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                [
                    drug_id,
                    data.get("patent_number"),
                    data.get("patent_expiry_date"),
                    data.get("patent_type"),
                    data.get("applicant_holder"),
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                ],
            )
            return str(new_row["id"]), True

    def _store_regulatory_milestone(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store an FDA regulatory milestone (submission/approval event)."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance
        links = record.resolved.resolved_links

        drug_link = links.get("nda_number")
        drug_id = drug_link.entity_id if drug_link else None

        row = self.db.fetch_one(
            """SELECT id FROM regulatory_milestones
               WHERE drug_id = %s AND submission_type = %s AND submission_number = %s""",
            [drug_id, data.get("submission_type"), data.get("submission_number")],
        )

        if row:
            self.db.execute(
                """
                UPDATE regulatory_milestones
                SET submission_status = COALESCE(%s, submission_status),
                    submission_status_date = COALESCE(%s, submission_status_date),
                    review_priority = COALESCE(%s, review_priority),
                    document_url = COALESCE(%s, document_url),
                    source_api = %s, source_url = %s, retrieved_at = %s
                WHERE id = %s
                """,
                [
                    data.get("submission_status"),
                    data.get("submission_status_date"),
                    data.get("review_priority"),
                    data.get("document_url"),
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                    row["id"],
                ],
            )
            return str(row["id"]), False
        else:
            new_row = self.db.fetch_one(
                """
                INSERT INTO regulatory_milestones
                    (drug_id, submission_type, submission_number,
                     submission_status, submission_status_date,
                     review_priority, document_url,
                     source_api, source_url, retrieved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                [
                    drug_id,
                    data.get("submission_type"),
                    data.get("submission_number"),
                    data.get("submission_status"),
                    data.get("submission_status_date"),
                    data.get("review_priority"),
                    data.get("document_url"),
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                ],
            )
            return str(new_row["id"]), True

    def _store_trial_outcome(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store a clinical trial outcome measure."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance

        trial_id = data.get("nct_id", record.resolved.normalized.raw.external_id)
        # Extract just the NCT ID if it contains extra info
        if "|" in trial_id:
            trial_id = trial_id.split("|")[0]

        new_row = self.db.fetch_one(
            """
            INSERT INTO trial_outcomes
                (trial_id, outcome_type, measure, time_frame, description,
                 source_api, source_url, retrieved_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            [
                trial_id,
                data.get("outcome_type"),
                data.get("measure"),
                data.get("time_frame"),
                data.get("description"),
                prov.source_type.value,
                prov.api_endpoint,
                prov.retrieved_at,
            ],
        )
        return str(new_row["id"]), True

    def _store_trial_location(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store a clinical trial site location."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance

        trial_id = data.get("nct_id", record.resolved.normalized.raw.external_id)
        if "|" in trial_id:
            trial_id = trial_id.split("|")[0]

        new_row = self.db.fetch_one(
            """
            INSERT INTO trial_locations
                (trial_id, facility_name, city, state, country, status,
                 source_api, source_url, retrieved_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            [
                trial_id,
                data.get("facility_name"),
                data.get("city"),
                data.get("state"),
                data.get("country"),
                data.get("status"),
                prov.source_type.value,
                prov.api_endpoint,
                prov.retrieved_at,
            ],
        )
        return str(new_row["id"]), True

    def _store_investigator(self, record: EmbeddedRecord, etl_run_id: str) -> tuple[str, bool]:
        """Store a key investigator (from trials or publications)."""
        data = record.resolved.normalized.canonical_data
        prov = record.resolved.normalized.raw.provenance

        # Try to find existing investigator by ORCID or name+affiliation
        orcid = data.get("orcid")
        name = data.get("name")

        row = None
        if orcid:
            row = self.db.fetch_one(
                "SELECT id FROM investigators WHERE orcid = %s",
                [orcid],
            )
        if not row and name:
            row = self.db.fetch_one(
                "SELECT id FROM investigators WHERE name = %s AND affiliation = %s",
                [name, data.get("affiliation")],
            )

        if row:
            self.db.execute(
                """
                UPDATE investigators
                SET affiliation = COALESCE(%s, affiliation),
                    affiliation_country = COALESCE(%s, affiliation_country),
                    orcid = COALESCE(%s, orcid),
                    source_api = %s, source_url = %s, retrieved_at = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                [
                    data.get("affiliation"),
                    data.get("affiliation_country"),
                    orcid,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                    row["id"],
                ],
            )
            return str(row["id"]), False
        else:
            new_row = self.db.fetch_one(
                """
                INSERT INTO investigators
                    (name, affiliation, affiliation_country, orcid,
                     source_api, source_url, retrieved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                [
                    name,
                    data.get("affiliation"),
                    data.get("affiliation_country"),
                    orcid,
                    prov.source_type.value,
                    prov.api_endpoint,
                    prov.retrieved_at,
                ],
            )
            return str(new_row["id"]), True
