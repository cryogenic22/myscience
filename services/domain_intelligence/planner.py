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
        "confidence": conf,
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

        for route in dim.routes:
            if route.kind != "predicate":
                # link / source routes are recorded but not yet executed — the
                # predicate substrate carries the value today. Transparent, not
                # invented (DI-3 honesty): the cell shows what it couldn't reach.
                skipped.append(f"{route.kind}:{route.value}")
                continue
            executed.append(f"predicate:{route.value}")
            try:
                rows = facts_as_of(self.db, etype, eid, as_of=as_of, predicate=route.value)
            except Exception:
                logger.exception("planner: facts_as_of failed for %s:%s pred=%s",
                                 etype, eid, route.value)
                rows = []
            for fact in rows:
                rendered = _fact_to_cell_fact(fact)
                # Dedup within the cell on the underlying claim VALUE (the
                # rendered object_value), so the same finding surfaced via two
                # predicates routed to one dimension (e.g. an AE that is also a
                # safety_signal) appears once.
                key = _render_value(fact.get("object_value")).strip().lower() \
                    or rendered["claim"].strip().lower()
                if not key or key in seen_claims:
                    continue
                seen_claims.add(key)
                facts.append(rendered)
                if len(facts) >= self.max_facts_per_dimension:
                    break
            if len(facts) >= self.max_facts_per_dimension:
                break

        return DimensionCell(
            dimension_key=dim.key,
            entity_id=eid,
            sub_question=dim.fill(entity["label"]),
            facts=facts,
            coverage=coverage_state(facts),
            routes_executed=executed,
            routes_skipped=skipped,
        )
