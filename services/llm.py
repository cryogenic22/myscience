"""
LLM Synthesis Service for Market-Zero.

Takes structured data (evidence, metrics, graph context) gathered by the
deterministic service layer and synthesizes it into analyst-grade narratives
using an LLM. Falls back to template narratives if no API key is configured
or if the LLM call fails.

Architecture rationale:
  - Deterministic services handle data gathering (fast, reliable, complete)
  - LLM handles ONLY synthesis (what it's good at: turning data into insight)
  - Single LLM call per request (~2-3s latency), not multi-step agent chains
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


# ── Post-synthesis validation ──────────────────────────────────────

_CITATION_RE = re.compile(r"\[(\d+)\]")


def validate_citations(narrative: str, evidence_count: int) -> dict:
    """Validate citation markers [N] in narrative against evidence count.

    Strips invalid citations (N > evidence_count or N == 0).
    Returns: {"narrative": cleaned_text, "valid": int, "stripped": int}
    """
    if not narrative:
        return {"narrative": "", "valid": 0, "stripped": 0}

    valid = 0
    stripped = 0

    def _replace(match):
        nonlocal valid, stripped
        n = int(match.group(1))
        if 1 <= n <= evidence_count:
            valid += 1
            return match.group(0)  # keep
        stripped += 1
        logger.debug("Stripped invalid citation [%d] (evidence_count=%d)", n, evidence_count)
        return ""  # remove

    cleaned = _CITATION_RE.sub(_replace, narrative)
    # Clean up double spaces from removed citations
    cleaned = re.sub(r"  +", " ", cleaned)

    return {"narrative": cleaned, "valid": valid, "stripped": stripped}


_BOLD_NUMBER_RE = re.compile(r"\*\*(\d+(?:\.\d+)?%?)\*\*")
_NUMBER_RE = re.compile(r"\b(\d+(?:\.\d+)?)\b")


def _extract_source_numbers(metrics: dict | None, evidence_snippets: list[str] | None) -> set[float]:
    """Extract all numeric values from metrics context and evidence for verification."""
    numbers: set[float] = set()
    if metrics:
        _collect_numbers_from_dict(metrics, numbers)
    if evidence_snippets:
        for snippet in evidence_snippets[:10]:
            for m in _NUMBER_RE.finditer(str(snippet)):
                try:
                    numbers.add(float(m.group(1)))
                except ValueError:
                    pass
    return numbers


def _collect_numbers_from_dict(d: dict | list, out: set[float], depth: int = 0) -> None:
    """Recursively collect numeric values from nested dict/list."""
    if depth > 5:
        return
    if isinstance(d, dict):
        for v in d.values():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                out.add(float(v))
            elif isinstance(v, (dict, list)):
                _collect_numbers_from_dict(v, out, depth + 1)
    elif isinstance(d, list):
        for item in d:
            if isinstance(item, (int, float)) and not isinstance(item, bool):
                out.add(float(item))
            elif isinstance(item, (dict, list)):
                _collect_numbers_from_dict(item, out, depth + 1)


def verify_narrative_numbers(
    narrative: str,
    source_numbers: set[float | int],
    tolerance: float = 1.0,
) -> dict:
    """Extract bold numbers from narrative and verify against source data.

    Extracts **N**, **N.N**, **N%** patterns.
    Numbers within `tolerance` of any source number are verified.

    Returns: {"verified": int, "flagged": int, "mismatches": [...]}
    """
    if not narrative:
        return {"verified": 0, "flagged": 0, "mismatches": []}

    matches = _BOLD_NUMBER_RE.findall(narrative)
    verified = 0
    flagged = 0
    mismatches = []

    for raw in matches:
        clean = raw.rstrip("%")
        try:
            num = float(clean)
        except ValueError:
            continue

        found = False
        for src in source_numbers:
            src_f = float(src)
            if abs(num - src_f) <= tolerance:
                found = True
                break
            # Also check percentage form: 82 matches 0.82
            if 0 < src_f < 1 and abs(num - src_f * 100) <= tolerance:
                found = True
                break

        if found:
            verified += 1
        else:
            flagged += 1
            mismatches.append(num)

    return {"verified": verified, "flagged": flagged, "mismatches": mismatches}


_BASE_RULES = """- Use **bold** for key entities, numbers, and findings.
- STRICT DATA GROUNDING: ONLY use numbers, percentages, and facts that appear in the PROVIDED CONTEXT below. Do NOT supplement with knowledge from your training data. No clinical efficacy numbers, no MACE reductions, no survival rates unless explicitly in the context.
- If the data is thin, say so honestly ("limited data available for X") rather than padding with external knowledge.
- CITATIONS: When you reference a specific fact, include the evidence number in square brackets inline, e.g. [1], [2]. Cite EVIDENCE items by their number. If there is a METRICS section, reference it as [metrics]. Only cite numbers that actually exist in the provided context. If there is NO EVIDENCE section and no METRICS section, do NOT use any citation markers.
- AIM for at least 2 citations per paragraph when evidence is available. Every factual claim should be traceable to a source."""

SYSTEM_PROMPTS: dict[str, str] = {
    "compare": f"""You are a senior pharmaceutical intelligence analyst. You are comparing entities head-to-head.

Rules:
- Lead with the key differentiator — which entity is stronger/weaker and why.
- Use comparative language: "X has 2.3x more trials", "Y leads in Phase 3 with N trials".
- Bold the winner on each dimension.
- Compute and state differentials, don't just list numbers side-by-side.
- End with a 1-sentence verdict.
- 2-3 paragraphs maximum. A comparison table is displayed alongside — don't restate every number.
- CRITICAL: ONLY use numbers and facts from the PROVIDED CONTEXT below. Do NOT inject clinical trial results, efficacy percentages, MACE reductions, or any other statistics from your training data. If the data doesn't cover a dimension, say "data not available" rather than filling in from memory.
- If COMPUTED DIFFERENTIALS are provided, use those exact numbers.
{_BASE_RULES}""",

    "landscape": f"""You are a senior pharmaceutical intelligence analyst. You are analyzing a competitive market landscape.

The data is segmented by THERAPEUTIC AREA (disease indication), NOT by company. Each row represents a therapeutic area where the queried mechanism/drug class is used.

Rules:
- Lead with the concentration insight — which therapeutic areas dominate activity for this mechanism.
- Name the top segments by their therapeutic area and distinguishing metric (drug count, trial volume, pipeline score).
- Do NOT say "dominated by companies" — the segments are therapeutic areas, not companies.
- If therapeutic areas overlap (e.g. "Diabetes Mellitus" and "Diabetes Mellitus, Type 2"), note that broader categories include subcategories and avoid double-counting.
- Note any gaps or underserved therapeutic areas worth investigating.
- 2-3 sentences maximum. A data table is displayed alongside — reference it naturally.
{_BASE_RULES}""",

    "pipeline": f"""You are a senior pharmaceutical intelligence analyst. You are reporting on drug pipeline metrics.

Rules:
- Lead with the headline finding: who leads and with what score.
- Note the phase distribution (early vs. late stage strength).
- Compare to benchmarks when possible (typical Phase 2→3 success ~30%, Phase 3→approval ~60%).
- 2-3 sentences maximum. A pipeline table is displayed alongside.
{_BASE_RULES}""",

    "portfolio": f"""You are a senior pharmaceutical intelligence analyst. You are briefing on a company portfolio.

Rules:
- Lead with the company's position: how many drugs, in what therapeutic areas.
- Note pipeline maturity (early vs. late stage balance).
- Highlight any standout drugs or competitive gaps.
- 2-3 paragraphs maximum. A summary table is displayed alongside.
{_BASE_RULES}""",

    "dossier": f"""You are a senior pharmaceutical intelligence analyst briefing an executive.

Rules:
- Lead with what the entity is and its significance.
- Key metrics in bold: pipeline score, trial count, phase distribution.
- Note any recent developments or notable trial activity.
- 2-4 paragraphs maximum.
{_BASE_RULES}""",

    "tabular": f"""You are a senior pharmaceutical intelligence analyst. The user asked for structured/tabular output.

Rules:
- Write 1-2 sentences ONLY as a brief summary header.
- Do NOT restate numbers from the table — a full data table is displayed below.
- Simply describe what the table shows and call out 1-2 notable patterns.
{_BASE_RULES}""",

    "default": f"""You are a senior pharmaceutical intelligence analyst at a top-tier strategy consulting firm.

Rules:
- Write 2-4 paragraphs maximum. Be concise but insightful.
- Lead with the most important finding or insight.
- Use specific numbers from the data provided.
- Highlight competitive dynamics, risks, and opportunities when relevant.
- You may use bullet points or short lists when they improve clarity.
{_BASE_RULES}""",
}

# Backward-compatible alias
SYSTEM_PROMPT = SYSTEM_PROMPTS["default"]


def _get_system_prompt(intent: str, format_hint: str | None = None) -> str:
    """Select the best system prompt based on intent and format hint."""
    if format_hint == "table":
        return SYSTEM_PROMPTS["tabular"]
    return SYSTEM_PROMPTS.get(intent, SYSTEM_PROMPTS["default"])

RESEARCH_SYSTEM_PROMPT = """You are preparing a decision-support research brief for a pharmaceutical leadership team.

Rules:
- Use clear section headers.
- Be factual and conservative in claims.
- Distinguish internal graph evidence from external web context.
- Do not invent data or citations.
- Keep recommendations actionable and specific to evidence.
- Maximum length: 700 words.
"""


def _compress_evidence(
    evidence_snippets: Optional[list[str]],
    question: str = "",
) -> tuple[Optional[list[str]], Optional[str]]:
    """Try to compress evidence snippets via ctxpack entity resolution.

    Returns (snippets, compressed_block):
    - If compression succeeded: (None, compressed_text) — use compressed_block as extra_context
    - If passthrough/unavailable: (original_snippets, None) — use snippets normally
    """
    if not evidence_snippets:
        return evidence_snippets, None

    try:
        from services.ctx_evidence import pack_evidence
        items = [{"content": s} for s in evidence_snippets]
        compressed_text, metrics = pack_evidence(items, question=question)

        if metrics.get("mode") == "ctx":
            logger.info(
                "Evidence compressed: %d → %d tokens (%.1fx, %d merged)",
                metrics.get("raw_tokens", 0),
                metrics.get("compressed_tokens", 0),
                metrics.get("ratio", 1),
                metrics.get("merged", 0),
            )
            return None, f"EVIDENCE (compressed):\n{compressed_text}"
        else:
            return evidence_snippets, None
    except Exception as e:
        logger.debug("Evidence compression unavailable: %s", e)
        return evidence_snippets, None


def _build_context_block(
    question: str,
    intent: str,
    entity_info: Optional[dict] = None,
    metrics: Optional[dict] = None,
    graph_summary: Optional[dict] = None,
    evidence_snippets: Optional[list[str]] = None,
    extra_context: Optional[str] = None,
    ctx_mode: str = "ctx",
) -> str:
    """Build a structured context block for the LLM.

    Pipeline:
    1. Compress evidence snippets via ctxpack entity resolution (if above threshold)
    2. Assemble full context via CTXContextBuilder (with threshold gate)
    3. Append few-shot exemplars for citation density
    4. Fall back to legacy flat format on failure

    ctx_mode: "ctx" (default) | "legacy"
    """
    # Step 1: Try to compress evidence before context assembly
    snippets_for_ctx, compressed_evidence = _compress_evidence(
        evidence_snippets, question=question,
    )

    # If evidence was compressed, append it to extra_context
    if compressed_evidence:
        if extra_context:
            extra_context = f"{extra_context}\n\n{compressed_evidence}"
        else:
            extra_context = compressed_evidence

    context = None
    try:
        from services.ctx_context import CTXContextBuilder
        builder = CTXContextBuilder(mode=ctx_mode)
        ctx_result = builder.build(
            question=question,
            intent=intent,
            entity_info=entity_info,
            metrics=metrics,
            graph_summary=graph_summary,
            evidence_snippets=snippets_for_ctx,
            extra_context=extra_context,
        )

        # Fire-and-forget telemetry
        try:
            from services.telemetry import log_ctx_event
            from api.deps import get_db
            log_ctx_event(
                db=get_db(),
                question=question,
                intent=intent,
                ctx_tokens=ctx_result.tokens,
                compression_ratio=ctx_result.compression_ratio,
                build_time_ms=ctx_result.build_time_ms,
                mode=ctx_result.mode,
            )
        except Exception:
            pass  # telemetry must never break the main flow

        context = ctx_result.text
    except Exception as e:
        logger.warning("CTX context builder failed, falling back to legacy: %s", e)
        # Fallback to legacy inline
        parts = [f"USER QUESTION: {question}", f"INTENT: {intent}"]
        if entity_info:
            parts.append(f"ENTITY: {json.dumps(entity_info, default=str)}")
        if metrics:
            parts.append(f"METRICS: {json.dumps(metrics, default=str)}")
        if graph_summary:
            parts.append(f"GRAPH CONTEXT: {json.dumps(graph_summary, default=str)}")
        if snippets_for_ctx:
            parts.append("EVIDENCE:")
            for i, snippet in enumerate(snippets_for_ctx[:10], 1):
                parts.append(f"  [{i}] {snippet}")
        if extra_context:
            parts.append(f"ADDITIONAL CONTEXT: {extra_context}")
        context = "\n\n".join(parts)

    # Step 3: Append few-shot exemplars for citation density
    try:
        from services.few_shot_library import FewShotLibrary
        _few_shot_lib = FewShotLibrary()
        exemplars = _few_shot_lib.get_exemplars(intent, max_examples=2)
        if exemplars:
            context += "\n\n" + _few_shot_lib.format_context(exemplars)
    except Exception as e:
        logger.debug("Few-shot library unavailable: %s", e)

    return context


class LLMSynthesizer:
    """Synthesizes structured pharma data into analyst-grade narratives."""

    def __init__(self, config):
        self.config = config
        self._client = None

    @property
    def enabled(self) -> bool:
        return (
            self.config.llm.enabled
            and bool(self.config.llm.api_key)
        )

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.config.llm.api_key)
        return self._client

    def _post_validate(
        self,
        narrative: str,
        evidence_count: int = 0,
        source_numbers: set | None = None,
    ) -> str:
        """Post-synthesis validation: citation check + numeric verification.

        Applied after every LLM synthesis to catch hallucinated citations
        and numeric drift from source data.
        """
        # Citation validation
        cit_result = validate_citations(narrative, evidence_count)
        narrative = cit_result["narrative"]
        if cit_result["stripped"] > 0:
            logger.info("Stripped %d invalid citation(s) from narrative", cit_result["stripped"])

        # Numeric verification (log only, don't modify narrative)
        if source_numbers:
            num_result = verify_narrative_numbers(narrative, source_numbers)
            if num_result["flagged"] > 0:
                logger.warning(
                    "Narrative has %d unverified bold number(s): %s",
                    num_result["flagged"], num_result["mismatches"],
                )

        return narrative

    def synthesize(
        self,
        question: str,
        intent: str,
        entity_info: Optional[dict] = None,
        metrics: Optional[dict] = None,
        graph_summary: Optional[dict] = None,
        evidence_snippets: Optional[list[str]] = None,
        extra_context: Optional[str] = None,
        fallback_narrative: str = "",
        format_hint: Optional[str] = None,
    ) -> str:
        """Synthesize a narrative from structured data.

        Args:
            question: The user's original question.
            intent: Detected intent (dossier, compare, landscape, etc.).
            entity_info: Primary entity details (name, type, properties).
            metrics: Relevant KPIs (pipeline, success rate, etc.).
            graph_summary: Graph neighborhood summary.
            evidence_snippets: Top evidence text snippets.
            extra_context: Any additional context string.
            fallback_narrative: Template narrative to return if LLM is unavailable.
            format_hint: Optional "table" or "chart" to adjust prompt style.

        Returns:
            Synthesized narrative string.
        """
        if not self.enabled:
            return fallback_narrative

        ctx_mode = getattr(self.config.llm, "ctx_mode", "ctx")
        context = _build_context_block(
            question=question,
            intent=intent,
            entity_info=entity_info,
            metrics=metrics,
            graph_summary=graph_summary,
            evidence_snippets=evidence_snippets,
            extra_context=extra_context,
            ctx_mode=ctx_mode,
        )

        system_prompt = _get_system_prompt(intent, format_hint)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context},
        ]

        primary_model = self.config.llm.model
        fallback_model = getattr(self.config.llm, "fallback_model", primary_model)
        models = [primary_model]
        if fallback_model and fallback_model != primary_model:
            models.append(fallback_model)

        client = self._get_client()
        for model in models:
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=self.config.llm.max_tokens,
                    temperature=self.config.llm.temperature,
                )
                narrative = response.choices[0].message.content.strip()
                if narrative:
                    if model != primary_model:
                        logger.info("Used fallback model %s (primary unavailable)", model)
                    # Post-synthesis validation
                    source_nums = _extract_source_numbers(metrics, evidence_snippets)
                    narrative = self._post_validate(
                        narrative,
                        evidence_count=len(evidence_snippets or []),
                        source_numbers=source_nums,
                    )
                    return narrative
            except Exception as e:
                logger.warning("Model %s failed: %s", model, e)
                continue

        return fallback_narrative

    def synthesize_stream(
        self,
        question: str,
        intent: str,
        entity_info: Optional[dict] = None,
        metrics: Optional[dict] = None,
        graph_summary: Optional[dict] = None,
        evidence_snippets: Optional[list[str]] = None,
        extra_context: Optional[str] = None,
        format_hint: Optional[str] = None,
    ):
        """Stream synthesis tokens. Yields str chunks. Falls back to empty if LLM unavailable."""
        if not self.enabled:
            return

        ctx_mode = getattr(self.config.llm, "ctx_mode", "ctx")
        context = _build_context_block(
            question=question,
            intent=intent,
            entity_info=entity_info,
            metrics=metrics,
            graph_summary=graph_summary,
            evidence_snippets=evidence_snippets,
            extra_context=extra_context,
            ctx_mode=ctx_mode,
        )

        system_prompt = _get_system_prompt(intent, format_hint)

        try:
            client = self._get_client()
            stream = client.chat.completions.create(
                model=self.config.llm.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": context},
                ],
                max_tokens=self.config.llm.max_tokens,
                temperature=self.config.llm.temperature,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content
        except Exception as e:
            logger.warning("LLM stream failed: %s", e)

    def synthesize_dossier(
        self,
        question: str,
        entity_name: str,
        entity_type: str,
        entity_details: Optional[dict] = None,
        metrics: Optional[dict] = None,
        graph_summary: Optional[dict] = None,
        evidence_snippets: Optional[list[str]] = None,
        fallback_narrative: str = "",
        extra_context: Optional[str] = None,
    ) -> str:
        """Specialized dossier synthesis."""
        entity_info = {
            "name": entity_name,
            "type": entity_type,
            **(entity_details or {}),
        }
        return self.synthesize(
            question=f"Tell me about {entity_name}",
            intent="dossier",
            entity_info=entity_info,
            metrics=metrics,
            graph_summary=graph_summary,
            evidence_snippets=evidence_snippets,
            fallback_narrative=fallback_narrative,
            extra_context=extra_context,
        )

    def synthesize_comparison(
        self,
        entity_names: list[str],
        metrics_by_entity: Optional[dict] = None,
        shared_connections: Optional[list] = None,
        unique_connections: Optional[dict] = None,
        fallback_narrative: str = "",
        computed_insights: str = "",
    ) -> str:
        """Specialized comparison synthesis."""
        extra = ""
        if shared_connections:
            shared_labels = [c.get("label", c.get("entity_id", "?")) for c in shared_connections[:10]]
            extra += f"Shared connections ({len(shared_connections)}): {', '.join(shared_labels)}. "
        if unique_connections:
            for eid, conns in unique_connections.items():
                labels = [c.get("label", "?") for c in conns[:5]]
                extra += f"Unique to {eid}: {', '.join(labels)}. "
        if computed_insights:
            extra += f"\n{computed_insights}"

        return self.synthesize(
            question=f"Compare {' vs '.join(entity_names)}",
            intent="compare",
            metrics=metrics_by_entity,
            extra_context=extra if extra else None,
            fallback_narrative=fallback_narrative,
        )

    def synthesize_landscape(
        self,
        question: str,
        segments: Optional[list[dict]] = None,
        fallback_narrative: str = "",
    ) -> str:
        """Specialized competitive landscape synthesis."""
        return self.synthesize(
            question=question,
            intent="landscape",
            metrics={"segments": segments or []},
            fallback_narrative=fallback_narrative,
        )

    def synthesize_pipeline(
        self,
        question: str,
        pipelines: Optional[list[dict]] = None,
        therapeutic_area: str = "",
        fallback_narrative: str = "",
    ) -> str:
        """Specialized pipeline synthesis."""
        return self.synthesize(
            question=question,
            intent="pipeline",
            metrics={"pipelines": pipelines or []},
            extra_context=f"Therapeutic area focus: {therapeutic_area}" if therapeutic_area else None,
            fallback_narrative=fallback_narrative,
        )

    def synthesize_research_report(
        self,
        question: str,
        graph_summary: Optional[dict] = None,
        metrics: Optional[dict] = None,
        evidence_snippets: Optional[list[str]] = None,
        web_results: Optional[list[dict]] = None,
        fallback_report: str = "",
    ) -> str:
        """Generate a deep-research brief with optional web augmentation."""
        if not self.enabled:
            return fallback_report

        extra_context = None
        if web_results:
            extra_context = f"WEB RESULTS: {json.dumps(web_results[:8], default=str)}"

        context = _build_context_block(
            question=question,
            intent="deep_research",
            metrics=metrics,
            graph_summary=graph_summary,
            evidence_snippets=evidence_snippets,
            extra_context=extra_context,
        )

        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self.config.llm.model,
                messages=[
                    {"role": "system", "content": RESEARCH_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"{context}\n\n"
                            "Write sections titled:\n"
                            "1) Executive Summary\n"
                            "2) Internal Evidence (Knowledge Graph)\n"
                            "3) Quantitative Signals\n"
                            "4) External Context (Web)\n"
                            "5) Risks and Data Gaps\n"
                            "6) Recommended Next Questions\n"
                            "Only include section 4 if web results are provided."
                        ),
                    },
                ],
                max_tokens=min(self.config.llm.max_tokens * 2, 2200),
                temperature=min(max(self.config.llm.temperature, 0.2), 0.5),
            )
            narrative = response.choices[0].message.content.strip()
            if narrative:
                return narrative
            return fallback_report
        except Exception as e:
            logger.warning("LLM research synthesis failed, using fallback: %s", e)
            return fallback_report
