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

import hashlib
import logging
import re
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from api.deps import (
    get_conversation_memory,
    get_db,
    get_entity_canonicalizer,
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
    detect_compound_intent,
    detect_intent,
    build_conversation_context,
    resolve_followup_question,
    apply_chat_modes,
    build_visualizations,
    coerce_bool,
    generate_followups,
    handle_compare,
    handle_compound,
    handle_deep_research,
    handle_dossier,
    handle_general,
    handle_landscape,
    handle_pipeline,
    handle_portfolio,
    handle_structured_query,
    handle_team_eval,
    normalize_scope,
    safe_filename,
    sanitize_transcript,
)

logger = logging.getLogger(__name__)


# ── SPEC-011: A/B routing for unified handler ──

def _should_use_unified_handler(session_id: str) -> bool:
    """Decide whether this session uses the CTX UnifiedChatHandler or legacy.

    Honors two env-driven knobs:
      - MZ_UNIFIED_HANDLER (bool, default true): hard kill switch
      - MZ_UNIFIED_HANDLER_ROLLOUT (float 0.0-1.0, default 1.0): traffic share

    Routing is deterministic per session_id: hash(session_id) mod 256 bucket
    means the same user always sees the same handler across messages.
    """
    if not config.agent.use_unified_handler:
        return False
    rollout = config.agent.unified_handler_rollout
    if rollout >= 1.0:
        return True
    if rollout <= 0.0:
        return False
    bucket = hashlib.md5(session_id.encode("utf-8")).digest()[0]
    return bucket < (rollout * 256)


def _log_chat_routing(
    handler: str,
    session_id: str,
    intent: str,
    fallback: bool = False,
    error: str | None = None,
    extra: dict | None = None,
) -> None:
    """Fire-and-forget telemetry for the A/B comparison.

    Logs as `chat_routing` event so the SQL: `... WHERE event_type = 'chat_routing'`
    can group by metadata.handler for unified-vs-legacy comparison.
    """
    try:
        from services.telemetry import log_ctx_event
        bucket = hashlib.md5(session_id.encode("utf-8")).digest()[0]
        metadata = {
            "handler": handler,
            "bucket": bucket,
            "intent": intent,
            "fallback_triggered": fallback,
        }
        if error:
            metadata["error"] = error[:200]
        if extra:
            metadata.update(extra)
        log_ctx_event(
            db=get_db(),
            question="",  # deliberately empty — handler attribution is what matters
            intent=intent,
            event_type="chat_routing",
            metadata=metadata,
        )
    except Exception:
        # Telemetry must never break the main chat flow
        pass


# ── SPEC_015 WS-1: brand→generic canonicalisation ──

# Tokens that indicate the surrounding text isn't an entity name.
_NON_ENTITY_TOKENS = {
    "the", "a", "an", "of", "for", "in", "on", "and", "or", "to",
    "vs", "vs.", "versus", "compare", "show", "tell", "what", "which",
    "is", "are", "does", "do", "side", "effects", "pipeline", "trial",
    "trials", "phase", "compared", "mechanism", "study", "studies",
    "drug", "company", "this", "that", "with", "without", "between",
}

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]+")


def _canonicalize_question(question: str, canonicalizer) -> tuple[str, dict]:
    """Replace high-confidence brand-name mentions with their generic name.

    Strategy: tokenise the question, attempt canonicalisation on each candidate
    token (and 2-token windows for compound names like "novo nordisk"). Replace
    only matches with confidence >= 0.7 (catches exact + alias, leaves fuzzy
    matches alone since they could be wrong).

    Returns (canonical_question, {original_token: CanonicalResult, ...}).
    """
    if not question or not canonicalizer:
        return question, {}

    tokens = _TOKEN_RE.findall(question)
    candidates: list[str] = []
    seen: set[str] = set()
    for tok in tokens:
        low = tok.lower()
        if low in _NON_ENTITY_TOKENS or len(tok) < 3 or low in seen:
            continue
        seen.add(low)
        candidates.append(tok)

    if not candidates:
        return question, {}

    try:
        results = canonicalizer.canonicalize_batch(candidates, hint_type="drug")
    except Exception:
        logger.exception("entity canonicalisation failed; using original question")
        return question, {}

    canonical_question = question
    canon_map: dict = {}
    for original, result in results.items():
        if result is None or result.confidence < 0.7:
            continue
        # Only replace when the canonical name actually differs (case-insensitive)
        if original.lower() == result.canonical_name.lower():
            continue
        # Word-boundary replacement — preserves surrounding punctuation
        pattern = re.compile(r"\b" + re.escape(original) + r"\b", re.IGNORECASE)
        canonical_question = pattern.sub(result.canonical_name, canonical_question)
        canon_map[original] = result

    if canon_map:
        logger.info(
            "Canonicalised %d term(s): %s",
            len(canon_map),
            {k: v.canonical_name for k, v in canon_map.items()},
        )
    return canonical_question, canon_map


router = APIRouter(prefix="/chat", tags=["chat"])


# ── CTX benchmark endpoint ──

@router.post("/ctx-benchmark")
def ctx_benchmark(body: dict):
    """Run benchmark comparing CTX vs legacy context pipelines.

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

    build_args = dict(
        question=question,
        intent=intent,
        entity_info=entity_info,
        metrics=metrics,
        graph_summary=graph_summary,
        evidence_snippets=evidence,
    )

    ctx_result = CTXContextBuilder(mode="ctx").build(**build_args)
    legacy_result = CTXContextBuilder(mode="legacy").build(**build_args)

    token_savings_pct = 0.0
    if legacy_result.tokens > 0:
        token_savings_pct = round((1 - ctx_result.tokens / legacy_result.tokens) * 100, 1)

    return {
        "summary": {
            "ctx_tokens": ctx_result.tokens,
            "ctx_build_ms": round(ctx_result.build_time_ms, 2),
            "legacy_tokens": legacy_result.tokens,
            "legacy_build_ms": round(legacy_result.build_time_ms, 2),
            "token_savings_pct": token_savings_pct,
        },
        "ctx": {
            "text": ctx_result.text,
            "tokens": ctx_result.tokens,
            "source_tokens": ctx_result.source_tokens,
            "compression_ratio": ctx_result.compression_ratio,
            "build_time_ms": round(ctx_result.build_time_ms, 2),
            "sections": ctx_result.sections,
        },
        "legacy": {
            "text": legacy_result.text,
            "tokens": legacy_result.tokens,
            "build_time_ms": round(legacy_result.build_time_ms, 2),
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
    t0 = time.monotonic()
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

    # SPEC_015 WS-1: canonicalise brand names before intent detection
    # so "Show pipeline for Ozempic" routes the same as "...for semaglutide"
    canonicalizer = get_entity_canonicalizer()
    resolved_question, canon_map = _canonicalize_question(resolved_question, canonicalizer)

    intent, params = detect_intent(resolved_question)
    if deep_research:
        intent, params = Intent.DEEP_RESEARCH, {}
    if team_eval:
        intent, params = Intent.TEAM_EVAL, {}
    logger.info("Chat intent: %s, params: %s", intent, params)

    # SPEC-011: Unified handler (CTX pipeline) — A/B routed by session
    use_unified = _should_use_unified_handler(session_id)
    if use_unified:
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
                    payload["metadata"] = {**payload.get("metadata", {}), "handler": "unified"}
                    _log_chat_routing("unified", session_id, str(intent.value if hasattr(intent, "value") else intent))
                    memory.add_exchange(question, payload.get("narrative", ""))
                    save_conversation_memory(session_id, memory, db)
                    return payload
            except Exception as e:
                logger.warning("Unified handler error, falling back to legacy: %s", e)
                _log_chat_routing(
                    "unified", session_id,
                    str(intent.value if hasattr(intent, "value") else intent),
                    fallback=True, error=str(e),
                )

    # Compound intent detection: "Show Pfizer portfolio and compare their top 3 drugs"
    if intent not in (Intent.DEEP_RESEARCH, Intent.TEAM_EVAL):
        compound = detect_compound_intent(resolved_question)
        if len(compound) > 1:
            try:
                logger.info("Compound intents detected: %s", [c[0] for c in compound])
                payload = handle_compound(
                    compound,
                    question=resolved_question,
                    db=db,
                    engine=engine,
                    metrics_svc=metrics_svc,
                    llm=llm,
                    conv_context=conv_context,
                )
                payload = apply_chat_modes(payload, include_graph, include_metrics, source_strict)
                payload["visualizations"] = build_visualizations(payload.get("data"))
                payload["followup_suggestions"] = generate_followups(
                    question, payload.get("intent", "general"), payload.get("narrative", ""), {},
                )
                memory.add_exchange(question, payload.get("narrative", ""))
                save_conversation_memory(session_id, memory, db)
                return payload
            except Exception as e:
                logger.warning("Compound handler error, falling back to single intent: %s", e)

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
            # SPEC_016 Phase 3.5: pass canonicalizer so handler can classify
            # the entity_name as drug (use drug_id) vs therapeutic_area.
            payload = handle_pipeline(
                params, metrics_svc, llm,
                conv_context=conv_context,
                canonicalizer=canonicalizer,
            )

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
        # SPEC-011: tag handler attribution for A/B comparison
        payload["metadata"] = {**payload.get("metadata", {}), "handler": "legacy"}
        _log_chat_routing("legacy", session_id, str(intent.value if hasattr(intent, "value") else intent))
        memory.add_exchange(question, payload.get("narrative", ""))
        save_conversation_memory(session_id, memory, db)

        # Fire-and-forget query telemetry for Data Steward signal collection
        try:
            from services.telemetry import log_query_event, detect_query_gap
            latency_ms = (time.monotonic() - t0) * 1000
            data = payload.get("data") or {}
            entity_focus = data.get("entity_focus") or []
            ents_requested = [e.get("label", "") for e in entity_focus if e.get("label")]
            ents_found = [e.get("label", "") for e in entity_focus if e.get("id")]
            ev_count = len(data.get("evidence") or [])
            sources = list((data.get("provenance_summary") or {}).get("by_source", {}).keys())
            conf = payload.get("confidence")
            gap_type, gap_details = detect_query_gap(ents_requested, ents_found, ev_count, conf)
            log_query_event(
                db=db, session_id=session_id, question=question, intent=intent,
                entities_requested=ents_requested or None,
                entities_found=ents_found or None,
                confidence=conf, evidence_count=ev_count,
                sources_used=sources or None,
                response_latency_ms=round(latency_ms, 1),
                gap_type=gap_type, gap_details=gap_details,
            )
        except Exception:
            pass  # telemetry must never break chat

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
    canonicalizer = Depends(get_entity_canonicalizer),
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
                payload = handle_pipeline(
                    params, metrics_svc, llm,
                    canonicalizer=canonicalizer,
                )
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
