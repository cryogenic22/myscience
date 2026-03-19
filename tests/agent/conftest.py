"""Agent-specific pytest fixtures for team eval and query graph tests."""

from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock

from tests.conftest import (
    MockLLM,
    StubTool,
    ToolCallRecorder,
    make_rag_result,
    make_sql_result,
    make_graph_result,
    make_metrics_result,
    make_empty_result,
)
from services.agent.tools.base import ToolResult


# ── Persona configs ──

PERSONAS = {
    "clinical_researcher": {
        "display_name": "Clinical Researcher",
        "system_prompt": "You are a clinical researcher analyzing trial data.",
        "focus": "Clinical trial evidence and study design",
        "tools": ["rag", "graph"],
    },
    "market_analyst": {
        "display_name": "Market Analyst",
        "system_prompt": "You are a market analyst evaluating competitive positioning.",
        "focus": "Market dynamics, pipeline value, competitive landscape",
        "tools": ["sql", "metrics"],
    },
    "regulatory_expert": {
        "display_name": "Regulatory Expert",
        "system_prompt": "You are a regulatory expert assessing approval pathways.",
        "focus": "Regulatory strategy, trial phase progression, approval likelihood",
        "tools": ["sql", "rag"],
    },
    "data_scientist": {
        "display_name": "Data Scientist",
        "system_prompt": "You are a data scientist evaluating evidence quality.",
        "focus": "Data quality, evidence density, statistical rigor",
        "tools": ["sql", "metrics"],
    },
}

SCHEMA_TEXT = """Tables:
  - drugs (id uuid PK, generic_name text, brand_name text, company_id uuid, mechanism_id uuid)
  - clinical_trials (id text PK, title text, status text, phase text, drug_id uuid)
  - companies (id uuid PK, name text)
  - entity_links (id uuid PK, source_entity_id text, target_entity_id text, link_type text)
"""


# ── Fixture: populated stub tools ──

@pytest.fixture
def populated_rag_tool():
    """RAG tool that returns tirzepatide trial data."""
    results = {
        "search": make_rag_result([
            {
                "source": "clinical_trials_gov",
                "entity_type": "clinical_trial",
                "entity_id": "NCT06635057",
                "content": "NCT06635057: Tirzepatide Ramadan study, Phase 4, ACTIVE_NOT_RECRUITING",
                "relevance": 0.92,
                "provenance": {"source_api": "clinical_trials_gov"},
            },
            {
                "source": "pubmed",
                "entity_type": "literature",
                "entity_id": "lit-001",
                "content": "Rahman et al. 2026 - real-world study of 109 T2DM patients on tirzepatide during Ramadan",
                "relevance": 0.88,
                "provenance": {"source_api": "pubmed"},
            },
            {
                "source": "clinical_trials_gov",
                "entity_type": "clinical_trial",
                "entity_id": "NCT05678901",
                "content": "NCT05678901: Tirzepatide fasting glucose, Phase 3, COMPLETED",
                "relevance": 0.85,
                "provenance": {"source_api": "clinical_trials_gov"},
            },
        ]),
    }
    return StubTool("rag", results)


@pytest.fixture
def populated_sql_tool():
    """SQL tool that returns trial breakdown data."""
    results = {
        "query": make_sql_result([
            {"phase": "Phase 3", "count": 32, "status": "COMPLETED"},
            {"phase": "Phase 4", "count": 20, "status": "RECRUITING"},
            {"phase": "Phase 2", "count": 15, "status": "ACTIVE_NOT_RECRUITING"},
        ]),
    }
    return StubTool("sql", results)


@pytest.fixture
def populated_graph_tool():
    """Graph tool that returns entity neighborhood."""
    results = {
        "neighborhood": make_graph_result(
            nodes=[
                {"entity_id": "drug-tirz", "entity_type": "drug", "label": "tirzepatide"},
                {"entity_id": "comp-lilly", "entity_type": "company", "label": "Eli Lilly"},
                {"entity_id": "mech-glp1", "entity_type": "mechanism", "label": "GLP-1/GIP agonist"},
            ],
            edges=[
                {"source_id": "comp-lilly", "target_id": "drug-tirz", "link_type": "OWNS", "confidence": 1.0},
                {"source_id": "drug-tirz", "target_id": "mech-glp1", "link_type": "TARGETS_MECHANISM", "confidence": 1.0},
            ],
        ),
    }
    return StubTool("graph", results)


@pytest.fixture
def populated_metrics_tool():
    """Metrics tool that returns pipeline data."""
    results = {
        "pipeline": make_metrics_result([
            {"drug_name": "tirzepatide", "pipeline_score": 92.5, "total_trials": 110, "company": "Eli Lilly"},
            {"drug_name": "semaglutide", "pipeline_score": 95.0, "total_trials": 180, "company": "Novo Nordisk"},
        ]),
        "landscape": make_metrics_result([
            {"mechanism_name": "GLP-1 agonist", "drug_count": 12, "total_pipeline_score": 450.0},
        ]),
    }
    return StubTool("metrics", results)


def _persona_llm_response(messages):
    """Generate a valid persona JSON response based on prompt context."""
    system_content = messages[0].content if messages else ""
    # Check if there's evidence in the prompt
    has_evidence = "DATABASE EVIDENCE" in system_content or "Evidence" in system_content

    if has_evidence:
        return json.dumps({
            "analysis": "Based on database evidence, tirzepatide shows strong clinical trial activity [1]. Multiple Phase 3 and Phase 4 trials are active [2].",
            "confidence": "high",
            "key_findings": [
                "110 tirzepatide clinical trials identified in database [1]",
                "Phase 4 Ramadan fasting study active (NCT06635057) [2]",
                "Real-world evidence from PubMed supports efficacy [3]",
            ],
            "data_gaps": [
                "Limited long-term fasting outcome data",
            ],
        })
    else:
        return json.dumps({
            "analysis": "No data found in database for this query.",
            "confidence": "low",
            "key_findings": [],
            "data_gaps": ["No database evidence available"],
        })


@pytest.fixture
def persona_llm():
    """LLM that returns grounded persona responses."""
    return MockLLM(response_fn=_persona_llm_response)


def _entity_extraction_response(messages):
    """Generate entity extraction result."""
    question = ""
    for msg in messages:
        content = getattr(msg, "content", "")
        if "tirzepatide" in content.lower() or "mounjaro" in content.lower():
            return json.dumps({
                "drugs": ["tirzepatide", "mounjaro"],
                "conditions": ["fasting", "ramadan", "low glucose"],
                "companies": ["Eli Lilly"],
                "mechanisms": ["GLP-1/GIP agonist"],
            })
        if "glp-1" in content.lower() or "glp1" in content.lower():
            return json.dumps({
                "drugs": ["semaglutide", "tirzepatide", "liraglutide"],
                "conditions": ["diabetes", "obesity"],
                "companies": ["Novo Nordisk", "Eli Lilly"],
                "mechanisms": ["GLP-1 agonist"],
            })
    return json.dumps({
        "drugs": [],
        "conditions": [],
        "companies": [],
        "mechanisms": [],
    })


def _routing_response(messages):
    """Generate persona routing result."""
    return "clinical_researcher, market_analyst, regulatory_expert"


def _synthesis_response(messages):
    """Generate synthesis result."""
    return (
        "Based on specialist analyses, tirzepatide shows strong clinical evidence "
        "with 110 trials in the database [1]. The Phase 4 Ramadan fasting study "
        "(NCT06635057) directly addresses glucose management during fasting [2]. "
        "Market positioning is strong with a pipeline score of 92.5 [3]."
    )


def _sql_planning_response(messages):
    """Generate SQL planning result."""
    return json.dumps([
        {
            "sql": "SELECT phase, COUNT(*) as count FROM clinical_trials WHERE drug_id IN (SELECT id FROM drugs WHERE generic_name = 'tirzepatide') GROUP BY phase",
            "label": "Trial phase breakdown for tirzepatide",
        }
    ])


@pytest.fixture
def smart_llm():
    """LLM that responds contextually based on message content."""
    call_count = [0]

    def response_fn(messages):
        call_count[0] += 1
        system = messages[0].content if messages else ""
        human = messages[-1].content if len(messages) > 1 else ""

        # Entity extraction
        if "extract" in system.lower() and "entities" in system.lower():
            return _entity_extraction_response(messages)

        # Routing
        if "routing" in system.lower() or "select the" in system.lower():
            return _routing_response(messages)

        # SQL planning
        if "sql" in system.lower() and "generate" in system.lower():
            return _sql_planning_response(messages)

        # Synthesis
        if "synthesize" in system.lower() or "lead" in system.lower():
            return _synthesis_response(messages)

        # Persona analysis (default)
        return _persona_llm_response(messages)

    return MockLLM(response_fn=response_fn)


@pytest.fixture
def personas():
    return PERSONAS.copy()


@pytest.fixture
def schema_text():
    return SCHEMA_TEXT
