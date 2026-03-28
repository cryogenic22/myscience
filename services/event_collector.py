"""EventCollector — ingest market events, deduplicate, assign trust, persist.

Ingests EventCandidate objects from news feeds / press releases / regulatory
announcements, deduplicates via content hash, assigns trust scores based on
source tier + corroboration, resolves primary entities, and persists to the
market_events table.

Trust scoring tiers:
    tier_1 (FDA, SEC, ClinicalTrials.gov) → base 0.9
    tier_2 (Reuters, Bloomberg, PubMed)   → base 0.6
    tier_3 (Google News, blogs, social)   → base 0.3
    + 0.15 per corroborating source (capped at 1.0)
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from db import Database

logger = logging.getLogger(__name__)


# ── Constants ──────────────────────────────────────────────────────

TIER_BASE_SCORES = {
    "tier_1": 0.9,
    "tier_2": 0.6,
    "tier_3": 0.3,
}

CORROBORATION_BONUS = 0.15


# ── Dataclasses ────────────────────────────────────────────────────

@dataclass
class EventCandidate:
    """A raw market event candidate before dedup and persistence."""
    source_feed: str           # 'fda_press', 'google_news', etc.
    source_tier: str           # 'tier_1', 'tier_2', 'tier_3'
    event_type: str            # 'approval', 'trial_readout', 'safety_signal', etc.
    description: str
    event_date: datetime | None
    source_url: str
    entity_hint: str | None
    entity_type_hint: str | None
    raw_data: dict = field(default_factory=dict)


@dataclass
class CollectionResult:
    """Summary of a collect() run."""
    total_fetched: int
    new_events: int
    duplicates_skipped: int
    trust_upgraded: int


# ── Service ────────────────────────────────────────────────────────

class EventCollector:
    """Ingests, deduplicates, scores, and persists market events."""

    def __init__(self, db: Database):
        self.db = db

    # ── Public API ─────────────────────────────────────────────────

    def collect(self, candidates: list[EventCandidate]) -> CollectionResult:
        """Process a batch of event candidates.

        For each candidate:
        1. Compute content hash
        2. Check for existing event with same hash
        3. If duplicate: bump corroboration count + upgrade trust if higher
        4. If new: resolve entity, assign trust, persist

        Returns a CollectionResult summary.
        """
        new_events = 0
        duplicates_skipped = 0
        trust_upgraded = 0

        for candidate in candidates:
            try:
                event_hash = self._compute_event_hash(candidate)
                existing = self._check_existing(event_hash)

                if existing is not None:
                    # Duplicate — bump corroboration
                    self._bump_corroboration(existing["id"])
                    duplicates_skipped += 1
                else:
                    # New event — resolve entity and persist
                    entity = self._resolve_primary_entity(
                        candidate.entity_hint, candidate.entity_type_hint
                    )
                    trust_score = self._assign_trust_score(candidate, corroboration_count=0)
                    self._persist_event(candidate, event_hash, trust_score, entity)
                    new_events += 1
            except Exception:
                logger.debug("Failed to process event candidate: %s",
                             candidate.source_url, exc_info=True)

        return CollectionResult(
            total_fetched=len(candidates),
            new_events=new_events,
            duplicates_skipped=duplicates_skipped,
            trust_upgraded=trust_upgraded,
        )

    def get_unprocessed_events(self, limit: int = 50) -> list[dict]:
        """Return events with status = 'new', sorted by trust_score descending."""
        try:
            return self.db.fetch_all(
                """
                SELECT id, event_type, description, source_feed, trust_score,
                       entity_id, entity_type, event_date, source_url, status,
                       created_at
                FROM market_events
                WHERE status = 'new'
                ORDER BY trust_score DESC
                LIMIT %s
                """,
                [limit],
            )
        except Exception:
            logger.debug("Failed to fetch unprocessed events", exc_info=True)
            return []

    # ── Internal Methods ───────────────────────────────────────────

    def _compute_event_hash(self, candidate: EventCandidate) -> str:
        """SHA-256 of normalized (source_url + event_type + description[:100]).

        Whitespace is collapsed so minor formatting differences don't
        create separate hashes.
        """
        url = (candidate.source_url or "").strip()
        event_type = (candidate.event_type or "").strip()
        desc = re.sub(r"\s+", " ", (candidate.description or "")[:100]).strip()

        payload = f"{url}|{event_type}|{desc}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _assign_trust_score(
        self, candidate: EventCandidate, corroboration_count: int = 0
    ) -> float:
        """Compute trust score from source tier + corroboration bonus.

        tier_1 → 0.9, tier_2 → 0.6, tier_3 → 0.3
        + 0.15 per corroborating source, capped at 1.0
        """
        base = TIER_BASE_SCORES.get(candidate.source_tier, 0.3)
        bonus = corroboration_count * CORROBORATION_BONUS
        return min(base + bonus, 1.0)

    def _resolve_primary_entity(
        self, entity_hint: str | None, entity_type_hint: str | None
    ) -> dict | None:
        """Attempt to resolve the primary entity via ILIKE lookup.

        Checks drugs first (if hint is 'drug' or unspecified), then companies.
        Returns dict with 'id' and name, or None if not found.
        """
        if not entity_hint:
            return None

        try:
            if entity_type_hint in (None, "drug"):
                row = self.db.fetch_one(
                    "SELECT id, generic_name FROM drugs WHERE generic_name ILIKE %s LIMIT 1",
                    [entity_hint],
                )
                if row:
                    return {"id": row["id"], "name": row["generic_name"], "type": "drug"}

            if entity_type_hint in (None, "company"):
                row = self.db.fetch_one(
                    "SELECT id, name FROM companies WHERE name ILIKE %s LIMIT 1",
                    [entity_hint],
                )
                if row:
                    return {"id": row["id"], "name": row["name"], "type": "company"}
        except Exception:
            logger.debug("Entity resolution failed for hint=%s", entity_hint, exc_info=True)

        return None

    def _check_existing(self, event_hash: str) -> dict | None:
        """Check if an event with this hash already exists."""
        return self.db.fetch_one(
            "SELECT id, event_hash FROM market_events WHERE event_hash = %s",
            [event_hash],
        )

    def _persist_event(
        self,
        candidate: EventCandidate,
        event_hash: str,
        trust_score: float,
        entity: dict | None,
    ) -> None:
        """INSERT a new market event row."""
        self.db.execute(
            """
            INSERT INTO market_events (
                event_hash, event_type, description, source_feed,
                source_url, source_tier, trust_score,
                entity_id, entity_type, event_date,
                raw_data, status, corroboration_count, created_at
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, 'new', 0, NOW()
            )
            """,
            [
                event_hash,
                candidate.event_type,
                candidate.description,
                candidate.source_feed,
                candidate.source_url,
                candidate.source_tier,
                trust_score,
                entity["id"] if entity else None,
                entity["type"] if entity else None,
                candidate.event_date,
                str(candidate.raw_data),
            ],
        )

    def _bump_corroboration(self, event_id: str) -> None:
        """Increment corroboration_count for an existing event."""
        self.db.execute(
            """
            UPDATE market_events
            SET corroboration_count = corroboration_count + 1
            WHERE id = %s
            """,
            [event_id],
        )
