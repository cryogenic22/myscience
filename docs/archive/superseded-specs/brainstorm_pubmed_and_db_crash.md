# Brainstorm: DB Crash, OpenAlex Integration & Pipeline Strengthening

*17–19 April 2026 — Technical Analysis*

**Sections:**
1. Database crash root cause + why volume resize isn't fixing it
2. PubMed full text — current state and recommendations
3. OpenAlex integration — the high-leverage move
4. Pipeline strengthening synthesis from lead's architecture review

---

---

## Part 1: Database Crash Root Cause Analysis

### The Crash: What Happened

The Railway PostgreSQL instance has been in a **crash loop since 2026-04-16 02:06 UTC** and is **still down as of 2026-04-17 21:20 UTC** (40+ hours). It cannot start.

### Root Cause: Disk Full

**Single root cause: the Railway volume ran out of disk space.**

The crash sequence:

1. **Apr 15 16:00** — First warnings: `pgsql_tmp` files fail during parallel query workers on `entity_links` joins (64-way parallel sort spills to disk, fills temp space). Queries against the dossier endpoint trigger this.

2. **Apr 15 16:00–Apr 16 00:22** — Continued operation but degraded. Data Steward runs (cycles 104, 105) fail on missing tables (`agent_sessions`, `agent_events`) and wrong column names (`source_type` vs `source_name` in `etl_runs`, `details` missing in `steward_actions`, `label` missing in `clinical_trials`, `primary_entity_id` missing in `market_events`). Also: `MIN(uuid)` fails because PostgreSQL has no built-in `min()` for UUID type. These are all schema drift issues — code references columns/tables that were never migrated.

3. **Apr 16 02:00** — Scheduled ETL kicks off (ClinicalTrials.gov connector, cron at 02:00 UTC). Starts bulk-inserting `trial_locations` rows.

4. **Apr 16 02:06:45** — **PANIC**: WAL write fails during `INSERT INTO trial_locations` for trial NCT05726227. PostgreSQL issues PANIC (unrecoverable), terminates all backends, attempts recovery.

5. **Apr 16 02:06:45 onward** — Recovery replays WAL from `D/66AB8DA8` to `D/7FFFFFB8` (~430 MB of WAL), completes redo successfully, but then FATAL: cannot write the new WAL segment (`pg_wal/xlogtemp.33`). Shuts down. Railway restarts the container. Same failure. Infinite crash loop.

6. **Apr 17 21:03** — Still crash-looping. Now getting floods of "database system is not yet accepting connections" as the app server hammers connection attempts during recovery.

### Why the Disk Filled

Three contributing factors, in order of impact:

| Factor | Estimated Impact | Details |
|--------|-----------------|---------|
| **WAL accumulation** | HIGH | ~430 MB of unrecyclable WAL between the two LSN markers. During the ETL bulk insert, WAL grows fast. If `max_wal_size` is at default (1 GB) and checkpoints can't keep up, WAL files pile up. |
| **Temp file spills** | MEDIUM | Parallel query workers on `entity_links` (600K+ links) spill sort/hash data to `base/pgsql_tmp/`. The 64-partition parallel sort seen in logs is a large memory spill. |
| **pgvector indexes + embeddings** | MEDIUM | 606K records with vector embeddings consume significant disk for both heap storage and IVFFlat/HNSW indexes. |

### The Schema Drift Problem (Secondary)

The logs reveal code referencing tables/columns that don't exist in the production database:

| Missing | Code Location | Issue |
|---------|--------------|-------|
| `agent_sessions` table | Data Steward agent harness | Migration never created |
| `agent_events` table | Data Steward agent harness | Migration never created |
| `steward_actions.details` column | Dossier handler | Column name mismatch |
| `market_events.primary_entity_id` column | Dossier handler | Column name mismatch |
| `clinical_trials.label` column | Quality scorecard | Column doesn't exist |
| `etl_runs.source_type` column | Data Steward | Should be `source_name` |

These don't cause the crash directly, but they mean the Data Steward runs are no-ops (every operation errors out), and quality checks silently fail. The steward runs every 2 hours, generating error log volume but doing no useful work.

### Update: Volume Resize Did NOT Fix the Crash Loop

You expanded the volume but the logs (through `2026-04-17 21:21:46`) still show:
```
FATAL: could not write to file "pg_wal/xlogtemp.32": No space left on device
```

**Why a volume resize alone isn't working:**

When a Railway volume is resized while a container is in a crash loop, the container keeps getting restarted by the orchestrator before the filesystem expansion can take effect. The block device gets the new size, but the mounted filesystem (ext4) inside the container still sees the old size. PostgreSQL crashes, container restarts, mount completes with old size, PostgreSQL crashes again.

### What to Actually Do (in this order)

**Step 1 — Force a clean redeploy (not a restart)**
1. Railway dashboard > Postgres service > **Settings**
2. Click **Redeploy** (this triggers a fresh container with a fresh mount)
3. If the option is "Restart" only, try **Remove deployment** then **Deploy** to force a new container

**Step 2 — Verify the volume size was actually applied**
After redeploy starts, immediately check `df -h` via Railway shell on the Postgres service:
```bash
df -h /var/lib/postgresql/data
```
If it shows the OLD size, the resize didn't propagate. You'll need to:
- Detach the volume, attach a new one of correct size, restore from backup
- OR contact Railway support — they can manually resize the underlying block device

**Step 3 — Clean up if filesystem shows new size but PG still crashes**
```bash
# Inside Railway shell on Postgres service:
ls -lh /var/lib/postgresql/data/pg_wal/    # See WAL accumulation
ls -lh /var/lib/postgresql/data/base/pgsql_tmp/  # See temp spills

# Don't delete pg_wal files manually — that corrupts the DB
# But you CAN safely delete pgsql_tmp contents:
rm -rf /var/lib/postgresql/data/base/pgsql_tmp/*
```

**Step 4 — If everything fails: restore from Railway backup**
1. Railway dashboard > Postgres > **Backups** tab
2. Find the most recent backup before `2026-04-16 02:06 UTC` (last clean state was `02:00:01 UTC`)
3. Restore to a new database with a properly-sized volume (10 GB+)
4. Update `DATABASE_URL` in your app service to point to the new DB
5. You will lose any data ingested between the backup time and the crash (~6 minutes of one ETL run)

### What Volume Size Do You Actually Need?

Quick math for your dataset:

| Component | Estimated Size |
|-----------|---------------|
| 606K records (heap) | ~2 GB |
| 9 vector embedding columns × 606K rows × 1536 dims × 4 bytes | ~3.5 GB |
| pgvector indexes (IVFFlat/HNSW) | ~1.5 GB |
| `entity_links` (600K+ rows) + indexes | ~500 MB |
| WAL (max_wal_size + headroom for ETL bursts) | ~2 GB |
| Temp file spills during parallel queries | ~1 GB |
| Free space buffer | ~2 GB |
| **Total minimum** | **~12 GB** |
| **Recommended** | **20 GB** |

If you set the volume to 5 GB or less, it will keep crashing. **Set it to at least 20 GB.**

### Preventive Measures

1. **Increase volume to 10 GB minimum** — 606K records with embeddings + WAL + temp sort space needs headroom
2. **Add `work_mem` setting** — Increase to 64 MB or 128 MB to reduce temp file spills for parallel sorts on `entity_links`
3. **Set `max_wal_size = 512MB`** and `checkpoint_completion_target = 0.7` — Tighter checkpoint cycles to recycle WAL faster
4. **Fix the ETL batch size** — ClinicalTrials.gov connector bulk-inserts thousands of `trial_locations` rows in one transaction. Consider chunked commits (every 500 rows) to reduce WAL pressure
5. **Disable or fix the Data Steward scheduler** — It runs every 2 hours, errors on every operation, generates noise. Either create the missing migrations or disable it until the schema is correct
6. **Add disk usage monitoring** — Railway supports metrics; set an alert at 80% disk usage

---

## Part 2: PubMed Data Collection — Can We Get Full PDFs?

### What We Currently Collect

We have **two connectors** for biomedical literature:

**PubMedConnector** (`connectors/pubmed.py`):
- Searches NCBI PubMed via E-Utilities API (esearch + efetch)
- Collects: title, abstract, authors, journal, MeSH terms, DOI, publication type, keywords, grant agencies
- Produces LITERATURE records + INVESTIGATOR records (first/last author)
- 41 hardcoded search queries covering GLP-1, SGLT2, DPP-4, cardiovascular drugs
- Max 50 articles per query, last 2 years
- **Does NOT collect full text** — PubMed only has abstracts

**PMCConnector** (`connectors/pmc.py`):
- Searches PubMed Central for **open-access full-text** articles
- Extracts full article body as structured text (sections + paragraphs from XML)
- Classifies as protocol / systematic review
- 25 target drugs, max 20 articles per drug
- Filters for `"open access"[filter]`
- **Already collects the full text** — but only for open-access articles in PMC

### Can We Get Actual PDFs?

Short answer: **Yes, partially, but it's complicated and probably not what we want.**

Here's the landscape:

#### Route 1: PMC Open Access Subset (Already Doing This)
- ~4 million articles with full text freely available
- We already extract the XML body text via PMCConnector
- The XML is richer than a PDF — structured sections, tagged references, machine-readable
- **Verdict: We're already getting the best version of this. No PDF needed.**

#### Route 2: PMC PDF Downloads
- PMC articles also have PDFs available at `https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{id}/pdf/`
- We could download these alongside the XML
- **Problem**: PDFs are binary blobs (2-20 MB each). For 500 articles that's 1-10 GB of storage
- **Problem**: PDFs need OCR/parsing to extract text (we already have the text from XML)
- **Problem**: Railway's volume is already full at ~1 GB
- **Verdict: PDFs from PMC are redundant — the XML full text is strictly better for our use case (search, embedding, citation).**

#### Route 3: Publisher APIs (Elsevier, Springer, Wiley, etc.)
- Most biomedical articles are behind publisher paywalls
- Elsevier ScienceDirect API: requires institutional subscription or API key ($$$)
- Springer Nature API: some open access, others require subscription
- Wiley Online Library API: institutional access required
- **We could get full text for ~30-40% more articles** if we had institutional API keys
- **Verdict: Feasible but requires paid API access. Not a quick win.**

#### Route 4: Unpaywall / OpenAlex for OA Discovery
- Unpaywall API (free): given a DOI, tells you if an open-access version exists and where
- OpenAlex (free): indexes 250M+ works with open access metadata
- We could use these to find OA versions of articles we only have abstracts for
- **Workflow**: For each PubMed article with a DOI, check Unpaywall → if OA version exists → fetch from the OA URL
- **Verdict: This is the highest-value next step. Low cost, legal, expands full-text coverage by 20-30%.**

#### Route 5: bioRxiv / medRxiv Preprints
- Free full-text access, no paywall
- API available for bulk download
- Many pharma-relevant preprints appear here before journal publication
- **Verdict: Good supplementary source. Easy to add as a new connector.**

### Recommendation: What to Actually Build

**Priority 1 (after DB fix): Unpaywall integration**
- For every PubMed article that has a DOI but no PMC full text
- Call Unpaywall API: `GET https://api.unpaywall.org/v2/{doi}?email={email}`
- If `is_oa: true`, fetch the `best_oa_location.url_for_pdf` or `url_for_landing_page`
- Store the full text alongside the existing abstract
- **Cost**: Free (polite use, email required). **Coverage boost**: ~20-30% of our PubMed articles

**Priority 2: Enrich existing PMC pipeline**
- We truncate full text to 2000 chars for embedding (`text_for_embedding = f"{title}. {full_text[:2000]}"`)
- We should embed the full text in chunks (overlapping 1000-token windows) for better retrieval
- Store section-level metadata (Methods, Results, Discussion) for smarter citation

**Priority 3: bioRxiv/medRxiv connector**
- New connector following BaseConnector pattern
- API: `https://api.biorxiv.org/details/biorxiv/{interval}`
- Free, no rate limit issues, full text available
- Especially valuable for cutting-edge drug mechanism research

**Priority 4 (deferred): Semantic Scholar API**
- Free API with full-text access for many papers
- Provides citation graphs, influential citations, TLDR summaries
- Could replace or supplement our PMC connector

### Why NOT to Chase PDFs

For our use case (pharma intelligence, entity linking, citation, embedding), **structured text > PDF**:

1. **PDFs are unstructured** — Tables, figures, multi-column layouts make text extraction lossy
2. **Storage cost** — Each PDF is 2-20 MB vs ~50 KB for extracted text. With a disk-full DB, this is a non-starter
3. **Processing cost** — PDF parsing (PyMuPDF, pdfplumber) adds complexity and error modes
4. **We already have the best data** — PMC XML gives us section-tagged, reference-linked, machine-readable text. A PDF is a downgrade from this.
5. **Legal risk** — Bulk-downloading publisher PDFs without subscription is legally questionable

The right mental model: **we want the text content, not the document container**. PDFs are a delivery format for humans. Our pipeline needs machine-readable text, which we already get from PubMed (abstracts) and PMC (full text XML).

### Architecture Note: Full-Text Storage

If we add Unpaywall or other full-text sources, we need to think about where to store longer documents. Options:

1. **In the existing `source_records.data` JSONB** — Works but makes the table very large
2. **Separate `literature_fulltext` table** — (`pmid`, `source`, `full_text`, `sections JSONB`, `fetched_at`)
3. **Object storage (S3/R2)** — Store full text as files, reference by key. Best for large volumes.

Given Railway's disk constraints, option 3 (Cloudflare R2 or similar) is probably necessary before we scale full-text ingestion.

---

---

## Part 3: OpenAlex Integration

### What OpenAlex Is

OpenAlex (https://openalex.org) is a free, open replacement for Microsoft Academic Graph and Web of Science. It indexes:
- **250M+ Works** (papers, preprints, books, datasets) — vs our ~2,000 PubMed articles
- **90M+ Authors** with disambiguated identities (ORCID-linked)
- **109K+ Sources** (journals, repositories, conferences)
- **Institutions** with ROR identifiers (canonical institution IDs)
- **Topics** (4,500+) — ML-tagged at Domain > Field > Subfield > Topic hierarchy
- **Concepts** (65K+) — older keyword tagging system, still maintained
- **Funders** with FundRef IDs
- **Citation graph** — `cited_by_count`, `referenced_works`, `related_works`

### Should We Download the Whole Snapshot? **No.**

The OpenAlex snapshot is **330 GB compressed / 1.6 TB uncompressed**, distributed as gzipped JSON Lines via S3.

**Reasons not to download the full snapshot:**

1. **Storage**: Your Railway DB just crashed at <1 GB. 1.6 TB is 1600× larger.
2. **99% irrelevant**: Most works are physics, history, social sciences, ML — irrelevant to pharma intelligence.
3. **Update friction**: Even with date-partitioned incremental updates, you'd be processing GB of JSON daily.
4. **Cost**: S3 egress + Railway disk for data you don't need.

**The right approach: pull selectively via the API.**

### What Sample Data Tells Us

Quick query to OpenAlex:
- `concepts.id:C71924100` (Medicine) + `concepts.id:C98274493` (Pharmacology) + `default.search:semaglutide` + 2024–2026
- **Result: 15,108 works** for just semaglutide alone

That's **300× more than our current 50 PubMed articles per query**. And every work comes with:
- Citation count + FWCI (field-weighted citation impact)
- Open access status + best OA URL (incorporates Unpaywall — replaces our planned Unpaywall integration)
- Topic assignments with confidence scores
- Author affiliations with ROR institution IDs
- Referenced works (citation graph)
- Funding info (replaces some SEC filing context)

### Recommended OpenAlex Connector Design

Build `connectors/openalex.py` following the existing `BaseConnector` pattern:

```python
class OpenAlexConnector(BaseConnector):
    """
    Pulls pharma-relevant works from OpenAlex.
    Strategy: filter by Pharmacology + Medicine concepts,
    paginated via cursor, polite pool (email in mailto param).
    """

    BASE_URL = "https://api.openalex.org/works"

    # Pharma-relevant concept IDs
    PHARMA_CONCEPTS = [
        "C98274493",  # Pharmacology
        "C71924100",  # Medicine
        "C2779134260", # Clinical trial
        "C126322002", # Internal medicine
        "C2780035454", # Drug discovery
    ]

    def fetch(self, since: datetime | None = None) -> list[RawRecord]:
        # Use cursor pagination (per_page=200, cursor=*)
        # Filter: concepts.id + publication_date>=since (incremental)
        # For each work: extract title, abstract (reconstructed from
        # abstract_inverted_index), DOI, OA URL, topics, authorships,
        # referenced_works, cited_by_count
        # Cross-link to existing drugs via DOI/title match
        ...
```

**Key implementation notes:**

1. **Polite pool** — Add `mailto=kapilpant@gmail.com` to all requests for higher rate limits (10 req/sec → unlimited)
2. **Cursor pagination** — Use `cursor=*` then follow `meta.next_cursor` for each page (handles 15K+ results cleanly)
3. **Abstract reconstruction** — OpenAlex stores abstracts as `abstract_inverted_index` (word → positions). Need a small helper to rebuild prose.
4. **Incremental sync** — Filter by `from_updated_date:YYYY-MM-DD` to only get new/changed records since last run
5. **Rate limit** — Free, 10 req/s with mailto. ~50 ms per page. Full pharma backfill in 30–60 min.

### How OpenAlex Strengthens the Pipeline

| Gap (from lead's review) | How OpenAlex Helps |
|--------------------------|-------------------|
| Citation graph missing in knowledge graph | `referenced_works`, `cited_by_count` add a new link type `CITES` between literature entities |
| Source diversity / cross-source corroboration weak (FAIR scorer) | Same DOI from multiple sources strengthens corroboration signal |
| MeSH-only ontology | OpenAlex Topics provide a complementary 4,500-term hierarchy with confidence scores |
| Author/institution data thin | ROR IDs unify institutions across sources; ORCID disambiguates authors |
| OA full-text discovery | `best_oa_location.pdf_url` replaces our planned Unpaywall integration |
| Publication impact signal | FWCI gives us a quality dimension for the FAIR scorer |
| Investigator network analysis | Author affiliations + co-authorship strengthens INVESTIGATOR entity type |

### Refresh Mechanism (Recommended)

Two-tier strategy fits the existing scheduler pattern:

**Tier 1 — Daily incremental (lightweight)**
- Add to `CONNECTOR_SCHEDULES` at 03:30 UTC (after PubMed/PMC complete)
- Use `from_updated_date:{yesterday}` filter
- Pulls only new/changed works since last run
- Expected volume: ~500–2,000 records/day for pharma queries
- Time: 1–5 min

**Tier 2 — Weekly full sweep (catches drift)**
- Sunday 04:00 UTC slot (currently free in scheduler)
- Use full concept filter without date restriction
- Catches retroactive metadata updates (citation counts, OA status changes, topic re-tagging)
- Time: 30–60 min

**Storage strategy:**
- LITERATURE table — extend with `openalex_id`, `cited_by_count`, `fwci`, `topics JSONB`, `concepts JSONB`
- New CITATION link type in `entity_links` (source=literature, target=literature, link_type=CITES)
- INSTITUTION as new entity type with ROR ID
- Keep full text out of Postgres — store OA URL only, fetch lazily when needed

### Coverage Estimate

If we target the same 41 PubMed search queries via OpenAlex pharma concepts:

| Source | Current Articles | After OpenAlex |
|--------|-----------------|---------------|
| Direct article metadata | ~2,000 (PubMed) | ~50,000+ (OpenAlex) |
| Full text available | ~500 (PMC OA) | ~15,000 (PMC + other OA via OpenAlex) |
| With citation context | 0 | ~50,000 |
| With FWCI quality score | 0 | ~50,000 |
| With author institution (ROR) | ~50% | ~95% |

This is a **25× expansion** of the literature base with richer per-record metadata.

### Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Storage explosion in already-fragile DB | Extend existing literature table, store full text URLs only (not the text), use JSONB for topics/concepts |
| Duplicate records (same paper from PubMed + OpenAlex) | Use DOI as primary dedup key in entity_consolidator; OpenAlex DOIs match PubMed DOIs |
| Citation graph blowout (50K papers × ~30 refs each = 1.5M links) | Only store CITES links between papers in our corpus, not external citations |
| API changes / rate limit breaches | Use polite pool with mailto, add 0.1s sleep between requests |
| Topic taxonomy drift | OpenAlex updates Topics quarterly; refresh tag mappings on weekly sweep |

---

## Part 4: Pipeline Strengthening — Synthesis from Lead's Review

The lead's architecture review (`lead_notes_4_dev.md`) scored the platform **7.8/10 overall** with specific recommendations. Here's how to address them, sequenced by impact and effort:

### Top 3 Highest-Leverage Changes

**1. Wire the CTX ContextGuard (Section 7.3) — Highest Single-Change Impact**
- The pre-generation context guard exists in `services/ctx_pipeline.py` (`check_response`) but is opt-in only via `MZ_UNIFIED_HANDLER=true`
- Currently hallucination prevention is post-hoc (`validate_citations` strips bad citations after generation)
- **Action**: Make UnifiedChatHandler the default. Set `MZ_UNIFIED_HANDLER=true` in production, monitor telemetry for regressions.
- **Effort**: 1 day. **Impact**: Eliminates a class of hallucinations entirely.

**2. Calibrate Link Confidence (Section 7.2)**
- Currently most links get 1.0 confidence regardless of how they were discovered (logs confirm this)
- **Action**: Update `cross_linker.py` and `entity_resolver.py` to set:
  - `exact_id` → 1.0
  - `entity_resolution` → resolution score (already computed)
  - `mesh_term` → 0.9
  - `llm_extracted` → 0.6–0.8
  - `user_tagged` → 0.95
- Add `min_confidence` parameter to `traverse_graph()` SQL function
- Filter evidence retrieval by confidence threshold
- **Effort**: 2–3 days. **Impact**: Better evidence quality, agents can reason about reliability.

**3. Close the Dark Data Gap (Section 7.1)**
- USER_DOCUMENT and USER_URL source types exist in the enum but no connector
- **Action**: Build `connectors/user_document.py` that:
  - Accepts PDF/DOCX/HTML uploads via new `/upload` endpoint
  - Extracts text with `pdfplumber` (PDFs), `python-docx` (Word), `BeautifulSoup` (HTML)
  - Chunks at 500 tokens with 50-token overlap (matches existing pattern)
  - Adds an LLM-based NER stage between normalize and entity_resolve to identify drug/company/trial mentions
- **Effort**: 1 week. **Impact**: Unlocks the platform's "ingest any pharma document" promise.

### Medium-Priority Strengthening

**4. Temporal Graph Queries (Section 7.4)**
- Add `valid_from`, `valid_until` columns to `entity_links` (migration 016)
- Update `cross_linker.py` to set `valid_from = retrieved_at`
- Extend `traverse_graph()` with `as_of_date` parameter
- Enables: "who owned this drug in 2020?", "competitive landscape 3 years ago"
- **Effort**: 3–4 days

**5. Conflict Resolution Policies for Entity Consolidation (Section 3.3)**
- Today: when sources disagree (e.g., FDA says approval Jan 2024, CT.gov says Feb 2024), system picks arbitrarily
- **Action**: Add a `field_authority_map` to domain pack:
  ```python
  drug_field_authority = {
      "approval_date": ["fda_orange_book", "openfda_labels", "clinical_trials_gov"],
      "generic_name": ["fda_orange_book", "rxnorm", "openfda_labels"],
      "company_id": ["fda_orange_book", "sec_edgar", "clinical_trials_gov"],
  }
  ```
- Consolidator picks value from highest-priority source available
- **Effort**: 2 days

**6. Pre-Store Quality Gating (Section 3.2)**
- Currently quality engine runs post-ingestion — bad records enter DB then get flagged
- **Action**: Move critical rules (e.g., "drug must have generic_name", "trial must have NCT ID") to PRE_STORE hook to reject before insertion
- **Effort**: 2–3 days

### Long-Term Strengthening

**7. Supplement MeSH with ATC, RxNorm, SNOMED (Section 7.6)**
- Add new connectors for ATC (drug classification by anatomy/therapeutic class) and RxNorm (normalized US drug names)
- These improve entity resolution for drugs and add hierarchical reasoning
- **Effort**: 1 week per terminology

**8. Source Diversity → Cross-Source Corroboration (Section 1.2)**
- Current FAIR metric measures whether entity has links to 2+ types
- Better metric: same fact corroborated by 2+ independent data sources
- **Action**: Add `corroboration_count` column to `data_quality_results`, compute via JOIN across source-tagged claims
- **Effort**: 3–4 days

**9. Schema Drift Cleanup (from crash logs)**
The DB crash logs revealed code referencing tables/columns that don't exist:
- `agent_sessions`, `agent_events` (Data Steward harness)
- `steward_actions.details`, `market_events.primary_entity_id`
- `clinical_trials.label`, `etl_runs.source_type`
- **Action**: Create migration 015 to add missing tables/columns, OR fix code to match existing schema
- **Effort**: 1 day. **Impact**: Stops the noise from steward error logs, lets the steward actually do work.

### How OpenAlex Reinforces Multiple Lead Recommendations

OpenAlex is rare in that it directly improves 4 of the 6 lead recommendations:

| Lead Recommendation | How OpenAlex Helps |
|---------------------|-------------------|
| 7.2 Calibrate link confidence | OpenAlex provides topic relevance scores (0.0–1.0) usable as confidence signal |
| 7.4 Temporal graph queries | OpenAlex `created_date`, `updated_date` give versioned metadata for free |
| 7.6 Supplement MeSH | OpenAlex Topics complement MeSH with ML-derived hierarchy |
| 7.5 Expand agent tool registry | New tools possible: `find_citing_papers`, `get_author_h_index`, `find_collaborators` |

This makes OpenAlex the **best ROI item to add to the roadmap** — it ships meaningful value AND multiplies the impact of other planned work.

---

## Final Summary

| # | Issue | Priority | Effort | Status |
|---|-------|----------|--------|--------|
| 1 | DB crash loop — needs proper redeploy + 20 GB volume | P0 | 1 hour | **Blocking everything** |
| 2 | Schema drift (missing tables/columns) | P1 | 1 day | Causing log noise + no-op steward runs |
| 3 | Wire CTX ContextGuard as default | P1 | 1 day | Highest hallucination-quality leverage |
| 4 | OpenAlex connector | P1 | 3–5 days | 25× literature expansion + citation graph |
| 5 | Calibrate link confidence | P2 | 2–3 days | Better evidence quality |
| 6 | Document upload connector + NER | P2 | 1 week | Unlocks dark data story |
| 7 | Temporal graph queries | P3 | 3–4 days | Historical analysis capability |
| 8 | Conflict resolution for consolidator | P3 | 2 days | Cleaner data when sources disagree |
| 9 | Pre-store quality gating | P3 | 2–3 days | Prevent bad data entering DB |
| 10 | ATC / RxNorm / SNOMED | P4 | 2–3 weeks | Long-term ontology depth |

**Recommended sprint order:**
- **This week**: #1 (fix DB), #2 (schema drift), #3 (CTX guard default)
- **Next 2 weeks**: #4 (OpenAlex), #5 (link confidence)
- **Following month**: #6 (dark data), #7 (temporal), #8 (conflicts), #9 (gating)

**The OpenAlex addition is genuinely strategic**: it directly addresses citation graph gap (currently 0% coverage), replaces planned Unpaywall work, multiplies pipeline strengthening recommendations, and gives 25× literature expansion at zero API cost. After fixing the DB, this should be the next major investment.
