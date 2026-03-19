"""Presentation planner -- deterministic data-shape analysis for display format.

No LLM calls. Inspects tool result data to decide the best display format.
"""

from __future__ import annotations

import re
from typing import Any, Optional


def _detect_chart_hints(context: str) -> dict:
    """Regex-based detection of chart type preferences from question text."""
    hints: dict[str, str] = {}
    lower = context.lower()

    # Trend / time-series → line chart
    if re.search(r"\b(trend|over time|year[- ]over[- ]year|monthly|quarterly|timeline|growth)\b", lower):
        hints["preferred_type"] = "line"

    # Composition / share / breakdown → donut chart
    elif re.search(r"\b(breakdown|composition|share|distribution|proportion|split|percent)\b", lower):
        hints["preferred_type"] = "donut"

    # Comparison / ranking → bar chart
    elif re.search(r"\b(compare|comparison|rank|top\s+\d+|versus|vs\.?|difference)\b", lower):
        hints["preferred_type"] = "bar"

    return hints


def _detect_outliers(rows: list[dict], val_col: str) -> list[dict]:
    """Flag values >2 standard deviations from the mean."""
    if not rows or not val_col:
        return []

    values = [_to_num(r.get(val_col, 0)) for r in rows]
    if len(values) < 3:
        return []

    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    std_dev = variance ** 0.5

    if std_dev == 0:
        return []

    outliers = []
    for i, (row, val) in enumerate(zip(rows, values)):
        z_score = (val - mean) / std_dev
        if abs(z_score) > 2:
            label_col = next((c for c in row if c != val_col and isinstance(row[c], str)), None)
            outliers.append({
                "index": i,
                "label": str(row.get(label_col, f"Row {i}")) if label_col else f"Row {i}",
                "value": val,
                "z_score": round(z_score, 2),
                "direction": "high" if z_score > 0 else "low",
            })

    return outliers


def plan_presentation(tool_results: dict, question: str = "") -> dict:
    """Analyse tool results and return a PresentationConfig dict.

    Returns:
        {
            "display": "metric_card" | "bar_chart" | "donut_chart" | "line_chart"
                       | "table" | "evidence_cards" | "persona_cards" | "narrative_only",
            "table_data": {columns, rows, title} or None,
            "visualizations": [VisualizationSpec, ...],
            "insights": {"outliers": [...]} (optional),
        }
    """
    table_data = None
    visualizations: list[dict] = []
    display = "narrative_only"
    insights: dict = {}

    # Detect chart preference from question text
    chart_hints = _detect_chart_hints(question) if question else {}

    # Check SQL results first (highest structured signal)
    sql_result = tool_results.get("sql") or tool_results.get("exec_sql")
    if sql_result and getattr(sql_result, "success", False) and sql_result.data:
        rows = sql_result.data
        columns = sql_result.columns
        row_count = sql_result.row_count

        if row_count == 1 and len(columns) == 1:
            display = "metric_card"
            table_data = _build_table_data(columns, rows, "Result")

        elif 1 <= row_count <= 15:
            numeric_cols = _find_numeric_columns(columns, rows)
            date_cols = _find_date_columns(columns, rows)
            category_cols = [c for c in columns if c not in numeric_cols and c not in date_cols]

            if date_cols and numeric_cols:
                display = "line_chart"
                date_col = date_cols[0]
                val_col = numeric_cols[0]
                visualizations.append({
                    "id": "agent-line-chart",
                    "type": "line",
                    "title": f"{_humanize(val_col)} over time",
                    "value_unit": "",
                    "data": [
                        {"label": str(r.get(date_col, "")), "value": _to_num(r.get(val_col, 0))}
                        for r in rows
                    ],
                    "recommended": True,
                    "display_priority": "high",
                })
            elif category_cols and numeric_cols and _looks_like_proportions(rows, numeric_cols[0]):
                display = "donut_chart"
                cat_col = category_cols[0]
                val_col = numeric_cols[0]
                visualizations.append({
                    "id": "agent-donut-chart",
                    "type": "donut",
                    "title": f"{_humanize(val_col)} by {_humanize(cat_col)}",
                    "value_unit": "",
                    "data": [
                        {"label": str(r.get(cat_col, "")), "value": _to_num(r.get(val_col, 0))}
                        for r in rows
                    ],
                    "recommended": True,
                    "display_priority": "high",
                })
            elif numeric_cols and row_count >= 2:
                display = "bar_chart"
                label_col = category_cols[0] if category_cols else columns[0]
                val_col = numeric_cols[0]
                visualizations.append({
                    "id": "agent-bar-chart",
                    "type": "bar",
                    "title": f"{_humanize(val_col)} by {_humanize(label_col)}",
                    "value_unit": "",
                    "data": [
                        {"label": str(r.get(label_col, "")), "value": _to_num(r.get(val_col, 0))}
                        for r in rows
                    ],
                    "recommended": True,
                    "display_priority": "high",
                })
            else:
                display = "table"

            table_data = _build_table_data(columns, rows, "Query Results")

        elif row_count > 15:
            display = "table"
            table_data = _build_table_data(columns, rows, "Query Results")

    # Check sql_detail enrichment (proactive detail rows for scalar counts)
    sql_detail = tool_results.get("sql_detail")
    if sql_detail and getattr(sql_detail, "success", False) and sql_detail.data:
        detail_rows = sql_detail.data
        detail_columns = sql_detail.columns
        detail_title = tool_results.get("sql_detail_title", "Details")
        if detail_rows and detail_columns:
            # Upgrade from metric_card to table when enrichment provides detail rows
            display = "table"
            table_data = _build_table_data(detail_columns, detail_rows, detail_title)

    # Check RAG results
    rag_result = tool_results.get("rag") or tool_results.get("exec_rag")
    if rag_result and getattr(rag_result, "success", False) and rag_result.data:
        if display == "narrative_only":
            display = "evidence_cards"

    # Check metrics results
    metrics_result = tool_results.get("metrics")
    if metrics_result and getattr(metrics_result, "success", False) and metrics_result.data:
        if display == "narrative_only":
            rows = metrics_result.data
            columns = metrics_result.columns
            if rows and columns:
                display = "bar_chart"
                numeric_cols = _find_numeric_columns(columns, rows)
                cat_cols = [c for c in columns if c not in numeric_cols]
                if numeric_cols and cat_cols:
                    visualizations.append({
                        "id": "agent-metrics-chart",
                        "type": "bar",
                        "title": f"{_humanize(numeric_cols[0])} by {_humanize(cat_cols[0])}",
                        "value_unit": "",
                        "data": [
                            {"label": str(r.get(cat_cols[0], "")), "value": _to_num(r.get(numeric_cols[0], 0))}
                            for r in rows[:15]
                        ],
                        "recommended": True,
                        "display_priority": "high",
                    })
                table_data = _build_table_data(columns, rows, "Metrics")

    # Apply chart hint overrides when question implies a specific chart type
    preferred = chart_hints.get("preferred_type")
    if preferred and visualizations and sql_result and getattr(sql_result, "success", False):
        rows = sql_result.data or []
        columns = sql_result.columns or []
        numeric_cols = _find_numeric_columns(columns, rows)
        category_cols = [c for c in columns if c not in numeric_cols]

        if preferred == "donut" and category_cols and numeric_cols and 2 <= len(rows) <= 8:
            # Override to donut if data shape allows
            cat_col, val_col = category_cols[0], numeric_cols[0]
            visualizations = [{
                "id": "agent-donut-chart",
                "type": "donut",
                "title": f"{_humanize(val_col)} by {_humanize(cat_col)}",
                "value_unit": "",
                "data": [{"label": str(r.get(cat_col, "")), "value": _to_num(r.get(val_col, 0))} for r in rows],
                "recommended": True,
                "display_priority": "high",
            }]
            display = "donut_chart"
        elif preferred == "bar" and category_cols and numeric_cols and len(rows) >= 2:
            # Override to bar
            label_col, val_col = category_cols[0], numeric_cols[0]
            visualizations = [{
                "id": "agent-bar-chart",
                "type": "bar",
                "title": f"{_humanize(val_col)} by {_humanize(label_col)}",
                "value_unit": "",
                "data": [{"label": str(r.get(label_col, "")), "value": _to_num(r.get(val_col, 0))} for r in rows],
                "recommended": True,
                "display_priority": "high",
            }]
            display = "bar_chart"

    # Detect outliers in visualization data
    if visualizations and sql_result and getattr(sql_result, "success", False):
        rows = sql_result.data or []
        numeric_cols = _find_numeric_columns(sql_result.columns or [], rows)
        if numeric_cols:
            outliers = _detect_outliers(rows, numeric_cols[0])
            if outliers:
                insights["outliers"] = outliers

    result = {
        "display": display,
        "table_data": table_data,
        "visualizations": visualizations,
    }
    if insights:
        result["insights"] = insights
    return result


def plan_team_eval_presentation(
    persona_analyses: list[dict],
    tool_results: dict,
    confidence_assessment: dict,
) -> dict:
    """Build presentation config for team eval mode."""
    base = plan_presentation(tool_results)
    base["display"] = "persona_cards"
    base["persona_analyses"] = persona_analyses
    base["confidence_assessment"] = confidence_assessment
    return base


def _build_table_data(
    columns: list[str],
    rows: list[dict],
    title: str,
) -> dict:
    """Build frontend-compatible TableData."""
    col_defs = []
    for col in columns:
        col_type = "text"
        if rows:
            sample = rows[0].get(col)
            if isinstance(sample, (int, float)):
                col_type = "number"
            elif isinstance(sample, str) and _looks_like_date_str(sample):
                col_type = "date"
        col_defs.append({"key": col, "label": _humanize(col), "type": col_type})

    return {
        "columns": col_defs,
        "rows": [{col: _serialize_value(r.get(col)) for col in columns} for r in rows],
        "title": title,
    }


def _find_numeric_columns(columns: list[str], rows: list[dict]) -> list[str]:
    """Find columns that contain numeric values."""
    numeric = []
    for col in columns:
        for r in rows[:5]:
            val = r.get(col)
            if isinstance(val, (int, float)):
                numeric.append(col)
                break
    return numeric


def _find_date_columns(columns: list[str], rows: list[dict]) -> list[str]:
    """Find columns likely containing dates."""
    date_keywords = {"date", "time", "created", "updated", "at", "year", "month"}
    date_cols = []
    for col in columns:
        lower = col.lower()
        if any(kw in lower for kw in date_keywords):
            date_cols.append(col)
    return date_cols


def _looks_like_proportions(rows: list[dict], val_col: str) -> bool:
    """Check if values look like proportions (2-8 rows, all positive)."""
    if len(rows) < 2 or len(rows) > 8:
        return False
    values = [_to_num(r.get(val_col, 0)) for r in rows]
    return all(v >= 0 for v in values)


def _looks_like_date_str(s: str) -> bool:
    """Quick heuristic to check if a string looks like a date."""
    return bool(re.match(r"\d{4}-\d{2}-\d{2}", s))


def _humanize(col_name: str) -> str:
    """Convert column_name to Column Name."""
    return col_name.replace("_", " ").title()


def _to_num(val: Any) -> float:
    """Safe conversion to float."""
    try:
        return float(val) if val is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _serialize_value(val: Any) -> Any:
    """Convert values to JSON-serializable form."""
    if val is None:
        return None
    if isinstance(val, (int, float, str, bool)):
        return val
    return str(val)
