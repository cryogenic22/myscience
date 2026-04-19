"""EntityCanonicalizer — resolve any drug/company name variant to canonical form.

WS-1 of SPEC_015 (intelligence remediation). Sits BEFORE intent detection in
the chat pipeline so brand names ("Ozempic") get rewritten to canonical
generic names ("semaglutide") before slot extraction.

Resolution order (cheapest first):
  1. exact_generic — drugs.generic_name exact (case-insensitive)
  2. exact_brand   — drugs.brand_name exact (case-insensitive)
  3. alias         — entity_aliases.alias_text exact
  4. fuzzy_generic — pg_trgm similarity on generic_name (>= 0.4)
  5. fuzzy_brand   — pg_trgm similarity on brand_name (>= 0.4)

Does NOT auto-create entities. If unresolvable, returns None — the chat
layer must surface "entity not found" rather than synthesize on missing data.

Returns the GENERIC name as canonical_name even when matched via brand,
so downstream consumers always work with the canonical form.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


_FUZZY_THRESHOLD = 0.4
_MIN_NAME_LENGTH = 2
_CACHE_MAX = 1000


@dataclass(frozen=True)
class CanonicalResult:
    """Canonical resolution outcome for a single name input."""
    entity_id: str
    canonical_name: str        # Always the generic_name / official name
    entity_type: str           # "drug", "company", etc.
    confidence: float          # 1.0 exact, 0.4-0.99 fuzzy
    method: str                # "exact_generic", "exact_brand", "alias", "fuzzy_generic", ...
    original_input: str        # What the user typed


class EntityCanonicalizer:
    """Resolve user-supplied entity names to canonical entities.

    Usage:
        canon = EntityCanonicalizer(db)
        result = canon.canonicalize("Ozempic", hint_type="drug")
        # result.canonical_name == "semaglutide"
    """

    def __init__(self, db) -> None:
        self._db = db
        # Bounded LRU cache: most recent N lookups
        self._cache: "OrderedDict[tuple[str, str], Optional[CanonicalResult]]" = OrderedDict()

    # ── Public API ──────────────────────────────────────────────

    def canonicalize(self, name: str, hint_type: str = "") -> Optional[CanonicalResult]:
        """Resolve a name to its canonical entity, or None if unresolvable."""
        if not name or not isinstance(name, str):
            return None
        normalized = name.strip()
        if len(normalized) < _MIN_NAME_LENGTH:
            return None

        cache_key = (normalized.lower(), hint_type or "")
        if cache_key in self._cache:
            self._cache.move_to_end(cache_key)
            return self._cache[cache_key]

        # Cascade — first non-None wins
        result: Optional[CanonicalResult] = None
        for strategy in (
            self._exact_generic,
            self._exact_brand,
            self._alias_lookup,
            self._fuzzy_generic,
            self._fuzzy_brand,
        ):
            try:
                result = strategy(normalized)
            except Exception:
                logger.exception("canonicalize strategy %s failed", strategy.__name__)
                continue
            if result is not None:
                break

        # Attach original_input
        if result is not None:
            result = CanonicalResult(
                entity_id=result.entity_id,
                canonical_name=result.canonical_name,
                entity_type=result.entity_type,
                confidence=result.confidence,
                method=result.method,
                original_input=normalized,
            )

        self._store(cache_key, result)
        return result

    def canonicalize_batch(
        self, names: list[str], hint_type: str = ""
    ) -> dict[str, Optional[CanonicalResult]]:
        """Resolve multiple names. Returns dict keyed by original input."""
        return {n: self.canonicalize(n, hint_type=hint_type) for n in names}

    # ── Strategies ──────────────────────────────────────────────

    def _exact_generic(self, name: str) -> Optional[CanonicalResult]:
        row = self._db.fetch_one(
            "SELECT id, generic_name FROM drugs "
            "WHERE LOWER(generic_name) = LOWER(%s) LIMIT 1",
            [name],
        )
        if not row:
            return None
        return CanonicalResult(
            entity_id=str(row["id"]),
            canonical_name=row["generic_name"],
            entity_type="drug",
            confidence=1.0,
            method="exact_generic",
            original_input=name,
        )

    def _exact_brand(self, name: str) -> Optional[CanonicalResult]:
        row = self._db.fetch_one(
            "SELECT id, generic_name FROM drugs "
            "WHERE brand_name IS NOT NULL "
            "AND LOWER(brand_name) = LOWER(%s) LIMIT 1",
            [name],
        )
        if not row:
            return None
        return CanonicalResult(
            entity_id=str(row["id"]),
            canonical_name=row["generic_name"],
            entity_type="drug",
            confidence=1.0,
            method="exact_brand",
            original_input=name,
        )

    def _alias_lookup(self, name: str) -> Optional[CanonicalResult]:
        row = self._db.fetch_one(
            "SELECT entity_id, alias_text FROM entity_aliases "
            "WHERE entity_type = 'drug' "
            "AND LOWER(alias_text) = LOWER(%s) LIMIT 1",
            [name],
        )
        if not row:
            return None
        # Look up the canonical generic_name for this entity
        drug = self._db.fetch_one(
            "SELECT id, generic_name FROM drugs WHERE id::text = %s LIMIT 1",
            [str(row["entity_id"])],
        )
        if not drug:
            return None
        return CanonicalResult(
            entity_id=str(drug["id"]),
            canonical_name=drug["generic_name"],
            entity_type="drug",
            confidence=0.95,
            method="alias",
            original_input=name,
        )

    def _fuzzy_generic(self, name: str) -> Optional[CanonicalResult]:
        rows = self._db.fetch_all(
            "SELECT id, generic_name, similarity(LOWER(generic_name), LOWER(%s)) AS sim "
            "FROM drugs "
            "WHERE similarity(LOWER(generic_name), LOWER(%s)) > %s "
            "ORDER BY sim DESC LIMIT 1",
            [name, name, _FUZZY_THRESHOLD],
        )
        if not rows:
            return None
        best = rows[0]
        return CanonicalResult(
            entity_id=str(best["id"]),
            canonical_name=best["generic_name"],
            entity_type="drug",
            confidence=float(best["sim"]),
            method="fuzzy_generic",
            original_input=name,
        )

    def _fuzzy_brand(self, name: str) -> Optional[CanonicalResult]:
        rows = self._db.fetch_all(
            "SELECT id, generic_name, similarity(LOWER(brand_name), LOWER(%s)) AS sim "
            "FROM drugs "
            "WHERE brand_name IS NOT NULL "
            "AND similarity(LOWER(brand_name), LOWER(%s)) > %s "
            "ORDER BY sim DESC LIMIT 1",
            [name, name, _FUZZY_THRESHOLD],
        )
        if not rows:
            return None
        best = rows[0]
        return CanonicalResult(
            entity_id=str(best["id"]),
            canonical_name=best["generic_name"],
            entity_type="drug",
            confidence=float(best["sim"]),
            method="fuzzy_brand",
            original_input=name,
        )

    # ── Internal ────────────────────────────────────────────────

    def _store(
        self,
        key: tuple[str, str],
        value: Optional[CanonicalResult],
    ) -> None:
        self._cache[key] = value
        if len(self._cache) > _CACHE_MAX:
            self._cache.popitem(last=False)
