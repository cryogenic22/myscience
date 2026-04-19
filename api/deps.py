"""Dependency injection for the Market-Zero API.

Provides singleton service instances via FastAPI's dependency system.
All services share a single database connection and config.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Optional

from fastapi import Depends, Header, HTTPException

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
from services.concept_registry import ConceptRegistry

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
def get_entity_canonicalizer():
    """Build and cache the EntityCanonicalizer singleton (SPEC_015 WS-1)."""
    from services.entity_canonicalizer import EntityCanonicalizer
    return EntityCanonicalizer(get_db())


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
def get_concept_registry() -> ConceptRegistry:
    """Build and cache a DB-backed ConceptRegistry singleton.

    Loads concepts from the ``concepts`` table on first access.
    Falls back to hardcoded pharma concepts if the table doesn't exist.
    """
    return ConceptRegistry(db=get_db())


# ── Agent Harness (Task 1A + 1B) ──

# Executor factories — thin wrappers that delegate to existing services.
# Each returns a callable (args: dict) -> dict suitable for
# MarketZeroHarness.register_executor().

def _make_steward_curate_executor(db):
    """Delegate to DataSteward.run_loop()."""
    def executor(args: dict) -> dict:
        from services.steward_signals import StewardSignalCollector
        from services.data_steward import DataSteward, StewardConfig

        collector = StewardSignalCollector(db)
        steward_cfg = StewardConfig(
            max_iterations=args.get("max_iterations", 20),
            skip_ai=args.get("skip_ai", True),
        )
        steward = DataSteward(db, collector, steward_cfg)
        summary = steward.run_loop()
        return {
            "completed": summary.completed,
            "failed": summary.failed,
            "iterations": summary.iterations,
            "feedback_resolved": summary.feedback_resolved,
            "elapsed_s": summary.total_elapsed_s,
        }
    return executor


def _make_mv_refresh_executor(db):
    """Refresh all materialized views via PharmaMetrics.refresh()."""
    def executor(args: dict) -> dict:
        try:
            metrics = PharmaMetrics(db, config)
            result = metrics.refresh()
            return {"refreshed": True, "views": result}
        except Exception as e:
            return {"refreshed": True, "error": str(e)}
    return executor


def _make_fair_score_executor(db):
    """Delegate to FAIRScorer.compute()."""
    def executor(args: dict) -> dict:
        from services.fair_scorer import FAIRScorer

        scorer = FAIRScorer(db)
        result = scorer.compute()
        return {"overall": result.overall}
    return executor


def _make_entity_influence_executor(db):
    """Delegate to GraphAnalytics.entity_influence()."""
    def executor(args: dict) -> dict:
        from services.graph_analytics import GraphAnalytics

        ga = GraphAnalytics(db)
        return ga.entity_influence(
            entity_id=args.get("entity_id", ""),
            entity_type=args.get("entity_type", ""),
        )
    return executor


def _make_competitive_clusters_executor(db):
    """Delegate to GraphAnalytics.competitive_clusters()."""
    def executor(args: dict) -> dict:
        from services.graph_analytics import GraphAnalytics

        ga = GraphAnalytics(db)
        clusters = ga.competitive_clusters(
            therapeutic_area=args.get("therapeutic_area", ""),
        )
        return {"clusters": clusters}
    return executor


def _make_entity_exclude_executor(db):
    """Mark an entity as excluded via direct SQL."""
    def executor(args: dict) -> dict:
        entity_id = args.get("entity_id")
        entity_type = args.get("entity_type", "drug")
        table_map = {
            "drug": "drugs",
            "company": "companies",
            "trial": "clinical_trials",
            "literature": "pubmed_articles",
            "event": "market_events",
        }
        table = table_map.get(entity_type)
        if table:
            db.execute(
                f"UPDATE {table} SET record_status = 'excluded' WHERE id = %s",
                [entity_id],
            )
        return {"excluded": True, "entity_id": entity_id}
    return executor


@lru_cache()
def get_harness():
    """Build and cache the MarketZeroHarness singleton with registered executors.

    Uses the same @lru_cache pattern as get_db(), get_search(), etc.
    Tool executors are thin wrappers that delegate to existing services.
    """
    from services.agent.harness import MarketZeroHarness, HarnessConfig
    from services.agent.permissions import SessionMode

    db = get_db()
    harness = MarketZeroHarness(
        db=db,
        config=HarnessConfig(session_mode=SessionMode.AUTONOMOUS),
    )

    # Register executors for all tools that have backing services
    harness.register_executor("steward_curate", _make_steward_curate_executor(db))
    harness.register_executor("mv_refresh", _make_mv_refresh_executor(db))
    harness.register_executor("fair_score", _make_fair_score_executor(db))
    harness.register_executor("entity_influence", _make_entity_influence_executor(db))
    harness.register_executor("competitive_clusters", _make_competitive_clusters_executor(db))
    harness.register_executor("entity_exclude", _make_entity_exclude_executor(db))

    logger.info(
        "Agent harness initialized with %d executors, %d tools in registry",
        len(harness._tool_executors),
        harness.registry.count(),
    )
    return harness


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


# ── SPEC_018: Auth dependencies ────────────────────────────────────

def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Database = Depends(get_db),
) -> Optional[dict]:
    """Resolve current user from Bearer token. Returns None for anonymous.

    Returns the DB user row (id, email, role) when token is valid AND user is
    active. Returns None when:
      - No Authorization header (anonymous)
      - Header is malformed
      - Token is invalid / expired / signed with wrong secret
      - User row missing or inactive

    Returning None instead of raising lets routes opt into "anonymous OK"
    behavior. Routes that REQUIRE auth use require_role() instead.
    """
    from services.auth import AuthError, decode_token

    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1]
    try:
        payload = decode_token(token)
    except AuthError:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    try:
        row = db.fetch_one(
            "SELECT id::text AS id, email, role, is_active "
            "FROM users WHERE id::text = %s LIMIT 1",
            [user_id],
        )
    except Exception:
        # DB unavailable — treat as anonymous rather than 500
        logger.exception("get_current_user: DB lookup failed")
        return None

    if not row or not row.get("is_active"):
        return None
    return row


def require_role(min_role: str):
    """Build a FastAPI dependency that enforces a minimum role.

    - 401 if anonymous (no valid token)
    - 403 if authenticated but role insufficient
    - returns the user dict otherwise

    Usage:
        @router.post("/upload", dependencies=[Depends(require_role("uploader"))])
        def upload(...): ...
    """
    from services.auth import role_satisfies

    def _dep(user: Optional[dict] = Depends(get_current_user)) -> dict:
        if user is None:
            raise HTTPException(status_code=401, detail="authentication required")
        if not role_satisfies(user.get("role"), min_role):
            raise HTTPException(
                status_code=403,
                detail=f"role '{user.get('role')}' insufficient (need '{min_role}' or higher)",
            )
        return user

    return _dep
