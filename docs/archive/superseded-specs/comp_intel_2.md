# SPEC-015 Review — Critique, KBQ Deep Dives, Workflow & Intelligence Layer

**Status:** Independent review of SPEC-015 ("CI Agent: Backend Reuse & Frontend Strategy")
**Purpose:** Stress-test the recommendation, deepen the KBQ analysis, sharpen the intelligence layer, red-team the plan.

---

## 1. Verdict on the SPEC-015 recommendation

**Short answer:** the *direction* is right; the *sizing* is optimistic; two foundational decisions are under-examined and one is hand-waved. Approve the direction, but rework Phase 1 scope before sprint planning.

### What the spec gets right

- **Extend, don't rebuild.** The mapping in §2 is honest and granular. 70% entity reuse is a real number, not marketing — `market_events` extended in migration 026 with `source_tier`, `trust_score`, `event_hash`, `corroborating_sources` is genuinely the Event spine; `entity_links` with provenance is genuinely the document↔entity graph; `EntityResolver` with 6 strategies is a substantial existing asset. Reuse is the right call.
- **New frontend, side-by-side at `/ci`.** Correct. The analyst's day is *not* a chat-and-canvas day. A digest-watchlist-alert-brief surface has fundamentally different information density and interaction primitives than a Q&A surface. Trying to graft CI onto the existing chat UX would have produced a worse version of both products.
- **Signal as the first-class missing concept.** This is the most important call in the document. They've correctly identified that the existing platform has *evidence* and *insights* but not the deduplicated, dual-tier-scored, KBQ-tagged, supersedable unit that an analyst's workflow revolves around. Everything else flows from this.
- **8-K item-code parser as the highest single leverage.** Right. Items 1.01 (deals), 2.02 (financials), 5.02 (exec) collectively unlock three of the six MVP KBQs from one connector extension. This is the correct sequencing call.
- **Phase 1 KBQ cut (1, 2, 4, 5, 9, 10).** Identical to the design doc's MVP, justified independently by their bottom-up gap analysis. Convergence between top-down and bottom-up is a good sign.

### Where I push back

#### 1.1 The 14-week Phase 1 estimate is optimistic by 30–50%

The spec lists 14 backend items (B1–B14) plus 9 frontend surfaces, sized at "1 backend + 1 NLP part-time + 1 frontend + part-time design" over 14 weeks. Three things are systematically underweighted:

- **B2 (8-K item-code parser) at "M, 1.5 weeks" is the wrong size.** Item 1.01 has thousands of edge cases — deal type taxonomy alone (M&A vs asset purchase vs license-in vs collab vs option vs co-promote) requires either a hand-tuned classifier on real filings or a structured-output LLM with a tight schema and a validation pass. Item 5.02 has the easier structure but extracting *successor* (HR2.4 from the design doc) reliably requires entity resolution against the company's leadership page in the same window. Realistic: **3–4 weeks**, not 1.5.
- **B1 (Signals table + clustering + scoring + supersedence) at "M, 2 weeks" is the wrong size.** The clustering service alone is a research-grade problem if you want it to handle "press release on Tuesday + 8-K on Wednesday + trade press echo Thursday" as one event without merging two genuinely-distinct deals announced the same week. Plus supersedence semantics, plus YAML rule loading, plus the review-queue state machine wiring. Realistic: **4 weeks**.
- **Frontend at "8–10 weeks for 9 surfaces"** is a sprint-per-surface budget. Reasonable for a static prototype; insufficient for the *evidence stack* component, the *side-by-side conflict view*, the *per-sentence citation rendering* with inline source previews. Those three components alone are 2–3 weeks each if done well.

**Recommendation:** rebudget Phase 1 to **18–20 weeks**, or cut F4 (Brief Composer), F8 (Connector Health), F9 (Trackers) and F5 (Ad-hoc Q&A) from MVP. Ship F1, F2, F3, F6, F7 (digest, signal detail, watchlist, alerts, reviewer queue) first. That's the actual analyst workflow. Briefs and trackers are Phase 1.5.

#### 1.2 The "share the data plane" decision is under-examined

The spec assumes `/ci` and `/research` share a single Postgres + a single API layer. This is mostly right — but two issues are skipped:

- **Read-write contention on `market_events`.** The CI workflow writes events at high frequency (CT.gov diffs, SPL diffs, 8-K parses) and the existing `/research` surface reads them through materialized views. If the diff/event-emission code lands without index review, you'll see slow MV refreshes and slow research queries simultaneously. Mitigation: a write path through `signals` that does *not* invalidate the existing MVs, plus an index audit on `market_events` before B3/B4 ship.
- **Conflicting tier semantics.** The existing platform has `trust_score` as a float per source. The CI design has `confidence_tier` as an enum {confirmed, reported, inferred} per *signal* (derived from source class + KBQ rule). The spec proposes adding the enum (B6) but does not say what happens to `trust_score`. Two options: (a) deprecate `trust_score` and migrate consumers, or (b) keep both and document which surfaces use which. Option (b) creates technical debt; option (a) is a real migration. Pick one explicitly.

#### 1.3 Risk #4 (schema drift cleanup, SPEC-010) is hand-waved as "must land before B2"

This is correct but understated. SPEC-010 is referenced as a hard prerequisite in three places (Risk table row 4, Open Question 8, Phase 1 implicit ordering) yet has no scoping in this document. If SPEC-010 slips, every B-item that touches the data plane slips with it. Recommendation: add an explicit gate condition — "Phase 1 sprint planning cannot start until SPEC-010 closes" — and treat it as a tracked dependency, not a footnote.

#### 1.4 The "no Tier 3 in Phase 1" call is correct but the procurement parallel-track is asserted, not planned

Tier 3 vendors (Cortellis, AlphaSense, Bloomberg) are each 3–9 month procurement cycles in pharma — legal review, security review, data-handling addenda, redistribution clauses. If you genuinely want them live for Phase 2 (week 24), procurement starts *now*, in parallel with Phase 1 kickoff. The spec says "runs in parallel as a separate decision track" but assigns no owner and no timeline. This will silently block Phase 2.

#### 1.5 Reviewer SLA + reviewer staffing is a product question being deferred as an engineering question

Open Question 3 ("Reviewer SLA: CI doc default is 2 business hours for impact=high — confirm staffing implication") frames this as a confirmation. It is not. **2-business-hour SLA on impact=high signals, with a target of, say, 50 high-impact signals/week, is roughly 0.3–0.5 FTE of senior CI analyst time committed to the queue.** That is a hiring decision, not a config flag. If staffing is not committed, the system either ships unreviewed (breaks principle P5) or silently sits in queue (breaks the alerting workflow).

### What I'd add to the spec

- **A "Phase 0" of two weeks**: SPEC-010 closure + index audit on `market_events` + decision on `trust_score` vs `confidence_tier` + reviewer staffing decision + Tier 3 procurement kickoff. Without these, Phase 1 starts on sand.
- **A "definition of done" for a Signal.** Right now B1 is described in implementation terms (table, service, clustering). Better: define what a correct Signal looks like by example. Take three real events from the last quarter (a Pfizer 8-K + 3 news articles; an Amgen CT.gov status change + press release; a CHMP positive opinion + EMA page + trade press), hand-build the expected Signal cluster for each, and use them as acceptance tests for B1 + B2 + B3.
- **A confidence-tier downgrade rule.** The spec adds the enum (B6) but the design doc and SPEC-015 both treat tier as static-on-write. Real signals decay: a press release claim that is *not* corroborated by an SEC filing within 4 business days should drop from `confirmed` → `reported`. Add a tier review job.

---

## 2. KBQ deep dives — the six MVP questions, sharper

The design doc and SPEC-015 cover 11 KBQs at survey depth. For the six MVP-cut KBQs, here is the next layer of detail an engineering team will need on day one of build.

### KBQ 1 — Financial & Market Performance (deeper)

**The signal that actually matters to a CI analyst is not "Pfizer reported $14.9B Q3 revenue."** That's a number any Bloomberg subscriber sees in 30 seconds. The CI signal is one of:

- **Guidance change** vs. prior quarter (raise / lower / reaffirm) — the *delta* and the *direction*, not the absolute level.
- **Segment / product-level callout** that wasn't in the prior quarter (e.g., "we are no longer breaking out Vyndaqel separately").
- **R&D ratio shift** outside the company's historical band (R&D as % of revenue moving >2 points YoY).
- **GAAP vs non-GAAP reconciliation deltas** that change reported margin by >1 point.
- **Tone shift** in MD&A on a specific product (the qualitative companion to the number).

**Implementation implications the SPEC understates:**

- The 8-K Item 2.02 parser is *not* the same engineering work as the 10-Q XBRL ingest. 8-K Item 2.02 attaches the press release as Exhibit 99.1, sometimes with a tabular financial summary, sometimes as prose. Three quarters of the signal is in the prose and a quarter is in the table. Plan for both extraction paths.
- **Guidance diff requires a Guidance entity, not just a number.** A "Guidance" has: metric (revenue / EPS / R&D / margin), period (FY2026, Q4 2026), value (point estimate or range), basis (GAAP / non-GAAP), issued_at, superseded_by. Compare across issuances. Without this entity, you cannot produce the signal "Pfizer raised FY revenue guidance by ~3% on the Q3 call vs. the Q2 call."
- **Segment data is the hard part.** Pharma segment revenue isn't in XBRL with reliable granularity. The realistic MVP target is *company-level* guidance + *flagged-for-analyst* product-level mentions in transcripts, *not* automated product-level revenue. Set this expectation up front or you'll over-promise.

**Hard rule that needs explicit encoding:** the design doc's HR1.3 ("ignore analyst estimates from non-credible sources") is a *whitelist* rule. Implementation: a `permitted_estimate_sources` column on the rule registry, defaulting to AlphaSense, Bloomberg, Refinitiv only. Anything else gets dropped at the extraction stage, not just down-tiered at scoring.

**Failure mode the spec doesn't list:** *consensus drift bias.* If the news API picks up the Pfizer guidance via a Reuters wire, and Reuters' headline frames "raised guidance" but the actual Pfizer release frames "narrowed guidance to upper half of prior range," the signal direction can be inverted by source choice. Mitigation: always pull the SEC + company release as anchor; trade press is evidence, never anchor, for financial KBQs.

### KBQ 2 — Corporate Governance & Leadership Changes (deeper)

This KBQ is structurally easier than KBQ 1 (8-K Item 5.02 is more standardised than Item 2.02) but has a sharper false-positive trap.

**The hidden signal: pattern over event.** A single CFO departure is medium impact. Three departures from the same therapeutic-area leadership team in 90 days is high impact and predicts pipeline reprioritisation. The CI design doc soft-rule lists this; SPEC-015 does not have a primitive for it. **Add a `pattern_signal` event type** that fires when N events of (event_type=exec_change, company_id=X, functional_area in [...]) occur in a window. This is a Signal that has no single anchor document — it's a meta-signal.

**The successor problem (HR2.4) is harder than it looks.** A press release saying "CEO X is stepping down; the board has initiated a search" produces an exec_change event with no successor. Three months later a separate press release says "Y has been appointed CEO." These need to link as the same *transition*, not appear as two unrelated events. Implementation: a `transition_id` on exec_change events that aggregates linked exit + arrival + interim within a window per company per role.

**LinkedIn as confirmation-only is the right call but enforcement is weak.** SPEC-015 mentions LinkedIn as a Phase 2 source for IR diffs. The design doc says LinkedIn confirms but doesn't trigger. In practice, LinkedIn profile changes lead the official 8-K by days to weeks. The right rule is: LinkedIn change *creates a candidate signal at confidence tier=inferred*; the 8-K *promotes it to confirmed* and links the LinkedIn observation as supporting evidence. This requires the candidate signal to exist in the system pre-confirmation, which means the dedup service must handle the case where evidence arrives in the "wrong" order (low-tier first, high-tier later). The spec's clustering service (B1) needs an explicit promotion path, not just an anchor-selection at-cluster-time path.

**Title taxonomy is non-trivial.** "EVP and President, Specialty Care" is C-suite-equivalent at one company and SVP-equivalent at another. The design doc's seniority_tier enum (HR2.1) needs a *per-company* override table or you'll either over-flag (treating SVPs as C-suite at large pharmas) or under-flag (missing genuine business-unit heads at smaller cos). This is a data-curation task, not a code task — but it's a task. ~50 priority companies × 2 hours of curation each = ~2 weeks of someone's time.

### KBQ 4 — Clinical information (deeper)

The design doc and SPEC-015 both flag this as the highest-feasibility KBQ. They're right that the data is available. They under-discuss what makes it *signal-grade* rather than just *data*.

**The four types of clinical signal, by impact:**

1. **Negative readout.** Trial halted, primary endpoint missed, terminated for safety. Highest impact. Strongest predictor of stock movement and pipeline reshuffle. Detected via CT.gov status → "Terminated" or "Suspended" + linked press release.
2. **Positive readout with a twist.** Met primary endpoint but with a side note (sub-group analysis only, p just-under-0.05, safety signal in arm). These are the highest-value CI signals because they require *reading the press release closely* — automated pipelines often miss them.
3. **Status / phase transition.** Phase 2 → Phase 3 is a routine event but a meaningful one. Best handled as a structured event, not a narrative signal.
4. **New trial registration in a competitor's space.** Lowest per-event impact, highest aggregate value. The pattern of new trial starts in an indication is a leading indicator of a competitor's strategic commitment.

**The spec's B3 (trial diff service) handles type 3 well, types 1–2 poorly, type 4 not at all.**

For types 1–2, you need NLP on the *press release* announcing the readout, not just a CT.gov status flip. The press release contains the efficacy values, the p-values, the safety signal, the sub-group caveats. CT.gov contains "Status: Completed" and the structured outcome measures (which are often delayed by months). **Add an explicit press-release-as-readout extraction path** that fires when (a) a press release mentions an NCT ID and (b) the NCT is in a state where readout is plausible (Phase 2/3, primary completion within ±90 days).

For type 4, you need an *aggregation* signal: "Company X has registered 4 new Phase 1 trials in solid tumor immuno-oncology in the last 6 months." This is the same `pattern_signal` primitive proposed for KBQ 2.

**The acronym-to-NCT mapping problem is bigger than acknowledged.** Press releases say "KEYNOTE-189" not NCT02578680. The spec's CrossLinker has a rule for this; in practice the alias table needs to be seeded from a curated source (Citeline has it; ClinicalTrials.gov mostly does not in a structured field). MVP option: scrape `Other Study ID Numbers` field from CT.gov v2 API (it usually contains the acronym) and back-fill a `trial_acronyms` table. ~80% coverage at zero cost; the remaining 20% is the manual curation Citeline gives you in Phase 3.

**Endpoint-met-but-clinically-meaningless.** The design doc soft-rule "discrepancy between press release claim and CT.gov status = flag for analyst" is one form of this. The harder form: a press release says "statistically significant improvement in X" where X is a *secondary* endpoint and the *primary* endpoint failed. Detecting this requires: (a) knowing which endpoint is primary (CT.gov has it, structured), (b) extracting which endpoint the press release is celebrating (NLP, hard). Worth flagging this as a *Phase 2 enhancement* rather than expecting it in MVP. In MVP, the right behavior is to surface the press release claim *with* the CT.gov primary endpoint side-by-side and let the analyst spot the mismatch.

### KBQ 5 — Product information (deeper)

The strongest signal in this KBQ is the *label change*, and the SPEC's B4 (DailyMed SPL diff) is the right work. Two things underspecified:

**SPL diffs are noisy at the XML level and meaningful at the section level.** A trivial whitespace change in the XML produces a "diff." The MVP target is section-level semantic diff: which named SPL sections (Indications and Usage, Dosage and Administration, Warnings and Precautions, Boxed Warning, Adverse Reactions) changed, and what the substantive change was. The pipeline:

1. Parse SPL XML to canonical section-keyed structure.
2. Diff at section level (text similarity > threshold = "no semantic change").
3. For sections that changed, run an LLM extraction with a structured schema: change_type (new_indication, dose_change, new_warning, contraindication_added, etc.), affected_population (if any), source_section.
4. Emit `label_change` event with the structured change as payload.

Step 3 is the signal-grade work. Without it, you get "the label changed" with a 200-page diff dump and no analyst will use it.

**Label change → new indication is commercially equivalent to a new approval (design doc soft-rule).** True, and this is the highest-impact label change type. But there's a wrinkle: a *supplemental* indication approval (sNDA) shows up in *both* Drugs@FDA *and* DailyMed. If both pipelines emit events independently, you get two signals for the same real-world event. The dedup service has to handle this — anchor on Drugs@FDA application action, link DailyMed SPL diff as evidence of the label realisation.

**LOE computation is harder than "patent expiry from Orange Book."** Real LOE date = max(latest_relevant_patent_expiry + any PTE, latest_exclusivity_expiry, pediatric_exclusivity_extension). The Orange Book has all the inputs but the *computation* requires understanding which patents are relevant (some are formulation, some are MoA, some have been challenged). Generic-entry-blocking patent ≠ all listed patents. **For MVP**, ship "earliest expiry of any listed patent or exclusivity" as a *floor* date with a clear caveat in the UI. Phase 3 with Cortellis or IPD Analytics gives you the curated LOE.

**Discontinuation events (status change to discontinued/withdrawn) are missing from the event taxonomy.** Both the design doc and SPEC-015 include `regulatory_approval`, `regulatory_submission`, `regulatory_crl`, `safety_alert`, `loe_event` — but not "company has discontinued marketing of the product." This is detectable from FDA Discontinued Drug Product List and from SEC discontinuation announcements. Add `product_discontinuation` event type.

### KBQ 9 — Regulatory & Policy (deeper)

This KBQ has the most sources and the most heterogeneity. The MVP scope (FDA approvals + EMA partial) is tight, and that's correct. Two underweighted pieces:

**FDA designations are the leading indicator, not the lagging one.** A Breakthrough Therapy Designation precedes approval by 6–18 months, often correlates with priority review, and frequently moves stock. The design doc lists designations as Phase 1.5; SPEC-015 lists them as Phase 1.5 (B-item not assigned). For an MVP that ships in 14–20 weeks, designations *should* be in scope. The data path is partly structured (FDA Orphan Drug Designation database, FDA Rare Pediatric Disease list) and partly press-release-driven (Breakthrough, Fast Track — FDA does not maintain a public list, the announcements are made by the company). Build the press-release-driven path; it's the same NLP infrastructure you're building for KBQ 10. **Add to MVP.**

**The CRL detection problem.** Complete Response Letters are the FDA saying "no" or "not yet." The FDA does not announce them. The company does, in an 8-K Item 8.01 (Other Events) and a press release. The signal is high-impact and is *negative*. Engineering implication: the 8-K parser cannot stop at Items 1.01, 2.02, 5.02 — Item 8.01 has to be in scope, and within Item 8.01 the parser has to recognise CRL-shaped narratives. This is a small extension to B2 but it should be explicit, not implied.

**EMA CHMP opinion → EC approval lead time is ~2 months and reliable.** Design doc soft-rule. This is a high-value *forward-looking* signal: a positive CHMP opinion lets you predict EU approval ±1 week. Build a derived event type `predicted_approval` that fires on CHMP-positive with a date 60 days forward, and reconciles to the actual `regulatory_approval` event when it arrives. This is a Phase 1 polish item, not a Phase 2 item — it's almost free given the EMA scraper.

**Cross-jurisdiction sequencing.** A drug approved by FDA in March, EMA in July, PMDA in November is one product but three regulatory_approval events. The CI signal is the *global rollout pattern*. Add a `regulatory_rollout` rolled-up signal that aggregates per-product. Same `pattern_signal` primitive again.

### KBQ 10 — M&A and Partnerships (deeper)

Highest-leverage from 8-K Item 1.01 + press release matching. Five things to nail:

**Deal type taxonomy.** A "deal" is not one shape. The team should agree on enum values up front:

- `acquisition` (full M&A)
- `asset_purchase` (single asset bought, often a marketed drug or pipeline asset)
- `license_in` (acquirer licenses rights from licensor)
- `license_out` (licensor grants rights)
- `collaboration` (joint R&D, no exclusive rights transfer)
- `option_to_license` (right to license later, often with exclusivity period)
- `co_promotion` (commercial only, no rights transfer)
- `co_development` (joint development, often with cost share)
- `royalty_monetisation` (royalty stream sale to financial buyer)

These overlap (a deal can be license-in + co-development + option) so the data model needs `deal_types[]` not a single enum.

**The financial-terms extraction problem.** Press releases use an enormous variety of phrasings: "$50M upfront, up to $500M in milestones, plus tiered royalties on net sales," "an upfront payment of $X, regulatory milestones up to $Y, commercial milestones up to $Z, plus royalties," "an undisclosed upfront and milestone-based payments potentially worth more than $1B." LLM with structured output is the right tool. The schema:

```
DealTerms {
  upfront_value_usd: number | null
  upfront_disclosed: bool
  milestones_total_potential_usd: number | null
  milestones_breakdown: [{ type: regulatory|commercial|development, max_value: number }]
  royalty_terms: { tier_count: int, range_low_pct: number, range_high_pct: number } | null | undisclosed
  equity_component: bool
  notes: string
}
```

Validate post-extraction by sanity rule: if upfront + max_milestones < headline "total deal value" mentioned, flag. If royalty range exceeds [0, 30], flag. These catch most LLM extraction errors.

**Undisclosed terms ≠ small deal (design doc soft-rule).** Encode this as a UI rule, not just a soft heuristic. When `upfront_disclosed = false`, the UI must show "Terms undisclosed" prominently — never imply a small deal by absence of a number.

**Acquirer-target side-of-deal direction matters.** Many press releases are co-issued. "Pfizer and Trillium announce" — same press release, but Pfizer is acquiring. The data model needs `acquirer_company_id` and `target_company_id` (or `licensee_id` / `licensor_id`) as separate fields, not just `parties[]`. Otherwise the analyst's question "what did Pfizer acquire this quarter" is an unanswerable graph query.

**Termination events.** Deals can be terminated. A licensee can return rights ("Pfizer terminates collaboration with X, returns all rights"). This is its own high-impact event type — currently missing from the design doc taxonomy. Add `deal_termination` with link to the original deal.

---

## 3. CI persona workflow — what the analyst's day actually looks like

Both documents describe workflows abstractly (Workflow A through E). Here is the same content from the inside, hour by hour, with the system primitives each step needs.

### 3.1 The morning analyst — Workflow A in detail

**07:30 — pre-market check.** Analyst opens the digest on their phone. The digest must:

- Be ≤30 seconds to triage at the headline level. **UI implication:** signal cards show entity + event type + impact tier + a 1-line summary, in that order. Headlines, not paragraphs.
- Be sorted by impact, *not* by time. A medium-impact signal from 06:00 should not push down a high-impact signal from 22:00 the prior evening.
- Show provenance immediately. **UI implication:** every card has a confidence tier badge (confirmed/reported/inferred) and a source-class indicator (FDA / SEC / press / news). Without this, the analyst doesn't know what's worth reading.
- Distinguish between *new* signals and *updates to prior signals* (supersedence). **UI implication:** a "this updates a signal from [date]" indicator on cards that are supersedences, not parallel feeds.

**System primitives required:** Signal table with `impact_tier`, `confidence_tier`, `superseded_by_signal_id`, `created_at`. Watchlist filter on entity_id. The spec covers all of these.

**System primitives missing:** A "digest snapshot" object that captures *what was shown* to *which user* at *what time*. Without this, the analyst cannot answer "did I see X this morning?" and the system cannot do session-aware deduplication ("don't show me a signal I already saw and dismissed yesterday"). **Add `digest_views` table.**

**08:30 — desk arrival, deep triage.** Analyst opens the laptop, goes through the digest in detail. For each signal:

- 80% are read-and-move-on.
- 15% are tagged for follow-up (will revisit later in the day).
- 4% are immediately escalated (ping a senior analyst, Slack a brand team).
- 1% trigger a deep-dive (Workflow B).

**System primitives required:** Tagging on signals (per-user labels). Quick-action buttons on signal cards (escalate, follow-up, dismiss-as-noise, promote-to-brief). A "follow-up queue" view that surfaces tagged signals later.

**Design implication SPEC-015 understates:** F1 (Daily Digest) is not just a list. It's a triage interface with strong keyboard shortcuts (j/k navigation, e to escalate, f to flag, x to dismiss, return to deep-dive). Analysts who use this 5 days/week will not tolerate a click-to-everywhere UX. **Plan keyboard navigation as a first-class concern, not a polish item.**

**10:00 — deep-dive on a chosen signal.** Workflow B. The analyst clicks into a signal that matters and wants to:

1. See the full evidence stack — every source document supporting this signal, ordered by confidence tier, with an expandable preview.
2. See the *historical context* — what has this entity done previously? For an exec change: prior leadership at this company for the last 5 years. For a guidance change: the last 8 quarters of guidance vs. actuals. For a trial status change: this trial's status history and related trials in the same indication.
3. See the *peer context* — what are competitors doing in this space? For an approval, competitor approvals in the same indication; for a deal, recent deals in the same therapeutic area; for an exec change, recent exec changes at peer companies.
4. Ask a free-form question — "what does this mean for [adjacent product]?" — and get a sourced answer.

**System primitives required:**

- Evidence stack rendering (B1 + frontend F2). Spec covers this.
- *Entity-keyed historical querying.* This requires materialised event-history-per-entity, not on-demand SQL. Otherwise the page takes 5+ seconds to render. Add a `entity_event_history` materialised view, refreshed nightly, indexed on (entity_id, event_type, event_date).
- *Peer-context retrieval.* This requires the indication / therapeutic-area edges that the spec mentions are partial (`therapeutic_areas` looser than CI's `Indication`). The realistic Phase 1 path: join via TA, accept lower precision than indication-level joining would give, document the limitation, plan the indication entity layer for Phase 2.
- *Conversational query routing.* The spec says reuse existing chat infra. This is right but understated — the chat needs to be *Signal-aware*, returning answers cited to Signals not raw documents. That's a non-trivial prompt and retrieval change.

**11:30 — composing a brief.** Analyst gets a request from a brand team: "give us a 2-page brief on [competitor] in [indication] for the last quarter." The analyst:

1. Opens the brief composer.
2. Picks company, date range, KBQs to include.
3. Reviews the auto-generated draft.
4. Edits headline and exec summary; tweaks 2–3 sections.
5. Submits to reviewer queue.
6. After review, exports to DOCX.

**SPEC-015 ships brief composer (B10 + F4) in MVP.** I'd defer F4 to Phase 1.5. Reason: the brief composer is high-leverage *only after* the signal pipeline is producing high-quality signals. Shipping it in week 14 against signals that are still being tuned will produce briefs that need heavy manual rework, which kills analyst trust in the auto-generated output. Better to ship F1+F2 to a small group of analysts at week 8, iterate signal quality for 4–6 weeks, then turn on F4. Same total time, much better quality at launch.

**14:00 — alert handling.** A high-impact alert fires (a competitor's CRL, say). The analyst:

1. Sees the Slack/email push.
2. Opens it; the link goes directly to the Signal Detail (F2), not to the digest.
3. Reviews; if confirmed accurate, sends a 1-line summary to the brand team via the system's "share" action (which generates a tracked outbound, not a copy-paste).
4. If it's a candidate signal awaiting review, the analyst is in fact the reviewer — approves or edits.

**System primitives required:**

- Reviewer-queue + alert engine wired together. SPEC-015's Risk #5 ("watchlist + alert blast radius") and B9 (reviewer queue) cover this.
- Tracked share-out action. Missing from the spec. Without it, you can't measure which signals drove which downstream conversations, and you can't iterate. **Add a `signal_shares` table and a "share" action on Signal Detail.**

### 3.2 Roles other than the morning analyst

The spec implicitly designs for one persona (the daily-digest CI analyst). At least three others exist:

**The senior CI lead.** Runs Workflow C (quarterly briefings), reviews escalations, owns watchlist taxonomy, tunes impact rules. Different surface needs: an "impact rule editor" UI for the YAML registry, a "trending themes" dashboard across the entire signal store, a "team queue" view of what their analysts are working on.

**The brand-team consumer.** Doesn't log into the CI surface daily but wants the brief output and the alert push. Different surface needs: an embeddable digest widget, a "subscribe to this product/indication" flow, no analyst-side controls.

**The reviewer / approver.** May overlap with the CI lead. Needs the F7 reviewer queue with side-by-side evidence view, fast approve/reject/edit, and a clear audit trail of decisions. Spec covers F7.

**Design implication:** F3 (Watchlist Manager) is not one feature, it's three — the analyst's personal watchlist, the team's shared watchlist, and the brand-team's subscription. Don't build them as one CRUD screen. Plan for the role split early.

---

## 4. Sharpening the intelligence layer

This is where the design has the most upside. The spec describes the intelligence layer pipeline (Extraction → Resolution → Linking → Dedup → Scoring/Synthesis) as adequate. It can be much sharper.

### 4.1 The dedup/clustering service is the heart and the spec under-specs it

The proposed clustering — group facts by (event_type, primary_entity, event_date ± window), pick anchor by confidence tier — is correct as a starting point but will produce visible errors at scale. Sharper specification:

**Tiered windowing per event type.** A single global "±window" is wrong. Define explicitly:

| Event type | Window | Rationale |
|---|---|---|
| `regulatory_approval` | ±2 days | FDA action date is precise; press release within 24h |
| `regulatory_crl` | ±7 days | Company discloses within 4 business days, news echoes |
| `deal_announced` | ±3 days | Co-issued press releases sometimes lag by a day |
| `exec_change` | ±14 days | LinkedIn → company page → 8-K can span 2 weeks |
| `trial_status_change` | ±30 days | CT.gov updates lag readouts by weeks |
| `trial_results_posted` | ±60 days | Press release → CT.gov results posting lag |
| `guidance_change` | ±2 days | Earnings call same-day as 8-K Item 2.02 |
| `label_change` | ±14 days | Approval action precedes SPL publication |
| `safety_alert` | ±1 day | Real-time |

**Clustering features beyond entity + date.** Two events at the same company on the same day are not always the same event. Add features:

- Indication / product overlap (if both events name a product, do they name the *same* product?).
- Person overlap (for exec changes, same person?).
- Trial overlap (for clinical signals, same NCT?).
- Document text similarity (Jaccard on entities mentioned, or embedding similarity above threshold).

Cluster only if window AND ≥1 of the secondary features match. This eliminates the "two distinct deals announced on the same day get merged" failure I flagged in §1.

**Anchor selection beyond confidence tier.** When two confirmed-tier sources disagree on a fact, *do not auto-select.* The design doc says this; the SPEC echoes it; but the implementation needs a concrete rule: if the cluster has ≥2 confirmed-tier sources and any structured field (date, value, party) disagrees beyond tolerance, set `cluster.status = 'conflict'` and route to reviewer queue. The reviewer picks the anchor.

**Promotion path for late-arriving high-tier evidence.** When a candidate signal exists at confidence=inferred (LinkedIn-only exec change) and an 8-K arrives 5 days later, the system must:

1. Find the existing cluster by entity + event_type + window.
2. Add the 8-K as evidence.
3. Promote `confidence_tier` from inferred → confirmed.
4. Update the anchor document.
5. Re-score impact.
6. Emit a `signal_updated` event so subscribers can be notified.
7. Mark the prior version with `superseded_by`.

The spec's B1 description does not enumerate steps 5–7. Make them explicit; otherwise alert subscribers will see two events instead of one update.

### 4.2 The KBQ rule engine needs versioning, not just hot-reload

SPEC-015 B5 says "YAML-defined ignore/confirm rules per HR1.1, HR1.2, HR2.1…" with hot-reload. This is necessary but not sufficient. Three things to add:

- **Rule versioning.** When a rule changes, the signals already produced under the old rule should not silently change interpretation. Version each rule; tag each signal with the rule version that produced it; on rule change, optionally re-evaluate historical signals and emit supersedences.
- **Rule provenance to the user.** When a signal is suppressed by a rule (e.g., an analyst estimate dropped under HR1.3), the analyst should be able to ask "why didn't I see X?" and get an answer. Suppressed candidates should be persisted, not discarded — at minimum logged with rule_id and signal_candidate.
- **Rule conflict detection.** When two rules apply to the same signal candidate and disagree, log it. Don't silently apply the first-matching one.

### 4.3 Confidence tier should be derived, not assigned

The spec's B6 is "confidence tier enum + derivation lookup." The design doc's §5.4 has a static lookup (SEC = confirmed, press release = confirmed for company-attributable, trade press = reported, LinkedIn/X = inferred, Tier 3 = confirmed for facts).

Three improvements:

**Fact-type-aware tier derivation.** A press release is `confirmed` for *what the company said* but `reported` for *forward-looking claims about market impact* and `inferred` for *competitive comparisons the company makes*. The tier depends on what the fact *is*, not just where it came from. Encode this with a (source_class, fact_type) → tier matrix.

**Corroboration as a tier modifier.** A `reported` claim corroborated by ≥2 independent reported sources rises to `corroborated` (or to `confirmed` per a rule). A `confirmed` claim that contradicts another `confirmed` claim drops to `disputed`. Tier is a function of the cluster, not just the source.

**Time-decay.** A `confirmed`-from-press-release claim that is *not* confirmed by an SEC filing within 4 business days (where one would be expected, e.g., a material agreement) should drop to `reported`. This is the explicit decay rule I mentioned in §1.5.

### 4.4 Synthesis with per-sentence citations is the right bar but needs more discipline

SPEC-015 says "per-sentence citation discipline" is a gap (§2.5). Three concrete asks:

- **Schema-locked LLM output.** Synthesis prompt outputs JSON with `[{sentence: "...", citations: ["doc_id_1", "signal_id_2"]}]`. Reject and retry if any sentence has zero citations or if citations don't resolve. Don't try to extract citations post-hoc from free text.
- **Citation must be supportive, not just topical.** A document that mentions Pfizer is not a valid citation for a sentence about Pfizer's guidance unless it discusses guidance. The spec mentions `validate_citations` exists; extend it to do *semantic* citation validation, not just presence-of-document validation. LLM-as-judge on (sentence, cited_text) pairs.
- **Hedging language tied to confidence tier.** Confirmed-tier facts use direct language ("Pfizer raised guidance"). Reported-tier facts use attributed language ("BioPharma Dive reports that Pfizer raised guidance"). Inferred-tier facts use hedged language ("LinkedIn observations suggest…"). This rule should be in the synthesis prompt as a hard constraint and validated post-hoc.

### 4.5 Two missing primitives the spec doesn't have

**Signal lineage.** Beyond `superseded_by`, capture *why* one signal supersedes another (new evidence, corrected fact, retraction, escalation, downgrade). Add `supersedence_reason`. Without this, an analyst who sees "Signal A superseded by Signal B" can't tell if it's a correction or a development.

**Negative signals.** The system as designed surfaces things that *happened*. Sometimes the signal is something that *didn't happen*: an expected PDUFA date passed without action, a CHMP opinion was scheduled but deferred, a trial's primary completion date slipped. These are inferred from the *absence* of an event by a date. Add a periodic job that fires `expected_event_missed` signals based on calendar projections (PDUFA dates, primary completion dates, CHMP meeting agendas). Lower-volume but highly-watched.

---

## 5. Red-team assessment

Things that worry me about this plan that are not adequately addressed in either document.

### R1 — Provenance integrity is asserted at write time but not at read time

Both documents commit to "every Signal cites ≥1 Document; every assertion in a brief cites ≥1 Signal" (CI design P1; SPEC-015 risks table). Write-time enforcement (NOT NULL + array length ≥ 1) catches the trivial case. It does not catch:

- A document was deleted/expired but signals still cite it.
- An LLM synthesis added a sentence that *says* it cites Signal X but the citation is wrong.
- A signal evidence list contains a document that has been retracted by its publisher.

**Add:** a periodic provenance audit job that walks all signals, resolves all evidence document IDs, and reports orphans / retractions / broken citations. Treat unresolved provenance as a signal-level integrity violation that pulls the signal from active digests until reviewed.

### R2 — The "two products on one data plane" decision will hurt twice

`/research` (existing chat+canvas) and `/ci` (new) share Postgres + entity layer + market_events. SPEC-015 §7 covers this as architectural. What it doesn't cover:

- **Read patterns are different.** `/research` does narrow deep reads (one entity, deep traversal). `/ci` does broad shallow reads (watchlist of 100 entities, last 24h, every event type). Same indices won't serve both well.
- **Write contention as discussed in §1.2.**
- **Schema evolution friction.** A field added for CI (e.g., `signal_id` on impact_assessments) requires the research surface team to know about it or risk breaking views.

**Mitigation:** designate a single team owner of the shared data plane (DBA-equivalent role), with both product surfaces as consumers. Schema changes go through that owner. Don't let two teams own one schema by committee.

### R3 — Phase 2's connector expansion is sized as "10 weeks" but contains the system's hardest engineering

Per-company IR scrapers (50–100 of them), payer formulary PDF diff, conference abstract scraping, transcript ingestion (Tier 2/3 path) — each of these alone is a multi-week problem. Bundling them into "10 weeks" is unrealistic.

**Reframe:** Phase 2 is not "10 weeks." It's a long tail of connector work that runs continuously after Phase 1 ships. Each connector is a sub-project with its own Phase 1/2/3. The Phase 2 *deliverable* should be "shipped 3 of these high-value connectors with quality" not "shipped all of them at undefined quality."

### R4 — The agent architecture is described but its failure modes aren't

10 specialist agents + orchestrator is the proposed agent shape. What happens when:

- An agent fails partway through extraction? Are partial extractions persisted or discarded?
- The orchestrator picks the wrong agent for a query (KBQ misclassification)?
- Two agents emit signals for the same event from different angles (Clinical Trials and Regulatory both extracting from the same press release)?
- An agent's tool call rate-limits a downstream API? Does it back off, retry, fail loudly?

**Add an agent-execution audit trail.** Per agent invocation: which prompt version, which tools called, which signals emitted, which entities resolved, total tokens, total wall-clock. Surface in admin UI. Without this, debugging "why did the agent miss this signal" is forensic archaeology.

### R5 — LLM cost and rate are unbudgeted

The spec mentions cost controls (LLM metered per agent, budget caps per workflow, cheap models for triage, premium for synthesis). The design doc says the same. Neither has actual numbers. At 50k documents/day NFR target, with extraction LLM calls on say 30% of docs, that's 15k LLM calls/day on extraction alone. Plus synthesis calls per signal, plus reviewer-assist calls, plus ad-hoc Q&A.

**Build a cost model before kickoff.** Estimated docs/day × extraction LLM calls × tokens × price = monthly LLM bill. If the answer is 6 figures, that's a budget conversation with finance, not a footnote.

### R6 — Adversarial inputs aren't considered

CI sources are mostly low-adversarial (FDA, SEC, peer-reviewed). But:

- **Press releases are marketing.** They overstate positive findings, bury negative ones, use weasel words ("we believe," "potentially first-in-class"). Extraction must be skeptical of evaluative claims, not just of factual ones.
- **Trade press has agendas.** Some outlets are pay-to-play for company coverage. Some have institutional bias toward certain companies. Track outlet-level bias in the source registry.
- **Social media (deferred to Phase 2/3) is an injection surface.** Anyone can tweet anything. If the system ingests social signals, it is an attack vector. Defer this until you have a clear story for adversarial robustness.

### R7 — The evaluation story is missing

How do we know the system is good?

- For Signals: precision (false positive rate — signals that aren't real events), recall (false negative rate — events the system missed), latency (event-to-signal time), dedup correctness (events split across multiple signals or merged across distinct events).
- For briefs: factual accuracy, citation correctness, analyst editing rate.
- For agents: tool-call success rate, end-to-end task completion rate.

**Build a labeled evaluation set before MVP launch.** 50 historical events, hand-labeled with expected signal output, expected evidence stack, expected impact tier. Run weekly against the production pipeline. Without this, you cannot tell whether a change improves or regresses the system.

### R8 — Compliance and licensing are mentioned but not specified

Tier 3 vendor data (Cortellis, AlphaSense, Bloomberg) often has redistribution restrictions. The spec says "licensed-source content is access-controlled and never redistributed in raw form. Output flagging if a brief includes Tier 3-derived content." This is a starting point. Real questions:

- Can a brief that *paraphrases* a Tier 3 fact be shared externally (with brand team, with client)?
- Can a Signal whose anchor is Tier 3 be alerted on?
- Can the system display Tier 3-sourced data to a user who is not licensed for that vendor (because someone else in the org is)?

These are *legal* questions, not engineering ones. They need to be answered in writing before Phase 3 starts, ideally before Tier 3 procurement.

### R9 — There's no plan for graceful degradation

What does the digest look like the morning a connector is broken? Right now: probably an empty section with no indication that data is stale. Worse: a digest that *seems* current but isn't.

**Add freshness assertions to the digest UI.** Every section shows "last updated: X" per source class. Sections older than N days display a warning. The connector health dashboard (F8) covers admin needs; the analyst-facing freshness signal covers user needs. They're different.

### R10 — The "signals supersede" semantics need a UI affordance not just a DB column

When a signal is superseded, the digest behavior is unclear. Options:

- Suppress the old signal entirely (analyst loses awareness of the prior state).
- Show both, marked.
- Show only the new one but link to the old.

Different choices for different events. A guidance change supersedes the prior guidance — old goes away. A trial status change *does not* supersede the prior status — both are part of the trial's history. The data model should distinguish *correction* from *progression*, and the UI should render them differently.

---

## 6. Bottom line

The SPEC-015 plan is **structurally right and tactically optimistic**. Approve the direction. Before sprint planning:

1. Lock the four answers SPEC-015 itself asks for (priority companies, TAs, /research surface fate, SPEC-010 sequencing).
2. Add the four answers I'm flagging on top: reviewer staffing decision, Tier 3 procurement owner, `trust_score` vs `confidence_tier` migration plan, evaluation set construction.
3. Rebudget Phase 1 to 18–20 weeks, or cut F4/F8/F9/F5 from MVP and ship F1+F2+F3+F6+F7 (the actual analyst's day) at week 14.
4. Land Phase 0 (SPEC-010 closure, index audit, reviewer staffing) as a hard prerequisite, two weeks, before Phase 1 sprint 1.

The single highest-leverage technical bet remains the 8-K item-code parser, properly sized at 3–4 weeks. The single highest-leverage product bet is keyboard-first signal triage in the Daily Digest. The single highest-leverage organisational bet is committing reviewer staffing alongside the engineering plan.

If those three bets land, the rest follows.