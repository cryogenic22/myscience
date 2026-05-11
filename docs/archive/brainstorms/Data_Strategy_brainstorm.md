The dev team's critique is sharp and largely correct. Let me be direct about what they caught and where I stand.

**On the stale data points — they're right, and it's my fault.**

The document was compiled from the schema migrations and the audit agent's read of the codebase, but I failed to cross-reference against the Phase 0/1/2 work that the team had already reported to me in this very conversation. I knew company_id had been backfilled (the team reported 97.6% in the Phase 2 summary), I knew COMPETES_WITH had been implemented (commit 5f64a1a), I knew 170 drug names had been cleaned, and I knew the biomarkers table existed (migration 017). These corrections should have been in the document from the start. That's not a "different snapshot" — it's me not reconciling what I'd already been told with what the audit agents returned from an earlier read. The report needs a refresh pass, and the team is right to flag it.

Specifically, the corrected state should read: company_id at ~97.6% (not 35%), COMPETES_WITH implemented (not missing), 21 link types (not 15), drug name cleaning in progress with 170 cleaned and 36 excluded (not "includes dosing instructions" as a current blanket statement), and biomarkers have a dedicated table (not "stored only as links").

**On their strategic pushbacks — I agree with four of five.**

**1. "32 → 40 tables in 90 days is scope creep."** They're right. I said in Section 9.1 that the gaps are in data completeness not schema design, and then proceeded to recommend 8 new tables. That's contradictory. Their sequencing is better: get existing entities to >80% completeness first, then add Disease + Drug Target (the two that unlock the most new queries), then evaluate what's next based on actual user demand. Month 1 should be completeness, not expansion.

**2. "Competitor Group as a first-class entity is over-engineering."** Agreed. I over-specified this. COMPETES_WITH already exists as a link type, and `mv_competitive_landscape` already groups drugs by (TA + mechanism). A materialised view gives you the same query-time result without schema overhead. I should have checked the existing metrics service before recommending a new table. Remove this from the expansion plan.

**3. "Disease entity — right priority, underestimated difficulty."** This is the most important pushback. The UMLS licensing conflict is real and I should have flagged it. UMLS requires individual registration and prohibits redistribution, which directly blocks the CC BY 4.0 public release. The team's recommendation — use MeSH-only for now, skip UMLS — is the pragmatic answer. MeSH is weaker for cross-vocabulary mapping but it's fully open and covers the primary use case (mapping trial conditions to structured entities). UMLS CUI can be added later as an internal enrichment layer that gets stripped from public dumps.

The effort estimate is also too optimistic. Free-text condition normalisation is genuinely hard — "Type 2 Diabetes Mellitus," "T2DM," "Diabetes, Type II," "non-insulin-dependent diabetes" all need to resolve to one entity. This is an entity resolution problem, not just a schema problem, and it should go through the existing 6-strategy cascade. I'd revise from "1-2 weeks" to "3-4 weeks" including the normalisation work.

**4. "Public dataset release is premature."** Completely agree. I should not have recommended a Month 1 HuggingFace release. The bioinformatics community will absolutely benchmark it against PrimeKG and OpenTargets on Day 1, and the completeness gaps (even after the recent improvements) would dominate the conversation. The team's gating criteria are correct: drug completeness >75% across all key fields, disease entity live, drug target entity live. That's probably Month 3–4 at the earliest, not Month 1.

**5. "Pricing data needs an NDC mapping layer."** Their 4–6 week estimate is more realistic than my 2–3 weeks. The NDC → RxCUI → molecule mapping via RxNorm is a separate resolution pipeline, not a simple connector. And the `rxcui` field on the drugs table is currently unpopulated, which means the entire mapping chain needs to be built. I underestimated this.

**The one place I'd push back on them:**

The dev team says "sequence the UX polish first — it improves perceived quality immediately while the data work compounds over weeks." I'd modify this slightly. The three reliability fixes I recommended earlier (persist ConversationMemory, restrict CORS, add connection pooling) should come before UX polish and before data expansion. These are the items that cause actual failures under real usage. A visitor who gets a good-looking UI but loses their conversation on a server restart has a worse experience than one who sees rough edges but has reliable sessions.

So my revised sequencing would be:

**Now → Week 1:** Reliability fixes (ConversationMemory persistence, CORS, connection pooling) + EPC mechanism backfill + approval_date extraction from regulatory milestones.

**Weeks 2–3:** UX quick wins (Q1–Q8 from the UX report — hide Data Quality tab, filter junk entities from library, fix quality score colour encoding, collapse search duplicates). These are 1–2 day tasks each and they transform perceived quality.

**Weeks 3–5:** Disease entity (MeSH-based, no UMLS). Remaining drug dedup. Get drug completeness above 75% across mechanism_id, company_id, and approval_date.

**Weeks 6–8:** Drug Target via OpenTargets bulk download (not API — the team is right about rate limits). Structured trial endpoints.

**Week 9+:** Evaluate public release readiness against the gating criteria. Pricing data only if there's demonstrated user demand.

The team's analysis is solid. The document needs a correction pass on the six stale claims, the Competitor Group entity should be dropped, and the public release timeline should slide to Month 3–4. I'd update the report if you'd like — shall I?