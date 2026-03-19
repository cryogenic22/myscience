"""
FAIR (Findable, Accessible, Interoperable, Reusable) compliance analysis.

Runs 8 analyses matching the original assessment:
  1. Unresolved entity count
  2. Company enrichment percentage
  3. Drug completeness percentage
  4. Embedding coverage (companies)
  5. Source authority naming consistency
  6. Ontology depth (TAs + MoAs)
  7. Quality scoring coverage
  8. Patent count

Computes per-dimension scores and overall FAIR score.
Outputs before/after comparison.

Usage: python fair_analysis.py
"""

import logging
from dataclasses import dataclass, field

from config import config
from db import Database

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class FAIRMetrics:
    """Container for all FAIR analysis metrics."""
    unresolved_count: int = 0
    unresolved_total: int = 0
    company_enriched_pct: float = 0.0
    company_total: int = 0
    company_enriched: int = 0
    drug_completeness_pct: float = 0.0
    drug_total: int = 0
    drug_auto_created: int = 0
    embedding_coverage_companies: float = 0.0
    embedding_total: int = 0
    embedding_filled: int = 0
    source_consistency_pct: float = 0.0
    source_inconsistent: int = 0
    ontology_ta_count: int = 0
    ontology_moa_count: int = 0
    quality_coverage_pct: float = 0.0
    quality_assessed: int = 0
    quality_total_entities: int = 0
    patent_count: int = 0

    # Per-dimension scores (0-10)
    scores: dict = field(default_factory=dict)
    overall_score: float = 0.0


def analyze(db) -> FAIRMetrics:
    """Run all 8 FAIR analyses and compute scores."""
    m = FAIRMetrics()

    # 1. Unresolved entities
    row = db.fetch_one("SELECT count(*) as c FROM unresolved_entities WHERE resolved = FALSE")
    m.unresolved_count = row["c"] if row else 0
    row = db.fetch_one("SELECT count(*) as c FROM unresolved_entities")
    m.unresolved_total = row["c"] if row else 0

    resolved_pct = 1.0 - (m.unresolved_count / max(m.unresolved_total, 1))
    m.scores["entity_resolution"] = round(min(10.0, resolved_pct * 10), 1)

    # 2. Company enrichment (fields: name, cik, ticker, country, sic_code, strategy_embedding)
    row = db.fetch_one("SELECT count(*) as c FROM companies")
    m.company_total = row["c"] if row else 0

    row = db.fetch_one(
        """
        SELECT count(*) as c FROM companies
        WHERE cik IS NOT NULL
          AND ticker IS NOT NULL
          AND country IS NOT NULL
        """
    )
    m.company_enriched = row["c"] if row else 0
    m.company_enriched_pct = (m.company_enriched / max(m.company_total, 1)) * 100
    m.scores["company_enrichment"] = round(min(10.0, m.company_enriched_pct / 10), 1)

    # 3. Drug completeness (non-auto-created have more fields)
    row = db.fetch_one("SELECT count(*) as c FROM drugs")
    m.drug_total = row["c"] if row else 0

    row = db.fetch_one(
        """
        SELECT count(*) as c FROM drugs
        WHERE source_authority = 'clinical_trials_gov'
          AND brand_name IS NULL
          AND nda_number IS NULL
          AND approval_date IS NULL
        """
    )
    m.drug_auto_created = row["c"] if row else 0
    auto_pct = (m.drug_auto_created / max(m.drug_total, 1)) * 100
    m.drug_completeness_pct = 100.0 - auto_pct
    m.scores["drug_completeness"] = round(min(10.0, m.drug_completeness_pct / 10), 1)

    # 4. Company embedding coverage
    row = db.fetch_one("SELECT count(*) as c FROM companies")
    m.embedding_total = row["c"] if row else 0

    row = db.fetch_one(
        "SELECT count(*) as c FROM companies WHERE strategy_embedding IS NOT NULL"
    )
    m.embedding_filled = row["c"] if row else 0
    m.embedding_coverage_companies = (m.embedding_filled / max(m.embedding_total, 1)) * 100
    m.scores["embedding_coverage"] = round(min(10.0, m.embedding_coverage_companies / 10), 1)

    # 5. Source authority naming consistency
    row = db.fetch_one("SELECT count(*) as c FROM drugs WHERE source_authority IS NOT NULL")
    total_with_source = row["c"] if row else 0

    row = db.fetch_one(
        """
        SELECT count(*) as c FROM drugs
        WHERE source_authority IS NOT NULL
          AND source_authority NOT IN (
              'clinical_trials_gov', 'fda_orange_book', 'fda_shortages',
              'sec_edgar', 'pubmed', 'mesh_ontology', 'openfda_faers',
              'openfda_labels', 'pmc', 'user_document', 'user_url', 'backfill'
          )
        """
    )
    m.source_inconsistent = row["c"] if row else 0
    m.source_consistency_pct = ((total_with_source - m.source_inconsistent) / max(total_with_source, 1)) * 100
    m.scores["source_consistency"] = round(min(10.0, m.source_consistency_pct / 10), 1)

    # 6. Ontology depth
    row = db.fetch_one("SELECT count(*) as c FROM therapeutic_areas")
    m.ontology_ta_count = row["c"] if row else 0

    row = db.fetch_one("SELECT count(*) as c FROM mechanisms_of_action")
    m.ontology_moa_count = row["c"] if row else 0

    # Score: 10 if TAs >= 20 and MoAs >= 25, scale down proportionally
    ta_score = min(5.0, (m.ontology_ta_count / 20) * 5)
    moa_score = min(5.0, (m.ontology_moa_count / 25) * 5)
    m.scores["ontology_depth"] = round(ta_score + moa_score, 1)

    # 7. Quality scoring coverage
    entity_tables = {
        "drug": "drugs",
        "company": "companies",
        "trial": "clinical_trials",
        "literature": "pubmed_articles",
        "event": "market_events",
    }
    total_entities = 0
    assessed_entities = 0
    for entity_type, table in entity_tables.items():
        row = db.fetch_one(f"SELECT count(*) as c FROM {table}")
        count = row["c"] if row else 0
        total_entities += count

        row = db.fetch_one(
            f"SELECT count(*) as c FROM {table} WHERE quality_score IS NOT NULL"
        )
        assessed = row["c"] if row else 0
        assessed_entities += assessed

    m.quality_total_entities = total_entities
    m.quality_assessed = assessed_entities
    m.quality_coverage_pct = (assessed_entities / max(total_entities, 1)) * 100
    m.scores["quality_coverage"] = round(min(10.0, m.quality_coverage_pct / 10), 1)

    # 8. Patent count
    row = db.fetch_one("SELECT count(*) as c FROM patents")
    m.patent_count = row["c"] if row else 0
    # Score: 10 if patents > 50, proportional otherwise
    m.scores["patent_data"] = round(min(10.0, (m.patent_count / 50) * 10), 1)

    # Overall FAIR score (weighted average)
    weights = {
        "entity_resolution": 2.0,
        "company_enrichment": 1.0,
        "drug_completeness": 1.5,
        "embedding_coverage": 1.0,
        "source_consistency": 1.5,
        "ontology_depth": 1.0,
        "quality_coverage": 1.0,
        "patent_data": 0.5,
    }

    weighted_sum = sum(m.scores.get(k, 0) * w for k, w in weights.items())
    total_weight = sum(weights.values())
    m.overall_score = round(weighted_sum / total_weight, 1)

    return m


def print_report(m: FAIRMetrics, baseline_score: float = 7.0):
    """Print formatted FAIR analysis report."""
    print("=" * 70)
    print("  FAIR Compliance Analysis — Market-Zero")
    print("=" * 70)

    print("\n1. Entity Resolution")
    print(f"   Unresolved: {m.unresolved_count:,} / {m.unresolved_total:,}")
    print(f"   Score: {m.scores.get('entity_resolution', 0)}/10")

    print("\n2. Company Enrichment")
    print(f"   Enriched: {m.company_enriched}/{m.company_total} ({m.company_enriched_pct:.1f}%)")
    print(f"   Score: {m.scores.get('company_enrichment', 0)}/10")

    print("\n3. Drug Completeness")
    print(f"   Total drugs: {m.drug_total}, Auto-created (sparse): {m.drug_auto_created}")
    print(f"   Completeness: {m.drug_completeness_pct:.1f}%")
    print(f"   Score: {m.scores.get('drug_completeness', 0)}/10")

    print("\n4. Embedding Coverage (Companies)")
    print(f"   With embeddings: {m.embedding_filled}/{m.embedding_total} ({m.embedding_coverage_companies:.1f}%)")
    print(f"   Score: {m.scores.get('embedding_coverage', 0)}/10")

    print("\n5. Source Authority Consistency")
    print(f"   Inconsistent records: {m.source_inconsistent}")
    print(f"   Consistency: {m.source_consistency_pct:.1f}%")
    print(f"   Score: {m.scores.get('source_consistency', 0)}/10")

    print("\n6. Ontology Depth")
    print(f"   Therapeutic Areas: {m.ontology_ta_count}")
    print(f"   Mechanisms of Action: {m.ontology_moa_count}")
    print(f"   Score: {m.scores.get('ontology_depth', 0)}/10")

    print("\n7. Quality Scoring Coverage")
    print(f"   Assessed: {m.quality_assessed:,}/{m.quality_total_entities:,} ({m.quality_coverage_pct:.1f}%)")
    print(f"   Score: {m.scores.get('quality_coverage', 0)}/10")

    print("\n8. Patent Data")
    print(f"   Patents: {m.patent_count}")
    print(f"   Score: {m.scores.get('patent_data', 0)}/10")

    print("\n" + "-" * 70)
    print(f"  OVERALL FAIR SCORE: {m.overall_score}/10")
    print(f"  Baseline score:     {baseline_score}/10")
    delta = m.overall_score - baseline_score
    direction = "+" if delta >= 0 else ""
    print(f"  Change:             {direction}{delta:.1f}")
    print("-" * 70)

    if m.overall_score >= 8.5:
        print("  Status: TARGET MET (>= 8.5)")
    else:
        print(f"  Status: {8.5 - m.overall_score:.1f} points to target")


if __name__ == "__main__":
    db = Database(config.db.dsn)
    db.connect()

    metrics = analyze(db)
    print_report(metrics, baseline_score=7.0)

    db.close()
