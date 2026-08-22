# TIV2 coordination kernel

**Status:** owner-directed implementation candidate. It is not active until independently reviewed,
merged to protected `main`, and observed successfully in CI.

## Goal

Replace manual multi-agent status editing with a small deterministic controller. Builders consume one
bounded work contract at a time. Reviewers consume an exact-SHA queue. The owner handles architecture,
priority, risk, and release decisions rather than relaying agent transcripts.

## Sources of truth

- `docs/COORDINATION.md` carries compact policy and program sequence. Feature builders never edit it.
- `coordination/contracts/work_graph.json` is the protected machine authority for dependencies, lanes,
  path claims, migration reservations, canonical acceptance statements, and verification methods.
- A design spec explains intent, constraints, and examples. It cannot redefine a criterion referenced
  by ID; the protected work graph is canonical when prose differs.
- GitHub issues, PRs, checks, and reviews are observations. Labels and agent prose are only mirrors.
- The controller derives eligibility. A builder cannot declare its own work review-ready or approved.
- File-based validation binds the parsed graph to canonical JSON using SHA-256, so LF/CRLF checkout
  policy cannot change the result. The future adapter must additionally bind the repository remote,
  protected ref, commit, Git blob, live baseline, and GitHub observations.
- JSON parsing is strict: duplicate object keys and non-finite numbers fail before validation, avoiding
  a graph whose meaning changes between parsers while retaining a valid collapsed digest.

## State model

```text
planned -> claimed -> red -> building -> green_local -> ci -> review_ready
review_ready -> changes_required -> building
review_ready -> approved -> merged -> observed -> closed
any non-terminal -> blocked
owner only -> cancelled
```

Blocked work retains its lane. An agent does not start a second item because its first item is waiting.
A push after review invalidates approval and returns the item to `building`.
`merged`, `observed`, and `closed` are not trusted labels: they require the same valid approval plus
externally bound merge evidence; observation and closure add their own timestamped evidence.
The future review-ready event persists repository, ref, baseline SHA, head SHA, canonical graph
digest plus Git blob, observation
window, and immutable evidence URL so later terminal validation does not substitute the newer `main`
SHA for the baseline that was reviewed.
`merged` does not satisfy a dependency. Only successful post-merge observation (`observed` or
`closed`) releases downstream work.

## Canonical acceptance contracts

The exact text and independent verification route for `CK#1` through `CK#6`, `A000#1`, and `B000#1`
live in `coordination/contracts/work_graph.json`. Future controller output must include both,
preventing an ID from retaining its name while its meaning silently changes.

The six kernel classes are graph integrity, collision control, TDD evidence, exact-head independent
review, protected-surface control, and non-vacuity. Their machine statements, not this summary, are the
acceptance bar.

## Development protocol

For every implementation item:

1. PM/controller selects the next dependency-ready item; the builder cannot pick around blockers.
2. The contract fixes the spec, acceptance statements, verifier, base, path claim, dependencies, risk,
   required checks, and any migration reservation before implementation begins.
3. The builder captures a real failing RED after the protected base and before the implementation,
   then a passing GREEN after the final edit. The controller requires external proof of
   `base -> distinct RED -> final head`. Counts and immutable evidence links are collected by tooling,
   not memory.
4. A failed check is fixed as a defect class: find siblings, report found/fixed/residual counts, and add
   a regression or mutation test. Point-patching a cited line is not closure.
5. Deterministic checks run before independent model judgement. Executable artifacts such as DDL must
   execute in an isolated compatible runtime before review.
6. Every item predeclares a `test:<path>` verifier. A `contract_pending` item is not eligible and its
   future path may be absent. Before activation, a separate protected contract change must make the
   item `executable`; from that point the test file must exist and CI derives the executed set from
   executable graph nodes. Missing targets, unsupported syntax, or an empty executable set fail closed.
7. The configured non-author reviewer reads the queue and submits only `APPROVE` or
   `CHANGES-REQUIRED` on the exact live head.
8. The owner merges or activates only after the server-side gate is green.

## Non-goals and trust boundary

This pure kernel cannot make local hooks tamper-proof, replace GitHub branch protection, create a
second human, auto-merge, change the acceptance bar, or activate production. Hooks are local guidance;
CI and server-side rules are the structural floor. Phase 1 exposes validation and graph-derived test
execution only; it does not register or export state, readiness, review, or queue methods. Synthetic
input containing observations and all live-shaped input fail closed. A later adapter-backed controller
is a separate type and must bind repository remote, ref, commit, graph digest/blob, and GitHub evidence
before exposing decisions.

## Rollout gates

1. `V2-GOV-001`: independently review and land this pure kernel and mutation suite.
2. `V2-GOV-002`: add the bound read-only GitHub adapter.
3. `V2-GOV-003`: prove it on disposable issues and PRs, including stale-head and self-review failures.
4. `V2-GOV-004`: enable board-sync in nudge mode and prove both CLIs.
5. `V2-GOV-005`: add serialized claim/invalidation mutations and label mirrors.
6. `V2-GOV-006`: observe pre-review and merge gates before making them required.
7. `V2-GOV-007`: pass two complete disposable lifecycles and record owner activation.

Only `V2-GOV-001` is `executable` in this change. Gates 2-7 and the two feature-lane baselines are
`contract_pending`: their exact future test paths are protected now, but they cannot enter a lifecycle
until a separate protected contract PR supplies the executable test and owner authorization.

Core `V2-A-000` and Data `V2-B-000` depend on `V2-GOV-007`; the graph cannot release either lane
after the kernel alone.

The first workflow is deliberately named `coordination-kernel`: it proves the deterministic exam, not
live GitHub reconciliation. The system is not described as foolproof or hardened until the structural
rollout completes and its bypass tests are green.
