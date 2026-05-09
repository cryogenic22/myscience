"""SPEC_033 — Counter-Recommendation Synthesizer.

Implements "A unanimous AI is a suspicious AI" (spec §6.4.1). Every
synthesis run produces:
  - one primary recommendation (highest-scoring option)
  - at least one counter-recommendation (different option, different rationale)

The counter-rec rule is enforced by the synthesizer itself — it never
returns a unanimous output. If the inputs cannot satisfy the rule
(e.g., <2 options), the service raises and the route translates to 422.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
# Constants
# ────────────────────────────────────────────────────────────────────

MAX_OPTIONS = 20
VALID_METHODS = {"score_based", "dimension_split", "llm_v1"}


# ────────────────────────────────────────────────────────────────────
# Domain dataclasses
# ────────────────────────────────────────────────────────────────────

@dataclass
class OptionInput:
    option_id: str
    label: str
    score: float                                   # 0-1
    predicted_outcome: Optional[str] = None
    risk_notes: Optional[str] = None
    dimension_scores: Optional[dict[str, float]] = None  # optional per-dim scores


@dataclass
class RecommendationSide:
    option_id: str
    label: str
    score: float
    rationale: str

    def to_dict(self) -> dict:
        return {
            "option_id": str(self.option_id),
            "label": self.label,
            "score": round(self.score, 4),
            "rationale": self.rationale,
        }


@dataclass
class RecommendationResult:
    recommendation_id: str
    brief_id: Optional[str]
    primary: RecommendationSide
    counter: RecommendationSide
    dissent_score: float
    synthesis_method: str
    created_at: Optional[datetime] = None
    started_by_user_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "recommendation_id": str(self.recommendation_id),
            "brief_id": str(self.brief_id) if self.brief_id else None,
            "primary": self.primary.to_dict(),
            "counter": self.counter.to_dict(),
            "dissent_score": round(self.dissent_score, 4),
            "synthesis_method": self.synthesis_method,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_by_user_id": str(self.started_by_user_id) if self.started_by_user_id else None,
        }


# ────────────────────────────────────────────────────────────────────
# Errors
# ────────────────────────────────────────────────────────────────────

class CounterRecRuleViolation(Exception):
    """Inputs cannot satisfy the ≥1 counter-rec invariant."""
    pass


class RecommendationNotFound(Exception):
    pass


# ────────────────────────────────────────────────────────────────────
# Validation
# ────────────────────────────────────────────────────────────────────

def _validate_options(options: list[OptionInput]) -> None:
    if not options:
        raise CounterRecRuleViolation("at least 2 options required")
    if len(options) < 2:
        raise CounterRecRuleViolation(
            f"counter-rec rule cannot be enforced with only {len(options)} option(s); "
            f"brief needs at least 2 options"
        )
    if len(options) > MAX_OPTIONS:
        raise ValueError(f"too many options; cap at {MAX_OPTIONS}")

    seen_ids: set[str] = set()
    for i, o in enumerate(options):
        if not o.option_id or not o.label:
            raise ValueError(f"options[{i}] missing option_id or label")
        if o.option_id in seen_ids:
            raise ValueError(f"options[{i}] duplicate option_id {o.option_id!r}")
        seen_ids.add(o.option_id)
        if not isinstance(o.score, (int, float)) or not math.isfinite(o.score):
            raise ValueError(f"options[{i}].score must be a finite number")
        if not (0.0 <= o.score <= 1.0):
            raise ValueError(f"options[{i}].score must be in [0, 1]")
        if o.dimension_scores is not None:
            for k, v in o.dimension_scores.items():
                if not isinstance(v, (int, float)) or not math.isfinite(v):
                    raise ValueError(
                        f"options[{i}].dimension_scores[{k!r}] must be a finite number"
                    )


# ────────────────────────────────────────────────────────────────────
# Pure synthesis math
# ────────────────────────────────────────────────────────────────────

def _cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine similarity over union of dimension keys; missing keys = 0.
    Returns 0 if either vector has zero magnitude."""
    keys = set(a.keys()) | set(b.keys())
    if not keys:
        return 0.0
    dot = sum(float(a.get(k, 0.0)) * float(b.get(k, 0.0)) for k in keys)
    na = math.sqrt(sum(float(a.get(k, 0.0)) ** 2 for k in keys))
    nb = math.sqrt(sum(float(b.get(k, 0.0)) ** 2 for k in keys))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _build_primary_rationale(opt: OptionInput) -> str:
    parts = [f"Top-scoring option ({opt.score:.2f})."]
    if opt.predicted_outcome:
        parts.append(opt.predicted_outcome.strip())
    return " ".join(parts)[:4000]


def _build_counter_rationale(opt: OptionInput, primary: OptionInput) -> str:
    risk = opt.risk_notes.strip() if opt.risk_notes else "a different risk profile"
    return (
        f"Dissent: {opt.label} scored {opt.score:.2f} but surfaces {risk}. "
        f"Worth weighing against the primary."
    )[:4000]


def synthesize_score_based(options: list[OptionInput]) -> tuple[OptionInput, OptionInput, float]:
    """Pick highest-scoring as primary; lowest-scoring (≠ primary) as counter."""
    by_score = sorted(options, key=lambda o: o.score, reverse=True)
    primary = by_score[0]
    # Counter: lowest-scoring that isn't primary
    counter = None
    for o in reversed(by_score):
        if o.option_id != primary.option_id:
            counter = o
            break
    if counter is None:
        # All options are the same row (shouldn't happen with dedup but defensive)
        raise CounterRecRuleViolation(
            "could not select a counter distinct from primary"
        )
    primary_score = max(0.01, primary.score)
    dissent = abs(primary.score - counter.score) / primary_score
    dissent = max(0.0, min(1.0, dissent))
    return primary, counter, dissent


def synthesize_dimension_split(options: list[OptionInput]) -> tuple[OptionInput, OptionInput, float]:
    """Pick top-scoring as primary; counter is the option most cosine-distant
    from primary across `dimension_scores`. Falls back to score_based if any
    option lacks dimension_scores."""
    if any(o.dimension_scores is None for o in options):
        # Not all options have dim scores → fall back
        return synthesize_score_based(options)
    by_score = sorted(options, key=lambda o: o.score, reverse=True)
    primary = by_score[0]
    # Pick the option whose dim vector is most cosine-distant from primary
    candidates = [o for o in options if o.option_id != primary.option_id]
    if not candidates:
        raise CounterRecRuleViolation("no counter candidate available")

    def _distance(o: OptionInput) -> float:
        sim = _cosine_similarity(primary.dimension_scores or {}, o.dimension_scores or {})
        return 1.0 - sim  # cosine distance

    counter = max(candidates, key=_distance)
    dissent = max(0.0, min(1.0, _distance(counter)))
    return primary, counter, dissent


# ────────────────────────────────────────────────────────────────────
# Service
# ────────────────────────────────────────────────────────────────────

class CounterRecSynthesizer:

    def synthesize(
        self,
        db,
        *,
        options: list[OptionInput],
        brief_id: Optional[str] = None,
        method: str = "score_based",
        started_by_user_id: Optional[str] = None,
        persist: bool = True,
    ) -> RecommendationResult:
        if method not in VALID_METHODS:
            raise ValueError(f"method must be in {sorted(VALID_METHODS)}")
        _validate_options(options)

        if method == "dimension_split":
            primary, counter, dissent = synthesize_dimension_split(options)
            # If we fell back to score_based, record that
            if any(o.dimension_scores is None for o in options):
                method = "score_based"
        else:
            primary, counter, dissent = synthesize_score_based(options)

        # Hard rule: counter must differ from primary
        if counter.option_id == primary.option_id:
            raise CounterRecRuleViolation(
                "synthesizer produced unanimous output; rule violated"
            )

        primary_rationale = _build_primary_rationale(primary)
        counter_rationale = _build_counter_rationale(counter, primary)

        rec = RecommendationResult(
            recommendation_id="",  # filled on persist
            brief_id=brief_id,
            primary=RecommendationSide(
                option_id=primary.option_id, label=primary.label,
                score=primary.score, rationale=primary_rationale,
            ),
            counter=RecommendationSide(
                option_id=counter.option_id, label=counter.label,
                score=counter.score, rationale=counter_rationale,
            ),
            dissent_score=dissent,
            synthesis_method=method,
            started_by_user_id=started_by_user_id,
        )

        if persist:
            self._persist(db, rec, options=options)
        return rec

    def _persist(
        self, db, rec: RecommendationResult, *, options: list[OptionInput],
    ) -> None:
        inputs = {
            "options": [
                {
                    "option_id": o.option_id, "label": o.label, "score": o.score,
                    "predicted_outcome": o.predicted_outcome,
                    "risk_notes": o.risk_notes,
                    "dimension_scores": o.dimension_scores,
                }
                for o in options
            ],
        }
        row = db.fetch_one(
            """
            INSERT INTO recommendation_synthesis_runs (
                brief_id, inputs_jsonb, primary_option_id, primary_rationale,
                counter_option_id, counter_rationale, dissent_score,
                synthesis_method, started_by_user_id
            ) VALUES (%s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s)
            RETURNING recommendation_id, created_at
            """,
            (
                rec.brief_id, json.dumps(inputs),
                rec.primary.option_id, rec.primary.rationale,
                rec.counter.option_id, rec.counter.rationale,
                rec.dissent_score, rec.synthesis_method,
                rec.started_by_user_id,
            ),
        )
        if not row:
            raise RuntimeError("synthesizer persist returned no row")
        rec.recommendation_id = str(row["recommendation_id"])
        rec.created_at = row.get("created_at")


# ────────────────────────────────────────────────────────────────────
# Read-side helpers
# ────────────────────────────────────────────────────────────────────

def get_recommendation(db, recommendation_id: str) -> Optional[dict]:
    row = db.fetch_one(
        """
        SELECT recommendation_id, brief_id, inputs_jsonb, primary_option_id,
               primary_rationale, counter_option_id, counter_rationale,
               dissent_score, synthesis_method, started_by_user_id, created_at
          FROM recommendation_synthesis_runs
         WHERE recommendation_id::text = %s
        """,
        (str(recommendation_id),),
    )
    return _row_to_dict(row) if row else None


def list_recommendations(
    db, *, brief_id: Optional[str] = None,
    limit: int = 50, offset: int = 0,
) -> list[dict]:
    if limit < 1 or limit > 500:
        raise ValueError("limit must be in [1, 500]")
    where = ["1=1"]
    params: list[Any] = []
    if brief_id is not None:
        where.append("brief_id::text = %s"); params.append(str(brief_id))
    params.extend([limit, offset])
    rows = db.fetch_all(
        f"""
        SELECT recommendation_id, brief_id, inputs_jsonb, primary_option_id,
               primary_rationale, counter_option_id, counter_rationale,
               dissent_score, synthesis_method, started_by_user_id, created_at
          FROM recommendation_synthesis_runs
         WHERE {' AND '.join(where)}
         ORDER BY created_at DESC
         LIMIT %s OFFSET %s
        """,
        tuple(params),
    ) or []
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: dict) -> dict:
    inputs = row.get("inputs_jsonb") or {}
    if isinstance(inputs, str):
        try: inputs = json.loads(inputs)
        except (TypeError, ValueError): inputs = {}
    # Reconstruct primary/counter sides from inputs + denormalized columns
    options_by_id = {o["option_id"]: o for o in (inputs.get("options") or [])}
    p_id = str(row["primary_option_id"])
    c_id = str(row["counter_option_id"])
    p_opt = options_by_id.get(p_id, {"option_id": p_id, "label": p_id, "score": 0.0})
    c_opt = options_by_id.get(c_id, {"option_id": c_id, "label": c_id, "score": 0.0})
    return {
        "recommendation_id": str(row["recommendation_id"]),
        "brief_id": str(row["brief_id"]) if row.get("brief_id") else None,
        "primary": {
            "option_id": p_id, "label": p_opt.get("label", p_id),
            "score": float(p_opt.get("score", 0.0)),
            "rationale": row["primary_rationale"],
        },
        "counter": {
            "option_id": c_id, "label": c_opt.get("label", c_id),
            "score": float(c_opt.get("score", 0.0)),
            "rationale": row["counter_rationale"],
        },
        "dissent_score": float(row["dissent_score"]),
        "synthesis_method": row["synthesis_method"],
        "started_by_user_id": str(row["started_by_user_id"]) if row.get("started_by_user_id") else None,
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
    }
