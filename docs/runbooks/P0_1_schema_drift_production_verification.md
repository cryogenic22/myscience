# Runbook — P0.1 Schema Drift Production Verification

**Owner:** Platform engineer (you)
**Estimated time:** 30 minutes
**Prerequisites:** Railway CLI installed and authenticated (`railway login`); DATABASE_URL accessible

---

## Context

SPEC-010 schema drift cleanup landed in commit `f23352f` (2026-04-19). Code fixes
+ migration 032 + the static test guards are all on `main`. **What this runbook
verifies is that the migrations are applied to the live Railway Postgres**, the
ones that were missing per the April 19 crash-loop logs.

The drift this closes:

| Drift | Fix | Status before runbook | Status after |
|---|---|---|---|
| `agent_sessions` table missing in prod | Migration 029 already in repo, must be applied | ❓ unknown — was missing on Apr 19 | ✅ applied |
| `agent_events` table missing in prod | Same migration 029 | ❓ unknown | ✅ applied |
| `market_events.primary_entity_id` missing | New migration 032 | ❌ missing | ✅ added |
| `etl_runs.source_type` query | Code fix to use `source_name` | ✅ fixed in commit `f23352f` | ✅ verified |
| `steward_actions.details` query | Code fix to alias `action_details AS details` | ✅ fixed | ✅ verified |
| `clinical_trials.label` query | Code fix to use `title` | ✅ fixed | ✅ verified |
| `MIN(uuid)` in dedup | Rewrote with `DISTINCT ON` | ✅ fixed | ✅ verified |

---

## Pre-flight (1 minute)

```bash
# Confirm you're on main and synced
git checkout main && git pull --ff-only

# Confirm Railway CLI is authenticated
railway whoami

# Confirm the right project is linked
railway status
```

Expected: project linked to your Postgres + app services.

---

## Step 1 — Take a manual backup before migrating (5 minutes)

Production DB recovered from a crash 9 days ago. Don't migrate without a backup
of the current state.

**Option A — Railway-managed backup:**
1. Railway dashboard → Postgres service → Backups tab
2. Click **Create backup now**
3. Wait for completion; note the timestamp

**Option B — `pg_dump` to local file:**
```bash
railway run --service postgres pg_dump --no-owner --no-acl \
  > "backups/$(date -u +%Y%m%dT%H%M%SZ)-pre-spec010.sql"
```

Confirm file size > 100 MB (a real dump, not an empty file).

---

## Step 2 — Run the migration runner (5 minutes)

`migrate.py` is idempotent — it checks `schema_migrations` table for which
migrations have been applied and skips ones already present. Safe to run.

```bash
railway run python migrate.py
```

**Expected output (paraphrased):**
```
Connecting to DATABASE_URL...
Found 35 migrations on disk; 27 already applied; 8 new to apply:
  028_molecular_targets.sql
  029_agent_sessions.sql       ← critical
  030_concepts_table.sql
  031_mv_fallback_events.sql
  032_market_events_primary_entity_id.sql  ← critical
  033_seed_brand_aliases.sql
  034_users_and_auth.sql
  035_canonical_molecule_id.sql
Applying 028... ✓
Applying 029... ✓
Applying 030... ✓
...
All migrations applied. New schema_migrations rows: 8.
```

**If a migration fails:** stop, capture the full error. Do NOT re-run blindly.
Some migrations have CREATE TABLE IF NOT EXISTS; some don't. A failed migration
mid-way leaves the schema in a partial state. Restore the backup if needed.

---

## Step 3 — Verify the migrations took (5 minutes)

Connect via Railway shell and run the verification queries:

```bash
railway connect postgres
```

In the psql prompt:

```sql
-- 029 verification
SELECT table_name FROM information_schema.tables
WHERE table_name IN ('agent_sessions', 'agent_events');
-- Expect: 2 rows

-- 032 verification
SELECT column_name FROM information_schema.columns
WHERE table_name = 'market_events' AND column_name = 'primary_entity_id';
-- Expect: 1 row

-- Quick sanity check — schema_migrations table
SELECT migration_name, applied_at FROM schema_migrations
WHERE migration_name IN ('029_agent_sessions.sql', '032_market_events_primary_entity_id.sql')
ORDER BY applied_at DESC;
-- Expect: 2 rows, applied_at within the last few minutes

\q
```

---

## Step 4 — Run the live DB tests against prod (10 minutes)

The 7 DB-required tests in `tests/test_schema_drift_fix.py` skip locally because
there's no DATABASE_URL. Run them against the live DB:

```bash
railway run python -m pytest tests/test_schema_drift_fix.py -v --no-header
```

**Expected:** all 14 tests pass (7 static + 7 live). Zero skipped.

**If any live test fails:** the migration didn't fully apply. Check the
schema_migrations table state vs the file system; `migrate.py` may have a bug,
or a previous partial-failure may have polluted state.

---

## Step 5 — Monitor logs for 4 hours (post-deploy)

Open Railway logs for both the app service and Postgres service. Watch for:

```
relation "agent_sessions" does not exist
relation "agent_events" does not exist
column "source_type" does not exist
column "details" does not exist
column "label" does not exist
function min(uuid) does not exist
```

**None of these should appear.** If they do, capture the timestamp + the full
log line and revert. The previous well-known-good is commit `f23352f`'s parent.

After 4 quiet hours, P0.1 is closed.

---

## Step 6 — Confirm the Data Steward runs cleanly (10 minutes)

The Data Steward runs every 2 hours. Wait for one cycle, then:

```sql
-- Most recent steward session
SELECT id, status, started_at, completed_at,
       total_steps, current_step
FROM agent_sessions
WHERE agent_type = 'data_steward'
ORDER BY started_at DESC
LIMIT 5;
```

**Expected:** at least one row with `status = 'completed'`. If `status = 'failed'`,
inspect `agent_events` for the same `session_id` to see what went wrong:

```sql
SELECT event_type, tool_name, result_status, metadata, created_at
FROM agent_events
WHERE session_id = '<id-from-above>'
ORDER BY created_at;
```

A clean run shows steady progress through the steward's loop with no
`result_status = 'error'` events tied to schema issues.

---

## Rollback procedure

If anything goes sideways post-migration:

1. **Restore from Step 1 backup.**
   - Railway-managed: dashboard → Backups tab → Restore.
   - `pg_dump`: `railway run --service postgres psql < backups/<timestamp>-pre-spec010.sql`

2. **Revert the code commit** (already merged on main):
   ```bash
   git revert f23352f
   git push origin main
   ```
   This restores code that doesn't reference `primary_entity_id` etc. — paired
   with the schema rollback, the system is back to pre-Apr-19 behavior.

3. Open an incident ticket with the captured logs and root-cause before any
   re-attempt.

---

## What this runbook leaves to a follow-up

- `services/data_steward.py` runs every 2 hours by default. We've left that
  cadence alone. If post-migration the steward generates new noise (different
  errors, not the SPEC-010 class), open a separate ticket. Don't bundle.
- The `MZ_STEWARD_ENABLED` / `MZ_SCHEDULER_ENABLED` env-var gates from the
  April 19 brainstorm doc are NOT yet implemented. Doing so is a Phase 1 task
  (swimlane B). For now the steward runs whether we like it or not — clean
  schema means it's no longer no-op'ing, which is the goal of this runbook.

---

## Sign-off

When all steps pass:

```
[YYYY-MM-DD HH:MM UTC] P0.1 closed.
- Backup taken: <timestamp / id>
- Migrations applied: 028, 029, 030, 031, 032, 033, 034, 035 (or subset)
- Live DB tests: 14/14 pass
- 4h log monitor: clean (zero schema-drift errors)
- Data Steward cycle: <session_id> completed at <timestamp>
- Verifier: <name>
```

Append to the Phase 0 closure log in SPEC-017.
