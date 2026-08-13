# PR Disposition — H0.1 census (hardened, on baseline 2026-08-13)

> **PROPOSED — verification pending (H0.2, owner-reviewed).** Per SPEC_HANDOFF §H0.1.3/§H0.2.4: do **not** infer an old PR has no unique commits; each `SUPERSEDED?`/close needs a `git log origin/main..<branch>` unique-commit check. All 41 PRs show **reviewDecision = none**.

origin/main = `31d923a` (2026-07-04); **no PR merged in ~40d** — these 41 are unmerged May–Jul work. #325/#326 are **H1-PROTECT** (excluded from cleanup).

| PR | branch | lane | mergeable | tip_on_origin | +/- | updated | merged | proposed disposition |
|---|---|---|---|---|---|---|---|---|
| #37 | `claude/be-002-materiality-diagnostic` | Product-Platform | CONFLICTING | yes | +852/-2 | 2026-05-10 | no | STALE-SCAFFOLD (3mo BE-*) — needs-rebase OR close-after-preserve; verify unique commits |
| #38 | `claude/be-037-tenant-id-core` | Product-Platform | MERGEABLE | yes | +518/-0 | 2026-05-10 | no | STALE-SCAFFOLD (3mo BE-*) — needs-rebase OR close-after-preserve; verify unique commits |
| #39 | `claude/be-038-tenant-isolation-middleware` | Product-Platform | MERGEABLE | yes | +529/-1 | 2026-05-10 | no | STALE-SCAFFOLD (3mo BE-*) — needs-rebase OR close-after-preserve; verify unique commits |
| #40 | `claude/be-039-tenant-audit-tests` | Product-Platform | MERGEABLE | yes | +513/-0 | 2026-05-10 | no | STALE-SCAFFOLD (3mo BE-*) — needs-rebase OR close-after-preserve; verify unique commits |
| #41 | `claude/be-001-evidence-card-fields` | Product-Platform | MERGEABLE | yes | +742/-5 | 2026-05-10 | no | STALE-SCAFFOLD (3mo BE-*) — needs-rebase OR close-after-preserve; verify unique commits |
| #43 | `claude/be-016-citation-tier` | Product-Platform | MERGEABLE | yes | +254/-0 | 2026-05-10 | no | STALE-SCAFFOLD (3mo BE-*) — needs-rebase OR close-after-preserve; verify unique commits |
| #45 | `claude/be-018-source-aggregation` | Product-Platform | MERGEABLE | yes | +217/-0 | 2026-05-10 | no | STALE-SCAFFOLD (3mo BE-*) — needs-rebase OR close-after-preserve; verify unique commits |
| #47 | `claude/be-019-why-this` | Product-Platform | CONFLICTING | yes | +425/-0 | 2026-05-10 | no | STALE-SCAFFOLD (3mo BE-*) — needs-rebase OR close-after-preserve; verify unique commits |
| #49 | `claude/be-021-saved-views` | Product-Platform | CONFLICTING | yes | +530/-0 | 2026-05-10 | no | STALE-SCAFFOLD (3mo BE-*) — needs-rebase OR close-after-preserve; verify unique commits |
| #56 | `claude/be-025-licence-model` | Product-Platform | MERGEABLE | yes | +230/-0 | 2026-05-10 | no | STALE-SCAFFOLD (3mo BE-*) — needs-rebase OR close-after-preserve; verify unique commits |
| #60 | `claude/be-009-adversary-twin` | Product-Platform | MERGEABLE | yes | +369/-0 | 2026-05-10 | no | STALE-SCAFFOLD (3mo BE-*) — needs-rebase OR close-after-preserve; verify unique commits |
| #61 | `claude/be-010-adversary-posterior` | Product-Platform | MERGEABLE | yes | +163/-0 | 2026-05-10 | no | STALE-SCAFFOLD (3mo BE-*) — needs-rebase OR close-after-preserve; verify unique commits |
| #62 | `claude/be-011-cockpit-stream` | Product-Platform | CONFLICTING | yes | +130/-0 | 2026-05-10 | no | STALE-SCAFFOLD (3mo BE-*) — needs-rebase OR close-after-preserve; verify unique commits |
| #63 | `claude/be-012-agent-authority` | Product-Platform | MERGEABLE | yes | +399/-0 | 2026-05-10 | no | STALE-SCAFFOLD (3mo BE-*) — needs-rebase OR close-after-preserve; verify unique commits |
| #64 | `claude/be-013-authority-endpoints` | Product-Platform | MERGEABLE | yes | +88/-0 | 2026-05-10 | no | STALE-SCAFFOLD (3mo BE-*) — needs-rebase OR close-after-preserve; verify unique commits |
| #65 | `claude/be-014-delegation-executor` | Product-Platform | MERGEABLE | yes | +336/-0 | 2026-05-10 | no | STALE-SCAFFOLD (3mo BE-*) — needs-rebase OR close-after-preserve; verify unique commits |
| #66 | `claude/be-027-034-phase1-connectors` | Product-Platform | CONFLICTING | yes | +524/-0 | 2026-05-10 | no | STALE-SCAFFOLD (3mo BE-*) — needs-rebase OR close-after-preserve; verify unique commits |
| #67 | `claude/be-035-curator-weight-learning` | Product-Platform | MERGEABLE | yes | +318/-0 | 2026-05-10 | no | STALE-SCAFFOLD (3mo BE-*) — needs-rebase OR close-after-preserve; verify unique commits |
| #68 | `claude/be-036-source-health` | Product-Platform | MERGEABLE | yes | +265/-0 | 2026-05-10 | no | STALE-SCAFFOLD (3mo BE-*) — needs-rebase OR close-after-preserve; verify unique commits |
| #69 | `claude/be-040-system-prompts-registry` | Product-Platform | CONFLICTING | yes | +287/-2 | 2026-05-10 | no | STALE-SCAFFOLD (3mo BE-*) — needs-rebase OR close-after-preserve; verify unique commits |
| #70 | `claude/be-041-prompt-calibration` | Product-Platform | MERGEABLE | yes | +299/-0 | 2026-05-10 | no | STALE-SCAFFOLD (3mo BE-*) — needs-rebase OR close-after-preserve; verify unique commits |
| #183 | `claude/data-substrate-emitters` | Data/Substrate | CONFLICTING | yes | +1339/-23 | 2026-06-08 | no | NEEDS-REBASE — conflicts; rebase onto baseline then re-review |
| #185 | `claude/fact-governance-convergence` | Data/Substrate | MERGEABLE | yes | +1572/-8 | 2026-06-28 | no | REVIEW/merge-candidate — recent+mergeable; independent review per SPEC_HANDOFF §4 |
| #186 | `claude/grounded-trial-answers` | Product-Platform | MERGEABLE | yes | +278/-0 | 2026-06-08 | no | REVIEW/merge-candidate — recent+mergeable; independent review per SPEC_HANDOFF §4 |
| #209 | `claude/platform/delivery-dashboard` | Product-Platform | MERGEABLE | yes | +248/-0 | 2026-06-11 | no | REVIEW/merge-candidate — recent+mergeable; independent review per SPEC_HANDOFF §4 |
| #216 | `claude/data/faers-discipline` | Data/Substrate | MERGEABLE | yes | +297/-2 | 2026-06-11 | no | REVIEW/merge-candidate — recent+mergeable; independent review per SPEC_HANDOFF §4 |
| #217 | `claude/data/mechanism-granularity` | Data/Substrate | MERGEABLE | yes | +278/-14 | 2026-06-12 | no | REVIEW/merge-candidate — recent+mergeable; independent review per SPEC_HANDOFF §4 |
| #222 | `claude/data/canonical-orphan-repair` | Data/Substrate | MERGEABLE | yes | +288/-0 | 2026-06-13 | no | REVIEW/merge-candidate — recent+mergeable; independent review per SPEC_HANDOFF §4 |
| #236 | `claude/data/coord-sync-protocol` | Data/Substrate | CONFLICTING | yes | +467/-2 | 2026-06-13 | no | NEEDS-REBASE — conflicts; rebase onto baseline then re-review |
| #238 | `claude/data/eval-comprehensive` | Data/Substrate | MERGEABLE | yes | +1080/-0 | 2026-06-13 | no | REVIEW/merge-candidate — recent+mergeable; independent review per SPEC_HANDOFF §4 |
| #242 | `claude/data/brand-alias-backfill` | Data/Substrate | CONFLICTING | yes | +1707/-0 | 2026-06-13 | no | NEEDS-REBASE — conflicts; rebase onto baseline then re-review |
| #317 | `claude/synth/ctx-negation-canary` | Product-Platform | MERGEABLE | yes | +181/-0 | 2026-07-05 | no | REVIEW/merge-candidate — recent+mergeable; independent review per SPEC_HANDOFF §4 |
| #318 | `claude/chore/ctxpack-session-memory-hooks` | Product-Platform | MERGEABLE | yes | +40/-1 | 2026-07-04 | no | REVIEW/merge-candidate — recent+mergeable; independent review per SPEC_HANDOFF §4 |
| #319 | `claude/data/lane2-ledger-freshness-monitor` | Data/Substrate | MERGEABLE | yes | +297/-20 | 2026-07-12 | no | REVIEW/merge-candidate — recent+mergeable; independent review per SPEC_HANDOFF §4 |
| #320 | `claude/data/fair-product-honest-reachable` | Data/Substrate | MERGEABLE | yes | +193/-22 | 2026-07-04 | no | REVIEW/merge-candidate — recent+mergeable; independent review per SPEC_HANDOFF §4 |
| #321 | `claude/frontend/ui-honesty-loop2` | Product-Platform(FE) | MERGEABLE | yes | +844/-84 | 2026-07-06 | no | REVIEW/merge-candidate — recent+mergeable; independent review per SPEC_HANDOFF §4 |
| #322 | `claude/data/dataset-definitions-all-sources` | Data/Substrate | MERGEABLE | yes | +559/-35 | 2026-07-06 | no | REVIEW/merge-candidate — recent+mergeable; independent review per SPEC_HANDOFF §4 |
| #323 | `claude/platform/redteam-board-consolidation` | Product-Platform | MERGEABLE | yes | +153/-4 | 2026-07-12 | no | REVIEW/merge-candidate — recent+mergeable; independent review per SPEC_HANDOFF §4 |
| #324 | `claude/data/qual-source-quality-provenance` | Data/Substrate | MERGEABLE | yes | +172/-11 | 2026-07-12 | no | REVIEW/merge-candidate — recent+mergeable; independent review per SPEC_HANDOFF §4 |
| #325 | `claude/platform/sec-001a-debug-zs-containment` | Product-Platform | MERGEABLE | yes | +199/-25 | 2026-07-12 | no | H1-PROTECT — rebase onto baseline + INDEPENDENT review, then land (do NOT cleanup) |
| #326 | `claude/platform/priv-001-pii-egress-gateway` | Product-Platform | MERGEABLE | yes | +247/-29 | 2026-07-15 | no | H1-PROTECT — rebase onto baseline + INDEPENDENT review, then land (do NOT cleanup) |

**Clusters:** stale scaffold #37–#70 (BE-* build-asks, 2026-05-10) · mid #183–#242 (June data/eval/governance) · recent #317–#326 (July; the live-relevant set incl. #325 SEC-001a + #326 PRIV-001 = H1).
