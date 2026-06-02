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

## Dashboard (regenerated 2026-06-01)

| Status        | Count |
|---------------|-------|
| in-progress   | 5     |
| triaged       | 103   |
| blocked       | 0     |
| proposed      | 0     |
| shipped (90d) | 8     |

## Currently in flight (5)

- [PB-001] SPEC-041 User Feedback Loop · in-app widget + autonomous triage — frontend-claude / PR #35
- [PB-002] SPEC-042 Centralized Product Backlog — frontend-claude / SPEC-042
- [PB-1301] Reskin remaining /ci tabs to Helix (consistency pass) — frontend-claude / n/a
- [PB-E05] Evidence drill-through — claims to source records — shared / adhoc
- [PB-H07] Dossier — competitor threat assessment in competitive domain — backend-claude / adhoc

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

**Epic IDs:** PB-1XX = E1, PB-2XX = E2, …, PB-CXX = E12. PB-13XX = E13, PB-EXX = E14.

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
- **Status**: shipped
- **Priority**: high
- **Owner**: frontend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E1.S1.4
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-11
- **Notes**: Closed by Loop #5. `KBQFilter` now multi-select with URL sync (`?kbq=financial,regulatory`); backend accepts CSV any-of. 7 vitest + 3 pytest cases added. Spec at `specs/SPEC_PB_104_multiselect_kbq_chips.md`.

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
- **Status**: shipped
- **Priority**: high
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E2.S2.1
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-11
- **Notes**: Frontend half shipped via Loop #8 (AgentGlyph + AgentIdentityStrip primitives + 11 tests + mounted in CIPage sidebar). Three named agents (Sentinel teal, Strategist violet, Curator green) with noun-form aria-labels for Phase 8 compliance. Status dots wire to SSE via PB-202 (BE-4 PR #51). Spec at `specs/SPEC_PB_201_agent_identity_strip.md`.

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
- **Status**: shipped
- **Priority**: high
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E3.S3.1
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-11
- **Notes**: Frontend scaffold shipped via Loop #6; mock data swapped to live BE-6 endpoint in Loop #9 (PR #57 merged 2026-05-11). `adaptDossierResponse` maps the wire shape onto the frontend `Dossier` type. Banner removed. Spec at `specs/SPEC_PB_301_dossier_scaffold.md` + `specs/SPEC_LOOP_9_swap_mocks_to_real.md`.

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
- **Status**: shipped
- **Priority**: high
- **Owner**: frontend-claude
- **Source**: spec
- **Source ref**: legacy:design-review-E4.S4.1
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-11
- **Notes**: Scaffold shipped via Loop #15 (TipTap installed, `/briefs/new` route, `CitationMark` + `useBriefAutosave` hook + mock-data banner + 5 tests). Backend save lands via BE-19 (PR #46) — swap is one line in `useBriefAutosave.persistDraft`. PB-402/403/404/405 build on top. Spec at `specs/SPEC_PB_401_brief_composer_scaffold.md`.

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
- **Status**: shipped
- **Priority**: high
- **Owner**: shared
- **Source**: spec
- **Source ref**: legacy:design-review-E5.S5.1
- **Blocked by**: n/a
- **Created**: 2026-05-10
- **Last touched**: 2026-05-11
- **Notes**: Frontend scaffold shipped via Loop #7; mock data swapped to live BE-8 endpoint in Loop #9 (PR #59 merged 2026-05-11). `adaptPayoffResponse` reshapes the backend's 2D `cells[][]` + index-pair recommendation into the flat frontend shape. Banner removed. Spec at `specs/SPEC_PB_501_payoff_matrix_scaffold.md` + `specs/SPEC_LOOP_9_swap_mocks_to_real.md`.

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

### E13 — Agentic CI cockpit (the future direction)

> **Why:** the `/ci` tabs are a BI-dashboard paradigm — a feed of signals + manual
> buttons where the human is the engine. The agentic future (already half-built in
> `/bridge` + the 3 agents + `game_theory`) inverts this: agents sense → frame →
> simulate → recommend; the human steers and judges. Run order (per product owner):
> **PB-1301 → PB-1302 → PB-1303.**

#### [PB-1301] Reskin remaining /ci tabs to Helix (consistency pass)
- **Type**: feature
- **Status**: in-progress
- **Priority**: high
- **Owner**: frontend-claude
- **Source**: roadmap
- **Source ref**: n/a
- **Blocked by**: n/a
- **Created**: 2026-05-22
- **Last touched**: 2026-05-22
- **Notes**: Sensing Feed + Signals DB + KBQ Dossier already on Helix (left-rail cards, OKLCH category hues, Instrument Serif + JetBrains Mono, no boxes — `src/lib/helix.ts`). Reskin the rest for a consistent cockpit: Watchlist, War Rooms, Decisions, Insights, Reviewer, sidebar/shell. Reskin to *consistent & quiet* (evidence layer), not hero-level — the agentic flow is the hero (PB-1303).

#### [PB-1302] Agentic-UX design doc (HTML) — Moments → war-game → commit
- **Type**: docs
- **Status**: triaged
- **Priority**: high
- **Owner**: frontend-claude
- **Source**: roadmap
- **Source ref**: n/a
- **Blocked by**: PB-1301
- **Created**: 2026-05-22
- **Last touched**: 2026-05-22
- **Notes**: Self-contained HTML (like `docs/ci-strategy-roadmap.html`). Specifies the agentic workflow: open to **Moments** (agent-sensed + framed), agent-drafted options + pre-run war-games, **conversational steering** ("re-run assuming Novo cuts WAC 50%"), commit + learn. Define the 3 agent roles' surfaces, the conversational model, and the war-game **mode toggle** (PB-1303). Mark reused (`game_theory.py`, `war_game_adversary.py`, `/bridge`, agents) vs new. Inputs needed flagged for Amit/Riya.

#### [PB-1303] Agentic war-game flow with mode toggle
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: shared
- **Source**: roadmap
- **Source ref**: n/a
- **Blocked by**: PB-1302
- **Created**: 2026-05-22
- **Last touched**: 2026-05-22
- **Notes**: Wire Moment → agent-drafted Decision Brief → **conversational multi-agent war-game** → commit → learn; make `/bridge` the primary surface, demote tabs to evidence layer. **War-game is a mode toggle** (product-owner requirement): (1) **Autonomous** — adversary agents self-analyse and report back with a full reasoning trace; humans take decisions where needed. (2) **Hybrid workshop** — human/AI team, a human can take an adversary seat (red-team). (3) **Game-theory** — `services/game_theory.py` Monte Carlo/Bayesian as the computational substrate *underneath* mode 2. Adversaries (competitor/payer/FDA/KOL) grounded in the knowledge graph. Builds on critical-path ④ (signal→framing) + ⑤ (learn loop) from `ci-strategy-roadmap.html`.

### E13b — Shape additions from the critical-analysis review

> **Source:** `docs/ci-critical-analysis.html` (2026-05-22) — an independent red-team
> that adopts our plan as the spine and adds shape at four seams + two sequencing
> nudges. **Tensions resolved (defaults adopted):** (1) agents default to **L2
> "suggest"**, not L3 "recommend", until calibration earns promotion; (2) war-game
> **always escalates to a human on commit** in v1; (3) hierarchy is **Moment = the
> morning trigger · KBQ view = a section of every Dossier · Signal = the substrate**,
> connected by the dossier.

#### [PB-1304] Dossier-as-spine composition contract
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: shared
- **Source**: roadmap
- **Source ref**: n/a
- **Blocked by**: PB-1307
- **Created**: 2026-05-22
- **Last touched**: 2026-05-22
- **Notes**: The dossier is the *persistent object every surface writes into*, not just surface #3. Section-level update contract (`POST /dossier/{id}/section/{id}/update` with `source: signal|wargame|decision|learn`, `by_agent`, `trace_id`); dossier renders as a composition of typed sections (extracted / kbq / synthesized / computed) each with coverage + last_refresh + evidence_ids. Adds one story to E3 (§7.2). Without it surfaces drift apart.

#### [PB-1305] Trace + steer schema
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: shared
- **Source**: roadmap
- **Source ref**: n/a
- **Blocked by**: n/a
- **Created**: 2026-05-22
- **Last touched**: 2026-05-22
- **Notes**: Structured trace events (id, parent_id, ts, agent, event_kind ∈ {belief_update, option_considered, option_eliminated, simulation_run, evidence_consulted, recommendation_rendered, moment_clustered, section_updated, attribution_landed}, inputs, reasoning{model,prompt_id}, output, surface_ref, user_visible). `POST /wargame/{id}/steer { instruction, mode, seats? } → {rounds, ev_by_option, belief_delta, recommendation, trace[]}`. **Land the trace data structure early (E2)** even if UI surfaces it later — cheap to capture, expensive to retrofit (§8.4/8.5).

#### [PB-1306] Twin ↔ Game-Theory pipeline
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: backend-claude
- **Source**: roadmap
- **Source ref**: n/a
- **Blocked by**: PB-1307
- **Created**: 2026-05-22
- **Last touched**: 2026-05-22
- **Notes**: The Twin's belief posteriors *are* the Bayesian priors the game-theory layer needs — one pipeline, not two things. `Twin priors → adversary objective functions → payoff matrix → equilibrium → recommendation → Twin posterior update`. `services/twin.py` (belief states w/ drivers + provenance) feeds `services/game_theory.py::solve_game(twin_priors, adversary_objectives, scenario_topology, payoff_estimates)`. Adversary objective fns need analyst input (decision G). §9.3/9.4.

#### [PB-1307] Facts ledger ⓪ — pulled forward (parallel with E3)
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: backend-claude
- **Source**: roadmap
- **Source ref**: n/a
- **Blocked by**: n/a
- **Created**: 2026-05-22
- **Last touched**: 2026-05-22
- **Notes**: Temporal, append-only `facts` table: kind ∈ {point, interval, anticipatory}, predicate, subject_entity, object_value JSONB, valid_from/to, asserted_at, source_doc_id→evidence_records, confidence, superseded_by, tenant_id, created_by. **Anticipatory facts** (e.g. "Novo WAC = $675 effective 2027-01-01", valid_from in future) are what let the war-game query state *as-of a target date*. Reviewer's nudge: **pull forward to run parallel with the dossier (weeks 5–10)** — dossier + war-game both depend on it. §9.1.

> **Sequencing nudges adopted:** (a) PB-1307 facts ledger pulled forward (parallel E3); (b) PB-1303 conversational war-game folds **into E5 war-game cockpit** (the cockpit without steering is half a war-game) — not separate E13 work; (c) multi-tenancy (E11) stays week 23 unless an external-customer commitment lands in 6 months.

> **Decisions still needed** (consolidated, beyond the 11 already in the strategy + agentic-UX docs):
> **A** default authority level (→ L2 suggest, Kapil+strategist) ·
> **B** trace default depth (→ summary + expand, design) ·
> **C** default war-game mode for a cold Moment (→ autonomous w/ trace, escalate on commit, Kapil) ·
> **D** facts-ledger sequencing (→ pull forward, backend+Kapil) ·
> **E** multi-tenancy timing (→ keep week 23 if no external commit, Kapil) ·
> **F** dossier-as-composition sign-off (→ adopt §7.2, backend+frontend) ·
> **G** adversary objective functions per top-5 competitor (→ draft from data_strategy, 2-line override each, Riya+strategist).

### E14 — Dossier as composition of the knowledge layer (KB remediation)

> **Why:** the dossier is the keystone — good dossiers are what make synthesis,
> scenarios, and war-gaming worth anything. KB1-KB3 (PRs #120/#121) shipped the
> persistence + versioning + UI for the dossier-as-spine vision (PB-1304), but
> `services/dossier_kb.py` assembles from the facts ledger (PB-1307) ONLY,
> ignoring the mature knowledge layer the platform already has (entity_resolver,
> compose_dossier, HybridSearch, GraphTraversal, PharmaMetrics, evidence_ledger).
> Result: a content regression vs. the legacy dossier and an asset-ref bug that
> returns empty dossiers in prod. This epic re-wires the dossier to COMPOSE the
> existing substrate — delivering the PB-1304 contract for real and proving the
> architecture (sensing + knowledge as shared services; CI as one application on
> top). Source analysis: `docs/dossier-kb-status.html` (rev 2); delivery plan:
> `docs/dossier-kb-loop-plan.html`. Each item = one loop:
> SPEC -> DESIGN(reuse-first) -> BUILD(TDD) -> RED-TEAM -> FIX -> LOG -> next.

#### [PB-E01] Resolve engagement asset to canonical entity id
- **Type**: bug
- **Status**: triaged
- **Priority**: urgent
- **Owner**: backend-claude
- **Source**: brainstorm
- **Source ref**: adhoc
- **Blocked by**: n/a
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: `assemble_dossier` passes the raw slug ('wegovy') to `facts_as_of`, but facts are keyed by canonical entity id (event_collector writes subject_entity_id=entity_id). Reuse `integration/entity_resolver` / drugs-table lookup to resolve `engagement.asset` before querying. The single true blocker — dossiers return empty even when the ledger is full. Acceptance: seeded-Postgres integration test returns >=1 non-gap domain.

#### [PB-E02] Compose dossier from compose_dossier + facts (no single-source)
- **Type**: refactor
- **Status**: triaged
- **Priority**: urgent
- **Owner**: backend-claude
- **Source**: brainstorm
- **Source ref**: adhoc
- **Blocked by**: PB-E01
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: `assemble_dossier` should pull from the existing `services/dossier.py:compose_dossier` (signals + evidence_records + entity_links + related entities) AND the facts ledger, normalized into DomainView. Delivers the PB-1304 composition contract; closes the content regression vs. the legacy dossier. Acceptance: parity test — composed dossier covers >= the domains the legacy composer would.

#### [PB-E03] Feed PharmaMetrics into clinical / competitive / pipeline domains
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: backend-claude
- **Source**: brainstorm
- **Source ref**: adhoc
- **Blocked by**: PB-E02
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: Reuse `services/metrics.py:PharmaMetrics` (drug_pipeline_strength, trial_success_rate, evidence_density, competitive_landscape) so quant-backed domains carry real, materialized-view numbers — no hallucinated math. Acceptance: a known drug shows its actual pipeline score in the clinical/pipeline domain.

#### [PB-E04] Competitive breadth via graph analytics + BCB competitive_set
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: backend-claude
- **Source**: brainstorm
- **Source ref**: adhoc
- **Blocked by**: PB-E03
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: Populate the competitive domain with real rivals using `services/graph_analytics.py:competitive_clusters` + `GraphTraversal.neighborhood` + the BCB's competitive_set (not just the focal asset). Acceptance: a competitor appears in the competitive domain with a cited graph edge.

#### [PB-E05] Evidence drill-through — claims to source records
- **Type**: feature
- **Status**: in-progress
- **Priority**: high
- **Owner**: shared
- **Source**: brainstorm
- **Source ref**: adhoc
- **Blocked by**: PB-E02
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: Delivers the anti-hallucination promise: every claim verifiable. **BACKEND SHIPPED (real-DB gated):** `DossierFact.source_url` → `sourceUrl` in `to_dict()`, populated from `object_value.source_url` + signal `source_url`; metformin 480/508 facts (94%) carry one. **FRONTEND SHIPPED (PB-UX03):** clicking a dossier fact opens the `ProvenancePanel` with the source + drill-through link (`sourceUrl` threaded through the DTOs → container → page). The core acceptance is met (clicking a fact opens its source). **REMAINING (deferred enhancement):** for facts backed by `evidence_records` (not just a URL), join the richer evidence snippet via `services/evidence_ledger.py` — tracked here but lower priority than wiring the remaining stages.

#### [PB-E06] Collapse competitor-dossier duplication onto one composed source
- **Type**: refactor
- **Status**: triaged
- **Priority**: medium
- **Owner**: backend-claude
- **Source**: brainstorm
- **Source ref**: adhoc
- **Blocked by**: PB-E04
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: Three entity-picture builders now exist (compose_dossier, war_game_adversary.build_competitor_dossier, dossier_kb). Point `build_competitor_dossier` at the same composed source and deprecate the parallel reads. Acceptance: war-game competitor view == dossier competitive domain for the same entity.

#### [PB-E07] Close dossier to war-game (auto-BCB + facts AS-OF)
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: backend-claude
- **Source**: brainstorm
- **Source ref**: adhoc
- **Blocked by**: PB-E06
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: Auto-populate the BCB from the dossier; feed a dossier snapshot (facts AS-OF the scenario date — temporal capability already in facts_as_of) into the scenario / war-game engines. Closes the keystone -> simulation handoff. Acceptance: a war-game run cites dossier-sourced grounding.

#### [PB-E08] Verify facts-ledger population + real-Postgres integration tests
- **Type**: infra
- **Status**: triaged
- **Priority**: high
- **Owner**: backend-claude
- **Source**: brainstorm
- **Source ref**: adhoc
- **Blocked by**: n/a
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: Run `scripts/backfill_facts.py`, assert facts row count > 0, and add real-Postgres integration tests for dossier assembly (the gate the KB1-KB3 fake-DB unit tests structurally could not provide). Prevents "real" being asserted from fake-DB tests again. Acceptance: SELECT count(*) FROM facts > 0; integration suite green in CI.

### E15 — Helix v8 benchmark parity (CI output gold standard)

> **Why:** the team produced a complete reference demo of the target CI output —
> `Helix_v8_Pharma_Wargaming` (a Novo/CagriSema obesity-launch wargame). It is the
> gold standard for what an engagement should *render*, and it exposes exactly
> where our sensing + knowledge + decision + learn layers fall short of it. The
> benchmark's defining property is a **fully provenance-linked spine**:
> signal → fact → insight → scenario → decision → outcome, with a **Learn loop**
> that re-calibrates scenario probabilities as new signals arrive. Code-grounded
> gap analysis (1 Jun 2026, 4 parallel Explore passes): `docs/helix-v8-benchmark-gap-analysis.html`.
> Layer verdicts — **Sense**: 4/8 source classes full, signals rich (materiality +
> impact) but **no forward-links**. **Dossier**: 8 domains ✓, fact_class ✓, insight
> frames+provenance ✓ — but gaps are state-only, no readiness score, no signal
> back-links, KOLs unwired. **Decide**: decision-brief/ledger/signing strong;
> scenarios deterministic (no probability/provenance), no NPV options, payoff
> matrix 2×2 not 3×3. **Learn**: telemetry + feedback loops + outcome tracking +
> EWMA all WIRED — only scenario calibration missing. Each item = one loop:
> SPEC -> DESIGN(reuse-first) -> BUILD(TDD) -> RED-TEAM(real DB) -> FIX -> LOG -> next.

#### [PB-H01] Signal forward-links — feeds_fact_ids + affects_scenario_ids
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: backend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: n/a
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: Benchmark signals carry `feeds_fact_ids` (dossier facts a signal feeds) and `affects_scenario_ids` (scenarios it re-weights). Our `signals` table (migration 037) is one-directional: event → signal → impact_assessment, no reverse edge. Add the two forward-link columns (additive migration) and populate them from the materiality/impact path. This unblocks both the calibration loop (PB-H14) and evidence drill-through (PB-E05). Acceptance: a seeded signal lists ≥1 fact it feeds and the scenario(s) it affects; integration test asserts the round-trip.

#### [PB-H02] Enable + auto-curate ALL connectable public sources
- **Type**: data
- **Status**: triaged
- **Priority**: high
- **Owner**: backend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-H17
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: USER PRIORITY (1 Jun): "data breadth is key — enable for all connectors we can connect and curate automatically from public sources." Benchmark uses an 8-class source taxonomy. We cover 1 (regulatory) and 3 (SEC filings) fully; 2 (literature/conferences — PubMed/PMC only), 4 (biz news — generic RSS), 6 (payer — NADAC only) partial; 5 (presentations) and 8 (RWD/consumer) missing. Scope: turn on every free/public connector we can, wire each through the unified ingestion hook (PB-H17) so it flows sense→fact→dossier, and let `services/data_steward.py` auto-curate (dedup/normalise/quality-score — it already loops). Sequence: payer (class 6 — drives the most benchmark facts) → conference/literature (class 2) → biz-news specialisation (class 4) → RWD (class 8 public proxies). Reuse `connectors/base.py` + source_registry FAIR scoring. Acceptance: every newly-enabled public connector is registered, health-checked, auto-curated, and lands facts in the ledger.

#### [PB-H03] Document upload + internal/client sources into the spine
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: backend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-H17
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: USER PRIORITY (1 Jun): "ability to add documents and upload to be used to connect like annual reports etc, and then ability to add more data sources that are internal when we do with client." Two channels, both via the unified ingestion hook (PB-H17): (a) DOCUMENT UPLOAD — annual reports, decks, PDFs → facts. The pipeline EXISTS (`connectors/user_document.py` + SPEC_014 NER); this loop verifies it lands facts in the ledger + dossier (not just chunks) and wires the UI. (b) INTERNAL/CLIENT sources (MSL notes, KOL/PBM panels, HCP surveys) — tenant-scoped, `internal`-class facts, the SME/expert-context channel. Acceptance: an uploaded annual report and a sample internal feed each produce dossier facts (tenant-scoped for internal).

#### [PB-H04] Dossier — actionable gaps (text + fill method + importance)
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: backend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-E02
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: Benchmark gaps are actionable: each carries `text` (what's missing), `method` (how to fill — e.g. primary research design), `importance` (high/medium). Our `DossierSnapshot.gaps()` (dossier_kb.py:235) returns state-only `{domain, priority}`. Add a `GapView` (text/method/importance) so the engagement's gaps stage drives real collection priorities. Pure-logic — fully unit-testable. Acceptance: a thin domain surfaces a gap with a human-readable description + fill method + importance; round-trips through the snapshot JSON.

#### [PB-H05] Dossier — per-domain readiness score (0–1)
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: backend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-E02
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: Benchmark shows a per-domain `ready` score (0–1, e.g. 0.85) and rolls it into engagement readiness (87%). We have only a 3-state `state` (gap/in_progress/complete) + an aggregate coverage_score. Add `readiness: float` to `DomainView`, derived from fact count + grounded-class presence + priority weighting (deterministic, no LLM). Pure-logic. Acceptance: a populated domain scores higher than a thin one; aggregate engagement readiness derivable.

#### [PB-H06] Dossier — wire KOLs into clinical domain
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: backend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-E02
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: Benchmark Domain 2 carries KOLs (name, affiliation, sentiment, position, stance). We have an `investigators` entity type + table (migration 040) but `compose_dossier`/`dossier_kb` never query it. Wire investigators linked to the focal asset into the clinical_profile domain as structured KOL content. Acceptance: a drug with linked investigators shows ≥1 KOL in its clinical domain.

#### [PB-H07] Dossier — competitor threat assessment in competitive domain
- **Type**: enhancement
- **Status**: in-progress
- **Priority**: medium
- **Owner**: backend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-E04
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: B5 routes related entities into the competitive domain. Benchmark competitors carry a threat assessment. **PARTIAL (shipped, real-DB gated on metformin):** fixed two competitive-domain QUALITY bugs found running the spine on prod — (1) the generic `market_event` predicate hit the `("market","competitive")` prefix rule, flooding competitive with 505 FDA-recall facts (now routes to wargame_specific; competitive 505→25); (2) `_related_entities` left competitor `name=None` ("FE resolves label"), so rivals rendered as UUIDs — now resolved server-side via `_resolve_related_names` (batch per type, reuses `_TYPE_TO_TABLE`); (3) signal-scenarios no longer spawn from the wargame_specific catch-all (recall noise). (4) NON-DESTRUCTIVE read-time junk filter: `_is_junk_competitor_name` skips placebo/dosage/trial-arm rows (reuses A6's `_should_exclude` + `DOSAGE_PATTERN`, plus a competitive-context arm regex for placebo-suffix / "+ healthy diet" / "treatment for"). Gate: metformin competitive 25→16 (clear junk gone). **REMAINING:** (a) derive + order rivals by a threat score (PharmaMetrics competitive_landscape + edge weight) — the original acceptance; (b) DEEPER residual is entity-consolidation debt — metformin's COMPETES_WITH neighbours are mostly its OWN un-consolidated variant rows ("Metformin group", "metformin intervention", salt forms), not distinct rivals. The read-time filter can't (and shouldn't) whack-a-mole these; the real fix is the A6 DESTRUCTIVE cleanup + `consolidate_drugs` (pending supervised) which merges variants into canonical drugs. Acceptance (remaining): competitive domain orders real rivals by a derived threat score with cited basis.

#### [PB-H08] Dossier — fact signal back-links + confidence enum + insight implication
- **Type**: enhancement
- **Status**: triaged
- **Priority**: medium
- **Owner**: backend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-H01
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: Benchmark facts carry `signal_ids` (back-links to the signals that produced them), confidence as a High/Medium enum, and split src_id/src_label; insights carry an `implication`. We have fact_class ✓ + insight frames+provenance ✓, but confidence is a bare decimal in source_label, no signal back-links, no insight implication. Depends on PB-H01 (signals must carry the forward edge first). Acceptance: a signal-derived fact lists its source signal id; insight renders an implication line.

#### [PB-H09] Scenario as first-class probabilistic object (grounded in dossier facts)
- **Type**: feature
- **Status**: triaged
- **Priority**: urgent
- **Owner**: backend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-E04
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: THE spine keystone. Benchmark scenarios are first-class objects: `prior_prob`, `current_prob`, `calibration_note`, `trigger`, `from_fact_ids` (provenance back to dossier facts), per-team `moves`, NPV-scored `decision_options`. Our `scenario_engine.py` is deterministic what-if (no probability, no provenance); `game_theory.py` has Bayesian runs but no persisted scenario object. DESIGN must reuse-audit scenario_engine / game_theory / war_game_adversary / war_room_rounds before adding a new `scenarios` table (additive). Derive candidate scenarios from the now-rich dossier (B2–B5), each carrying from_fact_ids + an initial prior. Unblocks PB-H14 (calibration). Acceptance: assembling a scenario from a real engagement's dossier yields ≥1 scenario citing the dossier facts that justify it, with a prior probability.

#### [PB-H10] NPV-scored decision options + recommended flag
- **Type**: enhancement
- **Status**: in-progress
- **Priority**: medium
- **Owner**: backend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-H09
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: Benchmark decision_options carry `npv_5yr` + `recommended: bool` + rationale. **PARTIAL SHIPPED (PR #142, services/scenarios.py)**: every derived scenario now carries 3 mutually-exclusive decision options with rationale + exactly one `recommended` (heuristic: high-threat→defend & differentiate, low-threat→segment & defend margin). Validated on live semaglutide. **REMAINING (the NPV half)**: quantitative `npv_5y_dkk_bn` is deliberately left None — fabricating bn-DKK figures without a value model would be dishonest. Needs a real value model (PharmaMetrics-driven or analyst-supplied) before options carry NPV. Acceptance (remaining): a decision option carries an NPV value grounded in a defensible model, not a guessed number.

#### [PB-H11] Move catalog with per-team impact vectors (guided wargaming)
- **Type**: feature
- **Status**: shipped
- **Priority**: low
- **Owner**: backend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-H09
- **Created**: 2026-06-01
- **Last touched**: 2026-06-02
- **Notes**: SHIPPED. Team moves (PR #142) + per-team impact vectors (PR #150): every move now carries an illustrative directional impact per team in [-1,1] (acting team positive; others per strategic logic), rendered as +/- chips with a "structural estimate, not a forecast" tooltip. Real-DB red-team (semaglutide): coherent vectors (Dulaglutide +0.6 / semaglutide -0.4 / Payers +0.1). NOTE: this is a transparent structural estimate, NOT the benchmark's quantitative payoff model; a real value model is PB-H10's deferred NPV half.

#### [PB-H10c] Scenario blocking is too coarse (all scenarios always blocked)
- **Type**: bug
- **Status**: shipped
- **Priority**: medium
- **Owner**: backend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-H09
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: SHIPPED (PR #145). Each scenario now blocked only by high gaps in its own evidence domain(s) (transient Scenario.source_domains) — own-evidence scenarios stay playable; context gaps belong to the gaps stage. Self-matches suppressed (_is_self_competitor). Real-DB red-team (semaglutide): 5→4 scenarios (self-match dropped), all 4 playable. Acceptance met.

#### [PB-H12] 3×3 Nash payoff matrix + Nash reasoning
- **Type**: feature
- **Status**: triaged
- **Priority**: low
- **Owner**: backend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-H11
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: Benchmark PAYOFF_MATRIX is 3×3 (Novo strategies × Lilly strategies), each cell an (npv_a, npv_b) pair, with a computed `nash_cell` + `nash_reasoning`. Our `simulation/payoff.py` builds 2×2 from Bayesian runs (delta_pct, not NPV pairs) and `game_theory.py` does Stackelberg (sequential) not simultaneous Nash. Generalise to N×N, emit NPV pairs, add a simultaneous-move Nash solver + reasoning. Note: SPEC-025 Bayesian/Stackelberg layer was deferred — this revisits it with the benchmark as the concrete target. Acceptance: a 3×3 matrix returns a Nash cell with a textual justification.

#### [PB-H13] Autonomous multi-round war-game play
- **Type**: feature
- **Status**: triaged
- **Priority**: low
- **Owner**: backend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-H12
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: Benchmark AUTONOMOUS_PLAY = a scripted multi-round team-move sequence with narration. We have `war_game_adversary.WarGameOrchestrator` (reactive per-option rounds) but no autonomous campaign that loops the war room through rounds without human prompting. Add an auto-play orchestration over the move catalog + payoff matrix. Acceptance: a war-game run produces a coherent N-round move/counter-move transcript autonomously.

#### [PB-H14] Scenario calibration loop (re-weight probability from new signals)
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: backend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-H09, PB-H01
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: THE Learn-loop gap. Benchmark re-weights `prior_prob → current_prob` as signals arrive, each change carrying a `calibration_note` tracing to the causing signal. Our learn layer is strong and WIRED (telemetry, 3 feedback loops, outcome detection every 1h, EWMA source-accuracy via `learning_service.py`) — but scenario probabilities are never recalibrated. Wire signal arrival (via affects_scenario_ids, PB-H01) → Bayesian update of scenario current_prob (reuse `learning_service.ewma_update`) → write a calibration_note. Closes the flywheel. Acceptance: a new signal affecting a scenario shifts its current_prob and records a calibration_note citing the signal.

#### [PB-H15] SDAL flywheel KPI dashboard (sense / decide / act / learn)
- **Type**: enhancement
- **Status**: triaged
- **Priority**: low
- **Owner**: shared
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-H14
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: Benchmark dashboard ties 4 KPIs to the sense/decide/act/learn loops (signals processed 7d, scenarios under evaluation, decisions committed, calibration updates 7d). We have the underlying data (query_telemetry, war_room_sessions, decisions, learning_runs) + `agents_activity.py` feeds, but no unified loop-keyed KPI surface. Aggregate the four into one dashboard endpoint + view. Acceptance: a dashboard shows one live KPI per flywheel loop, each linking to its detail view.

#### [PB-H16] Agentic narrative synthesis (depth-first, not prose-exact)
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: backend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-H09
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: USER DIRECTION (1 Jun): "for narrative we should get closer using agentic and LLM support but need not be exact — accuracy and depth of intelligence matter more, and quality of the war-game and decision-making is key." So: do NOT chase the demo's hand-authored prose fidelity. Use LLM/agentic synthesis to turn the grounded dossier + scenarios into narrative (scenario triggers, insight implications, decision_output) — but the bar is ACCURACY (every claim traces to a cited fact, no hallucinated numbers — reuse the H2 numeric-grounding discipline) and DEPTH of strategic reasoning / decision quality, not matching the demo word-for-word. Build on `services/llm.py` synthesis + the dossier/scenario provenance; gate with the golden-query eval (I1). Acceptance: scenario narrative + decision_output are LLM-generated, every quantitative claim cites a dossier fact, and a reviewer rates the strategic depth ≥ the templated baseline.

#### [PB-H17] Unified spine ingestion hook (connector / upload / internal → sense layer)
- **Type**: infra
- **Status**: triaged
- **Priority**: high
- **Owner**: backend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: n/a
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: USER DIRECTION (1 Jun): internal/client sources need "easy hooks to connect the data into the spine and the sense layer." The enabler for the whole data-breadth track (H02/H03). Define ONE uniform ingestion contract so any source — a public connector, an uploaded annual report, or an internal client feed — flows the same way: fetch/parse → normalise → resolve entities → embed → store → emit signal/fact → land in the dossier. Reuse + harden what exists: `connectors/base.py` Connector contract, `integration/pipeline.py` (fetch→normalize→resolve→embed→store→cross-link), `integration/pipeline_hooks.py` (PRE_STORE/POST_STORE/ON_NEW_ENTITY) and `services/fact_ingest.py` (event→fact). Deliverable: a documented `register_source()` / ingestion adapter so adding a new feed is a thin plug-in, not a bespoke integration; existing connectors refactored onto it as proof. Acceptance: a new toy source added via the hook lands a fact in the ledger with <50 lines of source-specific code. PARTIAL: the events→facts convergence half shipped as Loop H17a (scheduler post-task, reusing backfill_facts_from_events) — see PB-H18 for the writer bug it surfaced.

#### [PB-H18] Fix market_events writer schema drift (stale columns)
- **Type**: bug
- **Status**: shipped
- **Priority**: high
- **Owner**: backend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: n/a
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: Found while auditing legacy ingestion for H17 (1 Jun). The prod `market_events` table (verified twice via information_schema, 24 cols) has `primary_entity_id/_type/_name`, `source_api`, `drug_id`, `corroborating_sources`, `content_hash` — and does NOT have `entity_id`, `entity_type`, `source_feed`, `payload`, `raw_data`, `disclosed_date`, `source_document_id`, `corroboration_count`. Two writers INSERTed into the dropped columns and threw on prod: `services/event_collector.py:_persist_event` (LIVE — api/app.py:722 every background cycle for news) and `services/db_adapter_8k.py:_EVENT_INSERT_SQL` (→ ZERO 8-K events on prod). **SHIPPED**: both INSERTs aligned to the real 24-col schema (source_api, primary_entity_id/_type, drug_id, corroborating_sources jsonb; NOT NULL event_date/source_url COALESCE'd, retrieved_at NOW(); db_adapter ON CONFLICT now names the partial-index predicate `WHERE event_hash IS NOT NULL`). EventCollector INSERT extracted to module constant `_INSERT_EVENT_SQL` for testability. Regression net `tests/test_market_events_writers_schema.py` pins both writers' columns ⊆ the real schema + required NOT NULL cols present (the net fake-DB tests structurally couldn't provide). REAL-DB GATE PASSED: throwaway insert via each writer on prod — EventCollector row lands (source_api set, event_date defaulted, drug_id set) + fact emitted; db_adapter_8k row lands (partial-index ON CONFLICT works); throwaways cleaned (events DELETEd, append-only smoke fact self-superseded).

#### [PB-H19] Resolve orphaned high-value events → entities (so they become facts)
- **Type**: data
- **Status**: triaged
- **Priority**: high
- **Owner**: backend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: n/a
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: Found 1 Jun chasing data richness. The facts ledger (3,302 active facts) is dominated by `RECALL_CLASS_I` events (34,077, the only event_type with `drug_id` populated). The strategically VALUABLE events — `trial_readout` (255), `approval` (241), `ma_deal` (99), `regulatory_setback` (56), `supply_disruption` (50), `pricing`/`patent_ip`/`safety_signal`/`general` (~1,230 total) — have `primary_entity_id`, `primary_entity_name` AND `drug_id` all NULL, so `event_to_fact` returns None (no subject) and they NEVER become facts. They're pharma-news items whose drug/company is named only in the description (e.g. "FDA approves Lilly's Foundayo (orforglipron)"). Net: dossiers/scenarios miss every approval/trial/deal and see only recall noise — the core data-richness gap. Fix: an enrichment pass that resolves the entity from each orphaned event's description (reuse `integration/entity_resolver` + `domain/pharma/mention_normalizer`; match known drug/company names) → backfill `primary_entity_id`/`drug_id` → run `backfill_facts_from_events`. Likely wire into the EventCollector/news path so future events resolve on ingest (the real fix vs one-off backfill). Acceptance: a known approval event (e.g. Foundayo) resolves to its drug + appears as a fact in that drug's dossier.

### E16 — Engagement experience: personas, collaboration & deliverables

> **Why:** the UX analysis (`docs/ux-analysis-personas-collaboration.html`, companion to
> `engagement-agentic-ux-design.html`) reframes the engagement from a single-user flow into a
> **four-persona team sport** — Knowledge Curator (KC), Strategy Analyst (SA), Decision Maker (DM),
> Engagement Lead (EL) — defined by jobs-to-be-done, **deployment-agnostic** (works for ZS-delivered AND
> client self-service). The shipped frontend wires only the *dossier* stage; the rest are stubs. This epic
> encodes the analysis's phased build: **Foundation** (persona depth + collaboration primitives + provenance
> panel) → **Stage wiring** (the 5 unbuilt stages, with persona depth) → **Collaboration & deliverables**
> (team, activity, export) → **War-room depth & Learn**. Operating model = agent does work → human checkpoint
> → agent advances (per the design doc). Each item = one loop; frontend loops verify via `vite build`/tsc +
> the seeded demo engagement (semaglutide).

#### [PB-UX01] Persona selector + usePersonaDefaults (Foundation P1.1)
- **Type**: feature
- **Status**: shipped
- **Priority**: high
- **Owner**: frontend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: n/a
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: **SHIPPED.** `src/hooks/usePersona.ts`: Persona type (KC/SA/DM/EL), PERSONAS catalog, PRIMARY_STAGES, pure `personaDefaults(persona)` → {defaultStage, primaryStages, stageDepth(full|summary), canSteerAgent, canCommitDecision, canManageTeam}, and `usePersona()` localStorage hook (key `mz_persona`, default EL = hides nothing, cross-tab sync). `PersonaPicker.tsx` (lightweight select). Wired into EngagementDetailContainer: persona-driven default landing stage (explicit ?stage= still wins; never gates nav) + picker rendered. Progressive disclosure, NOT access control. +9 vitest tests (37 hook tests green), tsc clean, vite build OK. The foundation all persona-driven UX builds on; `stageDepth`/`canSteerAgent`/etc. consumed as each stage container ships.

#### [PB-UX02] Generic EntityComments component (Foundation P1.2)
- **Type**: feature
- **Status**: shipped
- **Priority**: high
- **Owner**: shared
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: n/a
- **Created**: 2026-06-01
- **Last touched**: 2026-06-02
- **Notes**: SHIPPED (PR #152). migration 076 entity_comments (target_type+target_id, applied to prod) + services/entity_comments.py (add/list + @mention parse) + new /comments router + reusable EntityComments component (count badge, @mention highlight, post). Comment-based only (no CRDT). Mounted on the brief stage (PB-UX08); mountable on any entity. Real-DB red-team round-trips.

#### [PB-UX03] Provenance side panel (Foundation P1.3)
- **Type**: feature
- **Status**: shipped
- **Priority**: high
- **Owner**: frontend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-E05
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: **SHIPPED.** `ProvenancePanel.tsx` — shared slide-in (claim + confidence-tier glyph/label + source + drill-through link to the shipped `sourceUrl` + fact id; graceful when no URL). Also closed the dossier's "data wired, UI under-exploits it" gap (the analysis flagged this): threaded `sourceUrl` + per-domain `readiness` through the DTOs → `DossierContainer` → `EngagementDossierPage`; added a `ReadinessBar` (TOC card + domain header + engagement-level in the page header + KB-header Readiness stat), a ↗ drill hint on facts with a source, and changed `onOpenFact` to pass the full fact → opens the panel. This also delivers the **frontend half of PB-E05** (every fact now drill-through-able). +5 tests; fixed 2 tests PB-UX01 had left red on main; full suite 862 green, tsc clean, vite build OK.

#### [PB-UX04] Scenarios stage — wire into stepper (Stage wiring P2.1)
- **Type**: feature
- **Status**: shipped
- **Priority**: high
- **Owner**: frontend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-UX01
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: SHIPPED (PR #141). `scenariosApi` (get/assemble, reuses ScenariosPage `Scenario` interface via type-only import) + `ScenariosContainer` (loading→not-derived→ready→error, mirrors DossierContainer) + wired into EngagementDetailContainer scenarios stage. Reuses ProvenancePanel (UX03) for trigger-evidence drill-through; header stats + re-derive. Real-DB red-team (live semaglutide) derives 5 grounded scenarios. Follow-up enrich PB-H10/H11 (team moves + options) shipped PR #142. Remaining for full persona depth: SA calibrate / DM select-for-war-game (→ PB-UX05+ / PB-H14).

#### [PB-UX05] Gaps stage — GapsContainer (Stage wiring P2.2)
- **Type**: feature
- **Status**: shipped
- **Priority**: high
- **Owner**: frontend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-UX01
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: SHIPPED (PR #143). Widened DossierGapsDTO; GapsContainer mirrors DossierContainer (assemble→render GapsPage); importance mapped from priority so the critical-gap workshop-blocking rule fires; added `fillMethod` to GapsPage ("how to fill"). Real-DB red-team (semaglutide) = 4 grounded gaps incl. critical pricing/access. Remediation is client-side → PB-UX05b for persistence.

#### [PB-UX05b] Persist gap remediation choices
- **Type**: enhancement
- **Status**: shipped
- **Priority**: medium
- **Owner**: backend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-UX05
- **Created**: 2026-06-01
- **Last touched**: 2026-06-02
- **Notes**: SHIPPED (PR #151). migration 075 gap_remediations (upsert on engagement+domain, applied to prod) + services/gap_remediation.py + GET/PUT endpoints + GapsContainer loads on mount (seeds readiness banner) and PUTs on change. Real-DB red-team round-trips. NOTE: feeding the scenario blocking from persisted remediation (vs derived gaps) is a future tie-in (PB-H10c decoupled blocking to own-domain gaps independently).

#### [PB-UX06] Synthesis stage — SynthesisContainer (Stage wiring P2.3)
- **Type**: feature
- **Status**: shipped
- **Priority**: medium
- **Owner**: shared
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-UX03
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: SHIPPED (PR #144) — was build-not-wire (no engagement-scoped insight derivation existed). migration 074 (engagement_id+dossier_snapshot_id+is_archived on insights/rejected_insights, applied to prod); `derive_synthesis_insights` (deterministic grounded candidates, one per substantive domain, frame from domain + signal→trigger, skips wargame_specific noise) → synthesis_test gate → assemble_and_persist + list_engagement_synthesis; GET/POST /engagements/{eid}/synthesis; synthesisApi + SynthesisContainer (reuses ProvenancePanel). Real-DB red-team (semaglutide) = 3 grounded insights (competitive/clinical/pipeline), 100% pass. FUTURE: optional H16 LLM polish of insight statements (the deterministic core is grounded; LLM would sharpen prose).

#### [PB-UX07] Sources stage — coverage view + upload (Stage wiring P2.4)
- **Type**: feature
- **Status**: shipped
- **Priority**: medium
- **Owner**: frontend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-UX01
- **Created**: 2026-06-01
- **Last touched**: 2026-06-02
- **Notes**: SHIPPED read-only coverage (PR #146): DossierSnapshot.source_coverage() + GET /engagements/{eid}/sources + SourcesContainer (per-source fact counts, domains, class mix, contribution bars). Real-DB red-team (semaglutide) = 4 sources / 290 facts; honestly surfaces noise concentration (ties PB-H07). UPLOAD half deferred to Data Hub epic E17 (PB-D01/D06) per user (curation UIs deferred).

#### [PB-UX08] Brief persistence + comments (Stage wiring P2.5)
- **Type**: feature
- **Status**: in-progress
- **Priority**: medium
- **Owner**: shared
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-UX02
- **Created**: 2026-06-01
- **Last touched**: 2026-06-02
- **Notes**: COMMENTS SHIPPED (PR #153): EntityComments mounted on the brief stage (target_type='brief'). REMAINING: in-app BCB authoring/editing — wire `useBriefAutosave` to a real update endpoint (`PUT /engagements/{eid}/brief`, currently the create-only path) + an edit form. Larger authoring surface; deferred. EL/KC author; all review.

#### [PB-UX09] Dossier curation surface (Stage wiring P2.6)
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: shared
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-UX01
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: Make the dossier curatable, not read-only: fact-level inline edit (claim/confidence/supersede), "Add fact" per domain for domain-expert enrichment (contributor + function-tag attribution), per-section export (PDF/Markdown). Backend: extend facts with contributed_by/contributor_function/edit_history. KEEP LEAN — facts not pages; agent writes prose from the fact base.

#### [PB-UX10] Engagement team management (Collaboration P3.1)
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: shared
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-UX01
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: `engagement_members` table (engagement_id, user_id, role KC/SA/DM/EL, invited_at, accepted_at) — per-engagement roles, not global. EL-only settings panel; invite-by-email. Needs auth maturity; can start email-only.

#### [PB-UX11] Activity timeline (Collaboration P3.2)
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: shared
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: n/a
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: Unified human+agent activity feed scoped to the engagement. `activity_log` table (actor_type agent|human, actor_id, action, target_type/id, ts, metadata). `ActivityDrawer` extends the demo's agent-drawer pattern. EL's primary oversight surface; the agent-activity rail from the design doc.

#### [PB-UX12] Export — Executive Brief + Intelligence Dossier (Deliverables P3.3)
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: backend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-UX04
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: Server-side PDF: Executive Brief (1-page, DM) + Intelligence Dossier (full 8-domain, KC/SA, provenance preserved). Agent-generated → human-reviewed → download (propose-confirm). Branded template (ZS or client). The engagement's tangible output.

#### [PB-UX13] Export — Strategy Deck PPTX (Deliverables P3.4)
- **Type**: feature
- **Status**: triaged
- **Priority**: low
- **Owner**: backend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-UX12
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: Slide pack (situation, insights, scenario matrix, war-room outcomes, decision rationale) via the existing PPTX/zs-slides pipeline. Agent selects content; user reviews; downloads. Per-org branding.

#### [PB-UX14] Engagement duplication (Deliverables P3.5 — quick win)
- **Type**: enhancement
- **Status**: triaged
- **Priority**: low
- **Owner**: shared
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: n/a
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: "Duplicate engagement" context-menu action on EngagementsTab cards — copies brief + source config + scenario structure, clears agent-generated content. 70% of template value for 10% of effort.

#### [PB-UX15] War-room seats + cross-functional guests (Collaboration P3.6)
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: shared
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-UX10
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: Configurable war-room seats (focal/competitor/stakeholder) with function tags (clinical/commercial/medical/access/finance), independent of engagement personas. Email-link guest invites scoped to the war room only (scoped JWT) — guests don't need engagement access. Move log shows seat + function lens. `war_room_seats` + `war_room_invitations` tables.

#### [PB-UX16] War-room guided move composer (War-room depth P4.1)
- **Type**: feature
- **Status**: triaged
- **Priority**: low
- **Owner**: shared
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-UX15
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: Full move composer (move types, team assignment, board-state meters) extending the war-room shell; multi-player turn-based. Adopt the demo's composer-panel. Guided mode first (maps to existing CommentsPanel flow).

#### [PB-UX17] War-room autonomous + game-theory modes (War-room depth P4.2/P4.3)
- **Type**: feature
- **Status**: triaged
- **Priority**: low
- **Owner**: backend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-UX16
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: Autonomous mode (agent plays all teams + narrates; user observes/steers) + game-theory mode (3×3 payoff matrix + Nash — see PB-H12). XL; needs deep agent orchestration + structured game-theory backend.

#### [PB-UX18] Decision outcome tracking — Learn loop (War-room depth P4.4)
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: backend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-UX04
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: After a decision commits (DM, signed + timestamped), the Helix agent monitors signals for outcome indicators and recalibrates (closes sense→decide→act→learn). Overlaps PB-H14 (scenario calibration); the learn machinery (learning_service EWMA, outcome_scheduler) is wired — this surfaces it on the committed decision.

#### [PB-UX19] Engagement version history & snapshots (War-room depth P4.5)
- **Type**: feature
- **Status**: triaged
- **Priority**: low
- **Owner**: backend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: n/a
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: `engagement_snapshots` at checkpoints (stage advance, war-room entry, decision commit) — immutable, browsable, restorable. `useStageAutosave` generalises useBriefAutosave. Dossier snapshots already exist (migration 072) — extend engagement-wide.

#### [PB-UX20] Adopt demo design language as codebase standard (cross-cutting)
- **Type**: enhancement
- **Status**: triaged
- **Priority**: medium
- **Owner**: frontend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: n/a
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: Adopt directly: fact-class confidence glyphs, flywheel chips (sense/decide/act/learn), insight frame tags (risk/opp/trigger/assumption), agent indicator in topbar. Adapt: domain-specific dossier layouts for top 2-3 domains; war-room mode picker (guided first). Fonts (Source Serif/Inter/JetBrains Mono) as a dedicated design-system loop. Skip: pricing grid, theme toggle, sidebar context card.

### E17 — Data Hub & horizontal intelligence substrate (DEFERRED)

> **Framing (user, 1 Jun 2026):** the data + sense layer is a HORIZONTAL intelligence
> substrate, not a CI/war-gaming database. The knowledge model (entities · facts ·
> evidence · graph · embeddings) + the CTX/query hydration APIs are the reusable seam;
> different orchestrating agents (CI/war-gaming today; regulatory, BD&L, med-affairs,
> portfolio tomorrow) plug in ABOVE that seam. Design discipline: keep the data layer
> domain-neutral and free of CI-specific coupling — model "engagement-scoped" as the
> general "consumer-scoped" case. Source: `docs/data-hub-agentic-layer-analysis.html`.
> **Status: all DEFERRED** — tackle after the immediate CI/UX walkthrough priorities
> (E16 stage wiring) are complete. Not a parallel agent for now; these are future loops
> for the same rigor (SPEC→reuse-first→TDD→real-DB red-team→PR), additive prod writes.

#### [PB-D01] Activate UserDocumentConnector (D0.1)
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: unassigned
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: n/a
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: DEFERRED. Size S. Uncomment the registration (connectors/__init__.py:44), add a minimal upload endpoint, wire into the pipeline. Ships the "upload PDF → entities light up" moment (master plan A8). Unlocks Tier 4 (contributed data) with zero new architecture. Domain-neutral: any consumer can contribute documents.

#### [PB-D02] Register QualityMonitorHook (D0.2)
- **Type**: enhancement
- **Status**: triaged
- **Priority**: medium
- **Owner**: unassigned
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: n/a
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: DEFERRED. Size S. One line in IntegrationPipeline.__init__ to register the (already-written) QualityMonitorHook so quality deltas across runs are tracked. Also populate the data steward's inert fair_before/fair_after. Quality-regression detection for free.

#### [PB-D03] Evidence-ledger population on ingest (D0.3 / master plan A4)
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: unassigned
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: n/a
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: DEFERRED. Size M. Each connector writes evidence records on ingest (the ledger has ~1 row today; the chain is theoretical). Makes provenance OPERATIONAL — directly enriches the sourceUrl/provenance the sense-spine already surfaces (PB-E05/UX03). Highest cross-cutting value: every downstream fact can cite a real evidence trail.

#### [PB-D04] HITL review queue UI (D1.1)
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: unassigned
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: n/a
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: DEFERRED (curation UI — user deferred all Phase-1 curation frontends). Size M. Surface the existing hitl_review_queue (HITLReviewManager.get_pending/resolve) as a curation panel: approve/reject/merge entity matches. Every human resolution creates an alias that improves future runs. When built, lives behind a dedicated Data tab (its own surface, not the engagement stages).

#### [PB-D05] Source health dashboard (D1.2)
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: unassigned
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: n/a
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: DEFERRED (curation UI). Size M. Surface source_registry FAIR scores (5 dims), fetch history, error rates, coverage per consumer; manual re-fetch trigger. Backend (/sources/health-summary) exists.

#### [PB-D06] Document upload UI + post-extraction review (D1.3)
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: unassigned
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-D01
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: DEFERRED (curation UI). Size M. Drag-and-drop upload, processing status in the agent activity feed, extracted-facts review (accept/reject/edit each assertion before it enters the knowledge model). The contribution workflow's quality gate.

#### [PB-D07] Fact annotations table (D1.4)
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: unassigned
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: n/a
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: DEFERRED. Size S. Separate fact_annotations table (fact_id, annotator_id, type, value, created_at) that the pipeline NEVER touches — a human overlay (relevance tags, confidence overrides, temporal qualifiers) that survives re-runs. Today a re-run can overwrite human curation.

#### [PB-D08] Connector scheduling & orchestration (D2.1)
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: unassigned
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: n/a
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: DEFERRED. Size L. Map each connector to a fetch cadence (CT.gov 6h, SEC 24h, news 30m), respect rate limits, track last/next-run + error rate. scheduler/runner.py exists. This is the sense loop's heartbeat — the system senses continuously, not on demand.

#### [PB-D09] Transcript ingestion pipeline (D2.2)
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: unassigned
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-D01
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: DEFERRED. Size L. Audio/video → transcription (Whisper API) → speaker diarisation → UserDocumentConnector → attributed facts ("Dr. X said Y about drug Z") at an internal/contributed confidence tier. The doc's highest-value NEW capability: qualitative intelligence (advisory boards, KOL interviews) that no competitor has.

#### [PB-D10] Licensed-data connector pattern (D2.3)
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: unassigned
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: n/a
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: DEFERRED. Size M. A LicensedBaseConnector extending BaseConnector: credentials vault, licence-expiry tracking (registry has license_status/license_renewal_at), rate-limit enforcement, consumer-scoped visibility. Ship one reference impl (e.g. Citeline). NOTE: commercial gating (who holds which licence) is the hard part, not the tech.

#### [PB-D11] Consumer-scoped data visibility (D2.4, generalised)
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: unassigned
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-D10
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: DEFERRED. Size M. A consumer_sources join table (generalises the doc's engagement_sources — per the horizontal-layer framing, an engagement is one consumer). CTX pipeline filters hydration by scope: a consumer sees public + its licensed + its internal data, never another's. Multi-tenant isolation without multi-tenant infra. KEY substrate primitive for repurposing the layer across agents.

#### [PB-D12] Decision-outcome → source recalibration (Learn loop, D3.1)
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: unassigned
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: n/a
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: DEFERRED. Size L. When a committed decision's outcome is observed, recalibrate source predictive_accuracy (sources that predicted correctly gain weight). learning_service.py already has EWMA source accuracy but runs=0. Closes the Learn loop; source trust becomes empirical. Relates to PB-H14 (scenario calibration).

#### [PB-D13] Cross-engagement / cross-consumer knowledge index (D3.2)
- **Type**: feature
- **Status**: triaged
- **Priority**: low
- **Owner**: unassigned
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: n/a
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: DEFERRED. Size M. Index insights/scenarios/decisions from completed engagements as retrievable context for new ones ("last time we analysed this market we concluded X; outcome was Y"). Evidence-ledger snapshots make this possible. Institutional memory — the substrate accumulates across all consumers.

#### [PB-D14] Real-time / streaming signal ingestion (D3.3)
- **Type**: feature
- **Status**: triaged
- **Priority**: low
- **Owner**: unassigned
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-D08
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: DEFERRED. Size L. Move high-priority sources (FDA alerts, CT.gov updates, SEC filings) from RSS polling to webhook/streaming. Sense loop detects critical signals in minutes, not hours.

#### [PB-D15] Internal-data connector framework (D3.4)
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: unassigned
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-D10, PB-D11
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: DEFERRED. Size L. Pattern for ingesting structured internal data (CRM exports, sales data, field notes) via upload/API/SFTP with row-level, consumer-scoped isolation. Extends LicensedBaseConnector. The client's own data is the most valuable + least accessible — turns a generic market view into "their competitive position."

#### [PB-D16] Investigator embedding + resolution strategy (agentic-ready gap)
- **Type**: enhancement
- **Status**: triaged
- **Priority**: low
- **Owner**: unassigned
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: n/a
- **Created**: 2026-06-01
- **Last touched**: 2026-06-01
- **Notes**: DEFERRED. Size S. The doc's audit of the 7 agentic-ready properties found one consistent gap: investigators have no embedding column + no embedding resolution strategy (low-confidence fuzzy matches sit in the unresolved queue). Add VECTOR(1536) + embedding strategy for investigators to close it.

### E18 — Integrated CI experience (flywheel IA)

> From the integrated-experience prototype (`docs/ci-integrated-experience-prototype.html`, v2).
> Reorganises the 9 flat artifact tabs around the sense→understand→decide→act→learn
> flywheel; Dossier + War Game become reusable building blocks (standalone + as engagement
> stages); the missing **promote bridge** (signal → dossier/war-game/engagement) is the
> connective tissue. User-approved: "build it, visible IA first."

#### [PB-IX02] Consolidate the 3 feeds → one Intelligence surface
- **Type**: feature
- **Status**: shipped
- **Priority**: high
- **Owner**: frontend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: n/a
- **Created**: 2026-06-02
- **Last touched**: 2026-06-02
- **Notes**: SHIPPED (PR #154). IntelligenceTab wraps Sensing Feed + Daily Digest + Signals DB behind a view toggle (Digest/Stream/Signals DB); CIPage 3 nav entries → 1; old deep-links route via viewFromTab.

#### [PB-IX03] Standalone Dossier surface (light path)
- **Type**: feature
- **Status**: shipped
- **Priority**: high
- **Owner**: shared
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: n/a
- **Created**: 2026-06-02
- **Last touched**: 2026-06-02
- **Notes**: SHIPPED (PR #155). assemble_dossier_for_asset (extracted from the engagement path) + GET /dossier-preview + StandaloneDossierTab (reuses EngagementDossierPage + ProvenancePanel) + Promote-to-engagement. Real-DB: semaglutide → 290 facts/8 domains, no engagement.

#### [PB-IX05] Re-group the CI nav around the flywheel
- **Type**: feature
- **Status**: shipped
- **Priority**: high
- **Owner**: frontend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-IX02, PB-IX03
- **Created**: 2026-06-02
- **Last touched**: 2026-06-02
- **Notes**: SHIPPED (PR #156). NAV_GROUPS: Sense / Engage (Dossier·War Game·Engagements) / Act / Learn / Admin. 'rooms' relabelled "War Game" (its own section per v2 feedback). All tab keys preserved.

#### [PB-IX01] Promote bridge — signal → dossier / war-game / engagement
- **Type**: feature
- **Status**: triaged
- **Priority**: high
- **Owner**: shared
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-IX02, PB-IX03
- **Created**: 2026-06-02
- **Last touched**: 2026-06-02
- **Notes**: The missing connector. A signal action menu (in IntelligenceTab) → seed a standalone dossier, a war game, or a full engagement from the signal. Upstream `signal_promoter.py` (events→signals) + `decisions.promote_round` (round→decision) exist; this adds the middle signal→work promotion + a seed endpoint. Highest-value IA loop.

#### [PB-IX04] War Game surface + mode picker (turn-based / game-theory / autonomous)
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: shared
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-IX05
- **Created**: 2026-06-02
- **Last touched**: 2026-06-02
- **Notes**: Unify the three play modes under one War Game home: guided turn-based (live: war_game_engine/adversary), game-theory payoff+Nash (PB-H12), autonomous N-round sim (PB-H13). Standalone start OR seeded from a scenario. The "rooms" tab is already relabelled War Game (IX-5); this gives it the mode picker + standalone launch.

#### [PB-IX06] Learn loop closes to Sense (re-order Digest from calibration)
- **Type**: feature
- **Status**: triaged
- **Priority**: medium
- **Owner**: backend-claude
- **Source**: feedback
- **Source ref**: adhoc
- **Blocked by**: PB-H14
- **Created**: 2026-06-02
- **Last touched**: 2026-06-02
- **Notes**: The flywheel's closing arc — scenario-prior + source-trust recalibration (PB-H14) re-orders what the Intelligence Digest surfaces first. Highest value, highest risk; depends on the Learn loop.

### E19 — Data richness (DR-loops): lift latent source data into the fact ledger

> From `docs/state-of-build-and-data-richness.html` (grounded in the live DB, 2 Jun).
> **Diagnosis:** the `facts` ledger the dossier reads has 3,303 rows but only 2
> distinct predicates (market_event, wac_usd) — a news-event monoculture — while
> 5,524 clinical_trials + 2,075 adverse_events + 185 drug_labels sit in entity
> tables and never become domain facts. **Not a sourcing problem; a plumbing
> problem.** Fix = a thin fact-emitter layer (entity rows → typed domain facts via
> the existing `route_predicate_to_domain`, writing evidence as it goes). No new
> sources. Sequenced loops (see the report for detail):
> **DR-0** emitter framework · **DR-1** clinical (clinical_trials→clinical/pipeline) ·
> **DR-2** pricing (NADAC→pricing&access, fixes the critical gap) · **DR-3** safety
> (FAERS) · **DR-4** labels (SPL) · **DR-5** evidence-ledger-on-ingest (1→thousands) ·
> **DR-6** mechanism/target (ChEMBL/OpenTargets) · **DR-7** literature/epidemiology
> (PubMed/PMC) · **DR-8** connector scheduling. Priority: DR-0+DR-1+DR-2+DR-5 first
> (biggest dossier-quality jump from data we already hold). The licensed gaps
> (Rx volume / claims / prescriber behaviour) stay in E17 tiers 2–3.
>
> **SHIPPED (2 Jun):** **DR-0** fact-emitter framework (`services/fact_emitters/`:
> `EmittedFact`/`EmitStats`/`FactEmitter` + idempotent `emit_one`/`run_emitter`,
> keyed on `object_value.source_row_id`); **DR-1** clinical-trials emitter
> (`ClinicalTrialEmitter`: clinical_trials → `clinical_trial` facts routed to
> `clinical_profile`); **DR-5** evidence-on-ingest (a standalone `evidence_record`
> per newly-asserted fact, linked via `facts.source_doc_id`). Also fixed a latent
> bug: `facts_as_of` never SELECTed `fact_class`, so every ledger fact rendered in
> the dossier as `signal` — now corrected. **Real-DB gate (semaglutide):** 174
> trial facts asserted, re-run idempotent, evidence_records 1→174, clinical_profile
> went gap→complete (readiness 1.0), overall readiness 0.36→0.47.
> **DR-2 (pricing) is BLOCKED:** `drug_pricing` is empty (0 rows) and there is no
> `nadac_prices` table — no source data to lift; needs a NADAC ingest first
> (E17/pricing backlog), so it is deferred, not skipped. **Still open:** DR-3
> (FAERS/adverse_events, 1,992 drug-linked rows ready), DR-4 (SPL labels, 175
> ready), DR-8 (scheduler wiring + full cross-drug backfill — emitters currently
> run per-drug on demand). Minor: the 174 demo facts carry pre-fix claim wording
> ("Clinical trial: Trial NCT…"); future emits use the cleaned format (append-only,
> so existing rows weren't rewritten).

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
