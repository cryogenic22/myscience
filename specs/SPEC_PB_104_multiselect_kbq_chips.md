# PB-104 — Multi-select KBQ chips (Loop #5)

**Status:** Shipped 2026-05-11
**Type:** bug
**Priority:** high
**Owner:** frontend-claude
**Source:** `docs/PRODUCT_BACKLOG.md` PB-104
**Source ref:** `design-review-output/enhancement-backlog.md` E1.S1.4 (heuristic finding H2)

## Why

`KBQFilter` was single-select: clicking a chip cleared the rest. Analysts
filtering the Signals DB couldn't combine cross-cutting questions
(e.g. "show me everything that's both `financial` and `regulatory`"). The
design review flagged this as a high-severity trust finding.

## What

1. `KBQFilter` (`frontend/src/components/ci/KBQFilter.tsx`) becomes
   multi-select: `selected: string[]` + `onSelect: (next: string[]) => void`.
2. The "All" chip clears the selection (active iff `selected.length === 0`).
3. Each KBQ chip toggles its membership in the array.
4. `aria-pressed` reflects each chip's state for assistive tech.
5. `SignalsTab` mirrors the selection to the URL via
   `useSearchParams`: `?kbq=financial,regulatory`. Reload restores the
   same chips.
6. `signalsApi.list` (`frontend/src/api.ts`) accepts `kbq?: string[]` and
   serialises to a single CSV `kbq=...` query param.
7. `/signals` (`api/routes/signals.py`) accepts a CSV of kbq tags and
   matches signals whose `kbq_tags` overlap any of them (PG `&&`
   array-overlap). Empty / whitespace-only / duplicate values are
   stripped before the query.

## Tests

- `frontend/__tests__/ci/KBQFilter.test.tsx` — 7 tests (empty state,
  multi-select active state, additive add, remove, "All" clears,
  aria-pressed).
- `tests/test_signals_api.py` — 3 new tests (CSV any-of match,
  whitespace stripping, empty-after-strip is a no-op). Pre-existing
  single-value test still passes.

## Compatibility

- Pre-existing `?kbq=financial` URLs still work (CSV with one value).
- `SignalsListParams.kbq` was `string | undefined`, now `string[] | undefined`.
  Only `SignalsTab` consumed this type; updated in same diff.

## Out of scope / deferred

- KBQ allowlist on the backend (silent any-string match preserved
  from pre-PB-104 behaviour).
- URL-sync for the impact filter (separate PB).
- Server-side dedup of `signal_kbq` URL param in `WarRoomView` (a
  different feature; uses a different param name).
