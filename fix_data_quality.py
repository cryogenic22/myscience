"""
Comprehensive data quality fix script for Market-Zero.

Addresses:
  F1: Literature-drug linkage (50% of pubmed_articles have NULL drug_id)
  F2: Drug-TA linkage for CV/HF drugs (380 drugs with no TA at all)
  F3: Quality score backfill (NULL scores on drugs/companies/articles)
  F4: Refresh materialized views
  F5: Verify entity_links consistency

Usage: python fix_data_quality.py
"""

import json
import logging
import re
import time

from config import config
from db import Database

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════
#  F1 — Literature-Drug Linkage
# ════════════════════════════════════════════════════════════

# Drug generic names to search for in article titles/abstracts
DRUG_NAME_PATTERNS = [
    # GLP-1 RAs
    ("semaglutide", None),
    ("liraglutide", None),
    ("tirzepatide", None),
    ("dulaglutide", None),
    ("exenatide", None),
    ("lixisenatide", None),
    ("albiglutide", None),
    # SGLT2i
    ("empagliflozin", None),
    ("dapagliflozin", None),
    ("canagliflozin", None),
    ("ertugliflozin", None),
    ("sotagliflozin", None),
    # DPP-4i
    ("sitagliptin", None),
    ("linagliptin", None),
    ("saxagliptin", None),
    ("alogliptin", None),
    ("vildagliptin", None),
    # Insulin
    ("insulin glargine", None),
    ("insulin lispro", None),
    ("insulin aspart", None),
    ("insulin degludec", None),
    ("insulin detemir", None),
    # Other diabetes
    ("metformin", None),
    ("pioglitazone", None),
    ("rosiglitazone", None),
    # CV / HF drugs
    ("sacubitril", None),
    ("valsartan", None),
    ("finerenone", None),
    ("vericiguat", None),
    ("ivabradine", None),
    ("carvedilol", None),
    ("metoprolol", None),
    ("bisoprolol", None),
    ("enalapril", None),
    ("ramipril", None),
    ("lisinopril", None),
    ("losartan", None),
    ("irbesartan", None),
    ("candesartan", None),
    ("spironolactone", None),
    ("eplerenone", None),
]

# CV/HF drug name patterns for TA classification
CV_HF_DRUG_PATTERNS = [
    # Beta-blockers
    (r"^carvedilol", "Heart Failure"),
    (r"^metoprolol", "Heart Failure"),
    (r"^bisoprolol", "Heart Failure"),
    (r"^nebivolol", "Cardiovascular Diseases"),
    (r"^atenolol", "Cardiovascular Diseases"),
    # ACE inhibitors
    (r"pril$", "Cardiovascular Diseases"),
    (r"^enalapril", "Heart Failure"),
    (r"^ramipril", "Cardiovascular Diseases"),
    (r"^lisinopril", "Cardiovascular Diseases"),
    (r"^captopril", "Cardiovascular Diseases"),
    # ARBs
    (r"sartan$", "Cardiovascular Diseases"),
    (r"^valsartan", "Heart Failure"),
    (r"^losartan", "Cardiovascular Diseases"),
    (r"^candesartan", "Heart Failure"),
    (r"^irbesartan", "Cardiovascular Diseases"),
    # ARNI
    (r"^sacubitril", "Heart Failure"),
    # MRAs
    (r"^spironolactone", "Heart Failure"),
    (r"^eplerenone", "Heart Failure"),
    (r"^finerenone", "Heart Failure"),
    # sGC stimulator
    (r"^vericiguat", "Heart Failure"),
    # If channel blocker
    (r"^ivabradine", "Heart Failure"),
    # SGLT2i also have HF indication
    (r"^empagliflozin", "Heart Failure"),
    (r"^dapagliflozin", "Heart Failure"),
    (r"^sotagliflozin", "Heart Failure"),
    # Diuretics
    (r"^furosemide", "Heart Failure"),
    (r"^bumetanide", "Heart Failure"),
    (r"^torsemide", "Heart Failure"),
    (r"^hydrochlorothiazide", "Hypertension"),
    (r"^chlorthalidone", "Hypertension"),
    # Calcium channel blockers
    (r"^amlodipine", "Hypertension"),
    (r"^nifedipine", "Hypertension"),
    (r"^diltiazem", "Cardiovascular Diseases"),
]


def _upsert_link(db, source_id, source_type, target_id, target_type,
                 link_type, via, confidence, source, metadata=None):
    """Insert a link, return True if created."""
    metadata_json = json.dumps(metadata) if metadata else None
    try:
        row = db.fetch_one(
            """
            INSERT INTO entity_links
                (source_entity_id, source_entity_type,
                 target_entity_id, target_entity_type,
                 link_type, link_via, confidence, metadata, provenance_source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (source_entity_id, target_entity_id, link_type) DO NOTHING
            RETURNING id
            """,
            [str(source_id), source_type, str(target_id), target_type,
             link_type, via, confidence, metadata_json, source],
        )
        return row is not None
    except Exception as e:
        logger.debug("Link upsert error: %s", e)
        return False


def fix_literature_drug_linkage(db):
    """
    F1: Match pubmed_articles to drugs by searching for drug generic names
    in article titles and abstracts.
    """
    print("\n" + "=" * 60)
    print("F1: Fix Literature-Drug Linkage")
    print("=" * 60)

    # Load drug name -> id mapping
    drugs = db.fetch_all("SELECT id, generic_name FROM drugs WHERE generic_name IS NOT NULL")
    drug_lookup = {}
    for d in drugs:
        name = d["generic_name"].lower().strip()
        drug_lookup[name] = str(d["id"])

    # Load articles without drug_id
    articles = db.fetch_all("""
        SELECT id, title, abstract
        FROM pubmed_articles
        WHERE drug_id IS NULL
    """)
    print(f"  Articles without drug_id: {len(articles)}")

    matched = 0
    links_created = 0
    for art in articles:
        art_text = ((art["title"] or "") + " " + (art["abstract"] or "")).lower()
        best_drug_id = None
        best_drug_name = None

        # Search for drug names in the article text
        for drug_name, _ in DRUG_NAME_PATTERNS:
            if drug_name in art_text:
                if drug_name in drug_lookup:
                    best_drug_id = drug_lookup[drug_name]
                    best_drug_name = drug_name
                    break  # Use first match (ordered by importance)

        if not best_drug_id:
            # Try matching against all drugs in DB
            for name, did in drug_lookup.items():
                if len(name) >= 5 and name in art_text:
                    best_drug_id = did
                    best_drug_name = name
                    break

        if best_drug_id:
            # Update drug_id FK
            try:
                db.execute(
                    "UPDATE pubmed_articles SET drug_id = %s WHERE id = %s AND drug_id IS NULL",
                    [best_drug_id, art["id"]],
                )
                matched += 1
            except Exception as e:
                logger.debug("Article drug_id update error: %s", e)

            # Create EVIDENCE_FOR link
            created = _upsert_link(
                db,
                source_id=str(art["id"]), source_type="literature",
                target_id=best_drug_id, target_type="drug",
                link_type="EVIDENCE_FOR", via="title_abstract_match",
                confidence=0.8, source="fix_data_quality",
                metadata={"matched_drug": best_drug_name},
            )
            if created:
                links_created += 1

    print(f"  Matched articles to drugs: {matched}")
    print(f"  EVIDENCE_FOR links created: {links_created}")

    # Report remaining unlinked
    remaining = db.fetch_one("SELECT count(*) as c FROM pubmed_articles WHERE drug_id IS NULL")
    total = db.fetch_one("SELECT count(*) as c FROM pubmed_articles")
    print(f"  Still unlinked: {remaining['c']}/{total['c']} ({remaining['c']*100//max(total['c'],1)}%)")

    return matched


def fix_drug_ta_linkage(db):
    """
    F2: Classify CV/HF drugs into therapeutic areas.
    Extends the backfill script which only covers diabetes/obesity patterns.
    """
    print("\n" + "=" * 60)
    print("F2: Fix Drug-TA Linkage (CV/HF drugs)")
    print("=" * 60)

    # Load TA lookup
    ta_lookup = {}
    for row in db.fetch_all("SELECT id, name FROM therapeutic_areas"):
        ta_lookup[row["name"]] = str(row["id"])

    # Load all drugs
    all_drugs = db.fetch_all("SELECT id, generic_name FROM drugs WHERE generic_name IS NOT NULL")
    print(f"  Total drugs to scan: {len(all_drugs)}")

    fk_updated = 0
    links_created = 0
    drug_ta_assignments = {}  # drug_id -> set of TA names

    for drug in all_drugs:
        did = str(drug["id"])
        gname = drug["generic_name"].lower().strip()

        for pattern, ta_name in CV_HF_DRUG_PATTERNS:
            if re.search(pattern, gname):
                if did not in drug_ta_assignments:
                    drug_ta_assignments[did] = set()
                drug_ta_assignments[did].add(ta_name)

    print(f"  Drugs matched to CV/HF TAs: {len(drug_ta_assignments)}")

    for did, ta_names in drug_ta_assignments.items():
        for ta_name in ta_names:
            if ta_name not in ta_lookup:
                continue
            ta_id = ta_lookup[ta_name]

            # Create IN_THERAPEUTIC_AREA link
            created = _upsert_link(
                db,
                source_id=did, source_type="drug",
                target_id=ta_id, target_type="therapeutic_area",
                link_type="IN_THERAPEUTIC_AREA", via="cv_hf_classification",
                confidence=0.85, source="fix_data_quality",
            )
            if created:
                links_created += 1

        # Update FK for drugs with NULL therapeutic_area_id
        # Pick HF > CV > Hypertension priority
        primary_ta = None
        for pref in ["Heart Failure", "Cardiovascular Diseases", "Hypertension"]:
            if pref in ta_names and pref in ta_lookup:
                primary_ta = pref
                break
        if primary_ta:
            try:
                db.execute(
                    "UPDATE drugs SET therapeutic_area_id = %s WHERE id = %s AND therapeutic_area_id IS NULL",
                    [ta_lookup[primary_ta], did],
                )
                fk_updated += 1
            except Exception as e:
                logger.debug("TA FK error: %s", e)

    print(f"  FK updates: {fk_updated}")
    print(f"  IN_THERAPEUTIC_AREA links created: {links_created}")

    # Also classify drugs by trial conditions (for drugs that still have no TA)
    print("\n  --- Scanning trial conditions for remaining unlinked drugs ---")
    unlinked = db.fetch_all("""
        SELECT d.id, d.generic_name
        FROM drugs d
        WHERE d.therapeutic_area_id IS NULL
        AND NOT EXISTS (
            SELECT 1 FROM entity_links el
            WHERE el.source_entity_id = d.id::text
            AND el.link_type = 'IN_THERAPEUTIC_AREA'
        )
    """)
    print(f"  Drugs still without any TA: {len(unlinked)}")

    TA_KEYWORD_MAP = {
        "heart failure": "Heart Failure",
        "hfref": "Heart Failure",
        "hfpef": "Heart Failure",
        "reduced ejection fraction": "Heart Failure",
        "preserved ejection fraction": "Heart Failure",
        "cardiac failure": "Heart Failure",
        "congestive heart failure": "Heart Failure",
        "cardiovascular": "Cardiovascular Diseases",
        "myocardial infarction": "Cardiovascular Diseases",
        "atherosclerosis": "Cardiovascular Diseases",
        "hypertension": "Hypertension",
        "blood pressure": "Hypertension",
        "diabetes": "Diabetes Mellitus",
        "type 2 diabetes": "Diabetes Mellitus, Type 2",
        "t2dm": "Diabetes Mellitus, Type 2",
        "obesity": "Obesity",
        "overweight": "Obesity",
    }

    trial_fixed = 0
    for drug in unlinked:
        did = str(drug["id"])
        # Check trial conditions for this drug
        trials = db.fetch_all(
            "SELECT conditions FROM clinical_trials WHERE drug_id = %s AND conditions IS NOT NULL",
            [did],
        )
        ta_names_found = set()
        for trial in trials:
            cond_text = " ".join(trial["conditions"]).lower() if isinstance(trial["conditions"], list) else (trial["conditions"] or "").lower()
            for kw, ta_name in TA_KEYWORD_MAP.items():
                if kw in cond_text and ta_name in ta_lookup:
                    ta_names_found.add(ta_name)

        if ta_names_found:
            for ta_name in ta_names_found:
                _upsert_link(
                    db,
                    source_id=did, source_type="drug",
                    target_id=ta_lookup[ta_name], target_type="therapeutic_area",
                    link_type="IN_THERAPEUTIC_AREA", via="trial_condition_match",
                    confidence=0.8, source="fix_data_quality",
                )
            # Update FK with most specific
            for pref in ["Diabetes Mellitus, Type 2", "Diabetes Mellitus", "Heart Failure",
                         "Obesity", "Cardiovascular Diseases", "Hypertension"]:
                if pref in ta_names_found and pref in ta_lookup:
                    db.execute(
                        "UPDATE drugs SET therapeutic_area_id = %s WHERE id = %s AND therapeutic_area_id IS NULL",
                        [ta_lookup[pref], did],
                    )
                    trial_fixed += 1
                    break

    print(f"  Fixed via trial conditions: {trial_fixed}")
    return links_created


def fix_quality_scores(db):
    """
    F3: Backfill quality scores for records with NULL quality_score.
    Uses a simplified scoring: based on field completeness.
    """
    print("\n" + "=" * 60)
    print("F3: Backfill Quality Scores")
    print("=" * 60)

    # Drugs: score based on completeness of key fields
    print("\n  --- Drugs ---")
    updated = db.execute("""
        UPDATE drugs SET quality_score = (
            0.3 * CASE WHEN generic_name IS NOT NULL AND generic_name != '' THEN 1.0 ELSE 0.0 END +
            0.15 * CASE WHEN brand_name IS NOT NULL AND brand_name != '' THEN 1.0 ELSE 0.0 END +
            0.15 * CASE WHEN therapeutic_area_id IS NOT NULL THEN 1.0 ELSE 0.0 END +
            0.1 * CASE WHEN mechanism_id IS NOT NULL THEN 1.0 ELSE 0.0 END +
            0.1 * CASE WHEN company_id IS NOT NULL THEN 1.0 ELSE 0.0 END +
            0.1 * CASE WHEN molecule_embedding IS NOT NULL THEN 1.0 ELSE 0.0 END +
            0.1 * CASE WHEN source_url IS NOT NULL AND source_url != '' THEN 1.0 ELSE 0.0 END
        )
        WHERE quality_score IS NULL
    """)
    count = db.fetch_one("SELECT count(*) as c FROM drugs WHERE quality_score IS NOT NULL")
    print(f"  Drugs with quality_score: {count['c']}")

    # Companies: score based on name, description, embedding
    print("\n  --- Companies ---")
    db.execute("""
        UPDATE companies SET quality_score = (
            0.3 * CASE WHEN name IS NOT NULL AND name != '' THEN 1.0 ELSE 0.0 END +
            0.2 * CASE WHEN ticker IS NOT NULL AND ticker != '' THEN 1.0 ELSE 0.0 END +
            0.2 * CASE WHEN country IS NOT NULL AND country != '' THEN 1.0 ELSE 0.0 END +
            0.15 * CASE WHEN strategy_embedding IS NOT NULL THEN 1.0 ELSE 0.0 END +
            0.15 * CASE WHEN source_url IS NOT NULL AND source_url != '' THEN 1.0 ELSE 0.0 END
        )
        WHERE quality_score IS NULL
    """)
    count = db.fetch_one("SELECT count(*) as c FROM companies WHERE quality_score IS NOT NULL")
    print(f"  Companies with quality_score: {count['c']}")

    # PubMed articles: score based on title, abstract, drug linkage
    print("\n  --- PubMed Articles ---")
    db.execute("""
        UPDATE pubmed_articles SET quality_score = (
            0.2 * CASE WHEN title IS NOT NULL AND title != '' THEN 1.0 ELSE 0.0 END +
            0.2 * CASE WHEN abstract IS NOT NULL AND abstract != '' THEN 1.0 ELSE 0.0 END +
            0.15 * CASE WHEN drug_id IS NOT NULL THEN 1.0 ELSE 0.0 END +
            0.1 * CASE WHEN journal IS NOT NULL AND journal != '' THEN 1.0 ELSE 0.0 END +
            0.1 * CASE WHEN authors IS NOT NULL THEN 1.0 ELSE 0.0 END +
            0.1 * CASE WHEN publication_date IS NOT NULL THEN 1.0 ELSE 0.0 END +
            0.1 * CASE WHEN abstract_embedding IS NOT NULL THEN 1.0 ELSE 0.0 END +
            0.05 * CASE WHEN doi IS NOT NULL THEN 1.0 ELSE 0.0 END
        )
        WHERE quality_score IS NULL
    """)
    count = db.fetch_one("SELECT count(*) as c FROM pubmed_articles WHERE quality_score IS NOT NULL")
    print(f"  PubMed articles with quality_score: {count['c']}")

    # Clinical trials: score based on completeness
    print("\n  --- Clinical Trials ---")
    db.execute("""
        UPDATE clinical_trials SET quality_score = (
            0.15 * CASE WHEN official_title IS NOT NULL AND official_title != '' THEN 1.0 ELSE 0.0 END +
            0.15 * CASE WHEN drug_id IS NOT NULL THEN 1.0 ELSE 0.0 END +
            0.1 * CASE WHEN phase IS NOT NULL AND phase != '' THEN 1.0 ELSE 0.0 END +
            0.1 * CASE WHEN status IS NOT NULL AND status != '' THEN 1.0 ELSE 0.0 END +
            0.1 * CASE WHEN sponsor_name IS NOT NULL AND sponsor_name != '' THEN 1.0 ELSE 0.0 END +
            0.1 * CASE WHEN conditions IS NOT NULL THEN 1.0 ELSE 0.0 END +
            0.1 * CASE WHEN enrollment_target IS NOT NULL THEN 1.0 ELSE 0.0 END +
            0.1 * CASE WHEN start_date IS NOT NULL THEN 1.0 ELSE 0.0 END +
            0.1 * CASE WHEN source_url IS NOT NULL AND source_url != '' THEN 1.0 ELSE 0.0 END
        )
        WHERE quality_score IS NULL
    """)
    count = db.fetch_one("SELECT count(*) as c FROM clinical_trials WHERE quality_score IS NOT NULL")
    print(f"  Clinical trials with quality_score: {count['c']}")

    # Show avg quality scores
    print("\n  Quality Score Summary:")
    for table in ['drugs', 'clinical_trials', 'pubmed_articles', 'companies']:
        r = db.fetch_one(f"SELECT avg(quality_score) as avg_q, min(quality_score) as min_q FROM {table}")
        avg_q = f"{r['avg_q']:.3f}" if r['avg_q'] else "N/A"
        min_q = f"{r['min_q']:.3f}" if r['min_q'] else "N/A"
        print(f"    {table:25s} avg={avg_q}  min={min_q}")


def fix_entity_links_consistency(db):
    """
    F5: Verify and fix entity_links consistency.
    - Remove orphan links (source or target entity no longer exists)
    - Deduplicate links
    """
    print("\n" + "=" * 60)
    print("F5: Entity Links Consistency Check")
    print("=" * 60)

    # Count links by type before
    rows = db.fetch_all(
        "SELECT link_type, count(*) as c FROM entity_links GROUP BY link_type ORDER BY c DESC"
    )
    total_before = sum(r["c"] for r in rows)
    print(f"  Total entity_links before: {total_before:,}")

    # Remove orphan EVIDENCE_FOR links (literature -> drug where drug doesn't exist)
    orphan_result = db.fetch_one("""
        SELECT count(*) as c FROM entity_links el
        WHERE el.link_type = 'EVIDENCE_FOR'
        AND el.target_entity_type = 'drug'
        AND NOT EXISTS (SELECT 1 FROM drugs d WHERE d.id::text = el.target_entity_id)
    """)
    if orphan_result["c"] > 0:
        db.execute("""
            DELETE FROM entity_links
            WHERE link_type = 'EVIDENCE_FOR'
            AND target_entity_type = 'drug'
            AND NOT EXISTS (SELECT 1 FROM drugs d WHERE d.id::text = target_entity_id)
        """)
        print(f"  Removed {orphan_result['c']} orphan EVIDENCE_FOR links")

    # Remove orphan IN_THERAPEUTIC_AREA links
    orphan_ta = db.fetch_one("""
        SELECT count(*) as c FROM entity_links el
        WHERE el.link_type = 'IN_THERAPEUTIC_AREA'
        AND NOT EXISTS (SELECT 1 FROM therapeutic_areas ta WHERE ta.id::text = el.target_entity_id)
    """)
    if orphan_ta["c"] > 0:
        db.execute("""
            DELETE FROM entity_links
            WHERE link_type = 'IN_THERAPEUTIC_AREA'
            AND NOT EXISTS (SELECT 1 FROM therapeutic_areas ta WHERE ta.id::text = target_entity_id)
        """)
        print(f"  Removed {orphan_ta['c']} orphan IN_THERAPEUTIC_AREA links")

    # Remove orphan HAS_ADVERSE_EVENT links
    orphan_ae = db.fetch_one("""
        SELECT count(*) as c FROM entity_links el
        WHERE el.link_type = 'HAS_ADVERSE_EVENT'
        AND NOT EXISTS (SELECT 1 FROM adverse_events ae WHERE ae.id::text = el.target_entity_id)
    """)
    if orphan_ae["c"] > 0:
        db.execute("""
            DELETE FROM entity_links
            WHERE link_type = 'HAS_ADVERSE_EVENT'
            AND NOT EXISTS (SELECT 1 FROM adverse_events ae WHERE ae.id::text = target_entity_id)
        """)
        print(f"  Removed {orphan_ae['c']} orphan HAS_ADVERSE_EVENT links")

    # Remove orphan HAS_LABEL links
    orphan_dl = db.fetch_one("""
        SELECT count(*) as c FROM entity_links el
        WHERE el.link_type = 'HAS_LABEL'
        AND NOT EXISTS (SELECT 1 FROM drug_labels dl WHERE dl.id::text = el.target_entity_id)
    """)
    if orphan_dl["c"] > 0:
        db.execute("""
            DELETE FROM entity_links
            WHERE link_type = 'HAS_LABEL'
            AND NOT EXISTS (SELECT 1 FROM drug_labels dl WHERE dl.id::text = target_entity_id)
        """)
        print(f"  Removed {orphan_dl['c']} orphan HAS_LABEL links")

    # Remove orphan HAS_FULL_TEXT links
    orphan_pmc = db.fetch_one("""
        SELECT count(*) as c FROM entity_links el
        WHERE el.link_type = 'HAS_FULL_TEXT'
        AND NOT EXISTS (SELECT 1 FROM pmc_articles pa WHERE pa.id::text = el.target_entity_id)
    """)
    if orphan_pmc["c"] > 0:
        db.execute("""
            DELETE FROM entity_links
            WHERE link_type = 'HAS_FULL_TEXT'
            AND NOT EXISTS (SELECT 1 FROM pmc_articles pa WHERE pa.id::text = target_entity_id)
        """)
        print(f"  Removed {orphan_pmc['c']} orphan HAS_FULL_TEXT links")

    # Cross-source linkage coverage report
    print("\n  Cross-source linkage coverage:")
    for table, link_type, label in [
        ("adverse_events", "HAS_ADVERSE_EVENT", "Adverse Events"),
        ("drug_labels", "HAS_LABEL", "Drug Labels"),
        ("pmc_articles", "HAS_FULL_TEXT", "PMC Articles"),
    ]:
        total = db.fetch_one(f"SELECT count(*) as c FROM {table}")["c"]
        with_drug = db.fetch_one(f"SELECT count(*) as c FROM {table} WHERE drug_id IS NOT NULL")["c"]
        with_link = db.fetch_one(
            "SELECT count(DISTINCT target_entity_id) as c FROM entity_links WHERE link_type = %s",
            [link_type]
        )["c"]
        pct = 100 * with_drug // max(total, 1)
        print(f"    {label:20s}: {total:>5} total, {with_drug:>5} with drug_id ({pct}%), {with_link:>5} graph links")

    # Count after
    total_after = db.fetch_one("SELECT count(*) as c FROM entity_links")["c"]
    print(f"  Total entity_links after: {total_after:,}")


def refresh_materialized_views(db):
    """F4: Refresh all materialized views."""
    print("\n" + "=" * 60)
    print("F4: Refresh Materialized Views")
    print("=" * 60)

    views = [
        "mv_drug_pipeline_strength",
        "mv_trial_success_rate",
        "mv_evidence_density",
        "mv_competitive_landscape",
        "mv_company_portfolio",
    ]
    for view in views:
        try:
            t0 = time.time()
            db.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}")
            elapsed = time.time() - t0
            count = db.fetch_one(f"SELECT count(*) as c FROM {view}")
            print(f"  {view}: {count['c']:>6} rows ({elapsed:.1f}s)")
        except Exception as e:
            # CONCURRENTLY requires unique index; fall back to non-concurrent
            try:
                db.execute(f"REFRESH MATERIALIZED VIEW {view}")
                count = db.fetch_one(f"SELECT count(*) as c FROM {view}")
                print(f"  {view}: {count['c']:>6} rows (non-concurrent)")
            except Exception as e2:
                print(f"  SKIP {view}: {e2}")


def show_final_report(db):
    """Show comprehensive post-fix report."""
    print("\n" + "=" * 60)
    print("FINAL DATA QUALITY REPORT")
    print("=" * 60)

    # Table counts
    print("\n  --- Table Counts ---")
    for t in ['drugs', 'clinical_trials', 'pubmed_articles', 'companies', 'entity_links']:
        r = db.fetch_one(f"SELECT count(*) as c FROM {t}")
        print(f"    {t:30s} {r['c']:>8,}")

    # Drug FK coverage
    print("\n  --- Drug FK Coverage ---")
    total = db.fetch_one("SELECT count(*) as c FROM drugs")["c"]
    for col in ['therapeutic_area_id', 'mechanism_id', 'company_id']:
        r = db.fetch_one(f"SELECT count(*) as c FROM drugs WHERE {col} IS NOT NULL")
        pct = r['c'] * 100 // max(total, 1)
        print(f"    {col:30s} {r['c']:>5}/{total} ({pct}%)")

    # Literature linkage
    print("\n  --- Literature Drug Linkage ---")
    total_lit = db.fetch_one("SELECT count(*) as c FROM pubmed_articles")["c"]
    linked = db.fetch_one("SELECT count(*) as c FROM pubmed_articles WHERE drug_id IS NOT NULL")["c"]
    print(f"    Linked: {linked}/{total_lit} ({linked*100//max(total_lit,1)}%)")

    # TA coverage
    print("\n  --- Therapeutic Area Coverage ---")
    rows = db.fetch_all("""
        SELECT ta.name,
               COUNT(DISTINCT d.id) as fk_count,
               COUNT(DISTINCT el.source_entity_id) as link_count
        FROM therapeutic_areas ta
        LEFT JOIN drugs d ON d.therapeutic_area_id = ta.id
        LEFT JOIN entity_links el ON el.target_entity_id = ta.id::text
            AND el.link_type = 'IN_THERAPEUTIC_AREA'
        GROUP BY ta.name
        ORDER BY link_count DESC
    """)
    for r in rows:
        print(f"    {r['name']:40s} FK={r['fk_count']:>4}  links={r['link_count']:>4}")

    # Entity links
    print("\n  --- Entity Links by Type ---")
    rows = db.fetch_all(
        "SELECT link_type, count(*) as c FROM entity_links GROUP BY link_type ORDER BY c DESC"
    )
    for r in rows:
        print(f"    {r['link_type']:35s} {r['c']:>8,}")

    # Quality scores
    print("\n  --- Quality Scores ---")
    for table in ['drugs', 'clinical_trials', 'pubmed_articles', 'companies']:
        r = db.fetch_one(f"""
            SELECT avg(quality_score) as avg_q,
                   min(quality_score) as min_q,
                   count(*) FILTER (WHERE quality_score IS NULL) as nulls
            FROM {table}
        """)
        avg_q = f"{r['avg_q']:.3f}" if r['avg_q'] else "N/A"
        print(f"    {table:25s} avg={avg_q}  nulls={r['nulls']}")

    # Drugs completely unlinked to any TA
    r = db.fetch_one("""
        SELECT count(*) as c FROM drugs d
        WHERE d.therapeutic_area_id IS NULL
        AND NOT EXISTS (
            SELECT 1 FROM entity_links el
            WHERE el.source_entity_id = d.id::text
            AND el.link_type = 'IN_THERAPEUTIC_AREA'
        )
    """)
    print(f"\n  Drugs with zero TA linkage: {r['c']}")


def run():
    db = Database(config.db.dsn)
    db.connect()
    t0 = time.time()

    print("=" * 60)
    print("Market-Zero: Comprehensive Data Quality Fix")
    print("=" * 60)

    fix_literature_drug_linkage(db)
    fix_drug_ta_linkage(db)
    fix_quality_scores(db)
    fix_entity_links_consistency(db)
    refresh_materialized_views(db)
    show_final_report(db)

    elapsed = time.time() - t0
    print(f"\n  Completed in {elapsed:.1f}s")
    db.close()


if __name__ == "__main__":
    run()
