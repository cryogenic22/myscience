# SPEC-010: Schema Drift Cleanup

*Date: 19 April 2026 (revised after schema audit)*
*Priority: P0 (blocks SPEC_011, SPEC_012)*
*Effort: 0.5 day (smaller than originally scoped)*

---

## Revision Note

Initial draft assumed all the missing tables / columns needed new migrations. After auditing `schema/migrations/`, the truth is more nuanced:

- `agent_sessions` and `agent_events` are **already created by migration 029** — the crash logs reflect production not having that migration applied (which the Railway recovery / restart now fixes when `migrate.py` runs)
- `steward_actions.action_details` exists in migration 021 but the dossier handler queries `details` — **code-side fix**
- `market_events.primary_entity_id` doesn't exist (migration 026 added `primary_entity_type` + `primary_entity_name` only) — **needs ONE new column**
- `clinical_trials.title` exists; quality scorecard queries `label` — **code-side fix**
- `etl_runs.source_name` exists (migration 001:154); steward queries `source_type` — **code-side fix**
- `MIN(uuid)` is a code bug (PG has no min for uuid) — **code-side fix**

Net: the ratio of schema fixes to code fixes flipped. Previous draft proposed migration 015; that number is taken (`015_mechanism_hierarchy.sql`). Use **migration 032** for the one column we actually need.

## Goal

Reconcile the production schema with what services reference, so that the Data Steward stops no-op'ing every 2 hours and the dossier handler returns recent actions / events again.

## Why This Matters

From `specs/logs_rough.md`:

| Code Reference | Actual Schema | Fix Type |
|----------------|--------------|----------|
| `agent_sessions` table | Created by migration 029 | Apply migration in prod |
| `agent_events` table | Created by migration 029 | Apply migration in prod |
| `etl_runs.source_type` | Column is `source_name` (migration 001) | Code fix |
| `steward_actions.details` | Column is `action_details` (migration 021) | Code fix |
| `market_events.primary_entity_id` | Doesn't exist (migration 026 only added `_type` and `_name`) | New migration 032 |
| `clinical_trials.label` | Column is `title` (migration 001) | Code fix |
| `MIN(uuid)` in dedup | UUID type has no `min()` | Code fix |

Net effect today: Data Steward is a no-op, dossier responses miss the events/actions section, log noise hides real issues.

## Tests First

Create `tests/test_schema_drift_fix.py` with these test functions, all of which must FAIL before any implementation:

```python
"""Verify the production schema matches what the code expects."""
import pytest
from db import Database
from config import config

@pytest.fixture(scope="module")
def db():
    return Database(config.db.dsn)

def test_agent_sessions_table_exists(db):
    """SPEC_010: agent_sessions table must exist for Data Steward."""
    rows = db.fetch_all(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_name = 'agent_sessions'"
    )
    assert len(rows) == 1

def test_agent_sessions_has_required_columns(db):
    rows = db.fetch_all(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'agent_sessions'"
    )
    cols = {r["column_name"] for r in rows}
    required = {
        "id", "agent_type", "goal", "status", "total_steps",
        "current_step", "checkpoint_data", "last_checkpoint",
        "started_at", "completed_at",
    }
    assert required.issubset(cols), f"missing: {required - cols}"

def test_agent_events_table_exists(db):
    rows = db.fetch_all(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_name = 'agent_events'"
    )
    assert len(rows) == 1

def test_agent_events_has_required_columns(db):
    rows = db.fetch_all(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'agent_events'"
    )
    cols = {r["column_name"] for r in rows}
    required = {
        "id", "session_id", "event_type", "agent_type",
        "tool_name", "trust_tier", "args_hash",
        "result_status", "metadata", "created_at",
    }
    assert required.issubset(cols)

def test_steward_actions_details_column(db):
    rows = db.fetch_all(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'steward_actions' AND column_name = 'details'"
    )
    assert len(rows) == 1

def test_market_events_primary_entity_id_column(db):
    rows = db.fetch_all(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'market_events' "
        "AND column_name = 'primary_entity_id'"
    )
    assert len(rows) == 1

def test_etl_runs_uses_source_name_not_source_type(db):
    """Confirm the actual column name and that code uses it."""
    rows = db.fetch_all(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'etl_runs' "
        "AND column_name IN ('source_name', 'source_type')"
    )
    cols = {r["column_name"] for r in rows}
    assert "source_name" in cols, "etl_runs must have source_name"

def test_steward_uses_correct_column_name():
    """Static check: steward code must reference source_name, not source_type."""
    from pathlib import Path
    src = Path("services/data_steward.py").read_text()
    # The stale-source query must use source_name
    assert "source_type" not in src or "source_name" in src, (
        "steward must query etl_runs.source_name, not source_type"
    )

def test_steward_dedup_does_not_use_min_uuid():
    """Static check: dedup query must not call MIN(uuid) — PG has no such function."""
    from pathlib import Path
    src = Path("services/data_steward.py").read_text()
    # If dedup logic exists in this file, it must not use MIN(id) on uuid
    if "DELETE FROM entity_links" in src:
        # Acceptable patterns: MIN(id::text) cast, ARRAY_AGG ORDER BY, DISTINCT ON
        assert "MIN(id)" not in src, (
            "Cannot use MIN(uuid) — cast to text or use DISTINCT ON"
        )

def test_clinical_trials_completeness_query_uses_existing_column():
    """The trial completeness scorecard must reference an existing column."""
    rows = Database(config.db.dsn).fetch_all(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'clinical_trials'"
    )
    cols = {r["column_name"] for r in rows}
    # Choose ONE of: brief_title, official_title, title — whichever exists
    assert any(c in cols for c in ("brief_title", "official_title", "title")), (
        "clinical_trials must have at least one title column"
    )
```

Also add a regression test that a Data Steward cycle runs cleanly:

```python
def test_data_steward_cycle_runs_without_schema_errors(db, caplog):
    """An end-to-end steward cycle must produce zero ERROR-level logs about missing schema."""
    from services.data_steward import DataSteward, StewardConfig
    steward = DataSteward(db, StewardConfig(max_iterations=1, dry_run=True, skip_ai=True))
    with caplog.at_level("ERROR"):
        steward.run_loop()
    schema_errors = [
        r for r in caplog.records
        if "does not exist" in r.message
        or "min(uuid)" in r.message.lower()
    ]
    assert schema_errors == [], f"steward emitted schema errors: {schema_errors}"
```

**Run them**: `python -m pytest tests/test_schema_drift_fix.py -v`. All must FAIL.

## Implementation Plan

### Step 1 — Create migration `schema/migrations/032_market_events_primary_entity_id.sql`

Single new column, idempotent:

```sql
-- 032_market_events_primary_entity_id.sql
-- Adds primary_entity_id to market_events. Migration 026 added _type and _name
-- but not the id; the dossier handler at api/routes/catalog.py:2747 queries
-- WHERE primary_entity_id = ... so this column is required.

ALTER TABLE market_events
    ADD COLUMN IF NOT EXISTS primary_entity_id TEXT;

CREATE INDEX IF NOT EXISTS idx_market_events_primary_entity_id
    ON market_events (primary_entity_id, primary_entity_type)
    WHERE primary_entity_id IS NOT NULL;
```

### Step 2 — Fix code-side column name mismatches

The bulk of the work. Each fix below is a single edit:

**(a) `etl_runs.source_type` → `source_name`** (in steward signal collector)

The query is:
```sql
SELECT source_type, MAX(finished_at) AS last_run
FROM etl_runs
WHERE status = 'completed'
GROUP BY source_type
HAVING MAX(finished_at) < NOW() - INTERVAL '14 days'
```
Change `source_type` → `source_name` (3 occurrences in this query).

**(b) `steward_actions.details` → `action_details`** (in dossier handler, `api/routes/catalog.py` ≈ line 2738+)

The query is:
```sql
SELECT action_type, details, status, completed_at
FROM steward_actions
WHERE entity_type = 'drug' AND entity_id = '...'
```
Change `details` → `action_details`. (Or alternatively, alias in SQL: `action_details AS details`.)

**(c) `clinical_trials.label` → `title`** (in quality scorecard, likely `scripts/quality_scorecard.py`)

The query is:
```sql
SELECT COUNT(*) AS filled FROM clinical_trials
WHERE label IS NOT NULL AND label::text != '' AND label::text != '{}'
```
Change all `label` → `title`. The simpler `IS NOT NULL` check suffices since `title` is `TEXT NOT NULL` per migration 001.

**(d) `MIN(id)` on uuid in dedup query** — rewrite using `DISTINCT ON`:

```sql
-- Replace the broken dedup:
WITH dupes AS (
    SELECT DISTINCT ON (source_entity_id, target_entity_id, link_type)
        id AS keep_id,
        source_entity_id, target_entity_id, link_type
    FROM entity_links
    ORDER BY source_entity_id, target_entity_id, link_type, created_at ASC
)
DELETE FROM entity_links el
USING dupes d
WHERE el.source_entity_id = d.source_entity_id
  AND el.target_entity_id = d.target_entity_id
  AND el.link_type = d.link_type
  AND el.id != d.keep_id;
```

### Step 3 — Verify migration 029 has been applied in production

Migration `029_agent_sessions.sql` already exists locally but the crash logs show `relation "agent_sessions" does not exist` — meaning it never got applied to the production DB. With the DB now restored, run:

```bash
railway run python migrate.py
```

`migrate.py` should be idempotent — it tracks applied migrations and skips ones already in production. After running, verify both tables exist:
```sql
SELECT table_name FROM information_schema.tables
WHERE table_name IN ('agent_sessions', 'agent_events');
-- expect 2 rows
```

### Step 4 — Apply migration 032

Same `migrate.py` run from Step 3 will pick up 032. Verify:
```sql
SELECT column_name FROM information_schema.columns
WHERE table_name = 'market_events' AND column_name = 'primary_entity_id';
-- expect 1 row
```

### Step 5 — Re-run the test suite

```bash
python -m pytest tests/test_schema_drift_fix.py -v
python -m pytest tests/ -v
```

All schema_drift_fix tests must pass. No existing tests may regress.

## Acceptance Criteria

- [ ] All tests in `tests/test_schema_drift_fix.py` pass
- [ ] Existing test suite has zero regressions (180+ tests still pass)
- [ ] Migration 015 applied to production via `python migrate.py`
- [ ] After deployment, monitor logs for 4 hours: zero errors matching `relation "agent_sessions"` or `relation "agent_events"` or `column "source_type"` or `column "details"` or `MIN(uuid)`
- [ ] One Data Steward cycle completes successfully (visible in `agent_sessions` with `status='completed'`)

## Rollout / Rollback

**Rollout:**
1. Run migration locally first: `MZ_DB_PORT=5432 python migrate.py`
2. Run full test suite locally
3. Push to main → Railway auto-deploys
4. Apply migration on Railway: `railway run python migrate.py`
5. Monitor Railway logs for 4 hours

**Rollback:**
- Migration is additive (`CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`). Safe to re-run.
- If code changes need rollback: `git revert <commit>` — schema additions don't break old code that didn't reference them.

## Out of Scope

- Wiring the AutonomousResearchAgent (separate task — has its own existing tests)
- Adding feedback loops to steward (deferred — current sprint is about removing errors, not adding features)
