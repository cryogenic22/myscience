"""Schema introspector — builds compact schema descriptions from DomainPack.

Used to provide LLMs with table/column/relationship context for SQL generation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from db import Database
from domain.schema import DomainPack

logger = logging.getLogger(__name__)


@dataclass
class JoinPath:
    """A join path between two tables."""
    tables: list[str]
    join_conditions: list[str]
    description: str


class SchemaIntrospector:
    """Reads DomainPack + information_schema to produce LLM-ready schema text."""

    def __init__(self, domain_pack: DomainPack, db: Database):
        self._pack = domain_pack
        self._db = db
        self._cached_description: Optional[str] = None
        self._column_cache: dict[str, list[dict]] = {}

    def get_schema_description(self) -> str:
        """Build a compact schema description for LLM prompts. Cached after first call."""
        if self._cached_description is not None:
            return self._cached_description

        parts = []

        # Table descriptions from domain pack entities
        parts.append("Tables:")
        entity_tables = set()
        for entity in self._pack.entities.values():
            table = entity.table_name
            entity_tables.add(table)
            columns = self._get_columns(table)
            col_descs = []
            for col in columns:
                desc = f"{col['column_name']} {col['data_type']}"
                if col["column_name"] == entity.id_column:
                    desc += " PK"
                col_descs.append(desc)
            col_str = ", ".join(col_descs) if col_descs else "..."
            parts.append(f"  - {table} ({col_str})")

        # entity_links table (always present) — IDs stored as TEXT, not UUID
        el_columns = self._get_columns("entity_links")
        if el_columns:
            col_descs = [f"{c['column_name']} {c['data_type']}" for c in el_columns]
            parts.append(f"  - entity_links ({', '.join(col_descs)})")
        else:
            parts.append("  - entity_links (id uuid PK, source_entity_id text, source_entity_type text, "
                          "target_entity_id text, target_entity_type text, link_type text, "
                          "confidence double precision, metadata jsonb)")

        # Relationships from link rules
        parts.append("")
        parts.append("Relationships (entity_links table):")
        for rule in self._pack.link_rules:
            parts.append(f"  - {rule.source_entity} --[{rule.link_type}]--> {rule.target_entity}")

        # Materialized views (try to discover)
        views = self._get_materialized_views()
        if views:
            parts.append("")
            parts.append("Materialized views:")
            for view in views:
                parts.append(f"  - {view}")

        # Join guidance
        parts.append("")
        parts.append("Join patterns:")
        parts.append("  - Direct FK: drugs.company_id = companies.id, drugs.therapeutic_area_id = therapeutic_areas.id, "
                      "drugs.mechanism_id = mechanisms_of_action.id, clinical_trials.drug_id = drugs.id")
        parts.append("  - Via entity_links (entity_links IDs are TEXT, entity table IDs may be UUID — ALWAYS cast with ::text):")
        parts.append("    company→trial: JOIN entity_links el ON el.source_entity_id = companies.id::text "
                      "AND el.link_type = 'SPONSORS' AND el.target_entity_id = clinical_trials.id")
        parts.append("    drug→literature: JOIN entity_links el ON el.target_entity_id = drugs.id::text "
                      "AND el.link_type = 'EVIDENCE_FOR' AND el.source_entity_id = pubmed_articles.id::text")
        parts.append("  - CRITICAL: entity_links.source_entity_id and target_entity_id are TEXT. "
                      "When joining to UUID id columns, ALWAYS cast: table.id::text = entity_links.source_entity_id")
        parts.append("  - clinical_trials.id is TEXT. All other entity tables have UUID id columns.")
        parts.append("  - clinical_trials.status values are UPPERCASE: 'RECRUITING', 'ACTIVE_NOT_RECRUITING', 'COMPLETED', 'TERMINATED', 'WITHDRAWN', 'NOT_YET_RECRUITING', 'SUSPENDED'")

        # Important filters
        parts.append("")
        parts.append("Important:")
        parts.append("  - Use WHERE record_status != 'superseded' on entity tables when available")
        parts.append("  - entity_links.link_type values are uppercase: OWNS, INVESTIGATES, EVIDENCE_FOR, etc.")
        parts.append("  - Always use ::uuid cast when comparing UUID columns with text parameters")
        parts.append("  - For 'active' trials, use: status IN ('RECRUITING', 'ACTIVE_NOT_RECRUITING')")
        parts.append("  - IMPORTANT: ALL clinical_trials.status values are UPPERCASE with underscores, never mixed case. "
                      "Examples: 'RECRUITING' (not 'Recruiting'), 'COMPLETED' (not 'Completed'), "
                      "'ACTIVE_NOT_RECRUITING' (not 'Active, not recruiting')")

        self._cached_description = "\n".join(parts)
        return self._cached_description

    def get_table_names(self) -> set[str]:
        """Return all table names the agent is allowed to query."""
        tables = {e.table_name for e in self._pack.entities.values()}
        tables.add("entity_links")
        # Add known views
        tables.update(self._get_materialized_views())
        return tables

    def get_joinable_paths(self, src_table: str, tgt_table: str) -> list[JoinPath]:
        """Find join paths between two tables via FKs or entity_links."""
        paths = []

        # Direct FK join (entity tables that have FK columns to other entity tables)
        src_cols = self._get_columns(src_table)
        for col in src_cols:
            col_name = col["column_name"]
            # Convention: FK columns end with _id and match a table name
            if col_name.endswith("_id") and col_name != "id":
                ref_table = self._guess_fk_table(col_name)
                if ref_table == tgt_table:
                    paths.append(JoinPath(
                        tables=[src_table, tgt_table],
                        join_conditions=[f"{src_table}.{col_name} = {tgt_table}.id"],
                        description=f"Direct FK: {src_table}.{col_name} -> {tgt_table}.id",
                    ))

        # Via entity_links
        src_entity = self._table_to_entity(src_table)
        tgt_entity = self._table_to_entity(tgt_table)
        if src_entity and tgt_entity:
            for rule in self._pack.link_rules:
                if (rule.source_entity == src_entity and rule.target_entity == tgt_entity) or \
                   (rule.source_entity == tgt_entity and rule.target_entity == src_entity):
                    paths.append(JoinPath(
                        tables=[src_table, "entity_links", tgt_table],
                        join_conditions=[
                            f"{src_table}.id = entity_links.source_entity_id AND "
                            f"entity_links.link_type = '{rule.link_type}' AND "
                            f"entity_links.target_entity_id = {tgt_table}.id"
                        ],
                        description=f"Via entity_links: {rule.source_entity} --[{rule.link_type}]--> {rule.target_entity}",
                    ))

        return paths

    def _get_columns(self, table: str) -> list[dict]:
        """Fetch column info from information_schema. Cached per table."""
        if table in self._column_cache:
            return self._column_cache[table]

        try:
            rows = self._db.fetch_all(
                """SELECT column_name, data_type
                   FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = %s
                   ORDER BY ordinal_position""",
                [table],
            )
            self._column_cache[table] = rows or []
        except Exception:
            logger.debug("Could not fetch columns for %s", table)
            self._column_cache[table] = []

        return self._column_cache[table]

    def _get_materialized_views(self) -> list[str]:
        """Discover materialized views in the public schema."""
        try:
            rows = self._db.fetch_all(
                """SELECT matviewname FROM pg_matviews
                   WHERE schemaname = 'public'
                   ORDER BY matviewname"""
            )
            return [r["matviewname"] for r in (rows or [])]
        except Exception:
            return []

    def _guess_fk_table(self, col_name: str) -> Optional[str]:
        """Guess the referenced table from a FK column name like 'company_id' -> 'companies'."""
        entity_map = self._pack.get_entity_table_map()
        # Strip _id suffix to get entity name
        base = col_name.rsplit("_id", 1)[0]
        return entity_map.get(base)

    def _table_to_entity(self, table: str) -> Optional[str]:
        """Map table name back to entity name."""
        for entity in self._pack.entities.values():
            if entity.table_name == table:
                return entity.name
        return None
