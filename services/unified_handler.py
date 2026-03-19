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

        # Build grounded system prompt
        system_prompt = self.pipeline.build_system_prompt(intent=plan.intent)

        # Build fallback narrative from retrieved data
        fallback = self._build_fallback(plan, retrieval, reasoning, metrics_data)

        # Call LLM with grounded context
        narrative = self._synthesize(plan, context_text, system_prompt, fallback, reasoning)

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
                "evidence": [],
                "graph_context": {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0},
                "metrics_context": metrics_data or {},
                "entity_focus": [
                    {"entity_type": "unknown", "label": e, "title": e}
                    for e in plan.entities_detected
                ],
                "provenance_summary": {
                    "total_evidence_items": len(retrieval.ctx_sections),
                    "by_source": {s: 1 for s in retrieval.sources_queried},
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
        context: str,
        system_prompt: str,
        fallback: str,
        reasoning: ReasoningResult,
    ) -> str:
        """Call LLM with grounded context, fall back on failure."""
        if not self.llm:
            return fallback

        try:
            # Route to appropriate LLM method based on intent
            if plan.intent == "compare":
                return self.llm.synthesize_comparison(
                    entity_names=plan.entities_detected,
                    fallback_narrative=fallback,
                )
            elif plan.intent == "dossier":
                return self.llm.synthesize_dossier(
                    fallback_narrative=fallback,
                )
            else:
                return self.llm.synthesize(
                    question=plan.original_question,
                    intent=plan.intent,
                    extra_context=context,
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
