"""DI-5 — playbook validation (the governance gate for SME authoring).

A playbook is only trustworthy if every route it declares actually resolves to
real retrieval the planner can execute. This module is the safety boundary for
the authoring API: it rejects a save when

  * a required structural field is missing/empty (id, dimensions, dimension.key);
  * a `predicate:` route targets a predicate the ledger does NOT route — i.e. it
    is unknown to BOTH _PREDICATE_DOMAIN and _PREDICATE_KBQ and is not routable
    by the dossier prefix router (falls to wargame_specific);
  * a `link:` route targets a link type that is not whitelisted (the pack's link
    rules + the derived COMPETES_WITH edge the graph serves);
  * a `source:` route targets a table not in route_executors.SOURCE_ROUTES;
  * the playbook's trigger DUPLICATES / ambiguously overlaps an existing
    playbook's (intent × entity-signature) trigger.

Reuse, not duplication: the predicate vocabulary IS the live ledger map
(route_predicate_to_domain), the source whitelist IS SOURCE_ROUTES, and the
link whitelist is derived from the pharma pack link rules — there is no second,
drifting copy of "what's valid".
"""

from __future__ import annotations

import logging
from typing import Iterable, Optional

from services.domain_intelligence.playbook import Playbook, Route

logger = logging.getLogger(__name__)


class PlaybookValidationError(ValueError):
    """Raised when a playbook fails a save-time validation rule.

    Carries the list of human-readable problems so the API can return all of
    them at once (an SME fixes everything in one round-trip)."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


# ── route vocabularies (single source of truth — no second copy) ───────


def known_predicates() -> set[str]:
    """The set of predicates the ledger explicitly routes (domain + KBQ maps)."""
    from services.dossier_kb import _PREDICATE_DOMAIN
    from services.kbq_views import _PREDICATE_KBQ

    return set(_PREDICATE_DOMAIN) | set(_PREDICATE_KBQ)


def predicate_is_routable(predicate: str) -> bool:
    """A predicate is routable when it is known exactly OR the dossier prefix
    router maps it to a real domain (not the wargame_specific catch-all)."""
    from services.dossier_kb import route_predicate_to_domain

    p = (predicate or "").strip().lower()
    if not p:
        return False
    if p in {x.lower() for x in known_predicates()}:
        return True
    return route_predicate_to_domain(p) != "wargame_specific"


def whitelisted_link_types() -> set[str]:
    """Link types a `link:` route may target: the pharma pack's declared link
    rules plus the derived COMPETES_WITH edge GraphTraversal serves (the route
    executor calls neighborhood with this link type)."""
    links: set[str] = {"COMPETES_WITH"}
    try:
        from domain.pharma.pack import get_pharma_pack

        pack = get_pharma_pack()
        for rule in getattr(pack, "link_rules", None) or []:
            lt = getattr(rule, "link_type", None)
            if lt:
                links.add(str(lt))
    except Exception:
        logger.debug("pharma pack link rules unavailable for validation", exc_info=True)
    return links


def whitelisted_source_tables() -> set[str]:
    """Source tables a `source:` route may read — the route executor whitelist."""
    from services.domain_intelligence.route_executors import SOURCE_ROUTES

    return set(SOURCE_ROUTES)


# ── route-level validation ─────────────────────────────────────────────


def validate_route(route: Route) -> Optional[str]:
    """Return an error string if the route is invalid, else None."""
    kind = (route.kind or "").strip().lower()
    value = (route.value or "").strip()
    if not value:
        return f"route {kind!r} has an empty value"
    if kind == "predicate":
        if not predicate_is_routable(value):
            return (
                f"predicate route '{value}' targets no real ledger predicate "
                f"(unknown to _PREDICATE_DOMAIN / _PREDICATE_KBQ and not "
                f"prefix-routable)"
            )
    elif kind == "link":
        if value not in whitelisted_link_types():
            return (
                f"link route '{value}' is not a whitelisted link type "
                f"(allowed: {sorted(whitelisted_link_types())})"
            )
    elif kind == "source":
        if value not in whitelisted_source_tables():
            return (
                f"source route '{value}' is not a whitelisted source table "
                f"(allowed: {sorted(whitelisted_source_tables())})"
            )
    else:
        return f"unknown route kind '{kind}' (must be predicate / link / source)"
    return None


# ── playbook-level validation ──────────────────────────────────────────


def validate_playbook(
    pb: Playbook,
    *,
    existing: Optional[Iterable[Playbook]] = None,
) -> None:
    """Validate a playbook for save. Raises PlaybookValidationError with ALL
    problems if any rule fails.

    Args:
        pb: the candidate playbook.
        existing: other playbooks to check trigger-overlap against (the one being
            edited is excluded by id). When None, the overlap check is skipped.
    """
    errors: list[str] = []

    # ── required structural fields ──
    if not (pb.id or "").strip():
        errors.append("playbook id is required")
    if not pb.dimensions:
        errors.append("playbook must declare at least one dimension")

    seen_keys: set[str] = set()
    for i, dim in enumerate(pb.dimensions):
        key = (dim.key or "").strip()
        if not key:
            errors.append(f"dimension[{i}] is missing a key")
            continue
        if key in seen_keys:
            errors.append(f"duplicate dimension key '{key}'")
        seen_keys.add(key)
        if not dim.routes:
            errors.append(f"dimension '{key}' has no routes")
        for route in dim.routes:
            err = validate_route(route)
            if err:
                errors.append(f"dimension '{key}': {err}")

    # ── trigger overlap (can't ambiguously duplicate another playbook) ──
    if existing is not None and pb.intent:
        for other in existing:
            if other.id == pb.id:
                continue  # editing self
            if (
                other.intent.lower() == pb.intent.lower()
                and other.entity_signature == pb.entity_signature
            ):
                errors.append(
                    f"trigger (intent='{pb.intent}', entities='{pb.entity_signature}') "
                    f"duplicates existing playbook '{other.id}'"
                )

    if errors:
        raise PlaybookValidationError(errors)
