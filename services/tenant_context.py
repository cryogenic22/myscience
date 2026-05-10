"""BE-38 — tenant context for the multi-tenancy middleware.

A single contextvar carries the active tenant slug across the
request. ``services/search.py`` and ``services/graph.py`` consume it
to inject ``WHERE tenant_id IN ('public', :current)`` filters into
their reads. Outside a request (cron, scripts) the contextvar is
empty and ``get_current_tenant`` returns ``'public'`` — the safest
default that never accidentally surfaces another customer's data.

The complementary db schema lives in
``schema/migrations/066_tenant_id_core_entities.sql`` (BE-37).
"""

from __future__ import annotations

import contextlib
import contextvars
from typing import Iterator, Optional


DEFAULT_TENANT = "public"

# Tables BE-37 added the column to. Tables not in this set must NOT
# have the WHERE filter appended — appending an unknown column would
# crash the query.
TABLES_WITH_TENANT: frozenset[str] = frozenset({
    "drugs",
    "companies",
    "clinical_trials",
    "mechanisms_of_action",
})

# Entity-type → table map for HybridSearch + GraphTraversal callers.
# Reuses the same naming HybridSearch already uses internally.
ENTITY_TYPE_TENANT_TABLES: dict[str, str] = {
    "drug": "drugs",
    "company": "companies",
    "trial": "clinical_trials",
    "mechanism": "mechanisms_of_action",
}


_current_tenant: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "mz_current_tenant", default=None
)


def get_current_tenant() -> str:
    """Return the active tenant slug, or ``'public'`` if not set."""
    val = _current_tenant.get()
    if val is None or not val.strip():
        return DEFAULT_TENANT
    return val


def set_current_tenant(tenant: Optional[str]) -> contextvars.Token:
    """Install ``tenant`` for the rest of this context.

    Pass ``None`` to clear (next read will return ``DEFAULT_TENANT``).
    Returns the contextvars Token so callers can reset() back.
    """
    return _current_tenant.set(tenant)


@contextlib.contextmanager
def with_tenant(tenant: Optional[str]) -> Iterator[str]:
    """Scoped tenant override::

        with with_tenant('pfizer'):
            results = search.search(...)   # filtered to pfizer + public
    """
    token = set_current_tenant(tenant)
    try:
        yield get_current_tenant()
    finally:
        _current_tenant.reset(token)


def tenant_filter_clause(
    *,
    table_alias: Optional[str] = None,
    tenant: Optional[str] = None,
) -> tuple[str, list]:
    """Return ``("AND <col> = ANY(%s)", [["public", "<tenant>"]])`` for
    appending to a WHERE clause.

    Pass ``table_alias`` if the column should be qualified
    (e.g. ``"d"`` → ``"d.tenant_id = ANY(%s)"``). Pass an explicit
    ``tenant`` to override the contextvar (used by tests).

    The ``ANY(%s)`` form means **public + the active tenant** are
    both visible — public rows stay visible from any tenant so the
    shared knowledge base never disappears.
    """
    eff_tenant = tenant if tenant is not None else get_current_tenant()
    col = "tenant_id" if not table_alias else f"{table_alias}.tenant_id"
    allowed = [DEFAULT_TENANT]
    if eff_tenant and eff_tenant != DEFAULT_TENANT:
        allowed.append(eff_tenant)
    # Use list so psycopg parameterises it as text[]
    return f"{col} = ANY(%s)", [allowed]
