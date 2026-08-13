# BE-1 — Evidence card fields on `evidence_records`

> Filed in `docs/AGENT_BACKLOG.md#be-1`. Loop opened 2026-05-10.
> Branch: `claude/be-001-evidence-card-fields`.

## 1 · Why

PB-101 (frontend) replaces `EvidenceStack.tsx` (which currently renders
only opaque `doc_id` strings) with an `EvidenceCard` primitive that
needs five fields per card:

| field | source |
|---|---|
| source name | `evidence_records.source_name` (BE-1) |
| favicon | derived from `source_url` (frontend) |
| tier badge | `evidence_records.source_tier` (BE-1) |
| date | `evidence_records.published_at` (BE-1) |
| 2-line snippet | `evidence_records.snippet` (BE-1) |

Today only `source_id` (a slug like `"clinical_trials_gov"`) and the
full `extracted_text` are stored. The frontend cannot render an
EvidenceCard without these enrichments.

## 2 · Design

### Schema (migration 068)

Four nullable columns on `evidence_records`. Nullable so existing
rows survive the ALTER without backfill (the append-only trigger
won't allow updating them after insert anyway, except via the
trigger-allowed first-fill below).

```sql
ALTER TABLE evidence_records
  ADD COLUMN source_name  TEXT,
  ADD COLUMN source_tier  TEXT
              CHECK (source_tier IS NULL
                     OR source_tier IN ('T1','T2','T3','T4')),
  ADD COLUMN published_at TIMESTAMPTZ,
  ADD COLUMN snippet      TEXT
              CHECK (snippet IS NULL OR char_length(snippet) <= 1000);
```

The append-only trigger (`evidence_records_append_only`) is widened
so a one-time first-fill of any of these four columns is allowed
(same pattern as the existing `archived_snapshot_ref` allowance).
Once set, the column becomes immutable.

### Source registry (defaults)

`services/evidence_ledger.py` gains a small per-source-id registry
that maps `source_id` → default `(source_name, source_tier)`. New
rows that don't supply explicit values get the registry defaults at
INSERT. Today's tier mapping (matches
`schema/migrations/058_materiality_scoring.sql`):

| source_id (canonical) | name | tier |
|---|---|---|
| `clinical_trials_gov` | ClinicalTrials.gov | T1 |
| `fda_orange_book` / `openfda_*` | FDA | T1 |
| `sec_edgar` | SEC EDGAR | T2 |
| `pubmed` / `mesh` / `pmc` | PubMed | T3 |
| `aacr` / `asco` / `ash` | Conference (AACR/ASCO/ASH) | T3 |
| (anything else) | source_id verbatim | T3 |

Snippet default = `LEFT(extracted_text, 200)` truncated at the last
sentence boundary, single trailing ellipsis if truncated. Computed
once at INSERT.

### `EvidenceItemResponse`

Adds the four new fields. Field shape is permissive (all optional)
so older callers keep working.

### Backfill

`scripts/backfill_evidence_card_fields.py` is a paginated
first-fill of the four columns on existing rows using the registry
+ snippet helper. Idempotent — only touches rows where any of the
four columns is NULL.

## 3 · Acceptance

Per AGENT_BACKLOG#BE-1:

- [x] Four columns added (migration 068).
- [x] Append-only trigger widened to allow first-fill of each.
- [x] Source registry + snippet helper land defaults at INSERT.
- [x] `_row_to_evidence` + `EvidenceRecord.to_dict` + `EvidenceItemResponse`
      surface the new fields.
- [x] Backfill script for legacy rows.
- [x] Frontend can render an EvidenceCard without further backend
      work.
