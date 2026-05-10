# SPEC-003: Deterministic Data Enrichment Module

> **Status**: Draft
> **Priority**: P1
> **LLM Cost**: Near-zero (all deterministic API calls)
> **Dependencies**: Existing connectors, entity_resolver, domain pack

---

## Problem Statement

The knowledge graph has critical data gaps that reduce analytical value:

| Gap | Impact | Current State |
|---|---|---|
| **Patent data** | Can't analyze patent cliffs, generic entry timing, IP strategy | Table exists, 0 rows |
| **Company enrichment** | Can't link SEC filings, track M&A, identify parent companies | ~0% have CIK/ticker |
| **Unresolved entities** | 42K orphaned entities from auto-create without normalization | MentionNormalizer now wired but backlog unprocessed |
| **Drug completeness** | Missing brand names, dosage forms, approval dates | ~40% complete |
| **Stale records** | Some sources haven't been re-fetched in 30+ days | No auto-refresh |

**FAIR score: 4.7/10 (target 8.5)**

All of these gaps can be filled with **deterministic API calls** — no LLM required.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Enrichment Scheduler (nightly or on-demand)                 │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Patent   │  │ Company  │  │ Resolution│  │ Drug     │   │
│  │ Enricher │  │ Enricher │  │ Sweep     │  │ Backfill │   │
│  └────┬─────┘  └────┬─────┘  └────┬──────┘  └────┬─────┘   │
│       │              │              │              │         │
│       ▼              ▼              ▼              ▼         │
│  FDA Orange    SEC EDGAR      Unresolved      DailyMed      │
│  Book Bulk     CIK Lookup     Queue           API           │
│  Download      (free API)     (internal)      (free)        │
│       │              │              │              │         │
│       ▼              ▼              ▼              ▼         │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  knowledge_store.py → PostgreSQL                      │   │
│  │  + entity_links (new patent/company links)            │   │
│  │  + resolution_audit (sweep results)                   │   │
│  │  + data_quality_results (FAIR score update)           │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  Quality Gate: FAIR delta ≥ 0 per batch, zero false links    │
└─────────────────────────────────────────────────────────────┘
```

---

## Module 1: Patent Enricher

### Source
FDA Orange Book bulk data download (updated monthly):
- URL: `https://www.fda.gov/drugs/drug-approvals-and-databases/orange-book-data-files`
- Format: ZIP containing `patent.txt` (pipe-delimited)
- Fields: Appl_No, Product_No, Patent_No, Patent_Expire_Date_Text, Drug_Substance_Flag, Drug_Product_Flag, Patent_Use_Code, Delist_Flag

### Implementation

```python
# connectors/patent_enricher.py

class PatentEnricher:
    """Populate patents table from FDA Orange Book bulk download."""

    ORANGE_BOOK_URL = "https://www.fda.gov/media/76860/download"

    def fetch_patents(self) -> list[dict]:
        """Download and parse Orange Book patent.txt."""
        # 1. Download ZIP
        # 2. Extract patent.txt
        # 3. Parse pipe-delimited rows
        # 4. Return list of {patent_number, expiry_date, nda_number, substance_flag, product_flag}

    def enrich(self, db: Database) -> EnrichmentResult:
        """Match patents to drugs via NDA number, populate patents table."""
        patents = self.fetch_patents()
        matched = 0
        for patent in patents:
            # Look up drug by nda_number
            drug = db.fetch_one(
                "SELECT id FROM drugs WHERE nda_number = %s",
                [patent['nda_number']]
            )
            if drug:
                # Upsert patent
                db.execute("""
                    INSERT INTO patents (patent_number, patent_expiry_date, applicant_holder, drug_id)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (patent_number) DO UPDATE
                    SET patent_expiry_date = EXCLUDED.patent_expiry_date
                """, [patent['patent_number'], patent['expiry_date'], patent.get('holder', ''), drug['id']])
                # Create entity link
                db.execute("""
                    INSERT INTO entity_links (source_entity_id, source_entity_type, target_entity_id, target_entity_type, link_type, confidence)
                    VALUES (%s, 'drug', %s, 'patent', 'HAS_PATENT', 1.0)
                    ON CONFLICT DO NOTHING
                """, [drug['id'], patent['patent_number']])
                matched += 1
        return EnrichmentResult(total=len(patents), matched=matched, source='fda_orange_book_bulk')
```

### Expected Impact
- **Records**: ~30,000 patents
- **Links**: ~15,000 drug→patent links
- **FAIR improvement**: +0.5 on patent dimension
- **LLM cost**: $0.00 (pure HTTP + CSV parsing)

### Quality Gates
- Patent numbers must match regex `^\d{6,8}$`
- Expiry dates must be valid future or recent past dates
- NDA numbers must match existing drugs (no orphan patents)

---

## Module 2: Company Enricher

### Source
SEC EDGAR Company Search API (free, no key required):
- URL: `https://efts.sec.gov/LATEST/search-index?q={company_name}&dateRange=custom&startdt=2020-01-01&enddt=2026-12-31`
- Also: `https://www.sec.gov/cgi-bin/browse-edgar?company={name}&CIK=&type=10-K&dateb=&owner=include&count=1&search_text=&action=getcompany`
- Returns: CIK, ticker, SIC code, state, filings

### Implementation

```python
# connectors/company_enricher.py

class CompanyEnricher:
    """Enrich companies with SEC EDGAR CIK, ticker, and SIC code."""

    EDGAR_COMPANY_URL = "https://efts.sec.gov/LATEST/search-index"
    EDGAR_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

    def fetch_ticker_map(self) -> dict[str, dict]:
        """Download SEC ticker→CIK mapping (single JSON file, ~2MB)."""
        # Returns {company_name_lower: {cik, ticker, title}}

    def enrich(self, db: Database) -> EnrichmentResult:
        """Match companies to SEC EDGAR CIK/ticker."""
        ticker_map = self.fetch_ticker_map()
        companies = db.fetch_all("SELECT id, company_name FROM companies WHERE cik IS NULL OR cik = ''")
        matched = 0
        for company in companies:
            name = company['company_name'].lower().strip()
            # Try exact match first
            match = ticker_map.get(name)
            if not match:
                # Try fuzzy: remove Inc/Corp/Ltd suffixes
                cleaned = re.sub(r'\s*(inc\.?|corp\.?|ltd\.?|plc|co\.?|llc)\s*$', '', name, flags=re.I).strip()
                match = ticker_map.get(cleaned)
            if match:
                db.execute("""
                    UPDATE companies SET cik = %s, ticker = %s
                    WHERE id = %s AND (cik IS NULL OR cik = '')
                """, [str(match['cik']), match['ticker'], company['id']])
                matched += 1
        return EnrichmentResult(total=len(companies), matched=matched, source='sec_edgar_tickers')
```

### Expected Impact
- **Companies enriched**: ~200-400 (of 1,422 total)
- **Fields populated**: CIK, ticker symbol
- **FAIR improvement**: +1.0 on company enrichment dimension
- **LLM cost**: $0.00 (single JSON download + string matching)

### Quality Gates
- CIK must be numeric, 7-10 digits
- Ticker must be 1-5 uppercase letters
- No CIK assigned to multiple companies (uniqueness check)

---

## Module 3: Resolution Sweep

### Source
Internal — re-process `unresolved_entities` table against current database.

### Implementation

```python
# connectors/resolution_sweep.py

class ResolutionSweep:
    """Clear unresolved entity backlog by re-running resolution against current DB."""

    def sweep(self, db: Database, entity_resolver, batch_size=500) -> EnrichmentResult:
        """Process unresolved entities in batches."""
        unresolved = db.fetch_all("""
            SELECT id, entity_type, raw_value, suggested_match_id, similarity_score
            FROM unresolved_entities
            WHERE status = 'pending'
            ORDER BY similarity_score DESC NULLS LAST
            LIMIT %s
        """, [batch_size])

        resolved = 0
        for entry in unresolved:
            # Re-run entity resolver with current DB state
            result = entity_resolver.resolve(
                entity_type=entry['entity_type'],
                raw_value=entry['raw_value'],
                source='resolution_sweep',
            )
            if result and result.get('entity_id'):
                # Mark as resolved
                db.execute("""
                    UPDATE unresolved_entities
                    SET status = 'resolved', resolved_entity_id = %s, resolved_at = NOW()
                    WHERE id = %s
                """, [result['entity_id'], entry['id']])
                resolved += 1
            else:
                # Update attempt count
                db.execute("""
                    UPDATE unresolved_entities
                    SET attempt_count = attempt_count + 1, last_attempted = NOW()
                    WHERE id = %s
                """, [entry['id']])

        return EnrichmentResult(total=len(unresolved), matched=resolved, source='resolution_sweep')
```

### Expected Impact
- **Queue**: 42K unresolved → estimated 60-80% resolvable with MentionNormalizer
- **Links created**: ~25K new entity_links
- **FAIR improvement**: +2.0 on entity resolution dimension
- **LLM cost**: $0.00 for exact/fuzzy/alias matches; ~$0.50 for LLM fallback on ambiguous cases

### Quality Gates
- No resolution with confidence < 0.4
- Audit trail for every resolution decision
- Max 3 attempts per entity (prevent infinite loops)
- Batch size capped at 500 to control DB load

---

## Module 4: Drug Completeness Backfill

### Source
DailyMed API (NLM, free):
- URL: `https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json?drug_name={name}`
- Returns: brand names, dosage forms, routes, active ingredients, labeler (company)

### Implementation

```python
# connectors/drug_backfill.py

class DrugBackfill:
    """Enrich drug records with DailyMed data (brand names, dosage forms)."""

    DAILYMED_URL = "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json"

    def enrich(self, db: Database) -> EnrichmentResult:
        """Find drugs missing brand_name or dosage_form, fill from DailyMed."""
        drugs = db.fetch_all("""
            SELECT id, generic_name FROM drugs
            WHERE (brand_name IS NULL OR brand_name = '')
            AND generic_name IS NOT NULL
            LIMIT 200
        """)
        enriched = 0
        for drug in drugs:
            data = self._fetch_dailymed(drug['generic_name'])
            if data:
                db.execute("""
                    UPDATE drugs SET brand_name = %s
                    WHERE id = %s AND (brand_name IS NULL OR brand_name = '')
                """, [data.get('brand_name', ''), drug['id']])
                enriched += 1
        return EnrichmentResult(total=len(drugs), matched=enriched, source='dailymed')
```

### Expected Impact
- **Drugs enriched**: ~500-800 (of 1,672 total missing brand names)
- **FAIR improvement**: +0.5 on drug completeness dimension
- **LLM cost**: $0.00 (REST API calls)

---

## Module 5: Source Refresh

### Source
Re-run existing connectors on stale records.

### Implementation

```python
# connectors/source_refresh.py

class SourceRefresh:
    """Re-fetch stale records from existing connectors."""

    STALENESS_THRESHOLD_DAYS = 30

    def identify_stale(self, db: Database) -> list[dict]:
        """Find sources with records older than threshold."""
        return db.fetch_all("""
            SELECT source, COUNT(*) as stale_count,
                   MIN(last_retrieved) as oldest
            FROM (
                SELECT 'clinical_trials_gov' as source, updated_at as last_retrieved FROM clinical_trials
                UNION ALL
                SELECT 'pubmed', retrieved_at FROM pubmed_articles
                UNION ALL
                SELECT 'fda_shortages', retrieved_at FROM market_events WHERE source = 'fda_shortages'
            ) sub
            WHERE last_retrieved < NOW() - INTERVAL '%s days'
            GROUP BY source
            ORDER BY stale_count DESC
        """ % self.STALENESS_THRESHOLD_DAYS)
```

### Expected Impact
- **Freshness**: All sources within 30 days
- **FAIR improvement**: +0.3 on freshness dimension
- **LLM cost**: $0.00

---

## Orchestration

### Enrichment Runner

```python
# connectors/enrichment_runner.py

@dataclass
class EnrichmentResult:
    total: int
    matched: int
    source: str
    errors: int = 0
    fair_delta: float = 0.0

class EnrichmentRunner:
    """Orchestrates all enrichment modules in priority order."""

    def run_all(self, db: Database) -> list[EnrichmentResult]:
        results = []

        # Priority 1: Resolution sweep (highest FAIR impact)
        results.append(ResolutionSweep().sweep(db, entity_resolver, batch_size=500))

        # Priority 2: Patent enrichment
        results.append(PatentEnricher().enrich(db))

        # Priority 3: Company CIK/ticker
        results.append(CompanyEnricher().enrich(db))

        # Priority 4: Drug brand names
        results.append(DrugBackfill().enrich(db))

        # Priority 5: Source refresh
        # (run via existing pipeline, not here)

        return results
```

### API Endpoint

```python
# In api/routes/chat.py or new api/routes/enrichment.py

@router.post("/enrichment/run")
def run_enrichment(db: Database = Depends(get_db)):
    """Trigger enrichment pipeline. Returns results summary."""
    runner = EnrichmentRunner()
    results = runner.run_all(db)
    return {
        "results": [asdict(r) for r in results],
        "total_enriched": sum(r.matched for r in results),
    }
```

### Scheduler Integration

```python
# In scheduler/runner.py

def schedule_enrichment():
    """Run enrichment nightly at 2 AM."""
    scheduler.add_job(
        run_enrichment_job,
        trigger='cron',
        hour=2,
        minute=0,
        id='nightly_enrichment',
    )
```

---

## Expected FAIR Impact

| Module | FAIR Dimension | Before | After | Delta |
|---|---|---|---|---|
| Resolution Sweep | Entity Resolution | 0.1 | 4.0 | +3.9 |
| Patent Enricher | Patent Data | 0.0 | 5.0 | +5.0 |
| Company Enricher | Company Enrichment | 0.0 | 3.0 | +3.0 |
| Drug Backfill | Drug Completeness | 0.4 | 3.0 | +2.6 |
| Source Refresh | Freshness | OK | OK | +0.3 |
| **Total weighted** | **Overall FAIR** | **4.7** | **~7.5** | **+2.8** |

**Estimated total LLM cost: < $1.00** (only for ambiguous entity resolution fallback)
**Estimated total API cost: $0.00** (all free public APIs)
**Estimated runtime: ~30 minutes** (network-bound, not compute-bound)

---

## Quality Gates (per run)

```
✅ FAIR score delta ≥ 0 (never decrease quality)
✅ Zero false entity links (confidence ≥ 0.4 required)
✅ All enrichment results logged to data_change_log
✅ Patent numbers validated (regex + date check)
✅ CIK uniqueness (no duplicate assignments)
✅ Resolution audit trail for every decision
✅ Batch size limits respected (500 per sweep)
```

---

## Implementation Order

| Step | Module | Effort | Depends On |
|---|---|---|---|
| 1 | EnrichmentResult dataclass + EnrichmentRunner | 30 min | — |
| 2 | ResolutionSweep | 1 hour | MentionNormalizer (done) |
| 3 | PatentEnricher | 1.5 hours | Orange Book URL |
| 4 | CompanyEnricher | 1 hour | SEC tickers JSON |
| 5 | DrugBackfill | 1 hour | DailyMed API |
| 6 | POST /enrichment/run endpoint | 30 min | Steps 1-5 |
| 7 | Scheduler integration | 30 min | Step 6 |
| 8 | FAIR score re-evaluation | 30 min | Step 7 |

**Total: ~7 hours**
