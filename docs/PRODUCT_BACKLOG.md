# Product Backlog — Market Zero

> **Single source of truth for product / feature / bug / infra work.**
>
> Refreshed **2026-05-10** to reflect the 12-epic / 24-week plan from the
> design review (`design-review-output/`). Replaces the 74 unfiltered
> consolidator rows from Loop #3.
>
> **Strategic frame:** the backend is category-defining; the next 24 weeks
> ship the experience to match. *Stop adding specs; finish the experience
> of the specs we have.* See [`design-review-output/design-strategy.md`](../design-review-output/design-strategy.md).
>
> - **Cross-agent coordination** lives in [`docs/AGENT_BACKLOG.md`](AGENT_BACKLOG.md).
>   Backend asks here are mirrored there with concrete instructions (BE-1 through BE-41).
> - **User-feedback queue** is cron-managed at [`feedback/live_user_feedback.md`](../feedback/live_user_feedback.md).
> - **Each spec** lives at `specs/SPEC_NNN_*.md`; this file references it.
> - **Design review source** for everything below: `design-review-output/enhancement-backlog.md` (12 epics, ~36 stories, ~120 tasks).
>
> **Validation:** `python -m scripts.validate_product_backlog` (must exit 0).
> **Dashboard refresh:** `python -m scripts.validate_product_backlog --regenerate-summary`.
> **Status taxonomy:** `proposed | triaged | blocked | in-progress | shipped | archived | wontfix`.
> See [SPEC-042 §4.2](../specs/SPEC_042_centralized_product_backlog.md).

## Dashboard (regenerated 2026-05-10)

| Status        | Count |
|---------------|-------|
| in-progress   | 2     |
| triaged       | 60    |
| blocked       | 0     |
| proposed      | 0     |
| shipped (90d) | 0     |

## Currently in flight (2)

- [PB-001] SPEC-041 User Feedback Loop · in-app widget + autonomous triage — frontend-claude / PR #35
- [PB-002] SPEC-042 Centralized Product Backlog — frontend-claude / SPEC-042

## 24-week sequencing — design-review plan

| Weeks | Epic | Outcome | Stories | First open PB |
|---|---|---|---|---|
| 1–2  | E1 · Trust foundation | 4 critical heuristic findings closed | 4 | PB-101 |
| 3–4  | E2 · Live agent presence | 3 named agents felt across surfaces | 4 | PB-201 |
| 5–7  | E3 · Entity dossier | Spine surface; brief composition speed lifts | 5 | PB-301 |
| 8–10 | E4 · Brief composer | Writing-first replaces 5-panel form | 5 | PB-401 |
| 11–12| E5 · War-game cockpit | Payoff matrix + adversary twins · the WOW surface | 5 | PB-501 |
| 13–14| E6 · Chat surface upgrade | Wire ConversationMemory + 6 metadata patterns | 6 | PB-601 |
| 15   | E7 · Graph as interlocutor | Ask-this-subgraph + saved subgraphs | 4 | PB-701 |
| 16–17| E8 · Data catalog view | Replaces /connectors raw JSON | 9 | PB-801 |
| 18–21| E9 · Phase 1 connectors | 8 free public sources close largest unfed KBQ gaps | 8 | PB-901 |
| 22   | E10 · Source registry + FAIR | Quality scoring + licence health surfaced | 3 | PB-A01 |
| 23   | E11 · Multi-tenancy enforcement | **CRITICAL** SaaS-blocker fix | 3 | PB-B01 |
| 24   | E12 · Prompt registry + active feedback | Closes the learning loop | 3 | PB-C01 |

**Epic IDs:** PB-1XX = E1, PB-2XX = E2, …, PB-CXX = E12.

## Recently shipped (last 90 days)

These have spec status = `Shipped`. Listed for context; not in the active queue.

| Spec | Title | Date | Surfaces |
|---|---|---|---|
| SPEC-022 | Cockpit design system | 2026-05-09 | tokens, primitives |
| SPEC-023 | Decision Briefs (backend) | 2026-05-09 | API + state machine |
| SPEC-024 | Evidence Ledger | 2026-05-09 | claims + evidence + snapshots |
| SPEC-026 | LLM Gateway + Prompt Registry | 2026-05-09 | telemetry + prompt versioning |
| SPEC-027 | Source Registry | 2026-05-09 | 5-dim quality scoring |
| SPEC-028 | War-Game Adversaries | 2026-05-09 | 4 adversary kinds + grounding |
| SPEC-029 | App-wide Aesthetics Upgrade (umbrella) | 2026-05-09 | shipping per child loop |
| SPEC-030 | Decision Workspace v2 | 2026-05-09 | 5-panel surface (PR merged) |
| SPEC-031 | Materiality Scoring | 2026-05-09 | factor-attributed v1 |
| SPEC-035 | Ask-Graph (backend) | 2026-05-09 | endpoint shipped |
| SPEC-041 | User Feedback Loop | 2026-05-10 | widget + cron (PR open) |
| SPEC-042 | Centralized Product Backlog | 2026-05-10 | this file (PR open) |

## Items by epic

### E0 — Currently in flight

#### [PB-001] SPEC-041 User Feedback Loop · in-app widget + autonomous triage
- **Type**: feature
- **Status**: in-progress
- **Priority**: high
- **Owner**: frontend-claude
- **Source**: spec
- **Source ref**: PR #35
- **Blocked by**: n/a
- **Created**: 2026-05-09
- **Last touched**: 2026-05-10
- **Notes**: Floating pill on every authenticated surface. Diagnostics + screenshots + 6 categories. 45-min autonomous triage cron. Stage 7 closed; awaiting merge.

#### [PB-002] SPEC-042 Centralized Product Backlog
- **Type**: docs
- **Status**: in-progress
- **Priority**: high
- **Owner**: frontend-claude
- **Source**: spec
- **Source ref**: SPEC-042
- **Blocked by**: n/a
- **Created**: 2026-05-09
- **Last touched**: 2026-05-10
- **Notes**: This file. Loop #3 shipped the consolidator + 158 file moves. Loop #4 (this commit) refreshed the body with the design-review 12-epic plan + filed BE-1..41 as backend asks in AGENT_BACKLOG.

### E1 — Trust foundation (weeks 1–2 · highest priority)

> **Why first:** four critical heuristic findings block Maya from doing her job today. All four are 2-week eng-only fixes. Before any new product surface ships, these go.

#### [PB-101] Evidence cards · replace opaque IDs with real evidence
- **Type**: feature
- **Status**: triaged
- **Priority**: urgent
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E1.S1.1
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Replace `EvidenceStack.tsx` (currently renders only doc_id strings) with EvidenceCard primitive showing source name + favicon + tier badge + date + 2-line snippet. Backend extends `evidence_records` schema (see AGENT_BACKLOG#BE-1). Closes Phase 3 finding C1 (critical).

#### [PB-102] Entity picker · replace UUID input with knowledge-graph autocomplete
- **Type**: feature
- **Status**: triaged
- **Priority**: urgent
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E1.S1.2
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: New `EntityCombobox` primitive (reusable in 5+ places). Replaces `entity_id (UUID)` text input in WatchlistTab "Add" form. Backend asks: verify `/search/suggest` returns name + type + connection_count. Closes finding C2 (critical).

#### [PB-103] Materiality factor breakdown drawer
- **Type**: feature
- **Status**: triaged
- **Priority**: urgent
- **Owner**: frontend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E1.S1.3
- **Blocked by**: PB-104b
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: New `MaterialityDrawer` component. Click any materiality score → drawer with 4 factors (source_tier, entity_criticality, claim_type, recency) showing input/value/weight/contribution + formula. Backend already produces factors via `services/materiality.py:score()`. Closes finding C4 (critical). DEPENDS ON PB-104b (production scores all show 1% — needs diagnostic first).

#### [PB-104] Multi-select KBQ chips · the 2-hour bug fix
- **Type**: bug
- **Status**: triaged
- **Priority**: high
- **Owner**: frontend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E1.S1.4
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: `KBQFilter.tsx:1-53` — toggle logic clears all other chips on click. Should be additive multi-select with URL sync (`?kbq=KBQ-3,KBQ-1`). Backend already supports any-of matching. Closes finding H2 (high). 2-hour fix.

#### [PB-104b] DIAGNOSTIC · production materiality scores all show 1%
- **Type**: bug
- **Status**: triaged
- **Priority**: urgent
- **Owner**: backend-claude
- **Source**: agent-ask
- **Source ref**: AGENT_BACKLOG#BE-2
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Live walk on 2026-05-09 found every materiality score on production renders as 1%. Either the scorer isn't running on new ingestion, or the factor weights are misconfigured, or the response shape changed. Investigate `services/materiality.py` + the ingestion pipeline. Required before PB-103 (drawer UI) ships.

### E2 — Live agent presence (weeks 3–4)

> **Why now:** the platform claims "agentic intelligence" but `AgentStatusBar` shows a static "Monitoring · 3 agents" label. Three named agents (Sentinel · Strategist · Curator) need to be visible across all surfaces with current activity, last action, and addressable nudges.

#### [PB-201] Agent identity · name them, give them roles
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E2.S2.1
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Three named agents with consistent glyphs across surfaces — Sentinel (SE / teal · Sense), Strategist (ST / violet · Frame+Simulate), Curator (CU / green · Learn+Recalibrate). New `AgentGlyph.tsx` primitive. Backend tags `/agent/events` with `agent: "sentinel"|"strategist"|"curator"` field (BE-3). Phase 8 verification mandates noun form (not verb form).

#### [PB-202] Agent activity feed · show what each agent is doing now
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E2.S2.2
- **Blocked by**: PB-201
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Live activity stream per agent (3-5s updates), each event with timestamp + kind + activity text + entity refs. SSE with reconnect + polling fallback. Backend: new `GET /agents/stream` SSE endpoint (BE-4). New `AgentRail` (refactored from AgentStatusBar) + `lib/sse.ts` utility. Closes Phase 5 G2.

#### [PB-203] Agent nudges · address an agent
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E2.S2.3
- **Blocked by**: PB-202
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Per-agent nudge intents — Sentinel (watch / ignore / boost source), Strategist (rerun sim / draft counter), Curator (explain score / mark outcome verified). Backend: new `POST /agents/{agent}/nudge` endpoint + intent registry at `services/agent/nudge_intents.py` (BE-5). Frontend: `NudgeMenu.tsx`.

#### [PB-204] Agent degradation visibility
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: frontend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E2.S2.4
- **Blocked by**: PB-202
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Failed/paused state on agent card with reason + retry affordance + escalate-to-steward link. Honest negative-space — empty feed must distinguish "nothing happened" from "agent is broken".

### E3 — Entity dossier (weeks 5–7)

> **Why now:** Maya thinks in entities; the product surfaces in queries/signals/briefs/rooms. The dossier is the highest-leverage missing surface — the spine that makes brief composition take 45min instead of 3hr.

#### [PB-301] Dossier route + three-column layout
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E3.S3.1
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: New `/dossier/{entity_type}/{slug-or-id}` route. Three columns: identity rail · synthesis main · evidence pile. entity_type ∈ { drug, company, mechanism, trial, therapeutic_area }. Backend: `GET /dossier/{type}/{slug}` composer endpoint that joins existing endpoints (BE-6). Closes Phase 5 G1.

#### [PB-302] Dossier synthesis with inline citations
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: frontend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E3.S3.2
- **Blocked by**: PB-301, PB-603
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: `services/llm.py::synthesize_dossier()` already exists. Frontend renders inline citations as numbered tier-coloured chips → click jumps to evidence card → hover shows source/date/snippet. Owner can edit inline. Reuses CitationChip from PB-603.

#### [PB-303] Dossier recent-moves timeline
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E3.S3.3
- **Blocked by**: PB-301
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: 30-day reverse-chronological timeline of signals + state transitions. Reusable `Timeline.tsx` primitive (also used in war-game evidence stream). Backend: include `recent_moves[]` in dossier composer (BE-6 sub-task).

#### [PB-304] Dossier evidence pile
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: frontend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E3.S3.4
- **Blocked by**: PB-101, PB-301
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Right-column up-to-3 evidence cards inline + "+N more" expand. Reuses EvidenceCard from PB-101. Source-tier badge variants reflect spec §8.3 4-tier model.

#### [PB-305] Dossier watching analysts + add-to-watchlist
- **Type**: feature
- **Status**: triaged
- **Priority**: low
- **Owner**: frontend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E3.S3.5
- **Blocked by**: PB-301, PB-102
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Face-stack of up-to-4 analyst avatars + "+N". Add-to-watchlist button reuses entity picker (PB-102). viewer can see, uploader+ can watch.

### E4 — Brief composer (weeks 8–10)

> **Why now:** the current `DecisionWorkspace` (5-panel composite) feels like Jira on first contact, three of the five panels are placeholders. Maya writes briefs by writing — the composer should be a document editor with inline AI suggestions, not a form.

#### [PB-401] Writing-first editor (TipTap)
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: frontend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E4.S4.1
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: TipTap/ProseMirror editor with custom marks for `{{cite:doc_id}}` (citations), `{{entity:slug}}` (entity mentions), AI suggestions (inline cards). Autosave 4s to `/decision-briefs/{id}`. State machine runs underneath, surfaced in slim sidebar. Pivot from current 5-panel `DecisionWorkspace.tsx`.

#### [PB-402] Inline AI suggestions
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E4.S4.2
- **Blocked by**: PB-401
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Strategist runs every 6s in background (recommend inline edits — add counter, name missing stakeholder, surface contradicting evidence); Curator scores evidence completeness 0-5 + offers one-click insert. Suggestions render as inline cards in document flow (not sidebar). Backend: new `services/brief_suggestions.py` + `POST /decision-briefs/{id}/suggest` (BE-7).

#### [PB-403] Options grid as in-doc primitive
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: frontend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E4.S4.3
- **Blocked by**: PB-401
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Decision options as a small structured grid INSIDE the editor (TipTap node). Recommended-state highlight (green border + box-shadow). Scoreline per option. Backend `POST /decision-briefs/{id}/options` already exists.

#### [PB-404] Slim sidebar (stakeholders / materiality / state)
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: frontend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E4.S4.4
- **Blocked by**: PB-401, PB-103
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Right sidebar with 3 cards — Stakeholders (round-robin scheduler), Materiality (reuses PB-103 drawer), State (state machine progress + next-action button).

#### [PB-405] Migration from legacy DecisionWorkspace
- **Type**: refactor
- **Status**: triaged
- **Priority**: medium
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E4.S4.5
- **Blocked by**: PB-401, PB-403
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: In-flight briefs read-only in legacy mode after week 8. Auto-migration script preserves state + maps option editor entries to options-block. Rollback path via composer→legacy.

### E5 — War-game cockpit (weeks 11–12 · the WOW surface)

> **Why now:** the current `WarRoomView` is a stack of dropdowns — a form, not a board. The cockpit prototype shows what continuous, collaborative war-game looks like with adversary digital twins, payoff matrix, posterior bars, and the authority spectrum.

#### [PB-501] Payoff matrix view (2×2)
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E5.S5.1
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: 2×2 matrix with delta% + confidence + recommended highlight per cell. Win green / neutral amber / lose red. `services/game_theory.py::run_bayesian()` already does 1,200 Monte Carlo. Backend: `POST /war-rooms/{id}/payoff-matrix` composer (BE-8) + `services/simulation/payoff.py`. Closes Phase 5 G4.

#### [PB-502] Adversary digital twins · posterior side panel
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E5.S5.2
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: 6 adversary twins (Pfizer, Lilly, AZN, FDA, Payer, KOL), each with behavioural posterior. Posterior renders as colour-coded bars (aggressive/defensive/cash-constrained). "What shifted this?" log of last 5 evidence updates. Backend: new `services/adversary_twin.py` + `GET /adversaries/{id}/posterior` (BE-9, BE-10). SPEC-028 grounding rules apply.

#### [PB-503] Live cockpit · agent thinking-stream
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E5.S5.3
- **Blocked by**: PB-501, PB-502, PB-202
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: New full-page `/war-game-cockpit` route. Strategist's reasoning steps live (done/now/queued). Sentinel + Curator panels show subscriptions. 8 stress-test variants beside baseline (flip vs hold). Override sliders re-run sim in seconds. Backend: SSE `GET /war-rooms/{id}/cockpit-stream` (BE-11).

#### [PB-504] Authority spectrum · 5 levels
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E5.S5.4
- **Blocked by**: PB-503
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: 5-level authority spectrum (L1 watch / L2 suggest / L3 recommend / L4 act-with-notice / L5 auto-audit) per scenario type. Earned promotion: ≥0.70 calibration over 14 scenarios → eligible for L3. Backend: new `services/agent/authority.py` + `api/routes/agent_authority.py` (BE-12, BE-13).

#### [PB-505] Delegation · "run while I sleep"
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E5.S5.5
- **Blocked by**: PB-503, PB-504
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Queue scenario in morning, read verdict at 7am. Backend: scheduled run executor (BE-14). Morning Pulse "delegated verdict" card with diff vs baseline. Replayable end-to-end.

### E6 — Chat surface upgrade (weeks 13–14)

> **Why now:** ConversationMemory is fully implemented in `services/conversation_memory.py:66-125` but `WorkspacePage.tsx:81-95` builds its own shallow `buildHistory()` instead of calling it. Wiring this in is the single highest-leverage chat fix per the audit. Plus 6 metadata patterns.

#### [PB-601] Wire ConversationMemory across turns
- **Type**: refactor
- **Status**: triaged
- **Priority**: urgent
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E6.S6.1
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: The class is built; just wire it. `WorkspacePage.sendQuery` passes session_id to `/chat`; backend loads ConversationMemory by session_id (BE-15) and feeds prompt assembly. "this drug" / "that competitor" resolves to entity context from prior turns. Branch indicator under user message. The audit's #1 transformative move.

#### [PB-602] Working set rail · entities pinned across the session
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: frontend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E6.S6.2
- **Blocked by**: PB-601
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Left rail of session-touched entities, sorted by recency. `services/conversation_memory.py::get_entities_discussed()` already exists. Pin button keeps entity at top. Click opens dossier in new pane.

#### [PB-603] Citation chips with progressive disclosure
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E6.S6.3
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Citation chip carries source tier in colour (green T1 · blue T2 · violet T3). Hover → source/date/snippet. Click → opens evidence card + highlight. Shift-click → full source. New `CitationChip.tsx` primitive (shared with E3, E4). Backend: ensure tier comes through with citation payload (BE-16).

#### [PB-604] Multidimensional confidence pill
- **Type**: refactor
- **Status**: triaged
- **Priority**: high
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E6.S6.4
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: New `ConfidencePill.tsx` showing composite % + 4 dimension bars (evidence, source diversity, recency, calibration). REPLACES current ConfidenceBadge / CalibrationChip / ImpactBadge inconsistency across surfaces. Backend: ensure 4-dimension breakdown is returned in `synthesize()` (BE-17).

#### [PB-605] Source strip on every answer
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E6.S6.5
- **Blocked by**: PB-603
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Horizontal strip under every assistant message: tier dot + source name + cite count per source. Click filters evidence panel to that source. Backend: aggregate-by-source endpoint (BE-18).

#### [PB-606] Why-this pattern across surfaces
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E6.S6.6
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Small "why this?" button next to anything proactive — Pulse cards, brief proposals, agent suggestions, war-game recs, framing trigger fires. Click → one-paragraph plain-language explanation + deep-link to factor breakdown / source registry / trigger config. Backend: explanation generator (LLM with prompt template) (BE-19).

### E7 — Graph as interlocutor (week 15)

> **Why now:** the graph renders well (Cytoscape, force-directed) but is read-only. The transformative move: select a subgraph and the right panel becomes a chat-like inquiry surface.

#### [PB-701] Ask-this-subgraph panel
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E7.S7.1
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Multi-select on graph nodes (cmd-click + lasso). Right panel "Ask this subgraph" with selection-specific suggestions (shortest path, three-way war-game, evidence on competes_with edges). Routes through `/ask` with subgraph context. Backend: `/ask` accepts `context.subgraph` (BE-20).

#### [PB-702] Edge-type filters as first-class
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: frontend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E7.S7.2
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Edge filters in left rail with colour swatches matching SVG strokes. Per-edge-type counts. `services/graph.py::traverse()` already accepts `link_types`.

#### [PB-703] Saved subgraphs · first-class objects
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E7.S7.3
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: "Save view" captures graph state (centre entity, hops, filters, selection). Versioned. Shareable URL. Backend: new `services/saved_views.py` + CRUD endpoints + `saved_views` table (BE-21).

#### [PB-704] Path-finding result overlay
- **Type**: feature
- **Status**: triaged
- **Priority**: low
- **Owner**: frontend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E7.S7.4
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Selecting 2 entities triggers path computation. `services/graph.py::path_between()` already exists. Result rendered as callout + highlighted edges/nodes. "Find alternatives" affordance.

### E8 — Data catalog view (weeks 16–17)

> **Why now:** the most differentiating asset (15 live connectors + 162k entities) is exposed as raw JSON at `/connectors`. The catalog has to do four jobs: substrate scope (executive), source quality (steward), gap visibility (executive), three personas without clutter.

#### [PB-801] Catalog overview · KPI strip + tier rollup
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E8.S8.1
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: New `CatalogPage.tsx`. KPI strip + per-tier rollup (T1 authoritative · T2 disclosure · T3 scientific · T4 licensed) showing sources / records / freshness / FAIR. Backend: extend `/catalog/stats` with tier-rollup data (BE-22).

#### [PB-802] KBQ readiness strip
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: frontend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E8.S8.2
- **Blocked by**: PB-801
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: 8 KBQ tiles with score 1-5 + colour-coded bottom border. Click opens per-KBQ detail (which sources feed it, which missing).

#### [PB-803] Ingestion activity stream + 24h health gauge
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E8.S8.3
- **Blocked by**: PB-801
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Activity stream (timestamp + source + outcome + record count + drift flag). 24h health gauge. Daily breadcrumbs. Backend: aggregate 24h stats endpoint (BE-23).

#### [PB-804] Source detail dive
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E8.S8.4
- **Blocked by**: PB-801
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: New `SourceDetailPage.tsx` with FAIR (5 dimensions per spec §8.3) + KBQ contributions + schedule + schema preview + top entities + recent records. Backend: extend `api/routes/sources.py` with FAIR breakdown + schema endpoint (BE-24).

#### [PB-805] Entity browse · the analyst's view
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: frontend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E8.S8.5
- **Blocked by**: PB-801
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Filterable entity catalog (entity type, quality score, source contributors, recency). Card grid with entity name + quality + source pills + connection count.

#### [PB-806] Coverage gaps + roadmap surface
- **Type**: feature
- **Status**: triaged
- **Priority**: low
- **Owner**: frontend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E8.S8.6
- **Blocked by**: PB-801
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Roadmap timeline (15 NOW + 8 P1 + 6 P2 + 7 P3 + 7 P4 = 43 future). Per-phase + per-KBQ closure rendering.

#### [PB-807] Licence health panel
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E8.S8.7
- **Blocked by**: PB-801
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Per-source row: annual cost · renewal date · health pill. Total today · projected after Phase 2. Backend: licence model in source registry (BE-25).

#### [PB-808] BYOD + connector marketplace
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: frontend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E8.S8.8
- **Blocked by**: PB-801
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Three doors (drop file, browse roadmap & vote, open SDK). Pending requests queue with vote counts.

#### [PB-809] Decommission /connectors raw JSON
- **Type**: refactor
- **Status**: triaged
- **Priority**: medium
- **Owner**: backend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E8.S8.9
- **Blocked by**: PB-801
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Move JSON response to `/api/connectors`; `/connectors` 301-redirects to `/catalog`. (BE-26)

### E9 — Phase 1 connectors · 8 free public sources (weeks 18–21)

> **Why now:** eight free public sources close major pieces of KBQs 4, 7, 8, 10 with engineering-only cost. No licence negotiation, no recurring spend.

#### [PB-901] USPTO PatentsView API connector
- **Type**: data
- **Status**: triaged
- **Priority**: high
- **Owner**: backend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E9.S9.1
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: New `connectors/uspto.py`. Closes KBQ-10 Patent. Weekly cron. Add patent entity type to domain pack if not present. (BE-27)

#### [PB-902] EPO Patents (OPS API) connector
- **Type**: data
- **Status**: triaged
- **Priority**: medium
- **Owner**: backend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E9.S9.2
- **Blocked by**: PB-901
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: New `connectors/epo.py`. Closes KBQ-10 (international). (BE-28)

#### [PB-903] bioRxiv + medRxiv preprints
- **Type**: data
- **Status**: triaged
- **Priority**: high
- **Owner**: backend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E9.S9.3
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: New connector with RSS + API. Closes scientific-priority KBQ-4. (BE-29)

#### [PB-904] FDA OPDP warning letters
- **Type**: data
- **Status**: triaged
- **Priority**: medium
- **Owner**: backend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E9.S9.4
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: FDA OPDP scraper + parser. Closes KBQ-3 Regulatory + KBQ-9 Reputational. (BE-30)

#### [PB-905] CMS Medicare Part D formulary files (50 plan files)
- **Type**: data
- **Status**: triaged
- **Priority**: high
- **Owner**: backend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E9.S9.5
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: CMS Part D batch connector. Closes KBQ-8 Access (formularies, PA, step therapy). (BE-31)

#### [PB-906] CMS Medicare B + D pricing files
- **Type**: data
- **Status**: triaged
- **Priority**: high
- **Owner**: backend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E9.S9.6
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: CMS pricing connector. Closes KBQ-7 Pricing (free public alternative to RedBook/FDB until executive cost-benefit). (BE-32)

#### [PB-907] WHO ICTRP global trial registry
- **Type**: data
- **Status**: triaged
- **Priority**: medium
- **Owner**: backend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E9.S9.7
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: WHO ICTRP connector + cross-walk to canonical Trial entity. Closes international trial gap. (BE-33)

#### [PB-908] VA / DoD national formulary
- **Type**: data
- **Status**: triaged
- **Priority**: low
- **Owner**: backend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E9.S9.8
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: VA/DoD formulary connector. Public-payer access gap. (BE-34)

### E10 — Source registry + FAIR scoring (week 22)

> **Why now:** spec §8.3 mandates every source as a tracked entity with multi-dim quality scoring. Today scoring exists in code but isn't surfaced.

#### [PB-A01] Source registry surface
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E10.S10.1
- **Blocked by**: PB-804
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Source registry page (admin/steward) with per-source FAIR detail + editable usage profile (per spec §11.4).

#### [PB-A02] Curator-driven weight learning
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: backend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E10.S10.2
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Outcome-to-weight feedback loop (`services/curator/weight_learning.py`). Weekly recalibration job. Weight-change audit log. (BE-35)

#### [PB-A03] Source health monitoring + graceful degradation
- **Type**: infra
- **Status**: triaged
- **Priority**: medium
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E10.S10.3
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Per-source SLA monitoring. "Missing because" inline message in user-facing answers when a source is degraded. (BE-36)

### E11 — Multi-tenancy enforcement (week 23 · CRITICAL)

> **Why now:** the intelligence-layer audit identified this as a critical gap. `scope_key` exists on `chat_sessions` and `deep_research_jobs` but core entity tables have no `tenant_id` and `services/search.py` does not WHERE-filter by scope. **A misconfigured query returns Pfizer's data inside Roche's session.**

#### [PB-B01] Tenant model in core entity tables
- **Type**: infra
- **Status**: triaged
- **Priority**: urgent
- **Owner**: backend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E11.S11.1
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Add `tenant_id` to drugs/companies/trials/mechanisms. Backfill. NOT NULL constraint after backfill. SaaS-blocker. (BE-37)

#### [PB-B02] Query middleware for tenant isolation
- **Type**: infra
- **Status**: triaged
- **Priority**: urgent
- **Owner**: backend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E11.S11.2
- **Blocked by**: PB-B01
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Inject tenant_id into all WHERE clauses via DB middleware. `services/search.py` + `services/graph.py` tenant filters. (BE-38)

#### [PB-B03] Tenant audit surface + isolation tests
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E11.S11.3
- **Blocked by**: PB-B02
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Tenant audit page (per Ravi prototype m6). Automated cross-tenant isolation tests in CI. Audit trail per tenant (90d retention). (BE-39)

### E12 — Prompt registry + active feedback (week 24)

> **Why now:** prompt_registry table exists and `llm_call_log.prompt_id` is wired, but core system prompts are hardcoded in `services/llm.py:179-250` (the `SYSTEM_PROMPTS` dict). The feedback loop is post-hoc, not active.

#### [PB-C01] Promote system prompts to the registry
- **Type**: refactor
- **Status**: triaged
- **Priority**: high
- **Owner**: backend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E12.S12.1
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Migrate `SYSTEM_PROMPTS` dict to prompt_registry. Update `services/llm.py` to load from registry. Versioning + A/B testing harness. (BE-40)

#### [PB-C02] Active feedback loop
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: backend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E12.S12.2
- **Blocked by**: PB-C01
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Outcome-to-prompt-weight backpropagation per spec §6.5.2. Flagged-prompt rollback flow. Weekly calibration job per prompt. (BE-41)

#### [PB-C03] Prompt registry surface
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E12.S12.3
- **Blocked by**: PB-C01
- **Created**: 2026-05-10
- **Last touched**: 2026-05-10
- **Notes**: Registry page (admin) with per-prompt calibration history + cost + latency trends.

## Out of scope (deferred per `design-strategy.md` §7)

The strategy doc explicitly defers these — they're aspirational, important, and *not* the right thing to build in the next 24 weeks. Listed so we don't re-litigate.

| Item | Defer to | Reason |
|---|---|---|
| Bayesian/Stackelberg/POMDP layer of war-game (SPEC-025) | v2 of E5 | Maths "pending sign-off"; cockpit MVP on stub-reactor first |
| Decision signing with cryptographic provenance (SPEC-034) | When buyer demands it | Premium feature; matters for enterprise/regulated |
| Source Discovery Agent (spec §7.1) | Phase 4 connector roadmap | Impressive but unnecessary while curated source list is small |
| War-game adversary LLM reactor (SPEC-028) | After cockpit MVP | Stub reactor ships first |
| Full Catalog deprecation | Q2 2027 | After dossier proves itself for one entity type (drug) |
| Phase 2 paid connectors (~$670k/yr) | After exec cost-benefit | IQVIA + MMIT + AlphaSense + RedBook — pick order based on TA |
| Multi-tenancy beyond E11 basic enforcement | When needed | Per-tenant pricing, white-labelling — premium |
| Real-time war-room mode (spec §9.1.3) | Phase 4 of original roadmap | Until cockpit single-user proves itself |

## References

- [`design-review-output/design-strategy.md`](../design-review-output/design-strategy.md) — strategic framing (12 sections, 24-week stance)
- [`design-review-output/enhancement-backlog.md`](../design-review-output/enhancement-backlog.md) — 12 epics × ~36 stories × ~120 tasks with acceptance criteria + code refs + prototype refs
- [`design-review-output/prototype/`](../design-review-output/prototype/) — 8 working HTML prototypes
- [`specs/CI_Agent_Reimagined_Spec.md`](../specs/CI_Agent_Reimagined_Spec.md) — north-star vision document
- [`docs/AGENT_BACKLOG.md`](AGENT_BACKLOG.md) — concrete backend asks per epic (BE-1 through BE-41)
