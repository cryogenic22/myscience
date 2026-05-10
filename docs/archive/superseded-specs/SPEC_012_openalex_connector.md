# SPEC-012: OpenAlex Connector

*Date: 19 April 2026*
*Priority: P1 (depends on SPEC_010 schema cleanup; should ship after SPEC_013 link confidence)*
*Effort: 3–5 days*

---

## Goal

Add a new `OpenAlexConnector` that pulls pharma-relevant works from the OpenAlex API into our literature corpus. Targets ~25× expansion of the current ~2,000 PubMed articles, plus citation graph (`CITES` link type), institution entities (ROR-identified), and Topic taxonomy as a complement to MeSH.

## Why This Matters

Current literature pipeline:
- ~2,000 articles from PubMed search queries
- ~500 with full text from PMC OA subset
- 0% citation graph coverage
- Author/institution data thin (~50% have institution attribution)

OpenAlex provides (free API, no auth required, polite pool with mailto):
- 250M+ works indexed; ~50K+ pharma-relevant works in 2024–2026 alone
- Citation counts + FWCI (field-weighted citation impact)
- Open access status with direct OA URLs (subsumes Unpaywall)
- ROR-identified institutional affiliations
- Topic hierarchy (Domain > Field > Subfield > Topic) with confidence scores
- `referenced_works` array — enables citation graph

This single connector advances 4 separate lead-recommended improvements: citation graph, source diversity, OA discovery, and ontology supplementation.

## Tests First

Create `tests/test_openalex_connector.py`:

```python
"""TDD for OpenAlexConnector. All tests must FAIL before implementation."""
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

from connectors.openalex import OpenAlexConnector, reconstruct_abstract
from connectors.base import RecordType, SourceType


def test_source_type_is_openalex():
    """SPEC_012: OpenAlex must register a new SourceType."""
    c = OpenAlexConnector()
    assert c.source_type() == SourceType.OPENALEX


def test_health_check_hits_openalex_api():
    c = OpenAlexConnector()
    result = c.health_check()
    assert result.healthy in (True, False)
    assert result.source_type == SourceType.OPENALEX


def test_polite_pool_mailto_in_request_params(monkeypatch):
    """All API calls must include mailto for higher rate limits."""
    monkeypatch.setenv("OPENALEX_MAILTO", "kapilpant@gmail.com")
    captured = {}
    def fake_get(url, params=None, **kw):
        captured["params"] = params
        resp = MagicMock(status_code=200, json=lambda: {"results": [], "meta": {"next_cursor": None}})
        return resp
    c = OpenAlexConnector()
    c.session.get = fake_get
    list(c.fetch_works_for_concept("C98274493"))
    assert captured["params"].get("mailto") == "kapilpant@gmail.com"


def test_reconstruct_abstract_from_inverted_index():
    """OpenAlex stores abstracts as inverted index. Helper must rebuild prose."""
    inverted = {
        "Semaglutide": [0],
        "reduces": [1],
        "A1C": [2],
        "by": [3],
        "1.5%": [4],
    }
    out = reconstruct_abstract(inverted)
    assert out == "Semaglutide reduces A1C by 1.5%"


def test_reconstruct_abstract_handles_repeated_words():
    inverted = {
        "the": [0, 3],
        "drug": [1],
        "showed": [2],
        "effect": [4],
    }
    assert reconstruct_abstract(inverted) == "the drug showed the effect"


def test_reconstruct_abstract_handles_none():
    """Many works have no abstract — return empty string."""
    assert reconstruct_abstract(None) == ""


def test_fetch_yields_literature_records():
    """Each OpenAlex work becomes a LITERATURE RawRecord."""
    fake_work = {
        "id": "https://openalex.org/W123",
        "doi": "https://doi.org/10.1/test",
        "title": "Test paper",
        "publication_date": "2025-01-15",
        "publication_year": 2025,
        "cited_by_count": 42,
        "fwci": 1.8,
        "abstract_inverted_index": {"Test": [0], "abstract": [1]},
        "open_access": {
            "is_oa": True,
            "oa_url": "https://example.com/pdf",
            "any_repository_has_fulltext": True,
        },
        "best_oa_location": {"pdf_url": "https://example.com/pdf"},
        "primary_location": {"source": {"display_name": "Test Journal"}},
        "topics": [{"id": "T1", "display_name": "Diabetes", "score": 0.95}],
        "concepts": [{"id": "C98274493", "display_name": "Pharmacology", "score": 0.9}],
        "authorships": [
            {
                "author": {"id": "A1", "display_name": "Smith J", "orcid": "0000-0001-0002-0003"},
                "institutions": [{"id": "I1", "display_name": "MIT", "ror": "https://ror.org/042nb2s44"}],
                "author_position": "first",
            }
        ],
        "referenced_works": ["https://openalex.org/W456", "https://openalex.org/W789"],
        "type": "article",
        "ids": {"openalex": "W123", "doi": "10.1/test", "pmid": "https://pubmed.ncbi.nlm.nih.gov/12345"},
    }
    with patch.object(OpenAlexConnector, "_paginate", return_value=iter([fake_work])):
        c = OpenAlexConnector()
        records = list(c.fetch())

    lit_recs = [r for r in records if r.record_type == RecordType.LITERATURE]
    assert len(lit_recs) == 1
    rec = lit_recs[0]
    assert rec.external_id == "W123"
    assert rec.data["doi"] == "10.1/test"
    assert rec.data["cited_by_count"] == 42
    assert rec.data["fwci"] == 1.8
    assert rec.data["abstract"].startswith("Test")
    assert rec.data["pmid"] == "12345"  # Stripped from URL
    assert rec.text_content.startswith("Test paper")


def test_fetch_yields_institution_records():
    """Each unique institution should be emitted as an INSTITUTION RawRecord."""
    # See test_fetch_yields_literature_records fixture
    fake_work = {
        "id": "https://openalex.org/W123",
        "title": "x", "publication_date": "2025-01-01",
        "authorships": [
            {"author": {"id": "A1", "display_name": "Smith"},
             "institutions": [{"id": "I1", "display_name": "MIT", "ror": "https://ror.org/042nb2s44"}],
             "author_position": "first"}
        ],
        "abstract_inverted_index": None,
        "ids": {"openalex": "W123"},
    }
    with patch.object(OpenAlexConnector, "_paginate", return_value=iter([fake_work])):
        c = OpenAlexConnector()
        records = list(c.fetch())

    inst = [r for r in records if r.record_type == RecordType.INSTITUTION]
    assert len(inst) == 1
    assert inst[0].external_id == "I1"
    assert inst[0].data["ror"] == "042nb2s44"


def test_fetch_emits_citation_links_only_for_known_works():
    """A CITES link must only be emitted between two works our pipeline knows.
    External citations are skipped to avoid graph blowout."""
    # When referenced_works points to W456 but W456 is not in our corpus,
    # no CITES link should be emitted.
    pass  # implementation detail — see _emit_citation_links


def test_incremental_fetch_uses_from_updated_date(monkeypatch):
    """fetch(since=...) must filter via from_updated_date param."""
    captured = {}
    def fake_get(url, params=None, **kw):
        captured["params"] = params
        return MagicMock(status_code=200, json=lambda: {"results": [], "meta": {"next_cursor": None}})
    c = OpenAlexConnector()
    c.session.get = fake_get
    list(c.fetch(since=datetime(2026, 4, 1)))
    f = captured["params"]["filter"]
    assert "from_updated_date:2026-04-01" in f


def test_cursor_pagination_follows_next_cursor():
    """Connector must paginate via cursor=*, follow meta.next_cursor."""
    pages = [
        {"results": [{"id": "W1", "title": "p1", "publication_date": "2025-01-01",
                      "abstract_inverted_index": None, "ids": {"openalex": "W1"}}],
         "meta": {"next_cursor": "abc"}},
        {"results": [{"id": "W2", "title": "p2", "publication_date": "2025-01-02",
                      "abstract_inverted_index": None, "ids": {"openalex": "W2"}}],
         "meta": {"next_cursor": None}},
    ]
    call_count = {"n": 0}
    def fake_get(url, params=None, **kw):
        i = call_count["n"]
        call_count["n"] += 1
        return MagicMock(status_code=200, json=lambda: pages[i])
    c = OpenAlexConnector()
    c.session.get = fake_get
    works = list(c._paginate({"filter": "x"}))
    assert len(works) == 2
    assert call_count["n"] == 2


def test_rate_limit_429_triggers_backoff(monkeypatch):
    """A 429 response must trigger exponential backoff retry."""
    sleeps = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))
    responses = [
        MagicMock(status_code=429, headers={"Retry-After": "2"}),
        MagicMock(status_code=200, json=lambda: {"results": [], "meta": {"next_cursor": None}}),
    ]
    call_count = {"n": 0}
    def fake_get(url, params=None, **kw):
        r = responses[call_count["n"]]
        call_count["n"] += 1
        return r
    c = OpenAlexConnector()
    c.session.get = fake_get
    list(c._paginate({"filter": "x"}))
    assert len(sleeps) >= 1 and sleeps[0] >= 2
```

Also add a test for the migration:

```python
# tests/test_openalex_schema.py
def test_literature_has_openalex_columns(db):
    """SPEC_012 migration 016 must add openalex_id, fwci, topics."""
    cols = {r["column_name"] for r in db.fetch_all(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'literature_articles'"
    )}
    for required in ("openalex_id", "cited_by_count", "fwci", "topics", "concepts"):
        assert required in cols

def test_cites_link_type_registered():
    from domain.pharma.pack import get_pharma_pack
    pack = get_pharma_pack()
    link_types = {rule.link_type for rule in pack.link_rules}
    assert "CITES" in link_types

def test_institution_entity_type_registered():
    from domain.pharma.pack import get_pharma_pack
    pack = get_pharma_pack()
    entity_types = {schema.entity_type for schema in pack.entity_schemas}
    assert "institution" in entity_types
```

**Run them**: `python -m pytest tests/test_openalex_connector.py tests/test_openalex_schema.py -v`. All must FAIL.

## Implementation Plan

### Step 1 — Add `SourceType.OPENALEX` and `RecordType.INSTITUTION`

In `connectors/base.py`:
```python
class SourceType(str, Enum):
    ...
    OPENALEX = "openalex"

class RecordType(str, Enum):
    ...
    INSTITUTION = "institution"
```

### Step 2 — Migration `schema/migrations/016_openalex_support.sql`

```sql
-- 016_openalex_support.sql
-- Adds OpenAlex-derived columns to literature, creates institutions table.

ALTER TABLE literature_articles
    ADD COLUMN IF NOT EXISTS openalex_id TEXT UNIQUE,
    ADD COLUMN IF NOT EXISTS cited_by_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS fwci NUMERIC(8, 4),
    ADD COLUMN IF NOT EXISTS topics JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS concepts JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS oa_url TEXT,
    ADD COLUMN IF NOT EXISTS is_oa BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_literature_openalex_id
    ON literature_articles (openalex_id) WHERE openalex_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_literature_cited_by
    ON literature_articles (cited_by_count DESC NULLS LAST);

CREATE TABLE IF NOT EXISTS institutions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    openalex_id TEXT UNIQUE,
    ror TEXT UNIQUE,
    display_name TEXT NOT NULL,
    country_code TEXT,
    type TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_institutions_ror ON institutions (ror) WHERE ror IS NOT NULL;
```

### Step 3 — Domain pack: add `institution` entity, `CITES` and `AFFILIATED_WITH` link types

In `domain/pharma/pack.py`, add:
- `EntitySchema` for `institution` (lookup keys: `ror`, `openalex_id`, `display_name`)
- `LinkRule` for `CITES` (literature → literature)
- `LinkRule` for `AFFILIATED_WITH` (investigator → institution)

### Step 4 — Build `connectors/openalex.py`

Skeleton, mirroring `connectors/pubmed.py` patterns:

```python
import os
import time
from datetime import datetime
from typing import Iterable, Optional
import requests

from connectors.base import (
    BaseConnector, HealthCheckResult, Provenance,
    RawRecord, RecordType, SourceType,
)

API_BASE = "https://api.openalex.org/works"

PHARMA_CONCEPTS = [
    "C98274493",   # Pharmacology
    "C71924100",   # Medicine
    "C2779134260", # Clinical trial
    "C126322002",  # Internal medicine
    "C2780035454", # Drug discovery
]


def reconstruct_abstract(inverted: Optional[dict]) -> str:
    """Rebuild prose from OpenAlex's word→positions inverted index."""
    if not inverted:
        return ""
    positions = []
    for word, idxs in inverted.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions)


class OpenAlexConnector(BaseConnector):
    def __init__(self, config=None, target_overrides=None):
        self.config = config
        self.mailto = os.getenv("OPENALEX_MAILTO", "")
        self.session = requests.Session()
        overrides = target_overrides or {}
        self._concepts = overrides.get("concepts", PHARMA_CONCEPTS)
        self._known_openalex_ids: set[str] = set()  # populated lazily for citation links

    def source_type(self) -> SourceType:
        return SourceType.OPENALEX

    def health_check(self) -> HealthCheckResult:
        ...  # GET /works?per_page=1

    def fetch(self, since: Optional[datetime] = None) -> list[RawRecord]:
        records: list[RawRecord] = []
        seen_inst_ids: set[str] = set()

        for concept_id in self._concepts:
            filter_str = f"concepts.id:{concept_id}"
            if since:
                filter_str += f",from_updated_date:{since:%Y-%m-%d}"
            params = {
                "filter": filter_str,
                "per_page": 200,
                "cursor": "*",
            }
            for work in self._paginate(params):
                lit, insts = self._parse_work(work)
                if lit:
                    records.append(lit)
                for inst in insts:
                    if inst.external_id not in seen_inst_ids:
                        seen_inst_ids.add(inst.external_id)
                        records.append(inst)

        # Citation links emitted in a second pass (now we know our corpus)
        records.extend(self._emit_citation_links(records))
        return records

    def _paginate(self, params: dict) -> Iterable[dict]:
        cursor = "*"
        while cursor:
            params["cursor"] = cursor
            if self.mailto:
                params["mailto"] = self.mailto
            resp = self.session.get(API_BASE, params=params, timeout=60)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", "2"))
                time.sleep(wait)
                continue
            resp.raise_for_status()
            body = resp.json()
            for work in body.get("results", []):
                yield work
            cursor = body.get("meta", {}).get("next_cursor")
            time.sleep(0.1)  # polite pause

    def _parse_work(self, work: dict) -> tuple[Optional[RawRecord], list[RawRecord]]:
        ...

    def _emit_citation_links(self, records: list[RawRecord]) -> list[RawRecord]:
        """Emit CITES links only when both source and target are in our corpus."""
        ...
```

### Step 5 — Register in connector registry

In `connectors/__init__.py`:
```python
from connectors.openalex import OpenAlexConnector
CONNECTOR_REGISTRY[SourceType.OPENALEX] = OpenAlexConnector
```

### Step 6 — Add to scheduler

In `scheduler/config.py`:
```python
SourceType.OPENALEX: {
    "label": "OpenAlex",
    "cron": {"hour": 3, "minute": 30},  # After PubMed (02:30) + PMC (03:00)
},
```

Add `SourceType.OPENALEX` to `RUN_ORDER` after `SourceType.PMC`.

### Step 7 — Configure environment

Add to Railway:
- `OPENALEX_MAILTO=kapilpant@gmail.com`

### Step 8 — Initial backfill (manual, one-time)

```bash
railway run python -c "from scheduler import DataPipelineScheduler; DataPipelineScheduler().run_one('openalex')"
```

Expect 30–60 minutes runtime, ~50K records inserted. Watch logs for rate limit issues.

## Acceptance Criteria

- [ ] All tests in `tests/test_openalex_connector.py` and `tests/test_openalex_schema.py` pass
- [ ] Existing test suite has zero regressions
- [ ] Migration 016 applied successfully
- [ ] Backfill completes without rate limit blocks
- [ ] Literature record count: from ~2,000 to ≥40,000 (allow some headroom under 50K depending on dedup)
- [ ] At least 1,000 CITES links created in `entity_links`
- [ ] At least 500 institution rows in `institutions` table
- [ ] `/health` connector status shows OpenAlex as healthy
- [ ] Daily incremental run (next day after backfill) inserts <2,000 new records (proves incremental filter works)

## Rollout / Rollback

**Rollout:**
1. Local tests pass.
2. Apply migration 016 locally; run a small fetch (`MAX_ARTICLES_PER_QUERY=50`) and verify records.
3. Deploy to Railway.
4. Apply migration: `railway run python migrate.py`.
5. Trigger one-shot backfill: `railway run python -c "..."`.
6. Monitor for 24 hours; verify daily cron runs incrementally.

**Rollback:**
- Remove from `RUN_ORDER` and connector registry → daily cron stops.
- Migration 016 is additive; no rollback needed at the schema level.
- If literature data is polluted: `DELETE FROM literature_articles WHERE openalex_id IS NOT NULL` recovers cleanly.

## Out of Scope

- Full-text fetching from OA URLs (deferred — store URL only, fetch lazily on demand from a future doc-fetch service)
- Citation graph beyond our corpus (would explode link table — only `CITES` links between our existing literature)
- Author entity disambiguation (use OpenAlex's existing author IDs; don't try to merge with our INVESTIGATOR records yet)
- Topic-based concept hierarchy promotion (separate task — supplement to MeSH)
