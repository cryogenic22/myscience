"""SPEC_029 — Framing Triggers.

Auto-create draft Decision Briefs from threshold/cluster/calendar evaluators.
Closes the spec's <24h signal-to-decision latency target by removing the
human-opens-war-room step from the auto-frame path.

The orchestrator is synchronous and idempotent: re-ticking with the same
state is a no-op (dedup rules in spec §Dedup rule). All evaluations are
isolated — a failure in one trigger doesn't abort others.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
# Constants
# ────────────────────────────────────────────────────────────────────

VALID_KINDS = {"threshold", "cluster", "calendar"}
VALID_FIRE_STATUSES = {"success", "skipped_no_match", "skipped_dedup", "failed"}

DEFAULT_THRESHOLD_MIN_SCORE = 80
MIN_THRESHOLD_FLOOR = 50           # sane floor: don't allow misconfigured low thresholds
DEFAULT_CLUSTER_SIZE = 3
DEFAULT_CLUSTER_WINDOW_DAYS = 14
DEFAULT_CALENDAR_INTERVAL_DAYS = 90
MAX_FIRES_PER_TICK = 100           # per-trigger cap; protects against runaway

# Whitelist of allowed config keys per kind (R8 — config injection guard)
ALLOWED_CONFIG_KEYS = {
    "threshold": {"min_materiality_score", "claim_types", "entity_types", "question_template"},
    "cluster":   {"min_cluster_size", "rolling_window_days", "entity_field",
                  "min_total_materiality", "question_template"},
    "calendar":  {"interval_days", "question_template", "default_options_count"},
}


# ────────────────────────────────────────────────────────────────────
# Domain dataclasses
# ────────────────────────────────────────────────────────────────────

@dataclass
class FramingTrigger:
    trigger_id: str
    name: str
    kind: str
    config: dict
    assignee_user_id: Optional[str]
    is_active: bool
    last_evaluated_at: Optional[datetime]
    next_fire_at: Optional[datetime]
    created_by_user_id: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    def to_dict(self) -> dict:
        return {
            "trigger_id": str(self.trigger_id),
            "name": self.name,
            "kind": self.kind,
            "config": self.config or {},
            "assignee_user_id": str(self.assignee_user_id) if self.assignee_user_id else None,
            "is_active": self.is_active,
            "last_evaluated_at": self.last_evaluated_at.isoformat() if self.last_evaluated_at else None,
            "next_fire_at": self.next_fire_at.isoformat() if self.next_fire_at else None,
            "created_by_user_id": str(self.created_by_user_id) if self.created_by_user_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass
class FireResult:
    trigger_id: str
    status: str
    signal_ids: list[str] = field(default_factory=list)
    brief_id: Optional[str] = None
    failure_reason: Optional[str] = None
    fire_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "trigger_id": str(self.trigger_id),
            "status": self.status,
            "signal_ids": [str(s) for s in self.signal_ids],
            "brief_id": str(self.brief_id) if self.brief_id else None,
            "failure_reason": self.failure_reason,
            "fire_id": str(self.fire_id) if self.fire_id else None,
        }


# ────────────────────────────────────────────────────────────────────
# Errors
# ────────────────────────────────────────────────────────────────────

class TriggerNotFound(Exception):
    pass


# ────────────────────────────────────────────────────────────────────
# Validation
# ────────────────────────────────────────────────────────────────────

def validate_config(kind: str, config: dict) -> None:
    if kind not in VALID_KINDS:
        raise ValueError(f"kind must be in {sorted(VALID_KINDS)}")
    if not isinstance(config, dict):
        raise ValueError("config must be a dict")

    allowed = ALLOWED_CONFIG_KEYS[kind]
    extra = set(config.keys()) - allowed
    if extra:
        raise ValueError(f"config has unknown keys for kind={kind}: {sorted(extra)}")

    if kind == "threshold":
        score = config.get("min_materiality_score", DEFAULT_THRESHOLD_MIN_SCORE)
        if not isinstance(score, (int, float)):
            raise ValueError("min_materiality_score must be a number")
        if score < MIN_THRESHOLD_FLOOR:
            raise ValueError(f"min_materiality_score must be >= {MIN_THRESHOLD_FLOOR} (sane floor)")
        if score > 100:
            raise ValueError("min_materiality_score must be <= 100")
        for fld in ("claim_types", "entity_types"):
            if fld in config and not isinstance(config[fld], list):
                raise ValueError(f"{fld} must be a list of strings")

    elif kind == "cluster":
        size = config.get("min_cluster_size", DEFAULT_CLUSTER_SIZE)
        if not isinstance(size, int) or size < 2 or size > 100:
            raise ValueError("min_cluster_size must be int in [2, 100]")
        win = config.get("rolling_window_days", DEFAULT_CLUSTER_WINDOW_DAYS)
        if not isinstance(win, int) or win < 1 or win > 365:
            raise ValueError("rolling_window_days must be int in [1, 365]")
        ef = config.get("entity_field", "entity_id")
        if ef not in {"entity_id", "claim_type"}:
            raise ValueError("entity_field must be 'entity_id' or 'claim_type'")

    elif kind == "calendar":
        interval = config.get("interval_days", DEFAULT_CALENDAR_INTERVAL_DAYS)
        if not isinstance(interval, int) or interval < 1 or interval > 3650:
            raise ValueError("interval_days must be int in [1, 3650]")


# ────────────────────────────────────────────────────────────────────
# Template rendering (safe; no eval)
# ────────────────────────────────────────────────────────────────────

_TEMPLATE_VAR = re.compile(r"\{(\w+)\}")


def render_question(template: str, variables: dict) -> str:
    """Single-pass {var} substitution; missing vars are left as `{var}`
    literal (graceful — the brief still gets a usable question)."""
    if not template:
        return ""
    def _sub(m):
        k = m.group(1)
        v = variables.get(k)
        return str(v) if v is not None else m.group(0)
    return _TEMPLATE_VAR.sub(_sub, template)


# ────────────────────────────────────────────────────────────────────
# DB row helpers
# ────────────────────────────────────────────────────────────────────

def _row_to_trigger(row: dict) -> FramingTrigger:
    cfg = row.get("config_jsonb") or {}
    if isinstance(cfg, str):
        try: cfg = json.loads(cfg)
        except (TypeError, ValueError): cfg = {}
    return FramingTrigger(
        trigger_id=str(row["trigger_id"]),
        name=row["name"],
        kind=row["kind"],
        config=cfg,
        assignee_user_id=str(row["assignee_user_id"]) if row.get("assignee_user_id") else None,
        is_active=bool(row.get("is_active", True)),
        last_evaluated_at=row.get("last_evaluated_at"),
        next_fire_at=row.get("next_fire_at"),
        created_by_user_id=str(row["created_by_user_id"]) if row.get("created_by_user_id") else None,
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


# ────────────────────────────────────────────────────────────────────
# CRUD service
# ────────────────────────────────────────────────────────────────────

class FramingTriggerService:

    @staticmethod
    def create(
        db,
        *,
        name: str,
        kind: str,
        config: dict,
        assignee_user_id: Optional[str] = None,
        created_by_user_id: Optional[str] = None,
    ) -> FramingTrigger:
        validate_config(kind, config)

        next_fire_at = None
        if kind == "calendar":
            interval = config.get("interval_days", DEFAULT_CALENDAR_INTERVAL_DAYS)
            next_fire_at = datetime.now(timezone.utc) + timedelta(days=int(interval))

        row = db.fetch_one(
            """
            INSERT INTO framing_triggers (
                name, kind, config_jsonb, assignee_user_id,
                next_fire_at, created_by_user_id
            ) VALUES (%s, %s, %s::jsonb, %s, %s, %s)
            RETURNING trigger_id, name, kind, config_jsonb, assignee_user_id,
                      is_active, last_evaluated_at, next_fire_at,
                      created_by_user_id, created_at, updated_at
            """,
            (name, kind, json.dumps(config), assignee_user_id,
             next_fire_at, created_by_user_id),
        )
        if not row:
            raise RuntimeError("create: insert returned no row")
        return _row_to_trigger(row)

    @staticmethod
    def get(db, trigger_id: str) -> Optional[FramingTrigger]:
        row = db.fetch_one(
            """
            SELECT trigger_id, name, kind, config_jsonb, assignee_user_id,
                   is_active, last_evaluated_at, next_fire_at,
                   created_by_user_id, created_at, updated_at
              FROM framing_triggers WHERE trigger_id::text = %s
            """,
            (str(trigger_id),),
        )
        return _row_to_trigger(row) if row else None

    @staticmethod
    def list(
        db,
        *,
        kind: Optional[str] = None,
        is_active: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FramingTrigger]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be in [1, 500]")
        if kind is not None and kind not in VALID_KINDS:
            raise ValueError(f"kind must be in {sorted(VALID_KINDS)}")
        where = ["1=1"]
        params: list[Any] = []
        if kind is not None:
            where.append("kind = %s"); params.append(kind)
        if is_active is not None:
            where.append("is_active = %s"); params.append(is_active)
        params.extend([limit, offset])
        rows = db.fetch_all(
            f"""
            SELECT trigger_id, name, kind, config_jsonb, assignee_user_id,
                   is_active, last_evaluated_at, next_fire_at,
                   created_by_user_id, created_at, updated_at
              FROM framing_triggers
             WHERE {' AND '.join(where)}
             ORDER BY created_at DESC
             LIMIT %s OFFSET %s
            """,
            tuple(params),
        ) or []
        return [_row_to_trigger(r) for r in rows]

    @staticmethod
    def update(
        db,
        trigger_id: str,
        *,
        name: Optional[str] = None,
        config: Optional[dict] = None,
        assignee_user_id: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> FramingTrigger:
        existing = FramingTriggerService.get(db, trigger_id)
        if not existing:
            raise TriggerNotFound(trigger_id)
        if config is not None:
            validate_config(existing.kind, config)
        sets: list[str] = []
        params: list[Any] = []
        if name is not None:
            sets.append("name = %s"); params.append(name)
        if config is not None:
            sets.append("config_jsonb = %s::jsonb"); params.append(json.dumps(config))
        if assignee_user_id is not None:
            sets.append("assignee_user_id = %s"); params.append(assignee_user_id)
        if is_active is not None:
            sets.append("is_active = %s"); params.append(is_active)
        if not sets:
            return existing
        params.append(str(trigger_id))
        db.execute(
            f"UPDATE framing_triggers SET {', '.join(sets)} WHERE trigger_id::text = %s",
            tuple(params),
        )
        return FramingTriggerService.get(db, trigger_id) or existing

    @staticmethod
    def delete(db, trigger_id: str) -> None:
        existing = FramingTriggerService.get(db, trigger_id)
        if not existing:
            raise TriggerNotFound(trigger_id)
        db.execute("DELETE FROM framing_triggers WHERE trigger_id::text = %s",
                   (str(trigger_id),))

    @staticmethod
    def list_fires(db, trigger_id: str, *, limit: int = 50) -> list[dict]:
        rows = db.fetch_all(
            """
            SELECT fire_id, trigger_id, fired_at, signal_ids, brief_id,
                   status, failure_reason
              FROM framing_trigger_fires
             WHERE trigger_id::text = %s
             ORDER BY fired_at DESC
             LIMIT %s
            """,
            (str(trigger_id), limit),
        ) or []
        return [
            {
                "fire_id": str(r["fire_id"]),
                "trigger_id": str(r["trigger_id"]),
                "fired_at": r["fired_at"].isoformat() if r.get("fired_at") else None,
                "signal_ids": [str(s) for s in (r.get("signal_ids") or [])],
                "brief_id": str(r["brief_id"]) if r.get("brief_id") else None,
                "status": r["status"],
                "failure_reason": r.get("failure_reason"),
            }
            for r in rows
        ]


# ────────────────────────────────────────────────────────────────────
# Orchestrator — evaluates triggers and creates briefs
# ────────────────────────────────────────────────────────────────────

class FramingOrchestrator:
    """Synchronous orchestrator. Inject a `brief_factory` to keep this
    decoupled from SPEC-023 imports during test."""

    def __init__(self, brief_factory=None):
        # brief_factory(db, *, question, trigger_kind, trigger_signal_ids,
        #               trigger_metadata, owner_user_id, evidence_refs) -> brief_dict
        # Default: import at runtime to avoid circular import on test
        self.brief_factory = brief_factory

    def _create_brief(self, db, **kwargs):
        if self.brief_factory:
            return self.brief_factory(db, **kwargs)
        # Default path — late import
        from services.decision_brief import DecisionBriefService
        return DecisionBriefService.create_draft(db, **kwargs)

    def tick(self, db) -> list[FireResult]:
        """Evaluate all active triggers; return per-trigger result."""
        triggers = FramingTriggerService.list(db, is_active=True, limit=500)
        results: list[FireResult] = []
        for t in triggers:
            try:
                result = self._evaluate_trigger(db, t)
            except Exception as exc:
                logger.exception("trigger %s evaluation crashed: %s", t.trigger_id, exc)
                result = self._record_fire(
                    db, trigger_id=t.trigger_id, status="failed",
                    signal_ids=[], brief_id=None, failure_reason=str(exc)[:500],
                )
            results.append(result)
        return results

    def evaluate_one(self, db, trigger_id: str) -> FireResult:
        t = FramingTriggerService.get(db, trigger_id)
        if not t:
            raise TriggerNotFound(trigger_id)
        return self._evaluate_trigger(db, t)

    # ── internal: per-kind evaluators ──

    def _evaluate_trigger(self, db, t: FramingTrigger) -> FireResult:
        if t.kind == "threshold":
            return self._evaluate_threshold(db, t)
        if t.kind == "cluster":
            return self._evaluate_cluster(db, t)
        if t.kind == "calendar":
            return self._evaluate_calendar(db, t)
        raise ValueError(f"unknown trigger kind: {t.kind}")

    def _evaluate_threshold(self, db, t: FramingTrigger) -> FireResult:
        cfg = t.config or {}
        min_score = cfg.get("min_materiality_score", DEFAULT_THRESHOLD_MIN_SCORE)
        claim_types = cfg.get("claim_types") or []
        entity_types = cfg.get("entity_types") or []
        template = cfg.get("question_template") or "Material signal: {claim_type} on {entity}"

        # Find candidate signals: materiality >= threshold, since last_evaluated_at
        params: list[Any] = [min_score]
        where = ["materiality_score >= %s"]
        if t.last_evaluated_at:
            where.append("created_at > %s")
            params.append(t.last_evaluated_at)
        if claim_types:
            where.append("claim_type = ANY(%s)")
            params.append(list(claim_types))
        if entity_types:
            where.append("entity_type = ANY(%s)")
            params.append(list(entity_types))
        params.append(MAX_FIRES_PER_TICK)

        candidates = db.fetch_all(
            f"""
            SELECT id, claim_type, entity_type, entity_id,
                   materiality_score, headline
              FROM signals
             WHERE {' AND '.join(where)}
             ORDER BY materiality_score DESC, created_at DESC
             LIMIT %s
            """,
            tuple(params),
        ) or []

        if not candidates:
            self._advance_cursor(db, t)
            return self._record_fire(
                db, trigger_id=t.trigger_id, status="skipped_no_match",
                signal_ids=[], brief_id=None,
            )

        # Dedup against prior fires for this trigger
        already_fired = self._signals_already_fired(db, t.trigger_id)

        first_match = None
        for c in candidates:
            sid = str(c["id"])
            if sid in already_fired:
                continue
            first_match = c
            break

        if not first_match:
            self._advance_cursor(db, t)
            return self._record_fire(
                db, trigger_id=t.trigger_id, status="skipped_dedup",
                signal_ids=[str(c["id"]) for c in candidates], brief_id=None,
            )

        sid = str(first_match["id"])
        question = render_question(template, {
            "claim_type": first_match.get("claim_type") or "signal",
            "entity": first_match.get("entity_id") or "(unknown entity)",
            "entity_type": first_match.get("entity_type") or "",
            "headline": first_match.get("headline") or "",
        })

        try:
            brief = self._create_brief(
                db,
                question=question,
                trigger_kind="threshold",
                trigger_signal_ids=[sid],
                trigger_metadata={
                    "trigger_id": str(t.trigger_id),
                    "trigger_name": t.name,
                    "min_materiality_score": min_score,
                    "matched_score": first_match.get("materiality_score"),
                },
                stakeholders=[],
                evidence_refs=[{"type": "signal", "id": sid}],
                owner_user_id=t.assignee_user_id,
            )
            brief_id = brief.brief_id if hasattr(brief, "brief_id") else brief.get("brief_id")
        except Exception as exc:
            self._advance_cursor(db, t)
            return self._record_fire(
                db, trigger_id=t.trigger_id, status="failed",
                signal_ids=[sid], brief_id=None,
                failure_reason=str(exc)[:500],
            )

        self._advance_cursor(db, t)
        return self._record_fire(
            db, trigger_id=t.trigger_id, status="success",
            signal_ids=[sid], brief_id=brief_id,
        )

    def _evaluate_cluster(self, db, t: FramingTrigger) -> FireResult:
        cfg = t.config or {}
        size = cfg.get("min_cluster_size", DEFAULT_CLUSTER_SIZE)
        window = cfg.get("rolling_window_days", DEFAULT_CLUSTER_WINDOW_DAYS)
        entity_field = cfg.get("entity_field", "entity_id")
        min_total = cfg.get("min_total_materiality")
        template = cfg.get("question_template") or "Cluster of {n} signals on {entity}"

        # Group signals by entity_field within rolling window
        having = ["COUNT(*) >= %s"]
        having_params: list[Any] = [size]
        if min_total:
            having.append("COALESCE(SUM(materiality_score), 0) >= %s")
            having_params.append(min_total)

        rows = db.fetch_all(
            f"""
            SELECT {entity_field} AS group_key,
                   array_agg(id::text ORDER BY created_at DESC) AS sids,
                   COUNT(*) AS n,
                   COALESCE(SUM(materiality_score), 0) AS total_score
              FROM signals
             WHERE created_at > NOW() - (%s || ' days')::interval
               AND {entity_field} IS NOT NULL
             GROUP BY {entity_field}
            HAVING {' AND '.join(having)}
             ORDER BY n DESC
             LIMIT %s
            """,
            (window, *having_params, MAX_FIRES_PER_TICK),
        ) or []

        if not rows:
            self._advance_cursor(db, t)
            return self._record_fire(
                db, trigger_id=t.trigger_id, status="skipped_no_match",
                signal_ids=[], brief_id=None,
            )

        # Dedup: skip clusters whose entity already fired within the window
        already = self._signals_already_fired(db, t.trigger_id)

        first = None
        for r in rows:
            sids = [str(s) for s in (r["sids"] or [])]
            if any(s in already for s in sids):
                continue
            first = (r, sids)
            break

        if not first:
            self._advance_cursor(db, t)
            return self._record_fire(
                db, trigger_id=t.trigger_id, status="skipped_dedup",
                signal_ids=[], brief_id=None,
            )

        match_row, sids = first
        question = render_question(template, {
            "n": match_row["n"], "entity": match_row["group_key"] or "(unknown)",
        })

        try:
            brief = self._create_brief(
                db,
                question=question,
                trigger_kind="cluster",
                trigger_signal_ids=sids,
                trigger_metadata={
                    "trigger_id": str(t.trigger_id),
                    "trigger_name": t.name,
                    "cluster_size": match_row["n"],
                    "window_days": window,
                    "total_materiality": float(match_row["total_score"] or 0),
                    "entity_field": entity_field,
                    "group_key": str(match_row["group_key"]) if match_row["group_key"] else None,
                },
                stakeholders=[],
                evidence_refs=[{"type": "signal", "id": s} for s in sids],
                owner_user_id=t.assignee_user_id,
            )
            brief_id = brief.brief_id if hasattr(brief, "brief_id") else brief.get("brief_id")
        except Exception as exc:
            self._advance_cursor(db, t)
            return self._record_fire(
                db, trigger_id=t.trigger_id, status="failed",
                signal_ids=sids, brief_id=None,
                failure_reason=str(exc)[:500],
            )

        self._advance_cursor(db, t)
        return self._record_fire(
            db, trigger_id=t.trigger_id, status="success",
            signal_ids=sids, brief_id=brief_id,
        )

    def _evaluate_calendar(self, db, t: FramingTrigger) -> FireResult:
        now = datetime.now(timezone.utc)
        if t.next_fire_at and now < t.next_fire_at:
            self._advance_cursor(db, t)
            return self._record_fire(
                db, trigger_id=t.trigger_id, status="skipped_no_match",
                signal_ids=[], brief_id=None,
            )

        cfg = t.config or {}
        interval = cfg.get("interval_days", DEFAULT_CALENDAR_INTERVAL_DAYS)
        template = cfg.get("question_template") or "Scheduled review: {name}"
        question = render_question(template, {"name": t.name})

        try:
            brief = self._create_brief(
                db,
                question=question,
                trigger_kind="calendar",
                trigger_signal_ids=[],
                trigger_metadata={
                    "trigger_id": str(t.trigger_id),
                    "trigger_name": t.name,
                    "interval_days": interval,
                },
                stakeholders=[],
                evidence_refs=[],
                owner_user_id=t.assignee_user_id,
            )
            brief_id = brief.brief_id if hasattr(brief, "brief_id") else brief.get("brief_id")
        except Exception as exc:
            return self._record_fire(
                db, trigger_id=t.trigger_id, status="failed",
                signal_ids=[], brief_id=None, failure_reason=str(exc)[:500],
            )

        # Advance next_fire_at
        next_fire = (t.next_fire_at or now) + timedelta(days=interval)
        if next_fire <= now:
            next_fire = now + timedelta(days=interval)
        db.execute(
            """
            UPDATE framing_triggers
               SET next_fire_at = %s, last_evaluated_at = NOW()
             WHERE trigger_id::text = %s
            """,
            (next_fire, str(t.trigger_id)),
        )
        return self._record_fire(
            db, trigger_id=t.trigger_id, status="success",
            signal_ids=[], brief_id=brief_id,
        )

    # ── internal: bookkeeping ──

    def _advance_cursor(self, db, t: FramingTrigger) -> None:
        if t.kind == "calendar":
            return  # calendar handles its own advancement
        db.execute(
            "UPDATE framing_triggers SET last_evaluated_at = NOW() WHERE trigger_id::text = %s",
            (str(t.trigger_id),),
        )

    def _signals_already_fired(self, db, trigger_id: str) -> set[str]:
        rows = db.fetch_all(
            """
            SELECT signal_ids FROM framing_trigger_fires
             WHERE trigger_id::text = %s AND status = 'success'
            """,
            (str(trigger_id),),
        ) or []
        out: set[str] = set()
        for r in rows:
            for s in (r.get("signal_ids") or []):
                out.add(str(s))
        return out

    def _record_fire(
        self,
        db,
        *,
        trigger_id: str,
        status: str,
        signal_ids: list[str],
        brief_id: Optional[str],
        failure_reason: Optional[str] = None,
    ) -> FireResult:
        if status not in VALID_FIRE_STATUSES:
            status = "failed"
        row = db.fetch_one(
            """
            INSERT INTO framing_trigger_fires (
                trigger_id, signal_ids, brief_id, status, failure_reason
            ) VALUES (%s, %s::uuid[], %s, %s, %s)
            RETURNING fire_id
            """,
            (str(trigger_id), [str(s) for s in signal_ids],
             str(brief_id) if brief_id else None, status, failure_reason),
        )
        fire_id = str(row["fire_id"]) if row else None
        return FireResult(
            trigger_id=str(trigger_id),
            status=status,
            signal_ids=[str(s) for s in signal_ids],
            brief_id=str(brief_id) if brief_id else None,
            failure_reason=failure_reason,
            fire_id=fire_id,
        )
