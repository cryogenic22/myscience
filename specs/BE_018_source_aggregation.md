# BE-18 — Aggregate-by-source helper

> Filed in `docs/AGENT_BACKLOG.md#be-18`. Stacks on
> `claude/be-001-evidence-card-fields`. Branch:
> `claude/be-018-source-aggregation`.

## 1 · Why

PB-605's "source strip" renders one chip per source under every
assistant message: tier dot + source name + cite count. The chat
response needs `source_aggregation: [...]` to drive it.

## 2 · Design

`services/source_aggregation.py::aggregate_by_source(evidence)`.
Pure function — chat handlers call it after assembling the evidence
pack and splice the result into the response.

Output shape::

    [
      {"source_id": "fda", "source_name": "FDA", "tier": "T1", "cite_count": 4},
      {"source_id": "sec_edgar", "source_name": "SEC EDGAR", "tier": "T2", "cite_count": 1},
      {"source_id": "pubmed", "source_name": "PubMed", "tier": "T3", "cite_count": 2},
    ]

Sort: tier ASC (T1 first → highest authority), `cite_count` DESC,
`source_name` ASC. Stable so the strip can render before streaming
finishes.

Source resolution:
1. Explicit `source_name` / `source_tier` on the evidence record
   (BE-1 fields) take precedence.
2. Otherwise the BE-1 source registry
   (`lookup_source_metadata(source_id)`) fills both.
3. Records without a resolvable source still surface as
   `source_id="unknown"` so the strip never silently drops items.

## 3 · Acceptance

- [x] One bucket per unique `source_id` with cumulative
      `cite_count`.
- [x] Tier inherited from explicit field or BE-1 registry.
- [x] Sort order: tier (T1→T4), cite_count desc, name asc.
- [x] Unknown sources surface as `unknown`.
- [ ] Chat handlers wire the helper into their response payloads
      (tracked as BE-18-FU1).
