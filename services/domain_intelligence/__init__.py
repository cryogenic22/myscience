"""Domain Intelligence — question-decomposition planner + SME-authorable packs.

The module that makes the chat *break a nuanced question down like a domain
expert*: a PLAN stage between understand and retrieve that selects a
**playbook** (the dimensions a domain expert examines for a class of question),
fills each dimension from grounded ledger facts, assembles a structured matrix,
and synthesizes per-dimension with citations + explicit gaps.

See docs/domain-intelligence-module-spec.html (DI-1 … DI-7).

Public surface:
  * playbook  — Playbook / Dimension / Route data model + PlaybookRegistry (DI-1)
  * planner   — DecompositionPlanner: matrix assembly from the ledger (DI-2)
  * synthesis — dimension-aware grounded narrative + gaps (DI-3)
"""

from __future__ import annotations

from services.domain_intelligence.playbook import (
    Dimension,
    Playbook,
    PlaybookRegistry,
    Route,
    get_playbook_registry,
)

__all__ = [
    "Dimension",
    "Playbook",
    "PlaybookRegistry",
    "Route",
    "get_playbook_registry",
]
