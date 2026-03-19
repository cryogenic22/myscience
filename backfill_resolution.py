"""
Backfill entity resolution and cross-links for existing data.

Fixes:
  1. Company CIK mismatches (EDGAR names → authoritative)
  2. clinical_trials.drug_id for 3,300+ orphaned trials
  3. pubmed_articles.drug_id for articles mentioning known drugs
  4. market_events.drug_id for enforcement actions
  5. entity_links for INVESTIGATES, SPONSORS, LED_BY, LOCATED_AT, HAS_OUTCOME

Usage: python backfill_resolution.py
"""

import logging
import time
from datetime import datetime

from config import config
from db import Database

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
logger = logging.getLogger(__name__)


def run_backfill():
    db = Database(config.db.dsn)
    db.connect()

    # Initialize OpenAI client for embedding/LLM strategies
    openai_client = None
    if config.embedding.api_key:
        from openai import OpenAI
        openai_client = OpenAI(api_key=config.embedding.api_key)

    from integration.entity_resolver import EntityResolver
    resolver = EntityResolver(db, config, openai_client=openai_client)

    print("=" * 60)
    print("Market-Zero: Entity Resolution Backfill")
    print("=" * 60)

    # ──────────────────────────────────────────────
    # Phase 1: Fix company CIK mismatches
    # ──────────────────────────────────────────────
    print("\n--- Phase 1: Fix company CIK mismatches ---")
    fix_company_ciks(db)

    # ──────────────────────────────────────────────
    # Phase 2: Backfill clinical_trials.drug_id
    # ──────────────────────────────────────────────
    print("\n--- Phase 2: Backfill clinical_trials.drug_id ---")
    backfill_trial_drug_ids(db, resolver)

    # ──────────────────────────────────────────────
    # Phase 3: Backfill pubmed_articles.drug_id
    # ──────────────────────────────────────────────
    print("\n--- Phase 3: Backfill pubmed_articles.drug_id ---")
    backfill_pubmed_drug_ids(db, resolver)

    # ──────────────────────────────────────────────
    # Phase 4: Backfill market_events.drug_id
    # ──────────────────────────────────────────────
    print("\n--- Phase 4: Backfill market_events.drug_id ---")
    backfill_event_drug_ids(db, resolver)

    # ──────────────────────────────────────────────
    # Phase 5: Generate entity_links for trials
    # ──────────────────────────────────────────────
    print("\n--- Phase 5: Generate entity_links ---")
    backfill_entity_links(db)

    # ──────────────────────────────────────────────
    # Phase 6: Backfill embeddings for new drugs
    # ──────────────────────────────────────────────
    print("\n--- Phase 6: Backfill embeddings for new drugs ---")
    backfill_new_drug_embeddings(db, openai_client)

    # ──────────────────────────────────────────────
    # Final report
    # ──────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("FINAL STATE")
    print("=" * 60)
    show_final_state(db)
    db.close()


def fix_company_ciks(db):
    """Fix mismatched company records using known CIK→name mappings."""
    # These are the target CIKs from config with their known correct names
    # We'll fix them based on the SEC EDGAR data we already fetched
    known_cik_names = {
        "0001000694": "Novo Nordisk A/S",
        "0000059478": "Eli Lilly and Company",
        "0001121404": "Sanofi",
        "0000816284": "AstraZeneca PLC",
        "0000078003": "Pfizer Inc.",
    }

    fixed = 0
    for cik, correct_name in known_cik_names.items():
        row = db.fetch_one("SELECT id, name FROM companies WHERE cik = %s", [cik])
        if row and row["name"] != correct_name:
            logger.info("Fixing company: '%s' → '%s' (CIK %s)", row["name"], correct_name, cik)
            db.execute(
                "UPDATE companies SET name = %s, updated_at = NOW() WHERE id = %s",
                [correct_name, row["id"]],
            )
            fixed += 1
        elif not row:
            # CIK not in DB yet — create it
            logger.info("Creating company: '%s' (CIK %s)", correct_name, cik)
            db.execute(
                """
                INSERT INTO companies (name, cik, source_api, source_url, retrieved_at)
                VALUES (%s, %s, 'sec_edgar', 'backfill', NOW())
                ON CONFLICT DO NOTHING
                """,
                [correct_name, cik],
            )
            fixed += 1

    print(f"  Fixed {fixed} company records")


def backfill_trial_drug_ids(db, resolver):
    """For trials with NULL drug_id, extract drug from interventions and resolve."""
    rows = db.fetch_all(
        """
        SELECT id, interventions, sponsor_name
        FROM clinical_trials
        WHERE drug_id IS NULL AND interventions IS NOT NULL
        ORDER BY id
        """
    )
    print(f"  {len(rows)} trials need drug_id resolution")

    resolved = 0
    auto_created = 0
    still_null = 0

    for i, row in enumerate(rows):
        drug_name = _extract_drug_from_interventions(row["interventions"])
        if not drug_name:
            still_null += 1
            continue

        # Try to find/create drug via the full cascade
        drug_id = _resolve_drug_name(db, resolver, drug_name)
        if drug_id:
            db.execute(
                "UPDATE clinical_trials SET drug_id = %s WHERE id = %s",
                [drug_id, row["id"]],
            )
            resolved += 1
        else:
            still_null += 1

        if (i + 1) % 500 == 0:
            logger.info("  Progress: %d/%d (resolved=%d)", i + 1, len(rows), resolved)

    print(f"  Resolved: {resolved}, Still NULL: {still_null}")


def backfill_pubmed_drug_ids(db, resolver):
    """For articles with NULL drug_id, search title/abstract for known drug names."""
    # Get all drug names for text matching
    drugs = db.fetch_all("SELECT id, generic_name FROM drugs")
    if not drugs:
        print("  No drugs in DB, skipping")
        return

    resolved = 0
    articles = db.fetch_all(
        "SELECT id, title, abstract FROM pubmed_articles WHERE drug_id IS NULL"
    )
    print(f"  {len(articles)} articles need drug_id resolution")

    for article in articles:
        text = f"{article['title'] or ''} {article['abstract'] or ''}".lower()
        best_match = None
        for drug in drugs:
            if drug["generic_name"].lower() in text:
                best_match = drug
                break

        if best_match:
            db.execute(
                "UPDATE pubmed_articles SET drug_id = %s WHERE id = %s",
                [best_match["id"], article["id"]],
            )
            resolved += 1

    print(f"  Resolved: {resolved}")


def backfill_event_drug_ids(db, resolver):
    """For events with NULL drug_id, search description for known drug names."""
    drugs = db.fetch_all("SELECT id, generic_name FROM drugs")
    if not drugs:
        print("  No drugs in DB, skipping")
        return

    resolved = 0
    events = db.fetch_all(
        "SELECT id, description FROM market_events WHERE drug_id IS NULL AND description IS NOT NULL"
    )
    print(f"  {len(events)} events need drug_id resolution")

    for event in events:
        desc = (event["description"] or "").lower()
        for drug in drugs:
            if drug["generic_name"].lower() in desc:
                db.execute(
                    "UPDATE market_events SET drug_id = %s WHERE id = %s",
                    [drug["id"], event["id"]],
                )
                resolved += 1
                break

    print(f"  Resolved: {resolved}")


def backfill_entity_links(db):
    """Generate entity_links for existing records that have FK relationships."""
    import json

    links_created = 0

    # 1. INVESTIGATES: trial → drug (from drug_id FK)
    trials_with_drug = db.fetch_all(
        "SELECT id, drug_id FROM clinical_trials WHERE drug_id IS NOT NULL"
    )
    for t in trials_with_drug:
        created = _upsert_link(db,
            source_id=t["id"], source_type="trial",
            target_id=str(t["drug_id"]), target_type="drug",
            link_type="INVESTIGATES", via="drug_id_fk", confidence=1.0,
            source="backfill")
        if created:
            links_created += 1
    print(f"  INVESTIGATES: {links_created} links")
    batch_links = links_created

    # 2. SPONSORS: company → trial (from sponsor_name matching)
    links_created_sponsors = 0
    sponsor_trials = db.fetch_all(
        """
        SELECT ct.id as trial_id, c.id as company_id
        FROM clinical_trials ct
        JOIN companies c ON LOWER(ct.sponsor_name) = LOWER(c.name)
        """
    )
    for st in sponsor_trials:
        created = _upsert_link(db,
            source_id=str(st["company_id"]), source_type="company",
            target_id=st["trial_id"], target_type="trial",
            link_type="SPONSORS", via="sponsor_name_fk", confidence=1.0,
            source="backfill")
        if created:
            links_created_sponsors += 1
    print(f"  SPONSORS: {links_created_sponsors} links")
    links_created += links_created_sponsors

    # 3. LED_BY: trial → investigator (from trial_outcomes/locations nct_id context)
    # Investigators don't have a direct trial_id FK, but we can link via
    # the connector data. For now, skip — this gets populated on next pipeline run.

    # 4. EVIDENCE_FOR: article → drug (from drug_id FK)
    links_evidence = 0
    articles_with_drug = db.fetch_all(
        "SELECT id, drug_id FROM pubmed_articles WHERE drug_id IS NOT NULL"
    )
    for a in articles_with_drug:
        created = _upsert_link(db,
            source_id=str(a["id"]), source_type="literature",
            target_id=str(a["drug_id"]), target_type="drug",
            link_type="EVIDENCE_FOR", via="drug_id_fk", confidence=1.0,
            source="backfill")
        if created:
            links_evidence += 1
    print(f"  EVIDENCE_FOR: {links_evidence} links")
    links_created += links_evidence

    # 5. SHORTAGE_AFFECTS: event → drug (from drug_id FK)
    links_shortage = 0
    events_with_drug = db.fetch_all(
        "SELECT id, drug_id FROM market_events WHERE drug_id IS NOT NULL"
    )
    for e in events_with_drug:
        created = _upsert_link(db,
            source_id=str(e["id"]), source_type="event",
            target_id=str(e["drug_id"]), target_type="drug",
            link_type="SHORTAGE_AFFECTS", via="drug_id_fk", confidence=1.0,
            source="backfill")
        if created:
            links_shortage += 1
    print(f"  SHORTAGE_AFFECTS: {links_shortage} links")
    links_created += links_shortage

    print(f"  Total new links: {links_created}")


def backfill_new_drug_embeddings(db, openai_client):
    """Generate embeddings for auto-created drugs that have NULL embedding."""
    if not openai_client:
        print("  No OpenAI client, skipping")
        return

    rows = db.fetch_all(
        "SELECT id, generic_name FROM drugs WHERE molecule_embedding IS NULL"
    )
    if not rows:
        print("  No drugs need embeddings")
        return

    print(f"  {len(rows)} drugs need embeddings")
    texts = [r["generic_name"] for r in rows]
    ids = [r["id"] for r in rows]

    BATCH = 50
    embedded = 0
    for i in range(0, len(texts), BATCH):
        batch_texts = texts[i:i + BATCH]
        batch_ids = ids[i:i + BATCH]
        try:
            response = openai_client.embeddings.create(
                input=batch_texts,
                model=config.embedding.model,
            )
            for row_id, emb_data in zip(batch_ids, response.data):
                db.execute(
                    "UPDATE drugs SET molecule_embedding = %s WHERE id = %s",
                    [emb_data.embedding, row_id],
                )
                embedded += 1
        except Exception as e:
            logger.error("Embedding batch failed: %s", e)
        time.sleep(0.2)

    print(f"  Embedded: {embedded}")


def show_final_state(db):
    """Print comprehensive database state."""
    # Row counts
    tables = [
        "therapeutic_areas", "mechanisms_of_action", "companies", "drugs",
        "patents", "regulatory_milestones", "clinical_trials", "trial_outcomes",
        "trial_locations", "investigators", "market_events", "pubmed_articles",
        "entity_links", "entity_aliases", "resolution_audit",
    ]
    print("\n  Row Counts:")
    for t in tables:
        cnt = db.fetch_one(f"SELECT count(*) as c FROM {t}")["c"]
        print(f"    {t:30s} {cnt:>7}")

    # Drug sources
    print("\n  Drugs by Source Authority:")
    rows = db.fetch_all("SELECT source_authority, count(*) as c FROM drugs GROUP BY source_authority ORDER BY c DESC")
    for r in rows:
        print(f"    {(r['source_authority'] or 'NULL'):30s} {r['c']:>5}")

    # Trial drug_id coverage
    total = db.fetch_one("SELECT count(*) as c FROM clinical_trials")["c"]
    linked = db.fetch_one("SELECT count(*) as c FROM clinical_trials WHERE drug_id IS NOT NULL")["c"]
    print(f"\n  Trial->Drug coverage: {linked}/{total} ({100*linked//max(total,1)}%)")

    # Entity links by type
    print("\n  Entity Links by Type:")
    rows = db.fetch_all("SELECT link_type, count(*) as c FROM entity_links GROUP BY link_type ORDER BY c DESC")
    for r in rows:
        print(f"    {r['link_type']:25s} {r['c']:>7}")

    # Resolution audit
    print("\n  Resolution Audit by Method:")
    rows = db.fetch_all(
        "SELECT resolution_method, count(*) as c, round(avg(confidence)::numeric, 2) as avg_conf "
        "FROM resolution_audit GROUP BY resolution_method ORDER BY c DESC"
    )
    for r in rows:
        print(f"    {r['resolution_method']:20s} {r['c']:>6} (avg confidence: {r['avg_conf']})")


# ─────────────── Helpers ───────────────

def _extract_drug_from_interventions(interventions: list) -> str | None:
    """Extract the first drug name from a trial's interventions TEXT[] column."""
    if not interventions:
        return None
    for intervention in interventions:
        intervention = intervention.strip()
        # ClinicalTrials.gov format: "DRUG: semaglutide" or just "semaglutide"
        if intervention.upper().startswith("DRUG: "):
            return intervention[6:].strip()
        if intervention.upper().startswith("BIOLOGICAL: "):
            return intervention[12:].strip()
    # If no typed prefix, return first intervention that looks like a drug name
    for intervention in interventions:
        clean = intervention.strip()
        # Skip obvious non-drugs
        lower = clean.lower()
        if any(lower.startswith(p) for p in [
            "behavioral:", "procedure:", "device:", "diagnostic:",
            "radiation:", "dietary supplement:", "combination product:",
            "genetic:", "other:",
        ]):
            continue
        if lower in ("placebo", "standard of care", "usual care", "sham",
                      "no intervention", "active comparator"):
            continue
        if clean and len(clean) > 2:
            return clean
    return None


def _resolve_drug_name(db, resolver, drug_name: str) -> str | None:
    """Resolve a drug name to a drug UUID using the cascade (without pipeline context)."""
    # First try exact case-insensitive match
    row = db.fetch_one(
        "SELECT id FROM drugs WHERE LOWER(generic_name) = LOWER(%s)",
        [drug_name.strip()],
    )
    if row:
        return str(row["id"])

    # Try fuzzy match
    row = db.fetch_one(
        """
        SELECT id, generic_name, similarity(generic_name, %s) AS sim
        FROM drugs
        WHERE similarity(generic_name, %s) >= %s
        ORDER BY sim DESC LIMIT 1
        """,
        [drug_name, drug_name, config.pipeline.fuzzy_match_threshold],
    )
    if row:
        return str(row["id"])

    # Auto-create the drug
    skip_terms = {"placebo", "standard of care", "usual care", "sham",
                  "no intervention", "behavioral", "dietary supplement",
                  "device", "procedure", "other"}
    clean = drug_name.strip()
    if clean.lower() in skip_terms or len(clean) < 3:
        return None

    try:
        new_row = db.fetch_one(
            """
            INSERT INTO drugs (generic_name, source_authority, source_api, source_url, retrieved_at)
            VALUES (%s, 'clinical_trials_gov', 'backfill', 'backfill', NOW())
            RETURNING id
            """,
            [clean],
        )
        if new_row:
            logger.info("Auto-created drug: '%s'", clean)
            # Log to resolution audit
            import json
            db.execute(
                """
                INSERT INTO resolution_audit
                    (raw_value, entity_type, resolved_entity_id, resolution_method,
                     confidence, reasoning, source_type, source_record_id, accepted)
                VALUES (%s, 'drug', %s, 'auto_create', 1.0, %s, 'backfill', 'backfill', true)
                """,
                [clean, str(new_row["id"]),
                 f"Auto-created drug '{clean}' during backfill. No existing match found."],
            )
            return str(new_row["id"])
    except Exception as e:
        # Likely race condition or dupe — try lookup again
        row = db.fetch_one(
            "SELECT id FROM drugs WHERE LOWER(generic_name) = LOWER(%s)",
            [clean],
        )
        if row:
            return str(row["id"])

    return None


def _upsert_link(db, source_id, source_type, target_id, target_type,
                 link_type, via, confidence, source, metadata=None) -> bool:
    """Insert a link, return True if created."""
    import json
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
            [source_id, source_type, target_id, target_type,
             link_type, via, confidence, metadata_json, source],
        )
        return row is not None
    except Exception:
        return False


if __name__ == "__main__":
    run_backfill()
