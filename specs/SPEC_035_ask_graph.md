✓ Signed off by Claude
Pending sign-off by Frontend Claude (Ask-Anything overlay consumes this)

# SPEC_035: /ask Graph-Traversal Endpoint

## Goal
Implement spec §9.2.4 "Ask-Anything panel": a persistent NL input that
runs graph traversals over the entity store and returns a graph-shaped
result (`{nodes, edges}`) suitable for direct rendering in the frontend.

## Why now
This is the LAST item in the v2 backlog. The frontend Ask-Anything
overlay has been blocked on a backend that returns graph-shaped (not
flat-list) results. Closing this completes the v2 contract.

## Non-goals (deferred)
- **LLM-driven NL parsing**. This loop ships pattern-matching for ~6
  question shapes; LLM-fallback is a follow-up via SPEC-026 LLMGateway.
- **Cypher / true graph DB**. Today entities are in PostgreSQL with
  entity_links; we use SQL recursive CTEs where graph traversal helps.
- **Auto-correction of typos**. Pattern matcher is strict for now.
- **Per-tenant compartmentalization** of results.

## Recognized question patterns (MVP)

| # | Pattern (regex-style) | What it does |
|---|---|---|
| P1 | `show me {entity_type}s? in {area}` | List entities filtered by therapeutic area |
| P2 | `what {relation} does {entity_name} have\?` | List linked entities by relation |
| P3 | `competitors of {company_name}` | entity_links where link_type='COMPETES_WITH' |
| P4 | `{entity_type}s? approved in (the )?last {N} (days?\|months?\|years?)` | Temporal filter |
| P5 | `find {entity_type}s? targeting {mechanism_name}` | mechanism-keyed lookup |
| P6 | `who sponsors {drug_name}` | drug → company link |

Patterns are tried in order; first match wins. Unmatched questions
return `{ status: 'unmatched', suggested_templates: [...] }` rather than
guessing — the frontend can render the suggestions list.

## Output shape

```json
{
  "question": "show me drugs in oncology",
  "matched_pattern": "P1",
  "intent": {
    "kind": "filter_entities",
    "entity_type": "drug",
    "filter": {"therapeutic_area_id": "oncology"}
  },
  "graph": {
    "nodes": [
      {"id": "drug-1", "type": "drug", "label": "Tirzepatide", "props": {...}},
      ...
    ],
    "edges": [
      {"source": "drug-1", "target": "ta-oncology", "type": "in_area"},
      ...
    ]
  },
  "result_count": {"nodes": 14, "edges": 14},
  "latency_ms": 87,
  "executed_sql_summary": "SELECT FROM drugs WHERE therapeutic_area_id=...",
  "ask_query_id": "uuid"
}
```

`graph.nodes[].id` is deep-linkable: frontend constructs entity URL from
`{type, id}` (e.g. `/entities/drug/drug-1`).

## Data contract

### Table: `ask_query_log`
Append-only telemetry.

| Column | Type | Notes |
|---|---|---|
| `ask_query_id` | UUID PK | gen_random_uuid() |
| `question` | TEXT NOT NULL | Original NL question (capped) |
| `matched_pattern` | TEXT | `P1`..`P6` or NULL when unmatched |
| `intent_jsonb` | JSONB NOT NULL | parsed intent |
| `result_node_count` | INTEGER NOT NULL DEFAULT 0 | |
| `result_edge_count` | INTEGER NOT NULL DEFAULT 0 | |
| `latency_ms` | INTEGER NOT NULL DEFAULT 0 | |
| `succeeded` | BOOLEAN NOT NULL | |
| `error_message` | TEXT | |
| `user_id` | UUID | who asked |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() | |

## API surface

| Method | Path | Purpose |
|---|---|---|
| POST | `/ask` | Run NL question; persist + return graph (viewer+) |
| GET | `/ask/templates` | List recognized patterns + example questions (viewer+) |
| GET | `/ask/history` | Recent queries by current user (viewer+) |

## Red-team

| # | Vector | Mitigation |
|---|---|---|
| R1 | SQL injection via question | Parameterized; pattern matcher extracts named groups, never inlines |
| R2 | DoS via massive question text | Cap at 500 chars at API layer |
| R3 | Result-size DoS | LIMIT 200 nodes per query |
| R4 | Cross-tenant leak via crafted entity_id | Today's entities are single-tenant; tighten when SPEC-030 lands |
| R5 | Unmatched questions silently get garbage | Service returns `status: 'unmatched'` with suggestions; never guesses |
| R6 | Excessive history retrieval | History capped at 50 entries |
| R7 | Recursive CTE runaway depth | Hard depth cap of 3 hops in any traversal pattern |

## Success criteria
- [ ] Migration 063 applies clean
- [ ] Each pattern recognized + executes correctly
- [ ] Unmatched questions return `unmatched` with suggestions
- [ ] Results return `{nodes, edges}` shape (not flat list)
- [ ] node.id is deep-linkable per spec
- [ ] Telemetry logged on every call
- [ ] Auth: viewer+ on all endpoints
- [ ] Tests cover patterns + unmatched + auth + red-team

## Out of scope
- LLM fallback parsing
- Multi-hop graph search beyond depth 3
- Geographic/temporal-scope inference
