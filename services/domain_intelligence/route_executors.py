"""DI-4 — link & source route executors.

In DI-2 the planner only executed `predicate:` routes (pulling facts from the
ledger); `link:` and `source:` routes were *recorded* in ``routes_skipped`` so
the cell stayed honest rather than inventing data. The value those routes point
at — graph edges (e.g. COMPETES_WITH) and structured source tables (e.g.
regulatory_milestones) — was real but unreached, so e.g. tirzepatide's
competition/regulatory cells showed as gaps although the data existed.

This module executes those two route kinds, returning the SAME compact, citeable
cell-fact shape the predicate path produces (see planner._fact_to_cell_fact), so
the matrix, synthesis, and coverage logic treat all three route kinds uniformly.

Grounding is preserved end to end:
  * a link fact cites the traversed edge (link type + the connecting node);
  * a source fact cites the table row (its key columns + source_url drill-through).
Nothing is inferred — a missing edge / empty table yields no facts, i.e. a gap.

Reuse, not duplication:
  * link routes use the EXISTING read-only GraphTraversal.neighborhood (services
    /graph.py) — we never edit the graph service, only call it;
  * the fact shape mirrors planner._fact_to_cell_fact / dossier_kb rendering.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from services.domain_intelligence.playbook import Route

logger = logging.getLogger(__name__)

# UUIDs in a link's `via` string ("shared mechanism <uuid> in TA <uuid>") are
# provenance plumbing, not analyst-readable — strip them so the claim reads as
# "<competitor> (via shared mechanism)". The relationship + competitor name are
# the grounded payload; the exact UUIDs live in the edge, not the narrative.
_UUID_RE = re.compile(
    r"\s*[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def _clean_via(via: str) -> str:
    """Drop raw UUIDs and collapse whitespace in a link's `via` description."""
    cleaned = _UUID_RE.sub("", via or "")
    cleaned = re.sub(r"\bin TA\b\s*$", "", cleaned).strip()
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,")
    return cleaned


# ── source-route whitelist ─────────────────────────────────────────
#
# Only these tables may be read by a `source:` route. Each entry declares the
# foreign-key column linking back to the subject entity, an ORDER BY for the
# most-relevant rows, and a renderer turning one row into a human claim. The
# whitelist is the safety boundary: an unknown table name yields no query (and
# no facts), exactly like the old skipped behaviour — never arbitrary SQL.


def _render_regulatory_milestone(row: dict) -> str:
    """One regulatory_milestones row → a compact human claim."""
    sub_type = (row.get("submission_type") or "").strip()
    sub_num = (row.get("submission_number") or "").strip()
    status = (row.get("submission_status") or "").strip()
    date = row.get("submission_status_date")
    priority = (row.get("review_priority") or "").strip()
    head = "Regulatory submission"
    if sub_type:
        head = f"{sub_type} submission" + (f" #{sub_num}" if sub_num else "")
    parts = [head]
    if status:
        parts.append(status)
    if date:
        parts.append(str(date))
    claim = " — ".join(parts[:2]) + (f" ({date})" if date else "")
    if priority and priority not in ("STANDARD", ""):
        claim += f" [{priority}]"
    return claim


# table → {fk, order_by, render, fact_class}
SOURCE_ROUTES: dict[str, dict] = {
    "regulatory_milestones": {
        "fk": "drug_id",
        "entity_type": "drug",
        "columns": (
            "submission_type, submission_number, submission_status, "
            "submission_status_date, review_priority, source_url"
        ),
        "order_by": "submission_status_date DESC NULLS LAST",
        "render": _render_regulatory_milestone,
        "fact_class": "reference",  # regulatory facts are reference-class
    },
}


# ── link routes ────────────────────────────────────────────────────


def execute_link_route(
    graph: Any,
    route: Route,
    entity_type: str,
    entity_id: str,
    limit: int = 6,
) -> list[dict]:
    """Traverse a single link type from the subject and ground each neighbour.

    Uses the EXISTING read-only GraphTraversal.neighborhood (1-hop, filtered to
    this link type). Returns cell-facts citing the edge — self-links and
    duplicate neighbour names are dropped. Empty/failed traversal → [] (a gap),
    never invented.
    """
    if graph is None:
        return []
    link_type = route.value
    try:
        sub = graph.neighborhood(entity_id, entity_type, link_types=[link_type])
    except Exception:
        logger.exception("link route traversal failed: %s on %s:%s",
                         link_type, entity_type, entity_id)
        return []

    nodes = getattr(sub, "nodes", None) or []
    edges = getattr(sub, "edges", None) or []
    label_by_id = {str(n.entity_id): (n.label or str(n.entity_id)) for n in nodes}

    facts: list[dict] = []
    seen_names: set[str] = set()
    center = str(entity_id)
    for edge in edges:
        # The neighbour is whichever end isn't the subject.
        src, tgt = str(edge.source_id), str(edge.target_id)
        neighbour_id = tgt if src == center else src
        if neighbour_id == center:
            continue  # self-link
        name = label_by_id.get(neighbour_id, neighbour_id)
        key = (name or "").strip().lower()
        if not key or key in seen_names:
            continue
        seen_names.add(key)
        via = _clean_via(getattr(edge, "via", "") or "")
        try:
            conf = float(getattr(edge, "confidence", None)) if getattr(edge, "confidence", None) is not None else None
        except (TypeError, ValueError):
            conf = None
        conf_str = f" · conf {conf:.0%}" if conf is not None else ""
        claim = name
        if via:
            claim = f"{name} (via {via})"
        facts.append({
            "id": f"link:{link_type}:{neighbour_id}",
            "predicate": f"link:{link_type}",
            "claim": claim,
            # graph-derived relationships are inferred (structural), not asserted
            # corporate/reference facts.
            "fact_class": "inferred",
            "source_label": f"graph {link_type}{conf_str}",
            "source_url": None,
            "confidence": conf,
        })
        if len(facts) >= limit:
            break
    return facts


# ── source routes ──────────────────────────────────────────────────


def execute_source_route(
    db: Any,
    route: Route,
    entity_type: str,
    entity_id: str,
    limit: int = 6,
) -> list[dict]:
    """Read a whitelisted structured source table for the subject and ground
    each row. Unknown table → [] with no query issued (the safety boundary)."""
    spec = SOURCE_ROUTES.get(route.value)
    if spec is None:
        logger.debug("source route %s not whitelisted — skipping", route.value)
        return []
    if spec.get("entity_type") and entity_type != spec["entity_type"]:
        # The table keys off a different entity type than the subject.
        return []
    sql = (
        f"SELECT {spec['columns']} FROM {route.value} "
        f"WHERE {spec['fk']}::text = %s "
        f"ORDER BY {spec['order_by']} LIMIT %s"
    )
    try:
        rows = db.fetch_all(sql, [str(entity_id), limit])
    except Exception:
        logger.exception("source route read failed: %s for %s", route.value, entity_id)
        return []

    render = spec["render"]
    fact_class = spec.get("fact_class", "reference")
    facts: list[dict] = []
    seen: set[str] = set()
    for i, row in enumerate(rows or []):
        try:
            claim = render(row)
        except Exception:
            logger.debug("source row render failed for %s", route.value, exc_info=True)
            continue
        key = (claim or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        facts.append({
            "id": f"source:{route.value}:{i}",
            "predicate": f"source:{route.value}",
            "claim": claim,
            "fact_class": fact_class,
            "source_label": f"{route.value}",
            "source_url": row.get("source_url") or None,
            "confidence": None,
        })
        if len(facts) >= limit:
            break
    return facts
