# Market Zero — Intelligence Layer Remediation Spec

**Date:** 19 April 2026
**Classification:** Engineering Spec — Implementation-Ready
**Audience:** Dev team (backend + frontend)
**Scope:** End-to-end intelligence layer rebuild — entity canonicalisation, intent parsing, retrieval orchestration, provenance, numeric guardrails, cross-turn consistency, eval harness

---

## 1. Executive Summary

A live transcript of Market Zero answering pharma intelligence questions was reviewed by a domain expert. The verdict: the system performs worse than a vanilla LLM on the very dimensions it should win on. Seven failure modes were identified, all traceable to specific code paths. This spec defines seven workstreams to remediate them, with exact file paths, function signatures, SQL changes, test requirements, and acceptance criteria.

**The core problem is not the LLM.** The retrieval, entity resolution, and orchestration layers underneath are broken. The LLM is generating confident prose on top of failed lookups and sparse data. Every workstream in this spec addresses infrastructure beneath the synthesis layer.

### Failure Modes Observed

| # | Failure | Root Cause | Workstream |
|---|---------|-----------|------------|
| F1 | "Show pipeline for Ozempic" → no data | `resolve_entity()` searches only `drugs.generic_name`, never `brand_name` | WS-1 |
| F2 | "What Phase 3 trials does what are the side effects of mounjaro have?" | `generate_followups()` embeds raw regex-extracted text into templates with no validation | WS-2, WS-6 |
| F3 | Trial count contradicts across turns (2, then 3, then 8) | No cross-turn numeric tracking; MV vs real-time fallback produces different aggregates | WS-5 |
| F4 | "2.5x stronger pipeline score of 5.0 vs 2.0" when real-world answer is the opposite | LLM editorialises sparse data; no coverage diagnostic flags 2-of-300 trials as low recall | WS-3, WS-4 |
| F5 | No per-claim provenance (NCT IDs, PMIDs) | Citations are `[N]` indices into evidence array, not source identifiers | WS-4 |
| F6 | "What is your ERD" → ignored, answered about semaglutide | Intent cascade has no meta/system intent; regex grabs "semaglutide" and routes to DOSSIER | WS-2 |
| F7 | Brand/generic synonyms not resolved (Ozempic≠semaglutide, Mounjaro≠tirzepatide) | No brand→INN mapping anywhere: not in mention_normalizer, not in fuzzy_match_fields, not in entity_aliases seed data | WS-1 |

---

## 2. Architecture Context

### Current Entity Name Flow (10 passage points)

Understanding where entity names travel is critical — a fix at the wrong point won't propagate.

```
HTTP POST /chat
  │
  ├─ [PP1] resolve_followup_question() — extracts prior topic from bold text in assistant messages
  │    └─ services/chat_handlers/context.py:52-110
  │
  ├─ [PP2] detect_intent(resolved_question) — regex extracts entity names into params dict
  │    └─ services/chat_handlers/intent.py:48-170
  │
  ├─ [PP3] BRANCH: unified_handler.handle() OR legacy handler dispatch
  │    │
  │    ├─ UNIFIED PATH:
  │    │   ├─ [PP4] CTXQueryPipeline.understand() → plan.entities_detected
  │    │   ├─ [PP5] _fetch_metrics(plan) → entity names → metrics_svc methods
  │    │   └─ [PP6] llm.synthesize_comparison(entity_names=plan.entities_detected)
  │    │
  │    └─ LEGACY PATH:
  │        └─ [PP7] handle_dossier/compare/landscape/etc(params) → entity names in params dict
  │
  ├─ [PP8] generate_followups(question, intent, narrative, params) — entity names in templates
  │
  ├─ [PP9] log_query_event() — entity names from payload → telemetry → steward signals
  │
  └─ [PP10] CTXContextBuilder.build(entity_info=...) — entity names baked into LLM context
```

**The canonical resolution point must be before PP2.** If entity names are wrong at intent detection, every downstream consumer inherits the error.

### Current Resolution Stack

```
User input: "ozempic"
  ↓
  mention_normalizer.normalize_drug_mention()     → "ozempic" (strips ™/® only, no brand→INN)
  ↓
  resolve_entity("ozempic", "", db)               → searches drugs.generic_name only → NULL
  ↓
  detect_intent() regex                           → extracts "ozempic" as entity_name
  ↓
  handle_dossier(params={"entity_name": "ozempic"})
  ↓
  engine.entity_dossier(entity_id=None)           → no data
  ↓
  llm.synthesize_dossier(fallback_narrative="No data available")
```

---

## 3. Workstream 1 — Entity Canonicalisation Service

### 3.1 Problem

Five layers fail to resolve brand names to INN:

1. **`mention_normalizer.py`** (L67-118): No `BRAND_TO_INN` dictionary. Strips dosage forms but leaves "ozempic" as-is.
2. **`pack.py`** (L38-56): `fuzzy_match_fields` only maps `{"generic_name": "generic_name"}`. The `brand_name` column is a recommended field but never searched.
3. **`entity_resolver.py`** (L104-110): `FUZZY_MATCH_FIELDS` dict has no `brand_name` entry. Fuzzy strategy (L324-364) and embedding strategy (L370-412) both query only `generic_name`.
4. **`formatting.py`** (L69-124): `resolve_entity()` hardcodes `table_map = {"drug": ("drugs", "generic_name")}`. Exact match (L109-114) and LIKE match (L117-122) both search only `generic_name`.
5. **`entity_aliases`** table (migration 003): Created with zero rows. No seed data for brand→INN mappings.

### 3.2 Design

Create a **canonicalisation layer** that sits before intent detection and resolves all drug name variants to a canonical form. This is not a simple dictionary — it must handle:

- Brand names: Ozempic, Wegovy, Rybelsus → semaglutide
- Code names: LY3298176 → tirzepatide
- Abbreviations: GLP-1 RA → mechanism class (not a drug)
- Combination products: Ozempic + metformin → semaglutide + metformin
- Misspellings: "semgalutide" → semaglutide (fuzzy)
- M&A lineage: Allergan → AbbVie (for companies)

### 3.3 Implementation

#### 3.3.1 Seed migration: `schema/migrations/032_seed_brand_aliases.sql`

```sql
-- Seed entity_aliases from existing drugs.brand_name column
INSERT INTO entity_aliases (entity_type, entity_id, alias_text, source_type, confidence, verified)
SELECT 'drug', d.id, LOWER(TRIM(d.brand_name)), 'fda_orange_book', 1.0, TRUE
FROM drugs d
WHERE d.brand_name IS NOT NULL
  AND TRIM(d.brand_name) != ''
  AND LOWER(TRIM(d.brand_name)) != LOWER(TRIM(d.generic_name))
ON CONFLICT DO NOTHING;

-- Seed company aliases from known M&A (manual curation list)
-- Add rows for: Allergan→AbbVie, Celgene→BMS, Shire→Takeda, etc.
-- This should be a curated CSV loaded via COPY or INSERT
```

**Acceptance:** After migration, `SELECT COUNT(*) FROM entity_aliases WHERE entity_type = 'drug'` returns > 0 rows. Every drug with a non-null `brand_name` has an alias entry.

#### 3.3.2 New service: `services/entity_canonicalizer.py`

```python
class EntityCanonicalizer:
    """Resolves any drug/company name variant to canonical (entity_id, canonical_name, entity_type).
    
    Called BEFORE intent detection. Does not create entities — only resolves to existing ones.
    Resolution order: exact generic_name → exact brand_name → alias table → fuzzy generic → fuzzy brand → embedding.
    """
    
    def __init__(self, db: Database) -> None:
        self._db = db
        self._cache: dict[str, CanonicalResult | None] = {}  # LRU bounded
    
    def canonicalize(self, name: str, hint_type: str = "") -> CanonicalResult | None:
        """Resolve a name to its canonical entity.
        
        Args:
            name: Raw user input (e.g., "Ozempic", "ozmpic", "LY3298176")
            hint_type: Optional entity type hint ("drug", "company", "mechanism")
        
        Returns:
            CanonicalResult(entity_id, canonical_name, entity_type, confidence, method)
            or None if unresolvable.
        """
    
    def canonicalize_batch(self, names: list[str]) -> dict[str, CanonicalResult | None]:
        """Resolve multiple names in one pass (for compare queries)."""
    
    def _exact_generic(self, name: str) -> CanonicalResult | None:
        """SELECT id, generic_name FROM drugs WHERE LOWER(generic_name) = LOWER(%s)"""
    
    def _exact_brand(self, name: str) -> CanonicalResult | None:
        """SELECT id, generic_name FROM drugs WHERE LOWER(brand_name) = LOWER(%s)"""
    
    def _alias_lookup(self, name: str) -> CanonicalResult | None:
        """SELECT entity_id, alias_text FROM entity_aliases 
           WHERE LOWER(alias_text) = LOWER(%s) AND entity_type IN ('drug','company')"""
    
    def _fuzzy_generic(self, name: str) -> CanonicalResult | None:
        """SELECT id, generic_name, similarity(LOWER(generic_name), LOWER(%s)) AS sim
           FROM drugs WHERE similarity(LOWER(generic_name), LOWER(%s)) > 0.4
           ORDER BY sim DESC LIMIT 1"""
    
    def _fuzzy_brand(self, name: str) -> CanonicalResult | None:
        """SELECT id, generic_name, similarity(LOWER(brand_name), LOWER(%s)) AS sim
           FROM drugs WHERE brand_name IS NOT NULL 
           AND similarity(LOWER(brand_name), LOWER(%s)) > 0.4
           ORDER BY sim DESC LIMIT 1"""
    
    def _embedding_lookup(self, name: str) -> CanonicalResult | None:
        """Vector similarity search against molecule_embedding column.
           Only if name length >= 4 and no fuzzy match found."""


@dataclass(frozen=True)
class CanonicalResult:
    entity_id: str
    canonical_name: str      # Always the generic_name / official name
    entity_type: str         # "drug", "company", "mechanism", etc.
    confidence: float        # 1.0 exact, 0.4-0.99 fuzzy, 0.3-0.8 embedding
    method: str              # "exact_generic", "exact_brand", "alias", "fuzzy_generic", etc.
    original_input: str      # What the user typed
```

**Key design decisions:**
- Returns `generic_name` as `canonical_name` always, even when matched via brand. This ensures downstream functions always work with the canonical form.
- Confidence varies by method (exact=1.0, alias=0.95, fuzzy=similarity score, embedding=cosine sim). This feeds into provenance.
- Cache is bounded (LRU, 1000 entries) and cleared on pipeline ingestion events.
- Does NOT create new entities (unlike `EntityResolver._auto_create`). If unresolvable, returns None and the system should say so rather than hallucinate.

#### 3.3.3 Wire into chat route: `api/routes/chat.py`

Insert canonicalisation **before** intent detection (before current line 234):

```python
# NEW: Canonicalise entity names in the question before intent detection
canonicalizer = get_entity_canonicalizer()  # new dep in deps.py
canonical_question, canon_map = _canonicalize_question(
    resolved_question, canonicalizer
)
# canon_map: {"ozempic": CanonicalResult(canonical_name="semaglutide", ...)}
# canonical_question: resolved_question with brand names replaced by canonical names

intent, params = detect_intent(canonical_question)  # now works with canonical names
```

New helper function:

```python
def _canonicalize_question(question: str, canonicalizer: EntityCanonicalizer) -> tuple[str, dict]:
    """Extract potential entity names from question, canonicalise them, replace in text.
    
    Strategy: tokenise on known delimiters (vs, and, compared to), attempt canonicalisation
    on each candidate. Replace only high-confidence matches (>= 0.7).
    
    Returns (canonical_question, map of original→CanonicalResult).
    """
```

#### 3.3.4 Update `resolve_entity()`: `services/chat_handlers/formatting.py`

Replace lines 77-122 to search both `generic_name` AND `brand_name`:

```python
table_map = {
    "drug": [
        ("drugs", "generic_name"),  # primary
        ("drugs", "brand_name"),    # secondary — NEW
    ],
    "company": [("companies", "name")],
    "therapeutic_area": [("therapeutic_areas", "name")],
    "mechanism": [("mechanisms_of_action", "name")],
    "literature": [("pubmed_articles", "title")],
}
```

For each entity type, iterate through column list. Return first match. If matched via `brand_name`, set `label` to the `generic_name` from the same row (canonical form).

#### 3.3.5 Update `FUZZY_MATCH_FIELDS`: `integration/entity_resolver.py`

Add `brand_name` entry at line 104:

```python
FUZZY_MATCH_FIELDS: dict[str, tuple[str, str, str]] = {
    "company_name": ("companies", "name", "company"),
    "generic_name": ("drugs", "generic_name", "drug"),
    "brand_name": ("drugs", "brand_name", "drug"),     # NEW
    "sponsor_name": ("companies", "name", "company"),
    "investigator_name": ("investigators", "name", "investigator"),
}
```

Update `_fuzzy_lookup()` (L324): when matched via `brand_name`, fetch `generic_name` from the same row and use it as the resolved label.

#### 3.3.6 Update `pack.py` drug schema: `domain/pharma/pack.py`

At line 50, add `brand_name` to fuzzy match fields:

```python
fuzzy_match_fields={"generic_name": "generic_name", "brand_name": "brand_name"},
```

### 3.4 Tests Required

| Test | File | What It Asserts |
|------|------|----------------|
| `test_canonicalize_brand_to_inn` | `tests/test_entity_canonicalizer.py` | "Ozempic" → semaglutide, "Mounjaro" → tirzepatide, "Wegovy" → semaglutide |
| `test_canonicalize_code_name` | same | "LY3298176" → tirzepatide (if alias seeded) |
| `test_canonicalize_misspelling` | same | "semgalutide" → semaglutide via fuzzy (sim > 0.4) |
| `test_canonicalize_unknown` | same | "xyznonexistent" → None |
| `test_canonicalize_batch` | same | Multiple names resolved in one call |
| `test_canonicalize_cache_hit` | same | Second call uses cache, no DB query |
| `test_resolve_entity_brand_name` | `tests/test_formatting.py` | `resolve_entity("ozempic", "drug", db)` returns semaglutide entity |
| `test_resolve_entity_generic_name` | same | `resolve_entity("semaglutide", "drug", db)` still works (no regression) |
| `test_fuzzy_match_brand` | `tests/test_entity_resolver.py` | Fuzzy strategy finds drug via `brand_name` column |
| `test_alias_seed_migration` | `tests/test_migrations.py` | After migration 032, alias count > 0 for drugs with brand_name |
| `test_chat_brand_name_e2e` | `tests/test_chat_e2e.py` | POST /chat with "Show pipeline for Ozempic" returns semaglutide data |
| `test_compare_brand_vs_generic` | same | "Compare Ozempic vs tirzepatide" resolves both correctly |

**Minimum: 15 tests.** All must pass before merging.

### 3.5 Acceptance Criteria

- [ ] "Show pipeline for Ozempic" returns semaglutide pipeline data
- [ ] "Compare Mounjaro vs Ozempic" resolves to tirzepatide vs semaglutide comparison
- [ ] "Wegovy side effects" resolves to semaglutide
- [ ] Fuzzy: "semgalutide" resolves to semaglutide with confidence < 1.0
- [ ] Unknown drugs return explicit "entity not found" message, not empty data
- [ ] All existing tests pass (no regression)
- [ ] Benchmark score ≥ 75%

---

## 4. Workstream 2 — Intent & NLU Layer

### 4.1 Problem

The intent detection layer (`intent.py`) uses regex patterns that:

1. **Extract full clause fragments as entity names.** The COMPARE regex (L63) `(.+?)\s+(?:vs\.?|versus|...)` captures "what are the side effects of mounjaro" as an entity when the user types malformed input.
2. **Have no slot validation.** Extracted text is never checked against known entity types, length bounds, or character patterns.
3. **Cannot handle meta/system questions.** "What is your ERD" matches the DOSSIER pattern (L156) `(?:what is)\s+(.+?)` and extracts "your ERD" as an entity name.
4. **Have no clarification fallback.** Ambiguous queries are silently routed to the best-match handler rather than asking the user to clarify.
5. **Cannot detect when the user is asking about the system itself** vs asking about pharma entities.

### 4.2 Design

Add three layers between raw input and handler dispatch:

```
User input
  ↓
  [Layer 1] Meta-intent classifier — is this about the system or about pharma?
  ↓
  [Layer 2] Slot extraction + validation — extract entity names, validate against DB
  ↓
  [Layer 3] Confidence gate — if confidence < threshold, generate clarification
  ↓
  Handler dispatch
```

### 4.3 Implementation

#### 4.3.1 Meta-intent detection: `services/chat_handlers/intent.py`

Add before the existing `detect_intent()` function (before line 48):

```python
_META_PATTERNS = [
    r'\b(?:your|the system|this (?:tool|platform|app)|market zero)\b.*\b(?:erd|schema|architecture|data model|how (?:do|does) (?:it|you)|what (?:data|sources)|capabilities)\b',
    r'\b(?:how (?:do|does)|what (?:can|does)) (?:you|this|it|the system)\b',
    r'\b(?:help|tutorial|guide|documentation|explain yourself)\b',
]

def detect_meta_intent(question: str) -> bool:
    """Returns True if the question is about the system itself, not about pharma entities."""
    q = question.lower().strip()
    return any(re.search(p, q) for p in _META_PATTERNS)
```

Wire into `detect_intent()` at the top:

```python
def detect_intent(question: str) -> tuple[str, dict]:
    q = question.lower().strip()
    
    # NEW: Meta-intent check first
    if detect_meta_intent(q):
        return Intent.GENERAL, {"meta": True, "original_question": question}
    
    # ... existing regex cascade
```

When `params.get("meta")` is True, `handle_general()` should use a system-description prompt instead of pharma retrieval.

#### 4.3.2 Slot validation: `services/chat_handlers/intent.py`

Add a validation function called after every regex extraction:

```python
_MAX_ENTITY_NAME_LENGTH = 60
_ENTITY_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9\s\-\'\.,/&()]+$')
_QUERY_FRAGMENT_INDICATORS = [
    'what', 'how', 'show', 'tell', 'compare', 'which', 'does', 'is', 'are',
    'the full', 'pipeline for', 'landscape for', 'side effects',
]

def _validate_entity_name(name: str) -> str | None:
    """Validate an extracted entity name. Returns cleaned name or None if invalid.
    
    Rejects:
    - Names longer than 60 characters (likely a query fragment)
    - Names containing question words (likely template concatenation)
    - Names with invalid characters
    - Empty or whitespace-only names
    """
    name = name.strip()
    if not name or len(name) > _MAX_ENTITY_NAME_LENGTH:
        return None
    if not _ENTITY_NAME_PATTERN.match(name):
        return None
    name_lower = name.lower()
    # Reject if it looks like a query fragment
    if any(indicator in name_lower for indicator in _QUERY_FRAGMENT_INDICATORS):
        return None
    return name
```

Call this after every regex group extraction. Example for COMPARE (around line 84):

```python
if vs_match:
    e1 = _validate_entity_name(vs_match.group(1))
    e2 = _validate_entity_name(vs_match.group(2))
    if e1 and e2:
        return Intent.COMPARE, {"entities": [e1, e2], ...}
    elif e1:
        return Intent.DOSSIER, {"entity_name": e1, ...}
    else:
        return Intent.GENERAL, {"clarification_needed": True, "original_question": question}
```

#### 4.3.3 Confidence gate: `api/routes/chat.py`

After intent detection, add a confidence check:

```python
intent, params = detect_intent(canonical_question)

# NEW: Confidence gate
if params.get("clarification_needed"):
    return {
        "narrative": f"I wasn't sure which entities you meant. Could you rephrase your question with specific drug or company names?",
        "intent": "clarification",
        "followup_suggestions": [
            "Compare semaglutide vs tirzepatide",
            "Show the pipeline for Keytruda",
            "What is the competitive landscape for GLP-1 drugs?",
        ],
    }
```

#### 4.3.4 Entity existence check before handler dispatch

After canonicalisation and intent detection, verify that extracted entities actually exist in the database before passing to handlers:

```python
# NEW: Verify entities exist before dispatching to handlers
if intent in (Intent.DOSSIER, Intent.COMPARE, Intent.PORTFOLIO):
    entity_names = params.get("entities", []) or [params.get("entity_name", "")]
    verified = []
    missing = []
    for name in entity_names:
        result = canonicalizer.canonicalize(name)
        if result:
            verified.append(result)
        else:
            missing.append(name)
    
    if missing and not verified:
        return {
            "narrative": f"I couldn't find {', '.join(missing)} in the database. Did you mean one of these?",
            "intent": "clarification",
            "suggestions": _suggest_similar_entities(missing, db),
        }
    elif missing:
        # Partial match — proceed with verified, note missing
        params["_unresolved_entities"] = missing
        params["_resolved_entities"] = verified
```

### 4.4 Tests Required

| Test | What It Asserts |
|------|----------------|
| `test_meta_intent_erd` | "What is your ERD" → meta intent, not DOSSIER |
| `test_meta_intent_capabilities` | "What can this system do?" → meta intent |
| `test_meta_intent_false_positive` | "What is semaglutide" → NOT meta (it's a pharma question) |
| `test_validate_entity_rejects_query_fragment` | "what are the side effects of mounjaro" → None |
| `test_validate_entity_accepts_drug` | "semaglutide" → "semaglutide" |
| `test_validate_entity_rejects_long` | 100-char string → None |
| `test_validate_entity_rejects_template` | "show the full" → None |
| `test_confidence_gate_returns_clarification` | Malformed compare query → clarification response |
| `test_entity_existence_check_missing` | Query about nonexistent drug → "not found" with suggestions |
| `test_entity_existence_check_partial` | Compare with 1 known, 1 unknown → proceeds with warning |

**Minimum: 12 tests.**

### 4.5 Acceptance Criteria

- [ ] "What is your ERD" returns a system description, not a pharma dossier
- [ ] "What Phase 3 trials does what are the side effects of mounjaro have?" is impossible to generate as a follow-up
- [ ] Malformed queries get a clarification response with example queries
- [ ] Queries about nonexistent entities get "not found" with similar-entity suggestions
- [ ] All existing intent detection tests pass (no regression in valid queries)

---

## 5. Workstream 3 — Retrieval Orchestration with Coverage Diagnostics

### 5.1 Problem

The system found 2 trials for semaglutide (which has 300+ on ClinicalTrials.gov) and built a comparative verdict on top of it. No coverage diagnostic was surfaced. The user has no way to know the answer is based on 0.7% of available data.

Two sub-problems:

1. **No recall estimation.** The system doesn't know or report what fraction of available data it retrieved.
2. **Verdict generation from sparse data.** The LLM generates comparative conclusions ("Semaglutide is better positioned") from statistically meaningless sample sizes.

### 5.2 Design

Add a **CoverageDiagnostic** that runs after retrieval and before synthesis. It estimates data completeness per entity and per source, and injects coverage warnings into the LLM context.

### 5.3 Implementation

#### 5.3.1 New class: `services/coverage_diagnostic.py`

```python
@dataclass(frozen=True)
class CoverageReport:
    entity_name: str
    entity_type: str
    local_count: int          # trials/articles/etc. in our DB
    estimated_universe: int   # estimated total from source APIs (cached)
    coverage_pct: float       # local_count / estimated_universe
    sources_queried: list[str]
    sources_missing: list[str]
    staleness_days: int       # days since last refresh for this entity
    confidence_label: str     # "high" (>60%), "moderate" (20-60%), "low" (<20%), "unknown"


class CoverageDiagnostic:
    """Estimates data completeness for entities in a query."""
    
    def __init__(self, db: Database, config: AppConfig) -> None:
        self._db = db
        self._config = config
    
    def assess(self, entity_id: str, entity_type: str, entity_name: str) -> CoverageReport:
        """Estimate coverage for a single entity.
        
        For drugs: count local trials, compare against ClinicalTrials.gov API count.
        For companies: count local filings, compare against SEC EDGAR count.
        For literature: count local articles, compare against PubMed count.
        """
    
    def assess_batch(self, entities: list[dict]) -> list[CoverageReport]:
        """Assess coverage for multiple entities."""
    
    def format_warning(self, reports: list[CoverageReport]) -> str:
        """Generate a human-readable coverage warning for injection into LLM context.
        
        Example output:
        "[COVERAGE WARNING] Semaglutide: 8 trials in database vs ~320 on ClinicalTrials.gov 
        (2.5% coverage). Conclusions based on this data may not reflect the full picture."
        """
    
    def _count_local_trials(self, entity_id: str) -> int:
        """SELECT COUNT(*) FROM clinical_trials ct 
           JOIN entity_links el ON el.target_entity_id = ct.id 
           WHERE el.source_entity_id = %s AND el.source_entity_type = 'drug'"""
    
    def _estimate_universe_trials(self, entity_name: str) -> int:
        """Query ClinicalTrials.gov API for total count. Cache for 24 hours.
           GET https://clinicaltrials.gov/api/v2/studies?query.term={name}&countTotal=true
        """
```

#### 5.3.2 Wire into synthesis flow

In `services/unified_handler.py`, after retrieval and before synthesis (around the `_synthesize` call):

```python
# NEW: Coverage diagnostic
coverage_reports = coverage_diagnostic.assess_batch([
    {"entity_id": e.entity_id, "entity_type": e.entity_type, "name": e.canonical_name}
    for e in resolved_entities
])

coverage_warning = coverage_diagnostic.format_warning(coverage_reports)
if coverage_warning:
    # Inject into LLM context so it can hedge appropriately
    extra_context = f"{extra_context}\n\n{coverage_warning}"
    
    # Also inject into response metadata for frontend display
    payload["coverage"] = [asdict(r) for r in coverage_reports]
```

In legacy handlers (`services/chat_handlers/handlers.py`), add the same pattern to `handle_dossier()`, `handle_compare()`, and `handle_pipeline()`.

#### 5.3.3 LLM system prompt amendment

In `services/llm.py`, update the system prompt (in `_get_system_prompt()`) to include:

```
If a COVERAGE WARNING is present in the context, you MUST:
1. Acknowledge the data limitation in your response
2. NOT draw comparative conclusions when coverage is below 20%
3. State the actual counts (e.g., "Based on 8 of approximately 320 known trials")
4. Suggest the user verify with primary sources for comprehensive analysis
```

#### 5.3.4 Verdict suppression for low-coverage comparisons

In `services/llm.py`, add a pre-synthesis check in `synthesize_comparison()`:

```python
def synthesize_comparison(self, entity_names, metrics_by_entity, ...):
    # NEW: Check if comparison is meaningful
    if metrics_by_entity:
        trial_counts = [m.get("total_trials", 0) for m in metrics_by_entity.values()]
        if all(c < 5 for c in trial_counts):
            # Too sparse for meaningful comparison
            return (
                f"Insufficient data for a reliable comparison. "
                f"Found {' and '.join(str(c) + ' trials' for c in trial_counts)} respectively. "
                f"A meaningful comparison requires broader data coverage."
            )
```

### 5.4 Tests Required

| Test | What It Asserts |
|------|----------------|
| `test_coverage_low_trial_count` | 2 local trials vs 300 estimated → "low" confidence label |
| `test_coverage_high_trial_count` | 200 local vs 300 estimated → "high" confidence label |
| `test_coverage_warning_format` | Warning text includes entity name, counts, and percentage |
| `test_coverage_injected_into_context` | LLM context contains coverage warning when coverage < 60% |
| `test_verdict_suppressed_sparse_data` | Compare with < 5 trials each → no comparative verdict |
| `test_coverage_cache` | Second call within 24h uses cached universe count |
| `test_coverage_unknown_universe` | API unavailable → confidence_label = "unknown" |

**Minimum: 10 tests.**

### 5.5 Acceptance Criteria

- [ ] "Compare semaglutide vs tirzepatide" with sparse data includes coverage caveat
- [ ] Coverage percentage visible in response metadata
- [ ] Comparisons with < 5 trials per entity do not produce "X is better than Y" verdicts
- [ ] Coverage estimates cached (no API call per query)
- [ ] System gracefully handles API unavailability

---

## 6. Workstream 4 — Provenance & Citation System

### 6.1 Problem

Citations are `[N]` indices into an evidence array. They carry no source identifiers (NCT ID, PMID, FDA label version). The user cannot trace any claim to its origin. This is unacceptable for pharma intelligence where regulatory defensibility matters.

Current citation flow:
1. `query_engine.query()` returns `EvidenceItem` objects with `provenance: str` field (L29-38)
2. LLM receives evidence as `evidence_snippets: list[str]` — text only, no IDs
3. LLM generates `[1]`, `[2]` markers referencing array indices
4. `validate_citations()` only checks `1 <= N <= len(evidence)` — no source verification

### 6.2 Design

Restructure evidence to carry structured provenance through the entire pipeline, and require the LLM to cite specific source identifiers.

### 6.3 Implementation

#### 6.3.1 Enrich `EvidenceItem`: `services/query_engine.py`

Update the dataclass (line 29):

```python
@dataclass
class EvidenceItem:
    source: str                    # "search", "graph", "metrics"
    entity_type: str
    entity_id: str
    content: str
    relevance: float
    provenance: str                # existing: source description
    # NEW fields:
    source_id: str = ""            # NCT ID, PMID, FDA app number, SEC CIK, etc.
    source_url: str = ""           # Direct URL to source record
    source_date: str = ""          # Date of source record (ISO 8601)
    source_database: str = ""      # "clinicaltrials.gov", "pubmed", "fda_orange_book", etc.
```

#### 6.3.2 Populate source IDs during retrieval

In `query_engine.query()` (line 121-129), when converting search results to evidence:

```python
for r in search_results:
    evidence.append(EvidenceItem(
        source="search",
        entity_type=r.entity_type,
        entity_id=r.entity_id,
        content=f"{r.title}: {r.snippet}",
        relevance=r.similarity,
        provenance=r.source_api,
        # NEW: extract source identifiers from the record
        source_id=r.metadata.get("nct_id") or r.metadata.get("pmid") or r.metadata.get("nda_number", ""),
        source_url=r.metadata.get("source_url", ""),
        source_date=r.metadata.get("retrieved_at", ""),
        source_database=r.source_api,
    ))
```

This requires that `SearchResult` (from `services/search.py`) carries metadata. Check the existing `SearchResult` dataclass and add a `metadata: dict` field if missing.

#### 6.3.3 Pass structured evidence to LLM: `services/llm.py`

Update `_build_context_block()` to format evidence with source IDs:

```python
def _format_evidence_for_llm(evidence: list[EvidenceItem]) -> str:
    """Format evidence with source identifiers for LLM consumption.
    
    Example output:
    [1] (NCT04816643, ClinicalTrials.gov, 2024-03-15) BARI-STEP trial: Phase 3...
    [2] (PMID:38291234, PubMed, 2024-01-20) Meta-analysis of semaglutide...
    """
    lines = []
    for i, e in enumerate(evidence, 1):
        source_tag = e.source_id or e.source_database or "unattributed"
        date_tag = e.source_date[:10] if e.source_date else "date unknown"
        lines.append(f"[{i}] ({source_tag}, {e.source_database}, {date_tag}) {e.content}")
    return "\n".join(lines)
```

#### 6.3.4 Update system prompt to require source citations

In `_get_system_prompt()`, add:

```
CITATION RULES:
- Every factual claim MUST include a citation in the format [N] where N corresponds to the evidence index.
- When citing trial data, include the NCT ID in your text: "the BARI-STEP trial (NCT04816643) [1]"
- When citing publications, include the PMID: "a 2024 meta-analysis (PMID:38291234) [2]"
- Do NOT make claims that are not supported by the provided evidence.
- If the evidence is insufficient to answer the question, say so explicitly.
```

#### 6.3.5 Update `validate_citations()`: `services/llm.py`

Enhance the validator (line 30) to check source ID presence:

```python
def validate_citations(
    narrative: str, 
    evidence: list[EvidenceItem],  # Changed from evidence_count: int
) -> dict:
    """Validate citations and enrich with source IDs.
    
    Returns:
        {
            "narrative": str,          # cleaned narrative
            "valid": int,              # valid citation count
            "stripped": int,           # removed invalid citations
            "unattributed_claims": int # factual sentences with no citation
        }
    """
```

Add a new check: count sentences containing numbers or specific claims that lack any `[N]` citation. Report as `unattributed_claims`.

#### 6.3.6 Provenance in response payload

Update the response structure in `api/routes/chat.py` to include structured provenance:

```python
payload["data"]["evidence"] = [
    {
        "content": e.content,
        "source_id": e.source_id,
        "source_url": e.source_url,
        "source_database": e.source_database,
        "source_date": e.source_date,
        "relevance": e.relevance,
    }
    for e in evidence_items
]
```

### 6.4 Tests Required

| Test | What It Asserts |
|------|----------------|
| `test_evidence_item_has_source_id` | EvidenceItem from clinical trial search has NCT ID |
| `test_evidence_item_has_pmid` | EvidenceItem from PubMed search has PMID |
| `test_evidence_formatted_with_source` | LLM context contains "(NCT..., ClinicalTrials.gov, date)" |
| `test_validate_citations_counts_unattributed` | Narrative with claims but no [N] → unattributed_claims > 0 |
| `test_response_payload_has_provenance` | /chat response includes source_id and source_url per evidence item |
| `test_provenance_survives_ctx_pipeline` | Evidence through CTX pipeline retains source IDs |

**Minimum: 8 tests.**

### 6.5 Acceptance Criteria

- [ ] Every evidence item in the response carries a source identifier (NCT ID, PMID, NDA number, etc.)
- [ ] LLM narratives include source identifiers inline (not just index numbers)
- [ ] `validate_citations()` reports unattributed factual claims
- [ ] Frontend can render clickable source links from `source_url`
- [ ] No regression in synthesis quality or latency

---

## 7. Workstream 5 — Numeric Guardrails & Cross-Turn Consistency

### 7.1 Problem

The system said semaglutide has 2 trials in one turn, 3 in the next, and 8 in another. Two root causes:

1. **MV vs real-time drift.** `drug_pipeline_strength()` (metrics.py L39-117) uses materialised view `mv_drug_pipeline_strength` but falls back to real-time SQL (L104-115) when MV returns ≤2 rows. The real-time query may aggregate differently.
2. **No cross-turn numeric tracking.** `ConversationMemory` tracks entity mention frequency (`_entity_counts: Counter`) but stores zero numeric properties. It cannot detect that trial counts changed.

### 7.2 Design

Two layers:

1. **Deterministic numeric grounding** — every number in the narrative must trace to a specific DB query result. The LLM cannot invent numbers.
2. **Cross-turn consistency tracking** — conversation memory records numeric claims per entity and flags contradictions.

### 7.3 Implementation

#### 7.3.1 Numeric grounding: `services/llm.py`

Add a post-synthesis validation that extracts all numbers from the narrative and verifies each against source data:

```python
def _ground_numbers(
    narrative: str,
    metrics: dict | None,
    evidence: list[EvidenceItem],
) -> tuple[str, list[str]]:
    """Verify every number in the narrative against source data.
    
    Returns:
        (cleaned_narrative, list of warnings)
    
    For each number found:
    1. Check if it appears in metrics dict (exact match)
    2. Check if it appears in evidence content (exact match)
    3. If not found in either, flag it as ungrounded
    
    Ungrounded numbers are:
    - Wrapped in qualification: "5.0" → "approximately 5"
    - Or removed if they appear to be invented scores
    """
    source_numbers = _extract_source_numbers(metrics, [e.content for e in evidence])
    narrative_numbers = _ALL_NUMBER_RE.findall(narrative)
    
    warnings = []
    for num_str in narrative_numbers:
        num = float(num_str)
        if not any(abs(num - src) < 0.01 for src in source_numbers):
            warnings.append(f"Ungrounded number: {num_str}")
            # Replace bold emphasis on ungrounded numbers
            narrative = narrative.replace(f"**{num_str}**", num_str)
    
    return narrative, warnings
```

Tighten the tolerance in `verify_narrative_numbers()` from ±2.0 to ±0.1 for trial counts and pipeline scores. The current ±2.0 tolerance means "8 trials" passes validation when the source says "6 trials".

#### 7.3.2 MV/real-time consistency: `services/metrics.py`

In `drug_pipeline_strength()`, remove the silent fallback or at minimum ensure both paths produce identical aggregation:

```python
def drug_pipeline_strength(self, drug_id=None, ta_id=None, limit=20):
    # Try materialised view first
    mv_results = self._query_mv("mv_drug_pipeline_strength", ...)
    
    if len(mv_results) <= 2 and (drug_id or ta_id):
        # Fallback to real-time
        rt_results = self._query_realtime_pipeline(drug_id, ta_id, limit)
        
        # NEW: If both available, cross-check
        if mv_results and rt_results:
            mv_count = sum(r["trial_count"] for r in mv_results)
            rt_count = sum(r["trial_count"] for r in rt_results)
            if mv_count != rt_count:
                logger.warning(
                    "MV/RT trial count mismatch: mv=%d rt=%d entity=%s",
                    mv_count, rt_count, drug_id or ta_id,
                )
        
        return rt_results
    return mv_results
```

#### 7.3.3 Cross-turn numeric tracking: `services/conversation_memory.py`

Extend `_Exchange` dataclass and tracking:

```python
@dataclass
class _Exchange:
    turn: int
    question: str
    response: str
    intent: str
    entities: list[str]
    # NEW:
    numeric_claims: dict[str, dict[str, float]]  
    # e.g., {"semaglutide": {"total_trials": 8, "phase3_trials": 3, "pipeline_score": 5.0}}
```

Update `add_exchange()` to extract and store numeric claims:

```python
def add_exchange(self, question, response, intent="", entities=None, metrics=None):
    # NEW: Extract numeric claims from metrics for tracked entities
    numeric_claims = {}
    if metrics and entities:
        for entity in entities:
            entity_metrics = metrics.get(entity, {})
            if entity_metrics:
                numeric_claims[entity] = {
                    k: v for k, v in entity_metrics.items() 
                    if isinstance(v, (int, float))
                }
    
    exchange = _Exchange(
        turn=self._turn_counter,
        question=question,
        response=response,
        intent=intent,
        entities=entities or [],
        numeric_claims=numeric_claims,
    )
```

Add contradiction detection:

```python
def check_consistency(self, entity: str, new_metrics: dict[str, float]) -> list[str]:
    """Check if new numeric claims contradict prior claims for the same entity.
    
    Returns list of contradiction warnings, e.g.:
    ["semaglutide total_trials changed from 2 (turn 1) to 8 (turn 3)"]
    """
    warnings = []
    for exchange in reversed(self._exchanges):
        prior = exchange.numeric_claims.get(entity, {})
        for key, prior_val in prior.items():
            new_val = new_metrics.get(key)
            if new_val is not None and prior_val != new_val:
                warnings.append(
                    f"{entity} {key} changed from {prior_val} (turn {exchange.turn}) "
                    f"to {new_val} (turn {self._turn_counter})"
                )
    return warnings
```

Wire into chat route: after metrics are fetched but before synthesis, call `memory.check_consistency()`. If contradictions found, inject a reconciliation note into the LLM context.

### 7.4 Tests Required

| Test | What It Asserts |
|------|----------------|
| `test_ground_numbers_strips_ungrounded` | Number not in source data loses bold emphasis |
| `test_ground_numbers_keeps_grounded` | Number matching source data preserved |
| `test_mv_rt_mismatch_logged` | Different MV vs RT counts produce warning log |
| `test_numeric_claims_tracked` | After add_exchange with metrics, numeric_claims stored |
| `test_consistency_detects_contradiction` | Same entity, different trial count → warning |
| `test_consistency_no_false_positive` | Same entity, same count → no warning |
| `test_contradiction_injected_into_context` | LLM context includes reconciliation note |
| `test_tighter_tolerance` | 8 vs 6 trials → flagged (old ±2.0 would pass) |

**Minimum: 10 tests.**

### 7.5 Acceptance Criteria

- [ ] Trial counts are identical across turns for the same entity (unless data actually changed)
- [ ] Ungrounded numbers (not traceable to DB) are flagged or removed
- [ ] MV/RT mismatches logged for monitoring
- [ ] Conversation memory tracks numeric claims per entity
- [ ] Contradictions surfaced in response when detected

---

## 8. Workstream 6 — Follow-Up Generation

### 8.1 Problem

`generate_followups()` in `formatting.py` (L127-172) directly embeds regex-extracted entity names into f-string templates with no validation. This produces nonsensical suggestions like "What Phase 3 trials does what are the side effects of mounjaro have?"

### 8.2 Implementation

#### 8.2.1 Validate entities before template insertion: `services/chat_handlers/formatting.py`

Replace the current `generate_followups()` with a validated version:

```python
def generate_followups(
    question: str, 
    intent: str, 
    narrative: str, 
    params: dict,
    resolved_entities: list[CanonicalResult] | None = None,  # NEW param
) -> list[str]:
    """Generate contextual follow-up suggestions using ONLY validated entity names.
    
    Rules:
    1. Never embed raw user text into templates
    2. Only use canonical entity names from resolved_entities
    3. If no entities resolved, return generic exploration suggestions
    4. Each suggestion must be a valid, self-contained query
    """
    suggestions = []
    
    # Use ONLY canonical names, never raw params
    entities = []
    if resolved_entities:
        entities = [r.canonical_name for r in resolved_entities]
    
    if not entities:
        # Generic fallback — no entity-specific suggestions
        return [
            "What are the latest Phase 3 trial readouts?",
            "Show the competitive landscape for oncology",
            "Which companies have the strongest pipelines?",
        ]
    
    entity = entities[0]  # Primary entity
    
    if intent == Intent.COMPARE and len(entities) >= 2:
        suggestions.append(f"What Phase 3 trials does {entities[0]} have?")
        suggestions.append(f"Show the full pipeline for {entities[1]}")
        suggestions.append(f"What is the safety profile of {entities[0]}?")
    elif intent == Intent.DOSSIER:
        suggestions.append(f"What clinical trials are running for {entity}?")
        suggestions.append(f"Show the competitive landscape for {entity}")
        suggestions.append(f"What companies are developing {entity}?")
    # ... etc for other intents
    
    return suggestions[:3]
```

#### 8.2.2 Update call site: `api/routes/chat.py`

At the `generate_followups()` call (around line 340):

```python
payload["followup_suggestions"] = generate_followups(
    canonical_question,   # Use canonical, not raw
    intent,
    payload.get("narrative", ""),
    params,
    resolved_entities=canonical_results,  # NEW: pass validated entities
)
```

### 8.3 Tests Required

| Test | What It Asserts |
|------|----------------|
| `test_followups_use_canonical_names` | Suggestions contain "semaglutide" not "ozempic" when brand was input |
| `test_followups_no_query_fragments` | No suggestion contains "what are the side effects" as an entity |
| `test_followups_no_entities_generic` | No resolved entities → generic suggestions returned |
| `test_followups_max_three` | Never more than 3 suggestions |
| `test_followups_are_valid_queries` | Each suggestion, when passed to detect_intent(), returns a valid intent (not GENERAL) |

**Minimum: 6 tests.**

### 8.4 Acceptance Criteria

- [ ] Follow-up suggestions never contain query fragments as entity names
- [ ] All suggestions are valid, parseable queries
- [ ] Suggestions use canonical entity names
- [ ] Generic fallback works when no entities are resolved

---

## 9. Workstream 7 — Eval Harness Overhaul

### 9.1 Problem

The current eval harness:
- Tests 96+ queries but only single-intent, single-turn
- Uses `must_mention` presence checks, not numeric accuracy
- Factual accuracy tolerance is ±2.0 (far too loose for trial counts)
- Citation validity weighted at only 0.15
- No brand-name queries (would have caught Ozempic failure immediately)
- No multi-turn consistency tests
- No coverage diagnostic tests

### 9.2 Implementation

#### 9.2.1 New query categories in `benchmark/golden_queries.json`

Add these categories to the existing query set:

**Synonym resolution (10 queries):**
```json
{
    "id": "SYN01",
    "intent": "dossier",
    "question": "Tell me about Ozempic",
    "expected": {
        "entities": ["semaglutide"],
        "must_mention": ["semaglutide", "GLP-1"],
        "must_not_mention": [],
        "min_evidence": 1,
        "min_citations": 1,
        "canonical_entity": "semaglutide"
    },
    "note": "Brand name must resolve to INN"
}
```

Other synonym queries: Mounjaro→tirzepatide, Keytruda→pembrolizumab, Humira→adalimumab, Wegovy→semaglutide, Rybelsus→semaglutide, Zepbound→tirzepatide, Jardiance→empagliflozin, Entresto→sacubitril/valsartan, Dupixent→dupilumab.

**Multi-turn consistency (5 dialogues):**
```json
{
    "id": "MT01",
    "type": "multi_turn",
    "turns": [
        {"question": "How many trials does semaglutide have?", "assert_numeric": {"total_trials": ">0"}},
        {"question": "What about tirzepatide?", "assert_numeric": {"total_trials": ">0"}},
        {"question": "Compare them", "assert_consistency": ["total_trials for semaglutide matches turn 1"]}
    ]
}
```

**Adversarial/edge-case (5 queries):**
```json
{
    "id": "ADV01",
    "intent": "general",
    "question": "What is your ERD?",
    "expected": {
        "must_mention": ["data model", "schema"],
        "must_not_mention": ["trial", "pipeline"],
        "meta_intent": true
    }
}
```

**Numeric precision (5 queries):**
```json
{
    "id": "NUM01",
    "intent": "pipeline",
    "question": "How many Phase 3 trials does semaglutide have?",
    "expected": {
        "entities": ["semaglutide"],
        "exact_numeric": {"phase3_trials": "FROM_DB"},
        "tolerance": 0
    },
    "note": "Exact match against DB count, zero tolerance"
}
```

#### 9.2.2 New scorers: `benchmark/scorers.py`

**Synonym resolution scorer:**
```python
def score_synonym_resolution(response: dict, expected: dict) -> float:
    """Check that brand name resolved to canonical entity.
    
    Returns 1.0 if canonical_entity appears in entity_focus labels.
    Returns 0.0 if original brand name appears instead.
    """
    canonical = expected.get("canonical_entity")
    if not canonical:
        return 1.0  # not a synonym test
    
    entity_labels = [e.get("label", "").lower() for e in response.get("entity_focus", [])]
    if canonical.lower() in entity_labels:
        return 1.0
    return 0.0
```

**Multi-turn consistency scorer:**
```python
def score_multi_turn_consistency(turn_responses: list[dict]) -> float:
    """Check that numeric claims are consistent across turns.
    
    Extracts numbers tied to entities across turns.
    Returns 1.0 if all consistent, penalises each contradiction by 0.2.
    """
```

**Numeric precision scorer (replaces loose factual accuracy):**
```python
def score_numeric_precision(response: dict, expected: dict, db: Database) -> float:
    """Check that numbers in the narrative match DB values exactly.
    
    For each expected numeric field:
    1. Query the DB for the actual value
    2. Extract the corresponding number from the narrative
    3. Compare with tolerance 0 (exact) or specified tolerance
    
    Returns ratio of correct numbers to total expected numbers.
    """
```

#### 9.2.3 Update weights: `benchmark/scorers.py`

Replace current weights (line 17):

```python
# OLD:
WEIGHTS = {
    "intent": 0.10,
    "grounding": 0.25,
    "factual": 0.25,
    "completeness": 0.25,
    "citation": 0.15,
}

# NEW:
WEIGHTS = {
    "intent": 0.10,
    "grounding": 0.20,
    "factual": 0.20,
    "completeness": 0.15,
    "citation": 0.20,        # increased from 0.15
    "synonym": 0.05,         # NEW
    "numeric_precision": 0.10, # NEW
}
```

#### 9.2.4 Multi-turn eval runner: `benchmark/eval_runner.py`

Add a new method to `EvalRunner`:

```python
def run_multi_turn(self, dialogue: dict) -> list[EvalResult]:
    """Run a multi-turn dialogue test.
    
    Maintains conversation state across turns.
    After each turn, checks assertions (numeric consistency, entity resolution).
    """
    session_id = f"eval-{dialogue['id']}-{uuid4()}"
    results = []
    
    for i, turn in enumerate(dialogue["turns"]):
        response = self._send_chat(
            question=turn["question"],
            session_id=session_id,
            conversation_history=self._build_history(results),
        )
        
        result = self._score_turn(response, turn, prior_results=results)
        results.append(result)
    
    return results
```

#### 9.2.5 CI gate update: `benchmark/ci_eval.py`

Update the CI evaluation to include new query categories:

```python
def run_ci_eval(threshold: float = 75.0, **kwargs):
    runner = EvalRunner(...)
    
    # Standard single-turn
    single_report = runner.run(golden_queries)
    
    # NEW: Multi-turn dialogues
    multi_report = runner.run_multi_turn_batch(multi_turn_dialogues)
    
    # NEW: Synonym resolution
    synonym_score = mean([r.scores.get("synonym", 1.0) for r in single_report.results])
    
    # Combined score
    combined = single_report.overall_score * 0.6 + multi_report.overall_score * 0.2 + synonym_score * 100 * 0.2
    
    if combined < threshold:
        sys.exit(1)
```

### 9.3 Tests Required

| Test | What It Asserts |
|------|----------------|
| `test_synonym_scorer_brand_resolved` | Brand name → canonical in entity_focus → score 1.0 |
| `test_synonym_scorer_brand_not_resolved` | Brand name unresolved → score 0.0 |
| `test_multi_turn_consistent` | Same entity count across turns → score 1.0 |
| `test_multi_turn_contradiction` | Different counts → score < 1.0 |
| `test_numeric_precision_exact` | DB says 8, narrative says 8 → score 1.0 |
| `test_numeric_precision_wrong` | DB says 8, narrative says 2 → score 0.0 |
| `test_new_weights_sum_to_one` | All weight values sum to 1.0 |
| `test_ci_eval_includes_synonym` | CI eval report includes synonym dimension |
| `test_golden_queries_have_synonyms` | At least 10 SYN-prefixed queries exist |
| `test_golden_queries_have_multi_turn` | At least 5 MT-prefixed dialogues exist |

**Minimum: 12 tests.**

### 9.4 Acceptance Criteria

- [ ] Golden queries include 10+ synonym tests, 5+ multi-turn dialogues, 5+ adversarial, 5+ numeric precision
- [ ] CI gate tests synonym resolution (brand→INN)
- [ ] CI gate tests multi-turn consistency
- [ ] Numeric precision scorer uses exact match (tolerance 0) for trial counts
- [ ] Citation weight increased to 0.20
- [ ] All new scorers have unit tests
- [ ] CI threshold still passes with new query set (adjust threshold if needed during rollout)

---

## 10. Execution Sequence

| Phase | Workstream | Duration | Dependencies | Rationale |
|-------|-----------|----------|-------------|-----------|
| **1** | WS-1: Entity Canonicalisation | 5-7 days | None | Foundation — everything else depends on correct entity resolution |
| **2** | WS-2: Intent & NLU Layer | 3-4 days | WS-1 (uses canonicaliser) | Second most impactful — prevents cascading failures |
| **3** | WS-6: Follow-Up Generation | 1-2 days | WS-1, WS-2 | Quick fix once entities are canonical |
| **4** | WS-4: Provenance & Citations | 3-4 days | WS-1 (enriched EvidenceItem) | Data plumbing — needs to be done before eval can test it |
| **5** | WS-5: Numeric Guardrails | 3-4 days | WS-1 (canonical entities for tracking) | Cross-turn consistency depends on stable entity identity |
| **6** | WS-3: Coverage Diagnostics | 3-4 days | WS-1, WS-4 (needs provenance to assess coverage) | Requires stable retrieval and provenance to estimate recall |
| **7** | WS-7: Eval Harness Overhaul | 4-5 days | All above (tests the full stack) | Must be last — the eval tests all fixes |

**Total: 22-30 days** with a single developer, or **12-16 days** with two developers (WS-1/WS-2 can be parallelised with WS-4/WS-5 once WS-1 is complete).

### Critical Path

```
WS-1 (Entity Canonicalisation)
  ├──→ WS-2 (Intent/NLU) ──→ WS-6 (Follow-Ups)
  ├──→ WS-4 (Provenance) ──→ WS-3 (Coverage)
  └──→ WS-5 (Numeric Guardrails)
                                    ↘
                                      WS-7 (Eval Overhaul)
                                    ↗
```

WS-1 is the single dependency that blocks everything. Prioritise it absolutely.

---

## 11. Definition of Done

The intelligence layer remediation is complete when:

1. **"Compare Ozempic vs Mounjaro"** resolves both to semaglutide and tirzepatide, retrieves data for both, and produces a comparison with per-claim provenance (NCT IDs, PMIDs)
2. **No follow-up suggestion** ever contains a query fragment as an entity name
3. **Trial counts are consistent** across all turns in a conversation for the same entity
4. **Every number** in a narrative traces to a specific DB value or is qualified as approximate
5. **Coverage warnings** appear when data represents < 20% of estimated universe
6. **Verdicts are suppressed** when supporting data is too sparse (< 5 data points)
7. **"What is your ERD"** gets a system description, not a pharma dossier
8. **Eval harness passes** with synonym, multi-turn, adversarial, and numeric precision tests at ≥ 75% composite score
9. **All existing tests still pass** — zero regressions
10. **Test count increases** by at least 80 new tests across all workstreams

---

## 12. Appendix: Current Code Reference

### Key File Paths

| File | Lines | What's There |
|------|-------|-------------|
| `integration/entity_resolver.py` | L104-110 | `FUZZY_MATCH_FIELDS` dict (missing brand_name) |
| `integration/entity_resolver.py` | L165-211 | `resolve()` main loop |
| `integration/entity_resolver.py` | L261 | `_exact_lookup()` |
| `integration/entity_resolver.py` | L290-318 | `_alias_lookup()` |
| `integration/entity_resolver.py` | L324-364 | `_fuzzy_lookup()` (searches only generic_name) |
| `integration/entity_resolver.py` | L370-412 | `_embedding_lookup()` |
| `integration/entity_resolver.py` | L844-860 | `_create_alias()` |
| `domain/pharma/mention_normalizer.py` | L67-118 | `normalize_drug_mention()` (no brand→INN map) |
| `domain/pharma/pack.py` | L38-56 | Drug EntitySchema (fuzzy_match_fields lacks brand_name) |
| `services/chat_handlers/formatting.py` | L69-124 | `resolve_entity()` (searches only generic_name) |
| `services/chat_handlers/formatting.py` | L127-172 | `generate_followups()` (no entity validation) |
| `services/chat_handlers/intent.py` | L48-170 | `detect_intent()` (all regex patterns) |
| `services/chat_handlers/intent.py` | L63-65 | COMPARE regex (captures clause fragments) |
| `services/chat_handlers/intent.py` | L156 | DOSSIER regex (matches "what is your ERD") |
| `services/llm.py` | L30-56 | `validate_citations()` (range check only) |
| `services/llm.py` | L96 | `verify_narrative_numbers()` (±2.0 tolerance) |
| `services/llm.py` | L430-504 | `synthesize()` (post-validation at L500) |
| `services/llm.py` | L589 | `synthesize_comparison()` (no sparsity check) |
| `services/ctx_pipeline.py` | L173-291 | `understand()` (intent + entity detection) |
| `services/ctx_pipeline.py` | L354-417 | `reason()` (no numeric validation) |
| `services/query_engine.py` | L76-189 | `query()` (separate metric calls per entity) |
| `services/query_engine.py` | L285-360 | `compare_entities()` (no cross-entity reconciliation) |
| `services/conversation_memory.py` | L66-315 | Full class (tracks entities, not numbers) |
| `services/metrics.py` | L39-117 | `drug_pipeline_strength()` (MV + RT fallback) |
| `api/routes/chat.py` | L197-386 | Main chat endpoint (full flow) |
| `api/routes/chat.py` | L340 | `generate_followups()` call site |
| `benchmark/scorers.py` | L17-23 | Weights (citation only 0.15) |
| `benchmark/scorers.py` | L85-134 | `score_factual_accuracy()` (±2.0 tolerance) |
| `benchmark/golden_queries.json` | — | 96+ queries, no synonyms, no multi-turn |
| `schema/migrations/001_core_tables.sql` | L60-78 | `drugs` table (has brand_name column) |
| `schema/migrations/003_entity_aliases.sql` | L5-14 | `entity_aliases` table (zero seed data) |
| `config.py` | L168 | `use_unified_handler` defaults to false |

### SQL Schemas Referenced

**drugs table:**
```
id UUID PK, company_id UUID FK, brand_name TEXT, generic_name TEXT NOT NULL,
nda_number TEXT, therapeutic_area_id UUID FK, mechanism_id UUID FK,
approval_date DATE, patent_expiry_date DATE, patent_number TEXT,
supply_status TEXT, molecule_embedding VECTOR(1536), source_api TEXT,
source_url TEXT, retrieved_at TIMESTAMP, created_at TIMESTAMP, updated_at TIMESTAMP
```

**entity_aliases table:**
```
id UUID PK, entity_type TEXT NOT NULL, entity_id UUID NOT NULL,
alias_text TEXT NOT NULL, source_type TEXT NOT NULL, confidence FLOAT NOT NULL,
verified BOOLEAN DEFAULT FALSE, created_at TIMESTAMP
```

**entity_links table:**
```
id UUID PK, source_entity_id UUID, source_entity_type TEXT,
target_entity_id UUID, target_entity_type TEXT, link_type TEXT,
link_via TEXT, confidence FLOAT DEFAULT 1.0, metadata JSONB,
provenance_source TEXT, created_at TIMESTAMP
```

### Regex Patterns in Intent Detection

| Pattern | Line | Captures | Risk |
|---------|------|----------|------|
| `(.+?)\s+(?:vs\.\|versus\|...)` | L63 | Entity names for COMPARE | Captures clause fragments |
| `differences?\s+between\s+(.+?)\s+and\s+(.+?)` | L67 | Entity pair | Same risk |
| `how\s+does\s+(.+?)\s+stack\s+up` | L70 | Single entity | Lower risk |
| `(?:which\|what)\s+.*?\b(.+?)\s+or\s+(.+?)` | L73 | Entity pair | High risk (greedy) |
| `(?:tell me about\|what is\|...)\s+(.+?)` | L156 | Entity for DOSSIER | Matches meta questions |

---

*Generated from code-level audit of the Market Zero codebase, 19 April 2026.*
*Based on domain expert review of live system transcript.*
