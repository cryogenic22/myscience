"""CTXQueryPipeline — Staged retrieve→reason→synthesize using CTX hydration.

Replaces the 8-handler intent fork with a unified pipeline that:
1. Understands (entity detection, coreference, classification)
2. Retrieves (CTX hydration + entity graph expansion)
3. Reasons (sufficiency check, gap detection, conflict detection)

Usage:
    pipeline = CTXQueryPipeline(corpus_doc=l2_doc, l3_doc=l3_doc)
    plan = pipeline.understand("Tell me about semaglutide")
    retrieval = pipeline.retrieve(plan)
    reasoning = pipeline.reason(plan, retrieval)
"""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Add ctxpack to path




from ctxpack.core.model import CTXDocument, Section
from ctxpack.core.hydrator import hydrate_by_name, hydrate_by_query, list_sections
from ctxpack.core.entity_graph import EntityGraph
from ctxpack.core.serializer import serialize
from ctxpack.modules.keywords import KeywordIndex
from ctxpack.modules.guard import ContextGuard, GuardResult
from ctxpack.modules.grounding import build_tail_reminder, count_catalog_entities


# ── Data classes ──

@dataclass
class QueryPlan:
    """Output of the Understand stage."""
    original_question: str
    resolved_question: str
    entities_detected: list[str] = field(default_factory=list)
    intent: str = "general"
    suggested_sources: list[str] = field(default_factory=list)


@dataclass
class RetrievalResult:
    """Output of the Retrieve stage."""
    ctx_sections: list[Section] = field(default_factory=list)
    token_count: int = 0
    sources_queried: list[str] = field(default_factory=list)
    _header_text: str = ""
    _section_texts: dict[str, str] = field(default_factory=dict)

    def render_context(self) -> str:
        """Render retrieved data as text for LLM consumption."""
        parts = []
        if self._header_text:
            parts.append(self._header_text)
        for section in self.ctx_sections:
            lines = list(_serialize_section_lines(section))
            parts.append("\n".join(lines))
        return "\n\n".join(parts)


@dataclass
class ReasoningResult:
    """Output of the Reason stage."""
    sufficient: bool = True
    gaps: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    confidence: float = 0.5
    refined_queries: list[str] = field(default_factory=list)
    computed_insights: list[str] = field(default_factory=list)
    retrieval: Optional[RetrievalResult] = None


# ── Helpers ──

def _serialize_section_lines(section: Section):
    """Yield serialized lines for a section."""
    from ctxpack.core.serializer import serialize_section
    yield from serialize_section(section)


# Intent detection patterns (reused from chat.py logic)
_COMPARE_RE = re.compile(
    r'\b(?:compare|versus|vs\.?)\b|(.+?)\s+vs\.?\s+(.+)', re.IGNORECASE
)
_LANDSCAPE_RE = re.compile(
    r'\b(?:landscape|competitive|market\s+(?:segments|overview))\b', re.IGNORECASE
)
_PIPELINE_RE = re.compile(
    r'\b(?:pipeline|drug\s+pipeline|phase\s+distribution)\b', re.IGNORECASE
)
_PORTFOLIO_RE = re.compile(r'\bportfolio\b', re.IGNORECASE)

# "Which companies dominate X", "who are the leaders in X", "what firms make X"
# — competitive questions that must route to landscape so the grounded metrics
# fire (instead of falling through to 'general' and hallucinating a dominant
# entity). Kept narrow: requires a market-actor noun OR an explicit dominance verb.
_LEADERS_RE = re.compile(
    r'\b(?:which|what|who|name)\b[^?]*\b(?:compan(?:y|ies)|players?|makers?|'
    r'manufacturers?|firms?|leaders?|developers?|vendors?)\b'
    r'|\b(?:dominate|dominates|dominating|market\s+leaders?|biggest\s+players?|'
    r'who\s+(?:makes|develops|sells|manufactures|leads?)|leads?\s+the\s+'
    r'(?:market|space|area|field))\b',
    re.IGNORECASE,
)
# "Phase 3 for X", "in Phase II" → pipeline (unless it's a count question, see below).
_PHASE_RE = re.compile(r'\bphase\s*(?:1|2|3|4|i{1,3}|iv)\b', re.IGNORECASE)
# Count/aggregation questions must stay structured even when they mention a phase.
_COUNT_RE = re.compile(r'\b(?:how many|count|total number|number of)\b', re.IGNORECASE)

# Organisation entities that are research/academic/clinical sponsors, NOT pharma
# market players. Disease words ("diabetes") keyword-match their names
# ("Baker Heart and Diabetes Institute") and mislead synthesis. Filtered from
# entity detection and (in metrics) from company rankings.
# Word-bounded so partial words don't false-positive (e.g. "Centene",
# "Centessa", a drug name containing "carb"). Morphological suffixes
# (institut\w*, universit\w*) catch institute/institutes/university/universities.
_JUNK_ORG_RE = re.compile(
    r'\b(?:institut\w*|universit\w*|college|school|foundation|hospital|'
    r'registry|ministry|department|center|centre|clinic|trust|consortium|'
    r'society|association|polyclinic)\b'
    r'|medical\s+cent(?:er|re)|health\s+system',
    re.IGNORECASE,
)


def _is_junk_org(name: str) -> bool:
    """True if a section/entity name is a research/academic/clinical org rather
    than a pharma market player. Used to keep disease-word queries from
    resolving to e.g. 'Dasman Diabetes Institute'."""
    return bool(name and _JUNK_ORG_RE.search(name))


def is_company_leaders_question(question: str) -> bool:
    """True for 'which companies dominate/lead/make X' — a company-centric
    question that needs a company-naming synthesis, not the mechanism-centric
    landscape persona (which is explicitly instructed NOT to name companies)."""
    return bool(question and _LEADERS_RE.search(question))


_STRUCTURED_PATTERNS = [
    re.compile(r'\b(?:how many|count|total number)\b', re.IGNORECASE),
    re.compile(r'\b(?:average|avg|mean|median)\b', re.IGNORECASE),
    re.compile(r'\b(?:top\s+\d+|bottom\s+\d+|rank)\b', re.IGNORECASE),
    re.compile(r'\b(?:by company|by drug|group by)\b', re.IGNORECASE),
    re.compile(r'\b(?:percentage|percent|rate|ratio)\b', re.IGNORECASE),
    re.compile(r'\b(?:list all|show all|every)\b', re.IGNORECASE),
]

# Coreference patterns
_COREF_PATTERNS = [
    (re.compile(r'\b(?:its?|their)\s+(pipeline|mechanism|company|portfolio|trials?)', re.I), 1),
    (re.compile(r'\b(?:this|that)\s+(space|area|market|drug|company|mechanism)', re.I), 1),
    (re.compile(r'\b(?:the same|those|these)\s+(\w+)', re.I), 1),
]


class CTXQueryPipeline:
    """Staged query pipeline using CTX hydration.

    Components:
        - KeywordIndex: Fast entity name matching
        - EntityGraph: Multi-hop relationship traversal
        - ContextGuard: Hallucination detection
        - Hydration: Query-adaptive section retrieval
    """

    def __init__(
        self,
        corpus_doc: CTXDocument,
        l3_doc: Optional[CTXDocument] = None,
    ):
        self.corpus_doc = corpus_doc
        self.l3_doc = l3_doc

        # Build keyword index from corpus
        self.keyword_index = KeywordIndex.from_document(corpus_doc)

        # Build entity graph for relationship traversal
        self.entity_graph = EntityGraph.from_document(corpus_doc)

        # Build section index for routing
        self._sections = list_sections(corpus_doc)

        # Extract entity names for guard
        entity_names: set[str] = set()
        for section in self._sections:
            name = section.get("name", "")
            entity_names.add(name)
            # Also add the entity name without prefix
            if "-" in name:
                short = name.split("-", 1)[-1].lower().replace("-", " ")
                entity_names.add(short)
        self._entity_names = entity_names

        # Context guard for hallucination detection
        self.guard = ContextGuard(
            known_entity_names=entity_names,
            on_low_confidence="warn",
        )

        # Cache L3 text for system prompt
        self._l3_text = serialize(l3_doc) if l3_doc else ""

    @property
    def available_sections(self) -> list[dict]:
        """List available sections for routing."""
        return self._sections

    # ── Stage 1: Understand ──

    def understand(
        self,
        question: str,
        history: Optional[list[dict]] = None,
    ) -> QueryPlan:
        """Parse question → entities, intent, sources."""
        history = history or []

        # Resolve coreferences
        resolved = self._resolve_coreference(question, history)

        # Detect entities via keyword index
        matched_sections = self.keyword_index.match(resolved)
        entities = []
        for section_name in matched_sections:
            # Skip research/academic/clinical orgs — disease words ("diabetes")
            # keyword-match their names ("...Diabetes Institute") and mislead
            # synthesis into naming a non-market-player as dominant.
            if _is_junk_org(section_name):
                continue
            # Extract entity name from section name (e.g., "DRUG-SEMAGLUTIDE" → "semaglutide")
            if "-" in section_name:
                entity_name = section_name.split("-", 1)[-1].lower().replace("-", " ")
            else:
                entity_name = section_name.lower()
            entities.append(entity_name)

        # Also try to extract entities from the compare pattern
        compare_match = re.search(r'(.+?)\s+vs\.?\s+(.+?)(?:\?|$)', resolved, re.IGNORECASE)
        if compare_match:
            for g in compare_match.groups():
                name = g.strip().lower()
                if name and name not in entities:
                    entities.append(name)

        # Classify intent
        intent = self._classify_intent(resolved)

        # Suggest sources
        sources = self._suggest_sources(intent, entities)

        return QueryPlan(
            original_question=question,
            resolved_question=resolved,
            entities_detected=entities,
            intent=intent,
            suggested_sources=sources,
        )

    def _classify_intent(self, question: str) -> str:
        """Classify question intent."""
        if _COMPARE_RE.search(question):
            return "compare"
        # "which companies dominate X" / "who leads X" → competitive landscape.
        # (A count phrasing — "how many companies…" — stays structured.)
        if _LEADERS_RE.search(question) and not _COUNT_RE.search(question):
            return "landscape"
        if _LANDSCAPE_RE.search(question):
            return "landscape"
        if _PORTFOLIO_RE.search(question):
            return "portfolio"

        # Count questions stay structured even if they mention a phase.
        is_count = bool(_COUNT_RE.search(question))
        if _PIPELINE_RE.search(question) or (_PHASE_RE.search(question) and not is_count):
            return "pipeline"

        # Check for structured query patterns
        hits = sum(1 for p in _STRUCTURED_PATTERNS if p.search(question))
        if hits >= 1:
            return "structured_query"

        # Check for dossier-like queries
        if re.search(r'\b(?:tell me about|what is|who is|describe)\b', question, re.I):
            return "dossier"

        return "general"

    def _resolve_coreference(self, question: str, history: list[dict]) -> str:
        """Resolve pronouns/demonstratives using conversation history."""
        if not history:
            return question

        # Extract prior topic from last assistant message
        prior_topic = ""
        for msg in reversed(history):
            if msg.get("role") == "user":
                # Extract entities from prior question
                prior_q = msg.get("content", "")
                # Try keyword matching on prior question
                matches = self.keyword_index.match(prior_q)
                if matches:
                    section = matches[0]
                    if "-" in section:
                        prior_topic = section.split("-", 1)[-1].lower().replace("-", " ")
                    break
            elif msg.get("role") == "assistant":
                content = msg.get("content", "")
                # Extract bold entities
                bold_matches = re.findall(r'\*\*([^*]+)\*\*', content)
                if bold_matches:
                    prior_topic = bold_matches[0].lower()
                    break

        if not prior_topic:
            return question

        resolved = question
        for pattern, group in _COREF_PATTERNS:
            if pattern.search(resolved):
                resolved = pattern.sub(f"{prior_topic} \\{group}", resolved)

        return resolved

    def _suggest_sources(self, intent: str, entities: list[str]) -> list[str]:
        """Suggest data sources based on intent."""
        sources = ["ctx_hydration"]

        if intent == "structured_query":
            sources.append("sql_aggregation")
        if intent in ("dossier", "compare", "general"):
            sources.append("graph_traversal")
            sources.append("vector_search")
        if intent == "landscape":
            sources.append("metrics.competitive_landscape")
        if intent == "pipeline":
            sources.append("metrics.drug_pipeline_strength")
        if intent == "portfolio":
            sources.append("metrics.company_portfolio")

        return sources

    # ── Stage 1.5: PLAN (Domain Intelligence — DI-2) ──

    def plan_decomposition(self, intent: str, entities: list[dict], db: Any,
                           as_of: Optional[Any] = None):
        """The PLAN stage: decompose a nuanced question into a grounded,
        per-dimension matrix (entities × dimensions) before generic retrieval.

        Sits between understand and retrieve, per the Domain Intelligence spec.
        `entities` are pre-resolved [{entity_id, entity_type, label}, ...]; `db`
        is passed in so the pipeline keeps its corpus-only constructor contract.

        Returns a QuestionMatrix, or None when no playbook matches the
        (intent × entity-type signature) — callers fall back to generic
        retrieval (graceful degradation). Failures never raise into the pipeline.
        """
        try:
            from services.domain_intelligence.planner import DecompositionPlanner
            return DecompositionPlanner(db).plan(intent, entities, as_of=as_of)
        except Exception:
            logger.debug("PLAN stage skipped (decomposition failed)", exc_info=True)
            return None

    # ── Stage 2: Retrieve ──

    def retrieve(self, plan: QueryPlan) -> RetrievalResult:
        """Hydrate relevant sections from CTX corpus."""
        sources_queried = []

        # Strategy 1: Hydrate by entity names (if we have them)
        sections = []
        header_text = ""

        if plan.entities_detected:
            # Map entities back to section names
            section_names = []
            for entity in plan.entities_detected:
                matches = self.keyword_index.match(entity)
                section_names.extend(matches)

            # Also expand via entity graph (1-hop)
            for section_name in list(section_names):
                neighbors = self.entity_graph.neighbors(section_name)
                section_names.extend(neighbors)

            # Deduplicate
            section_names = list(dict.fromkeys(section_names))

            if section_names:
                hydration = hydrate_by_name(
                    self.corpus_doc,
                    section_names[:10],  # cap at 10 sections
                )
                sections = hydration.sections
                header_text = hydration.header_text
                sources_queried.append("ctx_hydration_by_name")

        # Strategy 2: Fallback to query-based hydration
        if not sections:
            hydration = hydrate_by_query(
                self.corpus_doc,
                plan.resolved_question,
                max_sections=5,
            )
            sections = hydration.sections
            header_text = hydration.header_text
            sources_queried.append("ctx_hydration_by_query")

        # Count tokens
        token_count = 0
        for section in sections:
            lines = list(_serialize_section_lines(section))
            text = "\n".join(lines)
            token_count += len(text) // 4  # rough estimate

        return RetrievalResult(
            ctx_sections=sections,
            token_count=token_count,
            sources_queried=sources_queried,
            _header_text=header_text,
        )

    # ── Stage 3: Reason ──

    def reason(self, plan: QueryPlan, retrieval: RetrievalResult) -> ReasoningResult:
        """Evaluate sufficiency, detect gaps and conflicts."""
        gaps = []
        conflicts = []
        computed_insights = []

        # Check sufficiency: do we have sections for the requested entities?
        found_entities = set()
        context_text = retrieval.render_context().lower()
        for entity in plan.entities_detected:
            entity_lower = entity.lower()
            # Match if the entity name (or its significant words) appear in context
            words = [w for w in entity_lower.split() if len(w) > 2]
            if entity_lower in context_text:
                found_entities.add(entity)
            elif words and all(w in context_text for w in words):
                found_entities.add(entity)
            elif any(w in context_text for w in words if len(w) > 4):
                # Partial match on significant words (>4 chars)
                found_entities.add(entity)

        missing = [e for e in plan.entities_detected if e not in found_entities]
        if missing:
            for m in missing:
                gaps.append(f"No data found for entity: {m}")

        # Sufficiency check
        if not retrieval.ctx_sections:
            sufficient = False
            gaps.append("No relevant sections found in knowledge base")
        elif plan.entities_detected and len(found_entities) == 0:
            sufficient = False
            gaps.append("None of the requested entities found in retrieved data")
        else:
            sufficient = True

        # Confidence scoring
        if not plan.entities_detected:
            confidence = 0.3  # No entities detected = low confidence
        elif not sufficient:
            confidence = 0.2
        elif len(found_entities) == len(plan.entities_detected):
            confidence = 0.8  # All entities found
        else:
            confidence = 0.5  # Partial match

        # Boost confidence if we have substantial content
        if retrieval.token_count > 200:
            confidence = min(1.0, confidence + 0.1)

        # Compute insights for comparisons
        if plan.intent == "compare" and len(plan.entities_detected) >= 2:
            computed_insights.append(
                f"Comparing {len(plan.entities_detected)} entities: {', '.join(plan.entities_detected)}"
            )

        return ReasoningResult(
            sufficient=sufficient,
            gaps=gaps,
            conflicts=conflicts,
            confidence=confidence,
            computed_insights=computed_insights,
            retrieval=retrieval,
        )

    # ── Guard & Grounding ──

    def check_response(self, response: str, context: str = "") -> GuardResult:
        """Check LLM response for hallucination signals."""
        return self.guard.check(response, hydrated_context=context)

    def build_system_prompt(self, intent: str = "general") -> str:
        """Build grounded system prompt with entity catalog."""
        # Count entities in corpus
        entity_count = len([
            s for s in self._sections
            if s.get("name", "").startswith(("DRUG-", "COMPANY-", "MECHANISM-", "TRIAL-"))
        ])
        if entity_count == 0:
            entity_count = len(self._sections)

        # Build tail reminder (grounding checklist)
        tail = build_tail_reminder(
            entity_count=entity_count,
            entity_type="pharma entities",
            citation_format="[N]",
            custom_rules=[
                "Do NOT inject clinical trial results from your training data.",
                "If the data doesn't cover a dimension, say 'data not available'.",
            ],
        )

        # Combine intent-specific persona + grounding
        persona = self._get_persona(intent)

        return f"{persona}\n\n{tail}"

    def _get_persona(self, intent: str) -> str:
        """Get intent-specific persona instruction."""
        personas = {
            "dossier": "You are a senior pharmaceutical intelligence analyst providing an entity profile.",
            "compare": "You are a senior pharmaceutical intelligence analyst comparing entities head-to-head.",
            "landscape": "You are a senior pharmaceutical intelligence analyst analyzing competitive landscape segments by therapeutic area.",
            "pipeline": "You are a senior pharmaceutical intelligence analyst reporting on drug pipeline metrics.",
            "portfolio": "You are a senior pharmaceutical intelligence analyst reviewing a company portfolio.",
            "general": "You are a senior pharmaceutical intelligence analyst answering questions with precision.",
        }
        return personas.get(intent, personas["general"])
