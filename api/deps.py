"""Dependency injection for the Market-Zero API.

Provides singleton service instances via FastAPI's dependency system.
All services share a single database connection and config.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Optional

from db import Database
from config import config
from services.search import HybridSearch
from services.graph import GraphTraversal
from services.graph_analytics import GraphAnalytics
from services.metrics import PharmaMetrics
from services.query_engine import QueryEngine
from services.llm import LLMSynthesizer
from services.web_research import WebResearchService
from services.conversation_memory import ConversationMemory
from services.workspace import ChatWorkspaceService

logger = logging.getLogger(__name__)


# ── Per-session conversation memory (cached in-memory, persisted to DB) ──

_memory_store: dict[str, ConversationMemory] = {}


def get_conversation_memory(session_id: str = "default") -> ConversationMemory:
    """Get or create a ConversationMemory for the given session.

    On first access, attempts to restore from the conversation_snapshots
    table. Falls back to a fresh memory if the table doesn't exist or the
    session has no saved state.
    """
    if session_id not in _memory_store:
        mem = ConversationMemory(token_budget=4000)
        # Try to restore from DB
        try:
            import json as _json
            db = get_db()
            row = db.fetch_one(
                "SELECT snapshot FROM conversation_snapshots WHERE session_id = %s",
                [session_id],
            )
            if row and row.get("snapshot"):
                data = row["snapshot"]
                # JSONB columns come back as dict; snapshot() returns a JSON string
                snapshot_str = _json.dumps(data) if isinstance(data, dict) else data
                mem.restore(snapshot_str)
                logger.debug("Restored conversation memory for session %s", session_id)
        except Exception:
            pass  # Fresh memory is fine (table may not exist yet)
        _memory_store[session_id] = mem
    return _memory_store[session_id]


def save_conversation_memory(session_id: str, memory: ConversationMemory, db: Database) -> None:
    """Persist memory snapshot to PostgreSQL.

    Uses INSERT ... ON CONFLICT to upsert the snapshot. Failures are
    logged but never propagated so they cannot break the chat response.
    """
    try:
        import json as _json
        snapshot = _json.dumps(memory.snapshot())
        db.execute(
            """INSERT INTO conversation_snapshots (session_id, snapshot, updated_at)
               VALUES (%s, %s, NOW())
               ON CONFLICT (session_id)
               DO UPDATE SET snapshot = EXCLUDED.snapshot, updated_at = NOW()""",
            [session_id, snapshot],
        )
    except Exception as e:
        logger.warning("Failed to persist conversation memory: %s", e)


@lru_cache()
def get_db() -> Database:
    pool_size = int(os.environ.get("MZ_DB_POOL_SIZE", "5"))
    db = Database(config.db.dsn, pool_size=pool_size)
    db.connect()
    return db


@lru_cache()
def get_search() -> HybridSearch:
    return HybridSearch(get_db(), config)


@lru_cache()
def get_graph() -> GraphTraversal:
    return GraphTraversal(get_db(), config)


@lru_cache()
def get_graph_analytics() -> GraphAnalytics:
    return GraphAnalytics(get_db())


@lru_cache()
def get_metrics() -> PharmaMetrics:
    return PharmaMetrics(get_db(), config)


@lru_cache()
def get_query_engine() -> QueryEngine:
    return QueryEngine(
        get_db(), config,
        get_search(), get_graph(), get_metrics(),
    )


@lru_cache()
def get_llm() -> LLMSynthesizer:
    return LLMSynthesizer(config)


@lru_cache()
def get_web_research() -> WebResearchService:
    return WebResearchService(config)


@lru_cache()
def get_workspace() -> ChatWorkspaceService:
    return ChatWorkspaceService(get_db())


@lru_cache()
def get_fair_scorer():
    from services.fair_scorer import FAIRScorer
    return FAIRScorer(get_db())


@lru_cache()
def get_unified_handler():
    """Build unified handler with CTX pipeline. Returns None if unavailable."""
    try:
        from services.unified_handler import UnifiedChatHandler
        from services.ctx_corpus import PharmaCorpusBuilder
        import tempfile

        db = get_db()
        builder = PharmaCorpusBuilder(db)
        result = builder.pack(tempfile.mkdtemp())

        handler = UnifiedChatHandler(
            corpus_doc=result.document,
            l3_doc=result.l3_document,
            llm=get_llm(),
            metrics_svc=get_metrics(),
            db=db,
            engine=get_query_engine(),
        )
        logger.info("Unified handler initialized with %d entities", result.entity_count)
        return handler
    except Exception as e:
        logger.warning("Unified handler unavailable: %s", e)
        return None


# ── Agent graph factories ──

@lru_cache()
def _get_domain_pack():
    """Get the active domain pack (pharma by default)."""
    from domain.pharma.pack import get_pharma_pack
    return get_pharma_pack()


@lru_cache()
def _get_agent_tools():
    """Build shared agent tools."""
    from services.agent.schema_introspector import SchemaIntrospector
    from services.agent.tools.sql_tool import SQLQueryTool
    from services.agent.tools.rag_tool import RAGSearchTool
    from services.agent.tools.graph_tool import GraphSearchTool
    from services.agent.tools.metrics_tool import MetricsQueryTool

    pack = _get_domain_pack()
    db = get_db()
    introspector = SchemaIntrospector(pack, db)

    return {
        "sql_tool": SQLQueryTool(db, introspector.get_table_names(), max_rows=config.agent.max_sql_rows),
        "rag_tool": RAGSearchTool(get_search()),
        "graph_tool": GraphSearchTool(get_graph()),
        "metrics_tool": MetricsQueryTool(get_metrics()),
        "introspector": introspector,
    }


@lru_cache()
def get_query_graph() -> Optional[object]:
    """Build and cache the LangGraph query agent. Returns None if deps unavailable."""
    if not config.agent.enabled:
        return None
    try:
        from services.agent.llm_provider import get_agent_llm
        from services.agent.graphs.query_graph import build_query_graph

        llm = get_agent_llm(config)
        tools = _get_agent_tools()
        schema_text = tools["introspector"].get_schema_description()

        return build_query_graph(
            llm=llm,
            sql_tool=tools["sql_tool"],
            rag_tool=tools["rag_tool"],
            graph_tool=tools["graph_tool"],
            metrics_tool=tools["metrics_tool"],
            schema_text=schema_text,
        )
    except Exception as exc:
        logger.warning("Failed to build query graph: %s", exc)
        return None


@lru_cache()
def get_team_eval_graph() -> Optional[object]:
    """Build and cache the LangGraph team eval agent. Returns None if deps unavailable."""
    if not config.agent.enabled or not config.agent.team_eval_enabled:
        return None
    try:
        from services.agent.llm_provider import get_agent_llm
        from services.agent.graphs.team_eval_graph import build_team_eval_graph

        llm = get_agent_llm(config)
        tools = _get_agent_tools()
        pack = _get_domain_pack()

        # Convert AgentPersona dataclasses to dicts for the graph
        personas = {}
        for name, persona in pack.personas.items():
            personas[name] = {
                "display_name": persona.display_name,
                "system_prompt": persona.system_prompt,
                "focus": persona.focus,
                "tools": persona.tools,
            }

        schema_text = tools["introspector"].get_schema_description()

        return build_team_eval_graph(
            llm=llm,
            sql_tool=tools["sql_tool"],
            rag_tool=tools["rag_tool"],
            graph_tool=tools["graph_tool"],
            metrics_tool=tools["metrics_tool"],
            personas=personas,
            schema_text=schema_text,
        )
    except Exception as exc:
        logger.warning("Failed to build team eval graph: %s", exc)
        return None
