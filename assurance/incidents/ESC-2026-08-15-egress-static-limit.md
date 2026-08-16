# ESC-2026-08-15-egress-static-limit

- **Date:** 2026-08-15
- **Class:** security gate overclaimed its guarantee (a "cannot fail on a real bypass" static
  scanner silently missed statically-resolvable egress forms; and static analysis has a real
  runtime residual that must be named, not implied away)
- **Severity:** P1 (no live bypass shipped, but the WP-12C scanner is the inventory gate that
  later feeds PRIV-001b's guard-coverage assertion — a silent miss there is a silent hole)
- **Status:** **MITIGATED (not CLOSED).** The statically-resolvable forms below are CLOSED with
  passing regression tests. The *runtime-dynamic* residual is an accepted static-analysis
  limit, backstopped by the PRIV-001b runtime guard — it stays MITIGATED until PRIV-001b lands
  and is enforced.

## What escaped

An independent review of PR #327 (head `39df6cd`) reproduced four egress forms that the
"terminal-complete" scanner scanned to `hits=0`, while its docstring claimed a gate that
"cannot fail on a real bypass":

1. `getattr(client.chat.completions, "create")(...)` — string-literal reflection terminal.
2. `functools.partial(client.chat.completions.create)` then calling the result.
3. `self._go = client.chat.completions.create` (instance-attribute cache) then `self._go(...)`.
4. `go, _ = client.chat.completions.create, 1` (tuple-unpack) then `go(...)`.

All four are **statically resolvable** — no runtime information is needed to see them — so
deferring them while shipping the overclaim is the exact "treat a real bypass as out-of-scope"
move WP-12 exists to stop (conservation principle #3: a gate blind to a real bypass is vacuous).

## Root cause

The AST visitor only resolved aliases assigned to a single `Name` target and only inspected
call funcs that were `ast.Attribute`/`ast.Name`. It ignored: `ast.Call` funcs (`getattr(...)()`,
`partial(...)()`), attribute-target assignments (`self.x = ...`), tuple/list-unpack targets,
and the `getattr`/`partial` indirections.

## The fix (structural)

`assurance/egress_scan.py` now resolves the callable a value represents through `getattr` and
`partial`, tracks attribute-target aliases module-wide with a pre-pass (so `self.x(...)` is
caught regardless of method order), resolves them transitively (`self._go = self._raw = chain`),
handles tuple/list-unpack targets, `ast.Call` funcs, and walrus (`:=`) aliases, and — critically
— consults the attribute-alias table even when the attribute name IS a terminal word. The module
docstring is corrected to claim only what static analysis can deliver.

## Round-3 recurrence (found by the verification review, now closed)

A verification review reproduced a member of THIS class that the first fix missed:
`self.create = client.chat.completions.create ; self.create(...)` → `hits=0`. The
terminal-method branch matched `.create` on the *direct* chain (`self.create`, no provider
substring) and never fell through to the attribute-alias table. This is the exact "class claimed
closed while a realistic member is open" pattern; it is now closed (fall-through added), with
`test_scanner_catches_self_attr_named_like_terminal` plus walrus + two-hop tests. Lesson logged:
when you claim a *class* closed, test the most NATURAL member, not only a non-colliding one.

## The residual (named, not hidden)

Static analysis **cannot** see egress whose shape is only decidable at runtime — a method/attr
name in a variable (`getattr(o, name)` with `name` computed), a client injected by a
plugin/reflection, or `exec`/`eval`. It also does **not** model **container/subscript
indirection**, even with a literal key (`{"create": chain}["create"]()`), because that opens an
unbounded dict/`.get`/list-modeling surface; nor **cross-receiver attribute-cache namespace
unification** — `cls.create = client...create` set in a classmethod and read as `self.create(...)`
aliases the same slot through Python's class/instance attribute semantics, which static
name-resolution does not unify (same-receiver forms `self.x = ...; self.x(...)` ARE closed).
These are boundaries of the technique, not bugs to patch in the scanner; each is pinned by a
`strict=True` xfail so it can never be silently claimed as covered.

**⚠️ Correction on the "runtime backstop" (an earlier overclaim):** the PRIV-001b runtime guard
(`services/llm_gateway.py::guard_*`) wraps the **provider SDK client** `.create(...)` calls — it
only sanitizes egress that goes THROUGH those adapters. It does **NOT** intercept arbitrary
direct HTTP: a hand-rolled `requests.post(provider_url, ...)`, `httpx`, or
`urllib.request.urlopen(...)` bypasses the SDK client and therefore the wrapper entirely. So the
backstop for the SDK-client residuals above (runtime-computed method name, subscript indirection,
cross-receiver cache) is the runtime guard **only because those forms still terminate in an SDK
`.create`**. For NON-SDK direct HTTP there is no runtime backstop — the **static scanner is the
sole control**, which is why `urlopen(...)`/requests/httpx provider egress is now detected
statically (WP-12C), not deferred to a runtime guard that would never see it.

## Regression tests

- `tests/test_wp12c_egress_mutation.py::test_scanner_catches_getattr_reflection_terminal`
- `::test_scanner_catches_functools_partial_alias` / `::test_scanner_catches_partial_immediate_call`
- `::test_scanner_catches_self_attr_cached_callable`
- `::test_scanner_catches_self_attr_even_when_call_precedes_init`
- `::test_scanner_catches_tuple_unpack_alias` / `::test_scanner_catches_getattr_http`
- `::test_runtime_dynamic_dispatch_is_a_known_static_limit` — an **xfail** that documents the
  runtime residual: a runtime-computed `getattr(o, name)()` is NOT caught statically (and must
  not be silently claimed as covered). It flips to a real failure if someone ever claims to
  close it in the static scanner without the runtime guard.
