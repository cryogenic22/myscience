"""A2a — the Context Layer: the single typed door for reading composed
entity state. See specs/SPEC_A2a_context_layer.md.

The keystone is the FillState type: a Section refuses to construct in a
silently-empty state. Every section that is not POPULATED carries an
explicit reason. This is the structural enforcement of "no silent empty
section" — it is a type, not a convention, and the dataclass __post_init__
enforces it on every construction.

Skeleton: get_entity_360 and query_facts wrap the facts ledger.
traverse / semantic_search / emit_event are typed stubs that return
well-formed empties for now (A2b/A3/B will fill them in).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


# ── Errors ─────────────────────────────────────────────────────────


class ContextContractError(ValueError):
    """Raised when a Section is constructed in a state that violates its
    contract (e.g. POPULATED without data, or UNAVAILABLE_* without a reason).
    """


class EntityNotFound(LookupError):
    """The requested entity reference does not resolve to a known entity."""


# ── FillState + Section: the keystone type ─────────────────────────


class FillState(str, Enum):
    POPULATED            = "populated"
    UNAVAILABLE_NO_DATA  = "unavailable_no_data"
    UNAVAILABLE_STALE    = "unavailable_stale"
    UNAVAILABLE_BLOCKED  = "unavailable_blocked"
    UNAVAILABLE_ERROR    = "unavailable_error"


@dataclass(frozen=True)
class FactRef:
    """Lightweight reference to a fact (for provenance attachment)."""
    fact_id: str
    predicate: str
    source_doc_id: Optional[str] = None


@dataclass(frozen=True)
class Freshness:
    newest_at: Optional[datetime] = None
    oldest_at: Optional[datetime] = None


@dataclass
class Section:
    """One named section of an Entity 360.

    Invariants (enforced in __post_init__, the structural fix for the
    silent-empty-section problem called out in the gap analysis):

      POPULATED       requires data is not None
      UNAVAILABLE_*   requires reason to be a non-empty string

    The dataclass refuses to construct any other combination. A silent
    empty section is unrepresentable.
    """
    key: str
    fill: FillState
    as_of: datetime
    data: Any | None = None
    reason: str | None = None
    provenance: list[FactRef] = field(default_factory=list)
    freshness: Freshness | None = None

    def __post_init__(self):
        if self.fill is FillState.POPULATED:
            if self.data is None:
                raise ContextContractError(
                    f"section {self.key!r}: POPULATED requires data (got None)"
                )
        else:
            if not self.reason or not self.reason.strip():
                raise ContextContractError(
                    f"section {self.key!r}: {self.fill.value} requires a non-empty reason"
                )


@dataclass
class Entity360:
    identity: dict
    sections: dict[str, Section]
    as_of: datetime
    tenant: Optional[str] = None

    def __getitem__(self, key: str) -> Section:
        return self.sections[key]


@dataclass
class SubGraph:
    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)


# ── Entity-ref parsing ─────────────────────────────────────────────


_VALID_ENTITY_TYPES = {"drug", "company", "trial", "indication", "kol", "payer",
                       "mechanism", "therapeutic_area", "patent"}


def _parse_entity_ref(ref: str) -> tuple[str, str]:
    """`'drug:wegovy-demo'` → `('drug', 'wegovy-demo')`. Raises if malformed."""
    if not ref or ":" not in ref:
        raise EntityNotFound(
            f"entity ref must be 'type:id', got {ref!r}"
        )
    etype, _, eid = ref.partition(":")
    etype = etype.strip().lower()
    eid = eid.strip()
    if not etype or not eid:
        raise EntityNotFound(f"entity ref has empty type or id: {ref!r}")
    if etype not in _VALID_ENTITY_TYPES:
        raise EntityNotFound(
            f"unknown entity type {etype!r} (known: {sorted(_VALID_ENTITY_TYPES)})"
        )
    return etype, eid


# ── ContextLayer ───────────────────────────────────────────────────


class ContextLayer:
    """The five-operation door agents/routes call against.

    Agents never call services directly through this skeleton. The skeleton
    wraps facts_ledger for the read path and stubs the rest in a typed-clean
    way (A2b/A3/B fill in).
    """

    def __init__(self, db):
        self.db = db

    # ── get_entity_360 ─────────────────────────────────────────────

    def get_entity_360(
        self,
        entity_ref: str,
        *,
        projection: Optional[list[str]] = None,
        as_of: Optional[datetime] = None,
        tenant: Optional[str] = None,
    ) -> Entity360:
        """Composed view of an entity. Each section is a Section with an
        explicit FillState — never silently empty."""
        etype, eid = _parse_entity_ref(entity_ref)  # raises EntityNotFound
        when = as_of or datetime.now(timezone.utc)

        # Section builders. Each takes (etype, eid, when, tenant) and returns
        # a Section. Builders catch their own exceptions at the boundary and
        # surface them as UNAVAILABLE_ERROR — they never return [] or None
        # silently. The lint test (test_context_layer_no_silent_empty.py)
        # enforces this rule structurally.
        builders: dict[str, Callable[..., Section]] = {
            "identity": self._build_identity_section,
            "facts": self._build_facts_section,
        }

        sections: dict[str, Section] = {}
        keys = projection if projection is not None else list(builders.keys())
        for key in keys:
            builder = builders.get(key)
            if builder is None:
                sections[key] = Section(
                    key=key, fill=FillState.UNAVAILABLE_NO_DATA, as_of=when,
                    reason=f"no builder registered for section {key!r}",
                )
                continue
            sections[key] = self._run_builder(key, builder, etype, eid, when, tenant)

        return Entity360(
            identity={"type": etype, "id": eid},
            sections=sections,
            as_of=when,
            tenant=tenant,
        )

    def _run_builder(self, key, builder, etype, eid, when, tenant) -> Section:
        """Run a section builder; any uncaught exception becomes an
        UNAVAILABLE_ERROR section with the exception as the reason. This is
        the seam that replaces the dossier.py defensive try/except pattern
        that silently emptied sections."""
        try:
            return builder(etype, eid, when, tenant)
        except ContextContractError:
            # The builder itself violated the type contract — re-raise; it
            # is a programmer error, not data unavailability.
            raise
        except Exception as exc:
            logger.exception(
                "context layer section builder failed for %s on %s:%s",
                key, etype, eid,
            )
            return Section(
                key=key,
                fill=FillState.UNAVAILABLE_ERROR,
                as_of=when,
                reason=f"{type(exc).__name__}: {exc}",
            )

    # ── section builders ───────────────────────────────────────────

    def _build_identity_section(self, etype, eid, when, tenant) -> Section:
        # Minimal skeleton identity from the (etype, eid). A2b will hydrate
        # from the canonical entity tables; for now we surface what we know
        # is true by reference (the ref itself).
        data = {"type": etype, "id": eid, "ref": f"{etype}:{eid}"}
        return Section(
            key="identity",
            fill=FillState.POPULATED,
            as_of=when,
            data=data,
            provenance=[],
        )

    def _build_facts_section(self, etype, eid, when, tenant) -> Section:
        # Pulls from facts_ledger via query_facts. If zero facts, the section
        # is UNAVAILABLE_NO_DATA with a reason, not silently empty.
        facts = self.query_facts(
            {"subject_entity_type": etype, "subject_entity_id": eid},
            as_of=when,
            tenant=tenant,
        )
        if not facts:
            return Section(
                key="facts",
                fill=FillState.UNAVAILABLE_NO_DATA,
                as_of=when,
                reason=f"no facts in ledger for {etype}:{eid} as_of {when.isoformat()}",
            )
        # Compute freshness window
        asserted_at = [f.get("asserted_at") for f in facts if f.get("asserted_at")]
        freshness = Freshness(
            newest_at=max(asserted_at) if asserted_at else None,
            oldest_at=min(asserted_at) if asserted_at else None,
        )
        return Section(
            key="facts",
            fill=FillState.POPULATED,
            as_of=when,
            data={"count": len(facts), "facts": facts},
            provenance=[
                FactRef(
                    fact_id=str(f.get("id")),
                    predicate=f.get("predicate", ""),
                    source_doc_id=str(f["source_doc_id"]) if f.get("source_doc_id") else None,
                )
                for f in facts
            ],
            freshness=freshness,
        )

    # ── query_facts ────────────────────────────────────────────────

    def query_facts(
        self,
        filter: dict,
        *,
        as_of: Optional[datetime] = None,
        tenant: Optional[str] = None,
        min_confidence: float = 0.0,
    ) -> list[dict]:
        """Read facts from the ledger with temporal + tenant + confidence
        filtering. Does NOT route through facts_ledger.facts_as_of because
        that helper swallows DB errors into []; the Context Layer's contract
        is to surface them so callers (section builders) can convert them to
        UNAVAILABLE_ERROR via _run_builder."""
        from services.facts_ledger import _valid_at  # pure temporal predicate

        subj_type = filter.get("subject_entity_type")
        subj_id = filter.get("subject_entity_id")
        predicate = filter.get("predicate")
        if not subj_type or not subj_id:
            # No subject scope — return [] is the correct semantics for an
            # under-specified query (this is NOT a section build path, so
            # the "no silent empty" rule does not apply).
            return []
        when = as_of or datetime.now(timezone.utc)

        sql = """
            SELECT id, kind, predicate, subject_entity_type, subject_entity_id,
                   object_value, valid_from, valid_to, asserted_at, source_doc_id,
                   confidence, created_by, superseded_by, tenant_scope
              FROM facts
             WHERE subject_entity_type = %s AND subject_entity_id = %s
               {predicate_clause}
             ORDER BY valid_from DESC NULLS LAST, asserted_at DESC
        """
        params: list = [subj_type, str(subj_id)]
        pred_clause = ""
        if predicate:
            pred_clause = "AND predicate = %s"
            params.append(predicate)
        sql = sql.format(predicate_clause=pred_clause)
        # NO try/except here — let errors propagate to _run_builder so they
        # surface as UNAVAILABLE_ERROR sections, not silent empties.
        rows = self.db.fetch_all(sql, params)
        rows = [r for r in rows if _valid_at(r, when)]
        if min_confidence > 0.0:
            rows = [r for r in rows if (r.get("confidence") or 0.0) >= min_confidence]
        # tenant filtering: drop tenant-scoped facts that don't match. nullable
        # tenant_scope means "global" (visible to all).
        if tenant is not None:
            rows = [r for r in rows if (r.get("tenant_scope") in (None, tenant))]
        else:
            # Caller didn't specify a tenant — only return global facts to be
            # safe (no leakage).
            rows = [r for r in rows if r.get("tenant_scope") is None]
        return rows

    # ── traverse (stub for A2a; A3 fills it in) ────────────────────

    def traverse(
        self,
        start: str,
        edge_types: list[str],
        *,
        depth: int = 1,
        filter: Optional[dict] = None,
        tenant: Optional[str] = None,
    ) -> SubGraph:
        # Skeleton stub: returns an empty SubGraph. A3 will wire to
        # services.graph.traverse / neighborhood.
        return SubGraph(nodes=[], edges=[])

    # ── semantic_search (stub) ─────────────────────────────────────

    def semantic_search(
        self,
        query_text: str,
        *,
        scope: Optional[dict] = None,
        k: int = 20,
        tenant: Optional[str] = None,
    ) -> list[dict]:
        # Skeleton stub: a future loop wires this to services.search.
        return []

    # ── emit_event (stub for A2a; B1 implements the bus) ───────────

    def emit_event(self, event_type: str, payload: dict) -> str:
        # Skeleton stub: returns a synthetic event id and logs. Phase B
        # implements real dispatch.
        eid = f"evt-{uuid4().hex[:12]}"
        logger.info("context_layer.emit_event: %s → %s", event_type, eid)
        return eid
