"""
HybridSearch: Metadata filtering + vector similarity search across all entity types.

Combines structured metadata filters (phase, status, date, source) with semantic
vector search (pgvector cosine similarity) in a single query. This is the primary
retrieval interface for the knowledge layer.

Usage:
    search = HybridSearch(db, config)
    results = search.search("GLP-1 obesity Phase 3", entity_types=["trial"])
    similar = search.find_similar(drug_id, "drug")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """A single search result with provenance."""

    entity_id: str
    entity_type: str
    title: str
    snippet: str
    similarity: float
    metadata: dict
    provenance: dict
    quality_score: Optional[float] = None


# Per-entity-type search configuration
ENTITY_SEARCH_CONFIG = {
    "drug": {
        "table": "drugs",
        "id_col": "id",
        "id_cast": "::text",
        "embedding_col": "molecule_embedding",
        "title_expr": "COALESCE(brand_name || ' (' || generic_name || ')', generic_name)",
        "snippet_col": "generic_name",
        "metadata_cols": [
            "generic_name", "brand_name", "approval_date",
            "supply_status", "dosage_form", "marketing_status",
        ],
        "provenance_cols": ["source_api", "source_url", "retrieved_at"],
        "quality_col": "quality_score",
        "filters": {
            "therapeutic_area": ("therapeutic_area_id = %s", str),
            "mechanism": ("mechanism_id = %s", str),
            "company": ("company_id = %s", str),
        },
    },
    "trial": {
        "table": "clinical_trials",
        "id_col": "id",
        "id_cast": "",
        "embedding_col": "protocol_embedding",
        "title_expr": "COALESCE(official_title, 'Trial ' || id)",
        "snippet_col": "official_title",
        "metadata_cols": [
            "phase", "status", "sponsor_name", "enrollment_target",
            "start_date", "completion_date", "study_type",
        ],
        "provenance_cols": ["source_api", "source_url", "retrieved_at"],
        "quality_col": "quality_score",
        "filters": {
            "phase": ("phase = %s", str),
            "status": ("status = %s", str),
            "drug_id": ("drug_id = %s", str),
        },
    },
    "literature": {
        "table": "pubmed_articles",
        "id_col": "id",
        "id_cast": "::text",
        "embedding_col": "abstract_embedding",
        "title_expr": "title",
        "snippet_col": "COALESCE(NULLIF(LEFT(abstract, 520), ''), title)",
        "metadata_cols": [
            "pmid", "journal", "publication_date", "publication_type", "keywords", "authors",
        ],
        "provenance_cols": ["source_api", "source_url", "retrieved_at"],
        "quality_col": "quality_score",
        "filters": {
            "journal": ("journal ILIKE %s", lambda v: f"%{v}%"),
            "drug_id": ("drug_id = %s", str),
        },
    },
    "therapeutic_area": {
        "table": "therapeutic_areas",
        "id_col": "id",
        "id_cast": "::text",
        "embedding_col": "scope_note_embedding",
        "title_expr": "name",
        "snippet_col": "COALESCE(NULLIF(LEFT(scope_note, 520), ''), name)",
        "metadata_cols": ["mesh_id", "parent_mesh_id", "tree_numbers"],
        "provenance_cols": ["source_api", "source_url", "retrieved_at"],
        "quality_col": None,
        "filters": {},
    },
    "company": {
        "table": "companies",
        "id_col": "id",
        "id_cast": "::text",
        "embedding_col": "strategy_embedding",
        "title_expr": "name",
        "snippet_col": "name",
        "metadata_cols": ["ticker", "cik", "country", "sic_code"],
        "provenance_cols": ["source_api", "source_url", "retrieved_at"],
        "quality_col": "quality_score",
        "filters": {
            "country": ("country = %s", str),
            "ticker": ("ticker = %s", str),
        },
    },
    "event": {
        "table": "market_events",
        "id_col": "id",
        "id_cast": "::text",
        "embedding_col": None,  # no embedding column
        "title_expr": "LEFT(description, 100)",
        "snippet_col": "description",
        "metadata_cols": ["event_type", "event_date", "impact_score"],
        "provenance_cols": ["source_api", "source_url", "retrieved_at"],
        "quality_col": None,
        "filters": {
            "event_type": ("event_type = %s", str),
            "drug_id": ("drug_id = %s", str),
        },
    },
}


def recency_score(dt: datetime | str | None) -> float:
    """Score a timestamp by recency: recent → 1.0, old → 0.2.

    < 30 days: 1.0, 30-90d: 0.7, 90-365d: 0.4, > 1 year: 0.2.
    None → 0.5 (neutral default).
    """
    if dt is None:
        return 0.5
    if isinstance(dt, str):
        try:
            from datetime import datetime as dt_cls, timezone as tz
            dt = dt_cls.fromisoformat(dt.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return 0.5
    now = datetime.now(timezone.utc)
    if hasattr(dt, 'tzinfo') and dt.tzinfo is None:
        age_days = (now.replace(tzinfo=None) - dt).days
    else:
        age_days = (now - dt).days
    if age_days <= 0:
        return 1.0
    if age_days <= 30:
        return 1.0
    if age_days <= 90:
        return 0.7
    if age_days <= 365:
        return 0.4
    return 0.2


def rank_by_recency(evidence: list[dict], similarity_key: str = "similarity") -> list[dict]:
    """Re-rank evidence by relevance × recency.

    Each item gets a combined_score = similarity × recency_score.
    Returns sorted list (highest combined first).
    """
    if not evidence:
        return []

    scored = []
    for item in evidence:
        sim = float(item.get(similarity_key, 0.5))
        dt_val = item.get("retrieved_at") or item.get("publication_date")
        recency = recency_score(dt_val)
        combined = sim * recency
        scored.append((combined, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored]


class HybridSearch:
    """Metadata + vector hybrid search across the knowledge layer."""

    def __init__(self, db, config):
        self.db = db
        self.config = config
        self._embedder_client = None

    # Name-to-UUID resolution map
    _NAME_LOOKUP = {
        "drug": ("drugs", "generic_name"),
        "company": ("companies", "name"),
        "therapeutic_area": ("therapeutic_areas", "name"),
        "mechanism": ("mechanisms_of_action", "name"),
    }

    def _resolve_entity_id(self, entity_id: str, entity_type: str) -> str:
        """Resolve a human-readable name to a UUID if needed."""
        # Quick UUID check
        if len(entity_id) == 36 and entity_id.count("-") == 4:
            return entity_id
        if entity_type == "trial":
            return entity_id
        lookup = self._NAME_LOOKUP.get(entity_type)
        if not lookup:
            return entity_id
        table, name_col = lookup
        row = self.db.fetch_one(
            f"SELECT id::text AS entity_id FROM {table} WHERE LOWER({name_col}) = LOWER(%s)",
            [entity_id],
        )
        return row["entity_id"] if row else entity_id

    def _get_embedding(self, text: str) -> list[float]:
        """Generate embedding for a query string using OpenAI."""
        if self._embedder_client is None:
            try:
                from openai import OpenAI
                self._embedder_client = OpenAI(api_key=self.config.embedding.api_key)
            except ImportError:
                raise RuntimeError("openai package not installed")

        response = self._embedder_client.embeddings.create(
            model=self.config.embedding.model,
            input=text,
        )
        return response.data[0].embedding

    def search(
        self,
        query: str,
        entity_types: Optional[list[str]] = None,
        filters: Optional[dict] = None,
        date_range: Optional[tuple[str, str]] = None,
        source_types: Optional[list[str]] = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        """Compatibility wrapper for first-page search results."""
        results, _ = self.search_paginated(
            query=query,
            entity_types=entity_types,
            filters=filters,
            date_range=date_range,
            source_types=source_types,
            limit=limit,
            offset=0,
        )
        return results

    def search_paginated(
        self,
        query: str,
        entity_types: Optional[list[str]] = None,
        filters: Optional[dict] = None,
        date_range: Optional[tuple[str, str]] = None,
        source_types: Optional[list[str]] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[SearchResult], int]:
        """Full hybrid search across entity types with pagination."""
        if entity_types is None:
            entity_types = ["drug", "trial", "literature", "company"]

        query_embedding = self._get_embedding(query)
        all_results = []
        total_matches = 0
        window_limit = max(offset + limit, limit)

        for etype in entity_types:
            cfg = ENTITY_SEARCH_CONFIG.get(etype)
            if not cfg or not cfg["embedding_col"]:
                continue

            try:
                type_results = self._search_single_type(
                    query_embedding, etype, cfg, filters, date_range, source_types, window_limit
                )
                all_results.extend(type_results)
                total_matches += self._count_single_type(etype, cfg, filters, date_range, source_types)
            except Exception as exc:
                logger.warning("Search failed for entity type %s: %s", etype, exc)
                # Reset connection state so subsequent queries don't fail
                try:
                    self.db.conn.rollback()
                except Exception:
                    pass

        # Sort all results by similarity descending
        all_results.sort(key=lambda r: r.similarity, reverse=True)
        return all_results[offset: offset + limit], total_matches

    def find_similar(
        self,
        entity_id: str,
        entity_type: str,
        limit: int = 10,
    ) -> list[SearchResult]:
        """Find entities similar to a given entity by embedding proximity."""
        cfg = ENTITY_SEARCH_CONFIG.get(entity_type)
        if not cfg or not cfg["embedding_col"]:
            return []

        emb_col = cfg["embedding_col"]
        table = cfg["table"]
        id_col = cfg["id_col"]

        # Resolve name to UUID if needed
        resolved_id = self._resolve_entity_id(entity_id, entity_type)

        # Get the entity's embedding
        row = self.db.fetch_one(
            f"SELECT {emb_col} FROM {table} WHERE {id_col} = %s",
            [resolved_id],
        )
        if not row or not row[emb_col]:
            return []

        embedding = row[emb_col]

        # Search same type for similar
        results = self._search_single_type(
            embedding, entity_type, cfg,
            filters=None, date_range=None, source_types=None,
            limit=limit + 1,
        )

        # Exclude the source entity itself
        return [r for r in results if r.entity_id != str(resolved_id)][:limit]

    def search_entity_type(
        self,
        query: str,
        entity_type: str,
        filters: Optional[dict] = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        """Search within a single entity type (optimized path)."""
        cfg = ENTITY_SEARCH_CONFIG.get(entity_type)
        if not cfg or not cfg["embedding_col"]:
            return []

        query_embedding = self._get_embedding(query)
        return self._search_single_type(
            query_embedding, entity_type, cfg, filters,
            date_range=None, source_types=None, limit=limit,
        )

    def _search_single_type(
        self,
        query_embedding,
        entity_type: str,
        cfg: dict,
        filters: Optional[dict],
        date_range: Optional[tuple],
        source_types: Optional[list[str]],
        limit: int,
    ) -> list[SearchResult]:
        """Execute hybrid search on a single entity type."""
        table = cfg["table"]
        id_col = cfg["id_col"]
        id_cast = cfg["id_cast"]
        emb_col = cfg["embedding_col"]
        title_expr = cfg["title_expr"]
        snippet_col = cfg["snippet_col"]
        meta_cols = cfg["metadata_cols"]
        prov_cols = cfg["provenance_cols"]
        quality_col = cfg["quality_col"]
        where, where_params = self._build_where_clause(
            entity_type=entity_type,
            cfg=cfg,
            filters=filters,
            date_range=date_range,
            source_types=source_types,
        )

        # Build embedding vector as parameterized string
        # query_embedding may be a list of floats (from OpenAI) or a string (from DB)
        if isinstance(query_embedding, str):
            emb_str = query_embedding
        else:
            emb_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        # Metadata column selection
        meta_select = ", ".join(meta_cols)
        prov_select = ", ".join(prov_cols)
        quality_select = f", {quality_col}" if quality_col else ""

        query_sql = f"""
            SELECT
                {id_col}{id_cast} AS entity_id,
                {title_expr} AS title,
                {snippet_col} AS snippet,
                1 - ({emb_col} <=> %s::vector) AS similarity,
                {meta_select},
                {prov_select}
                {quality_select}
            FROM {table}
            {where}
            ORDER BY {emb_col} <=> %s::vector
            LIMIT %s
        """
        # Parameter order must match SQL placeholder order:
        # SELECT(%s::vector) -> WHERE(filter params) -> ORDER BY(%s::vector) -> LIMIT(%s)
        params = [emb_str] + where_params + [emb_str, limit]

        rows = self.db.fetch_all(query_sql, params)

        results = []
        for row in rows:
            metadata = {k: row.get(k) for k in meta_cols if row.get(k) is not None}
            provenance = {k: row.get(k) for k in prov_cols if row.get(k) is not None}
            # Convert non-serializable types
            for k, v in provenance.items():
                if hasattr(v, "isoformat"):
                    provenance[k] = v.isoformat()
            for k, v in metadata.items():
                if hasattr(v, "isoformat"):
                    metadata[k] = v.isoformat()

            results.append(SearchResult(
                entity_id=str(row["entity_id"]),
                entity_type=entity_type,
                title=str(row.get("title") or ""),
                snippet=str(row.get("snippet") or ""),
                similarity=float(row.get("similarity") or 0),
                metadata=metadata,
                provenance=provenance,
                quality_score=float(row[quality_col]) if quality_col and row.get(quality_col) else None,
            ))

        return results

    def _count_single_type(
        self,
        entity_type: str,
        cfg: dict,
        filters: Optional[dict],
        date_range: Optional[tuple],
        source_types: Optional[list[str]],
    ) -> int:
        """Count all rows matching metadata/source/date filters for a type."""
        table = cfg["table"]
        where, params = self._build_where_clause(
            entity_type=entity_type,
            cfg=cfg,
            filters=filters,
            date_range=date_range,
            source_types=source_types,
        )
        row = self.db.fetch_one(f"SELECT COUNT(*)::int AS count FROM {table} {where}", params)
        if not row:
            return 0
        return int(row.get("count") or 0)

    def _build_where_clause(
        self,
        entity_type: str,
        cfg: dict,
        filters: Optional[dict],
        date_range: Optional[tuple],
        source_types: Optional[list[str]],
    ) -> tuple[str, list]:
        """Build reusable WHERE clause and parameters for search/count queries."""
        emb_col = cfg["embedding_col"]
        conditions = [f"{emb_col} IS NOT NULL"]
        params: list = []

        # Exclude merged and excluded records (golden record pattern)
        if entity_type in ("drug", "company"):
            conditions.append("(record_status IS NULL OR record_status NOT IN ('excluded', 'merged'))")

        if filters:
            for key, value in filters.items():
                if key in cfg["filters"]:
                    clause, transform = cfg["filters"][key]
                    conditions.append(clause)
                    params.append(transform(value))

        if date_range:
            date_col = self._get_date_column(entity_type)
            if date_col:
                if date_range[0]:
                    conditions.append(f"{date_col} >= %s")
                    params.append(date_range[0])
                if date_range[1]:
                    conditions.append(f"{date_col} <= %s")
                    params.append(date_range[1])

        if source_types:
            conditions.append("source_api = ANY(%s)")
            params.append(source_types)

        where = "WHERE " + " AND ".join(conditions)
        return where, params

    @staticmethod
    def _get_date_column(entity_type: str) -> Optional[str]:
        """Map entity type to its primary date column."""
        return {
            "drug": "approval_date",
            "trial": "start_date",
            "literature": "publication_date",
            "company": None,
            "event": "event_date",
        }.get(entity_type)
