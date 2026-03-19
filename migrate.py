"""
Apply SQL migrations to the Market-Zero database.

Usage:
    python migrate.py              # Apply all pending migrations
    python migrate.py --check      # Check which migrations have been applied
    python migrate.py --reset      # Drop and recreate all tables (dev only)
"""

from __future__ import annotations

import os
import sys
import logging

from config import config
from db import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "schema", "migrations")


def get_migration_files() -> list[tuple[str, str]]:
    """Return sorted list of (filename, full_path) for all .sql files."""
    files = []
    for f in sorted(os.listdir(MIGRATIONS_DIR)):
        if f.endswith(".sql"):
            files.append((f, os.path.join(MIGRATIONS_DIR, f)))
    return files


def ensure_migrations_table(db: Database) -> None:
    """Create the schema_migrations tracking table if it doesn't exist."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename TEXT PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT NOW()
        )
    """)


def get_applied_migrations(db: Database) -> set[str]:
    """Return set of migration filenames already applied."""
    rows = db.fetch_all("SELECT filename FROM schema_migrations ORDER BY filename")
    return {row["filename"] for row in rows}


def apply_migration(db: Database, filename: str, filepath: str) -> None:
    """Apply a single migration file."""
    logger.info("Applying migration: %s", filename)
    with open(filepath, "r", encoding="utf-8") as f:
        sql = f.read()

    db.execute_script(sql)
    db.execute(
        "INSERT INTO schema_migrations (filename) VALUES (%s)",
        [filename],
    )
    logger.info("Applied: %s", filename)


def run_migrations(db: Database) -> int:
    """Apply all pending migrations. Returns count of migrations applied."""
    ensure_migrations_table(db)
    applied = get_applied_migrations(db)
    migrations = get_migration_files()

    count = 0
    for filename, filepath in migrations:
        if filename in applied:
            logger.info("Already applied: %s", filename)
            continue

        apply_migration(db, filename, filepath)
        count += 1

    if count == 0:
        logger.info("No pending migrations.")
    else:
        logger.info("Applied %d migration(s).", count)

    return count


def check_migrations(db: Database) -> None:
    """Show migration status."""
    ensure_migrations_table(db)
    applied = get_applied_migrations(db)
    migrations = get_migration_files()

    for filename, _ in migrations:
        status = "APPLIED" if filename in applied else "PENDING"
        print(f"  [{status}] {filename}")


def reset_database(db: Database) -> None:
    """Drop all tables and reapply. Development use only."""
    logger.warning("RESETTING DATABASE -- dropping all tables!")

    # Drop in reverse dependency order
    tables = [
        "schema_migrations",
        "deep_research_jobs",
        "chat_sessions",
        "entity_tags",
        "unresolved_entities",
        "entity_aliases",
        "entity_links",
        "investigators",
        "trial_locations",
        "trial_outcomes",
        "regulatory_milestones",
        "patents",
        "knowledge_chunks",
        "pubmed_articles",
        "market_events",
        "clinical_trials",
        "drugs",
        "companies",
        "mechanisms_of_action",
        "therapeutic_areas",
        "etl_runs",
    ]
    for table in tables:
        db.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

    logger.info("All tables dropped. Re-applying migrations...")
    run_migrations(db)


def main():
    db = Database(config.db.dsn)
    db.connect()

    try:
        if "--check" in sys.argv:
            check_migrations(db)
        elif "--reset" in sys.argv:
            confirm = input("This will DROP ALL TABLES. Type 'yes' to confirm: ")
            if confirm.strip().lower() == "yes":
                reset_database(db)
            else:
                print("Aborted.")
        else:
            run_migrations(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
