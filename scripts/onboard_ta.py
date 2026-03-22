"""TA onboarding orchestrator.

Phase 3.2: Single entry point to onboard a new therapeutic area.
Reads a TADefinition YAML, runs connectors with target overrides,
and executes post-processing.

Usage:
    python -m scripts.onboard_ta domain/ta_definitions/oncology.yaml [--dry-run] [--skip-fetch]
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from config import config
from db import Database
from domain.ta_definitions.schema import TADefinition, load_ta_definition

logger = logging.getLogger(__name__)

# Connector run order — same as scheduler
CONNECTOR_ORDER = [
    "mesh",
    "orange_book",
    "clinical_trials",
    "pubmed",
    "openfda_faers",
    "openfda_labels",
    "fda_shortages",
    "sec_edgar",
]

# Map connector name → module + class
CONNECTOR_MAP = {
    "mesh": ("connectors.mesh", "MeSHConnector"),
    "orange_book": ("connectors.orange_book", "OrangeBookConnector"),
    "clinical_trials": ("connectors.clinical_trials", "ClinicalTrialsConnector"),
    "pubmed": ("connectors.pubmed", "PubMedConnector"),
    "openfda_faers": ("connectors.openfda_faers", "OpenFDAFAERSConnector"),
    "openfda_labels": ("connectors.openfda_labels", "OpenFDALabelsConnector"),
    "fda_shortages": ("connectors.fda_shortages", "FDAShortagesConnector"),
    "sec_edgar": ("connectors.sec_edgar", "SECEdgarConnector"),
}


def _instantiate_connector(name: str, overrides: dict):
    """Import and instantiate a connector with target overrides."""
    import importlib

    module_path, class_name = CONNECTOR_MAP[name]
    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)

    # All connectors accept optional config
    connector = cls(config=config, target_overrides=overrides.get(name, {}))
    return connector


def run_connectors(ta: TADefinition, dry_run: bool = False) -> dict[str, dict]:
    """Run connectors with TA-specific target overrides."""
    from integration.pipeline import IntegrationPipeline
    from domain.pharma.pack import get_pharma_pack

    overrides = ta.to_connector_overrides()
    results = {}

    db = Database(config.db.dsn)
    db.connect()

    try:
        pack = get_pharma_pack()
        pipeline = IntegrationPipeline(db, config, domain_pack=pack)

        for name in CONNECTOR_ORDER:
            if name not in CONNECTOR_MAP:
                continue

            connector_overrides = overrides.get(name, {})
            # Skip connectors with no targets for this TA
            if not any(connector_overrides.values()):
                logger.info("Skipping %s (no targets)", name)
                results[name] = {"status": "skipped", "reason": "no targets"}
                continue

            if dry_run:
                logger.info("[DRY RUN] Would run %s with overrides: %s", name, connector_overrides)
                results[name] = {"status": "dry_run", "overrides": connector_overrides}
                continue

            try:
                logger.info("Running connector: %s", name)
                start = time.time()
                connector = _instantiate_connector(name, overrides)

                # Run connector through the full pipeline (fetch → normalize → resolve → embed → store → link)
                result = pipeline.run(connector)
                elapsed = time.time() - start

                results[name] = {
                    "status": "ok",
                    "elapsed_seconds": round(elapsed, 1),
                    "pipeline_result": result.summary() if hasattr(result, "summary") else str(result),
                }

            except Exception as e:
                logger.error("Connector %s failed: %s", name, e)
                results[name] = {"status": "error", "error": str(e)}

    finally:
        db.close()

    return results


def run_post_processing(ta: TADefinition, dry_run: bool = False) -> dict:
    """Run post-fetch curation tasks."""
    from scripts.backfill_ta_links import run as run_backfill
    from scripts.clean_drug_names import run as run_clean
    from scripts.dedup_companies import run as run_dedup
    from scripts.enrich_drugs import run as run_enrich_drugs
    from scripts.enrich_companies import run as run_enrich_companies
    from scripts.quality_scorecard import run as run_scorecard

    results = {}

    logger.info("Running post-processing: backfill TA links")
    results["backfill_ta_links"] = run_backfill(dry_run=dry_run)

    logger.info("Running post-processing: clean drug names")
    results["clean_drug_names"] = run_clean(dry_run=dry_run)

    logger.info("Running post-processing: dedup companies")
    results["dedup_companies"] = run_dedup(dry_run=dry_run)

    logger.info("Running post-processing: enrich drugs")
    results["enrich_drugs"] = run_enrich_drugs(dry_run=dry_run)

    logger.info("Running post-processing: enrich companies")
    results["enrich_companies"] = run_enrich_companies(dry_run=dry_run)

    # Refresh materialized views
    if not dry_run:
        try:
            from services.metrics import PharmaMetrics
            db = Database(config.db.dsn)
            db.connect()
            metrics = PharmaMetrics(db)
            metrics.refresh()
            db.close()
            logger.info("Materialized views refreshed")
        except Exception as e:
            logger.warning("View refresh failed: %s", e)

    # Generate scorecard
    logger.info("Generating quality scorecard")
    output_path = f"reports/quality_scorecard_{ta.name}.md"
    results["scorecard_path"] = output_path
    if not dry_run:
        run_scorecard(output_path=output_path)

    return results


def run(yaml_path: str, dry_run: bool = False, skip_fetch: bool = False) -> dict:
    """Full TA onboarding pipeline."""
    ta = load_ta_definition(yaml_path)
    logger.info("Onboarding TA: %s (%s)", ta.display_name, ta.name)
    logger.info(
        "Targets: %d drugs, %d conditions, %d MeSH IDs, %d companies",
        len(ta.target_drugs), len(ta.target_conditions),
        len(ta.mesh_ids), len(ta.target_companies),
    )

    results = {"ta": ta.name, "display_name": ta.display_name}

    if not skip_fetch:
        results["connectors"] = run_connectors(ta, dry_run=dry_run)
    else:
        logger.info("Skipping connector fetch (--skip-fetch)")
        results["connectors"] = {"status": "skipped"}

    results["post_processing"] = run_post_processing(ta, dry_run=dry_run)

    return results


def main():
    parser = argparse.ArgumentParser(description="Onboard a new therapeutic area")
    parser.add_argument("yaml_path", help="Path to TA definition YAML")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--skip-fetch", action="store_true", help="Skip connector fetch, run post-processing only")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not Path(args.yaml_path).exists():
        print(f"Error: TA definition not found: {args.yaml_path}")
        sys.exit(1)

    results = run(args.yaml_path, dry_run=args.dry_run, skip_fetch=args.skip_fetch)

    print("\n=== TA Onboarding Results ===")
    print(f"  TA: {results['display_name']} ({results['ta']})")

    if isinstance(results.get("connectors"), dict):
        print("\n  Connectors:")
        for name, info in results["connectors"].items():
            if isinstance(info, dict):
                print(f"    {name}: {info.get('status', 'unknown')}")
            else:
                print(f"    {name}: {info}")

    if isinstance(results.get("post_processing"), dict):
        print("\n  Post-processing:")
        for name, info in results["post_processing"].items():
            print(f"    {name}: {info}")

    if args.dry_run:
        print("\n  (dry run — no changes written)")


if __name__ == "__main__":
    main()
