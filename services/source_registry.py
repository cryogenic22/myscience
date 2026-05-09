"""SPEC_027 — Source Registry + 5-dim quality scoring.

Per-source identity + license posture + computed quality score driven by
five dimensions: coverage, latency, predictive_accuracy, stability,
license_health.

Quality computation reads what's available in the DB (evidence_records,
decisions, sources own row) and falls back to documented defaults when
ground-truth signals are missing. The Learning Service (SPEC-028) will
later sharpen `predictive_accuracy` and the connector lifecycle plumbing
(deferred) will sharpen `latency` + `stability`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
# Constants
# ────────────────────────────────────────────────────────────────────

VALID_KINDS = {"free", "paid", "internal"}
VALID_LICENSE_STATUSES = {"active", "expired", "rate_limited", "not_applicable"}
VALID_TIERS = {1, 2, 3, 4}

# Default per-tier coverage when there's no learned signal yet.
_TIER_COVERAGE_DEFAULTS = {1: 0.7, 2: 0.5, 3: 0.3, 4: 0.5}

# Weights for overall_score = Σ (weight × dimension)
QUALITY_WEIGHTS = {
    "coverage":             0.25,
    "latency":              0.20,
    "predictive_accuracy":  0.30,
    "stability":            0.15,
    "license_health":       0.10,
}

# Latency p95 above this caps the latency_score at 0
LATENCY_FLOOR_MS = 24 * 3600 * 1000  # 24 hours

# License renewal window: within this many days of renewal, score degrades linearly
LICENSE_RENEWAL_WINDOW_DAYS = 30


# ────────────────────────────────────────────────────────────────────
# Domain dataclasses
# ────────────────────────────────────────────────────────────────────

@dataclass
class QualityDimensions:
    coverage: Optional[float] = None
    latency_p95_ms: Optional[int] = None
    latency_score: Optional[float] = None
    predictive_accuracy: Optional[float] = None
    stability_score: Optional[float] = None
    license_health_score: Optional[float] = None
    overall_score: Optional[float] = None
    inputs: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "coverage": self.coverage,
            "latency_p95_ms": self.latency_p95_ms,
            "latency_score": self.latency_score,
            "predictive_accuracy": self.predictive_accuracy,
            "stability_score": self.stability_score,
            "license_health_score": self.license_health_score,
            "overall_score": self.overall_score,
            "inputs": self.inputs,
        }


@dataclass
class Source:
    source_id: str
    display_name: str
    tier: int
    kind: str
    base_url: Optional[str]
    description: Optional[str]
    active: bool
    license_status: str
    license_renewal_at: Optional[datetime]
    rate_limit_per_min: Optional[int]
    usage_profile: dict
    latest_quality_id: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    latest_quality: Optional[QualityDimensions] = None

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "display_name": self.display_name,
            "tier": self.tier,
            "kind": self.kind,
            "base_url": self.base_url,
            "description": self.description,
            "active": self.active,
            "license_status": self.license_status,
            "license_renewal_at": self.license_renewal_at.isoformat() if self.license_renewal_at else None,
            "rate_limit_per_min": self.rate_limit_per_min,
            "usage_profile": self.usage_profile or {},
            "latest_quality_id": str(self.latest_quality_id) if self.latest_quality_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "latest_quality": self.latest_quality.to_dict() if self.latest_quality else None,
        }


# ────────────────────────────────────────────────────────────────────
# Errors
# ────────────────────────────────────────────────────────────────────

class SourceNotFound(Exception):
    pass


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────

def _row_to_source(row: dict, latest_quality: Optional[QualityDimensions] = None) -> Source:
    profile = row.get("usage_profile") or {}
    if isinstance(profile, str):
        try: profile = json.loads(profile)
        except (TypeError, ValueError): profile = {}
    return Source(
        source_id=row["source_id"],
        display_name=row["display_name"],
        tier=row["tier"],
        kind=row.get("kind") or "free",
        base_url=row.get("base_url"),
        description=row.get("description"),
        active=bool(row.get("active", True)),
        license_status=row.get("license_status") or "not_applicable",
        license_renewal_at=row.get("license_renewal_at"),
        rate_limit_per_min=row.get("rate_limit_per_min"),
        usage_profile=profile,
        latest_quality_id=str(row["latest_quality_id"]) if row.get("latest_quality_id") else None,
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
        latest_quality=latest_quality,
    )


def _row_to_quality(row: dict) -> QualityDimensions:
    inputs = row.get("inputs_jsonb") or {}
    if isinstance(inputs, str):
        try: inputs = json.loads(inputs)
        except (TypeError, ValueError): inputs = {}
    return QualityDimensions(
        coverage=row.get("coverage"),
        latency_p95_ms=row.get("latency_p95_ms"),
        latency_score=row.get("latency_score"),
        predictive_accuracy=row.get("predictive_accuracy"),
        stability_score=row.get("stability_score"),
        license_health_score=row.get("license_health_score"),
        overall_score=row.get("overall_score"),
        inputs=inputs,
    )


def _validate_register_inputs(*, source_id: str, display_name: str, tier: int,
                              kind: str, license_status: str) -> None:
    if not source_id or not source_id.strip():
        raise ValueError("source_id required")
    if not display_name or not display_name.strip():
        raise ValueError("display_name required")
    if tier not in VALID_TIERS:
        raise ValueError(f"tier must be in {sorted(VALID_TIERS)}")
    if kind not in VALID_KINDS:
        raise ValueError(f"kind must be in {sorted(VALID_KINDS)}")
    if license_status not in VALID_LICENSE_STATUSES:
        raise ValueError(f"license_status must be in {sorted(VALID_LICENSE_STATUSES)}")


# ────────────────────────────────────────────────────────────────────
# Pure dimension scorers (testable in isolation)
# ────────────────────────────────────────────────────────────────────

def score_license_health(
    license_status: str,
    license_renewal_at: Optional[datetime],
    *,
    now: Optional[datetime] = None,
    window_days: int = LICENSE_RENEWAL_WINDOW_DAYS,
) -> float:
    """Map license posture to 0-1.

    - active                             → 1.0 (or linearly degraded in renewal window)
    - expired                            → 0.0
    - rate_limited                       → 0.5
    - not_applicable                     → 1.0 (free sources are always healthy)
    """
    if license_status == "expired":
        return 0.0
    if license_status == "rate_limited":
        return 0.5
    if license_status == "not_applicable":
        return 1.0
    # active
    if license_renewal_at is None:
        return 1.0
    now = now or datetime.now(timezone.utc)
    if license_renewal_at.tzinfo is None:
        license_renewal_at = license_renewal_at.replace(tzinfo=timezone.utc)
    delta_days = (license_renewal_at - now).total_seconds() / 86400.0
    if delta_days <= 0:
        return 0.0
    if delta_days >= window_days:
        return 1.0
    # Linear degradation as renewal approaches: window_days → 1.0, 0 days → 0.0
    return max(0.0, min(1.0, delta_days / window_days))


def score_latency(latency_p95_ms: Optional[int]) -> tuple[Optional[int], float]:
    """Map a p95 latency in ms to a 0-1 score (1 = freshest).

    Returns (latency_p95_ms, score). Falls back to 0.5 if no data.
    """
    if latency_p95_ms is None or latency_p95_ms < 0:
        return None, 0.5
    if latency_p95_ms >= LATENCY_FLOOR_MS:
        return latency_p95_ms, 0.0
    # Linear: 0 ms → 1.0, LATENCY_FLOOR → 0.0
    score = 1.0 - (latency_p95_ms / LATENCY_FLOOR_MS)
    return latency_p95_ms, max(0.0, min(1.0, score))


def score_coverage_default_for_tier(tier: int) -> float:
    return _TIER_COVERAGE_DEFAULTS.get(tier, 0.5)


def compute_overall(
    coverage: Optional[float],
    latency_score: Optional[float],
    predictive_accuracy: Optional[float],
    stability_score: Optional[float],
    license_health_score: Optional[float],
) -> float:
    """Weighted average of the 5 dimensions. Missing dims contribute 0.5
    (neutral) so we don't punish sources for unknown dims."""
    def _v(x): return 0.5 if x is None else max(0.0, min(1.0, float(x)))
    score = (
        QUALITY_WEIGHTS["coverage"]            * _v(coverage)            +
        QUALITY_WEIGHTS["latency"]             * _v(latency_score)       +
        QUALITY_WEIGHTS["predictive_accuracy"] * _v(predictive_accuracy) +
        QUALITY_WEIGHTS["stability"]           * _v(stability_score)     +
        QUALITY_WEIGHTS["license_health"]      * _v(license_health_score)
    )
    return max(0.0, min(1.0, score))


# ────────────────────────────────────────────────────────────────────
# Service
# ────────────────────────────────────────────────────────────────────

class SourceRegistryService:

    @staticmethod
    def register(
        db,
        *,
        source_id: str,
        display_name: str,
        tier: int,
        kind: str = "free",
        base_url: Optional[str] = None,
        description: Optional[str] = None,
        license_status: str = "not_applicable",
        license_renewal_at: Optional[datetime] = None,
        rate_limit_per_min: Optional[int] = None,
        usage_profile: Optional[dict] = None,
    ) -> Source:
        """Idempotent register. Same source_id → existing row returned.
        Use PATCH to update."""
        _validate_register_inputs(
            source_id=source_id, display_name=display_name, tier=tier,
            kind=kind, license_status=license_status,
        )

        existing = db.fetch_one(
            """
            SELECT source_id, display_name, tier, kind, base_url, description,
                   active, license_status, license_renewal_at, rate_limit_per_min,
                   usage_profile, latest_quality_id, created_at, updated_at
              FROM sources WHERE source_id = %s
            """,
            (source_id,),
        )
        if existing:
            return _row_to_source(existing)

        row = db.fetch_one(
            """
            INSERT INTO sources (
                source_id, display_name, tier, kind, base_url, description,
                license_status, license_renewal_at, rate_limit_per_min, usage_profile
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING source_id, display_name, tier, kind, base_url, description,
                      active, license_status, license_renewal_at, rate_limit_per_min,
                      usage_profile, latest_quality_id, created_at, updated_at
            """,
            (
                source_id, display_name, tier, kind, base_url, description,
                license_status, license_renewal_at, rate_limit_per_min,
                json.dumps(usage_profile or {}),
            ),
        )
        if not row:
            raise RuntimeError("register: insert returned no row")
        return _row_to_source(row)

    @staticmethod
    def get(db, source_id: str) -> Optional[Source]:
        row = db.fetch_one(
            """
            SELECT source_id, display_name, tier, kind, base_url, description,
                   active, license_status, license_renewal_at, rate_limit_per_min,
                   usage_profile, latest_quality_id, created_at, updated_at
              FROM sources WHERE source_id = %s
            """,
            (source_id,),
        )
        if not row:
            return None
        latest_quality = None
        if row.get("latest_quality_id"):
            qrow = db.fetch_one(
                """
                SELECT coverage, latency_p95_ms, latency_score, predictive_accuracy,
                       stability_score, license_health_score, overall_score, inputs_jsonb
                  FROM source_quality_history
                 WHERE quality_id::text = %s
                """,
                (str(row["latest_quality_id"]),),
            )
            if qrow:
                latest_quality = _row_to_quality(qrow)
        return _row_to_source(row, latest_quality=latest_quality)

    @staticmethod
    def list(
        db,
        *,
        tier: Optional[int] = None,
        kind: Optional[str] = None,
        active: Optional[bool] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Source]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be in [1, 500]")
        if tier is not None and tier not in VALID_TIERS:
            raise ValueError(f"tier must be in {sorted(VALID_TIERS)}")
        if kind is not None and kind not in VALID_KINDS:
            raise ValueError(f"kind must be in {sorted(VALID_KINDS)}")

        where = ["1=1"]
        params: list[Any] = []
        if tier is not None:
            where.append("tier = %s")
            params.append(tier)
        if kind is not None:
            where.append("kind = %s")
            params.append(kind)
        if active is not None:
            where.append("active = %s")
            params.append(active)
        params.extend([limit, offset])
        rows = db.fetch_all(
            f"""
            SELECT s.source_id, s.display_name, s.tier, s.kind, s.base_url,
                   s.description, s.active, s.license_status, s.license_renewal_at,
                   s.rate_limit_per_min, s.usage_profile, s.latest_quality_id,
                   s.created_at, s.updated_at,
                   q.coverage, q.latency_p95_ms, q.latency_score,
                   q.predictive_accuracy, q.stability_score,
                   q.license_health_score, q.overall_score, q.inputs_jsonb
              FROM sources s
         LEFT JOIN source_quality_history q ON q.quality_id = s.latest_quality_id
             WHERE {' AND '.join(where)}
             ORDER BY s.tier ASC, s.source_id ASC
             LIMIT %s OFFSET %s
            """,
            tuple(params),
        ) or []
        out = []
        for r in rows:
            quality = None
            if any(r.get(k) is not None for k in ("coverage", "overall_score")):
                quality = _row_to_quality(r)
            out.append(_row_to_source(r, latest_quality=quality))
        return out

    @staticmethod
    def update(
        db,
        source_id: str,
        *,
        display_name: Optional[str] = None,
        active: Optional[bool] = None,
        license_status: Optional[str] = None,
        license_renewal_at: Optional[datetime] = None,
        rate_limit_per_min: Optional[int] = None,
        usage_profile: Optional[dict] = None,
        description: Optional[str] = None,
    ) -> Source:
        existing = SourceRegistryService.get(db, source_id)
        if not existing:
            raise SourceNotFound(source_id)
        if license_status is not None and license_status not in VALID_LICENSE_STATUSES:
            raise ValueError(f"license_status must be in {sorted(VALID_LICENSE_STATUSES)}")
        sets: list[str] = []
        params: list[Any] = []
        if display_name is not None:
            sets.append("display_name = %s"); params.append(display_name)
        if active is not None:
            sets.append("active = %s"); params.append(active)
        if license_status is not None:
            sets.append("license_status = %s"); params.append(license_status)
        if license_renewal_at is not None:
            sets.append("license_renewal_at = %s"); params.append(license_renewal_at)
        if rate_limit_per_min is not None:
            sets.append("rate_limit_per_min = %s"); params.append(rate_limit_per_min)
        if usage_profile is not None:
            sets.append("usage_profile = %s::jsonb"); params.append(json.dumps(usage_profile))
        if description is not None:
            sets.append("description = %s"); params.append(description)
        if not sets:
            return existing
        params.append(source_id)
        db.execute(
            f"UPDATE sources SET {', '.join(sets)} WHERE source_id = %s",
            tuple(params),
        )
        return SourceRegistryService.get(db, source_id) or existing

    @staticmethod
    def recompute_quality(db, source_id: str) -> QualityDimensions:
        """Compute and persist a fresh quality row for the source.
        Returns the computed dimensions."""
        src = SourceRegistryService.get(db, source_id)
        if not src:
            raise SourceNotFound(source_id)

        inputs: dict = {}

        # license_health_score
        license_health = score_license_health(src.license_status, src.license_renewal_at)
        inputs["license"] = {
            "status": src.license_status,
            "renewal_at": src.license_renewal_at.isoformat() if src.license_renewal_at else None,
        }

        # coverage default by tier (until SPEC-028 wires real ground truth)
        coverage = score_coverage_default_for_tier(src.tier)
        inputs["coverage"] = {"method": "tier_default", "tier": src.tier}

        # latency: median lag from evidence_records.retrieved_at vs created_at,
        # bounded to last 1000 rows for cost control. Falls back to 0.5.
        try:
            lat_row = db.fetch_one(
                """
                SELECT percentile_cont(0.95) WITHIN GROUP
                       (ORDER BY EXTRACT(EPOCH FROM (created_at - retrieved_at)) * 1000) AS p95_ms
                  FROM (
                    SELECT created_at, retrieved_at
                      FROM evidence_records
                     WHERE source_id = %s
                       AND retrieved_at IS NOT NULL
                     ORDER BY created_at DESC
                     LIMIT 1000
                  ) recent
                """,
                (source_id,),
            )
            p95 = lat_row.get("p95_ms") if lat_row else None
            p95_int = int(p95) if p95 is not None else None
        except Exception as exc:
            logger.warning("latency query failed (falling back to default): %s", exc)
            p95_int = None
        latency_p95_ms, latency_score = score_latency(p95_int)
        inputs["latency"] = {"p95_ms": latency_p95_ms, "method": "evidence_records_p95"}

        # predictive_accuracy: deferred to SPEC-028; default 0.5
        predictive_accuracy = 0.5
        inputs["predictive_accuracy"] = {"method": "default_pending_spec_028"}

        # stability_score: stub — 1.0 if active, 0.0 if not. SPEC-028 will
        # use connector lifecycle event log when that lands.
        stability_score = 1.0 if src.active else 0.0
        inputs["stability"] = {"method": "active_flag", "active": src.active}

        overall = compute_overall(
            coverage=coverage,
            latency_score=latency_score,
            predictive_accuracy=predictive_accuracy,
            stability_score=stability_score,
            license_health_score=license_health,
        )

        row = db.fetch_one(
            """
            INSERT INTO source_quality_history (
                source_id, coverage, latency_p95_ms, latency_score,
                predictive_accuracy, stability_score, license_health_score,
                overall_score, inputs_jsonb
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING quality_id, computed_at, coverage, latency_p95_ms, latency_score,
                      predictive_accuracy, stability_score, license_health_score,
                      overall_score, inputs_jsonb
            """,
            (
                source_id, coverage, latency_p95_ms, latency_score,
                predictive_accuracy, stability_score, license_health,
                overall, json.dumps(inputs),
            ),
        )
        if not row:
            raise RuntimeError("recompute: insert returned no row")
        # Update the latest pointer
        db.execute(
            "UPDATE sources SET latest_quality_id = %s WHERE source_id = %s",
            (row["quality_id"], source_id),
        )
        return _row_to_quality(row)

    @staticmethod
    def history(db, source_id: str, *, limit: int = 100) -> list[QualityDimensions]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be in [1, 500]")
        rows = db.fetch_all(
            """
            SELECT quality_id, computed_at, coverage, latency_p95_ms, latency_score,
                   predictive_accuracy, stability_score, license_health_score,
                   overall_score, inputs_jsonb
              FROM source_quality_history
             WHERE source_id = %s
             ORDER BY computed_at DESC
             LIMIT %s
            """,
            (source_id, limit),
        ) or []
        out = []
        for r in rows:
            q = _row_to_quality(r)
            # Annotate computed_at into inputs for FE convenience
            d = q.to_dict()
            d["quality_id"] = str(r["quality_id"])
            d["computed_at"] = r["computed_at"].isoformat() if r.get("computed_at") else None
            out.append(d)
        return out

    @staticmethod
    def health_summary(db) -> dict:
        rows = db.fetch_all(
            """
            SELECT s.source_id, s.display_name, s.tier, s.active,
                   q.overall_score
              FROM sources s
         LEFT JOIN source_quality_history q ON q.quality_id = s.latest_quality_id
            """,
            (),
        ) or []
        active_count = sum(1 for r in rows if r.get("active"))
        with_score = [r for r in rows if r.get("overall_score") is not None]
        mean_score = (
            sum(float(r["overall_score"]) for r in with_score) / len(with_score)
            if with_score else None
        )
        bottom = sorted(with_score, key=lambda r: r["overall_score"])[:5]
        return {
            "total_sources": len(rows),
            "active_count": active_count,
            "scored_count": len(with_score),
            "mean_overall_score": round(mean_score, 4) if mean_score is not None else None,
            "bottom_5": [
                {
                    "source_id": r["source_id"],
                    "display_name": r["display_name"],
                    "tier": r["tier"],
                    "overall_score": round(float(r["overall_score"]), 4),
                }
                for r in bottom
            ],
        }
