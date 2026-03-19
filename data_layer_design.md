# Market-Zero Data System: Architecture Design

**Status:** Design Draft
**Depends on:** `vision_rough.md` (product vision, schema, ETL specs)

---

## Part 1: The Vision of the Data System

### What is this?

Strip away the UI, the scoring engine, the LLM -- what remains is the actual product: **a living, self-enriching pharmaceutical knowledge graph built from real public data.**

Every other component (risk scoring, agent, dashboard) is a *view* on top of this data system. If the data system is right, you can build ten different products on it. If the data system is wrong, no amount of UI polish or LLM cleverness will save you.

### The core insight

No single data source tells you anything useful on its own:

- ClinicalTrials.gov tells you a trial was **terminated** -- but not why it matters strategically.
- The FDA Orange Book tells you a patent **expires in 2032** -- but not who's already positioning to compete.
- PubMed tells you a mechanism has **adverse event reports** -- but not whether the FDA has acted on them.
- An SEC 10-K tells you a company **disclosed supply chain risk** -- but not which specific drugs are affected.

The value is in the **cross-links**: when the system can say "this terminated trial (ClinicalTrials.gov) was for the same mechanism (MeSH) as this drug (Orange Book) whose manufacturer (EDGAR 10-K) just disclosed a supply chain risk (EDGAR) while the FDA resolved the shortage (FDA Shortages API) -- and here's the published safety data (PubMed)."

**Each connector doesn't add rows. It adds dimensions.** The system gets smarter with every new source because the cross-linking surface area grows combinatorially.

### What the data system must be

1. **Source-agnostic pipeline.** Every data source -- whether it's the FDA, PubMed, or a user-uploaded PDF -- enters through the same contract. The pipeline doesn't know or care where data came from; it knows how to normalize, resolve, embed, and cross-link.

2. **Self-enriching.** When a new PubMed article arrives that mentions "Semaglutide" and has MeSH term `D009765` (Obesity), the system automatically links it to the existing drug record (from Orange Book), the existing trials (from ClinicalTrials.gov), and the existing company filings (from EDGAR) -- without any manual wiring.

3. **Provenance-complete.** Every fact in the system traces to a specific source, retrieved at a specific time, via a specific API call. This is non-negotiable for pharma.

4. **User-extensible.** An analyst should be able to drop a PDF, a URL, or a competitor's press release into the system and have it enter the same pipeline as an FDA filing. Same normalization, same entity resolution, same embedding, same cross-linking.

5. **Ontology-grounded.** The system doesn't invent categories. Therapeutic areas come from MeSH. Mechanisms come from MeSH pharmacological actions. Drug classifications come from the Orange Book. The ontology is imported, not designed.

---

## Part 2: Architecture (Working Backward)

### The Five Layers

```
                    ┌──────────────────────────────────┐
                    │        QUERY LAYER               │
                    │  (Risk Engine, Agent, API, UI)    │
                    └──────────────┬───────────────────┘
                                   │ reads
                    ┌──────────────▼───────────────────┐
                    │        SEMANTIC LAYER             │
                    │  Embeddings, Vector Index,        │
                    │  Ontology Graph, Cross-Links      │
                    └──────────────┬───────────────────┘
                                   │ built on
                    ┌──────────────▼───────────────────┐
                    │        KNOWLEDGE LAYER            │
                    │  Unified Schema (PostgreSQL)      │
                    │  Entities, Events, Chunks, Provenance │
                    └──────────────┬───────────────────┘
                                   │ fed by
                    ┌──────────────▼───────────────────┐
                    │        INTEGRATION LAYER          │
                    │  Normalize → Resolve → Embed →    │
                    │  Store → Cross-Link               │
                    └──────────────┬───────────────────┘
                                   │ receives from
                    ┌──────────────▼───────────────────┐
                    │        CONNECTOR LAYER            │
                    │  Source-specific adapters          │
                    │  (APIs, file parsers, scrapers)    │
                    │  + User Source Ingestion           │
                    └──────────────────────────────────┘
```

Data flows **up**. Queries flow **down**. Each layer has a clear contract with the layer above it.

---

## Part 3: Connector Layer

### The Connector Contract

Every connector -- whether it's ClinicalTrials.gov, PubMed, or a user-uploaded PDF -- must produce the same output: a list of `RawRecord` objects.

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class SourceType(Enum):
    CLINICAL_TRIALS_GOV = "clinical_trials_gov"
    FDA_ORANGE_BOOK = "fda_orange_book"
    FDA_SHORTAGES = "fda_shortages"
    SEC_EDGAR = "sec_edgar"
    PUBMED = "pubmed"
    MESH_ONTOLOGY = "mesh_ontology"
    USER_DOCUMENT = "user_document"
    USER_URL = "user_url"


class RecordType(Enum):
    DRUG = "drug"
    COMPANY = "company"
    TRIAL = "trial"
    EVENT = "event"
    LITERATURE = "literature"
    ONTOLOGY_TERM = "ontology_term"
    DOCUMENT_CHUNK = "document_chunk"


@dataclass
class Provenance:
    """Every record carries its full provenance."""
    source_type: SourceType
    api_endpoint: str            # The exact URL or file path
    query_params: dict           # The exact parameters used
    retrieved_at: datetime       # When this was fetched
    raw_response_hash: str       # SHA-256 of the raw API response (for audit)
    etl_run_id: Optional[str] = None


@dataclass
class RawRecord:
    """The universal output of every connector."""
    record_type: RecordType
    external_id: str             # Source-native ID (NCT number, PMID, NDA number, etc.)
    source_name: str             # Human-readable source name
    provenance: Provenance
    data: dict                   # Source-specific payload (normalized by integration layer)
    text_content: Optional[str] = None  # Free text for embedding (abstract, filing section, etc.)
    identifiers: dict = field(default_factory=dict)
    # Cross-link keys: {"mesh_ids": ["D009765"], "nda_number": "215256",
    #                    "generic_name": "semaglutide", "company_name": "Novo Nordisk"}
    # These are the hooks the integration layer uses for entity resolution.
```

### Why this contract matters

The integration layer downstream doesn't import `ClinicalTrialsConnector` or `PubMedConnector`. It receives `list[RawRecord]`. This means:

- Adding a new source = writing one new connector class. Zero changes to the pipeline.
- A user uploading a PDF produces `RawRecord` objects identical in shape to an FDA API response.
- Testing is trivial: mock a `RawRecord`, push it through the pipeline, verify the output.

### Connector Implementations

Each connector is a Python class that implements one method:

```python
from abc import ABC, abstractmethod


class BaseConnector(ABC):
    """Every connector implements this interface."""

    @abstractmethod
    def fetch(self, since: datetime | None = None) -> list[RawRecord]:
        """
        Fetch records from the source.

        Args:
            since: If provided, only fetch records updated after this timestamp.
                   If None, perform a full backfill.

        Returns:
            List of RawRecord objects with full provenance.
        """
        ...

    @abstractmethod
    def source_type(self) -> SourceType:
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Verify the source is reachable and responding."""
        ...
```

#### Connector Registry

```python
# connectors/__init__.py
# New connectors are registered here. That's it.

CONNECTOR_REGISTRY: dict[SourceType, type[BaseConnector]] = {
    SourceType.MESH_ONTOLOGY: MeSHConnector,
    SourceType.FDA_ORANGE_BOOK: OrangeBookConnector,
    SourceType.CLINICAL_TRIALS_GOV: ClinicalTrialsConnector,
    SourceType.FDA_SHORTAGES: FDAShortagesConnector,
    SourceType.SEC_EDGAR: EDGARConnector,
    SourceType.PUBMED: PubMedConnector,
    SourceType.USER_DOCUMENT: UserDocumentConnector,
    SourceType.USER_URL: UserURLConnector,
}
```

#### Connector Details

| Connector | External ID | Key `identifiers` for cross-linking | `text_content` (for embedding) |
|-----------|------------|--------------------------------------|-------------------------------|
| **MeSH** | Descriptor ID (`D003924`) | `mesh_id`, `tree_numbers`, `parent_descriptors` | Scope note / preferred label |
| **Orange Book** | NDA number (`215256`) | `nda_number`, `generic_name`, `patent_number`, `pharm_class` | None (structured data only) |
| **ClinicalTrials.gov** | NCT ID (`NCT05972063`) | `nct_id`, `sponsor_name`, `conditions` (MeSH-mappable), `interventions` | `detailed_description` + `eligibility_criteria` |
| **FDA Shortages** | NDC code or generic name | `generic_name`, `ndc`, `company_name` | `shortage_reason` |
| **SEC EDGAR** | Accession number | `cik`, `ticker`, `company_name`, `filing_type` | Filing section text (Item 1A, Item 7) |
| **PubMed** | PMID (`38291034`) | `pmid`, `mesh_ids`, `doi`, `author_affiliations` | `title` + `abstract` |
| **User Document** | Generated UUID | User-provided tags + LLM-extracted entities | Full document text (chunked) |
| **User URL** | URL hash | LLM-extracted entities | Fetched page content (cleaned, chunked) |

---

## Part 4: Integration Layer

This is the pipeline that transforms `RawRecord` objects into unified knowledge. It runs the same five steps for every record, regardless of source.

### Step 1: Normalize

Map source-specific field names to the unified schema. This is a thin translation layer.

```python
class Normalizer:
    """
    Translates source-specific data dicts into canonical field names.
    Each source has a mapping config, not code.
    """

    FIELD_MAPS: dict[SourceType, dict] = {
        SourceType.CLINICAL_TRIALS_GOV: {
            "protocolSection.identificationModule.nctId": "external_id",
            "protocolSection.statusModule.overallStatus": "status",
            "protocolSection.designModule.phases": "phase",
            "protocolSection.sponsorCollaboratorsModule.leadSponsor.name": "sponsor_name",
            "protocolSection.descriptionModule.detailedDescription": "description",
            # ...
        },
        SourceType.FDA_ORANGE_BOOK: {
            "application_number": "nda_number",
            "openfda.brand_name": "brand_name",
            "openfda.generic_name": "generic_name",
            # patent.txt fields:
            "patent_no": "patent_number",
            "patent_expire_date_text": "patent_expiry_date",
            # ...
        },
        # ... one mapping per source
    }

    def normalize(self, record: RawRecord) -> NormalizedRecord:
        mapping = self.FIELD_MAPS[record.provenance.source_type]
        # Apply mapping, validate required fields, return NormalizedRecord
        ...
```

**Key design decision:** Normalization is config-driven, not code-driven. Adding a new field mapping is editing a dict, not writing a function.

### Step 2: Entity Resolution

This is the critical step. When a ClinicalTrials.gov record says `sponsor_name = "Novo Nordisk A/S"` and the Orange Book says `company_name = "NOVO"`, the system must recognize these are the same entity.

```python
class EntityResolver:
    """
    Links incoming records to existing entities in the knowledge layer.
    Uses a hierarchy of matching strategies.
    """

    def resolve(self, record: NormalizedRecord) -> ResolvedRecord:
        """
        For each identifier in the record, attempt to match it to an
        existing entity in the DB. Returns the record annotated with
        resolved entity IDs (UUIDs from our tables).
        """
        resolved_links = {}

        # Strategy 1: Exact match on canonical IDs
        # NCT ID, PMID, NDA number, MeSH ID -- these are globally unique.
        # If the record has one, look it up directly.
        for id_type in ["nct_id", "pmid", "nda_number", "mesh_id"]:
            if id_type in record.identifiers:
                entity = self.exact_lookup(id_type, record.identifiers[id_type])
                if entity:
                    resolved_links[id_type] = entity.id

        # Strategy 2: Fuzzy match on names
        # Company names, drug names -- these vary across sources.
        # "Novo Nordisk A/S" vs "NOVO" vs "Novo Nordisk Inc."
        for name_type in ["company_name", "generic_name"]:
            if name_type in record.identifiers and name_type not in resolved_links:
                entity = self.fuzzy_lookup(name_type, record.identifiers[name_type])
                if entity and entity.confidence >= 0.85:
                    resolved_links[name_type] = entity.id
                else:
                    # Log to unresolved queue for manual review
                    self.log_unresolved(record, name_type)

        # Strategy 3: Ontology-mediated match
        # A PubMed article with MeSH term D009765 (Obesity) links to
        # all drugs in our DB whose therapeutic_area_id points to the
        # same MeSH descriptor.
        if "mesh_ids" in record.identifiers:
            for mesh_id in record.identifiers["mesh_ids"]:
                linked_entities = self.ontology_lookup(mesh_id)
                resolved_links.setdefault("ontology_links", []).extend(linked_entities)

        return ResolvedRecord(record=record, resolved_links=resolved_links)
```

#### The Entity Alias Table

Fuzzy matching is expensive and error-prone if done on every run. Instead, once a match is confirmed (automatically at >= 0.95 confidence, or manually for 0.85--0.95), it's stored as a permanent alias:

```sql
CREATE TABLE entity_aliases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type TEXT NOT NULL,          -- "company", "drug"
    entity_id UUID NOT NULL,            -- FK to the canonical entity
    alias_text TEXT NOT NULL,           -- The variant name (e.g., "Novo Nordisk A/S")
    source_type TEXT NOT NULL,          -- Which source uses this alias
    confidence FLOAT NOT NULL,          -- Match confidence when created
    verified BOOLEAN DEFAULT FALSE,     -- Manually confirmed?
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_alias_unique ON entity_aliases(entity_type, alias_text, source_type);
```

Next time "Novo Nordisk A/S" appears from ClinicalTrials.gov, it's an instant exact lookup against the alias table -- no fuzzy matching needed.

#### The Unresolved Queue

When the resolver can't match with sufficient confidence, the record goes to a review queue:

```sql
CREATE TABLE unresolved_entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_value TEXT NOT NULL,            -- The unmatched name
    record_type TEXT NOT NULL,          -- "company", "drug", etc.
    source_type TEXT NOT NULL,
    suggested_match_id UUID,            -- Best guess entity
    suggested_confidence FLOAT,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_by TEXT,                   -- "auto" or admin username
    resolved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

This queue is exposed in the admin UI. Resolving an entry creates an `entity_aliases` row so it never appears again.

### Step 3: Embed

Generate vector embeddings for any record that has `text_content`.

```python
class Embedder:
    """
    Generates embeddings for text content.
    Batched for efficiency, with provenance tracking.
    """

    def embed_batch(self, records: list[ResolvedRecord]) -> list[EmbeddedRecord]:
        texts = [r.record.text_content for r in records if r.record.text_content]

        # Batch call to OpenAI text-embedding-3-small
        # Records without text_content pass through with embedding=None
        embeddings = self.embedding_client.embed(texts, model="text-embedding-3-small")

        # Attach embeddings to records
        ...
```

**What gets embedded:**

| Record Type | Text Embedded | Why |
|------------|---------------|-----|
| Clinical Trial | `detailed_description` + `eligibility_criteria` | Semantic search for similar trials |
| PubMed Article | `title` + `abstract` | Literature search by concept |
| SEC Filing Chunk | 500-token section chunk | RAG retrieval for risk factor text |
| FDA Shortage | `shortage_reason` | Contextual similarity |
| User Document | Chunked document text | RAG retrieval |
| Drug | None (structured data) | Cross-linked via ontology, not embedding |
| Ontology Term | `scope_note` | Concept similarity for term mapping |

### Step 4: Store

Write the resolved, embedded records to the knowledge layer (Postgres).

```python
class KnowledgeStore:
    """
    Writes records to the appropriate tables with full provenance.
    Handles upserts (new records) and updates (changed records).
    """

    def store(self, record: EmbeddedRecord) -> str:
        """
        Route the record to the correct table based on record_type.
        Returns the UUID of the stored/updated row.
        """
        router = {
            RecordType.DRUG: self._store_drug,
            RecordType.COMPANY: self._store_company,
            RecordType.TRIAL: self._store_trial,
            RecordType.EVENT: self._store_event,
            RecordType.LITERATURE: self._store_pubmed_article,
            RecordType.ONTOLOGY_TERM: self._store_ontology_term,
            RecordType.DOCUMENT_CHUNK: self._store_knowledge_chunk,
        }
        return router[record.record.record_type](record)

    def _store_drug(self, record: EmbeddedRecord) -> str:
        """
        INSERT ... ON CONFLICT (nda_number) DO UPDATE
        Always preserves: source_api, source_url, retrieved_at
        """
        ...
```

### Step 5: Cross-Link

After storing, detect new relationships that this record creates.

```python
class CrossLinker:
    """
    Detects and records relationships between entities
    that span multiple sources.
    """

    def cross_link(self, record: EmbeddedRecord, stored_id: str):
        """
        After a record is stored, check if it creates new cross-links
        with existing entities.
        """
        links_created = []

        # Example: A new PubMed article with MeSH term D009765 (Obesity)
        # links to every drug in our DB with that therapeutic area.
        if record.record.record_type == RecordType.LITERATURE:
            mesh_ids = record.record.identifiers.get("mesh_ids", [])
            for mesh_id in mesh_ids:
                # Find drugs linked to this MeSH term
                drugs = self.db.query(
                    "SELECT id FROM drugs d "
                    "JOIN therapeutic_areas ta ON d.therapeutic_area_id = ta.id "
                    "WHERE ta.mesh_id = %s", [mesh_id]
                )
                for drug in drugs:
                    self._create_link(
                        source_id=stored_id,
                        source_type="pubmed_article",
                        target_id=drug.id,
                        target_type="drug",
                        link_type="EVIDENCE_FOR",
                        via="mesh_term",
                        mesh_id=mesh_id
                    )
                    links_created.append(drug.id)

        # Example: A new clinical trial links to a drug via intervention name
        # AND to a company via sponsor name (both already resolved in Step 2).
        if record.record.record_type == RecordType.TRIAL:
            # Drug link (via resolved generic_name → drug.id)
            # Company link (via resolved sponsor_name → company.id)
            # These were already resolved in Step 2; just record them.
            ...

        return links_created
```

#### The Cross-Link Table

```sql
-- Stores relationships discovered across sources.
-- This IS the knowledge graph, implemented as a table.
CREATE TABLE entity_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_entity_id UUID NOT NULL,
    source_entity_type TEXT NOT NULL,   -- "drug", "company", "trial", "pubmed_article"
    target_entity_id UUID NOT NULL,
    target_entity_type TEXT NOT NULL,
    link_type TEXT NOT NULL,            -- "OWNS", "SPONSORS", "EVIDENCE_FOR",
                                        -- "COMPETES_WITH", "PATENT_BLOCKS",
                                        -- "MENTIONED_IN", "SUPPLIES"
    link_via TEXT,                      -- How this link was discovered
                                        -- "mesh_term", "nda_number", "entity_resolution",
                                        -- "user_tagged", "llm_extracted"
    confidence FLOAT DEFAULT 1.0,      -- 1.0 for ID-based links, lower for inferred
    metadata JSONB,                     -- Extra context (e.g., {"mesh_id": "D009765"})
    provenance_source TEXT,            -- Which connector created this link
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_links_source ON entity_links(source_entity_id, source_entity_type);
CREATE INDEX idx_links_target ON entity_links(target_entity_id, target_entity_type);
CREATE INDEX idx_links_type ON entity_links(link_type);
```

**This replaces Neo4j for MVP.** The `entity_links` table is a flattened graph. Traversal queries use SQL joins:

```sql
-- "Find all evidence (PubMed) for drugs that compete with Semaglutide"
SELECT pa.title, pa.pmid, el2.link_type
FROM entity_links el1
JOIN entity_links el2 ON el1.target_entity_id = el2.target_entity_id
JOIN pubmed_articles pa ON el2.source_entity_id = pa.id
WHERE el1.source_entity_id = (SELECT id FROM drugs WHERE generic_name = 'Semaglutide')
  AND el1.link_type = 'COMPETES_WITH'
  AND el2.link_type = 'EVIDENCE_FOR';
```

---

## Part 5: Semantic Layer

The semantic layer provides three capabilities on top of the knowledge layer:

### A. Vector Search

Query the `embedding` columns across tables using pgvector's HNSW index.

```sql
-- "Find knowledge chunks about supply chain risk for GLP-1 drugs"
SELECT kc.chunk_text, kc.source_type, kc.source_reference, kc.source_url,
       1 - (kc.embedding <=> $query_embedding) AS similarity
FROM knowledge_chunks kc
JOIN entity_links el ON kc.entity_id = el.source_entity_id
  AND kc.entity_type = el.source_entity_type
WHERE el.link_type = 'MENTIONED_IN'
ORDER BY kc.embedding <=> $query_embedding
LIMIT 10;
```

### B. Ontology Traversal

Navigate the MeSH hierarchy to broaden or narrow queries.

```sql
-- "Find all drugs for mechanisms UNDER the GLP-1 family"
-- MeSH tree: D27.505.519.389.400 (GLP-1 Receptor Agonists is under this subtree)
SELECT d.brand_name, d.generic_name, moa.name AS mechanism
FROM drugs d
JOIN mechanisms_of_action moa ON d.mechanism_id = moa.id
JOIN therapeutic_areas ta ON d.therapeutic_area_id = ta.id
WHERE moa.mesh_id IN (
    SELECT mesh_id FROM mechanisms_of_action
    WHERE tree_numbers && ARRAY(
        SELECT unnest(tree_numbers) FROM mechanisms_of_action
        WHERE mesh_id = 'D000077205'  -- parent GLP-1 concept
    )
);
```

### C. Hybrid Retrieval (Structured + Semantic)

The most powerful queries combine SQL filters (structured) with vector search (semantic):

```python
class HybridRetriever:
    """
    Combines structured filters with semantic search.
    Used by the Risk Engine and the Research Agent.
    """

    def retrieve(
        self,
        query_text: str,
        entity_type: str | None = None,
        therapeutic_area_mesh_id: str | None = None,
        date_range: tuple[date, date] | None = None,
        source_types: list[str] | None = None,
        limit: int = 10,
    ) -> list[RetrievalResult]:
        """
        1. Embed the query text.
        2. Build SQL with structured WHERE clauses.
        3. ORDER BY vector similarity within the filtered set.
        """
        query_embedding = self.embedder.embed(query_text)

        sql = """
            SELECT kc.*, 1 - (kc.embedding <=> %(embedding)s) AS similarity
            FROM knowledge_chunks kc
            WHERE 1=1
        """
        params = {"embedding": query_embedding}

        if therapeutic_area_mesh_id:
            sql += """
                AND kc.entity_id IN (
                    SELECT d.id FROM drugs d
                    JOIN therapeutic_areas ta ON d.therapeutic_area_id = ta.id
                    WHERE ta.mesh_id = %(mesh_id)s
                )
            """
            params["mesh_id"] = therapeutic_area_mesh_id

        if source_types:
            sql += " AND kc.source_type = ANY(%(source_types)s)"
            params["source_types"] = source_types

        if date_range:
            sql += " AND kc.created_at BETWEEN %(start)s AND %(end)s"
            params["start"], params["end"] = date_range

        sql += " ORDER BY kc.embedding <=> %(embedding)s LIMIT %(limit)s"
        params["limit"] = limit

        return self.db.execute(sql, params)
```

---

## Part 6: User Source Mechanism

Users can add their own sources through two entry points. Both produce `RawRecord` objects and enter the same pipeline as any other connector.

### A. Document Upload

User uploads a PDF, DOCX, or text file through the UI or API.

```
POST /sources/upload
Content-Type: multipart/form-data

file: <binary>
metadata: {
    "entity_type": "company",       // What kind of entity does this relate to?
    "entity_name": "Novo Nordisk",  // Optional: pre-link to a known entity
    "source_label": "Internal competitive analysis",
    "tags": ["competitor", "pipeline"]
}
```

**Pipeline:**

1. **Extract text.** PDF → `pdfplumber` or `pymupdf`. DOCX → `python-docx`. Plain text → passthrough.
2. **Chunk.** Split into 500-token chunks with 50-token overlap.
3. **Entity extraction (LLM-assisted).** Send the first 2000 tokens to the LLM with a structured prompt: "Extract any drug names, company names, NCT numbers, or MeSH-relevant terms from this text. Return as JSON." This produces the `identifiers` dict for entity resolution.
4. **Produce `RawRecord`s.** One per chunk, with `record_type = DOCUMENT_CHUNK`, `source_type = USER_DOCUMENT`, and provenance pointing to the upload timestamp and user ID.
5. **Enter the integration pipeline.** Normalize → Resolve → Embed → Store → Cross-Link. The chunks are now searchable alongside FDA filings and PubMed abstracts.

### B. URL Ingestion

User provides a URL to a news article, press release, or regulatory document.

```
POST /sources/url
Content-Type: application/json

{
    "url": "https://www.novonordisk.com/news/press-releases/2025/02/...",
    "source_label": "Novo Nordisk press release",
    "tags": ["competitor", "pipeline-update"]
}
```

**Pipeline:**

1. **Fetch & clean.** HTTP GET → strip HTML → extract article body (using `trafilatura` or `readability-lxml`).
2. **Same as document upload from step 2 onward.**

### C. User Source Provenance

User-provided sources carry the same provenance structure as automated sources:

```python
Provenance(
    source_type=SourceType.USER_DOCUMENT,  # or USER_URL
    api_endpoint="upload://user/{user_id}",  # or the actual URL
    query_params={"filename": "competitive_analysis.pdf", "tags": ["competitor"]},
    retrieved_at=datetime.utcnow(),
    raw_response_hash=sha256(file_bytes),
    etl_run_id=None,  # User uploads don't have ETL runs
)
```

User sources are visually distinguished in the UI (tagged as "User Provided") but participate equally in scoring and retrieval.

---

## Part 7: How the Ontology Self-Enriches

This is the key thing to demonstrate. Each new connector makes the existing data more useful.

### The enrichment sequence (and what it proves at each step)

**Step 1: MeSH Ontology (the skeleton)**

```
therapeutic_areas: [Diabetes Mellitus Type 2, Obesity, ...]
mechanisms_of_action: [GLP-1 Receptor Agonists, DPP-4 Inhibitors, ...]
```

At this point you have: a taxonomy. No drugs, no companies, no events. Useful on its own? No. But it's the scaffolding everything else attaches to.

**Step 2: + FDA Orange Book (the assets)**

```
drugs: [Semaglutide (Ozempic, Wegovy), Tirzepatide (Mounjaro, Zepbound), ...]
  → linked to mechanisms via pharm_class → mesh_id
  → patent numbers and expiry dates from patent.txt
```

Now you have: drugs attached to the taxonomy with real patent data. You can already answer "which GLP-1 drugs have patents expiring before 2030?" purely from structured data.

**Step 3: + ClinicalTrials.gov (the activity)**

```
clinical_trials: [NCT05972063 (Tirzepatide Phase 3), ...]
  → linked to drugs via intervention name
  → linked to companies via sponsor name (entity resolution)
  → linked to therapeutic areas via condition → MeSH mapping
```

Now you have: the competitive landscape. You can answer "who is running Phase 3 trials in Obesity?" and "which companies sponsor trials for the same mechanism as Semaglutide?"

**Step 4: + FDA Shortages (the disruptions)**

```
market_events: [SHORTAGE_RESOLVED for Semaglutide, ...]
  → linked to drugs via generic_name
  → cross-linked to trials and companies via entity_links
```

Now you have: live market signals attached to the competitive landscape. The risk scoring engine can fire R2 (Shortage Loophole Closed) because the shortage event is linked to the drug which is linked to the mechanism.

**Step 5: + PubMed (the evidence)**

```
pubmed_articles: [PMID:38291034 (Semaglutide safety meta-analysis), ...]
  → linked to drugs via MeSH term matching (D000099194 = Semaglutide)
  → linked to therapeutic areas via MeSH descriptors
  → abstract embeddings enable semantic search
```

Now you have: published scientific evidence attached to every drug. The LLM critique can cite peer-reviewed literature, not just regulatory filings. R8 (Failed Precedent) can reference published adverse event analyses.

**Step 6: + SEC EDGAR (the strategy)**

```
knowledge_chunks: ["Item 1A: We face competition from biosimilar manufacturers...", ...]
  → linked to companies via CIK
  → linked to drugs via entity extraction
  → text embeddings enable RAG retrieval
```

Now you have: corporate strategic disclosures searchable alongside clinical data. The agent can find that Novo Nordisk disclosed supply chain concentration risk in the same filing where they discuss Semaglutide patent strategy.

**Step 7: + User Sources (the edge)**

```
knowledge_chunks: [User-uploaded competitive analysis, press release, ...]
  → linked to entities via LLM-extracted identifiers
  → same embedding space as all other chunks
```

Now the user's proprietary intelligence is integrated with public data. A user-uploaded "competitor pipeline deck" is retrievable alongside the competitor's 10-K and their ClinicalTrials.gov filings.

---

## Part 8: Project Structure

```
market_zero/
├── connectors/                     # Connector Layer
│   ├── __init__.py                 # CONNECTOR_REGISTRY
│   ├── base.py                     # BaseConnector, RawRecord, Provenance
│   ├── mesh.py                     # MeSHConnector
│   ├── orange_book.py              # OrangeBookConnector
│   ├── clinical_trials.py          # ClinicalTrialsConnector
│   ├── fda_shortages.py            # FDAShortagesConnector
│   ├── edgar.py                    # EDGARConnector
│   ├── pubmed.py                   # PubMedConnector
│   └── user_source.py              # UserDocumentConnector, UserURLConnector
│
├── integration/                    # Integration Layer
│   ├── __init__.py
│   ├── pipeline.py                 # Main pipeline: fetch → normalize → resolve → embed → store → link
│   ├── normalizer.py               # Field mapping configs per source
│   ├── entity_resolver.py          # Exact + fuzzy + ontology matching
│   ├── embedder.py                 # Batched OpenAI embedding calls
│   ├── knowledge_store.py          # Upsert logic per record type
│   └── cross_linker.py             # Post-store relationship detection
│
├── semantic/                       # Semantic Layer
│   ├── __init__.py
│   ├── hybrid_retriever.py         # Structured + vector search
│   ├── ontology.py                 # MeSH hierarchy traversal helpers
│   └── query_builder.py            # SQL builder for filtered vector queries
│
├── schema/                         # Knowledge Layer (DB)
│   ├── migrations/
│   │   ├── 001_core_tables.sql
│   │   ├── 002_entity_links.sql
│   │   ├── 003_entity_aliases.sql
│   │   └── 004_unresolved_queue.sql
│   └── seed/                       # Empty -- no seed data. Only ETL-sourced data.
│
├── api/                            # Query Layer (FastAPI)
│   ├── __init__.py
│   ├── simulate.py                 # POST /simulate, POST /simulate/compare
│   ├── market.py                   # GET /market/entity, GET /market/snapshot
│   ├── sources.py                  # POST /sources/upload, POST /sources/url
│   └── admin.py                    # GET /admin/health, POST /admin/ingest
│
├── scheduler/                      # ETL Scheduling
│   ├── cron.py                     # Schedule definitions per connector
│   └── runner.py                   # Execute connector → pipeline, record etl_run
│
├── tests/
│   ├── connectors/                 # One test file per connector (hits real APIs)
│   ├── integration/                # Pipeline tests with RawRecord fixtures
│   └── semantic/                   # Retrieval quality tests
│
└── config.py                       # DB connection, API keys, embedding model, etc.
```

---

## Part 9: Implementation Task List

Ordered by dependency. Each task produces a working, testable increment.

### Phase 0: Foundation

| # | Task | Produces | Depends On |
|---|------|----------|-----------|
| 0.1 | Set up PostgreSQL 16 + pgvector. Create database. | Running DB instance | Nothing |
| 0.2 | Write and apply `001_core_tables.sql` (companies, drugs, clinical_trials, market_events, knowledge_chunks, pubmed_articles, etl_runs) with all provenance columns | Schema ready | 0.1 |
| 0.3 | Write and apply `002_entity_links.sql` | Cross-link table ready | 0.2 |
| 0.4 | Write and apply `003_entity_aliases.sql` + `004_unresolved_queue.sql` | Entity resolution tables ready | 0.2 |
| 0.5 | Implement `BaseConnector`, `RawRecord`, `Provenance`, `SourceType`, `RecordType` in `connectors/base.py` | Connector contract defined | Nothing |
| 0.6 | Implement `pipeline.py` skeleton (the 5-step flow: normalize → resolve → embed → store → cross-link) with pass-through stubs | Pipeline runnable (no-op) | 0.5 |

### Phase 1: Ontology Bootstrap (MeSH)

| # | Task | Produces | Depends On |
|---|------|----------|-----------|
| 1.1 | Implement `MeSHConnector` -- fetches therapeutic area descriptors and pharmacological action terms from MeSH JSON-LD API | `RawRecord` list of ontology terms | 0.5 |
| 1.2 | Implement `normalizer.py` mapping for MeSH records | Normalized MeSH records | 1.1, 0.6 |
| 1.3 | Implement `knowledge_store.py` for `ONTOLOGY_TERM` record type (writes to `therapeutic_areas` and `mechanisms_of_action`) | Real MeSH terms in DB | 1.2, 0.2 |
| 1.4 | Run MeSH connector end-to-end. Verify: `SELECT * FROM therapeutic_areas WHERE mesh_id = 'D003924'` returns "Diabetes Mellitus, Type 2" with provenance. | **Ontology live in DB** | 1.1--1.3 |

### Phase 2: Drug Data (Orange Book)

| # | Task | Produces | Depends On |
|---|------|----------|-----------|
| 2.1 | Implement `OrangeBookConnector` -- downloads bulk ZIP, parses `patent.txt` + `product.txt`, queries openFDA API for approval data, joins on NDA number | `RawRecord` list of drugs with patent data | 0.5 |
| 2.2 | Implement normalizer mapping for Orange Book records | Normalized drug records | 2.1 |
| 2.3 | Implement `knowledge_store.py` for `DRUG` record type (writes to `drugs`, links `mechanism_id` and `therapeutic_area_id` via ontology matching) | Real drugs in DB with patent data | 2.2, 1.4 |
| 2.4 | Implement `entity_resolver.py` -- exact match on NDA number, pharm_class → mechanism_id lookup | Drugs linked to ontology | 2.3 |
| 2.5 | Run Orange Book connector end-to-end. Verify: `SELECT generic_name, patent_number, patent_expiry_date, source_url FROM drugs WHERE generic_name ILIKE '%semaglutide%'` returns real patent data. | **Drugs live in DB** | 2.1--2.4 |

### Phase 3: Clinical Trials

| # | Task | Produces | Depends On |
|---|------|----------|-----------|
| 3.1 | Implement `ClinicalTrialsConnector` -- queries API v2 for Diabetes/Obesity trials, supports `since` for incremental fetch | `RawRecord` list of trials | 0.5 |
| 3.2 | Implement normalizer mapping for ClinicalTrials.gov | Normalized trial records | 3.1 |
| 3.3 | Implement entity resolution for sponsor names (fuzzy match → `companies` table, create company if new + confidence > threshold) | Trials linked to companies | 3.2, 0.4 |
| 3.4 | Implement `embedder.py` -- batched OpenAI embedding for `detailed_description` | Trial embeddings | 3.2 |
| 3.5 | Implement `knowledge_store.py` for `TRIAL` record type | Real trials in DB | 3.3, 3.4 |
| 3.6 | Implement `cross_linker.py` for trials (trial → drug via intervention, trial → company via sponsor, trial → therapeutic area via condition) | Cross-links created | 3.5, 0.3 |
| 3.7 | Run ClinicalTrials.gov connector end-to-end. Verify: `SELECT ct.id, c.name FROM clinical_trials ct JOIN entity_links el ON ... JOIN companies c ON ...` returns real trials linked to real companies. | **Trials + Companies live in DB** | 3.1--3.6 |

### Phase 4: Market Events (FDA Shortages)

| # | Task | Produces | Depends On |
|---|------|----------|-----------|
| 4.1 | Implement `FDAShortagesConnector` -- queries openFDA shortages API, detects state changes vs. existing events | `RawRecord` list of shortage events | 0.5 |
| 4.2 | Implement normalizer + store for `EVENT` record type | Shortage events in DB | 4.1, 2.5 |
| 4.3 | Implement cross-linker for events (event → drug, event → company) | Events linked to drugs | 4.2, 0.3 |
| 4.4 | Run FDA Shortages connector end-to-end. Verify: `SELECT d.generic_name, me.event_type, me.source_url FROM market_events me JOIN drugs d ON ...` returns real shortage data linked to real drugs. | **Market events live in DB** | 4.1--4.3 |

### Phase 5: Literature (PubMed)

| # | Task | Produces | Depends On |
|---|------|----------|-----------|
| 5.1 | Implement `PubMedConnector` -- esearch by drug name + therapeutic area, efetch for metadata + MeSH terms, parse XML | `RawRecord` list of articles | 0.5 |
| 5.2 | Implement normalizer mapping for PubMed (XML field paths → canonical fields) | Normalized article records | 5.1 |
| 5.3 | Implement entity resolution via MeSH descriptor IDs (article mesh_ids → drugs with matching therapeutic_area.mesh_id or mechanism.mesh_id) | Articles linked to drugs via ontology | 5.2, 1.4, 2.5 |
| 5.4 | Implement embedder for article abstracts | Article embeddings | 5.2 |
| 5.5 | Run PubMed connector end-to-end. Verify: articles appear in `pubmed_articles` with real PMIDs and are cross-linked to drugs in `entity_links`. | **Literature live in DB** | 5.1--5.4 |

### Phase 6: Corporate Filings (EDGAR)

| # | Task | Produces | Depends On |
|---|------|----------|-----------|
| 6.1 | Implement `EDGARConnector` -- `sec-edgar-downloader` for 10-K filings, section extraction (Item 1A, Item 7), chunking | `RawRecord` list of filing chunks | 0.5 |
| 6.2 | Implement entity resolution for EDGAR (CIK → company_id exact match) | Chunks linked to companies | 6.1, 3.7 |
| 6.3 | Implement embedder for filing chunks | Chunk embeddings | 6.1 |
| 6.4 | Implement cross-linker for filing chunks (chunk → company via CIK, chunk → drug via entity name extraction in text) | Filing chunks linked to companies and drugs | 6.2, 0.3 |
| 6.5 | Run EDGAR connector end-to-end. Verify: `SELECT kc.source_reference, kc.source_url, c.name FROM knowledge_chunks kc JOIN entity_links el ON ... JOIN companies c ON ...` returns real 10-K excerpts linked to real companies. | **Filings live in DB** | 6.1--6.4 |

### Phase 7: User Sources

| # | Task | Produces | Depends On |
|---|------|----------|-----------|
| 7.1 | Implement `UserDocumentConnector` -- PDF/DOCX text extraction, chunking, LLM entity extraction | `RawRecord` list of user doc chunks | 0.5 |
| 7.2 | Implement `UserURLConnector` -- HTTP fetch, HTML cleaning, same chunking path | `RawRecord` list of URL content chunks | 0.5 |
| 7.3 | Implement `POST /sources/upload` and `POST /sources/url` API endpoints | User sources enter pipeline via API | 7.1, 7.2, 0.6 |
| 7.4 | Verify: upload a PDF, confirm chunks appear in `knowledge_chunks` with embeddings and are cross-linked to existing entities. | **User sources integrated** | 7.1--7.3 |

### Phase 8: Semantic Layer + Validation

| # | Task | Produces | Depends On |
|---|------|----------|-----------|
| 8.1 | Implement `hybrid_retriever.py` -- combined structured + vector queries | Semantic search working | All Phase 1--6 |
| 8.2 | Implement `ontology.py` -- MeSH hierarchy traversal helpers (broaden/narrow queries) | Ontology navigation working | 1.4 |
| 8.3 | Implement `GET /admin/health` with per-source freshness, record counts, and last successful ETL run | Admin monitoring working | All Phase 1--6 |
| 8.4 | **Provenance audit:** Select 20 random rows across all tables. For each, follow `source_url` to the real external source and confirm data matches. | Data integrity verified | All Phase 1--6 |
| 8.5 | **Cross-link audit:** Run `SELECT link_type, COUNT(*) FROM entity_links GROUP BY link_type` and verify the graph has meaningful density. | Graph quality verified | All Phase 1--6 |

---

## Part 10: What Success Looks Like

After all phases complete, run this query:

```sql
-- "For the drug Semaglutide, show me everything the system knows,
--  with provenance for every fact."
SELECT
    d.generic_name,
    d.patent_number,
    d.patent_expiry_date,
    d.source_url AS patent_source,

    ta.name AS therapeutic_area,
    ta.mesh_id,
    ta.source_url AS ontology_source,

    ct.id AS trial_nct_id,
    ct.status AS trial_status,
    ct.source_url AS trial_source,

    me.event_type,
    me.event_date,
    me.source_url AS event_source,

    pa.pmid,
    pa.title AS article_title,
    pa.source_url AS article_source,

    kc.source_type AS filing_type,
    kc.source_reference AS filing_section,
    kc.source_url AS filing_source

FROM drugs d
LEFT JOIN therapeutic_areas ta ON d.therapeutic_area_id = ta.id
LEFT JOIN entity_links el_trial ON d.id = el_trial.target_entity_id
    AND el_trial.link_type IN ('INVESTIGATES', 'SPONSORS')
LEFT JOIN clinical_trials ct ON el_trial.source_entity_id = ct.id::uuid
LEFT JOIN market_events me ON d.id = me.drug_id
LEFT JOIN entity_links el_lit ON d.id = el_lit.target_entity_id
    AND el_lit.link_type = 'EVIDENCE_FOR'
LEFT JOIN pubmed_articles pa ON el_lit.source_entity_id = pa.id
LEFT JOIN entity_links el_filing ON d.company_id = el_filing.target_entity_id
    AND el_filing.link_type = 'MENTIONED_IN'
LEFT JOIN knowledge_chunks kc ON el_filing.source_entity_id = kc.id
WHERE d.generic_name ILIKE '%semaglutide%'
LIMIT 50;
```

Every column has a `_source` companion. Every fact is real. The ontology links everything together. That's the product.
