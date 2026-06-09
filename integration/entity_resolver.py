"""
Step 2: Entity Resolution.

Links incoming records to existing entities in the knowledge layer using
a 6-strategy resolution cascade:
  1. Exact match on canonical IDs (NCT, PMID, NDA, MeSH ID, CIK, ORCID)
  2. Alias table lookup (previously confirmed matches)
  3. Fuzzy match on names (pg_trgm trigram similarity)
  4. Embedding similarity search (pgvector cosine distance)
  5. LLM-based analysis (GPT-4o-mini picks from candidates)
  6. Auto-create entity (create drug/company from credible source data)

Every resolution decision is logged to the `resolution_audit` table with
method, confidence, reasoning, and all candidates considered.

When all strategies fail, the record goes to the unresolved queue.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from connectors.base import SourceType
from domain.pharma.mention_normalizer import (
    normalize_drug_mention,
    normalize_company_mention,
    DRUG_SKIP_TERMS,
    COMPANY_SKIP_TERMS,
)
from integration.normalizer import NormalizedRecord

logger = logging.getLogger(__name__)


# Delimiters that separate the active ingredients of a combination drug name,
# e.g. "valsartan/sacubitril", "sacubitril and valsartan", "metformin + sitagliptin".
_COMBO_DELIM_RE = re.compile(r"\s*(?:/|\+|&|,|\band\b|\bplus\b|\bwith\b)\s*", re.IGNORECASE)


def _combo_components(name: str) -> set[str]:
    """Split a (possibly combination) drug name into its normalized component set.

    "sacubitril and valsartan" -> {"sacubitril", "valsartan"}
    "valsartan/sacubitril"     -> {"sacubitril", "valsartan"}
    "sacubitril"               -> {"sacubitril"}

    Each component is run through normalize_drug_mention to strip dosage/form/marks
    so the two sides compare on base compound names.
    """
    out: set[str] = set()
    for part in _COMBO_DELIM_RE.split(name or ""):
        cleaned = normalize_drug_mention(part)
        if cleaned and len(cleaned) >= 3:
            out.add(cleaned.lower())
    return out


# ============================================================
# Traceability dataclasses
# ============================================================


@dataclass
class ResolutionCandidate:
    """A candidate entity considered during resolution."""

    entity_id: str
    entity_name: str
    score: float
    method: str


@dataclass
class ResolutionTrace:
    """Full audit trail for a single resolution decision."""

    raw_value: str
    entity_type: str
    method: str               # exact_id, alias, fuzzy, embedding, llm, auto_create
    confidence: float
    reasoning: str
    candidates: list[ResolutionCandidate] = field(default_factory=list)
    accepted: bool = True


@dataclass
class ResolvedLink:
    """A single resolved entity reference."""

    entity_type: str          # "company", "drug", "therapeutic_area", "mechanism"
    entity_id: str            # UUID or TEXT ID from our tables
    matched_via: str          # "exact_id", "alias", "fuzzy", "embedding", "llm", "auto_create"
    confidence: float         # 1.0 for exact, lower for fuzzy/embedding/llm
    matched_value: str        # The value that was matched
    trace: Optional[ResolutionTrace] = None


@dataclass
class ResolvedRecord:
    """A NormalizedRecord annotated with resolved entity links."""

    normalized: NormalizedRecord
    resolved_links: dict[str, ResolvedLink] = field(default_factory=dict)
    ontology_links: list[ResolvedLink] = field(default_factory=list)


# ============================================================
# ID type → table/column for exact lookups
# ============================================================

EXACT_LOOKUP_MAP: dict[str, tuple[str, str, str]] = {
    # identifier_key: (table, column, entity_type)
    "nct_id": ("clinical_trials", "id", "trial"),
    "pmid": ("pubmed_articles", "pmid", "literature"),
    "nda_number": ("drugs", "nda_number", "drug"),
    "mesh_id": ("therapeutic_areas", "mesh_id", "therapeutic_area"),
    "cik": ("companies", "cik", "company"),
    "ticker": ("companies", "ticker", "company"),
    "orcid": ("investigators", "orcid", "investigator"),
    "patent_number": ("patents", "patent_number", "patent"),
}

# Name fields that require fuzzy/embedding/LLM matching
FUZZY_MATCH_FIELDS: dict[str, tuple[str, str, str]] = {
    # identifier_key: (table, name_column, entity_type)
    "company_name": ("companies", "name", "company"),
    "generic_name": ("drugs", "generic_name", "drug"),
    "brand_name": ("drugs", "brand_name", "drug"),  # WS-1: brand fallback
    "sponsor_name": ("companies", "name", "company"),
    "investigator_name": ("investigators", "name", "investigator"),
}

# Embedding columns per table (for Strategy 4)
EMBEDDING_COLUMNS: dict[str, str] = {
    "drugs": "molecule_embedding",
    "companies": "strategy_embedding",
    "investigators": None,  # no embedding column on investigators
}

# Sources credible enough to auto-create entities from
AUTO_CREATE_SOURCES = {
    SourceType.CLINICAL_TRIALS_GOV,
    SourceType.FDA_ORANGE_BOOK,
    SourceType.PUBMED,
    SourceType.FDA_SHORTAGES,
}


class EntityResolver:
    """
    Links incoming records to existing entities in the DB using a
    6-strategy cascade. Every decision is audited for traceability.

    When a domain_pack is provided, resolution config (lookup maps,
    fuzzy fields, embedding columns, skip terms) is read from the pack
    instead of module-level constants.
    """

    def __init__(self, db, config, openai_client=None, domain_pack=None):
        self.db = db
        self.config = config
        self.domain_pack = domain_pack
        self.fuzzy_threshold = config.pipeline.fuzzy_match_threshold
        self.auto_alias_threshold = config.pipeline.auto_alias_threshold
        self.embedding_threshold = config.pipeline.embedding_similarity_threshold
        self.llm_confidence_threshold = config.pipeline.llm_confidence_threshold
        self.llm_model = config.pipeline.llm_resolution_model
        self.llm_enabled = config.pipeline.llm_resolution_enabled
        self.auto_create_enabled = config.pipeline.auto_create_entities
        self.audit_enabled = config.pipeline.resolution_audit_enabled
        self.openai_client = openai_client
        self._embedding_cache: dict[str, list[float]] = {}

        # Build lookup maps from domain pack or fall back to module constants
        if domain_pack:
            self._exact_lookup_map = domain_pack.get_exact_lookup_map()
            self._fuzzy_match_fields = domain_pack.get_fuzzy_match_map()
            self._embedding_columns = domain_pack.get_embedding_columns()
            self._auto_create_sources = domain_pack.get_auto_create_sources()
        else:
            self._exact_lookup_map = EXACT_LOOKUP_MAP
            self._fuzzy_match_fields = FUZZY_MATCH_FIELDS
            self._embedding_columns = EMBEDDING_COLUMNS
            self._auto_create_sources = AUTO_CREATE_SOURCES

    def resolve(self, record: NormalizedRecord) -> ResolvedRecord:
        """Attempt to resolve all identifiers in the record to existing entities."""
        resolved = ResolvedRecord(normalized=record)
        identifiers = record.identifiers

        # Determine ontology identifier keys from domain pack
        ontology_keys = {}
        if self.domain_pack:
            for onto in self.domain_pack.ontologies:
                ontology_keys[onto.identifier_key] = onto
        else:
            ontology_keys["mesh_ids"] = None  # handled by _ontology_lookup

        for id_key, id_value in identifiers.items():
            if id_key in ontology_keys and isinstance(id_value, list):
                for onto_id in id_value:
                    links = self._ontology_lookup(onto_id, ontology_keys.get(id_key))
                    resolved.ontology_links.extend(links)
                continue

            link = self._resolve_single(id_key, id_value, record)
            if link:
                resolved.resolved_links[id_key] = link
                self._log_audit(link.trace, record)

                # Auto-create alias if high confidence and not an exact/auto match
                if (link.confidence >= self.auto_alias_threshold
                        and link.matched_via not in ("exact_id", "auto_create")):
                    self._create_alias(
                        entity_type=link.entity_type,
                        entity_id=link.entity_id,
                        alias_text=str(id_value),
                        source_type=record.raw.provenance.source_type,
                        confidence=link.confidence,
                    )
            else:
                # All strategies failed — log to unresolved queue
                if id_key in self._fuzzy_match_fields:
                    entity_type = self._fuzzy_match_fields[id_key][2]
                    self._log_unresolved(
                        raw_value=str(id_value),
                        record_type=entity_type,
                        source_type=record.raw.provenance.source_type,
                        context={"external_id": record.raw.external_id, "id_key": id_key},
                    )

        return resolved

    def resolve_drug_mention(
        self, value: str, source_type: SourceType
    ) -> Optional[ResolvedLink]:
        """DB-only drug resolution for backfills (no NormalizedRecord needed).

        Mirrors the ingest cascade for a drug name minus the embedding/LLM/
        auto-create strategies (which need an OpenAI client / credible source):
        alias -> fuzzy -> combo-component. Used by
        scripts/backfill_orphan_drug_links.py to recover rows that orphaned
        before the combo-component fallback existed.
        """
        value = (value or "").strip()
        if not value:
            return None
        link = self._alias_lookup("drug", value, source_type)
        if link:
            return link
        link = self._fuzzy_lookup("generic_name", value)
        if link:
            return link
        return self._combo_component_lookup("generic_name", value)

    def _resolve_single(
        self, id_key: str, id_value: Any, record: NormalizedRecord
    ) -> Optional[ResolvedLink]:
        """Try each strategy in priority order. Return first match or None."""

        # Strategy 1: Exact ID lookup
        if id_key in self._exact_lookup_map:
            link = self._exact_lookup(id_key, id_value)
            if link:
                return link

        # Strategy 2: Alias table lookup
        if id_key in self._fuzzy_match_fields:
            entity_type = self._fuzzy_match_fields[id_key][2]
            source_type = record.raw.provenance.source_type
            link = self._alias_lookup(entity_type, str(id_value), source_type)
            if link:
                return link

            # Strategy 3: Fuzzy name match (pg_trgm)
            link = self._fuzzy_lookup(id_key, str(id_value))
            if link:
                return link

            # Strategy 4: Embedding similarity search
            if self.openai_client:
                link = self._embedding_lookup(id_key, str(id_value))
                if link:
                    return link

            # Strategy 5: LLM analysis
            if self.openai_client and self.llm_enabled:
                link = self._llm_lookup(id_key, str(id_value), record)
                if link:
                    return link

            # Strategy 5b: Combo-component fallback. A drug searched by a mono
            # component name (e.g. "sacubitril") or a reordered combo name only
            # exists as a combination row (e.g. "valsartan/sacubitril"); trigram
            # fuzzy cannot bridge that gap. Fires only after fuzzy/embedding/LLM
            # miss, so a component with its own mono row (e.g. "valsartan")
            # resolves to the mono row first and never reaches here.
            link = self._combo_component_lookup(id_key, str(id_value))
            if link:
                return link

            # Strategy 6: Auto-create entity
            if self.auto_create_enabled:
                link = self._auto_create(id_key, str(id_value), record)
                if link:
                    return link

        return None

    # ============================================================
    # Strategy 1: Exact ID lookup
    # ============================================================

    def _exact_lookup(self, id_key: str, id_value: Any) -> Optional[ResolvedLink]:
        """Direct lookup on globally unique IDs."""
        table, column, entity_type = self._exact_lookup_map[id_key]
        row = self.db.fetch_one(
            f"SELECT id FROM {table} WHERE {column} = %s",
            [str(id_value)],
        )
        if row:
            return ResolvedLink(
                entity_type=entity_type,
                entity_id=str(row["id"]),
                matched_via="exact_id",
                confidence=1.0,
                matched_value=str(id_value),
                trace=ResolutionTrace(
                    raw_value=str(id_value),
                    entity_type=entity_type,
                    method="exact_id",
                    confidence=1.0,
                    reasoning=f"Exact match on {table}.{column} = '{id_value}'",
                    candidates=[ResolutionCandidate(str(row["id"]), str(id_value), 1.0, "exact_id")],
                ),
            )
        return None

    # ============================================================
    # Strategy 2: Alias table lookup
    # ============================================================

    def _alias_lookup(
        self, entity_type: str, alias_text: str, source_type: SourceType
    ) -> Optional[ResolvedLink]:
        """Check entity_aliases for a previously confirmed match."""
        row = self.db.fetch_one(
            """
            SELECT entity_id, confidence
            FROM entity_aliases
            WHERE entity_type = %s AND alias_text = %s AND source_type = %s
            """,
            [entity_type, alias_text, source_type.value],
        )
        # RC1: an alias may point to a now-merged/superseded dup row. Honouring
        # it links fresh data onto a dead duplicate (the exact failure that left
        # bioactivities pinned to a merged drug). If the aliased entity is in a
        # status-guarded table and soft-deleted, skip the alias so resolution
        # falls through to fuzzy (which ranks by richness → canonical row).
        if row and entity_type in {"drug", "company", "molecular_target"}:
            table = {"drug": "drugs", "company": "companies",
                     "molecular_target": "molecular_targets"}[entity_type]
            status_row = self.db.fetch_one(
                f"SELECT record_status FROM {table} WHERE id = %s",
                [str(row["entity_id"])],
            )
            if status_row and status_row.get("record_status") in (
                "merged", "superseded", "excluded"
            ):
                row = None
        if row:
            return ResolvedLink(
                entity_type=entity_type,
                entity_id=str(row["entity_id"]),
                matched_via="alias",
                confidence=row["confidence"],
                matched_value=alias_text,
                trace=ResolutionTrace(
                    raw_value=alias_text,
                    entity_type=entity_type,
                    method="alias",
                    confidence=row["confidence"],
                    reasoning=f"Found in alias table for source '{source_type.value}'",
                    candidates=[ResolutionCandidate(str(row["entity_id"]), alias_text, row["confidence"], "alias")],
                ),
            )
        return None

    # ============================================================
    # Strategy 3: Fuzzy name match (pg_trgm)
    # ============================================================

    # Tables whose duplicate rows are soft-deleted via record_status; the
    # resolver must never match a merged/superseded row (RC1) — doing so links
    # fresh data onto a dead duplicate and silently breaks downstream emitters.
    _STATUS_GUARDED_TABLES = {"drugs", "companies", "molecular_targets"}

    def _fuzzy_lookup(self, id_key: str, value: str) -> Optional[ResolvedLink]:
        """Fuzzy match using PostgreSQL trigram similarity."""
        if id_key not in self._fuzzy_match_fields:
            return None

        table, column, entity_type = self._fuzzy_match_fields[id_key]

        # Exclude soft-deleted dup rows (record_status), and for drugs prefer the
        # richest candidate among near-ties (matches resolve_asset_to_subject's
        # richness ranking, so ingest + read agree on the canonical row).
        status_clause = ""
        order_clause = "ORDER BY sim DESC"
        if table in self._STATUS_GUARDED_TABLES:
            status_clause = (
                "AND (record_status IS NULL "
                "OR record_status NOT IN ('merged', 'superseded', 'excluded'))"
            )
        if table == "drugs":
            order_clause = (
                "ORDER BY sim DESC, "
                "(SELECT count(*) FROM facts f WHERE f.subject_entity_id = drugs.id::text) "
                "+ (SELECT count(*) FROM clinical_trials ct WHERE ct.drug_id = drugs.id) DESC"
            )

        # Get top candidates for traceability
        candidates_rows = self.db.fetch_all(
            f"""
            SELECT id, {column} AS name, similarity({column}, %s) AS sim
            FROM {table}
            WHERE similarity({column}, %s) >= %s
            {status_clause}
            {order_clause}
            LIMIT 5
            """,
            [value, value, self.fuzzy_threshold],
        )

        if candidates_rows:
            best = candidates_rows[0]
            candidates = [
                ResolutionCandidate(str(r["id"]), r["name"], float(r["sim"]), "fuzzy")
                for r in candidates_rows
            ]
            return ResolvedLink(
                entity_type=entity_type,
                entity_id=str(best["id"]),
                matched_via="fuzzy",
                confidence=float(best["sim"]),
                matched_value=value,
                trace=ResolutionTrace(
                    raw_value=value,
                    entity_type=entity_type,
                    method="fuzzy",
                    confidence=float(best["sim"]),
                    reasoning=f"Trigram similarity {best['sim']:.3f} between '{value}' and '{best['name']}'",
                    candidates=candidates,
                ),
            )
        return None

    # ============================================================
    # Strategy 5b: Combo-component fallback
    # ============================================================

    def _combo_component_lookup(self, id_key: str, value: str) -> Optional[ResolvedLink]:
        """Resolve a drug name to the richest active combination drug that
        contains it as a component.

        Handles two failure modes that trigram fuzzy cannot:
          - a mono component ("sacubitril") whose drug only exists as a combo
            ("valsartan/sacubitril"),
          - a combo expressed with a different delimiter/order
            ("sacubitril and valsartan" vs "valsartan/sacubitril").

        Matches only when EVERY component of `value` is present in the candidate's
        component set (subset match), then picks the richest (facts + trials)
        active candidate — agreeing with resolve_asset_to_subject's richness rank.
        """
        if id_key not in ("generic_name", "brand_name"):
            return None
        value = (value or "").strip()
        if len(value) < 3:
            return None

        want = _combo_components(value)
        if not want:
            return None

        # Cheap prefilter: candidate combos must contain the longest component as
        # a substring AND look like a combination (carry a combo delimiter). The
        # delimiter clause prevents matching a mono row that merely contains the
        # substring.
        longest = max(want, key=len)
        candidates = self.db.fetch_all(
            """
            SELECT id, generic_name,
                   (SELECT count(*) FROM facts f
                      WHERE f.subject_entity_id = drugs.id::text)
                 + (SELECT count(*) FROM clinical_trials ct
                      WHERE ct.drug_id = drugs.id) AS richness
            FROM drugs
            WHERE (record_status IS NULL
                   OR record_status NOT IN ('merged', 'superseded', 'excluded'))
              AND generic_name ILIKE %s
              AND (generic_name LIKE '%%/%%'
                   OR generic_name LIKE '%%+%%'
                   OR generic_name ILIKE '%% and %%'
                   OR generic_name ILIKE '%% plus %%'
                   OR generic_name LIKE '%%&%%')
            ORDER BY richness DESC
            LIMIT 25
            """,
            ["%" + longest + "%"],
        )

        for cand in candidates:
            have = _combo_components(cand.get("generic_name") or "")
            if want and want.issubset(have):
                cand_name = cand.get("generic_name") or ""
                return ResolvedLink(
                    entity_type="drug",
                    entity_id=str(cand["id"]),
                    matched_via="combo_component",
                    confidence=0.85,
                    matched_value=value,
                    trace=ResolutionTrace(
                        raw_value=value,
                        entity_type="drug",
                        method="combo_component",
                        confidence=0.85,
                        reasoning=(
                            f"'{value}' components {sorted(want)} are a subset of "
                            f"combination drug '{cand_name}'; selected richest active "
                            f"row (richness={cand.get('richness')})."
                        ),
                        candidates=[ResolutionCandidate(
                            str(cand["id"]), cand_name, 0.85, "combo_component")],
                    ),
                )
        return None

    # ============================================================
    # Strategy 4: Embedding similarity search
    # ============================================================

    def _embedding_lookup(self, id_key: str, value: str) -> Optional[ResolvedLink]:
        """Find nearest entity by vector cosine similarity."""
        if id_key not in self._fuzzy_match_fields:
            return None

        table, column, entity_type = self._fuzzy_match_fields[id_key]
        emb_col = self._embedding_columns.get(table)
        if not emb_col:
            return None

        query_embedding = self._get_embedding(value)
        if not query_embedding:
            return None

        row = self.db.fetch_one(
            f"""
            SELECT id, {column} AS name,
                   1 - ({emb_col} <=> %s::vector) AS cosine_sim
            FROM {table}
            WHERE {emb_col} IS NOT NULL
            ORDER BY {emb_col} <=> %s::vector
            LIMIT 1
            """,
            [str(query_embedding), str(query_embedding)],
        )

        if row and float(row["cosine_sim"]) >= self.embedding_threshold:
            return ResolvedLink(
                entity_type=entity_type,
                entity_id=str(row["id"]),
                matched_via="embedding",
                confidence=float(row["cosine_sim"]),
                matched_value=value,
                trace=ResolutionTrace(
                    raw_value=value,
                    entity_type=entity_type,
                    method="embedding",
                    confidence=float(row["cosine_sim"]),
                    reasoning=f"Cosine similarity {row['cosine_sim']:.3f} between embedding of '{value}' and '{row['name']}'",
                    candidates=[ResolutionCandidate(str(row["id"]), row["name"], float(row["cosine_sim"]), "embedding")],
                ),
            )
        return None

    def _get_embedding(self, text: str) -> Optional[list[float]]:
        """Generate embedding for a text value (cached)."""
        if text in self._embedding_cache:
            return self._embedding_cache[text]
        try:
            response = self.openai_client.embeddings.create(
                input=[text],
                model=self.config.embedding.model,
            )
            embedding = response.data[0].embedding
            self._embedding_cache[text] = embedding
            return embedding
        except Exception as e:
            logger.warning("Embedding generation failed for '%s': %s", text[:50], e)
            return None

    # ============================================================
    # Strategy 5: LLM-based analysis
    # ============================================================

    def _llm_lookup(
        self, id_key: str, value: str, record: NormalizedRecord
    ) -> Optional[ResolvedLink]:
        """
        Use LLM to analyze whether an unresolved name matches any existing entity.
        The LLM receives top-5 candidates and picks one (or none).
        It cannot invent entity IDs — only select from real candidates.
        """
        if id_key not in self._fuzzy_match_fields:
            return None

        table, column, entity_type = self._fuzzy_match_fields[id_key]

        # Get top 5 candidates (even below fuzzy threshold).
        # COALESCE the similarity: rows whose {column} is NULL yield a NULL
        # similarity, and float(None) crashed the resolver (failed every record
        # whose top candidate had a NULL name, e.g. unnamed drug stubs).
        candidates_rows = self.db.fetch_all(
            f"""
            SELECT id, {column} AS name,
                   COALESCE(similarity({column}, %s), 0) AS sim
            FROM {table}
            ORDER BY similarity({column}, %s) DESC NULLS LAST
            LIMIT 5
            """,
            [value, value],
        )

        if not candidates_rows or float(candidates_rows[0]["sim"] or 0) < 0.1:
            return None

        source_type = record.raw.provenance.source_type.value
        candidate_list = [
            {"name": r["name"], "similarity": round(float(r["sim"]), 3)}
            for r in candidates_rows
        ]

        # Use domain pack prompt template if available
        if self.domain_pack and self.domain_pack.llm_resolution_prompt:
            prompt = self.domain_pack.llm_resolution_prompt.format(
                domain=self.domain_pack.name,
                entity_type=entity_type,
                value=value,
                source_type=source_type,
                external_id=record.raw.external_id,
                candidates_json=json.dumps(candidate_list, indent=2),
            )
        else:
            prompt = (
                "You are a pharmaceutical entity resolution system. "
                f"Determine if the query {entity_type} matches any of the candidates.\n\n"
                f'Query: "{value}"\n'
                f"Source: {source_type}\n"
                f"Record: {record.raw.external_id}\n\n"
                f"Candidates:\n{json.dumps(candidate_list, indent=2)}\n\n"
                'Respond with JSON only: {"match_index": <0-4 or null if no match>, '
                '"confidence": <0.0-1.0>, '
                '"reasoning": "<1-2 sentence explanation>"}'
            )

        try:
            response = self.openai_client.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0,
            )
            result = json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.warning("LLM resolution failed for '%s': %s", value[:50], e)
            return None

        match_idx = result.get("match_index")
        llm_confidence = float(result.get("confidence", 0))
        reasoning = result.get("reasoning", "")

        candidates = [
            ResolutionCandidate(str(r["id"]), r["name"], float(r["sim"]), "fuzzy")
            for r in candidates_rows
        ]

        trace = ResolutionTrace(
            raw_value=value,
            entity_type=entity_type,
            method="llm",
            confidence=llm_confidence,
            reasoning=f"LLM ({self.llm_model}): {reasoning}",
            candidates=candidates,
        )

        if match_idx is not None and 0 <= match_idx < len(candidates_rows):
            if llm_confidence >= self.llm_confidence_threshold:
                matched = candidates_rows[match_idx]
                trace.accepted = True
                return ResolvedLink(
                    entity_type=entity_type,
                    entity_id=str(matched["id"]),
                    matched_via="llm",
                    confidence=llm_confidence,
                    matched_value=value,
                    trace=trace,
                )

        # LLM said no match or low confidence — log the trace anyway
        trace.accepted = False
        self._log_audit(trace, record)
        return None

    # ============================================================
    # Strategy 6: Auto-create entity
    # ============================================================

    def _auto_create(
        self, id_key: str, value: str, record: NormalizedRecord
    ) -> Optional[ResolvedLink]:
        """
        Create the entity if it doesn't exist and the source is credible.
        Only for drugs (from interventions) and companies (from sponsors).
        """
        source_type = record.raw.provenance.source_type
        if source_type.value not in self._auto_create_sources and source_type not in self._auto_create_sources:
            return None

        if id_key == "generic_name":
            return self._auto_create_drug(value, record)
        elif id_key in ("sponsor_name", "company_name"):
            return self._auto_create_company(value, record)

        return None

    def _auto_create_drug(
        self, generic_name: str, record: NormalizedRecord
    ) -> Optional[ResolvedLink]:
        """Create a provisional drug record from trial/article intervention data."""
        raw_name = generic_name.strip()
        if not raw_name or len(raw_name) < 3:
            return None

        # Normalize the mention to extract base compound name
        clean_name = normalize_drug_mention(raw_name)
        if not clean_name or len(clean_name) < 3:
            return None

        # Skip placebo, behavioral interventions, etc.
        if self.domain_pack:
            entity_schema = self.domain_pack.entities.get("drug")
            skip_terms = entity_schema.skip_terms if entity_schema else set()
        else:
            skip_terms = DRUG_SKIP_TERMS
        if clean_name.lower() in skip_terms:
            return None

        # Double-check it really doesn't exist (case-insensitive)
        existing = self.db.fetch_one(
            "SELECT id, generic_name FROM drugs WHERE LOWER(generic_name) = LOWER(%s)",
            [clean_name],
        )
        if existing:
            # Normalized name matched — create alias from the raw mention
            if raw_name.lower() != clean_name.lower():
                self._create_alias(
                    entity_type="drug",
                    entity_id=str(existing["id"]),
                    alias_text=raw_name,
                    source_type=record.raw.provenance.source_type,
                    confidence=1.0,
                )
                logger.debug(
                    "Normalized drug '%s' → '%s' matched existing '%s'; alias created",
                    raw_name, clean_name, existing["generic_name"],
                )
            return ResolvedLink(
                entity_type="drug",
                entity_id=str(existing["id"]),
                matched_via="exact_name_icase",
                confidence=1.0,
                matched_value=clean_name,
                trace=ResolutionTrace(
                    raw_value=clean_name,
                    entity_type="drug",
                    method="exact_name_icase",
                    confidence=1.0,
                    reasoning=f"Case-insensitive exact match found: '{existing['generic_name']}'",
                    candidates=[ResolutionCandidate(str(existing["id"]), existing["generic_name"], 1.0, "exact_name_icase")],
                ),
            )

        # Create the drug
        prov = record.raw.provenance
        try:
            new_row = self.db.fetch_one(
                """
                INSERT INTO drugs (generic_name, source_authority, source_api, source_url, retrieved_at)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                [clean_name, prov.source_type.value, prov.source_type.value, prov.api_endpoint, prov.retrieved_at],
            )
        except Exception as e:
            # Unique constraint race condition — try lookup again
            logger.debug("Auto-create drug race condition for '%s': %s", clean_name, e)
            existing = self.db.fetch_one(
                "SELECT id FROM drugs WHERE LOWER(generic_name) = LOWER(%s)",
                [clean_name],
            )
            if existing:
                return ResolvedLink(
                    entity_type="drug",
                    entity_id=str(existing["id"]),
                    matched_via="auto_create",
                    confidence=1.0,
                    matched_value=clean_name,
                )
            return None

        if new_row:
            logger.info("Auto-created drug '%s' from %s", clean_name, prov.source_type.value)
            # Store raw mention as alias if normalization changed it
            if raw_name.lower() != clean_name.lower():
                self._create_alias(
                    entity_type="drug",
                    entity_id=str(new_row["id"]),
                    alias_text=raw_name,
                    source_type=prov.source_type,
                    confidence=1.0,
                )
            return ResolvedLink(
                entity_type="drug",
                entity_id=str(new_row["id"]),
                matched_via="auto_create",
                confidence=1.0,
                matched_value=clean_name,
                trace=ResolutionTrace(
                    raw_value=raw_name,
                    entity_type="drug",
                    method="auto_create",
                    confidence=1.0,
                    reasoning=(
                        f"Normalized '{raw_name}' → '{clean_name}'. "
                        f"No existing drug matched. "
                        f"Auto-created from {prov.source_type.value} data."
                    ),
                    candidates=[],
                ),
            )
        return None

    def _auto_create_company(
        self, name: str, record: NormalizedRecord
    ) -> Optional[ResolvedLink]:
        """Create a provisional company record from trial sponsor data."""
        raw_name = name.strip()
        if not raw_name or len(raw_name) < 3:
            return None

        # Normalize the company name to strip suffixes and noise
        clean_name = normalize_company_mention(raw_name)
        if not clean_name or len(clean_name) < 3:
            return None

        # Skip non-company terms
        if clean_name.lower() in COMPANY_SKIP_TERMS:
            return None

        # Case-insensitive check using normalized name
        existing = self.db.fetch_one(
            "SELECT id, name FROM companies WHERE LOWER(name) = LOWER(%s)",
            [clean_name],
        )
        if existing:
            # Normalized name matched — create alias from the raw mention
            if raw_name.lower() != clean_name.lower():
                self._create_alias(
                    entity_type="company",
                    entity_id=str(existing["id"]),
                    alias_text=raw_name,
                    source_type=record.raw.provenance.source_type,
                    confidence=1.0,
                )
                logger.debug(
                    "Normalized company '%s' → '%s' matched existing '%s'; alias created",
                    raw_name, clean_name, existing["name"],
                )
            return ResolvedLink(
                entity_type="company",
                entity_id=str(existing["id"]),
                matched_via="exact_name_icase",
                confidence=1.0,
                matched_value=clean_name,
                trace=ResolutionTrace(
                    raw_value=raw_name,
                    entity_type="company",
                    method="exact_name_icase",
                    confidence=1.0,
                    reasoning=f"Case-insensitive exact match found: '{existing['name']}'",
                    candidates=[ResolutionCandidate(str(existing["id"]), existing["name"], 1.0, "exact_name_icase")],
                ),
            )

        prov = record.raw.provenance
        try:
            new_row = self.db.fetch_one(
                """
                INSERT INTO companies (name, source_api, source_url, retrieved_at)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                [clean_name, prov.source_type.value, prov.api_endpoint, prov.retrieved_at],
            )
        except Exception as e:
            logger.debug("Auto-create company race condition for '%s': %s", clean_name, e)
            existing = self.db.fetch_one(
                "SELECT id FROM companies WHERE LOWER(name) = LOWER(%s)",
                [clean_name],
            )
            if existing:
                return ResolvedLink(
                    entity_type="company",
                    entity_id=str(existing["id"]),
                    matched_via="auto_create",
                    confidence=1.0,
                    matched_value=clean_name,
                )
            return None

        if new_row:
            logger.info("Auto-created company '%s' from %s", clean_name, prov.source_type.value)
            # Store raw mention as alias if normalization changed it
            if raw_name.lower() != clean_name.lower():
                self._create_alias(
                    entity_type="company",
                    entity_id=str(new_row["id"]),
                    alias_text=raw_name,
                    source_type=prov.source_type,
                    confidence=1.0,
                )
            return ResolvedLink(
                entity_type="company",
                entity_id=str(new_row["id"]),
                matched_via="auto_create",
                confidence=1.0,
                matched_value=clean_name,
                trace=ResolutionTrace(
                    raw_value=raw_name,
                    entity_type="company",
                    method="auto_create",
                    confidence=1.0,
                    reasoning=(
                        f"Normalized '{raw_name}' → '{clean_name}'. "
                        f"No existing company matched. "
                        f"Auto-created from {prov.source_type.value}."
                    ),
                    candidates=[],
                ),
            )
        return None

    # ============================================================
    # Ontology-mediated lookup (unchanged from original)
    # ============================================================

    def _ontology_lookup(self, ontology_id: str, ontology_config=None) -> list[ResolvedLink]:
        """Find all entities linked to an ontology ID (MeSH, GO, etc.)."""
        links = []

        if ontology_config and hasattr(ontology_config, 'lookups'):
            # Domain pack-driven ontology lookup
            for table, id_column, entity_type in ontology_config.lookups:
                rows = self.db.fetch_all(
                    f"SELECT id FROM {table} WHERE {id_column} = %s",
                    [ontology_id],
                )
                for row in rows:
                    links.append(ResolvedLink(
                        entity_type=entity_type,
                        entity_id=str(row["id"]),
                        matched_via="ontology",
                        confidence=1.0,
                        matched_value=ontology_id,
                    ))
        else:
            # Fallback: hardcoded MeSH lookup
            rows = self.db.fetch_all(
                "SELECT id FROM therapeutic_areas WHERE mesh_id = %s",
                [ontology_id],
            )
            for row in rows:
                links.append(ResolvedLink(
                    entity_type="therapeutic_area",
                    entity_id=str(row["id"]),
                    matched_via="ontology",
                    confidence=1.0,
                    matched_value=ontology_id,
                ))

            rows = self.db.fetch_all(
                "SELECT id FROM mechanisms_of_action WHERE mesh_id = %s",
                [ontology_id],
            )
            for row in rows:
                links.append(ResolvedLink(
                    entity_type="mechanism",
                    entity_id=str(row["id"]),
                    matched_via="ontology",
                    confidence=1.0,
                    matched_value=ontology_id,
                ))

        return links

    # ============================================================
    # Alias management
    # ============================================================

    def _create_alias(
        self,
        entity_type: str,
        entity_id: str,
        alias_text: str,
        source_type: SourceType,
        confidence: float,
    ) -> None:
        """Store a confirmed alias for future instant lookups."""
        self.db.execute(
            """
            INSERT INTO entity_aliases (entity_type, entity_id, alias_text, source_type, confidence)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (entity_type, alias_text, source_type) DO NOTHING
            """,
            [entity_type, entity_id, alias_text, source_type.value, confidence],
        )

    # ============================================================
    # Audit logging
    # ============================================================

    def _log_audit(self, trace: Optional[ResolutionTrace], record: NormalizedRecord) -> None:
        """Persist resolution decision to the audit table."""
        if not self.audit_enabled or trace is None:
            return

        candidates_json = json.dumps([
            {"id": c.entity_id, "name": c.entity_name, "score": c.score, "method": c.method}
            for c in trace.candidates
        ]) if trace.candidates else None

        resolved_id = None
        if trace.accepted and trace.candidates:
            resolved_id = trace.candidates[0].entity_id

        try:
            self.db.execute(
                """
                INSERT INTO resolution_audit
                    (raw_value, entity_type, resolved_entity_id, resolution_method,
                     confidence, reasoning, candidates_considered, source_type,
                     source_record_id, accepted)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                """,
                [
                    trace.raw_value,
                    trace.entity_type,
                    resolved_id,
                    trace.method,
                    trace.confidence,
                    trace.reasoning,
                    candidates_json,
                    record.raw.provenance.source_type.value,
                    record.raw.external_id,
                    trace.accepted,
                ],
            )
        except Exception as e:
            logger.warning("Failed to log resolution audit: %s", e)

    def _log_unresolved(
        self,
        raw_value: str,
        record_type: str,
        source_type: SourceType,
        context: dict,
    ) -> None:
        """Log an unmatched entity to the review queue."""
        suggested = None
        if record_type in ("company", "drug"):
            table = "companies" if record_type == "company" else "drugs"
            col = "name" if record_type == "company" else "generic_name"
            row = self.db.fetch_one(
                f"""
                SELECT id, {col} AS name, similarity({col}, %s) AS sim
                FROM {table}
                ORDER BY sim DESC
                LIMIT 1
                """,
                [raw_value],
            )
            if row and row["sim"] > 0.3:
                suggested = row

        try:
            self.db.execute(
                """
                INSERT INTO unresolved_entities
                    (raw_value, record_type, source_type, context,
                     suggested_match_id, suggested_match_name, suggested_confidence)
                VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s)
                """,
                [
                    raw_value,
                    record_type,
                    source_type.value,
                    json.dumps(context),
                    suggested["id"] if suggested else None,
                    suggested["name"] if suggested else None,
                    suggested["sim"] if suggested else None,
                ],
            )
        except Exception as e:
            logger.debug("Failed to log unresolved entity: %s", e)
