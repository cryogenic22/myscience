"""
Batch processing of unresolved entities.

Two phases:
  Phase 0: Exact-match sweep — resolve entities that now match drugs/companies
           in the DB using mention normalization (e.g., "SEMAGLUTIDE 0.5 MG
           INJECTION" → "semaglutide" → drugs.generic_name exact match).

  Phase 1 (tiered):
    Tier 1: Auto-resolve high confidence (>= 0.85) → create alias + mark resolved
    Tier 2: Medium confidence (0.60-0.85) → re-run fuzzy/embedding resolution
    Tier 3: Low confidence (< 0.60) → create HITL review items

Usage: python process_unresolved.py
"""

import json
import logging

from config import config
from db import Database

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
logger = logging.getLogger(__name__)


# ============================================================
# Phase 0: Exact-match sweep
# ============================================================


def exact_match_sweep(db, domain_pack=None, batch_size=500) -> dict:
    """
    Resolve unresolved entities via exact match against current DB state.

    Uses MentionNormalizer from domain pack to clean raw_value before matching.
    Runs BEFORE the tiered processing so the easy wins are handled first.

    Returns {"drugs_resolved": N, "companies_resolved": N, "other_resolved": N, "skipped": N}
    """
    # Get normalizers from domain pack or import directly
    normalize_drug = None
    normalize_company = None
    if domain_pack and domain_pack.mention_normalizers:
        drug_normalizer = domain_pack.mention_normalizers.get("drug")
        company_normalizer = domain_pack.mention_normalizers.get("company")
        if drug_normalizer:
            normalize_drug = drug_normalizer.normalize_fn
        if company_normalizer:
            normalize_company = company_normalizer.normalize_fn

    if not normalize_drug or not normalize_company:
        try:
            from domain.pharma.mention_normalizer import (
                normalize_drug_mention,
                normalize_company_mention,
            )
            normalize_drug = normalize_drug or normalize_drug_mention
            normalize_company = normalize_company or normalize_company_mention
        except ImportError:
            logger.warning("No mention normalizers available; sweep will use raw values")
            normalize_drug = normalize_drug or (lambda x: x.strip().lower())
            normalize_company = normalize_company or (lambda x: x.strip().lower())

    stats = {"drugs_resolved": 0, "companies_resolved": 0, "other_resolved": 0, "skipped": 0}
    offset = 0

    while True:
        batch = db.fetch_all(
            """
            SELECT id, raw_value, record_type, source_type
            FROM unresolved_entities
            WHERE resolved = FALSE AND (status IS NULL OR status = 'pending')
            ORDER BY id
            LIMIT %s OFFSET %s
            """,
            [batch_size, offset],
        )
        if not batch:
            break

        for row in batch:
            record_type = row["record_type"]
            raw_value = row["raw_value"]

            if record_type == "drug":
                normalized = normalize_drug(raw_value)
                entity_id = _find_drug_match(db, normalized, raw_value)
                if entity_id:
                    _resolve_exact_match(db, row, entity_id)
                    stats["drugs_resolved"] += 1
                else:
                    stats["skipped"] += 1

            elif record_type == "company":
                normalized = normalize_company(raw_value)
                entity_id = _find_company_match(db, normalized, raw_value)
                if entity_id:
                    _resolve_exact_match(db, row, entity_id)
                    stats["companies_resolved"] += 1
                else:
                    stats["skipped"] += 1

            else:
                stats["skipped"] += 1

        logger.info(
            "Sweep batch %d: processed %d rows (drugs=%d, companies=%d, skipped=%d)",
            offset // batch_size + 1, len(batch),
            stats["drugs_resolved"], stats["companies_resolved"], stats["skipped"],
        )

        # If this batch was smaller than batch_size, we're done
        if len(batch) < batch_size:
            break
        offset += batch_size

    total = stats["drugs_resolved"] + stats["companies_resolved"] + stats["other_resolved"]
    logger.info("Exact-match sweep complete: %d resolved, %d skipped", total, stats["skipped"])
    return stats


def _find_drug_match(db, normalized: str, raw_value: str):
    """Try to find a drug by normalized name, raw value, or alias."""
    if not normalized:
        return None

    # 1. Exact match on normalized generic_name
    match = db.fetch_one(
        "SELECT id FROM drugs WHERE LOWER(generic_name) = LOWER(%s) AND record_status != 'superseded'",
        [normalized],
    )
    if match:
        return str(match["id"])

    # 2. Try raw value (in case normalization was too aggressive)
    if raw_value.strip().lower() != normalized.lower():
        match = db.fetch_one(
            "SELECT id FROM drugs WHERE LOWER(generic_name) = LOWER(%s) AND record_status != 'superseded'",
            [raw_value.strip()],
        )
        if match:
            return str(match["id"])

    # 3. Check entity_aliases
    match = db.fetch_one(
        """
        SELECT entity_id FROM entity_aliases
        WHERE entity_type = 'drug' AND LOWER(alias_text) = LOWER(%s)
        LIMIT 1
        """,
        [normalized],
    )
    if match:
        return str(match["entity_id"])

    # Also check alias with raw value
    if raw_value.strip().lower() != normalized.lower():
        match = db.fetch_one(
            """
            SELECT entity_id FROM entity_aliases
            WHERE entity_type = 'drug' AND LOWER(alias_text) = LOWER(%s)
            LIMIT 1
            """,
            [raw_value.strip()],
        )
        if match:
            return str(match["entity_id"])

    return None


def _find_company_match(db, normalized: str, raw_value: str):
    """Try to find a company by normalized name, raw value, or alias."""
    if not normalized:
        return None

    # 1. Exact match on normalized name
    match = db.fetch_one(
        "SELECT id FROM companies WHERE LOWER(name) = LOWER(%s) AND record_status != 'superseded'",
        [normalized],
    )
    if match:
        return str(match["id"])

    # 2. Try raw value
    if raw_value.strip().lower() != normalized.lower():
        match = db.fetch_one(
            "SELECT id FROM companies WHERE LOWER(name) = LOWER(%s) AND record_status != 'superseded'",
            [raw_value.strip()],
        )
        if match:
            return str(match["id"])

    # 3. Check entity_aliases
    match = db.fetch_one(
        """
        SELECT entity_id FROM entity_aliases
        WHERE entity_type = 'company' AND LOWER(alias_text) = LOWER(%s)
        LIMIT 1
        """,
        [normalized],
    )
    if match:
        return str(match["entity_id"])

    return None


def _resolve_exact_match(db, row, entity_id: str):
    """Create alias, mark resolved, and log to resolution_audit."""
    raw_value = row["raw_value"]
    entity_type = row["record_type"]

    # Create alias for future resolution
    db.execute(
        """
        INSERT INTO entity_aliases (entity_type, entity_id, alias_text, source_type, confidence, verified)
        VALUES (%s, %s, %s, 'exact_match_sweep', 1.0, FALSE)
        ON CONFLICT (entity_type, alias_text, source_type) DO NOTHING
        """,
        [entity_type, entity_id, raw_value],
    )

    # Mark as resolved
    db.execute(
        """
        UPDATE unresolved_entities
        SET resolved = TRUE,
            status = 'resolved',
            resolution_method = 'exact_match_sweep'
        WHERE id = %s
        """,
        [row["id"]],
    )

    # Log to resolution audit
    db.execute(
        """
        INSERT INTO resolution_audit
            (raw_value, entity_type, resolved_entity_id, resolution_method,
             confidence, reasoning, source_type, source_record_id, accepted)
        VALUES (%s, %s, %s, 'exact_match_sweep', 1.0, %s, %s, %s, true)
        """,
        [
            raw_value, entity_type, entity_id,
            f"Exact match after mention normalization (sweep)",
            row.get("source_type", "unknown"),
            str(row["id"]),
        ],
    )

    logger.debug("Sweep resolved: '%s' → %s (%s)", raw_value, entity_id, entity_type)


def process_unresolved(db, resolver=None):
    """Process unresolved entities in three tiers."""
    pending = db.fetch_all(
        """
        SELECT id, raw_value, record_type, source_type,
               suggested_match_id, suggested_confidence,
               llm_analysis, llm_confidence, candidates_considered
        FROM unresolved_entities
        WHERE resolved = FALSE AND (status IS NULL OR status = 'pending')
        ORDER BY suggested_confidence DESC NULLS LAST
        """
    )
    print(f"  {len(pending)} unresolved entities to process")

    stats = {"tier1_resolved": 0, "tier2_resolved": 0, "tier3_hitl": 0, "skipped": 0}

    for row in pending:
        confidence = row.get("suggested_confidence") or row.get("llm_confidence") or 0.0
        suggested_id = row.get("suggested_match_id")

        if confidence >= 0.85 and suggested_id:
            # Tier 1: Auto-resolve
            _auto_resolve(db, row, confidence)
            stats["tier1_resolved"] += 1

        elif confidence >= 0.60:
            # Tier 2: Re-run resolution with current (larger) DB
            resolved = _retry_resolution(db, resolver, row)
            if resolved:
                stats["tier2_resolved"] += 1
            else:
                _create_hitl_item(db, row, confidence)
                stats["tier3_hitl"] += 1

        else:
            # Tier 3: Low confidence → HITL
            _create_hitl_item(db, row, confidence)
            stats["tier3_hitl"] += 1

    return stats


def _auto_resolve(db, row, confidence):
    """Create alias and mark entity as resolved."""
    entity_id = row["suggested_match_id"]
    raw_value = row["raw_value"]
    entity_type = row["record_type"]

    # Create alias for future resolution
    db.execute(
        """
        INSERT INTO entity_aliases (entity_type, entity_id, alias_text, source_type, confidence, verified)
        VALUES (%s, %s, %s, 'auto_resolve', %s, FALSE)
        ON CONFLICT (entity_type, alias_text, source_type) DO NOTHING
        """,
        [entity_type, entity_id, raw_value, confidence],
    )

    # Mark as resolved
    db.execute(
        """
        UPDATE unresolved_entities
        SET resolved = TRUE,
            status = 'resolved',
            resolution_method = 'auto_resolve_high_confidence'
        WHERE id = %s
        """,
        [row["id"]],
    )

    # Log to resolution audit
    db.execute(
        """
        INSERT INTO resolution_audit
            (raw_value, entity_type, resolved_entity_id, resolution_method,
             confidence, reasoning, source_type, source_record_id, accepted)
        VALUES (%s, %s, %s, 'auto_resolve', %s, %s, %s, %s, true)
        """,
        [
            raw_value, entity_type, entity_id, confidence,
            f"Auto-resolved from unresolved queue (confidence={confidence:.2f})",
            row.get("source_type", "unknown"),
            str(row["id"]),
        ],
    )

    logger.info("Auto-resolved: '%s' → %s (confidence=%.2f)", raw_value, entity_id, confidence)


def _retry_resolution(db, resolver, row):
    """Re-run entity resolution with current DB state."""
    if not resolver:
        return False

    raw_value = row["raw_value"]
    entity_type = row["record_type"]

    if entity_type == "drug":
        # Try exact match first
        match = db.fetch_one(
            "SELECT id FROM drugs WHERE LOWER(generic_name) = LOWER(%s)",
            [raw_value.strip()],
        )
        if match:
            _auto_resolve(db, {**row, "suggested_match_id": str(match["id"]),
                               "suggested_confidence": 0.90}, 0.90)
            return True

        # Try fuzzy match
        match = db.fetch_one(
            """
            SELECT id, generic_name, similarity(generic_name, %s) AS sim
            FROM drugs
            WHERE similarity(generic_name, %s) >= %s
            ORDER BY sim DESC LIMIT 1
            """,
            [raw_value, raw_value, 0.75],  # Lower threshold for retry
        )
        if match:
            _auto_resolve(db, {**row, "suggested_match_id": str(match["id"]),
                               "suggested_confidence": float(match["sim"])},
                          float(match["sim"]))
            return True

    elif entity_type == "company":
        match = db.fetch_one(
            "SELECT id FROM companies WHERE LOWER(name) = LOWER(%s)",
            [raw_value.strip()],
        )
        if match:
            _auto_resolve(db, {**row, "suggested_match_id": str(match["id"]),
                               "suggested_confidence": 0.95}, 0.95)
            return True

    return False


def _create_hitl_item(db, row, confidence):
    """Create a HITL review item for manual resolution."""
    payload = {
        "raw_value": row["raw_value"],
        "record_type": row["record_type"],
        "source_type": row.get("source_type", "unknown"),
        "suggested_match_id": row.get("suggested_match_id"),
        "confidence": confidence,
        "llm_analysis": row.get("llm_analysis"),
        "candidates": row.get("candidates_considered"),
    }

    db.execute(
        """
        INSERT INTO hitl_review_queue
            (review_type, entity_type, entity_id, priority, payload)
        VALUES ('entity_resolution', %s, %s, %s, %s::jsonb)
        ON CONFLICT DO NOTHING
        """,
        [
            row["record_type"],
            row.get("suggested_match_id") or str(row["id"]),
            max(10, int(60 - confidence * 50)),  # Higher confidence → lower priority number
            json.dumps(payload),
        ],
    )

    db.execute(
        "UPDATE unresolved_entities SET status = 'hitl_queued' WHERE id = %s",
        [row["id"]],
    )


if __name__ == "__main__":
    db = Database(config.db.dsn)
    db.connect()

    # Load domain pack for mention normalizers
    domain_pack = None
    try:
        from domain.pharma.pack import get_pharma_pack
        domain_pack = get_pharma_pack()
    except Exception as e:
        logger.warning("Could not load pharma domain pack: %s", e)

    # Initialize resolver for tier 2
    openai_client = None
    if config.embedding.api_key:
        try:
            from openai import OpenAI
            openai_client = OpenAI(api_key=config.embedding.api_key)
        except ImportError:
            pass

    resolver = None
    try:
        from integration.entity_resolver import EntityResolver
        resolver = EntityResolver(db, config, openai_client=openai_client, domain_pack=domain_pack)
    except Exception as e:
        logger.warning("Could not initialize resolver: %s", e)

    print("=" * 60)
    print("Market-Zero: Unresolved Entity Processing")
    print("=" * 60)

    # Phase 0: Exact-match sweep (fast, no ML needed)
    print("\n--- Phase 0: Exact-Match Sweep ---")
    sweep_stats = exact_match_sweep(db, domain_pack=domain_pack)
    print(f"  Drugs resolved:     {sweep_stats['drugs_resolved']}")
    print(f"  Companies resolved: {sweep_stats['companies_resolved']}")
    print(f"  Skipped:            {sweep_stats['skipped']}")

    # Phase 1: Tiered processing (remaining unresolved)
    print("\n--- Phase 1: Tiered Processing ---")
    stats = process_unresolved(db, resolver)

    print("\n--- Results ---")
    print(f"  Tier 1 (auto-resolved, >=0.85): {stats['tier1_resolved']}")
    print(f"  Tier 2 (re-resolved, 0.60-0.85): {stats['tier2_resolved']}")
    print(f"  Tier 3 (HITL queued, <0.60):     {stats['tier3_hitl']}")

    remaining = db.fetch_one(
        "SELECT count(*) as c FROM unresolved_entities WHERE resolved = FALSE AND (status IS NULL OR status = 'pending')"
    )
    print(f"\n  Remaining unresolved: {remaining['c']}")

    db.close()
    print("\nDone.")
