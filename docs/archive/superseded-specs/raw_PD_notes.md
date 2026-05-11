This is the most strategically important spec in the entire codebase. Let me give you the balanced view — what's strong, what's still AI-assisted rather than AI-led, and what the team should understand about the gap between the two.

---

**What this spec gets right**

The sense → model → decide → act → learn framework is the correct abstraction. Most CI platforms — and most "AI" products in pharma — stop at sense. They detect signals and present them. SPEC-021's insight is that the signal isn't the value; the decision made from it is. And the learning from that decision's outcome is what compounds value over time. The spec articulates this clearly and the phased build is pragmatic.

The grounding invariant is well-designed. The reaction engine builds competitor dossiers from real DB entities (drugs they own, trials they sponsor, recent events) and constrains the LLM to cite real assets. "If no asset enables the reaction → `hold_position`" is exactly the right constraint. This prevents the LLM from inventing plausible-sounding but fabricated competitive responses, which would be worse than useless in a strategic planning context.

The schema design is clean. War rooms, rounds, and reactions form a natural hierarchy. The `source_signal_id` foreign key connects simulations to the signals that triggered them, creating the traceability that Phase D needs. The 8 move types and 8 reaction types are a thoughtful enumeration of the pharma competitive action space. The 5 scoring dimensions (market share delta, time to execute, capex, regulatory risk, payer acceptance) are the right ones for a pharma strategy audience.

Phase D is correctly identified as the differentiator. The spec says "most pharma CI vendors ship Phase A and call it AI" — that's accurate. The outcome capture → prediction error → signal weight recalibration loop is genuine machine learning applied to competitive strategy. If you get there, it's a defensible capability.

---

**Where it sits on the AI-assisted vs AI-led spectrum**

Here's the honest assessment, phase by phase:

**Phase A (Simulation) — AI-assisted.** The human picks the competitive move. The human chooses which entity to simulate. The human interprets the reactions. The LLM's role is generating plausible competitor responses from structured prompts — it's a sophisticated text generator constrained by entity dossiers, not a reasoning agent. This is AI augmenting a human analyst's workflow. There's nothing wrong with that, but it should be called what it is.

**Phase B (Catalog) — No AI at all.** CRUD operations for listing and sharing war rooms. Pure application code.

**Phase C (Decision Ledger) — AI-assisted.** The human makes the decision, records the expected outcome, assigns an owner. The system stores it. The AI's contribution was in Phase A (generating reactions that informed the decision). This is record-keeping with AI-generated context, not AI-driven decision-making.

**Phase D (Outcome Capture + Flywheel) — AI-informed, approaching AI-led.** This is the most interesting phase. The system compares actual outcomes against simulated predictions and adjusts signal scoring weights. This is a learning loop. But as specified, it's a batch recalibration ("quarterly recalibration job") applied to signal weights, not a real-time adaptive system. The human still records the outcome manually. The system doesn't detect that the outcome occurred — it doesn't watch for the trial failure or the competitor launch and automatically capture the result.

**The follow-ups hint at AI-led but aren't specified.** Monte Carlo over 100 reaction draws, replay history mode, probabilistic scoring — these would move towards genuine AI-led analysis. But they're explicitly marked "not in any phase yet."

---

**What would make this truly AI-led**

There's a clear line between "AI assists humans in making decisions" and "AI leads the decision process with humans providing oversight." Here's where the spec currently stops short and what crossing that line would look like:

**The system should generate hypotheses, not just react to human-selected moves.** Today: a human sees a signal, clicks "Simulate", picks a move type, and the LLM generates reactions. AI-led: the system detects a signal, autonomously generates 2-3 plausible competitive moves the player could make, simulates reactions for each, scores them, and presents a ranked recommendation. The human's role shifts from "tell the system what to simulate" to "review and approve the system's recommendation."

This isn't a large architectural change. The war game engine already generates reactions. Generating moves is the same pattern in reverse — build a dossier of the player's assets, construct a prompt asking "given this signal, what are the 3 most impactful competitive responses available to this company?", constrain to the 8 move types, score each. The spec's own `MoveSelector` component pre-suggests a move type based on the signal's KBQ tag. Expand that from a heuristic suggestion to an LLM-reasoned recommendation with rationale.

**The system should play multiple rounds ahead.** The current spec is single-round: player makes a move, competitors react, done. Real competitive dynamics are multi-round: you launch a new indication, competitor X cuts price, you respond with a patient access programme, competitor Y accelerates their trial. The scenario engine should support multi-round simulation where the AI plays both sides forward, identifying stable equilibria and unstable dynamics. This is where the "war game" metaphor becomes genuinely apt — it's game theory, not just reaction prediction.

**Outcome capture should be automated, not manual.** Phase D requires the decision owner to manually record the actual outcome at the target date. AI-led: the system monitors the relevant entities (via existing connectors and the DataSteward signal loop) and detects when outcomes occur — trial status changes, FDA actions, competitor launches, market share shifts. It alerts the decision owner: "The decision you committed 60 days ago predicted Competitor X would hold_position. Our data shows they actually accelerated their Phase 3 trial (NCT09876543, status changed to RECRUITING on 15 April). Would you like to record this as the actual outcome?"

This connects the war room directly to the existing signal infrastructure. A signal that matches a decision's expected outcome triggers the post-mortem flow automatically. The flywheel closes without waiting for a human to remember to record results.

**Signal weight adjustment should be continuous, not quarterly.** The spec says "quarterly recalibration job." AI-led: every outcome capture immediately adjusts the relevant signal weights in real time. The system maintains a running accuracy score per signal category and surfaces its own confidence trends: "Clinical trial signals have predicted competitor reactions correctly 73% of the time over the last 6 months. M&A signals are at 41% — consider reducing their weight in decision prioritisation."

---

**The balanced view for the dev team**

Here's what I'd tell the team:

Build Phase A as specified. It's well-designed, pragmatic, and the 3-4 hour estimate is realistic given the existing infrastructure. The grounding invariant is the most important design decision in the spec — protect it. Every reaction must cite real DB entities. No fabrication, no plausible-sounding fictional competitors. This is what separates a useful simulation from a creative writing exercise.

Build Phase D properly or don't build it at all. The flywheel only works if the outcome data actually feeds back into signal weights and the system demonstrably gets better over time. A decision ledger without outcome-driven recalibration is just a spreadsheet with extra steps. If Phase D gets deprioritised or descoped, the entire spec loses its strategic justification.

Be honest about what's AI-assisted vs AI-led. In client-facing positioning, call Phase A what it is: "AI-powered competitive simulation grounded in real market data." Don't call it "AI-led decision-making" until the system is autonomously generating hypotheses, recommending actions, and self-correcting from outcomes. Overpromising on the AI-led dimension and underdelivering is worse than accurately positioning a strong AI-assisted capability.

The path from AI-assisted to AI-led is incremental, not architectural. The infrastructure in this spec supports the upgrade. War rooms already have structured moves, reactions, and scores. Adding autonomous move generation is a new prompt, not a new system. Adding multi-round simulation is a loop around the existing single-round engine. Adding automated outcome detection is wiring the DataSteward signals to the decision ledger. The architecture doesn't need to change — the autonomy level needs to increase at each phase.

The real test of "AI-led" is this: can a strategy team set up Market Zero at the start of a quarter, define their competitive scope, and at the end of the quarter receive a report that says "here are the 12 competitive moves that occurred, here's how they compared to our simulated predictions, here's how we've adjusted our models, and here are the 3 decisions you should consider for next quarter" — without anyone manually triggering simulations or recording outcomes in between? That's the vision. SPEC-021 Phase A is a credible first step towards it, but be clear-eyed that it's step one of five.

---

**Three specific things to strengthen in the spec before building:**

First, add a "confidence calibration" column to the reaction schema. Right now `confidence` is a categorical label (high/medium/low). Change it to a numeric score (0.0–1.0) with the categorical label derived from thresholds. This makes Phase D's prediction error computation mathematical rather than categorical, which is essential for meaningful weight adjustment.

Second, specify the grounding validation in the reaction engine explicitly. The spec says "reaction must cite real assets (NCT/PMID/drug_id)" but doesn't describe what happens when the LLM hallucinates an NCT ID. Add a post-generation validation step: for each cited asset, verify it exists in the DB. If it doesn't, strip the citation and downgrade confidence. This is the same numeric grounding pattern from the remediation spec, applied to simulation output.

Third, add coverage awareness to the dossier construction. When building a competitor's dossier for reaction generation, include a coverage statement: "We have data on 3 of this company's estimated 12 drugs and 4 of their approximately 25 active trials." This prevents the LLM from generating reactions based on an incomplete picture and helps the strategy team calibrate their trust in the simulation.