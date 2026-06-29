# Runbook: migration-sequence integrity

**Gate:** `tests/test_migration_integrity.py` (Lane-1, deterministic, DB-free)
**Wired:** `.github/workflows/conservation-gate.yml`, `protected-surface.txt`, `.github/CODEOWNERS`

## What it protects

`migrate.py` builds a database by applying every `.sql` in `schema/migrations/`
in number order and recording each in `schema_migrations`; re-runs skip what is
already applied (the auto-migrate-on-boot contract in
`tests/test_auto_migrate.py`). The blind spot: **a migration whose file is
missing from disk is invisible.** A DB that already has it applied never
notices — but a *fresh* rebuild (Railway redeploy from scratch, new contributor,
disaster recovery) produces a schema missing whatever that migration created,
and any later migration or code that depends on it crashes. The **fresh-DB crash
risk**. This is how migration **090** (fact governance) sat lost on `main`
undetected.

The gate makes that loss **fail closed at PR time** (conservation principle 3 —
no vacuous green).

## What it asserts

1. **No unexplained gap.** Every number in `[1, MAX]` is present, or a
   documented `SKIPPED_NUMBER`, or a tracked `PENDING_RESTORE`. Any *other*
   missing number fails — the new-silent-loss signal.
2. **Filename hygiene** (`NNN_lowercase_name.sql`) and **no duplicate numbers**,
   so sorted-by-filename apply order equals numeric order.
3. **Allowances stay honest.** `PENDING_RESTORE` entries must each name an owning
   PR, and the allowance **self-expires**: once a restored file lands on disk,
   `test_pending_restore_self_expires` fails until the entry is removed.

### The two allowance categories

- `SKIPPED_NUMBERS` — numbers never authored (the sequence jumped `083` → `087`,
  leaving 084/085/086 as permanent holes). No file is ever expected.
- `PENDING_RESTORE` — numbers that ARE real migrations, currently lost from
  `main`, whose restoration is an in-flight PR. This dict MUST shrink to empty
  as the PRs land.

## When the gate fires — how to respond

**`Unexplained gap(s) in the migration sequence: [N]`**
A migration number `N` is missing and is neither skipped nor pending. Decide which:
- *It was applied to prod but the file was never committed* → recover the file
  (check other branches: `git log --all --oneline -- 'schema/migrations/0NN_*'`)
  and commit it. A fresh rebuild needs it.
- *It is a real lost migration being restored in another PR* → add
  `N: "PR #xxx — restores 0NN_name.sql"` to `PENDING_RESTORE`.
- *It was never authored (a deliberate skip)* → add `N: "<reason>"` to
  `SKIPPED_NUMBERS`. Use sparingly; prefer a contiguous sequence.

**`migration 0NN now has a file on disk — its restoration is complete`**
The pending restoration landed. Remove `N` from `PENDING_RESTORE` (one line). Do
this **in the same PR that restores the file** — restoring a lost migration
should also retire the allowance that documented its absence.

## Known limitation — top-edge loss

The gap check is bounded by the highest migration number **on disk**, so it
catches *interior* loss (e.g. 090, lost between 089 and 091 — the realised
failure mode) but **not** a migration lost at a number *above* the current
maximum. There is no DB-free source of the "true ceiling" to check against. This
hole self-closes the moment any higher migration lands (the lost number becomes
interior). The cheap prod cross-check below (`migrate.py --check`) is the way to
catch a top-edge divergence in the meantime.

## Confirming against prod (optional, needs `DATABASE_URL`)

The gate is DB-free — it reasons about the disk sequence, which is what a fresh
rebuild produces. To cross-check what prod actually has applied:

```
python migrate.py --check     # prints [APPLIED]/[PENDING] per on-disk file
```

A migration that is `[PENDING]` against prod but whose objects already exist
(or vice-versa) is a sign the file/`schema_migrations` ledger diverged — worth a
closer look, but orthogonal to the disk-sequence integrity this gate guards.
