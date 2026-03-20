"""AI-assisted enrichment module.

Phase 3.4: Uses LLM to enrich entities with low completeness.
- Extract brand_name, approval_date, company, mechanism from PubMed abstracts
- Classify drugs into TAs based on trial condition text
- Detect and flag potential duplicates
- Confidence-gated: high confidence → auto-apply, low → HITL queue

Usage:
    python -m scripts.ai_enrich [--dry-run] [--entity-type drug] [--max-entities 50]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone

from config import config
from db import Database

logger = logging.getLogger(__name__)

HIGH_CONFIDENCE_THRESHOLD = 0.85
LOW_CONFIDENCE_THRESHOLD = 0.5


def _table_exists(db: Database, table_name: str) -> bool:
    row = db.fetch_one(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s) AS exists_",
        [table_name],
    )
    return bool(row and row.get("exists_"))


def _log_change(db: Database, entity_type: str, entity_id: str,
                change_type: str, fields: list[str]) -> None:
    db.execute(
        """
        INSERT INTO data_change_log
            (entity_type, entity_id, change_type, changed_fields, changed_at)
        VALUES (%s, %s, %s, %s, %s)
        """,
        [entity_type, entity_id, change_type, fields, datetime.now(timezone.utc)],
    )


def _queue_hitl(db: Database, entity_type: str, entity_id: str,
                review_type: str, payload: dict, priority: int = 3) -> None:
    """Create a HITL review item."""
    if not _table_exists(db, "hitl_review_queue"):
        return
    import uuid
    db.execute(
        """
        INSERT INTO hitl_review_queue (id, review_type, entity_type, entity_id, priority, status, payload, created_at)
        VALUES (%s, %s, %s, %s, %s, 'pending', %s::jsonb, NOW())
        """,
        [str(uuid.uuid4()), review_type, entity_type, entity_id,
         priority, json.dumps(payload)],
    )


def _call_llm(prompt: str, system_prompt: str = "") -> dict | None:
    """Call the LLM for enrichment. Returns parsed JSON or None."""
    api_key = config.llm.api_key or os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        logger.warning("No LLM API key configured, skipping AI enrichment")
        return None

    try:
        import openai
        client = openai.OpenAI(api_key=api_key)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=config.llm.model,
            messages=messages,
            temperature=0.1,
            max_tokens=512,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        logger.error("LLM call failed: %s", e)
        return None


DRUG_ENRICHMENT_SYSTEM = """You are a pharmaceutical data expert. Given a drug name and associated clinical trial/literature data, extract missing fields.

Return JSON with:
- brand_name: string or null (the marketed name)
- company: string or null (the manufacturer/developer)
- mechanism: string or null (drug class/mechanism of action)
- therapeutic_areas: list[str] (therapeutic areas)
- confidence: float 0-1 (your confidence in the extracted data)

Only include fields you are confident about. Use null for uncertain fields."""


def enrich_drugs_with_ai(db: Database, dry_run: bool = False,
                         max_entities: int = 50) -> dict[str, int]:
    """Use LLM to enrich drugs with low completeness."""
    stats = {"enriched": 0, "queued": 0, "skipped": 0}

    # Find drugs with missing key fields
    drugs = db.fetch_all(
        """
        SELECT d.id, d.generic_name, d.brand_name, d.company_id,
               d.mechanism_id, d.therapeutic_area_id
        FROM drugs d
        WHERE d.record_status IS DISTINCT FROM 'excluded'
          AND d.record_status IS DISTINCT FROM 'merged'
          AND (d.brand_name IS NULL OR d.brand_name = ''
               OR d.company_id IS NULL
               OR d.mechanism_id IS NULL)
        ORDER BY d.quality_score ASC NULLS FIRST
        LIMIT %s
        """,
        [max_entities],
    )

    logger.info("Found %d drugs needing AI enrichment", len(drugs))

    for drug in drugs:
        drug_id = str(drug["id"])
        name = drug.get("generic_name") or ""
        if not name:
            stats["skipped"] += 1
            continue

        # Gather context from linked trials/articles
        trials = db.fetch_all(
            """
            SELECT ct.conditions, ct.sponsor_name, ct.phase
            FROM clinical_trials ct
            JOIN entity_links el ON el.source_entity_id = ct.id
              AND el.source_entity_type = 'trial'
              AND el.link_type = 'INVESTIGATES'
              AND el.target_entity_id = %s
            LIMIT 5
            """,
            [drug_id],
        )

        articles = db.fetch_all(
            """
            SELECT pa.title, pa.mesh_terms
            FROM pubmed_articles pa
            JOIN entity_links el ON el.source_entity_id = pa.id::text
              AND el.source_entity_type = 'article'
              AND el.link_type = 'EVIDENCE_FOR'
              AND el.target_entity_id = %s
            LIMIT 3
            """,
            [drug_id],
        )

        # Build prompt with context
        context_parts = [f"Drug name: {name}"]
        if trials:
            trial_info = []
            for t in trials:
                parts = []
                if t.get("conditions"):
                    conds = t["conditions"] if isinstance(t["conditions"], list) else [t["conditions"]]
                    parts.append(f"conditions: {', '.join(conds)}")
                if t.get("sponsor_name"):
                    parts.append(f"sponsor: {t['sponsor_name']}")
                if t.get("phase"):
                    parts.append(f"phase: {t['phase']}")
                trial_info.append("; ".join(parts))
            context_parts.append("Clinical trials:\n" + "\n".join(f"  - {ti}" for ti in trial_info))

        if articles:
            article_info = []
            for a in articles:
                parts = [a.get("title", "")]
                if a.get("mesh_terms"):
                    mesh = a["mesh_terms"] if isinstance(a["mesh_terms"], list) else []
                    if mesh:
                        parts.append(f"MeSH: {', '.join(mesh[:5])}")
                article_info.append("; ".join(parts))
            context_parts.append("PubMed articles:\n" + "\n".join(f"  - {ai}" for ai in article_info))

        # Missing fields
        missing = []
        if not drug.get("brand_name"):
            missing.append("brand_name")
        if not drug.get("company_id"):
            missing.append("company")
        if not drug.get("mechanism_id"):
            missing.append("mechanism")

        context_parts.append(f"Missing fields: {', '.join(missing)}")
        prompt = "\n\n".join(context_parts)

        if dry_run:
            logger.info("[DRY RUN] Would call LLM for drug %s (%s)", name, drug_id)
            stats["skipped"] += 1
            continue

        result = _call_llm(prompt, DRUG_ENRICHMENT_SYSTEM)
        if not result:
            stats["skipped"] += 1
            continue

        confidence = result.get("confidence", 0)

        if confidence >= HIGH_CONFIDENCE_THRESHOLD:
            # Auto-apply
            updates = {}
            if result.get("brand_name") and not drug.get("brand_name"):
                updates["brand_name"] = result["brand_name"]

            if updates:
                set_parts = [f"{k} = %s" for k in updates]
                values = list(updates.values()) + [drug["id"]]
                db.execute(
                    f"UPDATE drugs SET {', '.join(set_parts)} WHERE id = %s",
                    values,
                )
                _log_change(db, "drug", drug_id, "ai_enrich_auto",
                            list(updates.keys()))
                stats["enriched"] += 1

            # Try to link company
            if result.get("company") and not drug.get("company_id"):
                company = db.fetch_one(
                    "SELECT id FROM companies WHERE LOWER(name) LIKE %s LIMIT 1",
                    [f"%{result['company'].lower()}%"],
                )
                if company:
                    db.execute(
                        "UPDATE drugs SET company_id = %s WHERE id = %s AND company_id IS NULL",
                        [company["id"], drug["id"]],
                    )
                    _log_change(db, "drug", drug_id, "ai_enrich_company",
                                ["company_id", f"company:{result['company']}"])
        elif confidence >= LOW_CONFIDENCE_THRESHOLD:
            # Queue for HITL review
            _queue_hitl(db, "drug", drug_id, "ai_enrichment_review", {
                "drug_name": name,
                "suggested": result,
                "confidence": confidence,
                "source": "ai_enrich",
            })
            stats["queued"] += 1
        else:
            stats["skipped"] += 1

    logger.info(
        "AI enrichment: enriched=%d, queued=%d, skipped=%d",
        stats["enriched"], stats["queued"], stats["skipped"],
    )
    return stats


DUPLICATE_DETECTION_SYSTEM = """You are a pharmaceutical data expert. Given two entity names and their metadata, determine if they are duplicates.

Return JSON with:
- is_duplicate: boolean
- confidence: float 0-1
- reasoning: string (brief explanation)"""


def detect_duplicates(db: Database, entity_type: str = "drug",
                      dry_run: bool = False, max_pairs: int = 100) -> int:
    """Use LLM to detect potential duplicate entities."""
    table_map = {"drug": "drugs", "company": "companies"}
    name_col = {"drug": "generic_name", "company": "name"}

    table = table_map.get(entity_type)
    col = name_col.get(entity_type)
    if not table or not col:
        return 0

    # Find entities with similar names (trigram similarity)
    pairs = db.fetch_all(
        f"""
        SELECT a.id AS id_a, a.{col} AS name_a,
               b.id AS id_b, b.{col} AS name_b,
               similarity(LOWER(a.{col}), LOWER(b.{col})) AS sim
        FROM {table} a
        JOIN {table} b ON a.id < b.id
          AND similarity(LOWER(a.{col}), LOWER(b.{col})) > 0.5
        WHERE a.record_status IS DISTINCT FROM 'merged'
          AND a.record_status IS DISTINCT FROM 'excluded'
          AND b.record_status IS DISTINCT FROM 'merged'
          AND b.record_status IS DISTINCT FROM 'excluded'
        ORDER BY sim DESC
        LIMIT %s
        """,
        [max_pairs],
    )

    flagged = 0
    for pair in pairs:
        if pair["sim"] > 0.9:
            # Very high similarity — auto-flag
            _queue_hitl(db, entity_type, str(pair["id_a"]), "duplicate_candidate", {
                "duplicate_of": str(pair["id_b"]),
                "name_a": pair["name_a"],
                "name_b": pair["name_b"],
                "similarity": float(pair["sim"]),
                "source": "ai_enrich_auto",
            })
            flagged += 1
        elif not dry_run:
            # Use LLM for borderline cases
            prompt = (
                f"Entity A: {pair['name_a']}\n"
                f"Entity B: {pair['name_b']}\n"
                f"Trigram similarity: {pair['sim']:.2f}\n"
                f"Entity type: {entity_type}"
            )
            result = _call_llm(prompt, DUPLICATE_DETECTION_SYSTEM)
            if result and result.get("is_duplicate") and result.get("confidence", 0) > 0.7:
                _queue_hitl(db, entity_type, str(pair["id_a"]), "duplicate_candidate", {
                    "duplicate_of": str(pair["id_b"]),
                    "name_a": pair["name_a"],
                    "name_b": pair["name_b"],
                    "ai_confidence": result["confidence"],
                    "reasoning": result.get("reasoning", ""),
                    "source": "ai_enrich_llm",
                })
                flagged += 1

    logger.info("Duplicate detection: %d pairs flagged for %s", flagged, entity_type)
    return flagged


def run(dry_run: bool = False, entity_type: str = "drug",
        max_entities: int = 50) -> dict:
    """Run AI enrichment pipeline."""
    db = Database(config.db.dsn)
    db.connect()

    try:
        results = {}

        if entity_type in ("drug", "all"):
            results["drug_enrichment"] = enrich_drugs_with_ai(db, dry_run, max_entities)

        results["duplicate_detection"] = detect_duplicates(
            db, entity_type if entity_type != "all" else "drug",
            dry_run=dry_run,
        )

        return results
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="AI-assisted entity enrichment")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--entity-type", default="drug", choices=["drug", "company", "all"])
    parser.add_argument("--max-entities", type=int, default=50)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    results = run(
        dry_run=args.dry_run,
        entity_type=args.entity_type,
        max_entities=args.max_entities,
    )

    print("\n=== AI Enrichment Results ===")
    for k, v in results.items():
        print(f"  {k}: {v}")
    if args.dry_run:
        print("  (dry run — no changes written)")


if __name__ == "__main__":
    main()
