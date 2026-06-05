"""DI-1 — Playbook data model + registry.

A **Playbook** is encoded domain expertise for answering a CLASS of question:
"to compare two drugs, an analyst examines mechanism, efficacy, safety, dosing,
regulatory status, pricing/access, and competitive position — and for each, here
is where the answer lives." It is *data*, not code.

The data model:
  * Route     — one retrieval route: predicate / link / source + value.
  * Dimension — a named bundle of routes + a sub-question template + weight.
  * Playbook  — trigger (intent × entity signature) + dimensions + synthesis shape.

Playbooks are YAML-seeded (services/domain_intelligence/playbooks/*.yaml) so
they are data, not hardcoded dicts. A DB table (migration 080) can override the
seed per id — the SME-editable path (DI-5). The registry loads the seed first,
then layers DB rows on top, falling back gracefully when the table is absent.

The routes deliberately reuse the EXACT predicates the fact ledger already
emits and the _PREDICATE_DOMAIN / _PREDICATE_KBQ maps already know, so a
dimension is a named view over retrieval the system already does.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

_PLAYBOOK_DIR = os.path.join(os.path.dirname(__file__), "playbooks")

# Route kinds the planner knows how to execute (DI-2).
_ROUTE_KINDS = ("predicate", "link", "source")


@dataclass(frozen=True)
class Route:
    """One retrieval route for a dimension.

    kind="predicate" → pull facts_as_of by that ledger predicate (the common case)
    kind="link"      → traverse an entity-graph link type (e.g. COMPETES_WITH)
    kind="source"    → read a structured source table (e.g. regulatory_milestones)
    """

    kind: str
    value: str

    @classmethod
    def parse(cls, spec: Any) -> "Route":
        """Parse a route spec. Accepts 'predicate:foo', 'link:BAR', 'source:baz',
        a bare string (→ predicate), or a {kind, value} / {predicate: foo} dict."""
        if isinstance(spec, Route):
            return spec
        if isinstance(spec, dict):
            if "kind" in spec and "value" in spec:
                return cls(str(spec["kind"]).strip(), str(spec["value"]).strip())
            # {predicate: "x"} / {link: "Y"} / {source: "z"}
            for kind in _ROUTE_KINDS:
                if kind in spec:
                    return cls(kind, str(spec[kind]).strip())
            raise ValueError(f"unparseable route dict: {spec!r}")
        text = str(spec).strip()
        if ":" in text:
            kind, _, value = text.partition(":")
            kind = kind.strip().lower()
            if kind in _ROUTE_KINDS:
                return cls(kind, value.strip())
        # bare token → predicate (the most common authoring shorthand)
        return cls("predicate", text)


@dataclass
class Dimension:
    """A named analytical dimension within a playbook — a routed sub-question."""

    key: str
    label: str
    sub_question: str = ""
    routes: list[Route] = field(default_factory=list)
    required: bool = False
    weight: float = 0.5

    def predicates(self) -> list[str]:
        """The predicate-kind route values (what the planner pulls from the ledger)."""
        return [r.value for r in self.routes if r.kind == "predicate"]

    def links(self) -> list[str]:
        return [r.value for r in self.routes if r.kind == "link"]

    def sources(self) -> list[str]:
        return [r.value for r in self.routes if r.kind == "source"]

    def fill(self, entity: str) -> str:
        """Template-fill the sub-question for a concrete entity."""
        return self.sub_question.replace("{entity}", entity) if self.sub_question else ""

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "sub_question": self.sub_question,
            "routes": [f"{r.kind}:{r.value}" for r in self.routes],
            "required": self.required,
            "weight": self.weight,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Dimension":
        return cls(
            key=str(d["key"]),
            label=str(d.get("label") or d["key"]),
            sub_question=str(d.get("sub_question") or ""),
            routes=[Route.parse(r) for r in (d.get("routes") or [])],
            required=bool(d.get("required", False)),
            weight=float(d.get("weight", 0.5)),
        )


@dataclass
class Playbook:
    """Encoded domain expertise for a class of question."""

    id: str
    pack: str = "pharma"
    trigger: dict = field(default_factory=dict)
    dimensions: list[Dimension] = field(default_factory=list)
    synthesis: dict = field(default_factory=dict)

    @property
    def intent(self) -> str:
        return str(self.trigger.get("intent") or "")

    @property
    def entity_signature(self) -> str:
        """Normalized entity-type signature, e.g. 'drug x drug'. Tolerates the
        '×' glyph and 'drug_x_drug' authoring forms."""
        raw = str(self.trigger.get("entities") or "").lower()
        return raw.replace("×", "x").replace("_", " ").strip()

    def matches(self, intent: str, entity_types: list[str]) -> bool:
        """Does this playbook's trigger fire for (intent, entity-type signature)?"""
        if (intent or "").lower() != self.intent.lower():
            return False
        return _signature_matches(self.entity_signature, entity_types)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "pack": self.pack,
            "trigger": dict(self.trigger),
            "dimensions": [d.to_dict() for d in self.dimensions],
            "synthesis": dict(self.synthesis),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Playbook":
        return cls(
            id=str(d["id"]),
            pack=str(d.get("pack") or "pharma"),
            trigger=dict(d.get("trigger") or {}),
            dimensions=[Dimension.from_dict(x) for x in (d.get("dimensions") or [])],
            synthesis=dict(d.get("synthesis") or {}),
        )


def _signature_matches(signature: str, entity_types: list[str]) -> bool:
    """A signature like 'drug x drug' matches exactly two drugs; 'drug' matches
    one drug. Tokens are joined by 'x'. Wildcard '*' matches any type."""
    if not signature:
        return False
    want = [t.strip() for t in signature.split("x") if t.strip()]
    if len(want) != len(entity_types):
        return False
    for w, got in zip(want, entity_types):
        if w != "*" and w != (got or "").lower():
            return False
    return True


class PlaybookRegistry:
    """Loads playbooks from the YAML seed, optionally overridden by DB rows.

    Args:
        db: Optional Database. When provided, playbooks in a ``playbooks`` table
            override seeds with the same id (the SME-editable path). Falls back
            to the seed when the table is absent/empty/erroring.
        load_seed: Load the bundled YAML packs (default True).
    """

    def __init__(self, db: Any = None, load_seed: bool = True) -> None:
        self._playbooks: dict[str, Playbook] = {}
        self._db = db
        if load_seed:
            self._load_seed()
        if db is not None:
            self._load_from_db()

    # ── loading ──

    def _load_seed(self) -> None:
        import yaml

        if not os.path.isdir(_PLAYBOOK_DIR):
            return
        for fname in sorted(os.listdir(_PLAYBOOK_DIR)):
            if not fname.endswith((".yaml", ".yml")):
                continue
            path = os.path.join(_PLAYBOOK_DIR, fname)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
                pb = Playbook.from_dict(data)
                self._playbooks[pb.id] = pb
            except Exception:
                logger.exception("Failed to load playbook seed %s", fname)

    def _load_from_db(self) -> int:
        """Layer DB-backed playbooks over the seed. Returns the count loaded."""
        if self._db is None:
            return 0
        try:
            rows = self._db.fetch_all(
                "SELECT id, pack, trigger, dimensions, synthesis "
                "FROM playbooks WHERE active = true"
            )
        except Exception as exc:
            logger.debug("Playbooks DB load skipped (table may not exist): %s", exc)
            return 0
        count = 0
        for row in rows or []:
            try:
                pb = Playbook.from_dict({
                    "id": row["id"],
                    "pack": row.get("pack") or "pharma",
                    "trigger": row.get("trigger") or {},
                    "dimensions": row.get("dimensions") or [],
                    "synthesis": row.get("synthesis") or {},
                })
                self._playbooks[pb.id] = pb
                count += 1
            except Exception:
                logger.exception("Failed to parse DB playbook %s", row.get("id"))
        return count

    # ── lookup / selection ──

    def get(self, playbook_id: str) -> Optional[Playbook]:
        return self._playbooks.get(playbook_id)

    def all(self) -> list[Playbook]:
        return list(self._playbooks.values())

    def select(self, intent: str, entity_types: list[str]) -> Optional[Playbook]:
        """Select the playbook whose trigger matches (intent × entity signature).

        Prefers the most-specific match (longest matching entity signature) when
        multiple fire. Returns None when nothing matches — the caller falls back
        to the legacy path (graceful degradation, never a crash)."""
        candidates = [pb for pb in self._playbooks.values()
                      if pb.matches(intent, entity_types)]
        if not candidates:
            return None
        candidates.sort(key=lambda pb: len(pb.entity_signature.split("x")), reverse=True)
        return candidates[0]


# Module-level singleton (seed-only; DB-backed registries are constructed
# per-request where a db handle is available, like ConceptRegistry).
_REGISTRY: Optional[PlaybookRegistry] = None


def get_playbook_registry() -> PlaybookRegistry:
    """Cached seed-only registry (zero DB calls), mirroring the concept-registry
    module singleton pattern in chat_handlers/handlers.py."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = PlaybookRegistry()
    return _REGISTRY
