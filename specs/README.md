# specs/ — index & canonical status

> **Clean source of trust.** This index says what is *current* vs *historical*.
> If a spec isn't listed under "Active" below, treat it as **reference/history** —
> the feature shipped and the living source is now the code + the boards, not the
> spec. Don't plan new work from an unlisted spec without re-validating it.

## Where the living truth actually lives

| You want… | Read |
|---|---|
| Operating rules / architecture / conventions | `../CLAUDE.md` |
| The harness floor (gates, DoD, protected surface) | `../.claude/rules/conservation-gates.md`, `../protected-surface.txt` |
| **Who owns what + how the agent lanes coordinate** | `../docs/COORDINATION.md` |
| Product / feature backlog (the feature board) | `../docs/PRODUCT_BACKLOG.md` |
| Backend↔frontend API contract | `../AGENTS.md` |

## Active specs (still describe current intent)

- `SPEC_001_autonomous_research_engine.md` — CTX pipeline architecture *(stub → `../docs/archive/superseded-specs/`; CLAUDE.md cites it)*
- `SPEC_002_frontend_ux_revamp.md` — UI design system *(stub → archive; CLAUDE.md cites it)*
- `SPEC_DATA_001_data_layer_remediation.md` — **data lane** active remediation plan (D1–D8)
- `data_strategy.md` — **data lane** living strategy (untracked working doc; owned by the data session)

## Historical (completed; kept for reference, not current intent)

These shipped — the code is the source of truth. Grouped by the lane that would
archive them (per `../docs/COORDINATION.md`); each lane prunes its own as cleanup.

- **Platform / backend** (decision flywheel, briefs, ledger, sim, gateway,
  registry, adversaries, materiality, learning, signing, ask-graph, engagements,
  context layer, feedback loop, fact/insight/entity/priority schemas): `SPEC_021`,
  `SPEC_023`–`SPEC_028`, `SPEC_029_framing_triggers`, `SPEC_031`–`SPEC_035`,
  `SPEC_041`, `SPEC_042`, `SPEC_A_*`, `SPEC_A2a_*`, `SPEC_W1`/`W2`, `SPEC_Z2`–`SPEC_Z5`,
  `BE_015`/`BE_017`/`BE_026`, `CI_Agent_Reimagined_Spec`.
- **Data / sensing** (data lane prunes): `SPEC_019_connector_management`,
  `SPEC_A1_fact_assertion_on_ingest`, `SPEC_Z1_fact_class`, plus the archived
  `SPEC_012`/`SPEC_013` stubs.
- **Frontend / UI** (Antigravity prunes): `SPEC_020`, `SPEC_022`, `SPEC_029_app_aesthetics`,
  `SPEC_030`, `SPEC_D1`/`D2`, all `SPEC_F2`–`SPEC_F12`, all `SPEC_LOOP_*`, all `SPEC_PB_*`,
  `raw_helix.md`/`helix_proto.tsx`/`test.tsx` prototypes.

## Already archived (SPEC-042, 2026-05-09)

`SPEC_001`–`SPEC_018` and various plans/notes were archived to
`../docs/archive/superseded-specs/`; the files remaining here under those names
are **redirect stubs**. See `../docs/archive/README.md`.
