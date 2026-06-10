"""DI-2 — the decomposition planner.

The core lift. Given an intent + the resolved entities, the planner:

  1. SELECTS the playbook whose trigger matches (intent × entity signature).
  2. EXPANDS each dimension into a per-entity sub-question (template-filled).
  3. ROUTES + RETRIEVES each dimension to its facts via facts_as_of by predicate
     (the rich substrate — clinical/mechanism/safety/literature facts already
     exist for the demo drugs), deduped within the cell.
  4. ASSEMBLES a structured matrix (entities × dimensions); each cell carries the
     grounded facts + a coverage state (covered / thin / gap).

This sits as the PLAN stage between understand and retrieve in ctx_pipeline.
Synthesis (DI-3) consumes the matrix; gaps are stated, never invented.

Reuse: facts_as_of (services.facts_ledger), the predicate→claim rendering from
services.dossier_kb (_render_value / _humanize), the PlaybookRegistry (DI-1).
Link/source routes are recorded but not yet executed (the predicate substrate
is where the value is today); they degrade to a transparent "route not yet
wired" rather than inventing data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from services.facts_ledger import facts_as_of
from services.dossier_kb import _render_value, _humanize, _coerce_fact_class
from services.domain_intelligence.playbook import (
    Dimension,
    Playbook,
    PlaybookRegistry,
    get_playbook_registry,
)
from services.domain_intelligence.route_executors import (
    execute_link_route,
    execute_source_route,
)

logger = logging.getLogger(__name__)

# Coverage thresholds: a cell with ≥ this many grounded facts is "covered";
# 1..(N-1) is "thin"; 0 is a "gap". Kept small — these dimensions are answered
# by a handful of high-signal facts, not volume.
_COVERED_THRESHOLD = 2


def coverage_state(facts: list[dict]) -> str:
    """gap (0 facts) / thin (1 fact) / covered (≥ threshold). Pure."""
    n = len(facts)
    if n == 0:
        return "gap"
    if n < _COVERED_THRESHOLD:
        return "thin"
    return "covered"


@dataclass
class DimensionCell:
    """One cell of the matrix: dimension × entity. Grounded facts + coverage."""

    dimension_key: str
    entity_id: str
    sub_question: str
    facts: list[dict] = field(default_factory=list)   # [{claim, fact_class, source_label, source_url, predicate, id}]
    coverage: str = "gap"
    routes_executed: list[str] = field(default_factory=list)
    routes_skipped: list[str] = field(default_factory=list)  # link/source routes not yet wired

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension_key,
            "entity_id": self.entity_id,
            "sub_question": self.sub_question,
            "coverage": self.coverage,
            "facts": self.facts,
            "routes_executed": self.routes_executed,
            "routes_skipped": self.routes_skipped,
        }


@dataclass
class QuestionMatrix:
    """The structured decomposition: entities × dimensions, each cell grounded."""

    playbook_id: str
    intent: str
    entities: list[dict]                 # [{entity_id, entity_type, label}]
    dimensions: list[Dimension]
    cells: dict[tuple[str, str], DimensionCell] = field(default_factory=dict)
    synthesis: dict = field(default_factory=dict)

    def cell(self, dimension_key: str, entity_id: str) -> Optional[DimensionCell]:
        return self.cells.get((dimension_key, entity_id))

    def coverage_summary(self) -> dict[str, str]:
        """Per-dimension rollup across entities: covered (any entity covered),
        thin (any entity has some evidence), else gap."""
        summary: dict[str, str] = {}
        for d in self.dimensions:
            states = [
                self.cells[(d.key, e["entity_id"])].coverage
                for e in self.entities
                if (d.key, e["entity_id"]) in self.cells
            ]
            if "covered" in states:
                summary[d.key] = "covered"
            elif "thin" in states:
                summary[d.key] = "thin"
            else:
                summary[d.key] = "gap"
        return summary

    def gaps(self) -> list[str]:
        """Dimension keys that are a gap for at least one entity (DI-3 honesty)."""
        out: list[str] = []
        for d in self.dimensions:
            for e in self.entities:
                c = self.cells.get((d.key, e["entity_id"]))
                if c and c.coverage == "gap":
                    out.append(d.key)
                    break
        return out

    def to_dict(self) -> dict:
        return {
            "playbook_id": self.playbook_id,
            "intent": self.intent,
            "entities": self.entities,
            "dimensions": [d.to_dict() for d in self.dimensions],
            "cells": [c.to_dict() for c in self.cells.values()],
            "coverage_summary": self.coverage_summary(),
            "gaps": self.gaps(),
            "synthesis": dict(self.synthesis),
        }


def _fact_to_cell_fact(fact: dict) -> dict:
    """Render a ledger fact into the cell's compact, citeable shape. Reuses the
    dossier_kb rendering so claims read identically to the dossier."""
    predicate = fact.get("predicate") or ""
    claim_value = _render_value(fact.get("object_value"))
    claim = (
        f"{_humanize(predicate)}: {claim_value}".strip().rstrip(":").strip()
        if claim_value else _humanize(predicate)
    )
    ov = fact.get("object_value")
    source_url = ov.get("source_url") if isinstance(ov, dict) else None
    created_by = fact.get("created_by") or "system"
    conf = fact.get("confidence")
    try:
        conf_str = f" · conf {float(conf):.0%}" if conf is not None else ""
    except (TypeError, ValueError):
        conf_str = ""
    return {
        "id": str(fact.get("id") or ""),
        "predicate": predicate,
        "claim": claim,
        "fact_class": _coerce_fact_class(fact.get("fact_class")),
        "source_label": f"{created_by}{conf_str}",
        "source_url": source_url or None,
        # float() so the cell dict is JSON-safe for non-FastAPI consumers
        # (telemetry / json.dumps) — facts_as_of can return a Decimal (cf. #195).
        "confidence": float(conf) if conf is not None else None,
    }


class DecompositionPlanner:
    """Decomposes a nuanced question into a grounded, per-dimension matrix."""

    def __init__(
        self,
        db: Any,
        registry: Optional[PlaybookRegistry] = None,
        max_facts_per_dimension: int = 6,
    ) -> None:
        self.db = db
        # A db-backed registry picks up SME edits (DI-5); fall back to the
        # cached seed-only singleton when no db handle is supplied.
        if registry is not None:
            self.registry = registry
        elif db is not None:
            self.registry = PlaybookRegistry(db=db)
        else:
            self.registry = get_playbook_registry()
        self.max_facts_per_dimension = max_facts_per_dimension
        self._graph: Any = None
        self._graph_init = False

    def _graph_traversal(self) -> Any:
        """Lazily build a read-only GraphTraversal for link routes. Cached;
        returns None if it can't be constructed (link routes then no-op into a
        gap rather than raising). Reuses the existing graph service unchanged."""
        if self._graph_init:
            return self._graph
        self._graph_init = True
        if self.db is None:
            return None
        try:
            from services.graph import GraphTraversal
            try:
                from config import config as _config
            except Exception:
                _config = None
            self._graph = GraphTraversal(self.db, _config)
        except Exception:
            logger.debug("planner: GraphTraversal unavailable; link routes skip", exc_info=True)
            self._graph = None
        return self._graph

    def plan(
        self,
        intent: str,
        entities: list[dict],
        as_of: Optional[datetime] = None,
    ) -> Optional[QuestionMatrix]:
        """Build the decomposition matrix, or None when no playbook matches
        (caller falls back to the legacy path — graceful, never a crash).

        `entities` are pre-resolved: [{entity_id, entity_type, label}, ...]."""
        entity_types = [(e.get("entity_type") or "drug") for e in entities]
        playbook = self.registry.select(intent, entity_types)
        if playbook is None:
            logger.debug("No playbook for intent=%s signature=%s", intent, entity_types)
            return None

        matrix = QuestionMatrix(
            playbook_id=playbook.id,
            intent=intent,
            entities=[
                {
                    "entity_id": e["entity_id"],
                    "entity_type": e.get("entity_type") or "drug",
                    "label": e.get("label") or e["entity_id"],
                }
                for e in entities
            ],
            dimensions=playbook.dimensions,
            synthesis=playbook.synthesis,
        )

        for dim in playbook.dimensions:
            for e in matrix.entities:
                cell = self._fill_cell(dim, e, as_of)
                matrix.cells[(dim.key, e["entity_id"])] = cell

        return matrix

    def _fill_cell(
        self, dim: Dimension, entity: dict, as_of: Optional[datetime]
    ) -> DimensionCell:
        """Route a single dimension for a single entity to grounded facts."""
        etype = entity["entity_type"]
        eid = entity["entity_id"]
        seen_claims: set[str] = set()
        facts: list[dict] = []
        executed: list[str] = []
        skipped: list[str] = []

        def _remaining() -> int:
            return self.max_facts_per_dimension - len(facts)

        def _add(rendered: dict, dedup_key: str) -> None:
            """Add a rendered cell-fact, deduping on a stable key so the same
            finding reached via two routes (e.g. an AE that is also a
            safety_signal, or a competitor named in a fact AND a graph edge)
            appears once."""
            key = (dedup_key or rendered.get("claim", "")).strip().lower()
            if not key or key in seen_claims:
                return
            seen_claims.add(key)
            facts.append(rendered)

        for route in dim.routes:
            if _remaining() <= 0:
                break

            if route.kind == "predicate":
                executed.append(f"predicate:{route.value}")
                try:
                    rows = facts_as_of(self.db, etype, eid, as_of=as_of, predicate=route.value)
                except Exception:
                    logger.exception("planner: facts_as_of failed for %s:%s pred=%s",
                                     etype, eid, route.value)
                    rows = []
                for fact in rows:
                    if _remaining() <= 0:
                        break
                    rendered = _fact_to_cell_fact(fact)
                    _add(rendered, _render_value(fact.get("object_value")))

            elif route.kind == "link":
                # Execute the link route via the read-only graph traversal.
                graph = self._graph_traversal()
                try:
                    link_facts = execute_link_route(
                        graph, route, etype, eid, limit=_remaining()
                    )
                except Exception:
                    logger.exception("planner: link route failed %s for %s:%s",
                                     route.value, etype, eid)
                    link_facts = []
                if graph is None:
                    skipped.append(f"link:{route.value}")
                else:
                    executed.append(f"link:{route.value}")
                    for rendered in link_facts:
                        if _remaining() <= 0:
                            break
                        _add(rendered, rendered.get("claim", ""))

            elif route.kind == "source":
                try:
                    src_facts = execute_source_route(
                        self.db, route, etype, eid, limit=_remaining()
                    )
                except Exception:
                    logger.exception("planner: source route failed %s for %s:%s",
                                     route.value, etype, eid)
                    src_facts = []
                # A non-whitelisted source table returns [] — record it as
                # skipped so the cell stays transparent about what it couldn't
                # reach (DI-3 honesty); a whitelisted one is executed.
                from services.domain_intelligence.route_executors import SOURCE_ROUTES
                if route.value in SOURCE_ROUTES:
                    executed.append(f"source:{route.value}")
                    for rendered in src_facts:
                        if _remaining() <= 0:
                            break
                        _add(rendered, rendered.get("claim", ""))
                else:
                    skipped.append(f"source:{route.value}")

            else:
                skipped.append(f"{route.kind}:{route.value}")

        return DimensionCell(
            dimension_key=dim.key,
            entity_id=eid,
            sub_question=dim.fill(entity["label"]),
            facts=facts,
            coverage=coverage_state(facts),
            routes_executed=executed,
            routes_skipped=skipped,
        )
