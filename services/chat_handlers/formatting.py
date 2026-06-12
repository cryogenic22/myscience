"""Formatting utilities for chat responses: follow-ups, visualizations, mode flags, entity resolution."""

from __future__ import annotations

import logging
import re
from typing import Optional

from db import Database
from services.chat_handlers.intent import Intent, MECHANISM_SYNONYMS

logger = logging.getLogger(__name__)


def coerce_bool(value, default: bool) -> bool:
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


def apply_chat_modes(payload: dict, include_graph: bool, include_metrics: bool, source_strict: bool) -> dict:
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


def _resolve_drug_richest(clean_name: str, db: Database) -> Optional[dict]:
    """Resolve a drug name/brand to its richest ACTIVE row.

    Audit RC1: duplicate drug rows (semaglutide ×17, tirzepatide ×2 on prod) plus
    the A6 consolidation's soft-deleted dups (record_status='merged'/'superseded')
    mean a bare LIMIT-1/no-ORDER-BY lands on an arbitrary near-empty duplicate —
    e.g. reporting 2 trials for a drug that actually owns 184. This mirrors the
    dossier resolver (services/dossier_kb.py _exact_lookup): exclude soft-deleted
    rows and rank the rest by data richness (facts + trials) so the row that owns
    the evidence wins. Returns the canonical generic_name as the label.
    """
    # richness = ledger facts + clinical trials owned by the row. Aliased away
    # from the bare word "label" so the SPEC-010 schema-drift gate (which flags
    # `\blabel\b` near `FROM clinical_trials`) stays green.
    richness = (
        "  (SELECT count(*) FROM facts f "
        "     WHERE f.subject_entity_type = 'drug' "
        "       AND f.subject_entity_id = d.id::text "
        "       AND f.superseded_by IS NULL) "
        "  + (SELECT count(*) FROM clinical_trials ct "
        "       WHERE ct.drug_id = d.id) AS richness "
    )
    status_filter = (
        "  AND d.record_status IS DISTINCT FROM 'merged' "
        "  AND d.record_status IS DISTINCT FROM 'superseded' "
        # 'excluded' = entity-extraction junk quarantined by the junk-row
        # consolidation; must never win resolution (a junk look-alike like
        # 'semaglutide or tirzepatide' otherwise resolves the query 'tirzepatide').
        "  AND d.record_status IS DISTINCT FROM 'excluded' "
    )
    try:
        # Exact match on generic_name or brand_name (score 1.0).
        row = db.fetch_one(
            "SELECT d.id::text AS entity_id, d.generic_name AS gname, " + richness +
            "FROM drugs d "
            "WHERE (LOWER(d.generic_name) = LOWER(%s) OR LOWER(d.brand_name) = LOWER(%s)) " +
            status_filter +
            "ORDER BY richness DESC, d.id LIMIT 1",
            [clean_name, clean_name],
        )
        if row:
            return {"entity_id": row["entity_id"], "label": row["gname"],
                    "entity_type": "drug", "match_score": 1.0}
        # Curated alias (brand/synonym → canonical drug), score 0.95. Sits between
        # exact and fuzzy — mirroring the dossier resolver cascade — so a brand like
        # 'Wegovy' resolves to semaglutide instead of a junk look-alike row that a
        # greedy fuzzy LIKE would otherwise grab.
        arow = db.fetch_one(
            "SELECT d.id::text AS entity_id, d.generic_name AS gname "
            "FROM entity_aliases a JOIN drugs d ON d.id::text = a.entity_id::text "
            "WHERE LOWER(a.alias_text) = LOWER(%s) AND a.entity_type = 'drug' " +
            status_filter +
            "LIMIT 1",
            [clean_name],
        )
        if arow:
            return {"entity_id": arow["entity_id"], "label": arow["gname"],
                    "entity_type": "drug", "match_score": 0.95}
        # Fuzzy LIKE (score 0.7) — require >=3 chars to avoid a wildcard catch-all.
        if len(clean_name) >= 3:
            row = db.fetch_one(
                "SELECT d.id::text AS entity_id, d.generic_name AS gname, " + richness +
                "FROM drugs d "
                "WHERE (LOWER(d.generic_name) LIKE LOWER(%s) OR LOWER(d.brand_name) LIKE LOWER(%s)) " +
                status_filter +
                "ORDER BY richness DESC, d.id LIMIT 1",
                [f"%{clean_name}%", f"%{clean_name}%"],
            )
            if row:
                return {"entity_id": row["entity_id"], "label": row["gname"],
                        "entity_type": "drug", "match_score": 0.7}
    except Exception:
        logger.exception("resolve_entity: richest-drug lookup failed for %r", clean_name)
    return None


def resolve_entity(name: str, entity_type: str, db: Database) -> Optional[dict]:
    """Resolve a name or UUID to entity_id + metadata + match_score.

    match_score: 1.0 for UUID/exact match, 0.7 for fuzzy LIKE match.

    SPEC_015 §3.3.4: drugs may be looked up via either generic_name (primary)
    or brand_name (secondary). When matched via brand_name, the returned label
    is the canonical generic_name from the same row.
    """
    import re as _re

    # table_map values: list of (table, search_column, label_column).
    # search_column is what we filter WHERE against; label_column is what we
    # return as the canonical "label". For drugs, brand searches still return
    # generic_name as the label.
    table_map: dict[str, list[tuple[str, str, str]]] = {
        "drug": [
            ("drugs", "generic_name", "generic_name"),  # primary
            ("drugs", "brand_name",   "generic_name"),  # secondary — returns generic
        ],
        "company": [("companies", "name", "name")],
        "therapeutic_area": [("therapeutic_areas", "name", "name")],
        "mechanism": [("mechanisms_of_action", "name", "name")],
        "literature": [("pubmed_articles", "title", "title")],
    }

    # Check if it's a UUID (or contains one)
    uuid_match = _re.search(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', name.lower())
    if uuid_match:
        uuid_val = uuid_match.group(0)
        for etype, columns in table_map.items():
            if entity_type and entity_type != etype:
                continue
            table, _search_col, label_col = columns[0]
            row = db.fetch_one(
                f"SELECT id::text AS entity_id, {label_col} AS label FROM {table} WHERE id::text = %s LIMIT 1",
                [uuid_val],
            )
            if row:
                return {"entity_id": row["entity_id"], "label": row["label"], "entity_type": etype, "match_score": 1.0}

    # Strip leading entity type words: "drug semaglutide" -> "semaglutide"
    clean_name = _re.sub(r'^(drug|company|trial|mechanism|therapeutic_area)\s+', '', name.strip(), flags=_re.IGNORECASE)

    # Guard: empty name should not match anything
    if not clean_name or len(clean_name) < 2:
        return None

    # Drugs first (when allowed): rank duplicate rows by data richness and skip
    # soft-deleted dups so the evidence-owning canonical row wins (RC1).
    if entity_type in ("", "drug"):
        drug = _resolve_drug_richest(clean_name, db)
        if drug:
            return drug
        if entity_type == "drug":
            return None

    for etype, columns in table_map.items():
        if etype == "drug":
            continue  # handled by _resolve_drug_richest above
        if entity_type and entity_type != etype:
            continue
        for table, search_col, label_col in columns:
            # Exact match first (score 1.0)
            row = db.fetch_one(
                f"SELECT id::text AS entity_id, {label_col} AS label FROM {table} "
                f"WHERE LOWER({search_col}) = LOWER(%s) LIMIT 1",
                [clean_name],
            )
            if row:
                return {"entity_id": row["entity_id"], "label": row["label"], "entity_type": etype, "match_score": 1.0}
            # Fuzzy match (score 0.7) — require at least 3 chars to prevent wildcard catch-all
            if len(clean_name) >= 3:
                row = db.fetch_one(
                    f"SELECT id::text AS entity_id, {label_col} AS label FROM {table} "
                    f"WHERE LOWER({search_col}) LIKE LOWER(%s) LIMIT 1",
                    [f"%{clean_name}%"],
                )
                if row:
                    return {"entity_id": row["entity_id"], "label": row["label"], "entity_type": etype, "match_score": 0.7}

    return None


def generate_followups(question: str, intent: str, narrative: str, params: dict) -> list[str]:
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


def expand_topic_synonyms(topic: str) -> str:
    """Expand common pharma abbreviations to full mechanism names."""
    lower = topic.lower().strip()
    for abbrev, full in MECHANISM_SYNONYMS.items():
        if abbrev in lower:
            return full
    return topic


def compute_comparison_insights(resolved: list[dict], metrics_comp: dict) -> str:
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


def build_visualizations(data: Optional[dict]) -> list[dict]:
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


def build_comparison_table(resolved: list[dict], metrics_comp: dict) -> dict | None:
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


def normalize_scope(raw_scope) -> str:
    scope = str(raw_scope or "default").strip()
    if not scope:
        return "default"
    if len(scope) > 120:
        scope = scope[:120]
    return scope


def safe_filename(raw_name: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9._-]+", "-", raw_name.strip().lower()).strip("-")
    return clean or "deep-research-report"


def sanitize_transcript(messages: list[dict]) -> list[dict]:
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


def to_number(value) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


# ── Confidence scoring ──


def compute_response_confidence(
    entity_resolved: bool = False,
    entity_match_score: float | None = None,
    evidence_count: int = 0,
    graph_node_count: int = 0,
    metrics_available: bool = False,
    graph_truncated: bool = False,
) -> float:
    """Compute response confidence (0.0-1.0) from data quality signals.

    Components:
    - Entity resolution (0-0.3): resolution success × match quality
    - Evidence depth (0-0.3): ≥10=0.3, ≥5=0.2, ≥1=0.1
    - Graph context (0-0.2): ≥20 nodes=0.2, ≥5=0.1, truncated=-0.05
    - Metrics available (0-0.2)
    """
    score = 0.0

    # Entity resolution (0-0.3)
    if entity_resolved:
        score += 0.3 * (entity_match_score if entity_match_score is not None else 0.8)

    # Evidence depth (0-0.3)
    if evidence_count >= 10:
        score += 0.3
    elif evidence_count >= 5:
        score += 0.2
    elif evidence_count >= 1:
        score += 0.1

    # Graph context (0-0.2)
    if graph_node_count >= 20:
        score += 0.2
    elif graph_node_count >= 5:
        score += 0.1
    if graph_truncated:
        score -= 0.05

    # Metrics (0-0.2)
    if metrics_available:
        score += 0.2

    return round(min(1.0, max(0.0, score)), 2)


# ── Compare graph builder ──


def build_compare_graph(
    entities: list[dict],
    shared_connections: list[dict],
    unique_connections: dict[str, list[dict]],
) -> dict:
    """Build graph_context from compare handler's shared/unique connections.

    Returns standard graph_context: {nodes, edges, node_count, edge_count}.
    Shared connections get edges to ALL compared entities.
    Unique connections get edges to their owning entity only.
    """
    nodes_by_id: dict[str, dict] = {}
    edges: list[dict] = []

    # Add compared entities as nodes
    for e in entities:
        eid = e.get("entity_id", "")
        if eid:
            nodes_by_id[eid] = {
                "entity_id": eid,
                "entity_type": e.get("entity_type", "drug"),
                "label": e.get("label", ""),
            }

    entity_ids = [e.get("entity_id", "") for e in entities]

    # Shared connections → edges to ALL compared entities
    for conn in (shared_connections or []):
        cid = conn.get("entity_id", "")
        if not cid:
            continue
        if cid not in nodes_by_id:
            nodes_by_id[cid] = {
                "entity_id": cid,
                "entity_type": conn.get("entity_type", "unknown"),
                "label": conn.get("label", ""),
            }
        for eid in entity_ids:
            if eid and eid != cid:
                edges.append({
                    "source_id": eid,
                    "target_id": cid,
                    "link_type": "SHARED",
                    "confidence": 1.0,
                })

    # Unique connections → edge to owning entity only
    for owner_id, conns in (unique_connections or {}).items():
        for conn in (conns or []):
            cid = conn.get("entity_id", "")
            if not cid:
                continue
            if cid not in nodes_by_id:
                nodes_by_id[cid] = {
                    "entity_id": cid,
                    "entity_type": conn.get("entity_type", "unknown"),
                    "label": conn.get("label", ""),
                }
            edges.append({
                "source_id": owner_id,
                "target_id": cid,
                "link_type": "UNIQUE",
                "confidence": 1.0,
            })

    nodes = list(nodes_by_id.values())
    return {
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


# ── Private chart builders ──

def _to_number(value) -> Optional[float]:
    """Internal alias used by chart builders."""
    return to_number(value)


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
