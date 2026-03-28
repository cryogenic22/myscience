"""Schedule definitions for the Market-Zero data pipeline.

Each connector has a cron schedule and a human-readable label.
Schedules are staggered to avoid hitting multiple APIs concurrently.

Pipeline execution order:
  1. Ontology (MeSH) -- defines TAs + mechanisms (monthly)
  2. Drug approvals (FDA Orange Book) -- populates drugs table (weekly)
  3. Clinical trials (CT.gov) -- links to drugs (daily)
  4. Literature (PubMed) -- links to drugs via entity resolution (daily)
  5. Full-text (PMC) -- enriches PubMed articles (daily)
  6. Safety (FAERS) -- adverse events per drug (weekly)
  7. Labels (openFDA) -- prescribing info per drug (weekly)
  8. Market events (FDA Shortages) -- recalls/shortages (daily)
  9. Company filings (SEC EDGAR) -- financial context (weekly)

Post-run hooks:
  - backfill_data_linkage: OWNS, IN_THERAPEUTIC_AREA, TARGETS_MECHANISM
  - fix_data_quality: literature-drug matching, quality scores
  - refresh materialized views
"""

from connectors.base import SourceType

# Maps SourceType -> APScheduler CronTrigger kwargs + label.
# All times in UTC. Staggered to avoid concurrent API hits.
CONNECTOR_SCHEDULES: dict[SourceType, dict] = {
    # ── Tier 1: Core entity sources (daily) ──
    SourceType.CLINICAL_TRIALS_GOV: {
        "label": "ClinicalTrials.gov",
        "cron": {"hour": 2, "minute": 0},                           # Daily 02:00
    },
    SourceType.PUBMED: {
        "label": "PubMed",
        "cron": {"hour": 2, "minute": 30},                          # Daily 02:30
    },
    SourceType.PMC: {
        "label": "PubMed Central",
        "cron": {"hour": 3, "minute": 0},                           # Daily 03:00
    },
    SourceType.FDA_SHORTAGES: {
        "label": "FDA Shortages",
        "cron": {"hour": 3, "minute": 30},                          # Daily 03:30
    },

    # ── Tier 2: Enrichment sources (weekly, staggered by day) ──
    SourceType.FDA_ORANGE_BOOK: {
        "label": "FDA Orange Book",
        "cron": {"hour": 4, "minute": 0, "day_of_week": "mon"},     # Monday 04:00
    },
    SourceType.OPENFDA_LABELS: {
        "label": "OpenFDA Drug Labels",
        "cron": {"hour": 4, "minute": 0, "day_of_week": "tue"},     # Tuesday 04:00
    },
    SourceType.SEC_EDGAR: {
        "label": "SEC EDGAR",
        "cron": {"hour": 4, "minute": 0, "day_of_week": "wed"},     # Wednesday 04:00
    },
    SourceType.OPENFDA_FAERS: {
        "label": "OpenFDA FAERS (Adverse Events)",
        "cron": {"hour": 4, "minute": 0, "day_of_week": "thu"},     # Thursday 04:00
    },

    # ── Tier 3: International sources (weekly) ──
    SourceType.EMA: {
        "label": "EMA (EU Medicines)",
        "cron": {"hour": 4, "minute": 30, "day_of_week": "fri"},    # Friday 04:30
    },

    # ── Tier 4: Ontology (monthly) ──
    SourceType.MESH_ONTOLOGY: {
        "label": "MeSH Ontology",
        "cron": {"hour": 5, "minute": 0, "day": 1},                 # 1st of month 05:00
    },
}

# Ordered list for --run-now / --run-all (ontology first, then data sources)
RUN_ORDER: list[SourceType] = [
    SourceType.MESH_ONTOLOGY,
    SourceType.FDA_ORANGE_BOOK,
    SourceType.CLINICAL_TRIALS_GOV,
    SourceType.EMA,
    SourceType.PUBMED,
    SourceType.PMC,
    SourceType.OPENFDA_FAERS,
    SourceType.OPENFDA_LABELS,
    SourceType.FDA_SHORTAGES,
    SourceType.SEC_EDGAR,
]

# Post-run tasks to execute after all connectors complete.
# These are run by the scheduler in order after a full pipeline cycle.
POST_RUN_TASKS = [
    "backfill_data_linkage",   # OWNS, TA, mechanism, sponsor links
    "fix_data_quality",         # literature-drug match, quality scores, MV refresh
]
