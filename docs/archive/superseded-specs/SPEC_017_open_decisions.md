# SPEC-017 — Open Decisions Before Phase 1 Sprint Planning

**Status:** Decision record — to be filled in by stakeholder review
**Inputs:** SPEC-016 §13, comp_intel_2.md §1
**Decision deadline:** End of Phase 0 (week 3) — block Phase 1 sprint planning until all eight are resolved

This document records the eight decisions that Phase 0 work can proceed without, but Phase 1 sprint planning cannot start without. Each decision has:

- **Options** considered
- **Tradeoffs** of each
- **My recommendation** with reasoning
- **Decision** — empty until reviewed
- **Owner** — who signs off
- **Implications** — what changes downstream once decided

---

## D1 — Module names (platform brand is locked to PulseAction.AI)

### Status — Resolved at platform level
**Platform brand: PulseAction.AI** (decided 2026-04-28). The remaining sub-question is just whether modules use a descriptive `PulseAction · {Module}` form or carry distinct product-name brands.

### Sub-question
Do modules carry the `PulseAction · {Module}` form (e.g., *PulseAction · CI*, *PulseAction · Research*), or do they get distinct product-name brands (e.g., *Pulse* for CI, *Atlas* for Research)?

### Options

| Option | Pros | Cons |
|---|---|---|
| **A. `PulseAction · {Module}`** (descriptive) | Reinforces platform brand; new modules slot in trivially; no per-module marketing work | Reads as a label rather than a product; may flatten differentiation |
| **B. Distinct product names** (e.g., *Pulse*, *Atlas*) | Memorable, distinct, supports per-module marketing; "Pulse" as CI reuses the platform's audio identity | Requires brand work per module; "Pulse" as both the platform's stem and a module name risks confusion |
| **C. Hybrid lockup** — platform mark + product name (e.g., *PulseAction.AI · Pulse*) | Best of both | Heavier in UI; needs typography lockup design |

### Recommendation
**B (Distinct product names) for analyst-facing surfaces, with PulseAction.AI co-located as a small sub-mark in the corner.** Pharma analysts work in the product daily; a name they can say in a sentence ("did you check Pulse this morning?") matters. The platform mark gives architectural honesty for stakeholders who care about that layer.

Suggested module names:
- *Pulse* (CI) — matches the alert/signal/heartbeat semantics; one syllable, easy. Naturally reads as "the active half of PulseAction."
- *Atlas* (Research) — matches the graph/exploration semantics; pharma-adjacent (atlas = comprehensive map).
- Reserved future: *Compass* (Regulatory), *Beacon* (Market Access), *Forum* (KOL).

### Decision
- [ ] A · `PulseAction · {Module}` (descriptive)
- [ ] B · Distinct product names (*Pulse* / *Atlas*)
- [ ] C · Hybrid lockup

**Decided value:** _________________
**Date:** _________________
**Owner:** Product

### Implications
Affects every UI wordmark (`apps/landing/src/components/Header.tsx`, `apps/ci/src/components/Sidebar.tsx`), domain names (subdomains? routes?), email-from names for alerts, and the design-tokens accent semantics.

---

## D2 — Light vs dark default

### Question
What theme does an unauthenticated visitor see?

### Options

| Option | Pros | Cons |
|---|---|---|
| **A. Light default, dark available** | Friendlier first impression; matches Apple/Stripe; many analysts prefer light during the day | Some analyst tooling is dark-default; mild friction for that contingent |
| **B. Dark default, light available** | Matches Linear, the existing `comp_intel.tsx` mockup, "serious tool" aesthetic; better for OLED | Less inviting to non-power users; eye strain in bright office |
| **C. System preference** (`prefers-color-scheme`) | Respects user OS choice; zero friction | First-time visitors get whatever their OS says — inconsistent brand |

### Recommendation
**A (Light default), with `prefers-color-scheme: dark` honored on first load and a manual toggle persisted in localStorage.** Light is the right default impression for a new commercial product; the toggle gives analysts who live in dark themes one click to their preference.

### Decision
- [ ] A · Light default
- [ ] B · Dark default
- [ ] C · System preference

**Decided value:** _________________
**Date:** _________________
**Owner:** Design

### Implications
Affects `data-theme` initial value on `<html>`, the marketing screenshots, the Storybook background defaults.

---

## D3 — Density default per surface

### Question
What density does each module's primary surface render at by default?

### Options

| Surface | Compact | Comfortable | Spacious |
|---|---|---|---|
| Mission Control | | ✅ | |
| CI Daily Digest | ✅ | | |
| CI Signal Detail | | ✅ | |
| CI Watchlist | ✅ | | |
| CI Reviewer Queue | ✅ | | |
| CI Trackers | ✅ | | |
| Research Workspace | | ✅ | |
| Brief Composer | | ✅ | |

### Recommendation
**Compact for triage surfaces (Daily Digest, Watchlist, Reviewer Queue, Trackers), Comfortable for read/compose surfaces (Mission Control, Signal Detail, Research Workspace, Brief Composer).** Per-user override persisted per device — analysts who want everything compact can flip globally.

### Decision
- [ ] Accept the table above
- [ ] Comfortable across the board (override later per-user)
- [ ] Compact across the board

**Decided value:** _________________
**Date:** _________________
**Owner:** Design

### Implications
Default `data-density` on each surface root; user-preference UI in settings.

---

## D4 — SSO timing

### Question
Does Phase 1 ship with SSO (Okta / Google Workspace) or with email/password only?

### Options

| Option | Pros | Cons |
|---|---|---|
| **A. Phase 1 email/password only**, SSO in Phase 2 | Faster Phase 1 ship; `users_and_auth` migration 034 already exists | Internal pilot users have to manage another password; some enterprises won't pilot without SSO |
| **B. Phase 1 with SSO from day one** | Enterprise-ready; fewer credential paths | Adds 1–2 weeks of integration work to Phase 0; depends on which IdP |
| **C. Magic-link email auth** (no password) | Modern, low-friction, no password management | Some enterprises block magic links; not standard for daily-use tools |

### Recommendation
**A (Email/password Phase 1) IF Phase 1 audience is internal-only.** Migrate to SSO in Phase 2 once we know which IdP the early enterprise pilots want. If D6 below resolves to "external pilot from Phase 1," upgrade this to **B** with Okta as the first integration.

### Decision
- [ ] A · Email/password Phase 1
- [ ] B · SSO from Phase 1 — IdP: __________
- [ ] C · Magic-link

**Decided value:** _________________
**Date:** _________________
**Owner:** Engineering + Security

### Implications
Affects auth migration plan, deployment env-var requirements, login UX in Mission Control.

---

## D5 — Commercial model

### Question
Is the platform sold as one license, or per-module?

### Options

| Option | Pros | Cons |
|---|---|---|
| **A. Per-module licensing** | Aligns price to use; lets customers add modules incrementally; matches Microsoft/Slack model | RBAC complexity (which modules each user has); marketing per module |
| **B. Single platform license** | Simpler sales motion; "all-you-can-eat" appeal; simpler RBAC | Sells the unused; harder to introduce expensive Tier 3-dependent modules later |
| **C. Tiered platform** (Standard / Pro / Enterprise) with module bundles | Common SaaS pattern; flexible | Hardest to design and explain |

### Recommendation
**A (Per-module licensing).** Per the platform thesis: each module is a product on top of the same horizontal layers. Customers may buy CI without Research, or vice versa. Tier 3-vendor-dependent modules (Phase 2/3) will have meaningfully different cost basis and should be priced separately. RBAC complexity is real but we're paying for it anyway because of D7.

### Decision
- [ ] A · Per-module
- [ ] B · Single platform
- [ ] C · Tiered bundles

**Decided value:** _________________
**Date:** _________________
**Owner:** Product + Commercial

### Implications
RBAC scopes, billing model, Mission Control's empty-state behavior (show "Discover X" cards for non-licensed modules), license-server integration.

---

## D6 — External users in Phase 1

### Question
Is Phase 1's pilot audience internal-only (your CI team), or does it include at least one external paying customer?

### Options

| Option | Pros | Cons |
|---|---|---|
| **A. Internal-only Phase 1 pilot** (4–8 users) | Lowest risk; full feedback velocity; defer compliance work | Slower revenue path; less external validation |
| **B. One external pilot customer** (e.g., a brand team at a single pharma) | External validation; potential reference customer | Adds compliance work (data residency, audit log requirements, SLA) and SSO requirement |
| **C. Multiple external pilots** | Strongest validation | Delays Phase 1 by ~4 weeks; multi-tenancy now becomes Phase 1 not Phase 2 |

### Recommendation
**A (Internal-only Phase 1)**, with explicit plan to onboard one external pilot at Phase 1.5 (signal-quality stable). Use Phase 1 to harden signal accuracy against the eval set. Going external before signals are reliable damages reference value.

### Decision
- [ ] A · Internal-only
- [ ] B · One external pilot
- [ ] C · Multiple external pilots

**Decided value:** _________________
**Date:** _________________
**Owner:** Product + GTM

### Implications
Multi-tenancy scope in Phase 1, audit log retention requirements, SSO timing (D4), data residency.

---

## D7 — Reviewer role

### Question
Are the reviewers (per CI principle P5 — "humans validate before high-stakes outputs ship") drawn from the CI analyst pool, or is there a dedicated reviewer role?

### Options

| Option | Pros | Cons |
|---|---|---|
| **A. CI analysts review each other's signals** | Lower headcount; analysts have domain context; same workflow surface | Conflict-of-interest on hot signals; capacity drain on triage time |
| **B. Dedicated reviewer (senior CI lead, 0.3–0.5 FTE)** | Clean separation of duties; quality consistency; fast SLA | New hire / re-org; one bottleneck on absences |
| **C. Hybrid: dedicated reviewer for impact=high; analysts review impact=medium** | Routes the limited resource to where it matters | More complex routing; two paths to maintain |

### Recommendation
**C (Hybrid)** assuming D5 is committed. Dedicated reviewer for impact=high — fast SLA (2 business hours), quality bar enforced. Analysts self-review impact=medium with random spot-checks by the dedicated reviewer. Impact=low is auto-shipped (no review). This is the only option that hits both the SLA target and the cost target.

### Decision
- [ ] A · Analyst pool reviews
- [ ] B · Dedicated reviewer
- [ ] C · Hybrid

**Decided value:** _________________
**Date:** _________________
**Owner:** Product + Operations

### Implications
F7 (Reviewer Queue) UI design — single workflow vs role-switched; staffing plan; reviewer-action telemetry; SLA dashboard.

---

## D8 — Supersedence reason enum

### Question
When a Signal supersedes another, which enum captures *why*? (Per SPEC-016 §1.2 — supersedence semantics need to distinguish correction from progression.)

### Options

Proposed enum values:

| Value | Meaning | Example |
|---|---|---|
| `corrected` | Prior signal had factual error; this one is the correction | "Approval date was wrong; fixed." |
| `progressed` | World moved forward; both signals are valid history | "Phase 2 → Phase 3 status change." |
| `downgraded` | Confidence tier reduced (e.g., expected SEC confirmation never arrived) | "Press release claim not confirmed in 4 days; demoted to reported." |
| `retracted` | Source retracted the underlying claim | "Press release withdrawn." |
| `merged` | Two distinct signal candidates determined to be the same event | "Wire-service article + 8-K were the same approval event." |

### Options for the choice itself

| Option | Pros | Cons |
|---|---|---|
| **A. Adopt the 5-value enum above** | Covers known cases; clear per-value UX semantics | Five is the max — keep tight |
| **B. Two values: `correction | progression`** | Simplest; matches the UI distinction | Loses fidelity for retraction / downgrade flows |
| **C. Free-text `supersedence_note`** | Maximum flexibility | Unanalyzable; analyst-typed prose drifts |

### Recommendation
**A (5-value enum) plus an optional `supersedence_note` free-text field for nuance.** UX semantics:

- `corrected` → old hidden in active digest, link "see correction"
- `progressed` → both shown in entity history strip, no hide
- `downgraded` → still visible but tier-badged
- `retracted` → old struck through, prominent retraction notice
- `merged` → old soft-hidden, evidence absorbed into new

### Decision
- [ ] A · 5-value enum (recommended)
- [ ] B · Two values
- [ ] C · Free text

**Decided value:** _________________
**Date:** _________________
**Owner:** Product + Engineering

### Implications
`signals.supersedence_reason` column type; Signal detail UI rendering; alert delivery suppression rules; reviewer queue presentation.

---

## Phase 0 dependencies

These decisions block specific Phase 1 sprint tasks:

| Decision | Blocks |
|---|---|
| D1 (brand) | C1 (Mission Control wordmark), all marketing artifacts |
| D2 (theme default) | C1, C2 (initial render) |
| D3 (density per surface) | C1, C3, C4, C5, C6 |
| D4 (SSO timing) | Auth migration, Phase 0 P0.9 final wiring |
| D5 (commercial) | RBAC scope design, Mission Control empty states for non-licensed modules |
| D6 (external Phase 1) | Multi-tenancy scope, compliance work |
| D7 (reviewer role) | F7 design, staffing plan, B9 reviewer queue scope |
| D8 (supersedence enum) | B7.2 supersedence semantics, signals schema |

---

## Decision log

When a decision is finalized, append below in this format:

```
[YYYY-MM-DD] D# decided: <choice>. Owner: <name>. Rationale: <one line>.
```

(empty until first decision is made)

---

*Authored 2026-04-28. Lives alongside SPEC-016 as the dependency-tracker for Phase 1 sprint kickoff.*
