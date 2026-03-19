"""
Core dataclasses for the domain pack system.

A DomainPack is the single configuration object that makes the pipeline
domain-agnostic. It replaces 6 hardcoded registries scattered across files:

  1. FIELD_MAPS        (normalizer.py)      → DomainPack.field_mappings
  2. EXACT_LOOKUP_MAP  (entity_resolver.py) → EntitySchema.exact_lookup_keys
  3. FUZZY_MATCH_FIELDS(entity_resolver.py) → EntitySchema.fuzzy_match_fields
  4. VALIDATION_SCHEMA (pipeline_hooks.py)  → EntitySchema.required/recommended
  5. ENTITY_TABLE_MAP  (data_quality.py)    → EntitySchema.table_name
  6. _link_* methods   (cross_linker.py)    → DomainPack.link_rules

To add a new domain, create a DomainPack with entity schemas and link rules.
The pipeline engine handles the rest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class EntitySchema:
    """
    Declares everything about an entity type in one place.

    This replaces scattered declarations across entity_resolver.py,
    data_quality.py, pipeline_hooks.py, and knowledge_store.py.

    Example (pharma):
        EntitySchema(
            name="drug",
            table_name="drugs",
            record_types=["drug"],
            required_fields=["generic_name"],
            recommended_fields=["brand_name", "company_id", ...],
            exact_lookup_keys={"nda_number": "nda_number"},
            fuzzy_match_fields={"generic_name": "generic_name"},
            embedding_column="molecule_embedding",
        )

    Example (genomics):
        EntitySchema(
            name="gene",
            table_name="genes",
            record_types=["gene"],
            required_fields=["symbol", "ensembl_id"],
            exact_lookup_keys={"ensembl_id": "ensembl_id", "entrez_id": "entrez_id"},
            fuzzy_match_fields={"gene_name": "full_name"},
            embedding_column="description_embedding",
        )
    """

    # Identity
    name: str                       # "drug", "gene", "sample"
    table_name: str                 # "drugs", "genes", "samples"
    id_column: str = "id"           # primary key column

    # Which RecordType values map to this entity
    record_types: list[str] = field(default_factory=list)

    # Validation (used by ValidationGateHook)
    required_fields: list[str] = field(default_factory=list)
    recommended_fields: list[str] = field(default_factory=list)

    # Resolution (used by EntityResolver)
    # Maps identifier_key (from RawRecord.identifiers) → DB column name
    exact_lookup_keys: dict[str, str] = field(default_factory=dict)
    fuzzy_match_fields: dict[str, str] = field(default_factory=dict)
    embedding_column: Optional[str] = None

    # Auto-create config
    auto_create_insert_sql: Optional[str] = None
    auto_create_params: Optional[Callable] = None  # fn(value, record) -> list[params]
    skip_terms: set[str] = field(default_factory=set)

    # Storage config
    store_columns: list[str] = field(default_factory=list)
    upsert_conflict_column: Optional[str] = None
    coalesce_on_update: bool = True

    # Quality
    consistency_checks: list[str] = field(default_factory=list)


@dataclass
class LinkRule:
    """
    Declares a cross-linking rule that fires when a record is stored.

    Replaces the per-type _link_drug(), _link_trial(), etc. methods in
    cross_linker.py with declarative config.

    Example:
        LinkRule(
            record_type="drug",
            identifier_key="company_name",
            link_type="OWNS",
            target_entity="drug",
            source_entity="company",
            stored_id_is="target",
        )

    This means: when a DRUG record is stored and it has a resolved
    "company_name" identifier, create an OWNS link from the resolved
    company to the stored drug.
    """

    record_type: str            # which RecordType triggers this rule
    identifier_key: str         # which resolved_links key to check
    link_type: str              # LinkType value (e.g., "OWNS")
    source_entity: str          # entity type of the source end
    target_entity: str          # entity type of the target end
    stored_id_is: str = "target"  # "source" or "target" — which end is the stored_id


@dataclass
class FieldMapping:
    """
    Maps source-specific field names to canonical field names.

    Replaces FIELD_MAPS entries in normalizer.py.
    """

    source_type: str                # SourceType value
    mappings: dict[str, str] = field(default_factory=dict)


@dataclass
class SourceConfig:
    """Configuration for a data source."""

    name: str                       # canonical name (e.g., "clinical_trials_gov")
    aliases: list[str] = field(default_factory=list)  # variant spellings
    auto_create_allowed: bool = False  # whether auto-create is enabled for this source


@dataclass
class OntologyConfig:
    """
    Declares an ontology lookup for entity resolution.

    Example (pharma):
        OntologyConfig(
            name="mesh",
            identifier_key="mesh_ids",
            lookups=[
                ("therapeutic_areas", "mesh_id", "therapeutic_area"),
                ("mechanisms_of_action", "mesh_id", "mechanism"),
            ],
        )

    Example (genomics):
        OntologyConfig(
            name="gene_ontology",
            identifier_key="go_ids",
            lookups=[
                ("pathways", "go_id", "pathway"),
                ("molecular_functions", "go_id", "molecular_function"),
            ],
        )
    """

    name: str
    identifier_key: str             # key in RawRecord.identifiers (e.g., "mesh_ids")
    lookups: list[tuple[str, str, str]] = field(default_factory=list)
    # Each tuple: (table_name, id_column, entity_type)


@dataclass
class MentionNormalizer:
    """
    Pluggable name cleaning for entity mentions.

    In pharma: "SEMAGLUTIDE 0.5mg injection" → "semaglutide"
    In genomics: "TP53 (tumor protein p53)" → "TP53"
    """

    entity_type: str
    normalize_fn: Callable[[str], str]  # fn(raw_mention) -> cleaned_name


@dataclass
class AgentPersona:
    """Defines a specialist persona for the agent team eval mode.

    Each persona has a domain-specific system prompt, focus areas,
    and a list of tools it can access.
    """

    name: str               # "clinical_researcher"
    display_name: str       # "Clinical Researcher"
    system_prompt: str      # Domain-specific expert instructions
    focus: str              # What this persona evaluates
    tools: list[str] = field(default_factory=lambda: ["rag"])  # ["sql", "rag", "graph"]


@dataclass
class DomainPack:
    """
    Complete domain configuration. One per domain.

    This is the single object that makes the pipeline domain-agnostic.
    The pipeline reads entity schemas, link rules, field mappings,
    resolution config, and validation rules from the active domain pack.

    Creating a new domain = creating a new DomainPack. No pipeline code changes.
    """

    # Identity
    name: str                   # "pharma", "genomics", "labdata"
    version: str                # "1.0.0"
    description: str            # Human-readable description

    # Entity declarations
    entities: dict[str, EntitySchema] = field(default_factory=dict)

    # Cross-linking rules
    link_rules: list[LinkRule] = field(default_factory=list)

    # Field mappings per source
    field_mappings: dict[str, FieldMapping] = field(default_factory=dict)

    # Source configurations
    sources: dict[str, SourceConfig] = field(default_factory=dict)

    # Ontology lookups
    ontologies: list[OntologyConfig] = field(default_factory=list)

    # Mention normalizers (pluggable name cleaning per entity type)
    mention_normalizers: dict[str, MentionNormalizer] = field(default_factory=dict)

    # Agent personas for team eval mode
    personas: dict[str, AgentPersona] = field(default_factory=dict)

    # Source canonicalization
    source_canonical: dict[str, str] = field(default_factory=dict)
    canonical_sources: set[str] = field(default_factory=set)

    # LLM resolution prompt template
    llm_resolution_prompt: str = (
        "You are an entity resolution system for the {domain} domain. "
        "Determine if the query {entity_type} matches any of the candidates."
    )

    # Staleness config: source_type -> [(table, source_column, source_value)]
    staleness_map: dict[str, list[tuple[str, str, str]]] = field(default_factory=dict)

    # --- Convenience methods ---

    def get_entity_for_record_type(self, record_type: str) -> Optional[EntitySchema]:
        """Find the entity schema that handles a given record type."""
        for entity in self.entities.values():
            if record_type in entity.record_types:
                return entity
        return None

    def get_record_type_to_entity_map(self) -> dict[str, str]:
        """Build the RECORD_TYPE_TO_ENTITY mapping from entity schemas."""
        mapping = {}
        for entity in self.entities.values():
            for rt in entity.record_types:
                mapping[rt] = entity.name
        return mapping

    def get_entity_table_map(self) -> dict[str, str]:
        """Build ENTITY_TABLE_MAP from entity schemas."""
        return {e.name: e.table_name for e in self.entities.values()}

    def get_entity_id_col_map(self) -> dict[str, str]:
        """Build ENTITY_ID_COL from entity schemas."""
        return {e.name: e.id_column for e in self.entities.values()}

    def get_exact_lookup_map(self) -> dict[str, tuple[str, str, str]]:
        """Build EXACT_LOOKUP_MAP from entity schemas."""
        result = {}
        for entity in self.entities.values():
            for id_key, column in entity.exact_lookup_keys.items():
                result[id_key] = (entity.table_name, column, entity.name)
        return result

    def get_fuzzy_match_map(self) -> dict[str, tuple[str, str, str]]:
        """Build FUZZY_MATCH_FIELDS from entity schemas."""
        result = {}
        for entity in self.entities.values():
            for id_key, column in entity.fuzzy_match_fields.items():
                result[id_key] = (entity.table_name, column, entity.name)
        return result

    def get_embedding_columns(self) -> dict[str, Optional[str]]:
        """Build EMBEDDING_COLUMNS from entity schemas."""
        return {
            e.table_name: e.embedding_column
            for e in self.entities.values()
            if e.embedding_column is not None
        }

    def get_validation_schema(self) -> dict[str, dict[str, list[str]]]:
        """Build VALIDATION_SCHEMA from entity schemas."""
        return {
            e.name: {
                "required": e.required_fields,
                "recommended": e.recommended_fields,
            }
            for e in self.entities.values()
            if e.required_fields or e.recommended_fields
        }

    def get_link_rules_for_record_type(self, record_type: str) -> list[LinkRule]:
        """Get all link rules that fire for a given record type."""
        return [r for r in self.link_rules if r.record_type == record_type]

    def get_auto_create_sources(self) -> set[str]:
        """Get source types that allow auto-create."""
        return {name for name, src in self.sources.items() if src.auto_create_allowed}

    def normalize_mention(self, entity_type: str, raw_value: str) -> str:
        """Clean a mention using the domain-specific normalizer, if registered."""
        normalizer = self.mention_normalizers.get(entity_type)
        if normalizer:
            return normalizer.normalize_fn(raw_value)
        return raw_value.strip()
