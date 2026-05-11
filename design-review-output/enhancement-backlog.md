# Market Zero — Enhancement Backlog

> **Twelve epics. ~36 user stories. ~120 tasks. Sequenced into 24 weeks.**
> Synthesised from the nine-phase design review, the data layer audit, the eight prototypes and the CI Reimagined Spec.

**Audience:** Engineering leads, frontend + backend engineers, designers, PM
**Format:** Each epic carries a *why*, *stories* (with acceptance criteria), *tasks* (with file references), *dependencies* and *effort*. Every task references the relevant code file in the codebase, the relevant prototype that demonstrates the future state, and the relevant audit doc that justified it.
**Effort scale:** S = 1–3 days · M = 1–2 weeks · L = 3+ weeks · XL = 6+ weeks
**Status legend:** `[ ]` not started · `[/]` in progress · `[x]` complete

---

## Sequencing summary · 24-week plan

| Weeks | Epics | Outcome |
|---|---|---|
| 1–2 | E1 · Trust foundation | 4 critical heuristic findings closed; first credibility lift for Maya |
| 3–4 | E2 · Live agent presence | Three named agents visible across all surfaces |
| 5–7 | E3 · Entity dossier | Spine surface; brief composition speed lifts |
| 8–10 | E4 · Brief composer | Writing-first replaces 5-panel form |
| 11–12 | E5 · War-game cockpit | Payoff matrix + adversary twins; the WOW surface |
| 13–14 | E6 · Chat surface upgrade | Working set, coreference, citation progressive disclosure |
| 15 | E7 · Graph as interlocutor | Ask-this-subgraph + saved subgraphs |
| 16–17 | E8 · Data catalog view | Replaces /connectors raw JSON with real catalog |
| 18–21 | E9 · Phase 1 connectors | 8 free public sources close largest unfed KBQ gaps |
| 22 | E10 · Source registry + FAIR | Quality scoring + licence health surfaced |
| 23 | E11 · Multi-tenancy enforcement | SaaS-blocker fix |
| 24 | E12 · Prompt registry + active feedback | Closes the learning loop |

**Feature-flag prefix:** `mz_audit_2026q3_*` per epic. Each epic ships behind its flag and graduates to default-on at the end of its sequence weeks.

---

## Reference index · the prototypes and audit docs

Every task below references one or more of these. They live in `design-review-output/`.

**Prototypes (HTML):**

- `prototype/future-state.html` · v1 vision (aspirational)
- `prototype/future-state-wired.html` · v2 with real API contracts + sample-or-live mode toggle
- `prototype/future-state-v3.html` · v3 substrate-first platform story
- `prototype/persona-analyst-mayas-tuesday.html` · analyst end-to-end day
- `prototype/persona-steward-ravis-tuesday.html` · data steward end-to-end day
- `prototype/wargame-agentic-cockpit.html` · continuous-collaborative war-game with adversary twins + authority spectrum
- `prototype/chat-graph-metadata.html` · reimagined chat + graph + 6 metadata patterns
- `prototype/data-layer-coverage.html` · 15×8 coverage matrix + 28-source roadmap
- `prototype/data-catalog-view.html` · the catalog surface

**Audit docs (Word):**

- `executive-summary.docx` · the one-pager
- `phase-reports/phase1-recon.docx` through `phase8-verification.docx` · the diagnostic trail
- `instruction-set/instruction-set.docx` · keep / refactor / build / decommission
- `tech-specs/tech-specs.docx` · component contracts + API shapes + perf budgets
- `backlog/backlog.docx` · the original 8-epic version of this doc
- `v3-positioning.docx` · platform positioning + live-app findings
- `prototype/api-mapping.docx` · every prototype surface mapped to its real endpoint
- `data-layer-audit.docx` · 15-connectors-vs-8-KBQs analysis + 28-source roadmap

---

# E1 · Trust foundation

> **Weeks 1–2 · closes 4 of 4 critical heuristic findings · the first credibility lift Maya feels.**

## Why
Phase 3 audit (`phase-reports/phase3-heuristics.docx`) identified four critical findings that block Maya from doing her job today: evidence is unviewable, watchlist requires UUIDs, no reasoning chain visible, materiality factors hidden. All four are fixable in two weeks with engineering-only cost. Before any new product surface ships, these four go.

## Stories

### S1.1 · Evidence cards · replace opaque IDs with real evidence

**As Maya** I want to see real evidence (source, date, tier, snippet) instead of opaque hex IDs, so I can vouch for any claim in 5 seconds.

**Acceptance criteria:**
- Every signal detail page renders evidence as cards (source name + favicon + tier badge + date + 2-line snippet)
- Click any card opens the source document in `LiteratureExplorer` if available, or the source URL in a new tab
- Evidence cards are sortable by tier, by date, by referenced-vs-not
- Aggregate views: by source tier, by recency profile (24h, 7d, 30d)

**Code refs:**
- `frontend/src/components/ci/EvidenceStack.tsx` · replace current implementation (renders only `doc_id` strings)
- `api/routes/evidence_ledger.py` · ensure response carries `source_name`, `source_tier`, `published_at`, `snippet` fields
- `api/schemas.py` · update `EvidenceItemResponse` to include the four new fields
- `frontend/src/api.ts` · update the `EvidenceItem` type def

**Prototype ref:** `prototype/chat-graph-metadata.html` · "Pattern 4 · evidence stack with pivots" + `prototype/data-catalog-view.html` · evidence rendering on source detail dive

**Audit ref:** `phase-reports/phase3-heuristics.docx` · finding C1 (critical)

**Tasks:**
- [ ] T1.1.1 · Evidence card component · M · `frontend/src/components/ci/EvidenceCard.tsx`
- [ ] T1.1.2 · Source-tier badge primitive · S · `frontend/src/components/ui/TierBadge.tsx`
- [ ] T1.1.3 · Snippet renderer with truncation + expand-on-hover · S
- [ ] T1.1.4 · Open-in-context link wiring (LiteratureExplorer or external URL) · S
- [ ] T1.1.5 · Aggregate-view tabs (by source / by tier / by recency) · M
- [ ] T1.1.6 · Backend: extend `evidence_records` schema to expose tier, snippet, published_at · S · `schema/migrations/`
- [ ] T1.1.7 · Backend: update `/signals/{id}` and `/decision-briefs/{id}/evidence` to return enriched evidence shape · S
- [ ] T1.1.8 · a11y: keyboard nav, focus rings, screen-reader labels · S

### S1.2 · Entity picker · replace UUID input with knowledge-graph autocomplete

**As Maya** I want to pick a watchlist entity by name, not paste a UUID, so I can onboard in two minutes.

**Acceptance criteria:**
- `WatchlistTab` "Add" form replaces `entity_id (UUID)` text input with a Combobox that searches the knowledge graph
- Search hits show entity name + type pill + connection count
- Selecting one creates the watchlist entry with the resolved entity_id
- Backend exposes `/search/suggest?q=...&entity_types=drug,company` for the autocomplete

**Code refs:**
- `frontend/src/components/ci/WatchlistTab.tsx` · replace lines for the entity_id input
- `frontend/src/components/ui/EntityCombobox.tsx` · new primitive (reusable in 5+ places)
- `api/routes/search.py` · `/search/suggest` exists; verify it returns the right shape
- `api/routes/watchlist.py` · no change to API contract

**Prototype ref:** `prototype/chat-graph-metadata.html` · "Pattern 2 · entity badge"

**Audit ref:** `phase-reports/phase3-heuristics.docx` · finding C2 (critical)

**Tasks:**
- [ ] T1.2.1 · EntityCombobox component (Radix Combobox or downshift) · M
- [ ] T1.2.2 · Backend: ensure /search/suggest returns name + type + connection_count · S
- [ ] T1.2.3 · Wire into WatchlistTab Add form · S
- [ ] T1.2.4 · Migration script for existing UUID-based watchlist entries (resolve to canonical entity) · S · `scripts/migrate_watchlist_entities.py`
- [ ] T1.2.5 · Update SignalsTab "filter by entity" to use the same Combobox · S

### S1.3 · Materiality factor breakdown · render the score the system already produces

**As Maya** I want to see why a signal scored 87, so I can defend the score to my brand lead.

**Acceptance criteria:**
- Every materiality score in the UI is clickable
- Click opens an inline drawer showing the four factors (source_tier, entity_criticality, claim_type, recency) with input, value, weight, contribution per factor, plus the formula
- Drawer has a "Tune weights" button (admin-only, for KBQ team) and a "View source registry" button
- The score formula is rendered in monospace as a readable equation

**Code refs:**
- `services/materiality.py` · the `score()` method already returns `materiality_factors` dict with all four factors structured (input, value, weight, contribution) · just consume it
- `api/routes/materiality.py` · `POST /materiality/score` is the endpoint
- `frontend/src/components/ci/MaterialityDrawer.tsx` · new component
- `frontend/src/components/ci/SensingFeed.tsx` · wire the drawer onto every materiality number
- `frontend/src/components/ci/SignalCard.tsx` · same

**Prototype ref:** `prototype/future-state-v3.html` · materiality explainer section + `prototype/chat-graph-metadata.html` · "Pattern 6 · why-this"

**Audit ref:** `phase-reports/phase3-heuristics.docx` · finding C4 (critical)

**Tasks:**
- [ ] T1.3.1 · MaterialityDrawer component with four bars + formula + tune-weights button · M
- [ ] T1.3.2 · Wire onto SensingFeed cards (production deployment shows materiality 1% — verify scoring service is producing factors) · S
- [ ] T1.3.3 · Wire onto SignalCard, SignalDetail, dossier signal lists · S
- [ ] T1.3.4 · Diagnostic: investigate why production materiality scores are all 1% (live walk found this on 9 May 2026) · S
- [ ] T1.3.5 · "Tune weights" interaction (PATCH `/materiality/weights`, admin role only) · M

### S1.4 · Multi-select KBQ chips · the 2-hour bug fix

**As Maya** I want to apply more than one KBQ filter at once, so I can see "regulatory + clinical readout" together.

**Acceptance criteria:**
- KBQFilter chips become multi-select (current behaviour: clicking a chip toggles all others off)
- URL state syncs the multi-select via `?kbq=KBQ-3,KBQ-1`
- Backend already supports any-of matching · no API change

**Code refs:**
- `frontend/src/components/ci/KBQFilter.tsx` · lines 1–53 · update toggle logic

**Prototype ref:** `prototype/chat-graph-metadata.html` · KBQ pills in conversation panel

**Audit ref:** `phase-reports/phase3-heuristics.docx` · finding H2 (high)

**Tasks:**
- [ ] T1.4.1 · Multi-select chip toggle logic · S
- [ ] T1.4.2 · URL state synchronisation · S
- [ ] T1.4.3 · Verify SignalsTab + dossier filter both consume the new shape · S

---

# E2 · Live agent presence

> **Weeks 3–4 · closes Phase 3 H9 + Phase 5 G2 · the first felt change in product personality.**

## Why
The platform claims "agentic intelligence" on the landing page but the only place this is felt is `AgentStatusBar` showing "Monitoring · 3 agents" as a static label. Three named agents (Sentinel, Strategist, Curator) need to be visible across all surfaces, with current activity, last action, and addressable nudges.

## Stories

### S2.1 · Agent identity · name them, give them roles

**As Maya** I want to know each agent by name and role, so they feel like colleagues not chatbots.

**Acceptance criteria:**
- Three named agents with consistent glyphs across all surfaces: Sentinel (SE / teal · Sense), Strategist (ST / violet · Frame + Simulate), Curator (CU / green · Learn + Recalibrate)
- Agent name + role appears wherever the system is doing work (Pulse, war-game, brief composer, ask-anything)
- Verify Phase 8 verification's amendment: roles use noun form (Sentinel/Strategist/Curator), not verb form (Sense/Frame/Learn) — the role form reads competent, the verb form reads cute

**Code refs:**
- `frontend/src/components/primitives/AgentStatusBar.tsx` · rename + extend to support 3-agent identity
- `frontend/src/components/agents/AgentGlyph.tsx` · new primitive · 3 colour-coded glyph variants
- `services/research_agent.py` + `services/conversation_memory.py` + `services/data_steward.py` · backend identity hooks
- `api/routes/agent.py` · `/agent/events` returns events tagged by agent name (verify shape)

**Prototype ref:** `prototype/persona-analyst-mayas-tuesday.html` (live agent panel) · `prototype/wargame-agentic-cockpit.html` (workforce panel)

**Audit ref:** `phase-reports/phase8-verification.docx` · Agent C amendment (rename to noun form)

**Tasks:**
- [ ] T2.1.1 · AgentGlyph component (3 variants) · S
- [ ] T2.1.2 · AgentStatusBar refactor → AgentRail (3 cards) · M
- [ ] T2.1.3 · Update copy across surfaces (search-and-replace "Monitoring" → role-specific) · S
- [ ] T2.1.4 · Backend: ensure `/agent/events` events carry `agent: "sentinel" | "strategist" | "curator"` field · S

### S2.2 · Activity feed · show what each agent is doing now

**As Maya** I want to see what each agent is doing right now and what it just did, so I can vouch for their work.

**Acceptance criteria:**
- Live activity stream per agent (updates every 3–5s)
- Each event: timestamp, kind (started / progress / completed / failed), activity text, entity refs
- Reconnect-on-disconnect with exponential backoff
- Falls back to polling if SSE unavailable

**Code refs:**
- `api/routes/agent.py` · add SSE endpoint `GET /agents/stream` (wraps existing `/agent/events`)
- `frontend/src/components/agents/AgentRail.tsx` · consume SSE stream
- `frontend/src/lib/sse.ts` · new utility for SSE with reconnect

**Prototype ref:** `prototype/wargame-agentic-cockpit.html` (workforce panel · live indicators) · `prototype/data-catalog-view.html` (ingestion activity stream — same pattern, different surface)

**Audit ref:** `phase-reports/phase5-gaps.docx` · Gap G2 (Live Agent Plane)

**Tasks:**
- [ ] T2.2.1 · Backend: `GET /agents/stream` SSE endpoint · M
- [ ] T2.2.2 · Frontend: SSE consumer with reconnect harness · M
- [ ] T2.2.3 · Activity card UI (per agent) · S
- [ ] T2.2.4 · Last-action history (last 5 actions, expandable) · S
- [ ] T2.2.5 · Polling fallback for environments without SSE support · S

### S2.3 · Nudges · address an agent

**As Maya** I want to be able to ask an agent to "watch this entity" or "rerun this simulation", so I can steer it without code.

**Acceptance criteria:**
- Each agent card has a nudge button
- Nudge intents per agent: Sentinel (watch entity / ignore source / boost source), Strategist (rerun sim / draft counter), Curator (explain score / mark outcome verified)
- POST `/agents/{agent}/nudge` with intent + payload
- Confirmation toast + completion event in the activity feed

**Code refs:**
- `api/routes/agent.py` · `POST /agents/{agent}/nudge` endpoint (new)
- `services/research_agent.py` + `services/conversation_memory.py` · accept and process nudges
- `frontend/src/components/agents/NudgeMenu.tsx` · new component

**Prototype ref:** `prototype/wargame-agentic-cockpit.html` (workforce + delegation sections)

**Tasks:**
- [ ] T2.3.1 · Intent registry per agent · S · `services/agent/nudge_intents.py`
- [ ] T2.3.2 · POST /agents/{agent}/nudge endpoint · M
- [ ] T2.3.3 · Nudge button in agent card · S
- [ ] T2.3.4 · Confirmation toast + completion event · S

### S2.4 · Degradation visibility

**As Maya** I want to see when an agent is paused or failing, so I do not assume an empty feed means nothing happened.

**Acceptance criteria:**
- Failed/paused state rendered on agent card with reason
- Retry affordance + "open issue" link

**Tasks:**
- [ ] T2.4.1 · Failure state rendering · S
- [ ] T2.4.2 · Reason text from backend · S
- [ ] T2.4.3 · Resume affordance + escalation to steward · S

---

# E3 · Entity dossier

> **Weeks 5–7 · closes Phase 5 G1 · the highest-leverage missing surface.**

## Why
Maya thinks in entities (compounds, companies, mechanisms, trials). The product surfaces in queries, signals, briefs and rooms — none of which are the entity. A first-class dossier is the spine that makes brief composition take 45 minutes instead of 3 hours.

## Stories

### S3.1 · Dossier route + three-column layout

**As Maya** I want to land on a single page that tells me everything about a compound, so I do not stitch context across five tabs.

**Acceptance criteria:**
- New route `/dossier/{entity_type}/{slug or id}`
- Three-column layout: identity rail (left) · synthesis main (centre) · evidence pile (right)
- entity_type ∈ { drug, company, mechanism, trial, therapeutic_area }

**Code refs:**
- `frontend/src/pages/DossierPage.tsx` · new
- `api/routes/dossier.py` · new (or composes from existing `/catalog/entity-profile/{type}/{id}` + `/graph/neighborhood/{type}/{id}` + `/signals?entity_id={id}`)
- `services/dossier.py` · new compose-service

**Prototype ref:** `prototype/future-state-wired.html` (dossier section · 3-column) · `prototype/persona-analyst-mayas-tuesday.html` (m2 dossier panel)

**Audit ref:** `phase-reports/phase5-gaps.docx` · Gap G1 · `tech-specs/tech-specs.docx` · B1 SPEC-036

**Tasks:**
- [ ] T3.1.1 · /dossier/{type}/{slug} route · S
- [ ] T3.1.2 · Three-column layout shell · S
- [ ] T3.1.3 · EntityCard primitive (identity rail) · S
- [ ] T3.1.4 · Backend: GET /dossier/{type}/{slug} composer endpoint · M
- [ ] T3.1.5 · slug-or-id URL parameter handling · S

### S3.2 · Synthesis with inline citations

**As Maya** I want to read a Strategist-written synthesis where every claim has a clickable citation, so I can defend it.

**Acceptance criteria:**
- Synthesis text renders inline citations as numbered chips (tier-coloured)
- Click a citation jumps to the matching evidence card in the right panel
- Hover shows source name + date + 1-line snippet
- Owner can edit the synthesis inline

**Code refs:**
- `services/llm.py` · `synthesize_dossier()` already exists · verify citations are produced
- `frontend/src/components/dossier/SynthesisPanel.tsx` · reuses CitationChip component from E6
- `frontend/src/components/ui/CitationChip.tsx` · shared (built in E6 S6.3 first; this story depends on it)

**Tasks:**
- [ ] T3.2.1 · SynthesisPanel component · M
- [ ] T3.2.2 · Citation jump-to-evidence interaction · S
- [ ] T3.2.3 · Inline edit affordance for owner · S

### S3.3 · Recent moves timeline

**As Maya** I want to see what changed in the last 30 days as a chronological timeline, so I can scan recency at a glance.

**Acceptance criteria:**
- Timeline of signals + state transitions in reverse-chronological order
- Each row: timestamp + KBQ tag + headline
- Lower-importance items rendered with reduced visual weight

**Code refs:**
- `frontend/src/components/dossier/Timeline.tsx` · reusable primitive
- Backend: `/dossier/{type}/{slug}` returns a `recent_moves[]` array (max 30 days)

**Tasks:**
- [ ] T3.3.1 · Timeline primitive (reusable in war-game evidence stream too) · M
- [ ] T3.3.2 · Backend: include recent_moves in dossier composer · S
- [ ] T3.3.3 · Lower-importance visual treatment (opacity, smaller dot) · S

### S3.4 · Evidence pile with grounded source registry

**As Maya** I want to see all evidence behind the dossier in one column, so the rest of the page is a story and the column is the proof.

**Acceptance criteria:**
- Right column shows up to 3 evidence cards inline + "+N more" expand
- Reuses EvidenceCard from E1 S1.1
- Source-tier badge variants reflect the spec's 4-tier model

**Tasks:**
- [ ] T3.4.1 · Evidence pile renderer (reuses E1 evidence cards) · S
- [ ] T3.4.2 · "+N more" expand interaction · S

### S3.5 · Watching analysts + add-to-watchlist

**As Maya** I want to know who else is watching a compound and add it to my own watchlist in one click.

**Acceptance criteria:**
- Face stack shows up to 4 analyst avatars + "+N"
- Add-to-watchlist button reuses E1 S1.2 entity picker pattern (single-click since entity is known)

**Tasks:**
- [ ] T3.5.1 · Watching faces stack component · S
- [ ] T3.5.2 · Watchlist toggle button · S
- [ ] T3.5.3 · Permissions check (viewer can see, uploader+ can watch) · S

---

# E4 · Brief composer

> **Weeks 8–10 · closes Phase 3 H1 + Phase 5 G5 · pivots from form-filling to authoring.**

## Why
The current `DecisionWorkspace` (5-panel composite) feels like Jira on first contact and three of the five panels are placeholders. Maya writes briefs by writing — the composer should be a document editor with inline AI suggestions, not a form.

## Stories

### S4.1 · Writing-first editor

**As Maya** I want to write a brief by writing prose, with citations and entity mentions inline, so the editor disappears.

**Acceptance criteria:**
- TipTap or ProseMirror editor with custom marks for citations (`{{cite:doc_id}}`), entity mentions (`{{entity:slug}}`), AI suggestions (inline cards)
- Autosave every 4 seconds to `/decision-briefs/{id}`
- State machine (draft → human_review → simulation_pending → decided → committed) runs underneath, surfaced in the slim sidebar (S4.4)

**Code refs:**
- `frontend/src/pages/DecisionWorkspace.tsx` · pivot from 5-panel
- `frontend/src/components/composer/BriefComposer.tsx` · new (TipTap-based)
- `api/routes/decision_briefs.py` · `GET`, `PATCH`, `POST /decision-briefs/{id}/options`, `POST /decision-briefs/{id}/transitions` all exist · no API change needed
- SPEC-023 unchanged

**Prototype ref:** `prototype/future-state-wired.html` (composer section) · `prototype/persona-analyst-mayas-tuesday.html` (m6 brief composition)

**Audit ref:** `phase-reports/phase5-gaps.docx` · Gap G5 · `tech-specs/tech-specs.docx` · B5

**Tasks:**
- [ ] T4.1.1 · TipTap setup with custom marks · M
- [ ] T4.1.2 · Citation mark (consume CitationChip from E6) · S
- [ ] T4.1.3 · Entity mention mark (consume EntityBadge from E6) · S
- [ ] T4.1.4 · Autosave every 4s with optimistic update + conflict resolution · M
- [ ] T4.1.5 · Persistence to /briefs/{id} via PATCH · S

### S4.2 · Inline AI suggestions

**As Maya** I want to have Strategist and Curator surface inline suggestions as I type, so I do not have to remember what to add.

**Acceptance criteria:**
- Strategist runs in background every 6 seconds: evaluates current draft, recommends inline edits (add counter, name missing stakeholder, surface contradicting evidence)
- Curator runs alongside: scores evidence completeness 0–5 and offers to insert evidence with one-click action
- Suggestions render as inline cards within the document flow (not in a sidebar)
- Accept/dismiss flow per suggestion

**Code refs:**
- `services/llm.py` · `synthesize_research_report()` close to what's needed; may need a `suggest_brief_edit()` variant
- `services/chat_handlers/handlers.py` · brief context handling
- `api/routes/decision_briefs.py` · add `POST /decision-briefs/{id}/suggest` endpoint
- `frontend/src/components/composer/AISuggestion.tsx` · new

**Prototype ref:** `prototype/persona-analyst-mayas-tuesday.html` (m6) · the violet-bordered suggest cards

**Tasks:**
- [ ] T4.2.1 · Backend: brief-context suggestion service · L · `services/brief_suggestions.py`
- [ ] T4.2.2 · Frontend: polling every 6s when in editable state · S
- [ ] T4.2.3 · Inline suggestion card component · M
- [ ] T4.2.4 · Accept/dismiss flow with optimistic edit · S
- [ ] T4.2.5 · Counter-recommendation prompt (when no counter named) · S

### S4.3 · Options grid

**As Maya** I want to capture decision options as a small grid of cards inside the doc, so they are first-class but not a separate panel.

**Acceptance criteria:**
- Options block primitive (renders inside editor as a structured node)
- Recommended-state highlight (green border + box-shadow per `prototype/persona-analyst-mayas-tuesday.html`)
- Scoreline per option (predicted outcome / cost / confidence)
- Add option flow inline

**Code refs:**
- `frontend/src/components/composer/OptionsBlock.tsx` · new
- `api/routes/decision_briefs.py` · `POST /decision-briefs/{id}/options` exists · no API change

**Tasks:**
- [ ] T4.3.1 · Options block primitive (TipTap node) · M
- [ ] T4.3.2 · Recommended-state highlight + scoreline · S
- [ ] T4.3.3 · Add option flow · S

### S4.4 · Slim sidebar (stakeholders / materiality / state)

**As Maya** I want to see who needs the brief, how material the decision is, and where I am in the state machine, without leaving the writing surface.

**Acceptance criteria:**
- Right sidebar with three cards: Stakeholders (round-robin scheduler), Materiality (score + impact framing), State (state machine progress with next-action affordance)

**Tasks:**
- [ ] T4.4.1 · Sidebar layout · S
- [ ] T4.4.2 · Stakeholder round-robin schedule UI · M
- [ ] T4.4.3 · Materiality summary card (reuses E1 S1.3 drawer) · S
- [ ] T4.4.4 · State machine progress + next-action button · S

### S4.5 · Migration from legacy DecisionWorkspace

**As Maya** I want to have my in-flight briefs move to the new composer without losing state, so I do not have to redo work.

**Acceptance criteria:**
- In-flight briefs read-only in legacy mode after week 8
- Auto-migration script preserves state + fields, maps option editor entries to options-block in the doc
- Rollback path available

**Tasks:**
- [ ] T4.5.1 · Read-only legacy mode toggle · S
- [ ] T4.5.2 · Auto-migration script · M · `scripts/migrate_briefs_to_composer.py`
- [ ] T4.5.3 · Field-to-block mapping logic · S
- [ ] T4.5.4 · Rollback path (composer → legacy) · S

---

# E5 · War-game cockpit

> **Weeks 11–12 · closes Phase 3 H5 + Phase 5 G4 · the WOW surface.**

## Why
The current `WarRoomView` is a stack of dropdowns and round history — a form, not a board. The cockpit prototype shows what a continuous, collaborative war-game looks like with adversary digital twins, payoff matrix, posterior bars and the authority spectrum.

## Stories

### S5.1 · Payoff matrix view

**As Maya** I want to see a 2×2 payoff matrix for two candidate moves and two adversary states, so I can scan the strategic landscape.

**Acceptance criteria:**
- 2×2 matrix renders cells with delta % + confidence + recommended highlight
- Cells colour-coded (win green / neutral amber / lose red)
- Recommended cell glows with shadow

**Code refs:**
- `frontend/src/components/ci/war/WarRoomView.tsx` · pivot from form-driven to spatial
- `frontend/src/components/wargame/PayoffMatrix.tsx` · new
- `api/routes/war_room.py` · add `POST /war-rooms/{id}/payoff-matrix` composer endpoint
- `services/game_theory.py` · `run_bayesian()` exists with 1,200 Monte Carlo · use for the cells
- `services/simulation/payoff.py` · new composer

**Prototype ref:** `prototype/wargame-agentic-cockpit.html` (cockpit + payoff section) · `prototype/persona-analyst-mayas-tuesday.html` (m5)

**Audit ref:** `phase-reports/phase5-gaps.docx` · Gap G4 · `tech-specs/tech-specs.docx` · B4

**Tasks:**
- [ ] T5.1.1 · Matrix layout · S
- [ ] T5.1.2 · Cell delta + confidence renderer with colour tier · S
- [ ] T5.1.3 · Recommended highlight + ribbon · S
- [ ] T5.1.4 · Hover tooltip with descriptor · S
- [ ] T5.1.5 · Backend: POST /war-rooms/{id}/payoff-matrix composer endpoint · M

### S5.2 · Adversary digital twins · posterior side panel

**As Maya** I want to see what we believe about Pfizer's archetype with confidence, so I know how robust the recommendation is.

**Acceptance criteria:**
- Six adversary digital twins (Pfizer, Lilly, AZN, FDA, Payer, KOL) · each with its own behavioural posterior
- Posterior renders as colour-coded bars (aggressive red, defensive amber, cash-constrained violet)
- "What shifted this?" log of last 5 evidence items that updated the posterior

**Code refs:**
- `services/adversary_twin.py` · new (per-competitor twin model)
- `api/routes/adversary.py` · new (`GET /adversaries/{id}/posterior`)
- `frontend/src/components/wargame/AdversaryPosteriorPanel.tsx` · new
- SPEC-028 grounding rules apply (adversary actions must cite evidence)

**Prototype ref:** `prototype/wargame-agentic-cockpit.html` (workforce twin lineup + digital twin deep-dive)

**Tasks:**
- [ ] T5.2.1 · Backend: adversary twin model + storage · L · `services/adversary_twin.py`
- [ ] T5.2.2 · Posterior bar component · S
- [ ] T5.2.3 · Backend posterior endpoint · M
- [ ] T5.2.4 · "What shifted this?" log · M
- [ ] T5.2.5 · 6 default twins seeded for diabetes/obesity TA · S

### S5.3 · Live cockpit · agent thinking-stream

**As Maya** I want to see the agents' reasoning live as the simulation runs, so the agents are colleagues not chatbots.

**Acceptance criteria:**
- Cockpit renders Strategist's reasoning steps live (done / now / queued)
- Sentinel + Curator panels show what they're subscribed to / waiting on
- Stress-test variants render beside baseline (8 variants showing flip vs hold)
- Override sliders let user tune assumptions; sim re-runs in seconds

**Code refs:**
- `frontend/src/pages/WarGameCockpit.tsx` · new (full-page cockpit surface)
- SSE stream `GET /war-rooms/{id}/cockpit-stream` · new endpoint
- `services/game_theory.py` · `run_bayesian()` already produces sample-by-sample; surface as stream

**Prototype ref:** `prototype/wargame-agentic-cockpit.html` (live cockpit section)

**Tasks:**
- [ ] T5.3.1 · Cockpit page route + layout · M
- [ ] T5.3.2 · Strategist thinking-stream component · M
- [ ] T5.3.3 · Sentinel + Curator panel components · S
- [ ] T5.3.4 · Stress-test variants grid · M
- [ ] T5.3.5 · Override slider panel · M
- [ ] T5.3.6 · SSE cockpit-stream endpoint · L

### S5.4 · Authority spectrum · 5 levels

**As Maya** I want to set how much autonomy each agent has per scenario type, so I can delegate routine sims and watch high-stakes ones.

**Acceptance criteria:**
- 5-level authority spectrum surfaced in war-room settings (L1 watch / L2 suggest / L3 recommend / L4 act-with-notice / L5 auto-audit)
- Per scenario type, default level + override
- Earned promotion based on Curator calibration window (>0.70 calibration → eligible for L3)

**Code refs:**
- `services/agent/authority.py` · new (calibration windowing + promotion logic)
- `api/routes/agent_authority.py` · new
- `frontend/src/pages/AuthoritySettings.tsx` · new

**Prototype ref:** `prototype/wargame-agentic-cockpit.html` (authority spectrum section)

**Tasks:**
- [ ] T5.4.1 · Authority model in code · M
- [ ] T5.4.2 · Calibration windowing per agent per scenario type · M
- [ ] T5.4.3 · Authority settings page · M
- [ ] T5.4.4 · Promotion notification flow · S

### S5.5 · Delegation · "run while I sleep"

**As Maya** I want to queue a scenario in the morning and read the verdict at 7am, so expensive sims don't block real time.

**Acceptance criteria:**
- Queue scenario with parameters + wake-me-up-only-if condition
- Agents run overnight, log every iteration to `game_theory_runs`
- Morning Pulse shows verdict with diff vs baseline + 2 new findings
- Replayable end-to-end

**Tasks:**
- [ ] T5.5.1 · Queue UI + parameter editor · M
- [ ] T5.5.2 · Backend: scheduled run executor · L
- [ ] T5.5.3 · Morning Pulse "delegated verdict" card · S
- [ ] T5.5.4 · Replay surface · M

---

# E6 · Chat surface upgrade

> **Weeks 13–14 · closes the audit's #1 chat finding (ConversationMemory wired) + adds 6 metadata patterns.**

## Why
ConversationMemory is fully implemented in `services/conversation_memory.py:66-125` but `WorkspacePage.tsx:81-95` builds its own shallow `buildHistory()` instead of calling it. Each turn is semi-independent. Wiring this in is the single highest-leverage chat fix. Plus: working set, citation progressive disclosure, branching.

## Stories

### S6.1 · Wire ConversationMemory across turns

**As Maya** I want each chat turn to remember the entities of every prior turn, so coreference works.

**Acceptance criteria:**
- `WorkspacePage.sendQuery` passes through `services/conversation_memory.ConversationMemory` (via `chat_handlers/context.py`)
- "this drug" / "that competitor" resolves to entity context from prior turns
- Branch indicator surfaced under user message: "Coreference resolved: this → tirzepatide (from turn 1)"

**Code refs:**
- `services/conversation_memory.py` · the class is built; just wire it
- `services/chat_handlers/context.py` · `build_conversation_context()` is the integration point
- `services/unified_handler.py` · UnifiedChatHandler.handle() receives the context
- `frontend/src/pages/WorkspacePage.tsx` · pass session_id; remove `buildHistory()`
- `api/routes/chat.py` · accept session_id; load memory by session

**Prototype ref:** `prototype/chat-graph-metadata.html` (chat surface, turn 2 user message + branch bar)

**Audit ref:** `phase-reports/phase3-heuristics.docx` · M7 (added by Phase 8 verification) · plus the audit's #1 transformative move

**Tasks:**
- [ ] T6.1.1 · Pass session_id from frontend to /chat · S
- [ ] T6.1.2 · Backend: load ConversationMemory by session_id · M
- [ ] T6.1.3 · Wire memory.get_context() into prompt assembly · M
- [ ] T6.1.4 · Coreference resolution in user prompt · M
- [ ] T6.1.5 · Branch indicator UI under user message · S
- [ ] T6.1.6 · Persist sessions across reloads · S

### S6.2 · Working set rail · entities pinned across the session

**As Maya** I want to see the entities I've touched in this session as a persistent rail, so I can pivot between them.

**Acceptance criteria:**
- Left rail shows entities Maya touched in session, sorted by recency
- Each entity card shows type + last-touched + turn count
- Pin button keeps an entity at top across sessions
- Click entity opens dossier in new pane

**Code refs:**
- `services/conversation_memory.py` · `get_entities_discussed()` already exists · just render
- `frontend/src/components/chat/WorkingSetRail.tsx` · new

**Prototype ref:** `prototype/chat-graph-metadata.html` (left rail of chat shell)

**Tasks:**
- [ ] T6.2.1 · WorkingSetRail component · M
- [ ] T6.2.2 · Pin/unpin persistence (localStorage scoped to session, then per-user) · S
- [ ] T6.2.3 · Click-to-open-dossier wiring · S

### S6.3 · Citation chips with progressive disclosure

**As Maya** I want every citation in the answer to tell me at a glance how trustable it is, and let me drill in with a click.

**Acceptance criteria:**
- Citation chip carries source tier in colour (green T1 · blue T2 · violet T3)
- Hover shows source name + date + 1-line snippet
- Click opens the matching evidence card in the right panel + highlights it
- Shift-click opens full source document

**Code refs:**
- `frontend/src/components/ui/CitationChip.tsx` · new (shared with E3, E4)
- `frontend/src/components/chat/NarrativeMessage.tsx` · lines 564-764 already render citations · refactor to use new chip
- `services/llm.py` · `validate_citations()` exists · ensure it tags with tier

**Prototype ref:** `prototype/chat-graph-metadata.html` (Pattern 1 · citation chip)

**Tasks:**
- [ ] T6.3.1 · CitationChip component (tier-coloured) · S
- [ ] T6.3.2 · Hover preview · S
- [ ] T6.3.3 · Click-to-jump-to-evidence interaction · S
- [ ] T6.3.4 · Shift-click open source · S
- [ ] T6.3.5 · Backend: ensure tier comes through with citation payload · S

### S6.4 · Multidimensional confidence pill

**As Maya** I want one composite confidence number plus four dimension bars, instead of three different vocabularies.

**Acceptance criteria:**
- Confidence rendered as pill: composite % + four dimension bars (evidence, source diversity, recency, calibration)
- Hover shows what each dimension means
- Click opens the why-this-confidence panel
- Replaces the current ConfidenceBadge enum + CalibrationChip + ImpactBadge inconsistency

**Code refs:**
- `frontend/src/components/ui/ConfidencePill.tsx` · new (replaces 3 components)
- `services/llm.py` · `synthesize()` returns `confidence_assessment` with `by_dimension`; verify shape
- `frontend/src/components/canvas/CanvasPanel.tsx` · lines 134-152 currently render single number · refactor

**Prototype ref:** `prototype/chat-graph-metadata.html` (Pattern 3 · confidence pill)

**Tasks:**
- [ ] T6.4.1 · ConfidencePill component · M
- [ ] T6.4.2 · Backend: ensure 4-dimension breakdown is returned · S
- [ ] T6.4.3 · Why-this-confidence panel · M
- [ ] T6.4.4 · Replace ConfidenceBadge / CalibrationChip / ImpactBadge across surfaces · M

### S6.5 · Source strip on every answer

**As Maya** I want a single horizontal strip showing what sources fed this answer, so I can scan provenance in 2 seconds.

**Acceptance criteria:**
- Strip rendered under every assistant message
- Shows per-source: tier dot + source name + count of cites from that source
- Click any source chip filters evidence panel to that source

**Tasks:**
- [ ] T6.5.1 · SourceStrip component · S
- [ ] T6.5.2 · Aggregate-by-source backend logic · S

### S6.6 · Why-this pattern across surfaces

**As Maya** I want a small "why this?" button next to anything proactive, so I can stop "wait why is the system showing me this?".

**Acceptance criteria:**
- Why-this button appears next to: Pulse cards, brief proposals, agent suggestions, war-game recommendations, framing trigger fires
- Click opens one-paragraph explanation in plain language + deep-link to factor breakdown / source registry / trigger config

**Tasks:**
- [ ] T6.6.1 · WhyThis button primitive · S
- [ ] T6.6.2 · Explanation generator (LLM-based with prompt template) · M
- [ ] T6.6.3 · Wire onto 5+ surfaces · M

---

# E7 · Graph as interlocutor

> **Week 15 · closes Phase 3 H + Phase 5 G7 · pivots the graph from picture to conversation partner.**

## Why
The graph renders well (Cytoscape, force-directed) but is read-only. The single transformative move: select a subgraph and the right panel becomes a chat-like inquiry surface — "what would you like to know about this network?" with smart suggestions specific to your selection.

## Stories

### S7.1 · Ask-this-subgraph panel

**As Maya** I want to select 2+ entities and ask the system a question about the network they form.

**Acceptance criteria:**
- Multi-select on graph nodes (cmd-click / lasso)
- Right panel shows "Ask this subgraph" with suggestions specific to selection (e.g. shortest path, three-way war-game, evidence on competes_with edges)
- Free-text composer beneath suggestions
- Routes through `/ask` with subgraph context

**Code refs:**
- `frontend/src/components/GraphExplorer.tsx` · add multi-select state + selection panel
- `frontend/src/components/graph/AskSubgraphPanel.tsx` · new
- `api/routes/ask.py` · `POST /ask` exists · accept `context.subgraph` (node_ids + edge_types)
- `services/llm.py` · context-aware question handling

**Prototype ref:** `prototype/chat-graph-metadata.html` (graph surface · ask-this-subgraph)

**Tasks:**
- [ ] T7.1.1 · Multi-select on graph (cmd-click + lasso) · M
- [ ] T7.1.2 · AskSubgraphPanel component · M
- [ ] T7.1.3 · Suggestion generator based on selection (shortest-path, evidence-on-edges, three-way) · M
- [ ] T7.1.4 · Backend: /ask accepts subgraph context · S

### S7.2 · Edge-type filters as first-class

**As Maya** I want to filter the graph by edge type (developed_by, competes_with, etc.), not just node type.

**Acceptance criteria:**
- Edge filters in left rail with colour swatches matching SVG strokes
- Per-edge-type counts visible
- Toggle hides edges of that type with smooth transition

**Code refs:**
- `services/graph.py` · `traverse()` already accepts `link_types` parameter · just expose

**Tasks:**
- [ ] T7.2.1 · Edge-type filter UI · S
- [ ] T7.2.2 · Filter state plumbing into traverse query · S

### S7.3 · Saved subgraphs · first-class objects

**As Maya** I want to save a subgraph view as a named object I can return to or share with my team.

**Acceptance criteria:**
- "Save view" button captures current graph state (centre entity, hops, filters, selection)
- Saved views in left rail; click reloads
- Shareable URL per saved view
- Versioned (re-save creates new version)

**Code refs:**
- `api/routes/saved_views.py` · new
- `services/saved_views.py` · new
- `frontend/src/components/graph/SavedViews.tsx` · new

**Tasks:**
- [ ] T7.3.1 · Backend: saved_views table + CRUD endpoints · M
- [ ] T7.3.2 · Save view UI · S
- [ ] T7.3.3 · Saved views list in left rail · S
- [ ] T7.3.4 · Shareable URL · S

### S7.4 · Path-finding result overlay

**As Maya** I want path-finding results highlighted on the graph (not just listed), so I can see the connection visually.

**Acceptance criteria:**
- Selecting 2 entities triggers path computation
- Result rendered as a callout + highlighted edges/nodes on the graph
- Alternative paths affordance

**Code refs:**
- `services/graph.py` · `path_between()` exists · just consume
- `frontend/src/components/GraphExplorer.tsx` · add path overlay rendering

**Tasks:**
- [ ] T7.4.1 · Path callout component · S
- [ ] T7.4.2 · Edge highlighting on selected path · S
- [ ] T7.4.3 · "Find alternatives" affordance · S

---

# E8 · Data catalog view

> **Weeks 16–17 · replaces the raw-JSON /connectors endpoint with a real catalog UI.**

## Why
The most differentiating asset of the platform (15 live connectors ingesting 162k+ trials) is exposed as a JSON dump at `/connectors`. The catalog has to do four jobs at once: show what's in the substrate (executive), show how good each piece is (steward), show what's missing (executive), and serve three personas without becoming cluttered.

## Stories

### S8.1 · Overview KPI strip + tier rollup

**As an executive** I want one screen that tells me how big the substrate is, how healthy it is, and what changed in the last 24 hours.

**Acceptance criteria:**
- KPI strip: connectors live · entities indexed · platform FAIR · HITL queue · signals overnight
- Per-tier rollup (T1 authoritative · T2 disclosure · T3 scientific · T4 licensed) with sources, records, freshness, FAIR

**Code refs:**
- `frontend/src/pages/CatalogPage.tsx` · new
- `api/routes/catalog.py` · `/catalog/stats` exists · extend with tier-rollup data

**Prototype ref:** `prototype/data-catalog-view.html` (overview section)

**Audit ref:** `data-layer-audit.docx` + Phase 5 G + v3 positioning

**Tasks:**
- [ ] T8.1.1 · CatalogPage route + layout · S
- [ ] T8.1.2 · KPI strip component · S
- [ ] T8.1.3 · Tier rollup component · S
- [ ] T8.1.4 · Backend: tier-rollup aggregation endpoint · S

### S8.2 · KBQ readiness strip

**As Maya** I want to see at a glance which KBQs the substrate can answer well.

**Acceptance criteria:**
- 8 KBQ tiles with score (1-5) + colour-coded bottom border
- Click tile opens per-KBQ detail (which sources feed it, which are missing)

**Tasks:**
- [ ] T8.2.1 · KBQ readiness strip component · S
- [ ] T8.2.2 · Per-KBQ detail page · M

### S8.3 · Ingestion activity stream + 24h health gauge

**As Ravi** I want to see what ran overnight, what failed, what drifted.

**Acceptance criteria:**
- Activity stream with timestamp + source + outcome + record count + drift flag
- 24h health gauge (uptime %)
- Daily breadcrumbs (cycles run, records ingested, drift events, cost)

**Tasks:**
- [ ] T8.3.1 · Activity stream component · S
- [ ] T8.3.2 · Health gauge component · S
- [ ] T8.3.3 · Backend: aggregate 24h stats endpoint · S

### S8.4 · Source detail dive

**As Ravi or Maya** I want to drill into any source and see its FAIR scoring, KBQ contributions, schedule, schema, top entities, recent records.

**Acceptance criteria:**
- Source detail page with FAIR (5 dimensions per spec §8.3) + KBQ contributions + schedule + schema preview + top entities + recent records

**Code refs:**
- `frontend/src/pages/SourceDetailPage.tsx` · new
- `api/routes/sources.py` · extend with FAIR breakdown + schema endpoint

**Tasks:**
- [ ] T8.4.1 · SourceDetailPage layout · M
- [ ] T8.4.2 · FAIR scoring renderer · S
- [ ] T8.4.3 · KBQ contribution renderer · S
- [ ] T8.4.4 · Schema preview component · S
- [ ] T8.4.5 · Top entities + recent records · S

### S8.5 · Entity browse · the analyst's view

**As Maya** I want to enter the catalog by entity not by source.

**Acceptance criteria:**
- Filterable entity catalog (entity type, quality score, source contributors, recency)
- Card grid with entity name + quality + source pills + connection count

**Tasks:**
- [ ] T8.5.1 · Entity browse page · M
- [ ] T8.5.2 · Filter rail · S
- [ ] T8.5.3 · Entity card grid · S

### S8.6 · Coverage gaps + roadmap surface

**As an executive** I want to see what's missing and when it ships.

**Acceptance criteria:**
- Roadmap timeline (15 NOW + 8 P1 + 6 P2 + 7 P3 + 7 P4 = 43 future)
- Per-phase row detail (what's in each, when, cost)
- Per-KBQ closure breakdown

**Tasks:**
- [ ] T8.6.1 · Roadmap timeline component · M
- [ ] T8.6.2 · Per-phase + per-KBQ closure rendering · S

### S8.7 · Licence health panel

**As an executive** I want cost transparency: what's free, what's paid, what's renewing soon, what would degrade if a licence lapsed.

**Acceptance criteria:**
- Per-source row: annual cost · renewal date · health pill
- Total today · projected after Phase 2

**Tasks:**
- [ ] T8.7.1 · Licence health table · S
- [ ] T8.7.2 · Backend: licence model in source registry · M

### S8.8 · BYOD + connector marketplace

**As anyone** I want three doors to add to the substrate: upload doc, request connector, build custom.

**Acceptance criteria:**
- Three card affordances (drop file, browse roadmap & vote, open SDK)
- Pending requests queue with vote counts

**Tasks:**
- [ ] T8.8.1 · Three-door card layout · S
- [ ] T8.8.2 · Drop-file pipeline animation (reuse from Ravi prototype) · M
- [ ] T8.8.3 · Connector roadmap browse + vote · M
- [ ] T8.8.4 · Pending requests queue · S

### S8.9 · Decommission /connectors raw JSON

**As anyone** I want /connectors to redirect to the new catalog page, not return JSON.

**Tasks:**
- [ ] T8.9.1 · Move JSON response to `/api/connectors` (machine-readable preserved) · S
- [ ] T8.9.2 · `/connectors` 301 redirects to `/catalog` · S

---

# E9 · Phase 1 connectors · 8 free public sources

> **Weeks 18–21 · closes the largest unfed KBQ gaps with zero licence cost.**

## Why
Per `data-layer-audit.docx`, eight free public sources close major pieces of KBQs 4, 7, 8, 10 with engineering-only cost. No licence negotiation, no recurring spend.

## Stories

### S9.1 · USPTO PatentsView API connector

**Closes:** KBQ-10 Patent · effort: S

**Code refs:**
- `connectors/uspto.py` · new (inherits from `connectors/base.py`)
- `integration/pipeline_hooks.py` · register USPTO source
- `domain/pharma/pack.py` · add patent entity type if not present

**Tasks:**
- [ ] T9.1.1 · Implement USPTO connector · S
- [ ] T9.1.2 · Schema + entity resolution rules · S
- [ ] T9.1.3 · Cron schedule (weekly) · S
- [ ] T9.1.4 · Tests · S

### S9.2 · EPO Patents (OPS API)
- [ ] T9.2.1 · Implement EPO connector · S

### S9.3 · bioRxiv + medRxiv preprints
- [ ] T9.3.1 · Implement preprint connector with RSS + API · S

### S9.4 · FDA OPDP warning letters
- [ ] T9.4.1 · Implement FDA OPDP scraper + parser · S

### S9.5 · CMS Medicare Part D formulary files (50 plan files)
- [ ] T9.5.1 · Implement CMS Part D batch connector · M

### S9.6 · CMS Medicare B + D pricing files
- [ ] T9.6.1 · Implement CMS pricing connector · M

### S9.7 · WHO ICTRP global trial registry
- [ ] T9.7.1 · Implement WHO ICTRP connector · S
- [ ] T9.7.2 · Cross-walk to canonical Trial entity · S

### S9.8 · VA / DoD national formulary
- [ ] T9.8.1 · Implement VA/DoD formulary connector · S

---

# E10 · Source registry + FAIR scoring

> **Week 22 · the steward's quality scaffolding · spec §8.3 mandate.**

## Why
Per spec §8.3, every source must be a tracked entity with learned multi-dimensional quality scoring. Today scoring exists in code but isn't surfaced.

## Stories

### S10.1 · Source registry surface
- [ ] T10.1.1 · Source registry page (admin/steward) · M
- [ ] T10.1.2 · Per-source FAIR detail · S
- [ ] T10.1.3 · Editable usage profile (per spec §11.4) · M

### S10.2 · Curator-driven weight learning
- [ ] T10.2.1 · Outcome-to-weight feedback loop · L · `services/curator/weight_learning.py`
- [ ] T10.2.2 · Weekly recalibration job · M
- [ ] T10.2.3 · Weight-change audit log · S

### S10.3 · Source health monitoring + graceful degradation
- [ ] T10.3.1 · Per-source SLA monitoring · M
- [ ] T10.3.2 · "Missing because" inline message in user-facing answers · M

---

# E11 · Multi-tenancy enforcement

> **Week 23 · the SaaS-blocker fix · the most important security/architecture epic.**

## Why
The intelligence layer audit identified this as a critical gap. `scope_key` exists on `chat_sessions` and `deep_research_jobs` but core entity tables have no `tenant_id` and `services/search.py` does not WHERE-filter by scope. A misconfigured query returns Pfizer's data inside Roche's session.

## Stories

### S11.1 · Tenant model in core entity tables
- [ ] T11.1.1 · Add `tenant_id` column to drugs, companies, trials, mechanisms · L · `schema/migrations/`
- [ ] T11.1.2 · Backfill tenant_id for existing records · M
- [ ] T11.1.3 · Add NOT NULL constraint after backfill · S

### S11.2 · Query middleware for tenant isolation
- [ ] T11.2.1 · Inject tenant_id into all WHERE clauses via DB middleware · L
- [ ] T11.2.2 · `services/search.py` tenant filter · M
- [ ] T11.2.3 · `services/graph.py` tenant filter · M

### S11.3 · Tenant audit surface + isolation tests
- [ ] T11.3.1 · Tenant audit page (per Ravi prototype m6) · M
- [ ] T11.3.2 · Automated cross-tenant isolation tests in CI · M
- [ ] T11.3.3 · Audit trail per tenant (90d retention) · M

---

# E12 · Prompt registry + active feedback

> **Week 24 · closes the learning loop · spec §10.3.**

## Why
Prompt registry table exists (`prompt_registry`) and `llm_call_log.prompt_id` is wired, but core system prompts are hardcoded in `services/llm.py:179-250` (the SYSTEM_PROMPTS dict) and the feedback loop is post-hoc not active.

## Stories

### S12.1 · Promote system prompts to the registry
- [ ] T12.1.1 · Migrate SYSTEM_PROMPTS dict to prompt_registry · M
- [ ] T12.1.2 · Update services/llm.py to load prompts from registry · M
- [ ] T12.1.3 · Versioning + A/B testing harness · L

### S12.2 · Active feedback loop
- [ ] T12.2.1 · Outcome-to-prompt-weight backpropagation · L · per spec §6.5.2
- [ ] T12.2.2 · Flagged-prompt rollback flow (Ravi prototype m7) · M
- [ ] T12.2.3 · Weekly calibration job per prompt · M

### S12.3 · Prompt registry surface
- [ ] T12.3.1 · Registry page (admin) · M
- [ ] T12.3.2 · Per-prompt calibration history · S
- [ ] T12.3.3 · Cost + latency trends per prompt · S

---

# Cross-cutting concerns

## Performance budget · premium surfaces only
Premium surfaces: SensingFeed, Dossier, War-Game Cockpit, Brief Composer, Learning Loop.

| Metric | Target |
|---|---|
| First Meaningful Paint | < 200ms |
| Time-to-Interactive | < 500ms |
| Largest Contentful Paint | < 800ms |
| Cumulative Layout Shift | < 0.05 |
| First Input Delay | < 60ms |

Enforced via Lighthouse CI in build pipeline. PRs that regress >50ms blocked.

## Accessibility minimum
- Lighthouse a11y ≥ 95 on every premium surface
- Keyboard contract published per surface (open via "?" overlay)
- All interactive surfaces respect `prefers-reduced-motion`
- WCAG AA contrast verified on both themes

## Telemetry per epic
Every premium surface emits `/telemetry` events on first view, on each significant interaction, on exit. Curator agent consumes these to recalibrate.

## Migration plans
Every legacy → new transition has:
1. Read-only legacy mode period (typically 2 weeks)
2. Auto-migration script with reversible rollback
3. Data integrity verification post-migration

## Decommission list (do these in week 25)
- [ ] Legacy DecisionsTab + `mz_legacy_decisions` flag path · `frontend/src/pages/CIPage.tsx:176-193`
- [ ] Auto-login of role=enterprise · `frontend/src/pages/CIPage.tsx:75-82`
- [ ] LandingPage two-CTA hero · `frontend/src/pages/LandingPage.tsx:99-108`
- [ ] LandingPage "Phase 01/02/03/04" pillar grid
- [ ] `newui.css` legacy stylesheet
- [ ] Mobile bottom-nav truncation `slice(0,4)` · `frontend/src/pages/CIPage.tsx:207-224`
- [ ] 150 lines of legacy Tailwind class overrides · `frontend/src/index.css`

## What NOT to build (deferred beyond week 24)
Per `phase-reports/phase8-verification.docx` Agent D feasibility check:
- Bayesian / Stackelberg / POMDP layer of war-game board (SPEC-025) — v2 of E5
- Decision signing (SPEC-034) — enterprise-only, ships when buyer demands
- Full Catalog deprecation — after dossier proves itself for one entity type
- Full Phase 2 paid connector integration — after executive cost-benefit on each

---

## How this becomes a tracker

Each epic above maps to one tracker epic. Each story maps to one tracker issue. Each task maps to one sub-task or PR. The acceptance criteria become the issue's Definition of Done. The code refs and prototype refs become the issue's "Resources" section.

For Linear: each `### S` heading becomes an issue title; each `- [ ] T` becomes a sub-issue; the prototype ref + audit ref + code refs become a "Spec" section in the description.

For Jira: same pattern using Epic > Story > Sub-task hierarchy.

For GitHub: convert each S to a milestone; each T to an issue with the `epic-NN` and `weeks-XX-YY` labels.

---

> **The bridge from audit to action. Walk it.**
> — Closing line of `executive-summary.docx`

