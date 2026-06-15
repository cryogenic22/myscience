"""Automated data curation pipeline.

Phase 5.2: Scheduled weekly (or post-pipeline-run) to maintain data quality.
Runs company dedup, drug name cleanup, mechanism backfill, TA linkage,
drug enrichment, AI enrichment, competition derivation, and quality scorecard.

Usage:
    python -m scripts.auto_curate [--dry-run] [--skip-ai]
"""

from __future__ import annotations

import argparse
import logging
import time

from config import config
from db import Database

logger = logging.getLogger(__name__)


def run(dry_run: bool = False, skip_ai: bool = False) -> dict:
    """Run the full auto-curation pipeline."""
    results = {}
    total_start = time.time()

    # 1. Company deduplication
    logger.info("Step 1/8: Company deduplication")
    try:
        from scripts.dedup_companies import run as run_dedup
        t0 = time.time()
        results["dedup_companies"] = run_dedup(dry_run=dry_run)
        results["dedup_companies"]["elapsed_s"] = round(time.time() - t0, 1)
    except Exception as e:
        logger.error("Company dedup failed: %s", e)
        results["dedup_companies"] = {"error": str(e)}

    # 2. Drug name cleanup
    logger.info("Step 2/8: Drug name cleanup")
    try:
        from scripts.clean_drug_names import run as run_clean
        t0 = time.time()
        results["clean_drug_names"] = run_clean(dry_run=dry_run)
        results["clean_drug_names"]["elapsed_s"] = round(time.time() - t0, 1)
    except Exception as e:
        logger.error("Drug cleanup failed: %s", e)
        results["clean_drug_names"] = {"error": str(e)}

    # 2.5. Drug consolidation (merge duplicates)
    logger.info("Step 2.5/9: Drug consolidation")
    try:
        from scripts.consolidate_drugs import run as run_consolidate
        t0 = time.time()
        results["consolidate_drugs"] = run_consolidate(dry_run=dry_run)
        results["consolidate_drugs"]["elapsed_s"] = round(time.time() - t0, 1)
    except Exception as e:
        logger.error("Drug consolidation failed: %s", e)
        results["consolidate_drugs"] = {"error": str(e)}

    # 2.6. fact_class reconcile (D-Q1 §8.2): registry/regulatory facts that fell
    # into the 'corporate' default get the honest 'reference' class BY SOURCE, so the
    # coverage lens reflects real data. Idempotent + self-healing each cycle — the
    # forward fix (emit_one) keeps new facts honest; this reconciles any drift.
    logger.info("Step 2.6: fact_class reconcile")
    try:
        from scripts.backfill_fact_class import run as run_factclass
        t0 = time.time()
        results["fact_class_reconcile"] = run_factclass(dry_run=dry_run)
        results["fact_class_reconcile"]["elapsed_s"] = round(time.time() - t0, 1)
    except Exception as e:
        logger.error("fact_class reconcile failed: %s", e)
        results["fact_class_reconcile"] = {"error": str(e)}

    # 2.7. Orphan relinking (pubmed articles + clinical trials -> drug). Runs AFTER
    # consolidation so the name index reflects merged/canonical drugs. Self-healing
    # each cycle so newly-ingested NULL-drug_id rows don't drift back over the
    # FK-orphan ceilings (the durability lesson from the #242 one-shot backfill).
    logger.info("Step 2.7/9: Orphan drug relinking (literature + trials)")
    try:
        from scripts.relink_literature import run as run_relink_lit
        from scripts.relink_trials import run as run_relink_trials
        t0 = time.time()
        results["relink_literature"] = run_relink_lit(dry_run=dry_run)
        results["relink_trials"] = run_relink_trials(dry_run=dry_run)
        results["relink_orphans_elapsed_s"] = round(time.time() - t0, 1)
    except Exception as e:
        logger.error("Orphan relinking failed: %s", e)
        results["relink_orphans"] = {"error": str(e)}

    # 3. Mechanism backfill (before TA linkage — mechanisms feed TA links)
    logger.info("Step 3/9: Mechanism backfill")
    try:
        from scripts.backfill_mechanisms import run as run_mech_backfill
        t0 = time.time()
        results["backfill_mechanisms"] = run_mech_backfill(dry_run=dry_run)
        results["backfill_mechanisms"]["elapsed_s"] = round(time.time() - t0, 1)
    except Exception as e:
        logger.error("Mechanism backfill failed: %s", e)
        results["backfill_mechanisms"] = {"error": str(e)}

    # 4. TA linkage backfill
    logger.info("Step 4/8: TA linkage backfill")
    try:
        from scripts.backfill_ta_links import run as run_backfill
        t0 = time.time()
        results["backfill_ta_links"] = run_backfill(dry_run=dry_run)
        results["backfill_ta_links"]["elapsed_s"] = round(time.time() - t0, 1)
    except Exception as e:
        logger.error("TA backfill failed: %s", e)
        results["backfill_ta_links"] = {"error": str(e)}

    # 5. Drug enrichment
    logger.info("Step 5/8: Drug enrichment")
    try:
        from scripts.enrich_drugs import run as run_enrich_drugs
        t0 = time.time()
        results["enrich_drugs"] = run_enrich_drugs(dry_run=dry_run)
        results["enrich_drugs"]["elapsed_s"] = round(time.time() - t0, 1)
    except Exception as e:
        logger.error("Drug enrichment failed: %s", e)
        results["enrich_drugs"] = {"error": str(e)}

    # 6. AI enrichment (optional)
    if not skip_ai:
        logger.info("Step 6/8: AI enrichment")
        try:
            from scripts.ai_enrich import run as run_ai
            t0 = time.time()
            results["ai_enrich"] = run_ai(dry_run=dry_run, max_entities=50)
            results["ai_enrich"]["elapsed_s"] = round(time.time() - t0, 1)
        except Exception as e:
            logger.error("AI enrichment failed: %s", e)
            results["ai_enrich"] = {"error": str(e)}
    else:
        results["ai_enrich"] = {"status": "skipped"}

    # 7. Competition derivation (uses mechanism+TA data from steps 3-4)
    logger.info("Step 7/8: Competition derivation")
    try:
        from scripts.derive_competition import run as run_competition
        t0 = time.time()
        results["derive_competition"] = run_competition(dry_run=dry_run)
        results["derive_competition"]["elapsed_s"] = round(time.time() - t0, 1)
    except Exception as e:
        logger.error("Competition derivation failed: %s", e)
        results["derive_competition"] = {"error": str(e)}

    # 8. Refresh materialized views (ensures portfolio/pipeline data is current)
    logger.info("Step 8/10: Refresh materialized views")
    try:
        from config import config as _cfg
        _db = Database(_cfg.db.dsn)
        _db.connect()
        for mv in ['mv_drug_pipeline_strength', 'mv_company_portfolio', 'mv_trial_success_rate',
                    'mv_evidence_density', 'mv_competitive_landscape', 'mv_safety_signals']:
            try:
                _db.execute(f'REFRESH MATERIALIZED VIEW {mv}')
            except Exception:
                pass
        _db.close()
        results["refresh_mvs"] = {"status": "ok", "elapsed_s": round(time.time() - t0, 1)}
        logger.info("Materialized views refreshed")
    except Exception as e:
        logger.error("MV refresh failed: %s", e)
        results["refresh_mvs"] = {"error": str(e)}

    # 9. Quality scorecard
    logger.info("Step 9/10: Quality scorecard")
    try:
        from scripts.quality_scorecard import run as run_scorecard
        t0 = time.time()
        run_scorecard(output_path="reports/quality_scorecard.md")
        results["quality_scorecard"] = {"status": "ok", "elapsed_s": round(time.time() - t0, 1)}
    except Exception as e:
        logger.error("Quality scorecard failed: %s", e)
        results["quality_scorecard"] = {"error": str(e)}

    # Log all actions
    total_elapsed = round(time.time() - total_start, 1)
    results["total_elapsed_s"] = total_elapsed

    if not dry_run:
        try:
            db = Database(config.db.dsn)
            db.connect()
            from datetime import datetime, timezone
            db.execute(
                """
                INSERT INTO data_change_log
                    (entity_type, entity_id, change_type, changed_fields, changed_at)
                VALUES ('system', 'auto_curate', 'auto_curate_run', %s, %s)
                """,
                [list(results.keys()), datetime.now(timezone.utc)],
            )
            db.close()
        except Exception as e:
            logger.warning("Failed to log auto-curate run: %s", e)

    logger.info("Auto-curation complete in %.1fs", total_elapsed)
    return results


def main():
    parser = argparse.ArgumentParser(description="Run automated data curation")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--skip-ai", action="store_true", help="Skip AI enrichment step")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    results = run(dry_run=args.dry_run, skip_ai=args.skip_ai)
    print("\n=== Auto-Curation Results ===")
    for k, v in results.items():
        if isinstance(v, dict):
            status = v.get("error", v.get("status", "ok"))
            elapsed = v.get("elapsed_s", "")
            print(f"  {k}: {status}" + (f" ({elapsed}s)" if elapsed else ""))
        else:
            print(f"  {k}: {v}")
    if args.dry_run:
        print("  (dry run — no changes written)")


if __name__ == "__main__":
    main()
