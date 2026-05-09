"""SPEC_032 — Learning Service: close the flywheel.

Reads outcomes from `decisions.calibration_score`, attributes each decision
to its contributing sources via the most-direct chain available, and
updates `sources.predictive_accuracy` via EWMA. Also flags
`prompt_registry` versions whose recent mean calibration is below
threshold (so an admin can review/retire them).

The service is synchronous, idempotent given a correctly-advanced
`since_cursor`, and isolates per-decision failures so a single bad
decision doesn't abort the whole run.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
# Constants (tunable; future config table can override)
# ────────────────────────────────────────────────────────────────────

DEFAULT_EWMA_ALPHA = 0.10
MAX_DECISIONS_PER_RUN = 1000
DEFAULT_LOOKBACK_DAYS = 30
PROMPT_FLAG_MIN_DECISIONS = 5
PROMPT_FLAG_CALIBRATION_THRESHOLD = 0.45
PROMPT_FLAG_WINDOW_DAYS = 30


# ────────────────────────────────────────────────────────────────────
# Domain dataclasses
# ────────────────────────────────────────────────────────────────────

@dataclass
class SourceAttribution:
    decision_id: str
    source_id: str
    calibration_score: float
    prior_accuracy: Optional[float]
    posterior_accuracy: float

    def to_dict(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "source_id": self.source_id,
            "calibration_score": round(self.calibration_score, 4),
            "prior_accuracy": round(self.prior_accuracy, 4) if self.prior_accuracy is not None else None,
            "posterior_accuracy": round(self.posterior_accuracy, 4),
        }


@dataclass
class PromptFlag:
    prompt_id: str
    prompt_name: Optional[str]
    decisions_observed: int
    mean_calibration: float
    flag_reason: str

    def to_dict(self) -> dict:
        return {
            "prompt_id": self.prompt_id,
            "prompt_name": self.prompt_name,
            "decisions_observed": self.decisions_observed,
            "mean_calibration": round(self.mean_calibration, 4),
            "flag_reason": self.flag_reason,
        }


@dataclass
class LearningRunResult:
    run_id: str
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    since_cursor: Optional[datetime]
    decisions_processed: int
    sources_updated: int
    prompts_flagged: int
    failure_reason: Optional[str] = None
    summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "run_id": str(self.run_id),
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "since_cursor": self.since_cursor.isoformat() if self.since_cursor else None,
            "decisions_processed": self.decisions_processed,
            "sources_updated": self.sources_updated,
            "prompts_flagged": self.prompts_flagged,
            "failure_reason": self.failure_reason,
            "summary": self.summary or {},
        }


# ────────────────────────────────────────────────────────────────────
# Pure math (testable in isolation)
# ────────────────────────────────────────────────────────────────────

def ewma_update(
    *, prior: Optional[float], observation: float, alpha: float = DEFAULT_EWMA_ALPHA
) -> float:
    """Exponential weighted moving average update. NULL prior seeds with
    the raw observation."""
    if not (0.0 < alpha <= 1.0):
        raise ValueError("alpha must be in (0, 1]")
    if not (0.0 <= observation <= 1.0):
        raise ValueError("observation must be in [0, 1]")
    if prior is None:
        return float(observation)
    if not (0.0 <= prior <= 1.0):
        raise ValueError("prior must be in [0, 1]")
    posterior = alpha * float(observation) + (1 - alpha) * float(prior)
    # Clamp defensively against fp edge cases
    return max(0.0, min(1.0, posterior))


# ────────────────────────────────────────────────────────────────────
# DB queries
# ────────────────────────────────────────────────────────────────────

def find_decisions_with_outcomes(
    db,
    *,
    since: Optional[datetime] = None,
    limit: int = MAX_DECISIONS_PER_RUN,
) -> list[dict]:
    """Find decisions whose actual_outcome was captured after `since`,
    that have a calibration_score, ordered by capture time ASC."""
    where = ["calibration_score IS NOT NULL", "actual_outcome_recorded_at IS NOT NULL"]
    params: list[Any] = []
    if since is not None:
        where.append("actual_outcome_recorded_at > %s")
        params.append(since)
    params.append(limit)
    rows = db.fetch_all(
        f"""
        SELECT id, calibration_score, actual_outcome_recorded_at,
               war_room_id, source_signal_id, owner_user_id, created_at
          FROM decisions
         WHERE {' AND '.join(where)}
         ORDER BY actual_outcome_recorded_at ASC
         LIMIT %s
        """,
        tuple(params),
    ) or []
    return [dict(r) for r in rows]


def find_source_ids_for_decision(db, decision: dict) -> tuple[list[str], str]:
    """Returns (source_ids, attribution_method). Tries three paths in order:

      1. Evidence-snapshot chain (preferred when SPEC-024 + decision signing wired)
      2. Brief.evidence_refs fallback (when decision links to a brief)
      3. signals.source via decision.source_signal_id (last-resort, today's path)
    """
    decision_id = str(decision["id"])

    # Path 1: evidence_snapshot chain
    try:
        rows = db.fetch_all(
            """
            SELECT DISTINCT er.source_id
              FROM evidence_snapshots es
              JOIN claim_evidence_links cel
                ON cel.claim_id::text = ANY(
                     SELECT (jsonb_array_elements(es.body->'claims')->>'claim_id')::text
                   )
              JOIN evidence_records er
                ON er.evidence_id = cel.evidence_id
             WHERE es.decision_id::text = %s
            """,
            (decision_id,),
        )
        sids = [r["source_id"] for r in (rows or []) if r.get("source_id")]
        if sids:
            return list(dict.fromkeys(sids)), "evidence_snapshot_chain"
    except Exception as exc:
        logger.debug("evidence_snapshot path failed for %s: %s", decision_id, exc)

    # Path 2: brief.evidence_refs fallback (if a brief is linked)
    try:
        rows = db.fetch_all(
            """
            SELECT DISTINCT s.source
              FROM decision_briefs b
              JOIN signals s
                ON s.id::text = ANY(
                     SELECT (jsonb_array_elements(b.evidence_refs)->>'id')::text
                     WHERE jsonb_array_elements(b.evidence_refs)->>'type' = 'signal'
                   )
             WHERE b.decision_id::text = %s
            """,
            (decision_id,),
        )
        sids = [r["source"] for r in (rows or []) if r.get("source")]
        if sids:
            return list(dict.fromkeys(sids)), "brief_evidence_refs"
    except Exception as exc:
        logger.debug("brief evidence_refs path failed for %s: %s", decision_id, exc)

    # Path 3: signals.source via decision.source_signal_id
    sig_id = decision.get("source_signal_id")
    if sig_id:
        try:
            row = db.fetch_one(
                "SELECT source FROM signals WHERE id::text = %s",
                (str(sig_id),),
            )
            if row and row.get("source"):
                return [row["source"]], "decision_source_signal"
        except Exception as exc:
            logger.debug("signal lookup failed for %s: %s", sig_id, exc)

    return [], "no_attribution_path"


def find_prompts_in_window(db, *, days: int = PROMPT_FLAG_WINDOW_DAYS) -> list[dict]:
    """Aggregate llm_call_log per prompt_id over the last N days, with a
    rough proxy for "decisions observed": count of distinct user_ids who
    invoked the prompt. (Real per-decision attribution requires
    llm_call_log.brief_id which is a follow-up.)"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.fetch_all(
        """
        SELECT lcl.prompt_id,
               pr.name AS prompt_name,
               COUNT(DISTINCT lcl.user_id) AS distinct_users,
               COUNT(*) AS total_calls
          FROM llm_call_log lcl
     LEFT JOIN prompt_registry pr ON pr.prompt_id = lcl.prompt_id
         WHERE lcl.prompt_id IS NOT NULL
           AND lcl.created_at > %s
           AND lcl.succeeded = TRUE
         GROUP BY lcl.prompt_id, pr.name
        """,
        (cutoff,),
    ) or []
    return [dict(r) for r in rows]


def mean_calibration_for_user(db, user_id: str, *, days: int = PROMPT_FLAG_WINDOW_DAYS) -> Optional[float]:
    """Mean calibration_score over the user's decisions in window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    row = db.fetch_one(
        """
        SELECT AVG(calibration_score) AS mean_cal,
               COUNT(*) AS n
          FROM decisions
         WHERE owner_user_id::text = %s
           AND calibration_score IS NOT NULL
           AND actual_outcome_recorded_at > %s
        """,
        (str(user_id), cutoff),
    )
    if not row or not row.get("n"):
        return None
    return float(row["mean_cal"]) if row.get("mean_cal") is not None else None


# ────────────────────────────────────────────────────────────────────
# LearningService — orchestrator
# ────────────────────────────────────────────────────────────────────

class LearningService:
    """Stateless orchestrator. Inject `auto_register_unknown_sources=True`
    if you want unknown source_ids to be skipped-with-counter rather than
    inserted into `sources`."""

    def __init__(
        self,
        *,
        alpha: float = DEFAULT_EWMA_ALPHA,
        max_decisions: int = MAX_DECISIONS_PER_RUN,
        auto_register_unknown_sources: bool = False,
    ):
        if not (0.0 < alpha <= 1.0):
            raise ValueError("alpha must be in (0, 1]")
        self.alpha = alpha
        self.max_decisions = max_decisions
        self.auto_register_unknown_sources = auto_register_unknown_sources

    def run(self, db, *, since: Optional[datetime] = None,
            started_by_user_id: Optional[str] = None) -> LearningRunResult:
        """Main entry point. Returns the persisted run record + summary."""
        # Resolve since cursor
        if since is None:
            since = self._resolve_since_cursor(db)

        # Insert a 'running' run row
        run_row = db.fetch_one(
            """
            INSERT INTO learning_service_runs (since_cursor, started_by_user_id)
            VALUES (%s, %s)
            RETURNING run_id, started_at, since_cursor, status,
                      decisions_processed, sources_updated, prompts_flagged
            """,
            (since, started_by_user_id),
        )
        if not run_row:
            raise RuntimeError("learning run insert returned no row")
        run_id = str(run_row["run_id"])
        started_at = run_row["started_at"]

        decisions_processed = 0
        attributions: list[SourceAttribution] = []
        skipped_reasons: dict[str, int] = {}
        attribution_methods: dict[str, int] = {}

        try:
            decisions = find_decisions_with_outcomes(
                db, since=since, limit=self.max_decisions,
            )

            # Phase 1: per-decision source attribution + EWMA update
            for d in decisions:
                try:
                    cal = d.get("calibration_score")
                    if cal is None:
                        skipped_reasons["no_calibration"] = skipped_reasons.get("no_calibration", 0) + 1
                        continue
                    cal = float(cal)
                    if not (0.0 <= cal <= 1.0):
                        skipped_reasons["calibration_out_of_range"] = skipped_reasons.get("calibration_out_of_range", 0) + 1
                        continue

                    sids, method = find_source_ids_for_decision(db, d)
                    attribution_methods[method] = attribution_methods.get(method, 0) + 1
                    if not sids:
                        skipped_reasons["no_source_attribution"] = skipped_reasons.get("no_source_attribution", 0) + 1
                        continue

                    decisions_processed += 1
                    for sid in sids:
                        attribution = self._update_source(
                            db, run_id=run_id, decision_id=str(d["id"]),
                            source_id=sid, calibration_score=cal,
                        )
                        if attribution:
                            attributions.append(attribution)
                except Exception as exc:
                    logger.exception("decision %s processing failed: %s", d.get("id"), exc)
                    skipped_reasons["processing_error"] = skipped_reasons.get("processing_error", 0) + 1

            # Phase 2: prompt flagging
            prompt_flags = self._flag_prompts(db, run_id)

            # Phase 3: persist summary
            sources_updated = len({a.source_id for a in attributions})
            new_since = max(
                (d["actual_outcome_recorded_at"] for d in decisions
                 if d.get("actual_outcome_recorded_at")),
                default=since,
            )
            summary = {
                "decisions_seen": len(decisions),
                "decisions_processed": decisions_processed,
                "sources_updated": sources_updated,
                "prompts_flagged": len(prompt_flags),
                "attribution_methods": attribution_methods,
                "skipped_reasons": skipped_reasons,
                "ewma_alpha": self.alpha,
                "max_decisions": self.max_decisions,
                "cap_hit": len(decisions) >= self.max_decisions,
                "new_since_cursor": new_since.isoformat() if new_since else None,
            }
            db.execute(
                """
                UPDATE learning_service_runs
                   SET status = 'complete',
                       completed_at = NOW(),
                       decisions_processed = %s,
                       sources_updated = %s,
                       prompts_flagged = %s,
                       summary_jsonb = %s::jsonb
                 WHERE run_id::text = %s
                """,
                (decisions_processed, sources_updated, len(prompt_flags),
                 json.dumps(summary), run_id),
            )
            return LearningRunResult(
                run_id=run_id, status="complete",
                started_at=started_at, completed_at=datetime.now(timezone.utc),
                since_cursor=since,
                decisions_processed=decisions_processed,
                sources_updated=sources_updated,
                prompts_flagged=len(prompt_flags),
                summary=summary,
            )
        except Exception as exc:
            logger.exception("learning run %s failed: %s", run_id, exc)
            db.execute(
                """
                UPDATE learning_service_runs
                   SET status = 'failed',
                       completed_at = NOW(),
                       failure_reason = %s
                 WHERE run_id::text = %s
                """,
                (str(exc)[:1000], run_id),
            )
            return LearningRunResult(
                run_id=run_id, status="failed",
                started_at=started_at, completed_at=datetime.now(timezone.utc),
                since_cursor=since,
                decisions_processed=decisions_processed,
                sources_updated=0, prompts_flagged=0,
                failure_reason=str(exc)[:1000],
                summary={"skipped_reasons": skipped_reasons},
            )

    # ── internal helpers ──

    def _resolve_since_cursor(self, db) -> datetime:
        """Use last successful run's started_at, or 30 days ago."""
        try:
            row = db.fetch_one(
                """
                SELECT started_at
                  FROM learning_service_runs
                 WHERE status = 'complete'
                 ORDER BY started_at DESC
                 LIMIT 1
                """
            )
        except Exception:
            row = None
        if row and row.get("started_at"):
            return row["started_at"]
        return datetime.now(timezone.utc) - timedelta(days=DEFAULT_LOOKBACK_DAYS)

    def _update_source(
        self, db, *, run_id: str, decision_id: str,
        source_id: str, calibration_score: float,
    ) -> Optional[SourceAttribution]:
        # Find current accuracy
        row = db.fetch_one(
            """
            SELECT q.predictive_accuracy
              FROM sources s
         LEFT JOIN source_quality_history q ON q.quality_id = s.latest_quality_id
             WHERE s.source_id = %s
            """,
            (source_id,),
        )
        if row is None:
            # Source not in registry
            if not self.auto_register_unknown_sources:
                return None
            try:
                db.execute(
                    """
                    INSERT INTO sources (source_id, display_name, tier, kind)
                    VALUES (%s, %s, 3, 'free')
                    ON CONFLICT (source_id) DO NOTHING
                    """,
                    (source_id, source_id),
                )
            except Exception as exc:
                logger.warning("auto-register failed for %s: %s", source_id, exc)
                return None
            row = {"predictive_accuracy": None}

        prior = row.get("predictive_accuracy")
        if prior is not None:
            prior = float(prior)
        posterior = ewma_update(prior=prior, observation=calibration_score, alpha=self.alpha)

        # Persist a new quality_history row pinning posterior into predictive_accuracy.
        # Using the registry's existing recompute infra would also re-derive other
        # dims; here we simply update the latest row's predictive_accuracy.
        try:
            new_q = db.fetch_one(
                """
                INSERT INTO source_quality_history (
                    source_id, predictive_accuracy, inputs_jsonb
                ) VALUES (%s, %s, %s::jsonb)
                RETURNING quality_id
                """,
                (source_id, posterior,
                 json.dumps({"learning_run_id": run_id, "decision_id": decision_id,
                             "prior": prior, "calibration_score": calibration_score,
                             "alpha": self.alpha, "method": "ewma"})),
            )
            if new_q:
                db.execute(
                    "UPDATE sources SET latest_quality_id = %s WHERE source_id = %s",
                    (new_q["quality_id"], source_id),
                )
        except Exception as exc:
            logger.warning("source quality update failed for %s: %s", source_id, exc)

        # Audit attribution
        db.execute(
            """
            INSERT INTO source_attribution_log (
                run_id, decision_id, source_id, calibration_score,
                prior_accuracy, posterior_accuracy
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (run_id, decision_id, source_id, calibration_score, prior, posterior),
        )
        return SourceAttribution(
            decision_id=decision_id, source_id=source_id,
            calibration_score=calibration_score,
            prior_accuracy=prior, posterior_accuracy=posterior,
        )

    def _flag_prompts(self, db, run_id: str) -> list[PromptFlag]:
        """For each prompt with ≥N distinct users invoking it in the window,
        compute mean calibration across those users' recent decisions; flag
        if below threshold."""
        flags: list[PromptFlag] = []
        try:
            prompts = find_prompts_in_window(db)
        except Exception as exc:
            logger.warning("prompt window query failed: %s", exc)
            return flags

        for p in prompts:
            distinct_users = int(p.get("distinct_users") or 0)
            if distinct_users < PROMPT_FLAG_MIN_DECISIONS:
                continue
            # Aggregate calibration across distinct users via a single query
            try:
                row = db.fetch_one(
                    """
                    SELECT AVG(d.calibration_score) AS mean_cal,
                           COUNT(*) AS n
                      FROM decisions d
                     WHERE d.calibration_score IS NOT NULL
                       AND d.owner_user_id IN (
                           SELECT DISTINCT user_id FROM llm_call_log
                            WHERE prompt_id::text = %s
                              AND created_at > NOW() - (%s || ' days')::interval
                              AND succeeded = TRUE
                       )
                       AND d.actual_outcome_recorded_at > NOW() - (%s || ' days')::interval
                    """,
                    (str(p["prompt_id"]), PROMPT_FLAG_WINDOW_DAYS, PROMPT_FLAG_WINDOW_DAYS),
                )
            except Exception as exc:
                logger.warning("prompt %s flag query failed: %s", p.get("prompt_id"), exc)
                continue
            n = int((row or {}).get("n") or 0)
            mean_cal = (row or {}).get("mean_cal")
            if n < PROMPT_FLAG_MIN_DECISIONS or mean_cal is None:
                continue
            mean_cal = float(mean_cal)
            if mean_cal < PROMPT_FLAG_CALIBRATION_THRESHOLD:
                flag = PromptFlag(
                    prompt_id=str(p["prompt_id"]),
                    prompt_name=p.get("prompt_name"),
                    decisions_observed=n, mean_calibration=mean_cal,
                    flag_reason="low_calibration",
                )
                # Persist
                try:
                    db.execute(
                        """
                        INSERT INTO prompt_quality_flag (
                            run_id, prompt_id, prompt_name, decisions_observed,
                            mean_calibration, flag_reason
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (run_id, str(p["prompt_id"]), p.get("prompt_name"),
                         n, mean_cal, "low_calibration"),
                    )
                except Exception as exc:
                    logger.warning("prompt flag insert failed: %s", exc)
                flags.append(flag)
        return flags


# ────────────────────────────────────────────────────────────────────
# Read-side helpers (used by GET routes)
# ────────────────────────────────────────────────────────────────────

def get_run(db, run_id: str) -> Optional[dict]:
    row = db.fetch_one(
        """
        SELECT run_id, started_at, completed_at, status, since_cursor,
               decisions_processed, sources_updated, prompts_flagged,
               failure_reason, summary_jsonb, started_by_user_id
          FROM learning_service_runs WHERE run_id::text = %s
        """,
        (str(run_id),),
    )
    return _run_row_to_dict(row) if row else None


def list_runs(db, *, status: Optional[str] = None, limit: int = 50, offset: int = 0) -> list[dict]:
    if limit < 1 or limit > 500:
        raise ValueError("limit must be in [1, 500]")
    if status is not None and status not in {"running", "complete", "failed"}:
        raise ValueError("status must be in {running|complete|failed}")
    where = ["1=1"]
    params: list[Any] = []
    if status is not None:
        where.append("status = %s"); params.append(status)
    params.extend([limit, offset])
    rows = db.fetch_all(
        f"""
        SELECT run_id, started_at, completed_at, status, since_cursor,
               decisions_processed, sources_updated, prompts_flagged,
               failure_reason, summary_jsonb, started_by_user_id
          FROM learning_service_runs
         WHERE {' AND '.join(where)}
         ORDER BY started_at DESC
         LIMIT %s OFFSET %s
        """,
        tuple(params),
    ) or []
    return [_run_row_to_dict(r) for r in rows]


def list_attributions(
    db, *, source_id: Optional[str] = None, since: Optional[datetime] = None,
    limit: int = 100,
) -> list[dict]:
    if limit < 1 or limit > 1000:
        raise ValueError("limit must be in [1, 1000]")
    where = ["1=1"]
    params: list[Any] = []
    if source_id:
        where.append("source_id = %s"); params.append(source_id)
    if since:
        where.append("created_at > %s"); params.append(since)
    params.append(limit)
    rows = db.fetch_all(
        f"""
        SELECT attribution_id, run_id, decision_id, source_id,
               calibration_score, prior_accuracy, posterior_accuracy,
               created_at
          FROM source_attribution_log
         WHERE {' AND '.join(where)}
         ORDER BY created_at DESC
         LIMIT %s
        """,
        tuple(params),
    ) or []
    return [
        {
            "attribution_id": str(r["attribution_id"]),
            "run_id": str(r["run_id"]),
            "decision_id": str(r["decision_id"]),
            "source_id": r["source_id"],
            "calibration_score": float(r["calibration_score"]),
            "prior_accuracy": float(r["prior_accuracy"]) if r.get("prior_accuracy") is not None else None,
            "posterior_accuracy": float(r["posterior_accuracy"]),
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        }
        for r in rows
    ]


def list_prompt_flags(db, *, since_days: int = 30, limit: int = 100) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    rows = db.fetch_all(
        """
        SELECT flag_id, run_id, prompt_id, prompt_name,
               decisions_observed, mean_calibration, flag_reason, created_at
          FROM prompt_quality_flag
         WHERE created_at > %s
         ORDER BY created_at DESC
         LIMIT %s
        """,
        (cutoff, limit),
    ) or []
    return [
        {
            "flag_id": str(r["flag_id"]),
            "run_id": str(r["run_id"]),
            "prompt_id": str(r["prompt_id"]),
            "prompt_name": r.get("prompt_name"),
            "decisions_observed": int(r["decisions_observed"]),
            "mean_calibration": float(r["mean_calibration"]),
            "flag_reason": r["flag_reason"],
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        }
        for r in rows
    ]


def _run_row_to_dict(row: dict) -> dict:
    summary = row.get("summary_jsonb") or {}
    if isinstance(summary, str):
        try: summary = json.loads(summary)
        except (TypeError, ValueError): summary = {}
    return {
        "run_id": str(row["run_id"]),
        "started_at": row["started_at"].isoformat() if row.get("started_at") else None,
        "completed_at": row["completed_at"].isoformat() if row.get("completed_at") else None,
        "status": row["status"],
        "since_cursor": row["since_cursor"].isoformat() if row.get("since_cursor") else None,
        "decisions_processed": int(row.get("decisions_processed") or 0),
        "sources_updated": int(row.get("sources_updated") or 0),
        "prompts_flagged": int(row.get("prompts_flagged") or 0),
        "failure_reason": row.get("failure_reason"),
        "summary": summary,
        "started_by_user_id": str(row["started_by_user_id"]) if row.get("started_by_user_id") else None,
    }
