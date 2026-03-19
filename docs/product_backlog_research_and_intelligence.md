# Signal Atlas Product Backlog

## Objective
Elevate the platform into a trusted pharma intelligence workspace with deep research, source-backed reasoning, and decision-support visuals.

## Epic 1: Deep Research Mode
- `P0` Add Deep Research execution mode in chat orchestration.
- `P0` Add optional web enrichment toggle with clear provenance separation.
- `P0` Generate structured research brief output (summary, internal evidence, quantitative signals, gaps, next questions).
- `P1` Add export options (`.md`, `.pdf`) for research briefs.
- `P1` Add long-running job support for large multi-step research tasks.

## Epic 2: Conversational Persistence
- `P0` Save and restore chat sessions from the UI.
- `P1` Add named folders / tags for saved sessions.
- `P1` Add shareable read-only links with signed access.
- `P2` Add server-side persistence and RBAC for enterprise usage.

## Epic 3: Visual Analytics in Chat
- `P0` Return chart specs from backend when structured metrics are available.
- `P0` Render bar/donut insight charts inline with responses.
- `P1` Add chart expansion (full-screen) and CSV export.
- `P1` Add compare mode chart packs (entity A vs entity B).

## Epic 4: Source Trust and Evidence UX
- `P0` Keep evidence source links visible and easy to open from responses.
- `P1` Add source freshness badges (`source date` vs `ingest date`).
- `P1` Add citation confidence scoring in report mode.
- `P2` Add source conflict detection and contradiction flags.

## Epic 5: Graph Explorer Value Lift
- `P1` Add query-to-subgraph generation templates (endpoints, comparators, outcomes).
- `P1` Add graph path explanation cards and node-level evidence rollups.
- `P2` Add scenario canvases for saved graph views tied to research sessions.

## Epic 6: Data Product Dashboard (Admin-ready)
- `P1` Add ingest health by connector and lag monitoring.
- `P1` Add ontology glossary quality checks (aliases, duplicates, stale concepts).
- `P2` Add governance workflows for curated ontology updates.

## Current Sprint Scope (Implemented in this pass)
- Deep Research mode + web toggle in chat.
- Structured report output in assistant responses.
- Saved conversation list with server-backed persistence API (plus local fallback cache).
- Inline insight chart rendering from backend chart specs.
- Async deep-research job API with status polling support.
- Report export endpoint and in-chat Markdown/Text download actions.
