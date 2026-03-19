"""Chat / Orchestration endpoint for the intelligence console.

Receives a natural language question, routes to the best service combination,
and returns a structured response with narrative + data cards.

Architecture:
  1. Regex-based intent detection (fast, deterministic)
  2. Deterministic service calls (search, graph, metrics)
  3. LLM synthesis of gathered data into analyst-grade narrative
  4. Falls back to template narrative if LLM is unavailable
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import re
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from api.deps import (
    get_db,
    get_llm,
    get_metrics,
    get_query_engine,
    get_query_graph,
    get_team_eval_graph,
    get_web_research,
    get_workspace,
)
from api.utils import normalize_provenance
from config import config
from db import Database
from services.graph import GraphTraversal
from services.query_engine import QueryEngine
from services.search import HybridSearch
from services.metrics import PharmaMetrics
from services.llm import LLMSynthesizer
from services.web_research import WebResearchService
from services.workspace import ChatWorkspaceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


# ── Intent Detection ──

class Intent:
    DEEP_RESEARCH = "deep_research"
    DOSSIER = "dossier"
    COMPARE = "compare"
    LANDSCAPE = "landscape"
    PORTFOLIO = "portfolio"
    PIPELINE = "pipeline"
    STRUCTURED_QUERY = "structured_query"
    TEAM_EVAL = "team_eval"
    GENERAL = "general"


def _coerce_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _apply_chat_modes(payload: dict, include_graph: bool, include_metrics: bool, source_strict: bool) -> dict:
    """Enforce frontend mode flags on chat payloads."""
    data = payload.get("data")
    if not isinstance(data, dict):
        return payload

    if not include_graph:
        data["graph_context"] = {
            "nodes": [],
            "edges": [],
            "node_count": 0,
            "edge_count": 0,
        }

    if not include_metrics:
        data["metrics_context"] = {}

    if source_strict:
        evidence = data.get("evidence")
        if isinstance(evidence, list):
            source_backed = []
            for item in evidence:
                if not isinstance(item, dict):
                    continue
                provenance = item.get("provenance")
                if not isinstance(provenance, dict):
                    continue
                if provenance.get("source_api") or provenance.get("source_url"):
                    source_backed.append(item)
            data["evidence"] = source_backed

            provenance_summary = data.get("provenance_summary")
            if isinstance(provenance_summary, dict):
                by_source = provenance_summary.get("by_source")
                if isinstance(by_source, dict):
                    provenance_summary["by_source"] = {
                        source: count for source, count in by_source.items() if source != "unknown"
                    }
                provenance_summary["total_evidence_items"] = len(source_backed)

    return payload


def detect_format_hint(question: str) -> str | None:
    """Detect if the user explicitly asks for a specific output format."""
    q = question.lower()
    if re.search(r'\b(table|tabular|rows|columns|spreadsheet|csv|breakdown|list all|show all|data export)\b', q):
        return "table"
    if re.search(r'\b(chart|graph|plot|visualize|bar chart|pie chart|histogram)\b', q):
        return "chart"
    return None


def detect_intent(question: str) -> tuple[str, dict]:
    """Classify question into an intent with extracted params."""
    q = question.lower().strip()

    # ── Guard: detect article / study titles (contain colon or long phrases) ──
    # If the query looks like a paper title, treat as general lookup rather than
    # letting "versus" trigger a drug comparison.
    _looks_like_title = (
        (':' in q and len(q) > 60)
        or re.search(r'(?:study|trial|randomized|multicenter|real-world|meta-analysis|systematic review)\b', q)
    )

    # Compare: "compare X vs Y", "X versus Y", "X and Y comparison"
    # Skip if query looks like a literature title.
    vs_match = re.search(
        r'(?:compare\s+)?(.+?)\s+(?:vs\.?|versus|compared?\s+(?:to|with))\s+(.+?)(?:\s+in\s+|\?|$)',
        q
    )
    if not _looks_like_title and (vs_match or ('compare' in q and 'landscape' not in q)):
        if vs_match:
            return Intent.COMPARE, {"entities": [vs_match.group(1).strip(), vs_match.group(2).strip()]}
        return Intent.COMPARE, {"entities": []}

    # Landscape: "competitive landscape", "market landscape", "GLP-1 landscape"
    # Must come before dossier to avoid "what is the competitive landscape" -> dossier
    if any(w in q for w in ['landscape', 'competitive', 'market segments', 'market overview']):
        # Extract topic: "GLP-1 landscape" → "GLP-1", "competitive landscape for diabetes" → "diabetes"
        topic = ""
        topic_match = re.search(r'(?:landscape|competitive|market\s+(?:segments|overview))\s+(?:for|in|of)\s+(.+?)(?:\?|$)', q)
        if topic_match:
            topic = topic_match.group(1).strip()
        else:
            # Try prefix: "GLP-1 landscape", "obesity competitive landscape"
            prefix_match = re.search(r'^(.+?)\s+(?:landscape|competitive|market)', q)
            if prefix_match:
                topic = prefix_match.group(1).strip()
                # Strip filler words
                topic = re.sub(r'^(?:show\s+me\s+(?:the\s+)?|what\s+is\s+(?:the\s+)?|the\s+|tabular\s+(?:breakdown\s+(?:of\s+)?)?(?:the\s+)?)', '', topic).strip()
        return Intent.LANDSCAPE, {"topic": topic}

    # Portfolio: "company portfolio", "Novo Nordisk portfolio"
    if 'portfolio' in q:
        name_match = re.search(r'(\w[\w\s]+?)\s+portfolio', q)
        return Intent.PORTFOLIO, {"company_name": name_match.group(1).strip() if name_match else ""}

    # Pipeline: "pipeline", "drug pipeline", "obesity pipeline", "heart failure pipeline"
    if 'pipeline' in q:
        ta_match = re.search(r'(.+?)\s+pipeline', q)
        ta = ta_match.group(1).strip() if ta_match else ""
        # Strip leading filler words
        ta = re.sub(r'^(?:show\s+me\s+(?:the\s+)?|what\s+is\s+(?:the\s+)?|the\s+|drug\s+)', '', ta).strip()
        return Intent.PIPELINE, {"therapeutic_area": ta}

    # Structured query: signals that need SQL-computed answers
    try:
        from services.agent.graphs.query_graph import has_structured_signals
        if has_structured_signals(q):
            return Intent.STRUCTURED_QUERY, {}
    except ImportError:
        pass

    # Dossier: "tell me about X", "dossier on X", "what is X"
    dossier_match = re.search(
        r'(?:tell me about|dossier on|what is|who is|describe|profile of|about)\s+(.+?)(?:\?|$)',
        q
    )
    if dossier_match:
        return Intent.DOSSIER, {"entity_name": dossier_match.group(1).strip()}

    # Bare entity name fallback: if the query is short (1-4 words) and doesn't
    # look like a question, treat it as a dossier request. This catches queries
    # like "semaglutide", "Novo Nordisk", "tirzepatide obesity" etc.
    word_count = len(q.split())
    if 1 <= word_count <= 4 and not re.search(r'\b(how|why|when|where|which|what|who|is|are|do|does|can|show|list|get)\b', q):
        return Intent.DOSSIER, {"entity_name": q}

    return Intent.GENERAL, {}


def _resolve_entity(name: str, entity_type: str, db: Database) -> Optional[dict]:
    """Resolve a name or UUID to entity_id + metadata."""
    import re as _re

    table_map = {
        "drug": ("drugs", "generic_name"),
        "company": ("companies", "name"),
        "therapeutic_area": ("therapeutic_areas", "name"),
        "mechanism": ("mechanisms_of_action", "name"),
        "literature": ("pubmed_articles", "title"),
    }

    # Check if it's a UUID (or contains one)
    uuid_match = _re.search(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', name.lower())
    if uuid_match:
        uuid_val = uuid_match.group(0)
        for etype, (table, col) in table_map.items():
            if entity_type and entity_type != etype:
                continue
            row = db.fetch_one(
                f"SELECT id::text AS entity_id, {col} AS label FROM {table} WHERE id::text = %s LIMIT 1",
                [uuid_val],
            )
            if row:
                return {"entity_id": row["entity_id"], "label": row["label"], "entity_type": etype}

    # Strip leading entity type words: "drug semaglutide" -> "semaglutide"
    clean_name = _re.sub(r'^(drug|company|trial|mechanism|therapeutic_area)\s+', '', name.strip(), flags=_re.IGNORECASE)

    for etype, (table, col) in table_map.items():
        if entity_type and entity_type != etype:
            continue
        # Exact match first
        row = db.fetch_one(
            f"SELECT id::text AS entity_id, {col} AS label FROM {table} WHERE LOWER({col}) = LOWER(%s) LIMIT 1",
            [clean_name],
        )
        if row:
            return {"entity_id": row["entity_id"], "label": row["label"], "entity_type": etype}
        # Fuzzy match
        row = db.fetch_one(
            f"SELECT id::text AS entity_id, {col} AS label FROM {table} WHERE LOWER({col}) LIKE LOWER(%s) LIMIT 1",
            [f"%{clean_name}%"],
        )
        if row:
            return {"entity_id": row["entity_id"], "label": row["label"], "entity_type": etype}

    return None


def _generate_followups(question: str, intent: str, narrative: str, params: dict) -> list[str]:
    """Generate 2-3 rule-based follow-up question suggestions."""
    suggestions: list[str] = []
    entities = params.get("entities", [])
    entity = entities[0] if entities else ""
    drug = params.get("drug_name", "") or params.get("entity_name", "") or entity
    company = params.get("company_name", "")
    ta = params.get("therapeutic_area", "")

    if intent == Intent.COMPARE and len(entities) >= 2:
        suggestions.append(f"What Phase 3 trials does {entities[0]} have?")
        suggestions.append(f"Show the full pipeline for {entities[1]}")
        if ta:
            suggestions.append(f"Who leads in {ta}?")
    elif intent == Intent.LANDSCAPE:
        topic = params.get("topic", "")
        if topic:
            suggestions.append(f"Which companies dominate the {topic} space?")
            suggestions.append(f"What drugs are in Phase 3 for {topic}?")
        else:
            suggestions.append("Compare the top 2 mechanisms head-to-head")
            suggestions.append("Which companies dominate this space?")
        if ta:
            suggestions.append(f"What drugs are in Phase 3 for {ta}?")
    elif intent == Intent.PIPELINE:
        if drug:
            suggestions.append(f"What is the success rate for {drug}?")
            suggestions.append(f"Compare {drug} vs its closest competitor")
        if ta:
            suggestions.append(f"Show the competitive landscape for {ta}")
    elif intent == Intent.PORTFOLIO and company:
        suggestions.append(f"What Phase 3 trials does {company} have?")
        suggestions.append(f"Compare {company} vs its largest competitor")
    elif intent == Intent.DOSSIER and drug:
        suggestions.append(f"What trials are running for {drug}?")
        suggestions.append(f"Show the competitive landscape for {drug}")
    else:
        # General intent — try to extract an entity from the question for follow-ups
        if drug:
            suggestions.append(f"Deep dive into {drug}")
            suggestions.append(f"What is the pipeline for {drug}?")
        elif ta:
            suggestions.append(f"Show the competitive landscape for {ta}")
            suggestions.append(f"What drugs are in late-stage trials for {ta}?")

    return suggestions[:3]


@router.post("/ctx-benchmark")
def ctx_benchmark(body: dict):
    """Run A/B benchmark comparing CTX vs legacy context pipelines.

    Send any chat-like payload with question + optional data,
    returns both pipelines' context text and metrics without calling the LLM.
    """
    from services.ctx_context import CTXContextBuilder

    question = body.get("question", "test query")
    intent = body.get("intent", "general")
    entity_info = body.get("entity_info")
    metrics = body.get("metrics")
    graph_summary = body.get("graph_summary")
    evidence = body.get("evidence_snippets", [])

    builder = CTXContextBuilder(mode="both")
    ab = builder.build(
        question=question,
        intent=intent,
        entity_info=entity_info,
        metrics=metrics,
        graph_summary=graph_summary,
        evidence_snippets=evidence,
    )

    return {
        "summary": ab.summary,
        "ctx": {
            "text": ab.active.text,
            "tokens": ab.active.tokens,
            "source_tokens": ab.active.source_tokens,
            "compression_ratio": ab.active.compression_ratio,
            "build_time_ms": round(ab.active.build_time_ms, 2),
            "sections": ab.active.sections,
        },
        "legacy": {
            "text": ab.comparison.text if ab.comparison else None,
            "tokens": ab.comparison.tokens if ab.comparison else None,
            "build_time_ms": round(ab.comparison.build_time_ms, 2) if ab.comparison else None,
        },
    }


@router.post("")
def chat(
    body: dict,
    db: Database = Depends(get_db),
    engine: QueryEngine = Depends(get_query_engine),
    metrics_svc: PharmaMetrics = Depends(get_metrics),
    llm: LLMSynthesizer = Depends(get_llm),
    web_research: WebResearchService = Depends(get_web_research),
):
    """Orchestration endpoint: detect intent, route to services, return structured response."""
    question = body.get("question", "").strip()
    if not question:
        return {"error": "No question provided"}

    include_graph = _coerce_bool(body.get("include_graph"), True)
    include_metrics = _coerce_bool(body.get("include_metrics"), True)
    source_strict = _coerce_bool(body.get("source_strict"), True)
    deep_research = _coerce_bool(body.get("deep_research"), False)
    include_web = _coerce_bool(body.get("include_web"), False)
    team_eval = _coerce_bool(body.get("team_eval"), False)
    conversation_history = body.get("conversation_history", [])
    if not isinstance(conversation_history, list):
        conversation_history = []

    # Build conversation context for all intents
    conv_context = _build_conversation_context(conversation_history)

    # Resolve follow-up references ("this space", "that drug", etc.)
    resolved_question = _resolve_followup_question(question, conversation_history)
    if resolved_question != question:
        logger.info("Follow-up resolved: %r → %r", question, resolved_question)

    intent, params = detect_intent(resolved_question)
    if deep_research:
        intent, params = Intent.DEEP_RESEARCH, {}
    if team_eval:
        intent, params = Intent.TEAM_EVAL, {}
    logger.info("Chat intent: %s, params: %s", intent, params)

    try:
        if intent == Intent.TEAM_EVAL:
            payload = _handle_team_eval(resolved_question, engine, db, llm)

        elif intent == Intent.STRUCTURED_QUERY:
            payload = _handle_structured_query(resolved_question, engine, db, llm, conversation_history)

        elif intent == Intent.DEEP_RESEARCH:
            payload = _handle_deep_research(
                question=resolved_question,
                db=db,
                engine=engine,
                llm=llm,
                web_research=web_research,
                include_graph=include_graph,
                include_metrics=include_metrics,
                include_web=include_web,
            )

        elif intent == Intent.DOSSIER:
            payload = _handle_dossier(params, db, engine, llm, conv_context=conv_context)

        elif intent == Intent.COMPARE:
            payload = _handle_compare(params, db, engine, llm, conv_context=conv_context)

        elif intent == Intent.LANDSCAPE:
            payload = _handle_landscape(resolved_question, params, metrics_svc, llm, conv_context=conv_context)

        elif intent == Intent.PORTFOLIO:
            payload = _handle_portfolio(params, db, engine, metrics_svc, llm, conv_context=conv_context)

        elif intent == Intent.PIPELINE:
            payload = _handle_pipeline(params, metrics_svc, llm, conv_context=conv_context)

        else:
            payload = _handle_general(
                resolved_question,
                engine,
                db,
                llm,
                include_graph=include_graph,
                include_metrics=include_metrics,
                conv_context=conv_context,
            )

        payload = _apply_chat_modes(payload, include_graph, include_metrics, source_strict)
        payload["visualizations"] = _build_visualizations(payload.get("data"))
        payload["followup_suggestions"] = _generate_followups(
            question, intent, payload.get("narrative", ""), params,
        )
        return payload

    except Exception as e:
        logger.exception("Chat error for question: %s", question)
        return {
            "narrative": f"I encountered an error processing your question: {str(e)}",
            "intent": intent,
            "data": None,
        }


@router.post("/stream")
def chat_stream(
    body: dict,
    db: Database = Depends(get_db),
    engine: QueryEngine = Depends(get_query_engine),
    metrics_svc: PharmaMetrics = Depends(get_metrics),
    llm: LLMSynthesizer = Depends(get_llm),
):
    """Streaming chat endpoint. Returns SSE events:
    - event: status — progress messages during tool execution
    - event: token — individual synthesis tokens
    - event: done — final structured payload (data, visualizations, etc.)
    """
    question = body.get("question", "").strip()
    if not question:
        return {"error": "No question provided"}

    include_graph = _coerce_bool(body.get("include_graph"), True)
    include_metrics = _coerce_bool(body.get("include_metrics"), True)
    source_strict = _coerce_bool(body.get("source_strict"), True)
    conversation_history = body.get("conversation_history", [])
    if not isinstance(conversation_history, list):
        conversation_history = []

    intent, params = detect_intent(question)

    def generate():
        import json as _json

        try:
            yield f"event: status\ndata: {_json.dumps({'message': 'Detecting intent...'})}\n\n"

            # Execute the data-gathering phase (non-streaming)
            yield f"event: status\ndata: {_json.dumps({'message': f'Processing {intent} query...'})}\n\n"

            if intent == Intent.COMPARE:
                payload = _handle_compare(params, db, engine, llm)
            elif intent == Intent.LANDSCAPE:
                payload = _handle_landscape(question, params, metrics_svc, llm)
            elif intent == Intent.PORTFOLIO:
                payload = _handle_portfolio(params, db, engine, metrics_svc, llm)
            elif intent == Intent.PIPELINE:
                payload = _handle_pipeline(params, metrics_svc, llm)
            elif intent == Intent.STRUCTURED_QUERY:
                payload = _handle_structured_query(question, engine, db, llm, conversation_history)
            else:
                payload = _handle_general(question, engine, db, llm, include_graph=include_graph, include_metrics=include_metrics)

            payload = _apply_chat_modes(payload, include_graph, include_metrics, source_strict)
            payload["visualizations"] = _build_visualizations(payload.get("data"))
            payload["followup_suggestions"] = _generate_followups(question, intent, payload.get("narrative", ""), params)

            # Stream the narrative token-by-token if LLM is available
            narrative = payload.get("narrative", "")
            if narrative:
                yield f"event: status\ndata: {_json.dumps({'message': 'Synthesizing narrative...'})}\n\n"
                for i in range(0, len(narrative), 4):
                    chunk = narrative[i:i+4]
                    yield f"event: token\ndata: {_json.dumps({'text': chunk})}\n\n"

            # Send the full structured payload as the final event
            # Remove narrative from done event since it was already streamed
            done_payload = {k: v for k, v in payload.items() if k != "narrative"}
            done_payload["narrative"] = narrative  # include for completeness
            yield f"event: done\ndata: {_json.dumps(done_payload, default=str)}\n\n"

        except Exception as exc:
            logger.exception("Stream error: %s", exc)
            yield f"event: error\ndata: {_json.dumps({'message': str(exc)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions")
def list_chat_sessions(
    scope_key: str = Query("default"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    workspace: ChatWorkspaceService = Depends(get_workspace),
):
    scope = _normalize_scope(scope_key)
    sessions = workspace.list_sessions(scope_key=scope, limit=limit, offset=offset)
    return {
        "sessions": sessions,
        "count": len(sessions),
        "limit": limit,
        "offset": offset,
    }


@router.post("/sessions")
def save_chat_session(
    body: dict,
    workspace: ChatWorkspaceService = Depends(get_workspace),
):
    scope = _normalize_scope(body.get("scope_key"))
    title = str(body.get("title") or "").strip() or "Saved conversation"
    session_id = str(body.get("session_id") or "").strip() or None
    transcript = body.get("transcript")
    if not isinstance(transcript, list):
        raise HTTPException(status_code=400, detail="transcript must be a list")
    summary = str(body.get("summary") or "").strip() or None

    saved = workspace.save_session(
        scope_key=scope,
        title=title,
        transcript=_sanitize_transcript(transcript),
        session_id=session_id,
        summary=summary,
    )
    return {"session": saved}


@router.get("/sessions/{session_id}")
def get_chat_session(
    session_id: str,
    scope_key: str = Query("default"),
    workspace: ChatWorkspaceService = Depends(get_workspace),
):
    scope = _normalize_scope(scope_key)
    payload = workspace.get_session(session_id=session_id, scope_key=scope)
    if not payload:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": payload}


@router.delete("/sessions/{session_id}")
def delete_chat_session(
    session_id: str,
    scope_key: str = Query("default"),
    workspace: ChatWorkspaceService = Depends(get_workspace),
):
    scope = _normalize_scope(scope_key)
    deleted = workspace.delete_session(session_id=session_id, scope_key=scope)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True, "session_id": session_id}


@router.post("/export/report")
def export_report(body: dict):
    report = str(body.get("report") or "").strip()
    if not report:
        raise HTTPException(status_code=400, detail="report is required")

    title = str(body.get("title") or "deep-research-report").strip()
    export_format = str(body.get("format") or "md").strip().lower()
    safe_name = _safe_filename(title or "deep-research-report")

    if export_format == "json":
        filename = f"{safe_name}.json"
        content = report
        media_type = "application/json"
    elif export_format == "txt":
        filename = f"{safe_name}.txt"
        content = report
        media_type = "text/plain; charset=utf-8"
    else:
        filename = f"{safe_name}.md"
        content = f"# {title}\n\n{report}\n"
        media_type = "text/markdown; charset=utf-8"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/research-jobs")
def create_research_job(
    body: dict,
    background_tasks: BackgroundTasks,
    workspace: ChatWorkspaceService = Depends(get_workspace),
):
    question = str(body.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    scope = _normalize_scope(body.get("scope_key"))
    options = {
        "include_graph": _coerce_bool(body.get("include_graph"), True),
        "include_metrics": _coerce_bool(body.get("include_metrics"), True),
        "source_strict": _coerce_bool(body.get("source_strict"), True),
        "include_web": _coerce_bool(body.get("include_web"), False),
    }

    job = workspace.create_research_job(
        scope_key=scope,
        question=question,
        options=options,
    )
    background_tasks.add_task(_run_research_job_task, job["id"], scope)
    return {"job": job}


@router.get("/research-jobs")
def list_research_jobs(
    scope_key: str = Query("default"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    workspace: ChatWorkspaceService = Depends(get_workspace),
):
    scope = _normalize_scope(scope_key)
    jobs = workspace.list_research_jobs(scope_key=scope, limit=limit, offset=offset)
    return {
        "jobs": jobs,
        "count": len(jobs),
        "limit": limit,
        "offset": offset,
    }


@router.get("/research-jobs/{job_id}")
def get_research_job(
    job_id: str,
    scope_key: str = Query("default"),
    workspace: ChatWorkspaceService = Depends(get_workspace),
):
    scope = _normalize_scope(scope_key)
    job = workspace.get_research_job(job_id=job_id, scope_key=scope)
    if not job:
        raise HTTPException(status_code=404, detail="Research job not found")
    return {"job": job}


def _build_conversation_context(history: list[dict]) -> str:
    """Build a compact text summary of the last 3 exchange pairs for follow-up resolution.

    Includes entities discussed, metrics shown, and SQL context from prior turns
    so the LLM can provide richer, more contextual follow-up answers.
    """
    if not history:
        return ""
    # Take last 6 messages (3 exchange pairs)
    recent = history[-6:]
    parts: list[str] = []
    all_entities: list[str] = []
    all_metrics: list[str] = []

    for msg in recent:
        role = msg.get("role", "unknown")
        content = str(msg.get("content", ""))[:500]
        sql_ctx = msg.get("sql_context", "")
        line = f"[{role}] {content}"
        if sql_ctx:
            line += f"\n  Prior SQL: {str(sql_ctx)[:300]}"
        parts.append(line)

        # Collect entity and metric context from assistant messages
        entities = msg.get("entities", [])
        if isinstance(entities, list):
            all_entities.extend(str(e) for e in entities[:5])
        metrics_types = msg.get("metrics_types", [])
        if isinstance(metrics_types, list):
            all_metrics.extend(str(m) for m in metrics_types[:5])

    # Append semantic summary
    if all_entities:
        unique_entities = list(dict.fromkeys(all_entities))[:8]
        parts.append(f"[context] Entities discussed: {', '.join(unique_entities)}")
    if all_metrics:
        unique_metrics = list(dict.fromkeys(all_metrics))[:6]
        parts.append(f"[context] Metrics shown: {', '.join(unique_metrics)}")

    return "\n".join(parts)


def _resolve_followup_question(question: str, history: list[dict]) -> str:
    """Expand ambiguous follow-up references using prior conversation context.

    Detects patterns like "this space", "that drug", "those companies", "its pipeline"
    and replaces them with the actual entity/topic from the most recent assistant message.
    """
    if not history:
        return question

    q = question.lower().strip()
    # Only attempt resolution for short follow-up questions with pronouns/demonstratives
    has_ref = re.search(
        r'\b(this|that|these|those|its|their|the same|above|it)\b', q
    )
    if not has_ref:
        return question

    # Extract the most recent topic from assistant messages
    prior_topic = ""
    prior_intent = ""
    for msg in reversed(history):
        if msg.get("role") != "assistant":
            continue
        content = str(msg.get("content", ""))
        # Try to extract the primary entity/topic from bold markers
        bold_matches = re.findall(r'\*\*([^*]+)\*\*', content)
        if bold_matches:
            prior_topic = bold_matches[0]
            break
        # Fall back to first sentence entity
        if content:
            prior_topic = content[:60].split(".")[0]
            break

    # Extract prior intent from the most recent user question
    for msg in reversed(history):
        if msg.get("role") == "user":
            prev_q = str(msg.get("content", "")).lower()
            _, prev_params = detect_intent(prev_q)
            prior_intent = prev_params.get("topic", "") or prev_params.get("entity_name", "") or prev_params.get("therapeutic_area", "")
            if not prior_intent and prior_topic:
                prior_intent = prior_topic
            break

    if not prior_intent and not prior_topic:
        return question

    topic = prior_intent or prior_topic

    # Replace references with the resolved topic
    resolved = question
    resolved = re.sub(r'\b(this|that)\s+(space|area|market|landscape|field|domain|segment)\b',
                      topic, resolved, flags=re.IGNORECASE)
    resolved = re.sub(r'\b(these|those)\s+(drugs?|compounds?|entities|companies|mechanisms?)\b',
                      f'{topic} \\2', resolved, flags=re.IGNORECASE)
    resolved = re.sub(r'\b(its?|their)\s+(pipeline|portfolio|trials?|landscape)\b',
                      f'{topic} \\2', resolved, flags=re.IGNORECASE)

    return resolved


def _handle_structured_query(
    question: str,
    engine: QueryEngine,
    db: Database,
    llm: LLMSynthesizer,
    conversation_history: list[dict] | None = None,
) -> dict:
    """Route to the LangGraph query agent for SQL-computed answers."""
    graph = get_query_graph()
    if graph is None:
        logger.info("Query graph not available, falling back to general handler")
        return _handle_general(question, engine, db, llm)

    conversation_context = _build_conversation_context(conversation_history or [])

    try:
        result = graph.invoke({
            "messages": [],
            "question": question,
            "conversation_context": conversation_context,
            "intent": "",
            "plan": {},
            "tool_results": {},
            "presentation": {},
            "table_data": None,
            "visualizations": [],
            "narrative": "",
            "error": None,
        })
        return _format_agent_response(result, Intent.STRUCTURED_QUERY)
    except Exception as exc:
        logger.warning("Query graph failed: %s, falling back", exc)
        return _handle_general(question, engine, db, llm)


def _handle_team_eval(
    question: str,
    engine: QueryEngine,
    db: Database,
    llm: LLMSynthesizer,
) -> dict:
    """Route to the LangGraph team eval agent for multi-persona analysis."""
    graph = get_team_eval_graph()
    if graph is None:
        logger.info("Team eval graph not available, falling back to general handler")
        return _handle_general(question, engine, db, llm)

    try:
        result = graph.invoke({
            "messages": [],
            "question": question,
            "extracted_entities": {},
            "active_personas": [],
            "persona_analyses": [],
            "tool_results": {},
            "combined_narrative": "",
            "confidence_assessment": {},
            "presentation": {},
            "table_data": None,
            "visualizations": [],
        })
        return _format_team_eval_response(result)
    except Exception as exc:
        logger.warning("Team eval graph failed: %s, falling back", exc)
        return _handle_general(question, engine, db, llm)


def _tool_result_value(result_obj, field: str, default=None):
    if result_obj is None:
        return default
    if isinstance(result_obj, dict):
        return result_obj.get(field, default)
    return getattr(result_obj, field, default)


def _extract_rag_evidence(tool_results: dict) -> tuple[list[dict], dict]:
    rag_result = tool_results.get("rag") if isinstance(tool_results, dict) else None
    rag_success = bool(_tool_result_value(rag_result, "success", False))
    rag_data = _tool_result_value(rag_result, "data", [])
    if not rag_success or not isinstance(rag_data, list):
        return [], {"total_evidence_items": 0, "by_source": {}}

    evidence: list[dict] = []
    by_source: dict[str, int] = {}
    by_entity_type: dict[str, int] = {}
    for item in rag_data:
        if not isinstance(item, dict):
            continue

        entity_type = str(item.get("entity_type") or "unknown")
        entity_id = str(item.get("entity_id") or "")
        content = str(item.get("content") or item.get("snippet") or item.get("title") or "").strip()
        if not content:
            continue

        raw_provenance = item.get("provenance")
        provenance = dict(raw_provenance) if isinstance(raw_provenance, dict) else {}
        if not provenance.get("source_api") and item.get("source"):
            provenance["source_api"] = str(item.get("source"))
        normalized_provenance = normalize_provenance(provenance, entity_type, entity_id)
        source_api = str(normalized_provenance.get("source_api") or item.get("source") or "unknown")

        relevance_raw = item.get("relevance")
        try:
            relevance = float(relevance_raw) if relevance_raw is not None else 0.0
        except (TypeError, ValueError):
            relevance = 0.0

        evidence.append(
            {
                "source": source_api,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "content": content,
                "relevance": relevance,
                "provenance": normalized_provenance,
            }
        )
        by_source[source_api] = by_source.get(source_api, 0) + 1
        by_entity_type[entity_type] = by_entity_type.get(entity_type, 0) + 1

    return evidence, {
        "total_evidence_items": len(evidence),
        "by_source": by_source,
        "by_entity_type": by_entity_type,
    }


def _extract_graph_context(tool_results: dict) -> dict:
    graph_result = tool_results.get("graph") if isinstance(tool_results, dict) else None
    graph_success = bool(_tool_result_value(graph_result, "success", False))
    graph_data = _tool_result_value(graph_result, "data", {})
    if not graph_success or not isinstance(graph_data, dict):
        return {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0}
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])
    return {
        "nodes": nodes if isinstance(nodes, list) else [],
        "edges": edges if isinstance(edges, list) else [],
        "node_count": len(nodes) if isinstance(nodes, list) else 0,
        "edge_count": len(edges) if isinstance(edges, list) else 0,
    }


def _format_agent_response(result: dict, intent: str) -> dict:
    """Format a query graph result into the standard chat response shape."""
    narrative = result.get("narrative", "")
    table_data = result.get("table_data")
    visualizations = result.get("visualizations", [])

    # Build a minimal data dict compatible with QueryResponse
    tool_results = result.get("tool_results", {})
    evidence, provenance_summary = _extract_rag_evidence(tool_results)
    graph_context = _extract_graph_context(tool_results)

    # Extract executed SQL for conversation context pass-through
    sql_meta = {}
    sql_result = tool_results.get("sql")
    if sql_result and hasattr(sql_result, "metadata") and isinstance(sql_result.metadata, dict):
        sql_meta["sql"] = sql_result.metadata.get("sql", "")
    elif isinstance(result.get("plan"), dict):
        sql_meta["sql"] = result["plan"].get("sql", "")

    return {
        "narrative": narrative,
        "intent": intent,
        "data": {
            "question": result.get("question", ""),
            "evidence": evidence,
            "graph_context": graph_context,
            "metrics_context": {},
            "entity_focus": [],
            "provenance_summary": provenance_summary,
        },
        "table_data": table_data,
        "visualizations": visualizations,
        "sql_meta": sql_meta,
    }


def _format_team_eval_response(result: dict) -> dict:
    """Format a team eval graph result into the standard chat response shape."""
    narrative = result.get("combined_narrative", "")
    persona_analyses = result.get("persona_analyses", [])
    confidence = result.get("confidence_assessment", {})
    table_data = result.get("table_data")
    visualizations = result.get("visualizations", [])
    tool_results = result.get("tool_results", {})
    evidence, provenance_summary = _extract_rag_evidence(tool_results)

    return {
        "narrative": narrative,
        "intent": Intent.TEAM_EVAL,
        "data": {
            "question": result.get("question", ""),
            "evidence": evidence,
            "graph_context": {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0},
            "metrics_context": {},
            "entity_focus": [],
            "provenance_summary": provenance_summary,
        },
        "table_data": table_data,
        "visualizations": visualizations,
        "persona_analyses": persona_analyses,
        "confidence_assessment": confidence,
    }


def _handle_dossier(params: dict, db: Database, engine: QueryEngine, llm: LLMSynthesizer, conv_context: str = "") -> dict:
    name = params.get("entity_name", "")
    resolved = _resolve_entity(name, "", db)

    if not resolved:
        # Try literature-specific search for article titles
        lit = _resolve_entity(name, "literature", db)
        if lit:
            resolved = lit
        else:
            result = engine.query(name)
            return _format_query_result("general", name, result, db, llm)

    etype = resolved["entity_type"]
    eid = resolved["entity_id"]
    label = resolved["label"]

    result = engine.entity_dossier(eid, etype)

    # ── Gather structured context for LLM ──
    entity_details = {}
    template_parts = []

    if etype == "drug":
        drug_row = db.fetch_one("""
            SELECT d.generic_name, d.brand_name, d.supply_status,
                   c.name AS company_name,
                   ta.name AS therapeutic_area,
                   m.name AS mechanism
            FROM drugs d
            LEFT JOIN companies c ON d.company_id = c.id
            LEFT JOIN therapeutic_areas ta ON d.therapeutic_area_id = ta.id
            LEFT JOIN mechanisms_of_action m ON d.mechanism_id = m.id
            WHERE d.id = %s::uuid
        """, [eid])

        if drug_row:
            entity_details = {
                "generic_name": drug_row["generic_name"],
                "brand_name": drug_row.get("brand_name"),
                "company": drug_row.get("company_name"),
                "mechanism": drug_row.get("mechanism"),
                "therapeutic_area": drug_row.get("therapeutic_area"),
                "supply_status": drug_row.get("supply_status"),
            }
            # Template fallback
            header = f"**{drug_row['generic_name']}"
            if drug_row.get("brand_name"):
                header += f" ({drug_row['brand_name']})"
            header += "**"
            parts = []
            if drug_row.get("company_name"):
                parts.append(f"owned by **{drug_row['company_name']}**")
            if drug_row.get("mechanism"):
                parts.append(f"a **{drug_row['mechanism']}**")
            if drug_row.get("therapeutic_area"):
                parts.append(f"targeting **{drug_row['therapeutic_area']}**")
            template_parts.append(f"{header} -- {', '.join(parts)}." if parts else f"{header}.")
            if drug_row.get("supply_status") and drug_row["supply_status"] != "NORMAL":
                template_parts.append(f"Supply status: **{drug_row['supply_status']}**.")
        else:
            template_parts.append(f"**{label}**.")

        # Connection summary
        conn_row = db.fetch_one("""
            SELECT COUNT(*) FILTER (WHERE link_type = 'INVESTIGATES') AS trial_links,
                   COUNT(*) FILTER (WHERE link_type = 'EVIDENCE_FOR') AS evidence_links,
                   COUNT(*) FILTER (WHERE link_type = 'IN_THERAPEUTIC_AREA') AS ta_links,
                   COUNT(*) FILTER (WHERE link_type = 'TARGETS_MECHANISM') AS mech_links,
                   COUNT(*) FILTER (WHERE link_type = 'OWNS') AS owns_links,
                   COUNT(*) AS total
            FROM entity_links
            WHERE source_entity_id::text = %s OR target_entity_id::text = %s
        """, [eid, eid])
        if conn_row and conn_row["total"] > 0:
            entity_details["connections"] = {
                "trials": conn_row["trial_links"],
                "publications": conn_row["evidence_links"],
                "therapeutic_areas": conn_row["ta_links"],
                "mechanisms": conn_row["mech_links"],
                "total": conn_row["total"],
            }
            conn_parts = []
            if conn_row["trial_links"]:
                conn_parts.append(f"{conn_row['trial_links']} trials")
            if conn_row["evidence_links"]:
                conn_parts.append(f"{conn_row['evidence_links']} publications")
            if conn_row["ta_links"]:
                conn_parts.append(f"{conn_row['ta_links']} therapeutic areas")
            if conn_parts:
                template_parts.append(
                    f"Connected to {', '.join(conn_parts)} in the knowledge graph "
                    f"(**{conn_row['total']} total connections**)."
                )

    elif etype == "company":
        template_parts.append(f"**{label}** company profile.")

    elif etype == "literature":
        art_row = db.fetch_one("""
            SELECT pa.title, pa.abstract, pa.journal, pa.publication_date,
                   pa.authors, d.generic_name AS drug_name,
                   ta.name AS therapeutic_area
            FROM pubmed_articles pa
            LEFT JOIN drugs d ON pa.drug_id = d.id
            LEFT JOIN therapeutic_areas ta ON d.therapeutic_area_id = ta.id
            WHERE pa.id = %s::uuid
        """, [eid])
        if art_row:
            entity_details = {
                "title": art_row["title"],
                "journal": art_row.get("journal"),
                "publication_date": str(art_row.get("publication_date", "")),
                "drug": art_row.get("drug_name"),
                "therapeutic_area": art_row.get("therapeutic_area"),
            }
            template_parts.append(f"**{art_row['title']}**")
            if art_row.get("journal"):
                template_parts.append(f"Published in *{art_row['journal']}*.")
            if art_row.get("abstract"):
                template_parts.append(art_row["abstract"][:500])
        else:
            template_parts.append(f"**{label}**.")

    else:
        template_parts.append(f"**{label}**.")

    # ── Metrics for LLM context + template ──
    metrics_for_llm = {}
    if result.metrics_context:
        for m_eid, metrics in result.metrics_context.items():
            if not isinstance(metrics, dict):
                continue
            metrics_for_llm = metrics
            p = metrics.get("pipeline", {})
            sr = metrics.get("success_rate", {})
            ev = metrics.get("evidence", {})

            if isinstance(p, dict) and p.get("pipeline_score") is not None:
                score = p["pipeline_score"]
                dominant_phase = max(
                    [("Phase 1", p.get("p1_count", 0)), ("Phase 2", p.get("p2_count", 0)),
                     ("Phase 3", p.get("p3_count", 0)), ("Phase 4", p.get("p4_count", 0))],
                    key=lambda x: x[1]
                )
                template_parts.append(
                    f"Pipeline score of **{score}** across {p.get('total_trials', 0)} trials, "
                    f"strongest in **{dominant_phase[0]}** ({dominant_phase[1]} trials)."
                )
            if isinstance(sr, dict) and sr.get("total", 0) > 0:
                completed = sr.get("completed", 0)
                terminated = sr.get("terminated", 0)
                active = sr.get("active", 0)
                parts = []
                if completed:
                    parts.append(f"{completed} completed")
                if active:
                    parts.append(f"{active} active")
                if terminated:
                    parts.append(f"{terminated} terminated")
                template_parts.append(f"Trial status: {', '.join(parts)}.")
            if isinstance(ev, dict) and ev.get("total_articles", 0) > 0:
                template_parts.append(
                    f"Evidence base of **{ev['total_articles']} PubMed articles**."
                )
            break

    # ── Market events for this entity ──
    if etype == "drug":
        events = db.fetch_all("""
            SELECT event_type, event_date, description, impact_score
            FROM market_events
            WHERE drug_id = %s::uuid
            ORDER BY event_date DESC NULLS LAST
            LIMIT 5
        """, [eid])
        if events:
            entity_details["recent_events"] = [
                {
                    "type": e["event_type"],
                    "date": str(e["event_date"]) if e["event_date"] else None,
                    "description": e["description"],
                    "impact": e["impact_score"],
                }
                for e in events
            ]
            for e in events:
                desc = e.get("description", "")
                date_str = str(e["event_date"]) if e.get("event_date") else ""
                template_parts.append(
                    f"**{e.get('event_type', 'Event')}** ({date_str}): {desc[:200]}"
                )

    # ── Evidence snippets for LLM ──
    evidence_snippets = [e.content for e in result.evidence[:10]]

    # ── Graph summary for LLM (include node labels, not just counts) ──
    graph_summary = None
    gc = result.graph_context
    if gc:
        # Extract top node labels grouped by entity type for richer LLM context
        nodes_by_type: dict[str, list[str]] = {}
        for node in gc.get("nodes", [])[:30]:
            if isinstance(node, dict) and node.get("label"):
                nt = node.get("entity_type", "other")
                nodes_by_type.setdefault(nt, []).append(node["label"])
        graph_summary = {
            "node_count": gc.get("node_count", 0),
            "edge_count": gc.get("edge_count", 0),
            "connections_by_type": gc.get("connections_by_type", {}),
            "connections_by_entity_type": gc.get("connections_by_entity_type", {}),
            "connected_entities": {k: v[:10] for k, v in nodes_by_type.items()},
        }

    # ── LLM synthesis (with template fallback) ──
    fallback = " ".join(template_parts)
    narrative = llm.synthesize_dossier(
        question=f"Tell me about {label}",
        entity_name=label,
        entity_type=etype,
        entity_details=entity_details,
        metrics=metrics_for_llm,
        graph_summary=graph_summary,
        evidence_snippets=evidence_snippets,
        fallback_narrative=fallback,
        extra_context=conv_context if conv_context else None,
    )

    return {
        "narrative": narrative,
        "intent": "dossier",
        "data": _enrich_result(result, db),
    }


def _compute_comparison_insights(resolved: list[dict], metrics_comp: dict) -> str:
    """Pre-compute differentials between two entities for LLM context."""
    if len(resolved) < 2:
        return ""

    insights: list[str] = []
    a, b = resolved[0], resolved[1]
    ma = metrics_comp.get(a["entity_id"], {})
    mb = metrics_comp.get(b["entity_id"], {})

    pa = ma.get("pipeline", {}) if isinstance(ma, dict) else {}
    pb = mb.get("pipeline", {}) if isinstance(mb, dict) else {}

    # Pipeline score ratio
    score_a = pa.get("pipeline_score", 0) or 0
    score_b = pb.get("pipeline_score", 0) or 0
    if score_a and score_b:
        if score_a >= score_b:
            ratio = score_a / score_b if score_b else float("inf")
            insights.append(f"{a['label']} has a {ratio:.1f}x stronger pipeline score than {b['label']} ({score_a} vs {score_b})")
        else:
            ratio = score_b / score_a if score_a else float("inf")
            insights.append(f"{b['label']} has a {ratio:.1f}x stronger pipeline score than {a['label']} ({score_b} vs {score_a})")

    # Trial volume difference
    trials_a = pa.get("total_trials", 0) or 0
    trials_b = pb.get("total_trials", 0) or 0
    diff = abs(trials_a - trials_b)
    if diff > 0:
        leader = a["label"] if trials_a > trials_b else b["label"]
        insights.append(f"{leader} has {diff} more trials ({max(trials_a, trials_b)} vs {min(trials_a, trials_b)})")

    # Late-stage (Phase 3) leadership
    p3_a = pa.get("p3_count", 0) or 0
    p3_b = pb.get("p3_count", 0) or 0
    if p3_a != p3_b:
        leader = a["label"] if p3_a > p3_b else b["label"]
        insights.append(f"{leader} leads in Phase 3 with {max(p3_a, p3_b)} trials vs {min(p3_a, p3_b)}")

    if not insights:
        return ""
    return "COMPUTED DIFFERENTIALS:\n" + "\n".join(f"- {i}" for i in insights)


def _handle_compare(params: dict, db: Database, engine: QueryEngine, llm: LLMSynthesizer, conv_context: str = "") -> dict:
    entity_names = params.get("entities", [])
    if len(entity_names) < 2:
        return {
            "narrative": "I need at least two entities to compare. Try: 'Compare semaglutide vs tirzepatide'.",
            "intent": "compare",
            "data": None,
        }

    resolved = []
    for name in entity_names:
        # Try drug first, then any entity type
        r = _resolve_entity(name, "drug", db)
        if not r:
            r = _resolve_entity(name, "", db)
        if r:
            resolved.append(r)

    if len(resolved) < 2:
        # Fall back to general query instead of returning an error
        original_q = " vs ".join(entity_names)
        logger.info("Compare fallback to general query: %s", original_q)
        result = engine.query(original_q)
        return _format_query_result("general", original_q, result, db, llm)

    result = engine.compare_entities([r["entity_id"] for r in resolved], resolved[0]["entity_type"])
    names = [r["label"] for r in resolved]

    # Template fallback
    template_parts = [f"Comparison of **{' vs '.join(names)}**."]
    if result.get("shared_connections"):
        template_parts.append(f"They share **{len(result['shared_connections'])} connections**.")

    metrics_comp = result.get("metrics_comparison", {})
    for r_ent in resolved:
        m = metrics_comp.get(r_ent["entity_id"], {})
        if isinstance(m, dict):
            p = m.get("pipeline", {})
            sr = m.get("success_rate", {})
            if isinstance(p, dict) and p.get("pipeline_score") is not None:
                template_parts.append(
                    f"**{r_ent['label']}**: pipeline score {p['pipeline_score']}, "
                    f"{p.get('total_trials', 0)} trials "
                    f"(P1: {p.get('p1_count', 0)}, P2: {p.get('p2_count', 0)}, "
                    f"P3: {p.get('p3_count', 0)}, P4: {p.get('p4_count', 0)})."
                )
            if isinstance(sr, dict) and sr.get("success_rate") is not None:
                template_parts.append(
                    f"Success rate: {float(sr['success_rate']):.1f}%."
                )

    # LLM synthesis
    fallback = " ".join(template_parts)

    # Build per-entity metrics for LLM
    metrics_for_llm = {}
    for r_ent in resolved:
        m = metrics_comp.get(r_ent["entity_id"], {})
        if m:
            metrics_for_llm[r_ent["label"]] = m

    # Pre-compute differentials so the LLM can cite them directly
    comparison_insights = _compute_comparison_insights(resolved, metrics_comp)
    if comparison_insights:
        fallback = fallback + "\n\n" + comparison_insights

    narrative = llm.synthesize_comparison(
        entity_names=names,
        metrics_by_entity=metrics_for_llm,
        shared_connections=result.get("shared_connections"),
        unique_connections=result.get("unique_connections"),
        fallback_narrative=fallback,
        computed_insights=comparison_insights,
    )

    # Normalize to standard QueryResponse format for frontend rendering
    entities_list = result.get("entities", [])
    normalized_data = {
        "question": f"Compare {' vs '.join(names)}",
        "evidence": [],
        "graph_context": {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0},
        "metrics_context": metrics_comp,
        "entity_focus": [
            {
                "entity_id": e.get("entity_id", ""),
                "entity_type": e.get("entity_type", "drug"),
                "title": e.get("label", "Unknown"),
                "label": e.get("label", "Unknown"),
                "metadata": e.get("properties", {}),
                "total_connections": e.get("total_connections"),
            }
            for e in entities_list
        ],
        "provenance_summary": {
            "total_evidence_items": len(result.get("shared_connections", [])),
            "by_source": {"graph": len(result.get("shared_connections", []))},
        },
    }

    # Build a comparison table so the frontend shows DataTable + CSV export
    comparison_table = _build_comparison_table(resolved, metrics_comp)

    return {
        "narrative": narrative,
        "intent": "compare",
        "data": normalized_data,
        "table_data": comparison_table,
    }


def _build_comparison_table(resolved: list[dict], metrics_comp: dict) -> dict | None:
    """Build a structured table from comparison metrics for DataTable rendering."""
    if not resolved or not metrics_comp:
        return None

    columns = [
        {"key": "metric", "label": "Metric", "type": "text"},
    ]
    for r in resolved:
        columns.append({"key": r["entity_id"], "label": r["label"], "type": "text"})

    rows: list[dict] = []
    metric_fields = [
        ("pipeline", "pipeline_score", "Pipeline Score"),
        ("pipeline", "p1_count", "Phase 1 Trials"),
        ("pipeline", "p2_count", "Phase 2 Trials"),
        ("pipeline", "p3_count", "Phase 3 Trials"),
        ("pipeline", "p4_count", "Phase 4 Trials"),
        ("pipeline", "total_trials", "Total Trials"),
        ("pipeline", "active_pipeline_score", "Active Pipeline Score"),
        ("success_rate", "success_rate", "Success Rate (%)"),
        ("success_rate", "total", "Total Completed+Terminated"),
        ("evidence", "total_articles", "Total Articles"),
        ("evidence", "recent_count", "Recent Articles"),
    ]

    for group_key, field_key, label in metric_fields:
        row: dict = {"metric": label}
        has_data = False
        for r in resolved:
            m = metrics_comp.get(r["entity_id"], {})
            group = m.get(group_key, {}) if isinstance(m, dict) else {}
            val = group.get(field_key) if isinstance(group, dict) else None
            if val is not None:
                has_data = True
                if isinstance(val, float):
                    row[r["entity_id"]] = f"{val:.1f}"
                else:
                    row[r["entity_id"]] = str(val)
            else:
                row[r["entity_id"]] = "—"
        if has_data:
            rows.append(row)

    if not rows:
        return None

    return {
        "columns": columns,
        "rows": rows,
        "title": f"Comparison: {' vs '.join(r['label'] for r in resolved)}",
    }


_MECHANISM_SYNONYMS = {
    "glp-1": "Glucagon-Like Peptide-1",
    "glp1": "Glucagon-Like Peptide-1",
    "sglt2": "Sodium-Glucose Transporter 2",
    "sglt-2": "Sodium-Glucose Transporter 2",
    "dpp-4": "Dipeptidyl-Peptidase IV",
    "dpp4": "Dipeptidyl-Peptidase IV",
    "ace inhibitor": "Angiotensin-Converting Enzyme",
    "arb": "Angiotensin II Type 1 Receptor",
    "beta blocker": "Adrenergic beta-Antagonist",
    "pde": "Phosphodiesterase",
    "mra": "Mineralocorticoid Receptor",
}


def _expand_topic_synonyms(topic: str) -> str:
    """Expand common pharma abbreviations to full mechanism names."""
    lower = topic.lower().strip()
    for abbrev, full in _MECHANISM_SYNONYMS.items():
        if abbrev in lower:
            return full
    return topic


def _handle_landscape(question: str, params: dict, metrics_svc: PharmaMetrics, llm: LLMSynthesizer, conv_context: str = "") -> dict:
    topic = params.get("topic", "")
    expanded_topic = _expand_topic_synonyms(topic) if topic else ""
    segments = metrics_svc.competitive_landscape(topic=expanded_topic if expanded_topic else None, limit=30)
    if not segments:
        return {"narrative": "No competitive landscape data available.", "intent": "landscape", "data": None}

    top = sorted(segments, key=lambda x: x.get("total_pipeline_score", 0), reverse=True)[:10]

    # Enrich with company participation data
    companies = metrics_svc.company_portfolio(limit=10)
    top_companies = sorted(companies, key=lambda c: c.get("pipeline_score_total", 0), reverse=True)[:5]

    # Compute concentration metrics
    drug_counts = [s.get("drug_count", 0) or 0 for s in segments]
    total_drugs = sum(drug_counts)

    hhi = 0
    top3_share = 0.0
    concentration_label = "fragmented"
    if total_drugs > 0:
        shares = [(dc / total_drugs) for dc in drug_counts]
        hhi = int(sum(s * s * 10000 for s in shares))
        top3_share = sum(sorted(shares, reverse=True)[:3]) * 100
        if hhi > 2500:
            concentration_label = "highly concentrated"
        elif hhi > 1500:
            concentration_label = "moderately concentrated"
        else:
            concentration_label = "fragmented"

    # Template fallback
    topic_label = f" for **{topic}**" if topic else ""
    template_parts = [f"The competitive landscape{topic_label} spans **{len(segments)} market segments**."]
    if top:
        best = top[0]
        template_parts.append(
            f"The strongest segment is **{best.get('mechanism_name', 'Unknown')}** "
            f"with {best.get('drug_count', 0)} drugs and a pipeline score of "
            f"{best.get('total_pipeline_score', 0):.0f}."
        )
    template_parts.append(
        f"Market concentration is **{concentration_label}** (HHI: {hhi}). "
        f"The top 3 segments account for **{top3_share:.0f}%** of total drugs."
    )
    if top_companies:
        company_names = [c.get("company_name", "?") for c in top_companies[:3]]
        template_parts.append(
            f"Leading companies by pipeline strength: **{', '.join(company_names)}**."
        )
    fallback = " ".join(template_parts)

    # Build extra context for LLM with company data
    extra_landscape_context = ""
    if top_companies:
        extra_landscape_context = "TOP COMPANIES:\n" + "\n".join(
            f"- {c.get('company_name', '?')}: {c.get('drug_count', 0)} drugs, "
            f"{c.get('trial_count', 0)} trials, pipeline score {c.get('pipeline_score_total', 0):.0f}"
            for c in top_companies
        )
    extra_landscape_context += (
        f"\n\nCONCENTRATION (across therapeutic areas, NOT companies): "
        f"{concentration_label} (HHI={hhi}, top-3 therapeutic area share={top3_share:.0f}%)"
    )
    if conv_context:
        extra_landscape_context += f"\n\nPRIOR CONVERSATION:\n{conv_context}"

    # LLM synthesis
    narrative = llm.synthesize(
        question=question,
        intent="landscape",
        metrics={"segments": top},
        extra_context=extra_landscape_context,
        fallback_narrative=fallback,
    )

    # Build table for DataTable + CSV export
    landscape_table = {
        "columns": [
            {"key": "mechanism_name", "label": "Mechanism", "type": "text"},
            {"key": "therapeutic_area", "label": "Therapeutic Area", "type": "text"},
            {"key": "drug_count", "label": "Drugs", "type": "number"},
            {"key": "trial_count", "label": "Trials", "type": "number"},
            {"key": "active_trial_count", "label": "Active Trials", "type": "number"},
            {"key": "total_pipeline_score", "label": "Pipeline Score", "type": "number"},
        ],
        "rows": [
            {
                "mechanism_name": s.get("mechanism_name", "Unknown"),
                "therapeutic_area": s.get("therapeutic_area", "—"),
                "drug_count": s.get("drug_count", 0),
                "trial_count": s.get("trial_count", 0),
                "active_trial_count": s.get("active_trial_count", 0),
                "total_pipeline_score": round(s.get("total_pipeline_score", 0), 1),
            }
            for s in top
        ],
        "title": "Competitive Landscape",
    }

    return {
        "narrative": narrative,
        "intent": "landscape",
        "data": {
            "question": question,
            "evidence": [],
            "graph_context": {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0},
            "metrics_context": {s.get("mechanism_name", f"seg_{i}"): {"competitive": s} for i, s in enumerate(top)},
            "entity_focus": [],
            "provenance_summary": {"total_evidence_items": len(segments), "by_source": {"metrics": len(segments)}},
        },
        "table_data": landscape_table,
    }


def _handle_portfolio(params: dict, db: Database, engine: QueryEngine, metrics_svc: PharmaMetrics, llm: LLMSynthesizer, conv_context: str = "") -> dict:
    name = params.get("company_name", "")
    resolved = _resolve_entity(name, "company", db)

    if not resolved:
        return {
            "narrative": f"Could not find company '{name}'. Try 'Novo Nordisk portfolio' or 'Eli Lilly portfolio'.",
            "intent": "portfolio",
            "data": None,
        }

    result = engine.entity_dossier(resolved["entity_id"], "company")
    portfolio = metrics_svc.company_portfolio(company_id=resolved["entity_id"], limit=1)

    # Template fallback
    template = f"**{resolved['label']}** portfolio overview."
    if portfolio:
        p = portfolio[0]
        template += (
            f" {p.get('drug_count', 0)} drugs, {p.get('trial_count', 0)} trials "
            f"({p.get('active_trial_count', 0)} active), pipeline score: {p.get('pipeline_score_total', 0):.0f}."
        )

    # LLM synthesis
    entity_details = {"company_name": resolved["label"]}
    if portfolio:
        entity_details.update(portfolio[0])

    evidence_snippets = [e.content for e in result.evidence[:10]]

    narrative = llm.synthesize_dossier(
        question=f"{resolved['label']} portfolio",
        entity_name=resolved["label"],
        entity_type="company",
        entity_details=entity_details,
        metrics={"portfolio": portfolio[0]} if portfolio else None,
        evidence_snippets=evidence_snippets,
        fallback_narrative=template,
    )

    # Build table for DataTable + CSV export
    portfolio_table = None
    if portfolio:
        p = portfolio[0]
        portfolio_table = {
            "columns": [
                {"key": "metric", "label": "Metric", "type": "text"},
                {"key": "value", "label": "Value", "type": "text"},
            ],
            "rows": [
                {"metric": "Drugs", "value": str(p.get("drug_count", 0))},
                {"metric": "Trials", "value": str(p.get("trial_count", 0))},
                {"metric": "Active Trials", "value": str(p.get("active_trial_count", 0))},
                {"metric": "Articles", "value": str(p.get("article_count", 0))},
                {"metric": "Therapeutic Areas", "value": str(p.get("ta_count", 0))},
                {"metric": "Pipeline Score", "value": str(round(p.get("pipeline_score_total", 0), 1))},
            ],
            "title": f"{resolved['label']} Portfolio",
        }

    return {
        "narrative": narrative,
        "intent": "portfolio",
        "data": _enrich_result(result, db),
        "table_data": portfolio_table,
    }


def _handle_pipeline(params: dict, metrics_svc: PharmaMetrics, llm: LLMSynthesizer, conv_context: str = "") -> dict:
    ta = params.get("therapeutic_area", "")
    pipelines = metrics_svc.drug_pipeline_strength(therapeutic_area=ta if ta else None, limit=20)

    if not pipelines:
        return {"narrative": "No pipeline data available for this query.", "intent": "pipeline", "data": None}

    top = sorted(pipelines, key=lambda x: x.get("pipeline_score", 0), reverse=True)[:10]

    # Template fallback
    template = f"Top **{len(top)}** drugs by pipeline strength"
    if ta:
        template += f" in **{ta}**"
    template += "."
    if top:
        best = top[0]
        template += (
            f" Leading: **{best.get('drug_name', 'Unknown')}** "
            f"(score: {best.get('pipeline_score', 0)}"
        )
        pr = best.get("phase_progression_rate")
        if pr is not None:
            template += f", late/early ratio: {pr}"
        pct = best.get("percentile_rank")
        if pct is not None:
            template += f", {pct}th percentile"
        template += ")."

    # Build extra context with phase distribution insights
    early_heavy = sum(1 for p in top if (p.get("p1_count", 0) or 0) + (p.get("p2_count", 0) or 0) > (p.get("p3_count", 0) or 0) + (p.get("p4_count", 0) or 0))
    late_heavy = len(top) - early_heavy
    extra_context = f"PIPELINE MATURITY: {late_heavy} of {len(top)} drugs are late-stage heavy (Phase 3+4 > Phase 1+2)."
    if ta:
        extra_context += f"\nTherapeutic area focus: {ta}"
    if conv_context:
        extra_context += f"\n\nPRIOR CONVERSATION:\n{conv_context}"

    # LLM synthesis
    narrative = llm.synthesize(
        question=f"Pipeline {'for ' + ta if ta else 'overview'}",
        intent="pipeline",
        metrics={"pipelines": top},
        extra_context=extra_context,
        fallback_narrative=template,
    )

    # Build table for DataTable + CSV export
    pipeline_table = {
        "columns": [
            {"key": "drug_name", "label": "Drug", "type": "text"},
            {"key": "p1_count", "label": "Phase 1", "type": "number"},
            {"key": "p2_count", "label": "Phase 2", "type": "number"},
            {"key": "p3_count", "label": "Phase 3", "type": "number"},
            {"key": "p4_count", "label": "Phase 4", "type": "number"},
            {"key": "total_trials", "label": "Total Trials", "type": "number"},
            {"key": "pipeline_score", "label": "Pipeline Score", "type": "number"},
        ],
        "rows": [
            {
                "drug_name": p.get("drug_name", "Unknown"),
                "p1_count": p.get("p1_count", 0),
                "p2_count": p.get("p2_count", 0),
                "p3_count": p.get("p3_count", 0),
                "p4_count": p.get("p4_count", 0),
                "total_trials": p.get("total_trials", 0),
                "pipeline_score": round(p.get("pipeline_score", 0), 1),
            }
            for p in top
        ],
        "title": f"Pipeline Strength{' — ' + ta if ta else ''}",
    }

    return {
        "narrative": narrative,
        "intent": "pipeline",
        "data": {
            "question": f"Pipeline {'for ' + ta if ta else 'overview'}",
            "evidence": [],
            "graph_context": {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0},
            "metrics_context": {p.get("drug_name", f"drug_{i}"): {"pipeline": p} for i, p in enumerate(top)},
            "entity_focus": [],
            "provenance_summary": {"total_evidence_items": len(top), "by_source": {"metrics": len(top)}},
        },
        "table_data": pipeline_table,
    }


def _handle_general(
    question: str,
    engine: QueryEngine,
    db: Database,
    llm: LLMSynthesizer,
    include_graph: bool = True,
    include_metrics: bool = True,
    conv_context: str = "",
) -> dict:
    result = engine.query(
        question,
        include_graph=include_graph,
        include_metrics=include_metrics,
    )
    return _format_query_result("general", question, result, db, llm, conv_context=conv_context)


def _handle_deep_research(
    question: str,
    db: Database,
    engine: QueryEngine,
    llm: LLMSynthesizer,
    web_research: WebResearchService,
    include_graph: bool,
    include_metrics: bool,
    include_web: bool,
) -> dict:
    """Expanded research flow: richer evidence pass + optional web augmentation."""
    result = engine.query(
        question,
        max_evidence=24,
        include_graph=include_graph,
        include_metrics=include_metrics,
    )
    enriched = _enrich_result(result, db)
    web_results = web_research.search(question, limit=6) if include_web else []

    report_fallback = _build_research_fallback_report(question, enriched, web_results)
    report = llm.synthesize_research_report(
        question=question,
        graph_summary=enriched.get("graph_context"),
        metrics=enriched.get("metrics_context"),
        evidence_snippets=[e.get("content", "") for e in enriched.get("evidence", [])[:12]],
        web_results=web_results,
        fallback_report=report_fallback,
    )
    narrative = _extract_research_summary(report)

    return {
        "narrative": narrative,
        "intent": Intent.DEEP_RESEARCH,
        "data": enriched,
        "report": report,
        "web_results": web_results,
        "report_meta": {
            "web_enabled": include_web,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "visualizations": _build_visualizations(enriched),
    }


def _format_query_result(intent: str, question: str, result, db: Database, llm: LLMSynthesizer, conv_context: str = "") -> dict:
    # Template fallback
    parts = []
    ec = len(result.evidence)
    gc = result.graph_context
    mc = result.metrics_context

    if result.entity_focus:
        parts.append(f"Found **{len(result.entity_focus)} entities** matching your query.")
    elif ec > 0:
        parts.append(f"Found **{ec} evidence items** for your query.")
    else:
        parts.append("I searched the knowledge graph but found limited results. Try being more specific.")

    if gc.get("node_count", 0) > 0:
        parts.append(f"Graph context: {gc['node_count']} nodes, {gc['edge_count']} edges.")

    if mc:
        for eid, metrics in mc.items():
            if isinstance(metrics, dict) and "pipeline" in metrics:
                p = metrics["pipeline"]
                if isinstance(p, dict):
                    parts.append(f"Pipeline score for {eid}: **{p.get('pipeline_score', 'N/A')}**.")
                    break

    fallback = " ".join(parts)

    # LLM synthesis
    evidence_snippets = [e.content for e in result.evidence[:10]]
    graph_summary = None
    if gc.get("node_count", 0) > 0:
        nodes_by_type: dict[str, list[str]] = {}
        for node in gc.get("nodes", [])[:30]:
            if isinstance(node, dict) and node.get("label"):
                nt = node.get("entity_type", "other")
                nodes_by_type.setdefault(nt, []).append(node["label"])
        graph_summary = {
            "node_count": gc["node_count"],
            "edge_count": gc["edge_count"],
            "connected_entities": {k: v[:10] for k, v in nodes_by_type.items()},
        }

    narrative = llm.synthesize(
        question=question,
        intent=intent,
        metrics=mc if mc else None,
        graph_summary=graph_summary,
        evidence_snippets=evidence_snippets,
        extra_context=conv_context if conv_context else None,
        fallback_narrative=fallback,
    )

    return {
        "narrative": narrative,
        "intent": intent,
        "data": _enrich_result(result, db),
    }


def _enrich_result(result, db: Database) -> dict:
    """Serialize QueryResult and normalize graph edges for frontend compatibility."""
    raw = _serialize_result(result)

    # Normalize graph edges: backend uses source/target/type, frontend expects source_id/target_id/link_type
    gc = raw.get("graph_context", {})
    if gc.get("edges"):
        gc["edges"] = [
            {
                "source_id": e.get("source_id") or e.get("source", ""),
                "target_id": e.get("target_id") or e.get("target", ""),
                "link_type": e.get("link_type") or e.get("type", ""),
                "confidence": e.get("confidence", 0.5),
                "via": e.get("via", ""),
            }
            for e in gc["edges"]
        ]

    # Enrich entity_focus with title field (frontend expects 'title')
    for ef in raw.get("entity_focus", []):
        if "title" not in ef:
            ef["title"] = ef.get("label", ef.get("entity_id", "Unknown"))
        if "metadata" not in ef:
            ef["metadata"] = ef.get("properties", {})

    # Add connection counts to entity_focus entries
    for ef in raw.get("entity_focus", []):
        eid = ef.get("entity_id", "")
        if eid and "total_connections" not in ef:
            row = db.fetch_one(
                """SELECT COUNT(*) AS cnt FROM entity_links
                   WHERE source_entity_id::text = %s OR target_entity_id::text = %s""",
                [eid, eid],
            )
            ef["total_connections"] = row["cnt"] if row else 0

    return raw


def _serialize_result(result) -> dict:
    """Convert a QueryResult dataclass to a JSON-safe dict."""
    return {
        "question": result.question,
        "evidence": [
            {
                "source": e.source,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "content": e.content,
                "relevance": e.relevance,
                "provenance": normalize_provenance(e.provenance, e.entity_type, e.entity_id),
            }
            for e in result.evidence
        ],
        "graph_context": result.graph_context,
        "metrics_context": result.metrics_context,
        "entity_focus": result.entity_focus,
        "provenance_summary": result.provenance_summary,
    }


def _extract_research_summary(report: str) -> str:
    if not report:
        return "Deep research completed. Open the report for full analysis."
    for raw_line in report.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        header = line.lstrip("#").strip().lower().rstrip(":")
        if header in {
            "executive summary",
            "internal evidence (knowledge graph)",
            "quantitative signals",
            "external context (web)",
            "risks and data gaps",
            "recommended next questions",
        }:
            continue
        return line if len(line) <= 340 else f"{line[:337]}..."
    compact = " ".join(report.split())
    return compact if len(compact) <= 340 else f"{compact[:337]}..."


def _build_research_fallback_report(question: str, data: dict, web_results: list[dict]) -> str:
    entities = [
        str(e.get("title") or e.get("label") or e.get("entity_id"))
        for e in data.get("entity_focus", [])[:5]
    ]
    evidence = data.get("evidence", [])
    graph_context = data.get("graph_context", {})
    provenance = data.get("provenance_summary", {})
    metrics_context = data.get("metrics_context", {})

    top_source = "unknown"
    by_source = provenance.get("by_source")
    if isinstance(by_source, dict) and by_source:
        top_source = max(by_source.items(), key=lambda item: _to_number(item[1]) or 0)[0]

    pipeline_label = None
    pipeline_score = None
    for metric_group in metrics_context.values():
        if not isinstance(metric_group, dict):
            continue
        pipeline = metric_group.get("pipeline")
        if not isinstance(pipeline, dict):
            continue
        score = _to_number(pipeline.get("pipeline_score"))
        if score is None:
            continue
        if pipeline_score is None or score > pipeline_score:
            pipeline_score = score
            pipeline_label = (
                pipeline.get("drug_name")
                or pipeline.get("name")
                or "top-ranked asset"
            )

    report_lines = [
        "## Executive Summary",
        (
            f'Research request: "{question}". The internal graph returned '
            f'{len(evidence)} evidence items with '
            f'{int(graph_context.get("node_count", 0))} connected nodes and '
            f'{int(graph_context.get("edge_count", 0))} links.'
        ),
        "",
        "## Internal Evidence (Knowledge Graph)",
        f"Primary entities detected: {', '.join(entities) if entities else 'None identified with high confidence.'}",
        f"Most represented source channel: {top_source}.",
        "",
        "## Quantitative Signals",
    ]
    if pipeline_label is not None and pipeline_score is not None:
        report_lines.append(f"Highest pipeline signal: {pipeline_label} (score {pipeline_score:.2f}).")
    else:
        report_lines.append("No strong quantitative metric row was available for this query.")

    if web_results:
        report_lines.extend(
            [
                "",
                "## External Context (Web)",
                f"Web search contributed {len(web_results)} additional references.",
            ]
        )
        for idx, item in enumerate(web_results[:4], 1):
            title = str(item.get("title", "Untitled source"))
            url = str(item.get("url", ""))
            report_lines.append(f"{idx}. {title} ({url})")

    report_lines.extend(
        [
            "",
            "## Risks and Data Gaps",
            "Potential entity aliasing and source freshness differences can change interpretation.",
            "",
            "## Recommended Next Questions",
            "1. Narrow to a therapeutic area and trial endpoint for precision.",
            "2. Validate top claims against linked primary sources before decisions.",
        ]
    )
    return "\n".join(report_lines)


def _build_visualizations(data: Optional[dict]) -> list[dict]:
    if not isinstance(data, dict):
        return []

    charts: list[dict] = []
    metrics_context = data.get("metrics_context")
    if isinstance(metrics_context, dict):
        pipeline_chart = _build_pipeline_chart(metrics_context)
        if pipeline_chart:
            charts.append(pipeline_chart)

        success_chart = _build_success_rate_chart(metrics_context)
        if success_chart:
            charts.append(success_chart)

        landscape_chart = _build_landscape_chart(metrics_context)
        if landscape_chart:
            charts.append(landscape_chart)

    provenance = data.get("provenance_summary")
    if isinstance(provenance, dict):
        by_entity_type = provenance.get("by_entity_type")
        if isinstance(by_entity_type, dict):
            entity_mix_data = [
                {"label": str(k).replace("_", " ").title(), "value": int(_to_number(v) or 0)}
                for k, v in by_entity_type.items()
                if (_to_number(v) or 0) > 0
            ]
            if len(entity_mix_data) >= 2:
                charts.append(
                    {
                        "id": "entity-type-mix",
                        "type": "donut",
                        "title": "Evidence mix by entity type",
                        "value_unit": "items",
                        "data": entity_mix_data,
                    }
                )

    return charts


def _build_pipeline_chart(metrics_context: dict) -> Optional[dict]:
    best_pipeline: Optional[dict] = None
    best_score: Optional[float] = None

    for metric_group in metrics_context.values():
        if not isinstance(metric_group, dict):
            continue
        pipeline = metric_group.get("pipeline")
        if not isinstance(pipeline, dict):
            continue
        score = _to_number(pipeline.get("pipeline_score"))
        if score is None:
            continue
        if best_score is None or score > best_score:
            best_score = score
            best_pipeline = pipeline

    if not best_pipeline:
        return None

    phase_data = [
        {"label": "Phase 1", "value": int(_to_number(best_pipeline.get("p1_count")) or 0)},
        {"label": "Phase 2", "value": int(_to_number(best_pipeline.get("p2_count")) or 0)},
        {"label": "Phase 3", "value": int(_to_number(best_pipeline.get("p3_count")) or 0)},
        {"label": "Phase 4", "value": int(_to_number(best_pipeline.get("p4_count")) or 0)},
    ]
    if sum(point["value"] for point in phase_data) <= 0:
        return None

    return {
        "id": "pipeline-phase-distribution",
        "type": "bar",
        "title": f"{best_pipeline.get('drug_name', 'Top asset')} phase distribution",
        "value_unit": "trials",
        "data": phase_data,
    }


def _build_success_rate_chart(metrics_context: dict) -> Optional[dict]:
    best_success: Optional[dict] = None
    best_total: float = -1

    for metric_group in metrics_context.values():
        if not isinstance(metric_group, dict):
            continue
        success = metric_group.get("success_rate")
        if not isinstance(success, dict):
            continue
        total = _to_number(success.get("total")) or 0
        if total > best_total:
            best_total = total
            best_success = success

    if not best_success or best_total <= 0:
        return None

    status_data = [
        {"label": "Completed", "value": int(_to_number(best_success.get("completed")) or 0)},
        {"label": "Active", "value": int(_to_number(best_success.get("active")) or 0)},
        {"label": "Terminated", "value": int(_to_number(best_success.get("terminated")) or 0)},
    ]
    if sum(point["value"] for point in status_data) <= 0:
        return None

    return {
        "id": "trial-status-breakdown",
        "type": "donut",
        "title": f"{best_success.get('drug_name', 'Top asset')} trial status",
        "value_unit": "trials",
        "data": status_data,
    }


def _build_landscape_chart(metrics_context: dict) -> Optional[dict]:
    """Build a bar chart from competitive landscape segments."""
    segments = []
    for metric_group in metrics_context.values():
        if not isinstance(metric_group, dict):
            continue
        comp = metric_group.get("competitive")
        if not isinstance(comp, dict):
            continue
        name = comp.get("mechanism_name") or comp.get("therapeutic_area") or "Unknown"
        score = _to_number(comp.get("total_pipeline_score")) or 0
        drug_count = _to_number(comp.get("drug_count")) or 0
        if score > 0 or drug_count > 0:
            segments.append({"label": name, "value": round(score, 1)})

    if len(segments) < 2:
        return None

    # Top 8 by pipeline score
    segments.sort(key=lambda x: x["value"], reverse=True)
    return {
        "id": "landscape-pipeline-scores",
        "type": "bar",
        "title": "Pipeline strength by mechanism",
        "value_unit": "score",
        "data": segments[:8],
    }


def _to_number(value) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_scope(raw_scope) -> str:
    scope = str(raw_scope or "default").strip()
    if not scope:
        return "default"
    if len(scope) > 120:
        scope = scope[:120]
    return scope


def _safe_filename(raw_name: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9._-]+", "-", raw_name.strip().lower()).strip("-")
    return clean or "deep-research-report"


def _sanitize_transcript(messages: list[dict]) -> list[dict]:
    sanitized: list[dict] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        sanitized.append(
            {
                "id": str(item.get("id") or ""),
                "role": str(item.get("role") or "assistant"),
                "content": str(item.get("content") or ""),
                "timestamp": item.get("timestamp"),
                "data": item.get("data"),
                "report": item.get("report"),
                "webResults": item.get("webResults"),
                "reportMeta": item.get("reportMeta"),
                "visualizations": item.get("visualizations"),
            }
        )
    return sanitized


def _run_research_job_task(job_id: str, scope_key: str) -> None:
    local_db = Database(config.db.dsn)
    local_db.connect()
    workspace = ChatWorkspaceService(local_db)
    try:
        workspace.mark_research_job_running(job_id=job_id)
        job = workspace.get_research_job(job_id=job_id, scope_key=scope_key)
        if not job:
            workspace.fail_research_job(job_id=job_id, error_message="Research job not found")
            return

        options = job.get("options") if isinstance(job.get("options"), dict) else {}
        include_graph = _coerce_bool(options.get("include_graph"), True)
        include_metrics = _coerce_bool(options.get("include_metrics"), True)
        source_strict = _coerce_bool(options.get("source_strict"), True)
        include_web = _coerce_bool(options.get("include_web"), False)

        search_svc = HybridSearch(local_db, config)
        graph_svc = GraphTraversal(local_db, config)
        metrics_svc = PharmaMetrics(local_db, config)
        engine = QueryEngine(local_db, config, search_svc, graph_svc, metrics_svc)
        llm = LLMSynthesizer(config)
        web_research = WebResearchService(config)

        payload = _handle_deep_research(
            question=job.get("question", ""),
            db=local_db,
            engine=engine,
            llm=llm,
            web_research=web_research,
            include_graph=include_graph,
            include_metrics=include_metrics,
            include_web=include_web,
        )
        payload = _apply_chat_modes(payload, include_graph, include_metrics, source_strict)
        payload["visualizations"] = _build_visualizations(payload.get("data"))

        workspace.complete_research_job(job_id=job_id, payload=payload)
    except Exception as exc:
        logger.exception("Research job failed: %s", job_id)
        workspace.fail_research_job(job_id=job_id, error_message=str(exc))
    finally:
        try:
            local_db.close()
        except Exception:
            pass
