# TIV2 coordination runbook

The normal human loop is intentionally short:

```text
Owner/PM: choose or approve priorities
Controller: select one dependency-ready item per free lane
Builder: RED -> GREEN -> CI -> request review
Reviewer: read exact-SHA review queue -> APPROVE or CHANGES-REQUIRED
Owner: merge/activate only when server gates are green
```

Builders do not edit `docs/COORDINATION.md`. They work from the controller-issued item and write
progress to its GitHub issue/PR. The PM/controller owns the compact board view.

## Local kernel checks

```powershell
python -m coordination --snapshot coordination/contracts/example_snapshot.json --allow-synthetic validate
python -m coordination --snapshot coordination/contracts/example_snapshot.json --allow-synthetic run-verifiers
```

The bundled snapshot is only a deterministic bootstrap fixture. It requires the explicit
`--allow-synthetic` switch, supports contract validation and execution of tests from executable graph
nodes, and cannot contain work observations. Phase 1 registers only `validate` and `run-verifiers`;
there is no `state`, `next`, or `review-queue` command or exported Python equivalent. All live-shaped
input is rejected until the separately reviewed, read-only GitHub adapter exists.

## Agent rule

Until `V2-GOV-007` is observed, no agent auto-picks work. If validation returns any violation, the
agent stops. A builder may not edit the graph, state machine, checks, or protected scope in the feature
PR that benefits from the change. Contract-pending work needs a separate protected contract PR before
implementation.

## Reviewer rule

After the live adapter lands, review only items it emits. Pin the remote head immediately before review
and verdict submission. Any changed head, missing check, zero-case result, self-review, unknown verdict,
or unresolved acceptance item is `CHANGES-REQUIRED`.
