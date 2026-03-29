"""
Pharma domain pack — complete domain configuration for Market-Zero.

Extracts all pharma-specific hardcoded values from the pipeline into
a single DomainPack declaration. This is the reference implementation
for how domain packs work.

Usage:
    from domain.pharma import get_pharma_pack
    pack = get_pharma_pack()
"""

from __future__ import annotations

from domain.schema import (
    AgentPersona,
    DomainPack,
    EntitySchema,
    FieldMapping,
    LinkRule,
    MentionNormalizer,
    OntologyConfig,
    SourceConfig,
)
from domain.pharma.mention_normalizer import (
    COMPANY_SKIP_TERMS,
    DRUG_SKIP_TERMS,
    normalize_company_mention,
    normalize_drug_mention,
)


def get_pharma_pack() -> DomainPack:
    """Build and return the pharma domain pack."""

    # ── Entity Schemas ──────────────────────────────────────────

    drug = EntitySchema(
        name="drug",
        table_name="drugs",
        record_types=["drug"],
        required_fields=["generic_name"],
        recommended_fields=[
            "brand_name", "company_id", "therapeutic_area_id",
            "mechanism_id", "nda_number", "approval_date",
        ],
        exact_lookup_keys={
            "nda_number": "nda_number",
        },
        fuzzy_match_fields={
            "generic_name": "generic_name",
        },
        embedding_column="molecule_embedding",
        skip_terms=DRUG_SKIP_TERMS,
        consistency_checks=["drug_company_link", "drug_ta_link"],
    )

    company = EntitySchema(
        name="company",
        table_name="companies",
        record_types=["company"],
        required_fields=["name"],
        recommended_fields=["cik", "ticker", "country", "sic_code"],
        exact_lookup_keys={
            "cik": "cik",
            "ticker": "ticker",
        },
        fuzzy_match_fields={
            "company_name": "name",
            "sponsor_name": "name",
        },
        embedding_column="strategy_embedding",
        skip_terms=COMPANY_SKIP_TERMS,
    )

    trial = EntitySchema(
        name="trial",
        table_name="clinical_trials",
        record_types=["trial"],
        required_fields=["nct_id", "title", "status"],
        recommended_fields=[
            "phase", "sponsor_name", "drug_id", "conditions", "start_date",
        ],
        exact_lookup_keys={
            "nct_id": "id",
        },
        fuzzy_match_fields={},
        embedding_column="protocol_embedding",
        consistency_checks=["trial_status_date", "trial_drug_link"],
    )

    literature = EntitySchema(
        name="literature",
        table_name="pubmed_articles",
        id_column="pmid",
        record_types=["literature"],
        required_fields=["title", "pmid"],
        recommended_fields=["abstract", "journal", "publication_date", "drug_id"],
        exact_lookup_keys={
            "pmid": "pmid",
        },
        fuzzy_match_fields={},
        embedding_column="abstract_embedding",
    )

    event = EntitySchema(
        name="event",
        table_name="market_events",
        record_types=["event"],
        required_fields=["event_type", "description"],
        recommended_fields=["event_date", "drug_id"],
        exact_lookup_keys={},
        fuzzy_match_fields={},
    )

    therapeutic_area = EntitySchema(
        name="therapeutic_area",
        table_name="therapeutic_areas",
        record_types=[],  # ontology_term routing is handled by KnowledgeStore
        exact_lookup_keys={
            "mesh_id": "mesh_id",
        },
        fuzzy_match_fields={},
    )

    mechanism = EntitySchema(
        name="mechanism",
        table_name="mechanisms_of_action",
        record_types=[],  # ontology_term routing is handled by KnowledgeStore
        exact_lookup_keys={},
        fuzzy_match_fields={},
    )

    investigator = EntitySchema(
        name="investigator",
        table_name="investigators",
        record_types=["investigator"],
        exact_lookup_keys={
            "orcid": "orcid",
        },
        fuzzy_match_fields={
            "investigator_name": "name",
        },
        embedding_column=None,
    )

    patent = EntitySchema(
        name="patent",
        table_name="patents",
        record_types=["patent"],
        exact_lookup_keys={
            "patent_number": "patent_number",
        },
        fuzzy_match_fields={},
    )

    biomarker = EntitySchema(
        name="biomarker",
        table_name="biomarkers",
        record_types=["biomarker"],
        required_fields=["name", "category"],
        recommended_fields=["abbreviation", "unit", "clinical_significance"],
        exact_lookup_keys={},
        fuzzy_match_fields={"biomarker_name": "name"},
        embedding_column=None,
    )

    adverse_event = EntitySchema(
        name="adverse_event",
        table_name="adverse_events",
        record_types=["adverse_event"],
        required_fields=["drug_name", "reaction"],
        recommended_fields=["outcome", "severity"],
        exact_lookup_keys={"report_id": "report_id"},
        fuzzy_match_fields={},
        embedding_column=None,
    )

    drug_label = EntitySchema(
        name="drug_label",
        table_name="drug_labels",
        record_types=["drug_label"],
        required_fields=["drug_name"],
        recommended_fields=["indications", "manufacturer"],
        exact_lookup_keys={"set_id": "set_id"},
        fuzzy_match_fields={},
        embedding_column=None,
    )

    molecular_target = EntitySchema(
        name="molecular_target",
        table_name="molecular_targets",
        record_types=["molecular_target"],
        required_fields=["gene_symbol"],
        recommended_fields=["target_name", "organism", "target_type"],
        exact_lookup_keys={
            "chembl_id": "chembl_id",
            "ensembl_id": "ensembl_id",
        },
        fuzzy_match_fields={"gene_symbol": "gene_symbol"},
        embedding_column=None,
    )

    bioactivity = EntitySchema(
        name="bioactivity",
        table_name="bioactivities",
        record_types=["bioactivity"],
        required_fields=["chembl_activity_id"],
        recommended_fields=["standard_type", "standard_value", "standard_units"],
        exact_lookup_keys={"chembl_activity_id": "chembl_activity_id"},
        fuzzy_match_fields={},
        embedding_column=None,
    )

    # ── Link Rules ──────────────────────────────────────────────
    # These replace the _link_drug(), _link_trial(), etc. methods

    link_rules = [
        # Drug links
        LinkRule(
            record_type="drug",
            identifier_key="company_name",
            link_type="OWNS",
            source_entity="company",
            target_entity="drug",
            stored_id_is="target",
        ),
        LinkRule(
            record_type="drug",
            identifier_key="therapeutic_area",
            link_type="IN_THERAPEUTIC_AREA",
            source_entity="drug",
            target_entity="therapeutic_area",
            stored_id_is="source",
        ),
        LinkRule(
            record_type="drug",
            identifier_key="mechanism",
            link_type="TARGETS_MECHANISM",
            source_entity="drug",
            target_entity="mechanism",
            stored_id_is="source",
        ),

        # Trial links
        LinkRule(
            record_type="trial",
            identifier_key="generic_name",
            link_type="INVESTIGATES",
            source_entity="trial",
            target_entity="drug",
            stored_id_is="source",
        ),
        LinkRule(
            record_type="trial",
            identifier_key="sponsor_name",
            link_type="SPONSORS",
            source_entity="company",
            target_entity="trial",
            stored_id_is="target",
        ),

        # Event links
        LinkRule(
            record_type="event",
            identifier_key="generic_name",
            link_type="SHORTAGE_AFFECTS",
            source_entity="event",
            target_entity="drug",
            stored_id_is="source",
        ),

        # Literature links
        LinkRule(
            record_type="literature",
            identifier_key="generic_name",
            link_type="EVIDENCE_FOR",
            source_entity="literature",
            target_entity="drug",
            stored_id_is="source",
        ),

        # Chunk links
        LinkRule(
            record_type="document_chunk",
            identifier_key="company_name",
            link_type="MENTIONED_IN",
            source_entity="knowledge_chunk",
            target_entity="company",
            stored_id_is="source",
        ),
        LinkRule(
            record_type="document_chunk",
            identifier_key="cik",
            link_type="MENTIONED_IN",
            source_entity="knowledge_chunk",
            target_entity="company",
            stored_id_is="source",
        ),
        LinkRule(
            record_type="document_chunk",
            identifier_key="generic_name",
            link_type="MENTIONED_IN",
            source_entity="knowledge_chunk",
            target_entity="drug",
            stored_id_is="source",
        ),

        # Patent links
        LinkRule(
            record_type="patent",
            identifier_key="nda_number",
            link_type="HAS_PATENT",
            source_entity="drug",
            target_entity="patent",
            stored_id_is="target",
        ),

        # Regulatory milestone links
        LinkRule(
            record_type="regulatory_milestone",
            identifier_key="nda_number",
            link_type="HAS_MILESTONE",
            source_entity="drug",
            target_entity="regulatory_milestone",
            stored_id_is="target",
        ),

        # Adverse event → drug
        LinkRule(
            record_type="adverse_event",
            identifier_key="generic_name",
            link_type="HAS_ADVERSE_EVENT",
            source_entity="drug",
            target_entity="adverse_event",
            stored_id_is="target",
        ),

        # Drug label → drug
        LinkRule(
            record_type="drug_label",
            identifier_key="generic_name",
            link_type="HAS_LABEL",
            source_entity="drug",
            target_entity="drug_label",
            stored_id_is="target",
        ),
    ]

    # ── Field Mappings ──────────────────────────────────────────
    # These replace FIELD_MAPS in normalizer.py

    field_mappings = {
        "mesh_ontology": FieldMapping(
            source_type="mesh_ontology",
            mappings={
                "name": "name",
                "mesh_id": "mesh_id",
                "tree_numbers": "tree_numbers",
                "scope_note": "scope_note",
                "parent_mesh_id": "parent_mesh_id",
                "ontology_type": "term_type",
            },
        ),
        "fda_orange_book": FieldMapping(
            source_type="fda_orange_book",
            mappings={
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
                "submission_type": "submission_type",
                "submission_number": "submission_number",
                "submission_status": "submission_status",
                "submission_status_date": "submission_status_date",
                "review_priority": "review_priority",
                "document_url": "document_url",
            },
        ),
        "clinical_trials_gov": FieldMapping(
            source_type="clinical_trials_gov",
            mappings={
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
                "outcome_type": "outcome_type",
                "measure": "measure",
                "time_frame": "time_frame",
                "description": "description",
                "facility_name": "facility_name",
                "city": "city",
                "state": "state",
                "country": "country",
                "location_status": "status",
                "investigator_name": "name",
                "investigator_affiliation": "affiliation",
                "investigator_country": "affiliation_country",
                "trial_nct_id": "trial_nct_id",
            },
        ),
        "fda_shortages": FieldMapping(
            source_type="fda_shortages",
            mappings={
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
        ),
        "pubmed": FieldMapping(
            source_type="pubmed",
            mappings={
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
                "author_name": "name",
                "author_affiliation": "affiliation",
                "author_country": "affiliation_country",
                "author_orcid": "orcid",
                "source_pmid": "source_pmid",
            },
        ),
        "sec_edgar": FieldMapping(
            source_type="sec_edgar",
            mappings={
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
        ),
        "user_document": FieldMapping(
            source_type="user_document",
            mappings={
                "filename": "filename",
                "chunk_text": "chunk_text",
                "chunk_index": "chunk_index",
                "user_tags": "user_tags",
                "extracted_entities": "extracted_entities",
            },
        ),
        "user_url": FieldMapping(
            source_type="user_url",
            mappings={
                "url": "url",
                "page_title": "page_title",
                "chunk_text": "chunk_text",
                "chunk_index": "chunk_index",
                "extracted_entities": "extracted_entities",
            },
        ),
    }

    # ── Source Configurations ───────────────────────────────────

    sources = {
        "mesh_ontology": SourceConfig(name="mesh_ontology"),
        "fda_orange_book": SourceConfig(
            name="fda_orange_book",
            aliases=["orange_book", "orangebook", "fda_drugsfda"],
            auto_create_allowed=True,
        ),
        "clinical_trials_gov": SourceConfig(
            name="clinical_trials_gov",
            aliases=["clinicaltrials_gov", "clinicaltrials", "ct_gov"],
            auto_create_allowed=True,
        ),
        "fda_shortages": SourceConfig(
            name="fda_shortages",
            aliases=["fda_shortage"],
            auto_create_allowed=True,
        ),
        "sec_edgar": SourceConfig(
            name="sec_edgar",
            aliases=["edgar"],
        ),
        "pubmed": SourceConfig(
            name="pubmed",
            auto_create_allowed=True,
        ),
        "openfda_faers": SourceConfig(name="openfda_faers"),
        "openfda_labels": SourceConfig(name="openfda_labels"),
        "pmc": SourceConfig(
            name="pmc",
            aliases=["pubmed_central"],
        ),
        "user_document": SourceConfig(name="user_document"),
        "user_url": SourceConfig(name="user_url"),
        "backfill": SourceConfig(name="backfill"),
    }

    # ── Source Canonicalization ──────────────────────────────────

    # Build canonical map from source configs
    source_canonical = {}
    canonical_sources = set()
    for src in sources.values():
        canonical_sources.add(src.name)
        for alias in src.aliases:
            source_canonical[alias] = src.name

    # ── Ontology Lookups ────────────────────────────────────────

    ontologies = [
        OntologyConfig(
            name="mesh",
            identifier_key="mesh_ids",
            lookups=[
                ("therapeutic_areas", "mesh_id", "therapeutic_area"),
                ("mechanisms_of_action", "mesh_id", "mechanism"),
            ],
        ),
    ]

    # ── Staleness Map ───────────────────────────────────────────

    staleness_map = {
        "clinical_trials_gov": [("clinical_trials", "source_api", "clinical_trials_gov")],
        "fda_orange_book": [("drugs", "source_api", "fda_orange_book")],
        "fda_shortages": [("market_events", "source_api", "fda_shortages")],
        "pubmed": [("pubmed_articles", "source_api", "pubmed")],
        "sec_edgar": [("companies", "source_api", "sec_edgar")],
    }

    # ── Mention Normalizers ─────────────────────────────────────

    mention_normalizers = {
        "drug": MentionNormalizer(
            entity_type="drug",
            normalize_fn=normalize_drug_mention,
        ),
        "company": MentionNormalizer(
            entity_type="company",
            normalize_fn=normalize_company_mention,
        ),
    }

    # ── Agent Personas ─────────────────────────────────────────

    personas = {
        "clinical_researcher": AgentPersona(
            name="clinical_researcher",
            display_name="Clinical Researcher",
            system_prompt=(
                "You are a clinical research specialist with deep expertise in "
                "clinical trial design, patient populations, efficacy and safety endpoints, "
                "and evidence-based medicine. You evaluate the strength of clinical evidence "
                "and identify gaps in trial data."
            ),
            focus="Is this supported by clinical evidence? Evaluate trial design quality, "
                  "patient populations, efficacy/safety signals, and evidence gaps.",
            tools=["rag", "graph"],
        ),
        "market_analyst": AgentPersona(
            name="market_analyst",
            display_name="Market Analyst",
            system_prompt=(
                "You are a pharmaceutical market analyst with expertise in competitive "
                "positioning, market dynamics, company strategy, patent landscapes, and "
                "commercial potential. You evaluate market implications and competitive threats."
            ),
            focus="What are the commercial implications? Evaluate competitive positioning, "
                  "market dynamics, company strategy, and patent landscape.",
            tools=["sql", "metrics"],
        ),
        "regulatory_expert": AgentPersona(
            name="regulatory_expert",
            display_name="Regulatory Expert",
            system_prompt=(
                "You are a regulatory affairs expert with deep knowledge of FDA approval "
                "pathways, regulatory milestones, compliance requirements, and precedent "
                "regulatory decisions. You evaluate regulatory risks and timelines."
            ),
            focus="What are the regulatory risks and timeline? Evaluate approval pathways, "
                  "regulatory milestones, FDA actions, and compliance considerations.",
            tools=["sql", "rag"],
        ),
        "data_scientist": AgentPersona(
            name="data_scientist",
            display_name="Data Scientist",
            system_prompt=(
                "You are a data scientist focused on data quality, statistical significance, "
                "entity resolution confidence, and knowledge graph completeness. You evaluate "
                "the reliability and completeness of the underlying data."
            ),
            focus="How reliable is this data? Evaluate data quality, statistical significance, "
                  "entity resolution confidence, and knowledge graph completeness.",
            tools=["sql", "metrics"],
        ),
    }

    # ── Assemble Pack ───────────────────────────────────────────

    return DomainPack(
        name="pharma",
        version="1.0.0",
        description=(
            "Pharmaceutical intelligence domain pack for Market-Zero. "
            "Covers drugs, companies, clinical trials, regulatory milestones, "
            "patents, literature, adverse events, and market events across "
            "10 data sources (FDA, ClinicalTrials.gov, PubMed, SEC EDGAR, MeSH)."
        ),
        entities={
            "drug": drug,
            "company": company,
            "trial": trial,
            "literature": literature,
            "event": event,
            "therapeutic_area": therapeutic_area,
            "mechanism": mechanism,
            "investigator": investigator,
            "patent": patent,
            "biomarker": biomarker,
            "adverse_event": adverse_event,
            "drug_label": drug_label,
            "molecular_target": molecular_target,
            "bioactivity": bioactivity,
        },
        link_rules=link_rules,
        field_mappings=field_mappings,
        sources=sources,
        ontologies=ontologies,
        mention_normalizers=mention_normalizers,
        source_canonical=source_canonical,
        canonical_sources=canonical_sources,
        staleness_map=staleness_map,
        personas=personas,
        llm_resolution_prompt=(
            "You are a pharmaceutical entity resolution system. "
            "Determine if the query {entity_type} matches any of the candidates.\n\n"
            'Query: "{value}"\n'
            "Source: {source_type}\n"
            "Record: {external_id}\n\n"
            "Candidates:\n{candidates_json}\n\n"
            'Respond with JSON only: {{"match_index": <0-4 or null if no match>, '
            '"confidence": <0.0-1.0>, '
            '"reasoning": "<1-2 sentence explanation>"}}'
        ),
    )
