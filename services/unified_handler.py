"""UnifiedChatHandler — single handler replacing 8 intent forks.

Uses CTXQueryPipeline for understand→retrieve→reason, then synthesizes
a grounded response with guard checks. A/B switchable via `enabled` flag.

Usage:
    handler = UnifiedChatHandler(corpus_doc=l2, l3_doc=l3, llm=llm, metrics_svc=metrics)
    result = handler.handle("Tell me about semaglutide")
    # result = {"narrative": ..., "intent": ..., "data": ..., "confidence": ..., "guard_status": ...}
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from services.ctx_pipeline import CTXQueryPipeline, QueryPlan, RetrievalResult, ReasoningResult

logger = logging.getLogger(__name__)

# Max evidence items surfaced to the frontend / fed to the LLM as numbered
# snippets. Kept aligned with the legacy dossier path (10) so citation indices
# [1..N] always resolve in the frontend evidence array.
_MAX_EVIDENCE = 10

# CTX section-name prefix → frontend entity_type.
_SECTION_TYPE_PREFIXES = {
    "DRUG": "drug",
    "COMPANY": "company",
    "TRIAL": "trial",
    "MECHANISM": "mechanism",
    "LITERATURE": "literature",
    "EVENT": "event",
    "THERAPEUTIC_AREA": "therapeutic_area",
    "INVESTIGATOR": "investigator",
    "PATENT": "patent",
}


def _parse_section_name(name: str) -> tuple[str, str]:
    """Map a CTX section name (e.g. ``DRUG-SEMAGLUTIDE``) → (entity_type, label)."""
    if not name:
        return "context", ""
    if "-" in name:
        prefix, rest = name.split("-", 1)
        entity_type = _SECTION_TYPE_PREFIXES.get(prefix.upper(), prefix.lower())
        return entity_type, rest.lower().replace("-", " ")
    return "context", name.lower()


def _sections_to_evidence(retrieval: RetrievalResult) -> list[dict]:
    """Convert hydrated CTX sections into frontend EvidenceItem dicts.

    The unified path retrieves text sections rather than the QueryEngine's
    structured EvidenceItem objects, so we lift each section into the same
    shape (source/entity_type/entity_id/content/relevance/provenance) the
    frontend ``CitationRef`` expects. The list order IS the citation order:
    ``[N]`` in the narrative resolves to ``evidence[N-1]``.
    """
    from ctxpack.core.serializer import serialize_section

    source = retrieval.sources_queried[0] if retrieval.sources_queried else "ctx_hydration"
    items: list[dict] = []
    for section in retrieval.ctx_sections[:_MAX_EVIDENCE]:
        name = getattr(section, "name", "") or ""
        entity_type, label = _parse_section_name(name)
        content = "\n".join(serialize_section(section)).strip()
        if not content:
            continue
        items.append(
            {
                "source": source,
                "entity_type": entity_type,
                "entity_id": name,
                "content": content,
                "relevance": 1.0,
                "provenance": {
                    "source": "ctx",
                    "section": name,
                    "entity_type": entity_type,
                    "label": label,
                },
            }
        )
    return items


def _count_by_source(evidence_items: list[dict]) -> dict[str, int]:
    """Tally evidence items per source for the provenance summary."""
    counts: dict[str, int] = {}
    for item in evidence_items:
        src = item.get("source", "ctx_hydration")
        counts[src] = counts.get(src, 0) + 1
    return counts


class UnifiedChatHandler:
    """Unified chat handler using staged CTX pipeline.

    Replaces the 8 intent-specific handlers with a single flow:
    1. Understand (entity detection, intent, coreference)
    2. Retrieve (CTX hydration + metrics + graph)
    3. Reason (sufficiency, gaps, confidence)
    4. Synthesize (grounded LLM narrative + guard)
    """

    def __init__(
        self,
        corpus_doc: Any,
        l3_doc: Any = None,
        llm: Any = None,
        metrics_svc: Any = None,
        db: Any = None,
        engine: Any = None,
    ):
        self.pipeline = CTXQueryPipeline(corpus_doc=corpus_doc, l3_doc=l3_doc)
        self.llm = llm
        self.metrics_svc = metrics_svc
        self.db = db
        self.engine = engine
        self.enabled = True

    def handle(
        self,
        question: str,
        conversation_history: Optional[list[dict]] = None,
        memory_context: Optional[str] = None,
        **kwargs,
    ) -> dict | None:
        """Process a question through the staged pipeline.

        Returns None when disabled (caller should fall back to legacy).
        """
        if not self.enabled:
            return None

        conversation_history = conversation_history or []

        # ── Stage 1: Understand ──
        plan = self.pipeline.understand(question, history=conversation_history)
        logger.info("Unified handler: intent=%s, entities=%s", plan.intent, plan.entities_detected)

        # ── Stage 2: Retrieve ──
        retrieval = self.pipeline.retrieve(plan)

        # Lift retrieved sections into structured evidence items. This is the
        # citation backbone: the frontend resolves [N] → evidence[N-1], and the
        # same snippets (numbered) are fed to the LLM so validate_citations sees
        # evidence_count > 0 and keeps the [N] markers instead of stripping them.
        evidence_items = _sections_to_evidence(retrieval)
        evidence_snippets = [it["content"] for it in evidence_items]

        # Augment with metrics for specific intents
        metrics_data = self._fetch_metrics(plan)

        # ── Stage 3: Reason ──
        reasoning = self.pipeline.reason(plan, retrieval)

        # ── Stage 4: Synthesize ──
        context_text = retrieval.render_context()

        # Add metrics to context if available
        if metrics_data:
            metrics_lines = []
            for key, items in metrics_data.items():
                metrics_lines.append(f"\n{key.upper()}:")
                for item in items[:10]:
                    parts = [f"{k}={v}" for k, v in item.items() if v is not None]
                    metrics_lines.append(f"  - {', '.join(parts)}")
            context_text += "\n\n" + "\n".join(metrics_lines)

        # Build fallback narrative from retrieved data
        fallback = self._build_fallback(plan, retrieval, reasoning, metrics_data)

        # Call LLM with grounded, numbered evidence so citations validate.
        narrative = self._synthesize(
            plan, fallback, evidence_snippets, metrics_data, memory_context,
        )

        # ── Guard check ──
        guard_result = self.pipeline.check_response(narrative, context_text)
        guard_status = guard_result.recommendation

        # ── Build table data ──
        table_data = self._build_table(plan, metrics_data)

        # ── Assemble response ──
        return {
            "narrative": narrative,
            "intent": plan.intent,
            "data": {
                "question": plan.original_question,
                "evidence": evidence_items,
                "graph_context": {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0},
                "metrics_context": metrics_data or {},
                "entity_focus": [
                    {"entity_type": "unknown", "label": e, "title": e}
                    for e in plan.entities_detected
                ],
                "provenance_summary": {
                    "total_evidence_items": len(evidence_items),
                    "by_source": _count_by_source(evidence_items),
                },
            },
            "table_data": table_data,
            "confidence": reasoning.confidence,
            "guard_status": guard_status,
        }

    def _fetch_metrics(self, plan: QueryPlan) -> dict[str, list[dict]]:
        """Fetch relevant metrics based on intent."""
        if not self.metrics_svc:
            return {}

        metrics = {}

        if plan.intent == "landscape":
            # Extract topic for filtering
            topic = None
            for entity in plan.entities_detected:
                topic = entity
                break
            segments = self.metrics_svc.competitive_landscape(
                topic=topic, limit=30,
            ) if hasattr(self.metrics_svc, 'competitive_landscape') else []
            if segments:
                metrics["competitive"] = segments

        elif plan.intent == "pipeline":
            pipelines = self.metrics_svc.drug_pipeline_strength(
                limit=20,
            ) if hasattr(self.metrics_svc, 'drug_pipeline_strength') else []
            if pipelines:
                metrics["pipeline"] = pipelines

        elif plan.intent == "portfolio":
            portfolios = self.metrics_svc.company_portfolio(
                limit=10,
            ) if hasattr(self.metrics_svc, 'company_portfolio') else []
            if portfolios:
                metrics["portfolio"] = portfolios

        return metrics

    def _synthesize(
        self,
        plan: QueryPlan,
        fallback: str,
        evidence_snippets: list[str],
        metrics_data: dict,
        memory_context: Optional[str] = None,
    ) -> str:
        """Call the LLM with grounded, numbered evidence; fall back on failure.

        All intents route through ``synthesize`` so every path feeds the LLM the
        same numbered ``evidence_snippets`` (the intent selects the persona via
        the system prompt). This is what lets ``validate_citations`` keep the
        ``[N]`` markers — the specialized ``synthesize_comparison`` dropped
        snippets entirely, which is why compare emitted 0 citations.
        """
        if not self.llm:
            return fallback

        extra_context = (
            f"CONVERSATION MEMORY:\n{memory_context}" if memory_context else None
        )
        try:
            return self.llm.synthesize(
                question=plan.original_question,
                intent=plan.intent,
                metrics=metrics_data or None,
                evidence_snippets=evidence_snippets,
                extra_context=extra_context,
                fallback_narrative=fallback,
            )
        except Exception as e:
            logger.warning("LLM synthesis failed: %s, using fallback", e)
            return fallback

    def _build_fallback(
        self,
        plan: QueryPlan,
        retrieval: RetrievalResult,
        reasoning: ReasoningResult,
        metrics_data: dict,
    ) -> str:
        """Build template narrative from retrieved data (no LLM)."""
        parts = []

        if not reasoning.sufficient:
            parts.append(f"Limited data available for this query.")
            if reasoning.gaps:
                parts.append(f"Gaps identified: {', '.join(reasoning.gaps[:3])}.")
            return " ".join(parts)

        # Entity-based fallback
        if plan.entities_detected:
            entities_str = ", ".join(f"**{e}**" for e in plan.entities_detected[:5])
            parts.append(f"Retrieved data for {entities_str}.")

        # Metrics-based fallback
        if metrics_data.get("competitive"):
            segments = metrics_data["competitive"]
            parts.append(f"Found **{len(segments)} competitive segments**.")
            if segments:
                top = segments[0]
                parts.append(
                    f"Top segment: **{top.get('mechanism_name', 'Unknown')}** "
                    f"with {top.get('drug_count', 0)} drugs."
                )

        if metrics_data.get("pipeline"):
            pipelines = metrics_data["pipeline"]
            parts.append(f"Found **{len(pipelines)} drugs** in pipeline analysis.")

        # Sections-based fallback
        if retrieval.ctx_sections:
            parts.append(f"Context: {retrieval.token_count} tokens from {len(retrieval.ctx_sections)} sections.")

        if not parts:
            parts.append("Data retrieved but no specific insights to highlight.")

        return " ".join(parts)

    def _build_table(self, plan: QueryPlan, metrics_data: dict) -> dict | None:
        """Build DataTable for structured results."""
        if plan.intent == "landscape" and metrics_data.get("competitive"):
            segments = metrics_data["competitive"]
            return {
                "columns": [
                    {"key": "mechanism_name", "label": "Mechanism", "type": "text"},
                    {"key": "therapeutic_area", "label": "Therapeutic Area", "type": "text"},
                    {"key": "drug_count", "label": "Drugs", "type": "number"},
                    {"key": "trial_count", "label": "Trials", "type": "number"},
                ],
                "rows": [
                    {
                        "mechanism_name": s.get("mechanism_name", ""),
                        "therapeutic_area": s.get("therapeutic_area", ""),
                        "drug_count": s.get("drug_count", 0),
                        "trial_count": s.get("trial_count", 0),
                    }
                    for s in segments[:15]
                ],
                "title": "Competitive Landscape",
            }

        if plan.intent == "pipeline" and metrics_data.get("pipeline"):
            pipelines = metrics_data["pipeline"]
            return {
                "columns": [
                    {"key": "drug_name", "label": "Drug", "type": "text"},
                    {"key": "pipeline_score", "label": "Pipeline Score", "type": "number"},
                    {"key": "total_trials", "label": "Trials", "type": "number"},
                ],
                "rows": [
                    {
                        "drug_name": p.get("drug_name", ""),
                        "pipeline_score": p.get("pipeline_score", 0),
                        "total_trials": p.get("total_trials", 0),
                    }
                    for p in pipelines[:15]
                ],
                "title": "Drug Pipeline",
            }

        return None
