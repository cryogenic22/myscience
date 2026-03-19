"""
Seed quality rules, generate dataset catalog, and run initial quality assessment.

Usage: python seed_quality_and_catalog.py
"""

import json
import logging

from config import config
from db import Database
from integration.data_quality import DataQualityEngine
from integration.dataset_catalog import DatasetCatalog

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
logger = logging.getLogger(__name__)


def seed_quality_rules(db):
    """Insert configurable quality rules for each entity type."""
    rules = [
        # ── Drugs ──
        {
            "entity_type": "drug",
            "rule_name": "drug_completeness_core",
            "rule_type": "completeness",
            "rule_config": {"fields": ["generic_name", "company_id", "therapeutic_area_id", "approval_date"], "threshold": 0.5},
            "severity": "warning",
        },
        {
            "entity_type": "drug",
            "rule_name": "drug_embedding_coverage",
            "rule_type": "embedding_coverage",
            "rule_config": {"embedding_column": "molecule_embedding"},
            "severity": "warning",
        },
        {
            "entity_type": "drug",
            "rule_name": "drug_cross_source",
            "rule_type": "cross_source",
            "rule_config": {"min_sources": 2},
            "severity": "info",
        },
        {
            "entity_type": "drug",
            "rule_name": "drug_freshness",
            "rule_type": "freshness",
            "rule_config": {"max_age_days": 180},
            "severity": "info",
        },
        {
            "entity_type": "drug",
            "rule_name": "drug_company_link",
            "rule_type": "consistency",
            "rule_config": {"check": "drug_company_link"},
            "severity": "warning",
        },

        # ── Trials ──
        {
            "entity_type": "trial",
            "rule_name": "trial_completeness_core",
            "rule_type": "completeness",
            "rule_config": {"fields": ["phase", "status", "sponsor_name", "conditions", "interventions", "start_date"], "threshold": 0.7},
            "severity": "warning",
        },
        {
            "entity_type": "trial",
            "rule_name": "trial_drug_link",
            "rule_type": "consistency",
            "rule_config": {"check": "trial_drug_link"},
            "severity": "warning",
        },
        {
            "entity_type": "trial",
            "rule_name": "trial_status_date",
            "rule_type": "consistency",
            "rule_config": {"check": "trial_status_date"},
            "severity": "info",
        },
        {
            "entity_type": "trial",
            "rule_name": "trial_embedding_coverage",
            "rule_type": "embedding_coverage",
            "rule_config": {"embedding_column": "protocol_embedding"},
            "severity": "warning",
        },
        {
            "entity_type": "trial",
            "rule_name": "trial_freshness",
            "rule_type": "freshness",
            "rule_config": {"max_age_days": 90},
            "severity": "info",
        },

        # ── Companies ──
        {
            "entity_type": "company",
            "rule_name": "company_completeness_core",
            "rule_type": "completeness",
            "rule_config": {"fields": ["name", "cik", "ticker", "country"], "threshold": 0.5},
            "severity": "warning",
        },
        {
            "entity_type": "company",
            "rule_name": "company_freshness",
            "rule_type": "freshness",
            "rule_config": {"max_age_days": 365},
            "severity": "info",
        },

        # ── Literature ──
        {
            "entity_type": "literature",
            "rule_name": "article_completeness_core",
            "rule_type": "completeness",
            "rule_config": {"fields": ["title", "abstract", "pmid", "journal", "publication_date", "drug_id"], "threshold": 0.7},
            "severity": "warning",
        },
        {
            "entity_type": "literature",
            "rule_name": "article_embedding_coverage",
            "rule_type": "embedding_coverage",
            "rule_config": {"embedding_column": "abstract_embedding"},
            "severity": "warning",
        },

        # ── Events ──
        {
            "entity_type": "event",
            "rule_name": "event_completeness_core",
            "rule_type": "completeness",
            "rule_config": {"fields": ["event_type", "description", "event_date", "drug_id"], "threshold": 0.7},
            "severity": "warning",
        },
        {
            "entity_type": "event",
            "rule_name": "event_drug_link",
            "rule_type": "consistency",
            "rule_config": {"check": "trial_drug_link"},
            "severity": "info",
        },

        # ── NEW: Company enrichment rules ──
        {
            "entity_type": "company",
            "rule_name": "company_embedding_coverage",
            "rule_type": "embedding_coverage",
            "rule_config": {"embedding_column": "strategy_embedding"},
            "severity": "warning",
        },
        {
            "entity_type": "company",
            "rule_name": "company_cross_source",
            "rule_type": "cross_source",
            "rule_config": {"min_sources": 1},
            "severity": "info",
        },
        {
            "entity_type": "company",
            "rule_name": "company_completeness_enrichment",
            "rule_type": "completeness",
            "rule_config": {"fields": ["name", "cik", "ticker", "country", "sic_code", "strategy_embedding"], "threshold": 0.5},
            "severity": "warning",
        },

        # ── NEW: Drug extended completeness + consistency ──
        {
            "entity_type": "drug",
            "rule_name": "drug_completeness_extended",
            "rule_type": "completeness",
            "rule_config": {
                "fields": ["generic_name", "brand_name", "mechanism_id", "nda_number",
                           "approval_date", "dosage_form", "route", "company_id"],
                "threshold": 0.4,
            },
            "severity": "warning",
        },
        {
            "entity_type": "drug",
            "rule_name": "drug_ta_linkage",
            "rule_type": "consistency",
            "rule_config": {"check": "drug_ta_link"},
            "severity": "warning",
        },
        {
            "entity_type": "drug",
            "rule_name": "drug_source_consistency",
            "rule_type": "naming_consistency",
            "rule_config": {
                "column": "source_authority",
                "allowed": ["clinical_trials_gov", "fda_orange_book", "fda_shortages",
                            "sec_edgar", "pubmed", "mesh_ontology", "openfda_faers",
                            "openfda_labels", "pmc", "user_document", "user_url", "backfill"],
            },
            "severity": "error",
        },

        # ── NEW: Article freshness + cross-source ──
        {
            "entity_type": "literature",
            "rule_name": "article_freshness",
            "rule_type": "freshness",
            "rule_config": {"max_age_days": 365},
            "severity": "info",
        },
        {
            "entity_type": "literature",
            "rule_name": "article_cross_source",
            "rule_type": "cross_source",
            "rule_config": {"min_sources": 1},
            "severity": "info",
        },

        # ── NEW: Event freshness ──
        {
            "entity_type": "event",
            "rule_name": "event_freshness",
            "rule_type": "freshness",
            "rule_config": {"max_age_days": 90},
            "severity": "info",
        },
    ]

    inserted = 0
    for rule in rules:
        try:
            db.execute(
                """
                INSERT INTO data_quality_rules (entity_type, rule_name, rule_type, rule_config, severity)
                VALUES (%s, %s, %s, %s::jsonb, %s)
                ON CONFLICT (entity_type, rule_name) DO NOTHING
                """,
                [rule["entity_type"], rule["rule_name"], rule["rule_type"],
                 json.dumps(rule["rule_config"]), rule["severity"]],
            )
            inserted += 1
        except Exception as e:
            logger.error("Failed to insert rule %s: %s", rule["rule_name"], e)

    print(f"  Seeded {inserted} quality rules")
    return inserted


def run_quality_assessment(db, engine):
    """Run quality assessment across key entity types."""
    entity_types = ["drug", "trial", "company", "literature", "event"]

    print("\nQuality Assessment Results:")
    print("-" * 70)

    for et in entity_types:
        report = engine.assess_table(et)
        print(f"\n  {et.upper()}")
        print(f"    Total records:  {report.total_records}")
        print(f"    Assessed:       {report.assessed_records}")
        print(f"    Avg score:      {report.avg_score}")
        print(f"    Passing:        {report.passing_count}")
        print(f"    Failing:        {report.failing_count}")

        if report.by_rule:
            print(f"    Rules:")
            for rule_name, stats in report.by_rule.items():
                print(f"      {rule_name:40s} avg={stats['avg_score']:.2f}  pass={stats['passed']}  fail={stats['failed']}")


def generate_catalog(db, catalog):
    """Generate dataset catalog and Croissant metadata."""
    catalog.refresh_all()

    entries = catalog.get_full_catalog()
    print(f"\nDataset Catalog ({len(entries)} entries):")
    print("-" * 70)

    for entry in entries:
        name = entry["dataset_name"]
        rows = entry["row_count"] or 0
        quality = entry.get("quality_score_avg")
        compl = entry.get("completeness_pct")
        fresh = entry.get("freshness_days")
        license_name = entry.get("license_name", "N/A")

        quality_str = f"{quality:.2f}" if quality else "N/A"
        compl_str = f"{compl:.0f}%" if compl else "N/A"
        fresh_str = f"{fresh:.0f}d" if fresh else "N/A"

        print(f"  {name:45s} {rows:>7} rows  Q={quality_str}  C={compl_str}  F={fresh_str}  [{license_name}]")

    # Export full Croissant bundle
    bundle = catalog.export_croissant_bundle()
    print(f"\nCroissant Bundle: {bundle['name']}")
    print(f"  Total size: {bundle['totalSize']}")
    print(f"  Sub-datasets: {len(bundle.get('hasPart', []))}")
    print(f"  Known biases: {len(bundle['cr:rai']['knownBias'].split('. '))} documented")
    print(f"  Preprocessing steps: {len(bundle['cr:rai']['preprocessingSteps'])} documented")


def show_hitl_status(db):
    """Show current HITL review queue status."""
    from integration.pipeline_hooks import HITLReviewManager
    mgr = HITLReviewManager(db)
    stats = mgr.get_stats()

    print("\nHITL Review Queue:")
    print("-" * 40)
    if not stats:
        print("  No items in queue")
    else:
        for status, types in stats.items():
            print(f"  {status}:")
            for rtype, count in types.items():
                print(f"    {rtype}: {count}")


if __name__ == "__main__":
    db = Database(config.db.dsn)
    db.connect()

    print("=" * 60)
    print("Market-Zero: Quality Rules, Catalog & Assessment")
    print("=" * 60)

    # Phase 1: Seed quality rules
    print("\n--- Phase 1: Seed Quality Rules ---")
    seed_quality_rules(db)

    # Phase 2: Run quality assessment (sample — drugs and companies are small enough)
    print("\n--- Phase 2: Quality Assessment ---")
    engine = DataQualityEngine(db, config)

    # Assess small tables fully, large tables sampled
    for et in ["drug", "company"]:
        report = engine.assess_table(et)
        print(f"\n  {et.upper()}: {report.assessed_records} assessed, avg_score={report.avg_score}")
        for rn, rs in report.by_rule.items():
            print(f"    {rn:40s} avg={rs['avg_score']:.2f}")

    # Sample assessment for trials (too many to assess all)
    trial_sample = db.fetch_all("SELECT id FROM clinical_trials LIMIT 100")
    trial_results = engine.assess_batch("trial", [r["id"] for r in trial_sample])
    scores = [engine.compute_composite_score(v) for v in trial_results.values() if v]
    avg_trial = sum(scores) / len(scores) if scores else 0
    print(f"\n  TRIAL (sample of {len(trial_sample)}): avg_score={avg_trial:.3f}")

    # Phase 3: Generate dataset catalog
    print("\n--- Phase 3: Dataset Catalog ---")
    catalog = DatasetCatalog(db, config)
    generate_catalog(db, catalog)

    # Phase 4: HITL status
    print("\n--- Phase 4: HITL Status ---")
    show_hitl_status(db)

    db.close()
    print("\nDone.")
