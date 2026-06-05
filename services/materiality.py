"""SPEC_031 — Factor-attributed materiality scoring.

Replaces the single-weight scorer with an attributed model whose output is
`(score: 0-100, factors: dict)`. The frontend uses the factor breakdown to
render "why this signal is critical" tooltips.

Score formula:
    score = 100 × (
        weights.source_tier         × tier_values[tier_int]
      + weights.entity_criticality  × criticality_values[criticality_kind]
      + weights.claim_type          × claim_type_values[claim_type]
      + weights.recency             × exp(-ln(2) × age_days / half_life_days)
    ) clamped to [0, 100]

The weights table is a singleton row in `materiality_weight_config`. Editing
it is admin-level; the public scorer always reads the active row.
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
# Defaults — used when DB has no active config (and as documentation)
# ────────────────────────────────────────────────────────────────────

DEFAULT_WEIGHTS = {
    "source_tier":         0.30,
    "entity_criticality":  0.30,
    "claim_type":          0.25,
    "recency":             0.15,
}

DEFAULT_TIER_VALUES = {
    1: 1.0,   # tier 1: authoritative public (FDA, ClinicalTrials.gov, EMA)
    2: 0.7,   # tier 2: disclosure & news (SEC, IR, press)
    3: 0.4,   # tier 3: scientific & conference (PubMed, ASCO)
    4: 0.6,   # tier 4: licensed CI (Citeline, AlphaSense, MMIT)
}

DEFAULT_CLAIM_TYPE_VALUES = {
    "clinical_readout":     1.00,
    "regulatory_action":    0.95,
    "safety_signal":        0.85,
    "pricing_change":       0.80,
    "formulary_change":     0.75,
    "pipeline_update":      0.60,
    "earnings_commentary":  0.40,
    "other":                0.30,
}

DEFAULT_CRITICALITY_VALUES = {
    "focal":           1.0,
    "top_competitor":  0.7,
    "watched":         0.5,
    "other":           0.2,
}

DEFAULT_RECENCY_HALF_LIFE_DAYS = 30.0

REQUIRED_WEIGHT_KEYS = {"source_tier", "entity_criticality", "claim_type", "recency"}

VALID_CRITICALITY = set(DEFAULT_CRITICALITY_VALUES.keys())
VALID_CLAIM_TYPES = set(DEFAULT_CLAIM_TYPE_VALUES.keys())

EPS = 1e-6


# ────────────────────────────────────────────────────────────────────
# Domain dataclasses
# ────────────────────────────────────────────────────────────────────

@dataclass
class WeightConfig:
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    tier_values: dict[int, float] = field(default_factory=lambda: dict(DEFAULT_TIER_VALUES))
    claim_type_values: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_CLAIM_TYPE_VALUES))
    criticality_values: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_CRITICALITY_VALUES))
    recency_half_life_days: float = DEFAULT_RECENCY_HALF_LIFE_DAYS
    config_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "config_id": str(self.config_id) if self.config_id else None,
            "weights": dict(self.weights),
            "tier_values": {str(k): v for k, v in self.tier_values.items()},
            "claim_type_values": dict(self.claim_type_values),
            "criticality_values": dict(self.criticality_values),
            "recency_half_life_days": self.recency_half_life_days,
        }


@dataclass
class MaterialityFactor:
    factor: str
    input_value: Any
    factor_value: float
    weight: float
    contribution: float  # 100 × weight × factor_value

    def to_dict(self) -> dict:
        return {
            "input": self.input_value,
            "value": round(self.factor_value, 4),
            "weight": round(self.weight, 4),
            "contribution": round(self.contribution, 4),
        }


@dataclass
class MaterialityResult:
    score: float                              # 0-100, clamped
    factors: dict[str, MaterialityFactor]
    score_method: str = "factor_attributed_v1"
    weights_config_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "materiality_score": round(self.score, 2),
            "materiality_factors": {k: v.to_dict() for k, v in self.factors.items()},
            "score_method": self.score_method,
            "weights_config_id": str(self.weights_config_id) if self.weights_config_id else None,
        }


# ────────────────────────────────────────────────────────────────────
# Validation helpers
# ────────────────────────────────────────────────────────────────────

def validate_weights(weights: dict) -> None:
    """Weights must contain the 4 required keys, all ≥ 0, summing to 1.0."""
    if not isinstance(weights, dict):
        raise ValueError("weights must be a dict")
    missing = REQUIRED_WEIGHT_KEYS - set(weights.keys())
    if missing:
        raise ValueError(f"weights missing required keys: {sorted(missing)}")
    extra = set(weights.keys()) - REQUIRED_WEIGHT_KEYS
    if extra:
        raise ValueError(f"weights has unknown keys: {sorted(extra)}")
    total = 0.0
    for k in REQUIRED_WEIGHT_KEYS:
        v = weights[k]
        if not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ValueError(f"weights[{k!r}] must be a finite number")
        if v < 0:
            raise ValueError(f"weights[{k!r}] must be ≥ 0")
        total += float(v)
    if abs(total - 1.0) > EPS:
        raise ValueError(f"weights must sum to 1.0 (got {total:.6f})")


def validate_factor_values(values: dict, name: str) -> None:
    if not isinstance(values, dict) or not values:
        raise ValueError(f"{name} must be a non-empty dict")
    for k, v in values.items():
        if not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ValueError(f"{name}[{k!r}] must be a finite number")
        if not (0 <= v <= 1):
            raise ValueError(f"{name}[{k!r}] must be in [0, 1]")


# ────────────────────────────────────────────────────────────────────
# Pure scorer
# ────────────────────────────────────────────────────────────────────

def _recency_factor(age_days: float, half_life_days: float) -> float:
    """Exponential decay; returns 1.0 at 0 days, 0.5 at half_life."""
    if age_days < 0:
        # Future-dated signals: clamp to 1.0 (max recency)
        age_days = 0.0
    return math.exp(-math.log(2) * age_days / half_life_days)


def _coerce_int_tier(tier: Any) -> int:
    """Tier values are stored as keyed by string OR int; normalize to int."""
    try:
        return int(tier)
    except (TypeError, ValueError):
        return -1


def compute_materiality(
    *,
    source_tier: Optional[int],
    entity_criticality: Optional[str],
    claim_type: Optional[str],
    age_days: Optional[float],
    config: Optional[WeightConfig] = None,
) -> MaterialityResult:
    """Pure computation. Missing inputs fall back to:
      - source_tier missing → tier 3 (scientific & conference) value
      - entity_criticality missing/unknown → 'other'
      - claim_type missing/unknown → 'other'
      - age_days missing → 0 (treat as fresh)
    """
    cfg = config or WeightConfig()

    # Source tier
    tier_int = _coerce_int_tier(source_tier) if source_tier is not None else 3
    tier_keyed = cfg.tier_values
    # tier_values keys may be strings (from JSON) or ints; try both
    tier_value = tier_keyed.get(tier_int)
    if tier_value is None:
        tier_value = tier_keyed.get(str(tier_int))
    if tier_value is None:
        tier_value = 0.4  # documented default for tier 3
    tier_factor = MaterialityFactor(
        factor="source_tier",
        input_value=tier_int,
        factor_value=float(tier_value),
        weight=cfg.weights["source_tier"],
        contribution=100 * cfg.weights["source_tier"] * float(tier_value),
    )

    # Entity criticality
    crit_kind = (entity_criticality or "other").strip().lower()
    if crit_kind not in cfg.criticality_values:
        crit_kind = "other"
    crit_value = cfg.criticality_values.get(crit_kind, 0.2)
    crit_factor = MaterialityFactor(
        factor="entity_criticality",
        input_value=crit_kind,
        factor_value=float(crit_value),
        weight=cfg.weights["entity_criticality"],
        contribution=100 * cfg.weights["entity_criticality"] * float(crit_value),
    )

    # Claim type
    ct = (claim_type or "other").strip().lower()
    if ct not in cfg.claim_type_values:
        ct_used = "other"
    else:
        ct_used = ct
    ct_value = cfg.claim_type_values.get(ct_used, 0.3)
    ct_factor = MaterialityFactor(
        factor="claim_type",
        input_value=ct_used,
        factor_value=float(ct_value),
        weight=cfg.weights["claim_type"],
        contribution=100 * cfg.weights["claim_type"] * float(ct_value),
    )

    # Recency
    age = float(age_days) if age_days is not None else 0.0
    rec_value = _recency_factor(age, cfg.recency_half_life_days)
    rec_factor = MaterialityFactor(
        factor="recency",
        input_value={"days": age},
        factor_value=rec_value,
        weight=cfg.weights["recency"],
        contribution=100 * cfg.weights["recency"] * rec_value,
    )

    score = (tier_factor.contribution + crit_factor.contribution +
             ct_factor.contribution + rec_factor.contribution)
    score = max(0.0, min(100.0, score))

    return MaterialityResult(
        score=score,
        factors={
            "source_tier": tier_factor,
            "entity_criticality": crit_factor,
            "claim_type": ct_factor,
            "recency": rec_factor,
        },
        weights_config_id=cfg.config_id,
    )


# ────────────────────────────────────────────────────────────────────
# DB helpers — config CRUD
# ────────────────────────────────────────────────────────────────────

def _row_to_config(row: dict) -> WeightConfig:
    def _parse(v, default):
        if v is None: return default
        if isinstance(v, (dict, list)): return v
        if isinstance(v, str):
            try: return json.loads(v)
            except (TypeError, ValueError): return default
        return default

    weights = _parse(row.get("weights_jsonb"), DEFAULT_WEIGHTS)
    tier = _parse(row.get("tier_values_jsonb"), DEFAULT_TIER_VALUES)
    # tier keys may be strings from JSON; normalize keys to int
    tier_norm = {}
    for k, v in tier.items():
        try: tier_norm[int(k)] = float(v)
        except (TypeError, ValueError): pass
    return WeightConfig(
        weights=weights,
        tier_values=tier_norm,
        claim_type_values=_parse(row.get("claim_type_values_jsonb"), DEFAULT_CLAIM_TYPE_VALUES),
        criticality_values=_parse(row.get("criticality_values_jsonb"), DEFAULT_CRITICALITY_VALUES),
        recency_half_life_days=float(row.get("recency_half_life_days") or DEFAULT_RECENCY_HALF_LIFE_DAYS),
        config_id=str(row["config_id"]),
    )


def get_active_config(db) -> WeightConfig:
    """Fetch the active weight config; returns code defaults if no row."""
    try:
        row = db.fetch_one(
            """
            SELECT config_id, weights_jsonb, tier_values_jsonb,
                   claim_type_values_jsonb, criticality_values_jsonb,
                   recency_half_life_days
              FROM materiality_weight_config
             WHERE is_active = TRUE
             LIMIT 1
            """
        )
    except Exception as exc:
        logger.warning("get_active_config DB read failed; falling back to defaults: %s", exc)
        return WeightConfig()
    if not row:
        return WeightConfig()
    return _row_to_config(row)


def replace_active_config(
    db,
    *,
    weights: dict,
    tier_values: dict,
    claim_type_values: dict,
    criticality_values: dict,
    recency_half_life_days: float,
    user_id: Optional[str] = None,
) -> WeightConfig:
    """Replace the active config: deactivate current, insert new active."""
    validate_weights(weights)
    validate_factor_values(tier_values, "tier_values")
    validate_factor_values(claim_type_values, "claim_type_values")
    validate_factor_values(criticality_values, "criticality_values")
    if recency_half_life_days <= 0 or recency_half_life_days > 3650:
        raise ValueError("recency_half_life_days must be in (0, 3650]")

    # Deactivate previous
    db.execute(
        "UPDATE materiality_weight_config SET is_active = FALSE WHERE is_active = TRUE",
    )
    row = db.fetch_one(
        """
        INSERT INTO materiality_weight_config (
            is_active, weights_jsonb, tier_values_jsonb,
            claim_type_values_jsonb, criticality_values_jsonb,
            recency_half_life_days, created_by_user_id
        ) VALUES (TRUE, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s)
        RETURNING config_id, weights_jsonb, tier_values_jsonb,
                  claim_type_values_jsonb, criticality_values_jsonb,
                  recency_half_life_days
        """,
        (
            json.dumps(weights),
            json.dumps({str(k): v for k, v in tier_values.items()}),
            json.dumps(claim_type_values),
            json.dumps(criticality_values),
            recency_half_life_days,
            user_id,
        ),
    )
    if not row:
        raise RuntimeError("replace_active_config: insert returned no row")
    return _row_to_config(row)


# ────────────────────────────────────────────────────────────────────
# Persist score to signals table
# ────────────────────────────────────────────────────────────────────

def persist_score_to_signal(db, *, signal_id: str, result: MaterialityResult) -> None:
    """Update signals.materiality_factors (and score if the column exists).

    Best-effort (failure is non-fatal — caller still gets the computed
    result). The base `signals` table only has `materiality_factors` (added
    by migration 058); `materiality_score` is an optional column some
    deployments add. We always write `materiality_factors` (the contract the
    frontend reads, summing factor contributions) and additionally write
    `materiality_score` when that column is present.
    """
    factors_json = json.dumps({k: v.to_dict() for k, v in result.factors.items()})
    try:
        db.execute(
            """
            UPDATE signals
               SET materiality_score = %s,
                   materiality_factors = %s::jsonb
             WHERE id::text = %s
            """,
            (int(round(result.score)), factors_json, str(signal_id)),
        )
        return
    except Exception as exc:
        # Most likely the optional `materiality_score` column is absent.
        # Fall back to writing only the factor breakdown, which is the
        # column the UI actually reads.
        logger.debug(
            "persist_score_to_signal: score+factors write failed (%s); "
            "retrying factors-only for signal %s",
            exc,
            signal_id,
        )
    try:
        db.execute(
            """
            UPDATE signals
               SET materiality_factors = %s::jsonb
             WHERE id::text = %s
            """,
            (factors_json, str(signal_id)),
        )
    except Exception as exc:
        logger.warning("persist_score_to_signal failed for signal %s: %s", signal_id, exc)


# ────────────────────────────────────────────────────────────────────
# Signal → scorer-input mapping (for batch (re)scoring of real signals)
# ────────────────────────────────────────────────────────────────────
#
# The factor-attributed scorer (compute_materiality) takes typed inputs
# (source_tier, entity_criticality, claim_type, age_days). Real signals
# don't carry those directly — they carry kbq_tags, an event source_tier,
# confidence_tier, impact_tier, and created_at. These helpers derive the
# scorer inputs from a signal row so historical/ongoing signals get a real
# materiality breakdown instead of a NULL factors column.
#
# ROOT-CAUSE NOTE: before this, `materiality_factors` was only ever written
# by the manual POST /materiality/score endpoint, so in production every
# signal had NULL factors. The UI then fell back to the raw `impact_score`
# fraction (0..1), which renders as a degenerate "~1%" for every signal.
# Populating real factors here is the deferred "batch re-score" from
# SPEC_031 (Out of scope → now in scope as a bounded, idempotent job).

# kbq_tag → claim_type. kbq_tags is the per-signal classification the
# intelligence layer assigns; map the strongest tag to a claim_type the
# scorer values. Order in _KBQ_PRIORITY decides which tag wins when a
# signal carries several.
_KBQ_TO_CLAIM_TYPE: dict[str, str] = {
    "clinical":       "clinical_readout",
    "regulatory":     "regulatory_action",
    "safety":         "safety_signal",
    "pricing_access": "pricing_change",
    "pricing":        "pricing_change",
    "m_and_a":        "pipeline_update",
    "strategic":      "pipeline_update",
    "product":        "pipeline_update",
    "financial":      "earnings_commentary",
    "governance":     "earnings_commentary",
}

# When a signal has multiple kbq_tags, the most material claim wins.
_KBQ_PRIORITY: tuple[str, ...] = (
    "clinical", "regulatory", "safety", "pricing_access", "pricing",
    "m_and_a", "strategic", "product", "financial", "governance",
)


def kbq_tags_to_claim_type(kbq_tags: Optional[list]) -> str:
    """Pick the most material claim_type from a signal's kbq_tags.

    Returns 'other' when there are no tags or none map (the scorer then
    applies the 'other' value, never a silent zero — SPEC_031 R3)."""
    if not kbq_tags:
        return "other"
    tags = {str(t).strip().lower() for t in kbq_tags if t}
    for tag in _KBQ_PRIORITY:
        if tag in tags and tag in _KBQ_TO_CLAIM_TYPE:
            return _KBQ_TO_CLAIM_TYPE[tag]
    # Fall back to any mapped tag, else 'other'
    for tag in tags:
        if tag in _KBQ_TO_CLAIM_TYPE:
            return _KBQ_TO_CLAIM_TYPE[tag]
    return "other"


def normalize_source_tier(raw: Any) -> Optional[int]:
    """Coerce an event source_tier to the int 1-4 the scorer expects.

    Accepts ints (3), numeric strings ("3"), and labelled strings
    ("tier_3", "tier 2"). Returns None when nothing parseable — caller
    then uses the scorer's documented tier-3 default."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)) and math.isfinite(raw):
        t = int(raw)
        return t if 1 <= t <= 4 else None
    if isinstance(raw, str):
        s = raw.strip().lower().replace("tier", "").replace("_", " ").strip()
        for token in s.split():
            try:
                t = int(token)
            except ValueError:
                continue
            if 1 <= t <= 4:
                return t
    return None


def derive_signal_inputs(row: dict) -> dict:
    """Map a signal (joined with its event's source_tier) to scorer inputs.

    Expected keys on `row`: kbq_tags, source_tier (event), age_days.
    entity_criticality has no per-signal source in the current schema, so
    it defaults to 'other' (the scorer's conservative floor) — the spread
    still comes from claim_type · source_tier · recency. When a watchlist /
    focal mapping exists later, thread it in here.
    """
    return {
        "source_tier": normalize_source_tier(row.get("source_tier")),
        "entity_criticality": (row.get("entity_criticality") or "other"),
        "claim_type": kbq_tags_to_claim_type(row.get("kbq_tags")),
        "age_days": row.get("age_days"),
    }


@dataclass
class RescoreStats:
    scanned: int = 0
    scored: int = 0
    skipped: int = 0
    min_score: Optional[float] = None
    max_score: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "scanned": self.scanned,
            "scored": self.scored,
            "skipped": self.skipped,
            "min_score": round(self.min_score, 2) if self.min_score is not None else None,
            "max_score": round(self.max_score, 2) if self.max_score is not None else None,
        }


def recompute_signal_scores(
    db,
    *,
    limit: int = 500,
    force: bool = False,
    config: Optional[WeightConfig] = None,
) -> RescoreStats:
    """Bounded, idempotent (re)score of real signals → materiality_factors.

    - Selects up to `limit` signals. By default only signals whose
      `materiality_factors` is NULL (idempotent: a second run is a no-op
      once everything is scored). `force=True` re-scores everything in the
      window (e.g. after a weights change).
    - Derives scorer inputs from each signal's real fields (kbq_tags →
      claim_type, event source_tier, created_at → age_days) and persists
      the factor breakdown via persist_score_to_signal.
    - Returns a RescoreStats with the resulting score range so the caller
      can confirm a real spread (not a constant).
    """
    cfg = config or get_active_config(db)
    where = "" if force else "WHERE s.materiality_factors IS NULL"
    rows = db.fetch_all(
        f"""
        SELECT s.id::text                                       AS id,
               s.kbq_tags                                       AS kbq_tags,
               e.source_tier                                    AS source_tier,
               EXTRACT(EPOCH FROM (NOW() - s.created_at)) / 86400.0 AS age_days
          FROM signals s
          LEFT JOIN market_events e ON s.event_id = e.id
          {where}
         ORDER BY s.created_at DESC
         LIMIT %s
        """,
        (int(limit),),
    ) or []

    stats = RescoreStats(scanned=len(rows))
    for row in rows:
        inputs = derive_signal_inputs(dict(row))
        result = compute_materiality(
            source_tier=inputs["source_tier"],
            entity_criticality=inputs["entity_criticality"],
            claim_type=inputs["claim_type"],
            age_days=inputs["age_days"],
            config=cfg,
        )
        persist_score_to_signal(db, signal_id=row["id"], result=result)
        stats.scored += 1
        stats.min_score = result.score if stats.min_score is None else min(stats.min_score, result.score)
        stats.max_score = result.score if stats.max_score is None else max(stats.max_score, result.score)
    stats.skipped = stats.scanned - stats.scored
    return stats
