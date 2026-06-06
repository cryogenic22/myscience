"""Track I — the EVAL HARNESS.

The measurement layer. The Domain Forge mints gold labels (forge_eval_items:
prompt → SME answer, by round type). This harness runs the SYSTEM's own answer
for the same prompt and scores it, so we can report accuracy / precision /
recall / coverage over time, per round-type and per playbook.

  * scorers.py  — pure system-vs-gold scoring per round type (no DB, no I/O):
                  what_matters → DecompositionPlanner dimensions;
                  routing      → playbook routes (set precision/recall);
                  signal_or_noise → materiality score ordering;
                  critique     → cell groundedness vs the SME grade.
  * harness.py  — EvalHarness: load gold → compute system answer → score →
                  aggregate → persist an eval run (eval_runs / eval_results).

Reuse, not duplication: the planner, the playbook registry, the materiality
scorer, and the Forge gold contract are CALLED here, never reimplemented. The
benchmark/eval_runner.py golden-query runner is a different (chat-response)
harness; this one scores the structured Forge gold set.
"""

from services.evaluation.scorers import (
    ItemScore,
    Verdict,
    score_critique,
    score_routing,
    score_signal_or_noise,
    score_what_matters,
)
from services.evaluation.harness import EvalHarness, EvalRunSummary

__all__ = [
    "EvalHarness",
    "EvalRunSummary",
    "ItemScore",
    "Verdict",
    "score_what_matters",
    "score_routing",
    "score_signal_or_noise",
    "score_critique",
]
