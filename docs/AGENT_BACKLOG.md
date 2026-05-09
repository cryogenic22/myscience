# Agent Backlog

Cross-domain bug & request board between Claude (backend) and Antigravity
(frontend). Either agent may file. Items are tagged by area and addressed by
the agent who owns that area.

> **Note**: For product/feature backlog, see `docs/backlog.md`. This file is
> only for agent-to-agent coordination.

Tags:
- `[BACKEND]` — request directed at Claude
- `[FRONTEND]` — request directed at Antigravity
- `[PROTOCOL]` — protocol violation or ambiguity; user mediates

Format:
```
## [TAG] Short title
- Filed: YYYY-MM-DD by <agent>
- Need / Repro: <what's needed or how to reproduce>
- Why: <motivation>
- Priority: low | medium | high | urgent
- Status: open | in-progress | done | wontfix
```

---

## [FRONTEND] InboxTab login wall blocks the default landing
- Filed: 2026-05-09 by Claude
- Repro: Open `/ci` (the CI page) without an `mz_auth_token` in localStorage.
  The default tab is now `inbox` (since Phase E), which renders only the message
  "Log in (viewer or above) to see your decision inbox." with no login CTA.
- Why: Hostile first impression — unauthenticated users hit a dead end on the
  primary surface. The user reported this directly.
- Suggested fix: Either (a) detect auth state in `frontend/src/pages/CIPage.tsx`
  and default unauth users to `digest` (which works without auth), OR (b)
  replace the message in `frontend/src/components/ci/InboxTab.tsx` with a real
  login CTA + button that routes to `/login`, OR (c) both.
- Reference: `frontend/src/pages/CIPage.tsx:39` (default tab) and
  `frontend/src/components/ci/InboxTab.tsx` (unauth branch).
- Priority: urgent
- Status: **done** (2026-05-09 — see `docs/UI_CHANGELOG.md`. CIPage defaults
  unauthed users to `digest`; InboxTab unauth branch now renders a real login CTA.)

## [FRONTEND] UI is "demo-grade" — needs Phase F Cockpit redesign
- Filed: 2026-05-09 by Claude
- Need: Comprehensive UX/UI redesign matching the sophistication of Oura Ring,
  Apple Health, Apple.com, Spotify. User has explicitly asked for this.
- Reference prototype: `specs/test.tsx` — the "north star" — sophisticated dark
  theme, SVG flow diagrams, Syne+DM Mono typography, color-coded scoring matrices.
- Suggested approach: Write `specs/SPEC_022_cockpit_design_system.md` first
  with: design tokens (light + dark), motion principles, typography hierarchy,
  component primitives (MetricRing, Sparkline, RadarChart, FlowDiagram,
  Timeline, AgentStatusBar, HeroCard), phased implementation plan.
- Implement progressively per surface, behind feature flag
  `localStorage.mz_ui_v2 === 'true'` until ready to flip.
- Priority: high
- Status: open

---

# CI Decision Flywheel v2 — items from `specs/CI_Agent_Reimagined_Spec.md`

The CI Agent Reimagined Spec (filed 2026-05-09) describes a next-generation
Decision Flywheel platform. Much of it is **already partially built** in
SPEC-021. The items below are the gaps between current state and the spec's
target state. Each is tagged for ownership.

> **Coordination rule** (per `AGENTS.md` §5): items marked `[CROSS-CUTTING]`
> require a written `specs/SPEC_NNN_*.md` with sign-off from BOTH agents
> before implementation begins. The spec defines the data contract; backend
> ships first, frontend consumes.

---

## Backend backlog (Claude)

### [BACKEND] Decision Brief object (first-class, with options + stakeholders)
- Filed: 2026-05-09 by Claude (from spec §6.2.2)
- Need: Promote war_rooms / decisions into a proper `decision_briefs` table
  with: `brief_id`, `question`, `trigger_signal_ids[]`, `stakeholders[]`,
  `time_horizon`, `options[]` (min 2, target 3-5), `evidence_refs[]`,
  `constraints[]`, `success_criteria`, `confidence_to_proceed`, plus a state
  machine (`draft → human_review → simulation_pending → simulation_complete →
  decision_pending → committed → in_review → closed`).
- Why: Current `war_rooms` are option-discovery surfaces and current `decisions`
  capture commitment, but neither is a structured Brief that frames the
  question + stakeholders + success criteria up-front. Spec treats this as
  the canonical handoff from sensing → simulation.
- Cross-cutting: write `specs/SPEC_023_decision_briefs.md` first (data contract
  blocks frontend Decision Workspace work).
- Priority: high
- Status: **done** (2026-05-09 — `specs/SPEC_023_decision_briefs.md`,
  migration 052, `services/decision_brief.py`, `api/routes/decision_briefs.py`,
  31 tests green. Commits 1dace1c + b0e52b5.)

### [BACKEND] Triggers — threshold / cluster / calendar
- Filed: 2026-05-09 by Claude (from spec §6.2.1)
- Need: A `framing_triggers` evaluator (cron-style, runs every 5 min) that
  detects: (a) any signal with materiality_score ≥ 80, (b) ≥3 related signals
  within a rolling window, (c) calendar-scheduled review points. On trigger,
  auto-creates a draft DecisionBrief and routes to the assigned strategist.
- Why: Today decisions only get created when a human opens a war room.
  Auto-framing closes the signal-to-decision latency gap (spec target: <24h).
- Depends on: Decision Brief object above.
- Priority: medium
- Status: open

### [BACKEND] Materiality scoring — learned model with calibration
- Filed: 2026-05-09 by Claude (from spec §6.1.2)
- Need: Replace the current heuristic scorer with a trained model whose
  inputs include source tier, entity criticality, claim type, recency.
  Calibration reviewed quarterly. Outputs go on every signal as
  `materiality_score` (0-100) plus a JSON `materiality_factors` explaining
  the score (so the frontend signal card can show "why this is material").
- Why: Spec metric "materiality precision >70%". Today's scoring is a single
  weight, not factor-attributed. Antigravity's signal cards need the factor
  breakdown.
- Priority: high
- Status: **done** (2026-05-09 — specs/SPEC_031_materiality_scoring.md, migration 058, services/materiality.py, api/routes/materiality.py, 29 tests green. Factor-attributed v1; learned weight tuning deferred to SPEC-028 Learning Service.)

### [BACKEND] Source registry with quality scoring (5 dimensions)
- Filed: 2026-05-09 by Claude (from spec §8.3)
- Need: A `sources` table with per-source quality across 5 dimensions:
  coverage, latency, predictive_accuracy, stability, license_health. Computed
  nightly. Surfaced via `GET /sources/health` for the Source Health admin UI.
- Why: Today connectors are hard-coded; no learned weighting. Spec target:
  source weights influence materiality scoring + evidence ranking.
- Priority: medium
- Status: **done** (2026-05-09 — `specs/SPEC_027_source_registry.md`,
  migration 055, `services/source_registry.py`, `api/routes/sources.py`,
  36 tests green. 5-dim scoring with documented weights + license-health
  linear degradation. `predictive_accuracy` placeholder until SPEC-028.)

### [BACKEND] Evidence ledger — content-addressed claim provenance
- Filed: 2026-05-09 by Claude (from spec §8.2)
- Need: Append-only `evidence_ledger` table: `source_id`, `source_url`,
  `archived_snapshot_ref` (S3 key for snapshot), `retrieved_at`,
  `extraction_method` (agent + model + prompt versions), `extracted_text`
  (exact passage), `confidence` (calibrated 0-1), `contradicting_evidence_ids[]`.
  Every Claim node in the graph references one or more ledger records.
- Why: Spec hallucination-control invariant: "every claim must be linkable to
  one or more evidence ledger records." Today provenance is `provenance_source`
  string — not reproducible, not content-addressed.
- Cross-cutting: spec §11.2 reproducibility ("given a decision_id, recreate
  exact evidence available at decision time"). Frontend Evidence Panel +
  evidence-affordance click-throughs depend on this.
- Priority: high
- Status: open

### [BACKEND] War-game adversaries — multi-agent role-play
- Filed: 2026-05-09 by Claude (from spec §6.3.2)
- Need: Replace current single move-suggester with adversary panel:
  - `CompetitorAgent` (one per top-3 competitor, prompted with that
    competitor's known strategy + recent moves + financial position from KG)
  - `PayerAgent` (formulary economics, IRA pressure, recent decisions)
  - `RegulatorAgent` (FDA/EMA posture, advisory committee patterns)
  - `KOLAgent` (clinical opinion-leader + patient advocacy reactions)
  Each reacts per option per round (default 3 rounds). Discipline rule:
  every adversary action MUST be tagged with a historical precedent or
  stated strategy from the KG. Outputs: war-game transcript per option.
- Why: Spec calls this "the most distinctive capability." Current war room
  scoring matrix is static; adversary role-play is the simulation upgrade.
- Cross-cutting: write `specs/SPEC_024_adversary_war_game.md`. Frontend
  War-Room mode (real-time multi-user with adversary transcripts) depends.
- Priority: medium
- Status: open

### [BACKEND] Monte Carlo simulation service
- Filed: 2026-05-09 by Claude (from spec §6.3.1)
- Need: Probabilistic outcome distributions — for each Brief option, run N
  trials with parameter uncertainty, return distribution + sensitivity ranking
  + assumptions log + reproducibility seed.
- Why: Spec mode for pricing decisions, launch-timing, R&D portfolio prio.
- Priority: medium (deferred until Decision Brief object lands)
- Status: open

### [BACKEND] LLM Gateway — centralized provider + prompt registry
- Filed: 2026-05-09 by Claude (from spec §10.3)
- Need: Promote `llm_telemetry.chat_with_telemetry` into a proper Gateway
  service: prompt registry (versioned, addressable by prompt_id), provider
  abstraction (route per-task), centralized cost guardrails, PII filter on
  the way out, content-policy filter on the way in. Every prompt used in
  prod is registered + tied to outcomes (so Learning Service can attribute
  prediction accuracy to specific prompt versions).
- Why: Today prompts are scattered across services. Spec calls this
  "non-negotiable" for cost visibility, prompt versioning, provider
  portability, and PII safety.
- Priority: medium
- Status: **done** (2026-05-09 — `specs/SPEC_026_llm_gateway.md`,
  migration 054, `services/llm_gateway.py`, `api/routes/llm_gateway.py`,
  46 tests green. Prompt registry + PII filter (email/SSN/phone/Luhn-CC) +
  cost summary endpoint. Provider abstraction deferred to follow-up.)

### [BACKEND] Learning Service — source-weight + agent-strategy updates
- Filed: 2026-05-09 by Claude (from spec §6.5.2)
- Need: Nightly job + on-review-trigger that:
  1. Compares predicted vs actual outcome on every Decision past `review_at`
  2. Attributes accuracy to source(s) that contributed evidence
  3. Updates `sources.predictive_accuracy` (raises good sources, demotes bad)
  4. Flags prompt versions with poor accuracy for review
  5. Retrains recommendation calibration model when N new outcomes accumulated
- Why: This is the "flywheel rotating" — today we capture outcomes but don't
  feed them back into source weights or prompt selection.
- Depends on: Source registry (above) + LLM Gateway (above).
- Priority: medium
- Status: open

### [BACKEND] Counter-recommendation enforcement
- Filed: 2026-05-09 by Claude (from spec §6.4.1)
- Need: Recommendation Agent must always return at least one well-argued
  counter-recommendation alongside its top pick. Rejected if it doesn't.
  Spec: "A unanimous AI is a suspicious AI."
- Why: Cheap, high-trust win. Antigravity needs the dissent payload to render
  a "Dissent view" panel in the Decision Workspace.
- Priority: low (cheap to add when Decision Workspace is being built)
- Status: open

### [BACKEND] Decision signing + immutable evidence_snapshot
- Filed: 2026-05-09 by Claude (from spec §6.4.2 + §11.2)
- Need: On decision commit, freeze `evidence_snapshot` (a content hash of all
  ledger records referenced by the brief at commit time) and cryptographically
  sign the immutable fields with the decision-maker's session token. Replay
  endpoint: `GET /decisions/{id}/replay` reconstructs exact agent calls,
  prompts, and outputs from snapshot + LLM call log.
- Why: Spec "every decision is reproducible." Required for audit/compliance.
- Depends on: Evidence ledger (above) + LLM Gateway (above).
- Priority: medium
- Status: open

### [BACKEND] /ask graph-traversal natural-language endpoint
- Filed: 2026-05-09 by Claude (from spec §9.2.4 "Ask-Anything")
- Need: NL → Cypher (or SQL recursive CTE) → graph traversal. Returns
  graph-shaped result (nodes + edges, deep-linkable to entity pages), not a
  flat search result list.
- Why: Spec persistent overlay; every page can ask "show me every product in
  my TA whose payer access has degraded in the last 90 days."
- Priority: medium
- Status: open

---

## Game-theoretic simulation backlog (Claude)

> Adds formal game-theoretic structure to the war-game layer. All three items
> roll up under `specs/SPEC_025_game_theoretic_simulation.md`. Depends on
> SPEC_028 War-Game Adversaries landing first.

### [BACKEND] Bayesian war-game upgrade — incomplete-information adversaries
- Filed: 2026-05-09 by Claude (from game-theory recommendation)
- Need: Each adversary agent carries a "type distribution" over private states
  (e.g., CompetitorAgent type ∈ {aggressive, defensive, cash-constrained} with
  prior probabilities sourced from KG signals). Each round samples a type per
  adversary; reactions are belief-distributions, not point reactions. Output:
  posterior over outcomes per option after N rounds.
- Why: Pharma adversaries have private info (pipeline state, internal Phase 2
  reads, cost structure). Treating them as fully observable misses the central
  uncertainty in CI strategy.
- Depends on: SPEC_028 war-game adversaries.
- Priority: medium
- Status: open

### [BACKEND] Stackelberg sequencing module — leader-follower analysis
- Filed: 2026-05-09 by Claude (from game-theory recommendation)
- Need: For any Decision Brief option that is timing-sensitive (launch date,
  readout date, regulatory submission date), compute the Stackelberg-optimal
  competitor counter-move. Algorithm: enumerate competitor's response set,
  apply their estimated payoff function (sourced from KG + recent moves),
  return arg-max counter. Surface as a "Stackelberg outlook" panel in the
  simulation output: "If you accelerate Phase 3 readout 4 months, the
  Stackelberg-optimal Pfizer response is to fast-follow with PRGN-2009 +
  defensive pricing in 2L."
- Why: Pharma launches are inherently sequential — first-mover sets context,
  follower optimizes against it. Current simultaneous-move war-game misses
  this structure.
- Depends on: SPEC_028 war-game adversaries.
- Priority: medium
- Status: open

### [BACKEND] POMDP value-of-information service
- Filed: 2026-05-09 by Claude (from game-theory recommendation)
- Need: For any pending Decision Brief, compute expected information value
  of waiting for upcoming signals (earnings calendar, FDA action calendar,
  conference dates from KG). Frame the brief as a POMDP: signals → posterior
  belief update → optimal action under updated belief. Compare expected utility
  of "decide now with current belief" vs "wait W weeks, decide with updated
  belief minus W·discount_rate." Surface as a "Wait vs Decide" panel.
- Why: Strategists routinely face the question "is it worth waiting for the
  next earnings call?" Today this is intuition; the POMDP gives a principled
  answer with explicit assumptions.
- Priority: medium
- Status: open

---

## Frontend backlog (Antigravity)

> All items below trace to spec §9 (Frontend Design Specification). Items
> marked **[needs backend]** are blocked on a corresponding [BACKEND] item
> above; items marked **[buildable now]** can ship against today's API.

### [FRONTEND] Sensing Feed as default Inbox surface — [buildable now]
- Filed: 2026-05-09 by Claude (from spec §9.1.1)
- Need: Replace current InboxTab with a Sensing Feed: per-user materiality-
  ranked signal stream, organized by entity (focal product, top competitors,
  key indications). Each signal card shows: source, timestamp, materiality
  score WITH the factors driving it (waiting on backend factor breakdown but
  ship without first), KBQ view(s) it changed, one-click "frame as decision."
- Spec ref: §9.1.1 Always-On Sensing Mode
- Reads: `GET /signals` (cursor-paginated), `GET /inbox`
- Priority: high
- Status: open

### [FRONTEND] Confidence as a first-class visual — [buildable now]
- Filed: 2026-05-09 by Claude (from spec §9.2.1)
- Need: Every claim, recommendation, forecast across the app renders with a
  visible confidence indicator. Never show a number without uncertainty;
  never collapse a range into a point estimate without explicit user click.
  Build a `<Confidence value={0.74} />` primitive with tier coloring + tooltip.
- Spec ref: §9.2.1
- Priority: high
- Status: open

### [FRONTEND] Evidence panel — one-click from any claim — [buildable now]
- Filed: 2026-05-09 by Claude (from spec §9.2.2)
- Need: Every claim across the UI has an "evidence" affordance (small icon
  next to the claim) that opens a side panel showing: source, retrieved_at,
  exact passage, contradicting evidence (if any), agent reasoning that
  produced the claim. Build a `<EvidenceAffordance claimId={...} />` primitive.
- Spec ref: §9.2.2
- Reads: `GET /evidence/{claim_id}` (lightweight; backs onto current
  provenance fields until evidence ledger ships, then upgrades).
- Priority: high
- Status: open

### [FRONTEND] Disagreement-surface design — [buildable now]
- Filed: 2026-05-09 by Claude (from spec §9.2.3)
- Need: When two sources disagree on a claim (e.g., formulary tier 2 vs tier 3),
  the UI surfaces both side-by-side, ranks by source quality, lets the user
  designate which to accept or escalate.
- Spec ref: §9.2.3
- Priority: medium
- Status: open

### [FRONTEND] Decision Workspace — multi-panel single-page surface — [needs backend]
- Filed: 2026-05-09 by Claude (from spec §9.1.2)
- Need: 5-panel layout per spec:
  - Brief panel (top): question, options, time horizon, stakeholders (editable
    until simulation runs)
  - Evidence panel (left): KBQ views, deep-linkable to source records
  - Simulation panel (center): scenario / Monte Carlo / war-game outputs with
    interactive sensitivity controls
  - Recommendation panel (right): ranked options, Dissent view, commit action
  - Reasoning trace (collapsible drawer): full chain of agent calls + prompts
    + intermediate outputs
- Spec ref: §9.1.2
- Blocked on: Decision Brief object backend [BACKEND above]
- Priority: high
- Status: open

### [FRONTEND] War-Room Mode — real-time multi-user — [needs backend]
- Filed: 2026-05-09 by Claude (from spec §9.1.3)
- Need: Multiple users join the same Decision Brief, see live-updating
  evidence + simulations, run new war-game rounds with custom adversary
  prompts, chat alongside the workspace. Session persisted as Decision Brief
  artifact when room closes.
- Spec ref: §9.1.3
- Blocked on: war-game adversary backend + WebSocket/SSE channel
- Priority: medium
- Status: open

### [FRONTEND] Outcome Dashboard — predictions vs outcomes — [partial-now / full-needs-backend]
- Filed: 2026-05-09 by Claude (from spec §9.3 + §13.1)
- Need: Surface that shows: prediction accuracy over time (current
  InsightsTab is the seed), source-quality trends, agent-strategy performance.
- Spec ref: §9.3, §13
- Buildable now from `GET /insights`; full version blocked on Source registry
  + Learning Service.
- Priority: medium
- Status: open

### [FRONTEND] Source Health admin surface — [needs backend]
- Filed: 2026-05-09 by Claude (from spec §9.3)
- Need: Per-source freshness, error rates, license status, quality scores
  (5 dimensions). Power-user / admin surface.
- Spec ref: §9.3
- Blocked on: Source registry [BACKEND above]
- Priority: low
- Status: open

### [FRONTEND] Ask-Anything persistent overlay — [needs backend]
- Filed: 2026-05-09 by Claude (from spec §9.2.4)
- Need: Persistent NL input (⌘K palette feel) that runs graph traversals.
  Results render as graph-shaped result (nodes + edges, deep-linkable to
  entity views), not flat search list.
- Spec ref: §9.2.4
- Blocked on: `/ask` endpoint [BACKEND above]
- Priority: medium
- Status: open

### [FRONTEND] Reasoning trace UI — [partial-now]
- Filed: 2026-05-09 by Claude (from spec §10.4 observability)
- Need: Collapsible drawer in Decision Workspace showing full chain of agent
  calls, prompts, intermediate outputs. Backend already has `llm_call_log`;
  needs surface to render trace given a brief_id or decision_id.
- Spec ref: §10.4 ("trace ID surfaced in the Reasoning Trace UI panel")
- Priority: medium
- Status: open

