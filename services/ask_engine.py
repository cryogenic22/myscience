"""SPEC_035 — /ask graph-traversal engine.

NL question → matched pattern → parameterized SQL → graph-shaped result.

This is intentionally pattern-matching (not LLM); each pattern has a
named regex group → SQL template binding so user input is never inlined
into SQL. LLM-fallback parsing is a follow-up via SPEC-026 LLMGateway.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
# Constants
# ────────────────────────────────────────────────────────────────────

MAX_QUESTION_CHARS = 500
MAX_NODES = 200
MAX_HISTORY = 50
MAX_GRAPH_DEPTH = 3


# ────────────────────────────────────────────────────────────────────
# Patterns — order matters; first match wins
# ────────────────────────────────────────────────────────────────────

# Each pattern has:
#   id, regex, intent builder, executor name
# Executors are methods on AskEngine.

_PATTERNS: list[dict] = [
    {
        "id": "P1",
        "regex": re.compile(
            r"^\s*(show me|list|find)\s+(?P<entity_type>drug|company|trial|indication|mechanism|therapeutic_area)s?\s+in\s+(?P<area>[\w\s\-/]+?)\s*\??\s*$",
            re.IGNORECASE,
        ),
        "executor": "filter_entities_by_area",
        "example": "Show me drugs in oncology",
    },
    {
        "id": "P2",
        "regex": re.compile(
            r"^\s*what\s+(?P<relation>trials|competitors|sponsors|drugs|companies|mechanisms|indications)\s+does\s+(?P<entity_name>[\w\s\-]+?)\s+have\s*\??\s*$",
            re.IGNORECASE,
        ),
        "executor": "linked_entities",
        "example": "What trials does Tirzepatide have?",
    },
    {
        "id": "P3",
        "regex": re.compile(
            r"^\s*(competitors|rivals)\s+(of|to)\s+(?P<company_name>[\w\s\-\.&]+?)\s*\??\s*$",
            re.IGNORECASE,
        ),
        "executor": "competitors_of",
        "example": "Competitors of Pfizer",
    },
    {
        "id": "P4",
        "regex": re.compile(
            r"^\s*(?P<entity_type>drug|trial|approval|signal)s?\s+(approved|added|filed|recorded)\s+(in\s+)?(the\s+)?last\s+(?P<n>\d{1,4})\s+(?P<unit>day|week|month|year)s?\s*\??\s*$",
            re.IGNORECASE,
        ),
        "executor": "recent_entities",
        "example": "Drugs approved in the last 30 days",
    },
    {
        "id": "P5",
        "regex": re.compile(
            r"^\s*(find|show me|list)\s+(?P<entity_type>drug|trial)s?\s+targeting\s+(?P<mechanism_name>[\w\s\-\(\)\,]+?)\s*\??\s*$",
            re.IGNORECASE,
        ),
        "executor": "entities_by_mechanism",
        "example": "Find drugs targeting GLP-1 receptor",
    },
    {
        "id": "P6",
        "regex": re.compile(
            r"^\s*who\s+sponsors\s+(?P<drug_name>[\w\s\-]+?)\s*\??\s*$",
            re.IGNORECASE,
        ),
        "executor": "sponsor_of_drug",
        "example": "Who sponsors Tirzepatide?",
    },
]


def list_templates() -> list[dict]:
    """Public list of recognized patterns + example questions for the
    Ask-Anything UI to render as suggestions."""
    return [
        {"id": p["id"], "example": p["example"], "executor": p["executor"]}
        for p in _PATTERNS
    ]


# ────────────────────────────────────────────────────────────────────
# Domain dataclasses
# ────────────────────────────────────────────────────────────────────

@dataclass
class GraphNode:
    id: str
    type: str
    label: str
    props: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"id": str(self.id), "type": self.type, "label": self.label, "props": self.props}


@dataclass
class GraphEdge:
    source: str
    target: str
    type: str
    props: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"source": str(self.source), "target": str(self.target),
                "type": self.type, "props": self.props}


@dataclass
class GraphResult:
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }


@dataclass
class ParsedIntent:
    matched_pattern: Optional[str]   # P1..P6 or None
    executor: Optional[str]
    params: dict = field(default_factory=dict)
    raw_question: str = ""

    def to_dict(self) -> dict:
        return {
            "matched_pattern": self.matched_pattern,
            "executor": self.executor,
            "params": self.params,
            "raw_question": self.raw_question,
        }


@dataclass
class AskResult:
    question: str
    matched_pattern: Optional[str]
    intent: ParsedIntent
    graph: GraphResult
    status: str  # 'ok' | 'unmatched' | 'failed'
    latency_ms: int
    executed_sql_summary: Optional[str] = None
    suggested_templates: Optional[list[dict]] = None
    error_message: Optional[str] = None
    ask_query_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "matched_pattern": self.matched_pattern,
            "intent": self.intent.to_dict(),
            "graph": self.graph.to_dict(),
            "result_count": {"nodes": len(self.graph.nodes), "edges": len(self.graph.edges)},
            "status": self.status,
            "latency_ms": self.latency_ms,
            "executed_sql_summary": self.executed_sql_summary,
            "suggested_templates": self.suggested_templates,
            "error_message": self.error_message,
            "ask_query_id": str(self.ask_query_id) if self.ask_query_id else None,
        }


# ────────────────────────────────────────────────────────────────────
# Parser (pattern-only; LLM-fallback is a follow-up)
# ────────────────────────────────────────────────────────────────────

def parse_question(question: str) -> ParsedIntent:
    if not question or not question.strip():
        return ParsedIntent(matched_pattern=None, executor=None, raw_question="")
    q = question.strip()
    if len(q) > MAX_QUESTION_CHARS:
        q = q[:MAX_QUESTION_CHARS]

    for p in _PATTERNS:
        m = p["regex"].match(q)
        if m:
            params = {k: v.strip() for k, v in m.groupdict().items() if v}
            # Normalize keys that gate executor logic (entity_type, relation,
            # unit) to lowercase so case-variant questions don't behave
            # differently. Entity name fields preserve case for display.
            for case_key in ("entity_type", "relation", "unit"):
                if case_key in params:
                    params[case_key] = params[case_key].lower()
            return ParsedIntent(
                matched_pattern=p["id"],
                executor=p["executor"],
                params=params,
                raw_question=q,
            )
    return ParsedIntent(matched_pattern=None, executor=None,
                        params={}, raw_question=q)


# ────────────────────────────────────────────────────────────────────
# Engine — executes parsed intents
# ────────────────────────────────────────────────────────────────────

class AskEngine:

    def ask(
        self,
        db,
        *,
        question: str,
        user_id: Optional[str] = None,
        persist: bool = True,
    ) -> AskResult:
        if not question or not question.strip():
            raise ValueError("question required")
        if len(question) > MAX_QUESTION_CHARS:
            raise ValueError(f"question exceeds {MAX_QUESTION_CHARS} chars")

        t0 = time.perf_counter()
        intent = parse_question(question)
        graph = GraphResult()
        status = "ok"
        sql_summary = None
        error = None
        suggestions = None

        if intent.executor is None:
            status = "unmatched"
            suggestions = list_templates()[:5]
        else:
            try:
                executor = getattr(self, f"_exec_{intent.executor}", None)
                if executor is None:
                    raise RuntimeError(f"executor not found: {intent.executor}")
                graph, sql_summary = executor(db, intent.params)
                # Bound result size
                if len(graph.nodes) > MAX_NODES:
                    graph.nodes = graph.nodes[:MAX_NODES]
                # Drop edges referencing nodes we trimmed
                kept_ids = {n.id for n in graph.nodes}
                graph.edges = [e for e in graph.edges if e.source in kept_ids and e.target in kept_ids]
            except Exception as exc:
                logger.exception("ask executor failed: %s", exc)
                status = "failed"
                error = str(exc)[:500]

        elapsed = int((time.perf_counter() - t0) * 1000)
        result = AskResult(
            question=question.strip(),
            matched_pattern=intent.matched_pattern,
            intent=intent,
            graph=graph,
            status=status,
            latency_ms=elapsed,
            executed_sql_summary=sql_summary,
            suggested_templates=suggestions,
            error_message=error,
        )

        if persist:
            try:
                row = db.fetch_one(
                    """
                    INSERT INTO ask_query_log (
                        question, matched_pattern, intent_jsonb,
                        result_node_count, result_edge_count, latency_ms,
                        succeeded, error_message, user_id
                    ) VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s)
                    RETURNING ask_query_id
                    """,
                    (
                        result.question, result.matched_pattern,
                        json.dumps(intent.to_dict()),
                        len(graph.nodes), len(graph.edges), elapsed,
                        status == "ok", error, user_id,
                    ),
                )
                if row:
                    result.ask_query_id = str(row["ask_query_id"])
            except Exception as exc:
                logger.warning("ask_query_log insert failed: %s", exc)

        return result

    # ── Executors (all parameterized; user input never inlined) ──

    def _exec_filter_entities_by_area(self, db, params: dict) -> tuple[GraphResult, str]:
        entity_type = self._safe_entity_type(params.get("entity_type"))
        area = (params.get("area") or "").strip()
        # Entity-table names match the `entity_type` enum; whitelisted via _safe_entity_type
        rows = db.fetch_all(
            f"""
            SELECT e.id, e.name
              FROM {entity_type}s e
         LEFT JOIN therapeutic_areas ta ON ta.id = e.therapeutic_area_id
             WHERE LOWER(ta.name) ILIKE %s
                OR LOWER(ta.id::text) = LOWER(%s)
             LIMIT %s
            """,
            (f"%{area.lower()}%", area, MAX_NODES),
        ) or []
        graph = GraphResult()
        for r in rows:
            graph.nodes.append(GraphNode(id=str(r["id"]), type=entity_type,
                                          label=r.get("name") or str(r["id"])))
            graph.edges.append(GraphEdge(source=str(r["id"]),
                                          target=f"ta:{area}",
                                          type="in_area"))
        graph.nodes.append(GraphNode(id=f"ta:{area}", type="therapeutic_area",
                                      label=area))
        return graph, f"SELECT FROM {entity_type}s JOIN therapeutic_areas WHERE name ILIKE '%{area}%'"

    def _exec_linked_entities(self, db, params: dict) -> tuple[GraphResult, str]:
        relation = (params.get("relation") or "").lower().strip()
        entity_name = (params.get("entity_name") or "").strip()
        # Map the natural-language relation to a target entity type
        relation_to_target = {
            "trials": "trial", "competitors": "company",
            "sponsors": "company", "drugs": "drug",
            "companies": "company", "mechanisms": "mechanism",
            "indications": "indication",
        }
        target_type = relation_to_target.get(relation, "entity")

        rows = db.fetch_all(
            """
            SELECT el.from_entity_id, el.from_entity_type,
                   el.to_entity_id, el.to_entity_type, el.link_type
              FROM entity_links el
              JOIN entities e ON e.id = el.from_entity_id
             WHERE LOWER(e.name) ILIKE %s
               AND el.to_entity_type = %s
             LIMIT %s
            """,
            (f"%{entity_name.lower()}%", target_type, MAX_NODES),
        ) or []
        graph = GraphResult()
        seen_nodes: set[str] = set()
        for r in rows:
            from_id = str(r["from_entity_id"])
            to_id = str(r["to_entity_id"])
            if from_id not in seen_nodes:
                graph.nodes.append(GraphNode(id=from_id, type=r["from_entity_type"],
                                              label=entity_name))
                seen_nodes.add(from_id)
            if to_id not in seen_nodes:
                graph.nodes.append(GraphNode(id=to_id, type=r["to_entity_type"],
                                              label=to_id))
                seen_nodes.add(to_id)
            graph.edges.append(GraphEdge(source=from_id, target=to_id,
                                          type=r["link_type"]))
        return graph, f"SELECT FROM entity_links WHERE from~ILIKE '%{entity_name}%' AND to_type='{target_type}'"

    def _exec_competitors_of(self, db, params: dict) -> tuple[GraphResult, str]:
        company_name = (params.get("company_name") or "").strip()
        rows = db.fetch_all(
            """
            SELECT el.from_entity_id, el.to_entity_id,
                   c1.name AS from_name, c2.name AS to_name
              FROM entity_links el
              JOIN companies c1 ON c1.id = el.from_entity_id
              JOIN companies c2 ON c2.id = el.to_entity_id
             WHERE el.link_type = 'COMPETES_WITH'
               AND LOWER(c1.name) ILIKE %s
             LIMIT %s
            """,
            (f"%{company_name.lower()}%", MAX_NODES),
        ) or []
        graph = GraphResult()
        seen: set[str] = set()
        for r in rows:
            from_id = str(r["from_entity_id"])
            to_id = str(r["to_entity_id"])
            if from_id not in seen:
                graph.nodes.append(GraphNode(id=from_id, type="company",
                                              label=r.get("from_name") or from_id))
                seen.add(from_id)
            if to_id not in seen:
                graph.nodes.append(GraphNode(id=to_id, type="company",
                                              label=r.get("to_name") or to_id))
                seen.add(to_id)
            graph.edges.append(GraphEdge(source=from_id, target=to_id,
                                          type="COMPETES_WITH"))
        return graph, f"SELECT competitors of '{company_name}'"

    def _exec_recent_entities(self, db, params: dict) -> tuple[GraphResult, str]:
        entity_type = self._safe_entity_type(params.get("entity_type"))
        n = int(params.get("n", 30))
        unit = (params.get("unit") or "day").lower()
        unit_days = {"day": 1, "week": 7, "month": 30, "year": 365}.get(unit, 1)
        days = n * unit_days
        time_col = "approval_date" if entity_type == "drug" else "created_at"
        rows = db.fetch_all(
            f"""
            SELECT id, name, {time_col} AS event_at
              FROM {entity_type}s
             WHERE {time_col} > NOW() - (%s || ' days')::interval
             ORDER BY {time_col} DESC
             LIMIT %s
            """,
            (days, MAX_NODES),
        ) or []
        graph = GraphResult()
        for r in rows:
            graph.nodes.append(GraphNode(
                id=str(r["id"]), type=entity_type,
                label=r.get("name") or str(r["id"]),
                props={"event_at": r["event_at"].isoformat()
                       if hasattr(r.get("event_at"), "isoformat") else None},
            ))
        return graph, f"SELECT recent {entity_type}s past {days} days"

    def _exec_entities_by_mechanism(self, db, params: dict) -> tuple[GraphResult, str]:
        entity_type = self._safe_entity_type(params.get("entity_type"))
        mechanism_name = (params.get("mechanism_name") or "").strip()
        # Look up mechanism, then entities linked to it
        rows = db.fetch_all(
            f"""
            SELECT e.id, e.name, m.id AS mechanism_id, m.name AS mechanism_name
              FROM {entity_type}s e
              JOIN mechanisms m ON m.id = e.mechanism_id
             WHERE LOWER(m.name) ILIKE %s
             LIMIT %s
            """,
            (f"%{mechanism_name.lower()}%", MAX_NODES),
        ) or []
        graph = GraphResult()
        seen_mechs: set[str] = set()
        for r in rows:
            graph.nodes.append(GraphNode(id=str(r["id"]), type=entity_type,
                                          label=r.get("name") or str(r["id"])))
            mid = str(r["mechanism_id"])
            if mid not in seen_mechs:
                graph.nodes.append(GraphNode(id=mid, type="mechanism",
                                              label=r.get("mechanism_name") or mid))
                seen_mechs.add(mid)
            graph.edges.append(GraphEdge(source=str(r["id"]), target=mid,
                                          type="targets"))
        return graph, f"SELECT {entity_type}s targeting mechanism '%{mechanism_name}%'"

    def _exec_sponsor_of_drug(self, db, params: dict) -> tuple[GraphResult, str]:
        drug_name = (params.get("drug_name") or "").strip()
        rows = db.fetch_all(
            """
            SELECT d.id AS drug_id, d.name AS drug_name,
                   c.id AS company_id, c.name AS company_name
              FROM drugs d
              JOIN companies c ON c.id = d.company_id
             WHERE LOWER(d.name) ILIKE %s
             LIMIT %s
            """,
            (f"%{drug_name.lower()}%", MAX_NODES),
        ) or []
        graph = GraphResult()
        seen: set[str] = set()
        for r in rows:
            d_id = str(r["drug_id"])
            c_id = str(r["company_id"])
            if d_id not in seen:
                graph.nodes.append(GraphNode(id=d_id, type="drug",
                                              label=r.get("drug_name") or d_id))
                seen.add(d_id)
            if c_id not in seen:
                graph.nodes.append(GraphNode(id=c_id, type="company",
                                              label=r.get("company_name") or c_id))
                seen.add(c_id)
            graph.edges.append(GraphEdge(source=d_id, target=c_id,
                                          type="sponsored_by"))
        return graph, f"SELECT sponsor of '%{drug_name}%'"

    # ── Internal: whitelist entity_type to prevent SQL injection via table name ──

    _SAFE_ENTITY_TYPES = {"drug", "company", "trial", "indication",
                          "mechanism", "therapeutic_area", "approval", "signal"}

    def _safe_entity_type(self, t: Optional[str]) -> str:
        t = (t or "").lower().strip()
        if t in self._SAFE_ENTITY_TYPES:
            return t
        # Fallback to drug to prevent injection; service-level safe default
        return "drug"


# ────────────────────────────────────────────────────────────────────
# Read-side helpers (history)
# ────────────────────────────────────────────────────────────────────

def list_history(db, *, user_id: str, limit: int = 20) -> list[dict]:
    if limit < 1 or limit > MAX_HISTORY:
        raise ValueError(f"limit must be in [1, {MAX_HISTORY}]")
    rows = db.fetch_all(
        """
        SELECT ask_query_id, question, matched_pattern,
               result_node_count, result_edge_count, latency_ms,
               succeeded, created_at
          FROM ask_query_log
         WHERE user_id::text = %s
         ORDER BY created_at DESC
         LIMIT %s
        """,
        (str(user_id), limit),
    ) or []
    return [
        {
            "ask_query_id": str(r["ask_query_id"]),
            "question": r["question"],
            "matched_pattern": r.get("matched_pattern"),
            "result_node_count": int(r.get("result_node_count") or 0),
            "result_edge_count": int(r.get("result_edge_count") or 0),
            "latency_ms": int(r.get("latency_ms") or 0),
            "succeeded": bool(r.get("succeeded")),
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        }
        for r in rows
    ]
