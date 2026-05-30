# SPEC A2a — Context Layer skeleton + `FillState` type

*Phase A loop 2 of the spine convergence. 30 May 2026.*

## Problem
Today, routes/agents/services reach into SQL directly and into `dossier.py`/`graph.py`/`query_engine.py` in three different ways to compose an entity view. Provenance, freshness, and tenant scope are enforced nowhere; failures inside section composition are silently swallowed (`dossier.py:118,150,188`). The Context Layer is the single typed door that closes this seam and makes "no silent empty section" a *type*, not a convention.

## Contract — `services/context_layer.py`

### The keystone: `FillState`
```python
class FillState(str, Enum):
    POPULATED            = "populated"
    UNAVAILABLE_NO_DATA  = "unavailable_no_data"
    UNAVAILABLE_STALE    = "unavailable_stale"
    UNAVAILABLE_BLOCKED  = "unavailable_blocked"
    UNAVAILABLE_ERROR    = "unavailable_error"

@dataclass
class Section:
    key: str
    fill: FillState
    as_of: datetime
    data: Any | None = None
    reason: str | None = None
    provenance: list[FactRef] = field(default_factory=list)
    freshness: Freshness | None = None
    # __post_init__ raises ContextContractError if invariants violated
```
The dataclass **refuses to construct** when `fill is POPULATED` and `data is None`, or when `fill is not POPULATED` and `reason` is empty/None. A silent-empty section becomes unrepresentable.

### Five operations
```python
def get_entity_360(entity_ref, *, projection=None, as_of=None, tenant=None) -> Entity360
def query_facts(filter, *, as_of=None, tenant=None, min_confidence=0.0) -> list[Fact]
def traverse(start, edge_types, *, depth=1, filter=None, tenant=None) -> SubGraph
def semantic_search(query_text, *, scope=None, k=20, tenant=None) -> list[Ref]
def emit_event(event_type, payload) -> EventId
```

`Entity360` = `{ identity: dict, sections: dict[str, Section], as_of: datetime, tenant: str | None }`.

A2a delivers the **skeleton**: types, signatures, FillState invariants, `get_entity_360` and `query_facts` implemented by wrapping `facts_ledger` and existing services. `traverse`/`semantic_search`/`emit_event` are stubs that return well-typed empties or raise `NotImplementedError` cleanly. Consumer migration is A2b.

## Acceptance tests
1. **FillState invariants**: `Section(fill=POPULATED, data=None)` raises `ContextContractError`. `Section(fill=UNAVAILABLE_NO_DATA, reason="")` raises. `Section(fill=UNAVAILABLE_NO_DATA, reason="no facts in window")` constructs.
2. **`get_entity_360` returns Entity360 with at least an identity section.**
3. **`get_entity_360(as_of=future)` surfaces anticipatory facts** (verifies wraps facts_ledger correctly).
4. **`get_entity_360` swallows nothing**: when an internal section query raises, the section returns with `fill=UNAVAILABLE_ERROR` and `reason=str(exc)` — never `[]` or `None` silently.
5. **`query_facts` proxies `facts_ledger.facts_as_of`** with provenance attached.

## Out of scope (drift guard)
- No consumer migration (A2b).
- No real graph traversal beyond what exists in `services/graph.py` (A3-ish).
- No event bus implementation (Phase B).
- No tenant RLS enforcement (E).

## Files
- NEW `services/context_layer.py`
- NEW `tests/test_context_layer.py`
- NEW `tests/test_context_layer_no_silent_empty.py` (lint test forbidding `except…: return []` in section builders)
