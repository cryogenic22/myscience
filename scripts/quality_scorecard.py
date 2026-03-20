"""Quality scorecard generator.

Phase 2.2: Produces a comprehensive quality report covering completeness,
cross-link density, source diversity, and freshness per entity type.

Usage:
    python -m scripts.quality_scorecard [--output reports/quality_scorecard.md]
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timezone

from config import config
from db import Database

logger = logging.getLogger(__name__)

# Required fields per entity type for completeness calculation
REQUIRED_FIELDS = {
    "drug": ["generic_name", "brand_name", "company_id", "therapeutic_area_id",
             "mechanism_id", "approval_date"],
    "company": ["name", "ticker", "country", "region", "market_cap_tier"],
    "trial": ["official_title", "sponsor_name", "status", "phase",
              "conditions", "start_date", "label"],
    "therapeutic_area": ["name", "mesh_id", "scope_note"],
    "mechanism": ["name", "mesh_id"],
    "article": ["title", "pmid", "journal", "publication_date", "mesh_terms"],
}

TABLE_MAP = {
    "drug": "drugs",
    "company": "companies",
    "trial": "clinical_trials",
    "therapeutic_area": "therapeutic_areas",
    "mechanism": "mechanisms_of_action",
    "article": "pubmed_articles",
}


def _table_exists(db: Database, table_name: str) -> bool:
    row = db.fetch_one(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s) AS exists_",
        [table_name],
    )
    return bool(row and row.get("exists_"))


def compute_completeness(db: Database) -> dict[str, dict]:
    """Compute per-field completeness for each entity type."""
    results = {}

    for etype, table in TABLE_MAP.items():
        fields = REQUIRED_FIELDS.get(etype, [])
        if not fields:
            continue

        total_row = db.fetch_one(f"SELECT COUNT(*) AS cnt FROM {table}")
        total = total_row["cnt"] if total_row else 0
        if total == 0:
            results[etype] = {"total": 0, "fields": {}, "overall": 0.0}
            continue

        field_scores = {}
        for field in fields:
            try:
                # Handle array fields
                row = db.fetch_one(
                    f"""
                    SELECT COUNT(*) AS filled FROM {table}
                    WHERE {field} IS NOT NULL
                      AND {field}::text != ''
                      AND {field}::text != '{{}}'
                    """
                )
                filled = row["filled"] if row else 0
                field_scores[field] = round(filled / total, 3)
            except Exception:
                field_scores[field] = 0.0

        overall = sum(field_scores.values()) / len(field_scores) if field_scores else 0.0
        results[etype] = {
            "total": total,
            "fields": field_scores,
            "overall": round(overall, 3),
        }

    return results


def compute_link_density(db: Database) -> dict[str, dict]:
    """Compute cross-link density per entity type."""
    results = {}

    for etype, table in TABLE_MAP.items():
        total_row = db.fetch_one(f"SELECT COUNT(*) AS cnt FROM {table}")
        total = total_row["cnt"] if total_row else 0
        if total == 0:
            results[etype] = {"total": 0, "linked": 0, "density": 0.0, "avg_links": 0.0}
            continue

        # Count entities with at least one link
        linked_row = db.fetch_one(
            """
            SELECT COUNT(DISTINCT entity_id) AS cnt
            FROM (
                SELECT source_entity_id AS entity_id FROM entity_links WHERE source_entity_type = %s
                UNION
                SELECT target_entity_id AS entity_id FROM entity_links WHERE target_entity_type = %s
            ) sub
            """,
            [etype, etype],
        )
        linked = linked_row["cnt"] if linked_row else 0

        # Average links per entity
        avg_row = db.fetch_one(
            """
            SELECT COALESCE(AVG(link_count), 0) AS avg_links
            FROM (
                SELECT entity_id, COUNT(*) AS link_count
                FROM (
                    SELECT source_entity_id AS entity_id FROM entity_links WHERE source_entity_type = %s
                    UNION ALL
                    SELECT target_entity_id AS entity_id FROM entity_links WHERE target_entity_type = %s
                ) sub
                GROUP BY entity_id
            ) counts
            """,
            [etype, etype],
        )
        avg_links = float(avg_row["avg_links"]) if avg_row else 0.0

        results[etype] = {
            "total": total,
            "linked": linked,
            "density": round(linked / total, 3) if total > 0 else 0.0,
            "avg_links": round(avg_links, 1),
        }

    return results


def compute_source_diversity(db: Database) -> dict[str, list[dict]]:
    """Count records per source_api per entity type."""
    results = {}

    for etype, table in TABLE_MAP.items():
        try:
            rows = db.fetch_all(
                f"""
                SELECT source_api, COUNT(*) AS cnt
                FROM {table}
                WHERE source_api IS NOT NULL
                GROUP BY source_api
                ORDER BY cnt DESC
                """
            )
            results[etype] = [{"source": r["source_api"], "count": r["cnt"]} for r in rows]
        except Exception:
            results[etype] = []

    return results


def compute_freshness(db: Database) -> dict[str, dict]:
    """Compute freshness per entity type."""
    results = {}

    for etype, table in TABLE_MAP.items():
        try:
            row = db.fetch_one(
                f"""
                SELECT MAX(retrieved_at) AS latest,
                       MIN(retrieved_at) AS earliest,
                       EXTRACT(EPOCH FROM (NOW() - MAX(retrieved_at))) / 86400 AS days_stale
                FROM {table}
                WHERE retrieved_at IS NOT NULL
                """
            )
            if row and row.get("latest"):
                results[etype] = {
                    "latest": row["latest"].isoformat() if hasattr(row["latest"], "isoformat") else str(row["latest"]),
                    "earliest": row["earliest"].isoformat() if row.get("earliest") and hasattr(row["earliest"], "isoformat") else None,
                    "days_stale": round(float(row["days_stale"]), 1) if row.get("days_stale") else None,
                }
            else:
                results[etype] = {"latest": None, "earliest": None, "days_stale": None}
        except Exception:
            results[etype] = {"latest": None, "earliest": None, "days_stale": None}

    return results


def compute_ta_coverage(db: Database) -> list[dict]:
    """Count linked entities per therapeutic area."""
    return db.fetch_all(
        """
        SELECT ta.name, COUNT(DISTINCT el.source_entity_id) AS linked_entities
        FROM therapeutic_areas ta
        LEFT JOIN entity_links el
          ON el.target_entity_id = ta.id::text
          AND el.target_entity_type = 'therapeutic_area'
        GROUP BY ta.name
        ORDER BY linked_entities DESC
        """
    )


def compute_quality_scores(db: Database) -> dict[str, dict]:
    """Get quality assessment scores per entity type."""
    if not _table_exists(db, "data_quality_results"):
        return {}

    rows = db.fetch_all(
        """
        SELECT entity_type,
               COUNT(DISTINCT entity_id) AS assessed,
               ROUND(AVG(score)::numeric, 3) AS avg_score,
               COUNT(*) FILTER (WHERE passed) AS passed,
               COUNT(*) FILTER (WHERE NOT passed) AS failed
        FROM data_quality_results
        GROUP BY entity_type
        """
    )
    return {
        r["entity_type"]: {
            "assessed": r["assessed"],
            "avg_score": float(r["avg_score"]) if r["avg_score"] else 0,
            "passed": r["passed"],
            "failed": r["failed"],
        }
        for r in rows
    }


def compute_overall_score(completeness: dict, links: dict, quality: dict) -> float:
    """Compute weighted overall quality score (0-1)."""
    scores = []

    # Completeness weight: 0.35
    comp_scores = [v["overall"] for v in completeness.values() if v["total"] > 0]
    if comp_scores:
        scores.append(("completeness", sum(comp_scores) / len(comp_scores), 0.35))

    # Link density weight: 0.30
    density_scores = [v["density"] for v in links.values() if v["total"] > 0]
    if density_scores:
        scores.append(("link_density", sum(density_scores) / len(density_scores), 0.30))

    # Quality rules weight: 0.35
    if quality:
        q_scores = [v["avg_score"] for v in quality.values() if v["assessed"] > 0]
        if q_scores:
            scores.append(("quality_rules", sum(q_scores) / len(q_scores), 0.35))

    if not scores:
        return 0.0

    total_weight = sum(s[2] for s in scores)
    return round(sum(s[1] * s[2] for s in scores) / total_weight, 3)


def generate_report(db: Database) -> str:
    """Generate markdown quality scorecard."""
    completeness = compute_completeness(db)
    links = compute_link_density(db)
    sources = compute_source_diversity(db)
    freshness = compute_freshness(db)
    ta_coverage = compute_ta_coverage(db)
    quality = compute_quality_scores(db)
    overall = compute_overall_score(completeness, links, quality)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        f"# Market Zero Quality Scorecard",
        f"",
        f"*Generated: {now}*",
        f"",
        f"## Overall Score: {overall:.1%}",
        f"",
        f"Target: ≥75%",
        f"",
    ]

    # Completeness
    lines.append("## Completeness by Entity Type")
    lines.append("")
    lines.append("| Entity Type | Total | Overall | Key Missing Fields |")
    lines.append("|---|---|---|---|")
    for etype, data in completeness.items():
        missing = [f for f, s in data["fields"].items() if s < 0.5]
        missing_str = ", ".join(missing[:4]) if missing else "none"
        lines.append(
            f"| {etype} | {data['total']} | {data['overall']:.0%} | {missing_str} |"
        )
    lines.append("")

    # Field-level detail
    lines.append("### Field-Level Completeness")
    lines.append("")
    for etype, data in completeness.items():
        if not data["fields"]:
            continue
        lines.append(f"**{etype}** ({data['total']} records)")
        lines.append("")
        for field, score in sorted(data["fields"].items(), key=lambda x: x[1]):
            bar = "█" * int(score * 20) + "░" * (20 - int(score * 20))
            lines.append(f"- `{field}`: {bar} {score:.0%}")
        lines.append("")

    # Link density
    lines.append("## Cross-Link Density")
    lines.append("")
    lines.append("| Entity Type | Total | Linked | Density | Avg Links |")
    lines.append("|---|---|---|---|---|")
    for etype, data in links.items():
        lines.append(
            f"| {etype} | {data['total']} | {data['linked']} | "
            f"{data['density']:.0%} | {data['avg_links']} |"
        )
    lines.append("")

    # TA coverage
    lines.append("## Therapeutic Area Coverage")
    lines.append("")
    lines.append("| Therapeutic Area | Linked Entities |")
    lines.append("|---|---|")
    for ta in ta_coverage:
        status = "✓" if ta["linked_entities"] > 0 else "✗"
        lines.append(f"| {status} {ta['name']} | {ta['linked_entities']} |")
    lines.append("")

    # Source diversity
    lines.append("## Source Diversity")
    lines.append("")
    for etype, srcs in sources.items():
        if srcs:
            lines.append(f"**{etype}**: " + ", ".join(
                f"{s['source']}({s['count']})" for s in srcs
            ))
    lines.append("")

    # Freshness
    lines.append("## Data Freshness")
    lines.append("")
    lines.append("| Entity Type | Latest Update | Days Stale |")
    lines.append("|---|---|---|")
    for etype, data in freshness.items():
        latest = data.get("latest", "—") or "—"
        if latest != "—":
            latest = latest[:10]
        stale = data.get("days_stale")
        stale_str = f"{stale:.0f}" if stale is not None else "—"
        lines.append(f"| {etype} | {latest} | {stale_str} |")
    lines.append("")

    # Quality rules
    if quality:
        lines.append("## Quality Rule Scores")
        lines.append("")
        lines.append("| Entity Type | Assessed | Avg Score | Passed | Failed |")
        lines.append("|---|---|---|---|---|")
        for etype, data in quality.items():
            lines.append(
                f"| {etype} | {data['assessed']} | {data['avg_score']:.0%} | "
                f"{data['passed']} | {data['failed']} |"
            )
        lines.append("")

    return "\n".join(lines)


def run(output_path: str | None = None) -> str:
    """Generate scorecard and optionally write to file."""
    db = Database(config.db.dsn)
    db.connect()

    try:
        report = generate_report(db)

        if output_path:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "w") as f:
                f.write(report)
            logger.info("Scorecard written to %s", output_path)

        return report
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Generate quality scorecard")
    parser.add_argument(
        "--output", "-o",
        default="reports/quality_scorecard.md",
        help="Output file path (default: reports/quality_scorecard.md)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    report = run(output_path=args.output)
    print(report)


if __name__ == "__main__":
    main()
