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

    # ── Tier 3: International + pricing + news ──
    SourceType.EMA: {
        "label": "EMA (EU Medicines)",
        "cron": {"hour": 4, "minute": 30, "day_of_week": "fri"},    # Friday 04:30
    },
    SourceType.NADAC: {
        "label": "CMS NADAC Pricing",
        "cron": {"hour": 5, "minute": 0, "day_of_week": "sat"},     # Saturday 05:00
    },
    SourceType.NEWS: {
        "label": "Pharma News & Events",
        "cron": {"hour": 6, "minute": 0},                           # Daily 06:00
    },

    # ── Tier 4: Molecular & discovery (weekly) ──
    SourceType.CHEMBL: {
        "label": "ChEMBL Bioactivity",
        "cron": {"hour": 5, "minute": 30, "day_of_week": "sat"},    # Saturday 05:30
    },
    SourceType.PUBCHEM: {
        "label": "PubChem Compounds",
        "cron": {"hour": 6, "minute": 0, "day_of_week": "sat"},     # Saturday 06:00
    },
    SourceType.OPEN_TARGETS: {
        "label": "Open Targets Genetics",
        "cron": {"hour": 6, "minute": 30, "day_of_week": "sat"},    # Saturday 06:30
    },

    # ── Tier 5: Ontology (monthly) ──
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
    SourceType.NADAC,
    SourceType.NEWS,
    SourceType.CHEMBL,
    SourceType.PUBCHEM,
    SourceType.OPEN_TARGETS,
]

# Post-run tasks to execute after all connectors complete.
# These are run by the scheduler in order after a full pipeline cycle.
POST_RUN_TASKS = [
    "backfill_data_linkage",   # OWNS, TA, mechanism, sponsor links
    "fix_data_quality",         # literature-drug match, quality scores, MV refresh
]


# ── Per-source freshness SLA (D1) ──
# Maps SourceType -> (target_table, recency_column, sla_days). Drives
# scripts/connector_health.py. A *single* global freshness_max_days is too
# coarse: CT.gov/PubMed run daily (2d SLA) while FAERS/Labels/ChEMBL run weekly
# (14d SLA). A source whose newest target-table row is older than its SLA is a
# silent failure (e.g. labels/FAERS were 105d stale while logging SUCCESS).
# recency_column is the ingestion-time column to age against (prefer
# retrieved_at / last_verified_at over created_at).
FRESHNESS_SLA_DAYS: dict[SourceType, tuple[str, str, int]] = {
    SourceType.CLINICAL_TRIALS_GOV: ("clinical_trials", "last_verified_at", 2),
    SourceType.PUBMED:              ("pubmed_articles", "last_verified_at", 2),
    SourceType.PMC:                 ("pmc_articles", "retrieved_at", 3),
    SourceType.FDA_SHORTAGES:       ("market_events", "retrieved_at", 2),
    SourceType.FDA_ORANGE_BOOK:     ("drugs", "updated_at", 14),
    SourceType.OPENFDA_LABELS:      ("drug_labels", "retrieved_at", 14),
    SourceType.SEC_EDGAR:           ("companies", "updated_at", 14),
    SourceType.OPENFDA_FAERS:       ("adverse_events", "retrieved_at", 14),
    # EMA stores EU CTIS trials as TRIAL records into clinical_trials with
    # source_api='ema' (NOT regulatory_milestones — that table is Orange
    # Book's). The (table,col,days) SLA shape can't filter by source_api, so
    # flow here reflects the shared clinical_trials table; the connector's
    # per-run records_inserted (E2E in the scorecard) is the true EMA signal.
    SourceType.EMA:                 ("clinical_trials", "last_verified_at", 14),
    SourceType.NEWS:                ("market_events", "retrieved_at", 2),
    SourceType.CHEMBL:              ("bioactivities", "retrieved_at", 14),
    SourceType.OPEN_TARGETS:        ("molecular_targets", "retrieved_at", 14),
    SourceType.PUBCHEM:             ("drugs", "updated_at", 14),
    SourceType.NADAC:               ("drug_pricing", "retrieved_at", 14),
    SourceType.MESH_ONTOLOGY:       ("therapeutic_areas", "updated_at", 45),
}

# Sources whose APIs are confirmed dead / have no live source feed. They stay
# scheduled (cheap, self-healing if the source returns) but their connector
# returns 0 rows by design, so the scorecard reports them as DEFERRED rather
# than RED — distinguishing "we gave up" from "it silently broke". Each entry
# carries the reproduced reason so the verdict is auditable.
KNOWN_DEFERRED_SOURCES: dict[SourceType, str] = {
    SourceType.NADAC: (
        "CMS NADAC endpoint (data.medicaid.gov/resource/4j6z-xnwq) returns "
        "HTTP 404 - CMS migrated platforms in 2025/26; no live feed and no "
        "rows in drug_pricing. Needs a new source URL before it can flow."
    ),
}
