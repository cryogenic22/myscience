"""FAIRScorer — automated FAIR data quality snapshot computation and persistence.

Computes five FAIR dimensions:
  1. Entity completeness (per-type field fill rates)
  2. Link density (avg links per entity, normalized)
  3. Source diversity (% entities with 2+ distinct sources)
  4. Freshness (% records updated within 30 days)
  5. Resolution rate (% of unresolved-entity entries cleared)

Weighted overall score persisted to data_quality_snapshots for trending.

Usage:
    scorer = FAIRScorer(db)
    snapshot = scorer.compute()
    scorer.persist(snapshot)
"""

from __future__ import annotations

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Required fields per entity type for completeness checks
COMPLETENESS_FIELDS = {
    "drug": {
        "table": "drugs",
        "fields": ["generic_name", "company_id", "mechanism_id", "therapeutic_area_id", "approval_date"],
    },
    "company": {
        "table": "companies",
        "fields": ["name", "ticker", "cik", "country"],
    },
    "trial": {
        "table": "clinical_trials",
        "fields": ["official_title", "phase", "status", "sponsor_name", "start_date"],
    },
    "article": {
        "table": "pubmed_articles",
        "fields": ["title", "pmid", "journal", "publication_date"],
    },
}

# All entity tables for aggregate counts
ENTITY_TABLES = ["drugs", "companies", "clinical_trials", "pubmed_articles"]

# Weights for overall score
WEIGHTS = {
    "completeness": 0.25,
    "link_density": 0.20,
    "source_diversity": 0.15,
    "freshness": 0.25,
    "resolution_rate": 0.15,
}

# Target avg links per entity for normalization (10 = perfect density)
LINK_DENSITY_TARGET = 10.0


class FAIRScorer:
    """Computes and persists FAIR data quality snapshots."""

    def __init__(self, db):
        self.db = db

    # ── Public API ──

    def compute(self) -> dict:
        """Compute all FAIR dimensions and return scored snapshot."""
        completeness = self._entity_completeness()
        density = self._link_density()
        diversity = self._source_diversity()
        freshness = self._freshness()
        resolution = self._resolution_rate()
        total_records = self._total_records()
        total_links = self._total_links()

        # Weighted overall score
        comp_values = list(completeness.values())
        avg_completeness = sum(comp_values) / len(comp_values) if comp_values else 0.0

        overall = (
            WEIGHTS["completeness"] * avg_completeness
            + WEIGHTS["link_density"] * density
            + WEIGHTS["source_diversity"] * diversity
            + WEIGHTS["freshness"] * freshness
            + WEIGHTS["resolution_rate"] * resolution
        )

        return {
            "overall_score": round(overall, 4),
            "entity_completeness": completeness,
            "link_density": round(density, 4),
            "source_diversity": round(diversity, 4),
            "freshness": round(freshness, 4),
            "resolution_rate": round(resolution, 4),
            "total_records": total_records,
            "total_links": total_links,
        }

    def persist(self, snapshot: dict) -> None:
        """Save snapshot to data_quality_snapshots table."""
        details_json = json.dumps(snapshot)

        self.db.execute(
            """INSERT INTO data_quality_snapshots
               (overall_score, entity_completeness, link_density, source_diversity,
                freshness, resolution_rate, total_records, total_links, details)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            [
                snapshot["overall_score"],
                json.dumps(snapshot["entity_completeness"]),
                snapshot["link_density"],
                snapshot["source_diversity"],
                snapshot["freshness"],
                snapshot["resolution_rate"],
                snapshot["total_records"],
                snapshot["total_links"],
                details_json,
            ],
        )

    def latest(self) -> Optional[dict]:
        """Return the most recent snapshot, or None."""
        row = self.db.fetch_one(
            """SELECT * FROM data_quality_snapshots
               ORDER BY created_at DESC
               LIMIT 1"""
        )
        return dict(row) if row else None

    def trend(self, n: int = 5) -> list[dict]:
        """Return the last N snapshots for trend analysis."""
        rows = self.db.fetch_all(
            """SELECT * FROM data_quality_snapshots
               ORDER BY created_at DESC
               LIMIT %s""",
            [n],
        )
        return rows

    # ── Private dimension calculators ──

    def _entity_completeness(self) -> dict[str, float]:
        """Compute per-type completeness as avg field fill rate (0.0 - 1.0)."""
        result = {}

        for etype, spec in COMPLETENESS_FIELDS.items():
            table = spec["table"]
            fields = spec["fields"]

            row = self.db.fetch_one(f"SELECT COUNT(*) AS cnt FROM {table}")
            total = row["cnt"] if row else 0

            if total == 0:
                result[etype] = 0.0
                continue

            field_scores = []
            for field_name in fields:
                try:
                    row = self.db.fetch_one(
                        f"""SELECT COUNT(*) AS filled FROM {table}
                            WHERE {field_name} IS NOT NULL
                              AND {field_name}::text != ''"""
                    )
                    filled = row["filled"] if row else 0
                    field_scores.append(filled / total)
                except Exception:
                    field_scores.append(0.0)

            avg_score = sum(field_scores) / len(field_scores) if field_scores else 0.0
            result[etype] = round(avg_score, 4)

        return result

    def _link_density(self) -> float:
        """Compute avg links per entity, normalized to 0.0-1.0.

        Normalization: min(avg_links / LINK_DENSITY_TARGET, 1.0)
        """
        total_entities = self._total_records()
        if total_entities == 0:
            return 0.0

        total_links = self._total_links()
        avg_links = total_links / total_entities
        return round(min(avg_links / LINK_DENSITY_TARGET, 1.0), 4)

    def _source_diversity(self) -> float:
        """Fraction of entities sourced from 2+ distinct source_api values.

        Queries each entity table for entities with multiple sources.
        Returns 0.0-1.0.
        """
        try:
            row = self.db.fetch_one(
                """SELECT COUNT(*) AS multi, SUM(1) AS total
                   FROM (
                       SELECT entity_id
                       FROM (
                           SELECT source_entity_id AS entity_id, source_entity_type AS etype
                           FROM entity_links
                           WHERE link_type != 'COMPETES_WITH'
                           UNION ALL
                           SELECT target_entity_id, target_entity_type
                           FROM entity_links
                           WHERE link_type != 'COMPETES_WITH'
                       ) sub
                       GROUP BY entity_id
                       HAVING COUNT(DISTINCT etype) >= 2
                   ) multi_source"""
            )
            if row and row.get("total") and row.get("multi"):
                total_entities = self._total_records()
                if total_entities == 0:
                    return 0.0
                return round(min(row["multi"] / total_entities, 1.0), 4)
        except Exception:
            pass
        return 0.0

    def _freshness(self) -> float:
        """Fraction of records with retrieved_at within the last 30 days.

        Returns 0.0-1.0.
        """
        total = 0
        recent = 0

        for table in ENTITY_TABLES:
            try:
                row = self.db.fetch_one(
                    f"""SELECT
                            COUNT(*) AS total,
                            COUNT(*) FILTER (
                                WHERE retrieved_at >= NOW() - INTERVAL '30 days'
                            ) AS recent
                        FROM {table}
                        WHERE retrieved_at IS NOT NULL"""
                )
                if row:
                    total += row.get("total", 0) or 0
                    recent += row.get("recent", 0) or 0
            except Exception:
                pass

        if total == 0:
            return 0.0
        return round(recent / total, 4)

    def _resolution_rate(self) -> float:
        """Fraction of unresolved_entities that have been resolved.

        Returns 1.0 if no unresolved entries exist (perfect).
        """
        try:
            total_row = self.db.fetch_one(
                "SELECT COUNT(*) AS cnt FROM unresolved_entities"
            )
            total = total_row["cnt"] if total_row else 0

            if total == 0:
                return 1.0

            unresolved_row = self.db.fetch_one(
                "SELECT COUNT(*) AS cnt FROM unresolved_entities WHERE resolved = FALSE"
            )
            unresolved = unresolved_row["cnt"] if unresolved_row else 0

            return round((total - unresolved) / total, 4)
        except Exception:
            return 1.0

    def _total_records(self) -> int:
        """Sum of records across all entity tables."""
        total = 0
        for table in ENTITY_TABLES:
            try:
                row = self.db.fetch_one(f"SELECT COUNT(*) AS cnt FROM {table}")
                total += row["cnt"] if row else 0
            except Exception:
                pass
        return total

    def _total_links(self) -> int:
        """Total number of entity links."""
        try:
            row = self.db.fetch_one("SELECT COUNT(*) AS cnt FROM entity_links")
            return row["cnt"] if row else 0
        except Exception:
            return 0
