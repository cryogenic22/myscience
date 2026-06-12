# Helix — Full-Stack Loop Specs (backend + frontend)

*Author: data/intelligence lane. Date: 2026-06-12. Status: active.*

> **Why this doc.** `docs/helix-intelligence-buildplan.md` (#226) specs the
> **backend/data** loops + the Output-Quality Benchmark (OQ1–OQ6). This companion
> pairs each loop with its **frontend** vertical slice so a capability ships
> *visible*, not just wired — and gates each slice on the same OQ benchmark.
> Sequencing and OQ mapping follow #226 exactly; this adds the UI contract and
> reuses the existing CI surfaces (`ScenariosContainer`, `ProvenancePanel`,
> `scenariosApi`, the `Sparkline`/`ProbabilityDial` atoms).
>
> Already shipped: **#223** = build-plan Loop 1 core (signal stance →
> downward calibration, grounded in `signals.direction`). These full-stack loops
> complete and surface it.

## Reuse map (verified on `origin/main`)
| Surface | Path |
|---|---|
| Scenario read/derive API | `api/routes/engagements.py` `GET/POST …/scenarios[/assemble]` |
| Scenario model + persist | `services/scenarios.py` (`to_dict`, `persist_scenarios`) |
| Calibration | `services/scenario_calibration.py` (`calibrate_engagement_scenarios`) |
| Scenarios stage container | `frontend/src/components/ci/ScenariosContainer.tsx` |
| Provenance drill panel | `frontend/src/components/ci/ProvenancePanel.tsx` |
| API client | `frontend/src/api.ts` `scenariosApi` |
| Trend/sparkline atom | `frontend/src/components/ci/InsightsTab.tsx` `Sparkline` |
| Prior→current dial | `frontend/src/pages/ScenariosPage.tsx` `ProbabilityDial` |
| Next migration # | **092** (origin/main at 091_crosswalk_records) |

---

## FS-1 — Scenario Probability History + Timeline  *(OQ2 / H-b; completes Loop 1 DoD)*
**Capability:** every probability move is auditable and visible — "this scenario
dropped 0.50→0.38 because of a negative tirzepatide readout on 2026-06-10."

**Backend**
- Migration **092** `scenario_calibration_history` (append-only): `id`,
  `scenario_id` FK, `prev_prob`, `new_prob`, `delta`, `n_supporting`,
  `n_contradicting`, `triggering_signal_id` (nullable FK), `method`,
  `calibration_note`, `created_at`. GIST/btree index on `(scenario_id, created_at)`.
- `scenario_calibration.calibrate_engagement_scenarios`: when `current_prob`
  changes, append a history row (prev→new→delta + the stance mix already computed
  in #223 + latest triggering signal). Append-only, no UPDATE. Idempotent: only
  append when the value actually changed (skip no-op recomputes).
- API `GET /engagements/{eid}/scenarios/{sid}/probability-history` → ordered rows.
- **Tests (Lane-1):** a probability change writes exactly one history row; a no-op
  recompute writes none (idempotent); a `contradicts`-driven drop writes a row
  with `delta < 0` and `n_contradicting > 0` (this is **OQ2** structural gate).

**Frontend**
- `scenariosApi.history(eid, sid)` client (mirror `scenariosApi.get`).
- `ProbabilityTimeline` component (reuse the `Sparkline` div/flex pattern — no new
  dep): a compact prob-over-time line on each scenario card; up moves green, down
  moves amber/red; hover shows delta + note + date.
- Click a point → `ProvenancePanel` on the triggering signal/fact (reuse existing
  panel + `onOpenFact`).
- **Test:** renders the timeline from a history fixture incl. a downward move;
  empty history → "no calibration yet" honest empty state.

**DoD:** OQ2 green on the CagriSema fixture; downward move from #223 is visible
with its audit row; prod probe shows a real history row when a calibration runs.

---

## FS-2 — Contradiction as first-class + surfacing  *(OQ3 / Loop 1 remainder)*
**Capability:** a contradicting signal is *shown*, not averaged away.

**Backend:** persist per-scenario the contributing signals' stance (supports/
contradicts) so the API can expose them; add a `contradiction` marker on the
scenario payload when ≥1 contradicting signal contributed. (Reuses #223
`signal_stance`; no new model.) Expose in `Scenario.to_dict()`.
**Frontend:** supports/contradicts chips on the scenario's signal list; a
"⚠ contradicted" badge on the scenario card; the contradiction is never silently
reconciled. Reuse the existing scenario card + chip styles.
**DoD:** OQ3 structural gate green; a contradicted scenario reads as contradicted.

---

## FS-3 — Helix Readiness Checklist  *(H-d / P6 / OQ5)*
**Capability:** per-domain readiness so "beautiful but unsupported" fails loud.

**Backend:** extend dossier domain state beyond `complete/in_progress/gap` with
`contradicted` (conflicting facts in domain), `stale` (outside freshness SLA),
`internal_only` (tenant-scoped facts). Readiness-checklist API: per-domain state +
contradiction count + calibration completeness + internal-data flags.
**Frontend:** a Readiness panel on the dossier/summary stage — a domain × 6-state
grid (the Helix readiness checklist), each cell linking to its gaps/contradictions.
**DoD:** OQ5 supported; a stale/contradicted domain is visibly flagged.

---

## FS-4 — Epistemic timestamps + as-of view  *(Loop 2 / H-h / OQ6)*
**Capability:** fair hindsight — "what did we know as of date D?"

**Backend:** additive nullable `observed_at`, `detected_at`, `known_to_team_at` on
facts (distinct from `asserted_at`), `contradicts_fact_ids`; an as-of
reconstruction path + the **as-of regression gate** (Lane-1) from #226 Loop 2.
**Frontend:** an as-of date control on the engagement timeline that re-renders the
dossier/scenarios "as known then"; a "what we knew" badge.
**DoD:** OQ6 green; as-of query never leaks current truth into the past.

---

## FS-5 — D1 emitters  *(Loop 3; backend-only, frontend = richer dossier)*
RegulatoryMilestone / TrialOutcome / Investigator(KOL) / PublicationClaim /
CompanyFinancial emitters (per #226 §3 Loop 3). No new UI — they lift dossier
domains `gap/thin → covered`, which the existing dossier surfaces already render.

---

## Sequencing
**FS-1 → FS-2 → FS-3 → FS-4**, with FS-5 (emitters) interleavable any time (it's
independent). Each ships against the Helix Output-Quality Benchmark (#226 §5) with
a prod before/after probe per `conservation-gates.md` DoD. Payer/pricing (D2) stays
deferred pending the sourcing decision (#226 §2.2).
