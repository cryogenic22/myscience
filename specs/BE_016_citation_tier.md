# BE-16 — Citation payload carries source tier

> Filed in `docs/AGENT_BACKLOG.md#be-16`. Stacks on
> `claude/be-001-evidence-card-fields` (reuses the source registry).
> Branch: `claude/be-016-citation-tier`.

## 1 · Why

PB-603 (frontend CitationChip primitive) needs to colour each chip
by tier (T1=green, T2=blue, T3=violet, T4=amber). Today the chat
response carries inline `[N]` markers in the narrative but no
`citations[]` array — so the chip renderer has nothing to read.

## 2 · Design

### `extract_citations_with_tier(narrative, evidence) -> list[dict]`

New helper in `services/llm.py`. Scans `[N]` markers, dedups, looks
up tier per marker in this order:

1. Explicit `evidence[N-1].source_tier` (BE-1 wired this onto
   `evidence_records` for new ingestion).
2. `services.evidence_ledger.lookup_source_metadata(source_id)`
   registry fallback for legacy rows.

Emits one item per unique marker, keeping the order of first
appearance::

    {
      "n": 3,
      "evidence_id": "ev-...",
      "source_id": "pubmed",
      "source_name": "PubMed",
      "source_tier": "T3",
      "published_at": "2026-04-01T00:00:00Z",
      "snippet": "…",
      "source_url": "https://pubmed.ncbi.nlm.nih.gov/123",
    }

Out-of-range markers (`[7]` when only 3 records exist) are silently
skipped — the existing `validate_citations` already strips them
from the rendered narrative.

### What this PR does

- Ships the helper + 8 tests covering: empty inputs, explicit tier,
  registry fallback, invalid markers, dedup, ordering, URL/date,
  field-shape matching.

### What's deferred (follow-up)

The chat handlers (`services/chat_handlers/handlers.py`) need to
call this and splice `citations: [...]` into their payloads. That's
a 1-line edit per handler but touches 8 different handler functions.
Tracked as **BE-16-FU1** for the next PR after this one to keep the
diff readable.

## 3 · Acceptance

- [x] Helper emits `{n, source_name, source_tier, published_at,
      snippet, source_url, evidence_id, source_id}` per `[N]`.
- [x] Tier resolution prefers explicit field, falls back to BE-1
      registry, returns None for unmapped slugs (per registry
      contract).
- [x] Out-of-range markers silently skipped.
- [x] Order of first appearance preserved; duplicates emitted once.
- [ ] Chat handlers wire the helper into their response payloads
      (BE-16-FU1).
