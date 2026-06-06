"""Domain Forge — gamified SME knowledge elicitation.

One SME interaction = a playbook edit + a gold eval label + a validation signal.

  * prompts.py  — generate a round prompt FROM real DB entities (round type ①
                  "What matters?": pick/rank the dimensions for a compare question).
  * engine.py   — the round engine: create round → submit constrained answer →
                  persist (a) the elicited dimension into a playbook version via
                  the existing PlaybookAuthoringService and (b) a gold eval item;
                  DF-2 validation + multi-SME consensus + correctness-gated score.

Reuse, not duplication: authoring (services.domain_intelligence.authoring),
validation (services.domain_intelligence.validation), and the playbook model are
called, never reimplemented. The forge_* tables (migration 083) are only the
round / eval / score substrate around those existing writes.
"""

from services.domain_forge.engine import (
    ForgeEngine,
    RoundNotFound,
    RoundAlreadyAnswered,
    InvalidAnswer,
)
from services.domain_forge.prompts import (
    DIMENSION_OPTIONS,
    generate_what_matters_round,
)

__all__ = [
    "ForgeEngine",
    "RoundNotFound",
    "RoundAlreadyAnswered",
    "InvalidAnswer",
    "DIMENSION_OPTIONS",
    "generate_what_matters_round",
]
