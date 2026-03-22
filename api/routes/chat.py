"""Chat / Orchestration endpoint for the intelligence console.

Receives a natural language question, routes to the best service combination,
and returns a structured response with narrative + data cards.

Architecture:
  1. Regex-based intent detection (fast, deterministic)
  2. Deterministic service calls (search, graph, metrics)
  3. LLM synthesis of gathered data into analyst-grade narrative
  4. Falls back to template narrative if LLM is unavailable

Handler logic lives in services/chat_handlers/. This file is a thin router.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from api.deps import (
    get_conversation_memory,
    get_db,
    get_llm,
    get_metrics,
    get_query_engine,
    get_unified_handler,
    get_web_research,
    get_workspace,
    save_conversation_memory,
)
from config import config
from db import Database
from services.graph import GraphTraversal
from services.query_engine import QueryEngine
from services.search import HybridSearch
from services.metrics import PharmaMetrics
from services.llm import LLMSynthesizer
from services.web_research import WebResearchService
from services.workspace import ChatWorkspaceService

from services.chat_handlers import (
    Intent,
    detect_intent,
    build_conversation_context,
    resolve_followup_question,
    apply_chat_modes,
    build_visualizations,
    coerce_bool,
    generate_followups,
    normalize_scope,
    safe_filename,
    sanitize_transcript,
    handle_compare,
    handle_deep_research,
    handle_dossier,
    handle_general,
    handle_landscape,
    handle_pipeline,
    handle_portfolio,
    handle_structured_query,
    handle_team_eval,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


# ── CTX benchmark endpoint ──

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


# ── Main chat endpoint ──

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

    include_graph = coerce_bool(body.get("include_graph"), True)
    include_metrics = coerce_bool(body.get("include_metrics"), True)
    source_strict = coerce_bool(body.get("source_strict"), True)
    deep_research = coerce_bool(body.get("deep_research"), False)
    include_web = coerce_bool(body.get("include_web"), False)
    team_eval = coerce_bool(body.get("team_eval"), False)
    conversation_history = body.get("conversation_history", [])
    if not isinstance(conversation_history, list):
        conversation_history = []

    # Server-side conversation memory (per session)
    session_id = str(body.get("session_id", "")).strip() or "default"
    memory = get_conversation_memory(session_id)

    # Use ConversationMemory for context and coreference resolution
    conv_context = memory.get_context() or build_conversation_context(conversation_history)

    # Resolve follow-up references using memory (falls back to ad-hoc if memory is empty)
    resolved_question = memory.resolve_reference(question) if memory.get_context() else resolve_followup_question(question, conversation_history)
    if resolved_question != question:
        logger.info("Follow-up resolved: %r → %r", question, resolved_question)

    intent, params = detect_intent(resolved_question)
    if deep_research:
        intent, params = Intent.DEEP_RESEARCH, {}
    if team_eval:
        intent, params = Intent.TEAM_EVAL, {}
    logger.info("Chat intent: %s, params: %s", intent, params)

    # Unified handler (CTX pipeline) — opt-in via MZ_UNIFIED_HANDLER=true
    if config.agent.use_unified_handler:
        unified = get_unified_handler()
        if unified:
            try:
                result = unified.handle(resolved_question, conversation_history=conversation_history, memory_context=conv_context)
                if result is not None:
                    payload = result
                    payload["visualizations"] = payload.get("visualizations") or build_visualizations(
                        payload.get("data"),
                    )
                    payload["followup_suggestions"] = payload.get("followup_suggestions") or generate_followups(
                        question, payload.get("intent", "general"), payload.get("narrative", ""), params,
                    )
                    memory.add_exchange(question, payload.get("narrative", ""))
                    save_conversation_memory(session_id, memory, db)
                    return payload
            except Exception as e:
                logger.warning("Unified handler error, falling back to legacy: %s", e)

    try:
        if intent == Intent.TEAM_EVAL:
            payload = handle_team_eval(resolved_question, engine, db, llm)

        elif intent == Intent.STRUCTURED_QUERY:
            payload = handle_structured_query(resolved_question, engine, db, llm, conversation_history)

        elif intent == Intent.DEEP_RESEARCH:
            payload = handle_deep_research(
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
            payload = handle_dossier(params, db, engine, llm, conv_context=conv_context)

        elif intent == Intent.COMPARE:
            payload = handle_compare(params, db, engine, llm, conv_context=conv_context)

        elif intent == Intent.LANDSCAPE:
            payload = handle_landscape(resolved_question, params, metrics_svc, llm, conv_context=conv_context)

        elif intent == Intent.PORTFOLIO:
            payload = handle_portfolio(params, db, engine, metrics_svc, llm, conv_context=conv_context)

        elif intent == Intent.PIPELINE:
            payload = handle_pipeline(params, metrics_svc, llm, conv_context=conv_context)

        else:
            payload = handle_general(
                resolved_question,
                engine,
                db,
                llm,
                include_graph=include_graph,
                include_metrics=include_metrics,
                conv_context=conv_context,
            )

        payload = apply_chat_modes(payload, include_graph, include_metrics, source_strict)
        payload["visualizations"] = build_visualizations(payload.get("data"))
        payload["followup_suggestions"] = generate_followups(
            question, intent, payload.get("narrative", ""), params,
        )
        memory.add_exchange(question, payload.get("narrative", ""))
        save_conversation_memory(session_id, memory, db)
        return payload

    except Exception as e:
        logger.exception("Chat error for question: %s", question)
        error_msg = f"I encountered an error processing your question: {str(e)}"
        memory.add_exchange(question, error_msg)
        save_conversation_memory(session_id, memory, db)
        return {
            "narrative": error_msg,
            "intent": intent,
            "data": None,
        }


# ── Streaming chat endpoint ──

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

    include_graph = coerce_bool(body.get("include_graph"), True)
    include_metrics = coerce_bool(body.get("include_metrics"), True)
    source_strict = coerce_bool(body.get("source_strict"), True)
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
                payload = handle_compare(params, db, engine, llm)
            elif intent == Intent.LANDSCAPE:
                payload = handle_landscape(question, params, metrics_svc, llm)
            elif intent == Intent.PORTFOLIO:
                payload = handle_portfolio(params, db, engine, metrics_svc, llm)
            elif intent == Intent.PIPELINE:
                payload = handle_pipeline(params, metrics_svc, llm)
            elif intent == Intent.STRUCTURED_QUERY:
                payload = handle_structured_query(question, engine, db, llm, conversation_history)
            else:
                payload = handle_general(question, engine, db, llm, include_graph=include_graph, include_metrics=include_metrics)

            payload = apply_chat_modes(payload, include_graph, include_metrics, source_strict)
            payload["visualizations"] = build_visualizations(payload.get("data"))
            payload["followup_suggestions"] = generate_followups(question, intent, payload.get("narrative", ""), params)

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


# ── Session endpoints ──

@router.get("/sessions")
def list_chat_sessions(
    scope_key: str = Query("default"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    workspace: ChatWorkspaceService = Depends(get_workspace),
):
    scope = normalize_scope(scope_key)
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
    scope = normalize_scope(body.get("scope_key"))
    title = str(body.get("title") or "").strip() or "Saved conversation"
    session_id = str(body.get("session_id") or "").strip() or None
    transcript = body.get("transcript")
    if not isinstance(transcript, list):
        raise HTTPException(status_code=400, detail="transcript must be a list")
    summary = str(body.get("summary") or "").strip() or None

    saved = workspace.save_session(
        scope_key=scope,
        title=title,
        transcript=sanitize_transcript(transcript),
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
    scope = normalize_scope(scope_key)
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
    scope = normalize_scope(scope_key)
    deleted = workspace.delete_session(session_id=session_id, scope_key=scope)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True, "session_id": session_id}


# ── Report export ──

@router.post("/export/report")
def export_report(body: dict):
    report = str(body.get("report") or "").strip()
    if not report:
        raise HTTPException(status_code=400, detail="report is required")

    title = str(body.get("title") or "deep-research-report").strip()
    export_format = str(body.get("format") or "md").strip().lower()
    safe_name = safe_filename(title or "deep-research-report")

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


# ── Research jobs ──

@router.post("/research-jobs")
def create_research_job(
    body: dict,
    background_tasks: BackgroundTasks,
    workspace: ChatWorkspaceService = Depends(get_workspace),
):
    question = str(body.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    scope = normalize_scope(body.get("scope_key"))
    options = {
        "include_graph": coerce_bool(body.get("include_graph"), True),
        "include_metrics": coerce_bool(body.get("include_metrics"), True),
        "source_strict": coerce_bool(body.get("source_strict"), True),
        "include_web": coerce_bool(body.get("include_web"), False),
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
    scope = normalize_scope(scope_key)
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
    scope = normalize_scope(scope_key)
    job = workspace.get_research_job(job_id=job_id, scope_key=scope)
    if not job:
        raise HTTPException(status_code=404, detail="Research job not found")
    return {"job": job}


# ── Background task for research jobs ──

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
        include_graph = coerce_bool(options.get("include_graph"), True)
        include_metrics = coerce_bool(options.get("include_metrics"), True)
        source_strict = coerce_bool(options.get("source_strict"), True)
        include_web = coerce_bool(options.get("include_web"), False)

        search_svc = HybridSearch(local_db, config)
        graph_svc = GraphTraversal(local_db, config)
        metrics_svc = PharmaMetrics(local_db, config)
        engine = QueryEngine(local_db, config, search_svc, graph_svc, metrics_svc)
        llm = LLMSynthesizer(config)
        web_research = WebResearchService(config)

        payload = handle_deep_research(
            question=job.get("question", ""),
            db=local_db,
            engine=engine,
            llm=llm,
            web_research=web_research,
            include_graph=include_graph,
            include_metrics=include_metrics,
            include_web=include_web,
        )
        payload = apply_chat_modes(payload, include_graph, include_metrics, source_strict)
        payload["visualizations"] = build_visualizations(payload.get("data"))

        workspace.complete_research_job(job_id=job_id, payload=payload)
    except Exception as exc:
        logger.exception("Research job failed: %s", job_id)
        workspace.fail_research_job(job_id=job_id, error_message=str(exc))
    finally:
        try:
            local_db.close()
        except Exception:
            pass
