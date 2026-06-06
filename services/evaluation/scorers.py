"""EV-1 — pure system-vs-gold scorers, one per Forge round type.

Each scorer takes the GOLD answer (from a forge_eval_items row) and the SYSTEM's
answer (computed by the harness from the live planner / playbook / materiality
model for the SAME prompt) and returns an ItemScore: a verdict
(correct / partial / miss) plus, for set-valued answers, precision & recall.

These are PURE — no DB, no I/O. The harness (harness.py) is responsible for
computing the system answer and feeding it here, which keeps the scoring logic
testable in isolation and free of the live substrate. No fabricated numbers: a
verdict is derived only from the two answers passed in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Verdict vocabulary — a small, auditable enum.
CORRECT = "correct"
PARTIAL = "partial"
MISS = "miss"
SKIPPED = "skipped"
Verdict = str  # type alias for readability


@dataclass
class ItemScore:
    """The score for one gold item against the system's answer."""

    verdict: Verdict
    precision: Optional[float] = None   # set-valued answers (routing) only
    recall: Optional[float] = None
    covered: bool = False               # did the system produce ANY answer? (coverage)
    detail: dict = field(default_factory=dict)

    # ── derived numerics for aggregation ──
    @property
    def is_correct(self) -> bool:
        return self.verdict == CORRECT

    @property
    def is_partial(self) -> bool:
        return self.verdict == PARTIAL

    @property
    def accuracy_credit(self) -> float:
        """Accuracy gives full credit for correct, half for partial, none else.
        Skipped items are excluded from accuracy by the aggregator (not scored)."""
        if self.verdict == CORRECT:
            return 1.0
        if self.verdict == PARTIAL:
            return 0.5
        return 0.0

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "precision": self.precision,
            "recall": self.recall,
            "covered": self.covered,
            "detail": dict(self.detail),
        }


def _norm_set(items) -> set[str]:
    """A normalized string set (trim + lower), dropping blanks."""
    return {str(x).strip().lower() for x in (items or []) if str(x).strip()}


# ════════════════════════════════════════════════════════════════════
# ① what_matters — gold top dimension vs the planner's dimensions
# ════════════════════════════════════════════════════════════════════

def score_what_matters(
    gold_dimensions: list[str],
    system_dimensions: list[str],
    *,
    system_top: Optional[str] = None,
) -> ItemScore:
    """The SME ranked the dimensions that matter for a compare; the system's
    answer is the DecompositionPlanner's dimensions for that compare's playbook.

    Verdict on the SME's TOP pick (what matters MOST):
      * correct — the system surfaces the gold top dimension AND ranks it first
                  (its top-weighted dimension).
      * partial — the system surfaces the gold top dimension, but not first.
      * miss    — the system does not surface the gold top dimension at all.

    precision/recall over the full ranked set quantify how well the system's
    dimension set matches what the SME said matters.
    """
    gold = [str(d).strip().lower() for d in (gold_dimensions or []) if str(d).strip()]
    sys = [str(d).strip().lower() for d in (system_dimensions or []) if str(d).strip()]
    sys_set = set(sys)
    gold_set = set(gold)
    covered = bool(sys)

    if not gold:
        return ItemScore(SKIPPED, covered=covered, detail={"reason": "no gold dimensions"})
    if not covered:
        return ItemScore(MISS, covered=False, recall=0.0, precision=0.0,
                         detail={"reason": "system produced no dimensions (no playbook match)",
                                 "gold": gold})

    gold_top = gold[0]
    sys_top = (str(system_top).strip().lower() if system_top else (sys[0] if sys else ""))

    # set-level recall/precision over what-matters dimensions
    inter = gold_set & sys_set
    recall = len(inter) / len(gold_set) if gold_set else 0.0
    precision = len(inter) / len(sys_set) if sys_set else 0.0

    if gold_top in sys_set:
        verdict = CORRECT if gold_top == sys_top else PARTIAL
    else:
        verdict = MISS
    return ItemScore(
        verdict, precision=round(precision, 4), recall=round(recall, 4),
        covered=True,
        detail={"gold_top": gold_top, "system_top": sys_top,
                "gold": gold, "system": sys, "overlap": sorted(inter)},
    )


# ════════════════════════════════════════════════════════════════════
# ③ routing — gold trusted route-set vs the playbook dimension's routes
# ════════════════════════════════════════════════════════════════════

def score_routing(
    gold_routes: list[str],
    system_routes: list[str],
) -> ItemScore:
    """The SME picked the fact-types/sources they TRUST for a dimension; the
    system's answer is the playbook dimension's actual routes.

    Set-valued: precision = |gold ∩ system| / |system|,
                recall    = |gold ∩ system| / |gold|.
      * correct — exact set match (precision == recall == 1).
      * partial — non-empty overlap.
      * miss    — disjoint sets.
    """
    gold = _norm_set(gold_routes)
    sys = _norm_set(system_routes)
    covered = bool(sys)

    if not gold:
        return ItemScore(SKIPPED, covered=covered, detail={"reason": "no gold routes"})
    inter = gold & sys
    recall = len(inter) / len(gold) if gold else 0.0
    precision = len(inter) / len(sys) if sys else 0.0

    if sys and gold == sys:
        verdict = CORRECT
    elif inter:
        verdict = PARTIAL
    else:
        verdict = MISS
    return ItemScore(
        verdict, precision=round(precision, 4), recall=round(recall, 4),
        covered=covered,
        detail={"gold": sorted(gold), "system": sorted(sys),
                "overlap": sorted(inter)},
    )


# ════════════════════════════════════════════════════════════════════
# ② signal_or_noise — gold most-material signal vs materiality ordering
# ════════════════════════════════════════════════════════════════════

def score_signal_or_noise(
    gold_signal_id: str,
    ranked_signal_ids: list[str],
) -> ItemScore:
    """The SME picked the MOST MATERIAL of the round's candidate signals; the
    system's answer is those same candidates re-ranked by the materiality model
    (highest score first).

      * correct — the materiality model ranks the gold signal #1.
      * partial — the gold signal is in the top half (better than chance) but
                  not #1.
      * miss    — the gold signal is in the bottom half.

    Coverage = the system produced a non-empty ranking.
    """
    gold = str(gold_signal_id or "").strip()
    ranked = [str(s).strip() for s in (ranked_signal_ids or []) if str(s).strip()]
    covered = bool(ranked)
    if not gold:
        return ItemScore(SKIPPED, covered=covered, detail={"reason": "no gold signal"})
    if not covered or gold not in ranked:
        return ItemScore(MISS, covered=covered,
                         detail={"reason": "gold signal not in system ranking",
                                 "gold": gold, "ranked": ranked})
    rank = ranked.index(gold)          # 0-based
    n = len(ranked)
    if rank == 0:
        verdict = CORRECT
    elif rank < (n + 1) // 2:          # strictly within the top half
        verdict = PARTIAL
    else:
        verdict = MISS
    return ItemScore(
        verdict, covered=True,
        detail={"gold": gold, "rank": rank + 1, "of": n, "ranked": ranked},
    )


# ════════════════════════════════════════════════════════════════════
# ④ critique — gold accuracy grade vs the system's cell groundedness
# ════════════════════════════════════════════════════════════════════

def score_critique(
    gold_grade: str,
    system_grounded: bool,
) -> ItemScore:
    """The SME graded a real machine-generated cell (correct / partial / wrong);
    the system's "answer" is whether it still stands behind the cell — i.e.
    whether grounded evidence for it exists.

    A correct system is one whose confidence MATCHES the SME's grade:
      * gold 'correct'  + grounded  → the system was right (CORRECT verdict).
      * gold 'wrong'    + grounded  → the system asserted a wrong cell (MISS).
      * gold 'partial'             → the cell is half-right (PARTIAL verdict).
      * gold 'correct'  + ungrounded→ the system can no longer support a cell the
                                       SME called correct (PARTIAL — lost evidence).
      * gold 'wrong'    + ungrounded→ the system no longer asserts the wrong cell
                                       (CORRECT — it self-corrected).
    """
    grade = str(gold_grade or "").strip().lower()
    if grade not in ("correct", "partial", "wrong"):
        return ItemScore(SKIPPED, covered=False, detail={"reason": f"unknown grade '{grade}'"})

    if grade == "partial":
        verdict = PARTIAL
    elif grade == "correct":
        verdict = CORRECT if system_grounded else PARTIAL
    else:  # wrong
        verdict = MISS if system_grounded else CORRECT
    return ItemScore(
        verdict, covered=True,
        detail={"gold_grade": grade, "system_grounded": bool(system_grounded)},
    )
