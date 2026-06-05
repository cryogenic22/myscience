"""
Pipeline hook system for Market-Zero.

Provides a registry of hooks that fire at defined lifecycle points in the
data pipeline. Hooks can observe, filter, block, or escalate to HITL review.

Hook points:
    POST_FETCH       - after fetch, before normalize (can filter records)
    PRE_STORE        - after embed, before DB write (change detection)
    POST_STORE       - after DB write (quality gate, side effects)
    ON_QUALITY_FAIL  - when quality score < threshold (HITL escalation)
    ON_CONFLICT      - when upsert detects changed data (diff tracking)
    ON_NEW_ENTITY    - when auto-create fires (approval queue)
    ON_WITHDRAWAL    - when source no longer has record (soft delete)
    ON_RUN_COMPLETE  - after full ETL run (reports, staleness scan)
"""

from __future__ import annotations

import hashlib
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ─── Data structures ─────────────────────────

@dataclass
class HookContext:
    """Context passed to every hook invocation."""
    hook_point: str
    record: Optional[Any] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    etl_run_id: str = ""
    source_type: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class HookResult:
    """Result returned by a hook execution."""
    action: str = "continue"  # continue, skip, queue_review, block
    message: str = ""
    data: dict = field(default_factory=dict)


class PipelineHook(ABC):
    """Base class for all pipeline hooks."""

    name: str = "unnamed_hook"
    hook_points: list[str] = []

    def should_fire(self, ctx: HookContext) -> bool:
        """Override to add conditional logic beyond hook_point matching."""
        return True

    @abstractmethod
    def execute(self, ctx: HookContext) -> HookResult:
        """Execute the hook logic. Must return a HookResult."""
        ...


# ─── Hook Registry ───────────────────────────

class HookRegistry:
    """
    Manages registered hooks and dispatches them at pipeline lifecycle points.

    Usage:
        registry = HookRegistry(db, config)
        registry.register(QualityGateHook(db, config))
        results = registry.fire("POST_STORE", context)
    """

    def __init__(self, db, config):
        self.db = db
        self.config = config
        self._hooks: dict[str, list[PipelineHook]] = {}

    def register(self, hook: PipelineHook):
        """Register a hook for its declared hook_points."""
        for point in hook.hook_points:
            if point not in self._hooks:
                self._hooks[point] = []
            self._hooks[point].append(hook)
            logger.debug("Registered hook '%s' for %s", hook.name, point)

    def fire(self, hook_point: str, ctx: HookContext) -> list[HookResult]:
        """
        Fire all hooks registered for this point.

        Returns list of HookResults. If any result has action='block',
        the caller should stop processing.
        """
        ctx.hook_point = hook_point
        hooks = self._hooks.get(hook_point, [])
        results = []

        for hook in hooks:
            try:
                if hook.should_fire(ctx):
                    result = hook.execute(ctx)
                    results.append(result)
                    if result.action == "block":
                        logger.warning(
                            "Hook '%s' blocked processing: %s",
                            hook.name, result.message,
                        )
                        break
            except Exception as e:
                logger.error("Hook '%s' failed: %s", hook.name, e, exc_info=True)
                results.append(HookResult(action="continue", message=f"Hook error: {e}"))

        return results

    def has_block(self, results: list[HookResult]) -> bool:
        """Check if any hook result has action='block'."""
        return any(r.action == "block" for r in results)


# ─── Built-in Hooks ──────────────────────────

class ChangeDetectionHook(PipelineHook):
    """
    Computes content hash before store. If unchanged, signals skip.
    If changed, logs the change to data_change_log.
    """

    name = "change_detection"
    hook_points = ["PRE_STORE"]

    def __init__(self, db, config):
        self.db = db
        self.config = config

    def should_fire(self, ctx: HookContext) -> bool:
        return self.config.pipeline.change_detection_enabled

    def execute(self, ctx: HookContext) -> HookResult:
        canonical_data = ctx.metadata.get("canonical_data", {})
        if not canonical_data:
            return HookResult(action="continue")

        # Compute hash of canonical payload
        new_hash = self._compute_hash(canonical_data)
        ctx.metadata["content_hash"] = new_hash

        # Check existing hash
        entity_type = ctx.entity_type
        entity_id = ctx.entity_id
        if not entity_type or not entity_id:
            return HookResult(action="continue", data={"content_hash": new_hash})

        from integration.data_quality import ENTITY_TABLE_MAP, ENTITY_ID_COL
        # Try domain pack first via registry
        from domain.registry import DomainRegistry
        _dp = DomainRegistry.active()
        if _dp:
            _etm = _dp.get_entity_table_map()
            _eic = _dp.get_entity_id_col_map()
        else:
            _etm = ENTITY_TABLE_MAP
            _eic = ENTITY_ID_COL
        table = _etm.get(entity_type)
        id_col = _eic.get(entity_type, "id")
        if not table:
            return HookResult(action="continue", data={"content_hash": new_hash})

        # Skip UUID-typed columns when entity_id isn't a valid UUID
        # (e.g. Orange Book ANDA/NDA application numbers)
        if id_col == "id":
            import re
            if not re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', str(entity_id), re.I):
                return HookResult(action="continue", data={"content_hash": new_hash})

        existing = self.db.fetch_one(
            f"SELECT content_hash FROM {table} WHERE {id_col} = %s", [entity_id]
        )

        if existing and existing.get("content_hash") == new_hash:
            # No change — just update verification timestamp
            self.db.execute(
                f"UPDATE {table} SET last_verified_at = NOW() WHERE {id_col} = %s",
                [entity_id],
            )
            return HookResult(
                action="skip",
                message="Content unchanged, updated last_verified_at",
                data={"content_hash": new_hash, "changed": False},
            )

        # Content changed — log to change log
        old_hash = existing["content_hash"] if existing else None
        change_type = "updated" if existing else "created"

        # Detect which fields changed
        changed_fields = ctx.metadata.get("changed_fields")

        self.db.execute(
            """
            INSERT INTO data_change_log
                (entity_type, entity_id, change_type, changed_fields,
                 old_content_hash, new_content_hash, etl_run_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            [entity_type, entity_id, change_type, changed_fields,
             old_hash, new_hash, ctx.etl_run_id],
        )

        return HookResult(
            action="continue",
            message=f"Content {change_type}",
            data={"content_hash": new_hash, "changed": True, "change_type": change_type},
        )

    @staticmethod
    def _compute_hash(data: dict) -> str:
        """Deterministic SHA-256 of sorted JSON payload."""
        # Filter out non-content fields (embeddings, timestamps, etc.)
        skip_keys = {
            "molecule_embedding", "strategy_embedding", "abstract_embedding",
            "protocol_embedding", "scope_note_embedding", "embedding",
            "retrieved_at", "created_at", "updated_at", "last_verified_at",
            "content_hash", "quality_score", "record_status",
        }
        filtered = {k: v for k, v in data.items() if k not in skip_keys and v is not None}
        canonical = json.dumps(filtered, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class QualityGateHook(PipelineHook):
    """
    After store, runs quality assessment. If score falls below threshold,
    escalates to HITL review queue.
    """

    name = "quality_gate"
    hook_points = ["POST_STORE"]

    def __init__(self, db, config, quality_engine):
        self.db = db
        self.config = config
        self.quality_engine = quality_engine

    def should_fire(self, ctx: HookContext) -> bool:
        return self.config.pipeline.quality_enabled

    def execute(self, ctx: HookContext) -> HookResult:
        if not ctx.entity_type or not ctx.entity_id:
            return HookResult(action="continue")

        results = self.quality_engine.assess_record(ctx.entity_type, ctx.entity_id)
        if not results:
            return HookResult(action="continue")

        composite = self.quality_engine.compute_composite_score(results)
        failures = [r for r in results if not r.passed]

        if composite < self.config.pipeline.quality_fail_threshold:
            # Critical quality failure — escalate to HITL
            self._create_hitl_item(ctx, composite, failures, "critical")
            if self.config.pipeline.hitl_mode == "strict":
                return HookResult(
                    action="block",
                    message=f"Quality score {composite} below fail threshold",
                    data={"quality_score": composite, "failures": len(failures)},
                )

        elif composite < self.config.pipeline.quality_warn_threshold:
            self._create_hitl_item(ctx, composite, failures, "warning")

        return HookResult(
            action="continue",
            data={"quality_score": composite, "failures": len(failures)},
        )

    def _create_hitl_item(self, ctx, score, failures, level):
        priority = 10 if level == "critical" else 40
        self.db.execute(
            """
            INSERT INTO hitl_review_queue
                (review_type, entity_type, entity_id, priority, payload, source_etl_run_id)
            VALUES ('quality_failure', %s, %s, %s, %s::jsonb, %s)
            """,
            [
                ctx.entity_type, ctx.entity_id, priority,
                json.dumps({
                    "quality_score": score,
                    "level": level,
                    "failures": [
                        {"rule": f.rule_name, "score": f.score, "details": f.details}
                        for f in failures
                    ],
                    "source_type": ctx.source_type,
                }),
                ctx.etl_run_id,
            ],
        )


class NewEntityReviewHook(PipelineHook):
    """
    When a new entity is auto-created, queues it for HITL review
    if confidence is below threshold.
    """

    name = "new_entity_review"
    hook_points = ["ON_NEW_ENTITY"]

    def __init__(self, db, config):
        self.db = db
        self.config = config

    def execute(self, ctx: HookContext) -> HookResult:
        confidence = ctx.metadata.get("confidence", 1.0)
        method = ctx.metadata.get("resolution_method", "unknown")

        if confidence < self.config.pipeline.hitl_confidence_threshold:
            priority = int(50 - (1.0 - confidence) * 40)  # lower confidence → higher priority
            self.db.execute(
                """
                INSERT INTO hitl_review_queue
                    (review_type, entity_type, entity_id, priority, payload, source_etl_run_id)
                VALUES ('new_entity', %s, %s, %s, %s::jsonb, %s)
                """,
                [
                    ctx.entity_type, ctx.entity_id, priority,
                    json.dumps({
                        "confidence": confidence,
                        "resolution_method": method,
                        "raw_value": ctx.metadata.get("raw_value", ""),
                        "source_type": ctx.source_type,
                        "candidates": ctx.metadata.get("candidates", []),
                    }),
                    ctx.etl_run_id,
                ],
            )
            if self.config.pipeline.hitl_mode == "manual":
                return HookResult(
                    action="block",
                    message=f"New entity requires manual approval (confidence={confidence})",
                )

        return HookResult(action="continue")


class StalenessHook(PipelineHook):
    """
    After a run completes, identifies records that weren't seen in this run
    and marks them as potentially stale.
    """

    name = "staleness_check"
    hook_points = ["ON_RUN_COMPLETE"]

    def __init__(self, db, config, domain_pack=None):
        self.db = db
        self.config = config
        self.domain_pack = domain_pack

    def execute(self, ctx: HookContext) -> HookResult:
        source_type = ctx.source_type
        run_id = ctx.etl_run_id
        max_days = self.config.pipeline.freshness_max_days

        # Use domain pack staleness map if available
        if self.domain_pack:
            source_table_map = self.domain_pack.staleness_map
        else:
            source_table_map = {
                "clinical_trials_gov": [("clinical_trials", "source_api", "clinical_trials_gov")],
                "fda_orange_book": [("drugs", "source_api", "fda_orange_book")],
                "fda_shortages": [("market_events", "source_api", "fda_shortages")],
                "pubmed": [("pubmed_articles", "source_api", "pubmed")],
                "sec_edgar": [("companies", "source_api", "sec_edgar")],
            }

        tables = source_table_map.get(source_type, [])
        stale_count = 0

        for table_name, source_col, source_val in tables:
            result = self.db.fetch_one(
                f"""
                WITH updated AS (
                    UPDATE {table_name}
                    SET record_status = 'stale'
                    WHERE {source_col} = %s
                      AND record_status = 'active'
                      AND (last_verified_at IS NULL OR last_verified_at < NOW() - INTERVAL '%s days')
                    RETURNING 1
                )
                SELECT count(*) AS cnt FROM updated
                """,
                [source_val, max_days],
            )
            if result:
                stale_count += result.get("cnt", 0)

        # Source-level freshness check (D1). The per-record map above does NOT
        # cover every scheduled source (notably it omitted openfda_labels /
        # openfda_faers — the two that died silently for 105 days). Drive a
        # source-level "is this source's newest row past its SLA?" check off the
        # single FRESHNESS_SLA_DAYS config so any *scheduled* source is covered
        # automatically without a bespoke per-record entry. This surfaces a dead
        # source during the run, complementing scripts/connector_health.py.
        source_stale = self._check_source_freshness(source_type)

        return HookResult(
            action="continue",
            message=f"Marked {stale_count} records as stale"
            + (f"; SOURCE OVER SLA: {source_type}" if source_stale else ""),
            data={"stale_count": stale_count, "source_stale": source_stale},
        )

    def _check_source_freshness(self, source_type: str) -> bool:
        """Return True if the source's target table's newest row is past its SLA.

        Reads the per-source SLA registry (scheduler.config.FRESHNESS_SLA_DAYS)
        so new sources are covered the moment they're scheduled. Best-effort and
        read-only — never blocks the run."""
        try:
            from scheduler.config import FRESHNESS_SLA_DAYS

            entry = next(
                (v for k, v in FRESHNESS_SLA_DAYS.items() if k.value == source_type),
                None,
            )
            if not entry:
                return False
            table, recency_col, sla_days = entry
            row = self.db.fetch_one(
                f"SELECT max({recency_col}) AS newest, count(*) AS n FROM {table}"
            )
            if not row or not row.get("n"):
                logger.warning("Source %s target table %s is EMPTY (SLA %dd)",
                               source_type, table, sla_days)
                return True
            newest = row.get("newest")
            if newest is None:
                return True
            from datetime import datetime, timezone

            if newest.tzinfo is None:
                newest = newest.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - newest).total_seconds() / 86400.0
            if age_days > sla_days:
                logger.warning(
                    "Source %s OVER SLA: %s newest is %.1fd old (SLA %dd)",
                    source_type, table, age_days, sla_days,
                )
                return True
            return False
        except Exception as exc:  # noqa: BLE001 — alerting must never fail the run
            logger.debug("Source freshness check failed for %s: %s", source_type, exc)
            return False


class ValidationGateHook(PipelineHook):
    """
    Pre-store validation: enforces required/recommended fields per entity type,
    source authority consistency, and completeness ratio.

    In strict mode, blocks records missing required fields.
    In normal mode, annotates record metadata with validation results.
    """

    name = "validation_gate"
    hook_points = ["PRE_STORE"]

    # Per-entity-type validation schema (fallback when no domain pack)
    _DEFAULT_VALIDATION_SCHEMA = {
        "drug": {
            "required": ["generic_name"],
            "recommended": ["brand_name", "company_id", "therapeutic_area_id",
                            "mechanism_id", "nda_number", "approval_date"],
        },
        "company": {
            "required": ["name"],
            "recommended": ["cik", "ticker", "country", "sic_code"],
        },
        "trial": {
            "required": ["nct_id", "title", "status"],
            "recommended": ["phase", "sponsor_name", "drug_id", "conditions",
                            "start_date"],
        },
        "literature": {
            "required": ["title", "pmid"],
            "recommended": ["abstract", "journal", "publication_date", "drug_id"],
        },
        "event": {
            "required": ["event_type", "description"],
            "recommended": ["event_date", "drug_id"],
        },
    }

    def __init__(self, db, config, domain_pack=None):
        self.db = db
        self.config = config
        # Use domain pack validation schema if available
        if domain_pack:
            self._validation_schema = domain_pack.get_validation_schema()
            self._canonical_sources = domain_pack.canonical_sources
        else:
            self._validation_schema = self._DEFAULT_VALIDATION_SCHEMA
            self._canonical_sources = None

    def execute(self, ctx: HookContext) -> HookResult:
        entity_type = ctx.entity_type
        if not entity_type:
            return HookResult(action="continue")

        schema = self._validation_schema.get(entity_type)
        if not schema:
            return HookResult(action="continue")

        canonical_data = ctx.metadata.get("canonical_data", {})
        if not canonical_data:
            return HookResult(action="continue")

        issues = []
        missing_required = []
        missing_recommended = []

        # Check required fields
        for field_name in schema.get("required", []):
            val = canonical_data.get(field_name)
            if val is None or val == "" or val == []:
                missing_required.append(field_name)
                issues.append(f"Missing required field: {field_name}")

        # Check recommended fields
        for field_name in schema.get("recommended", []):
            val = canonical_data.get(field_name)
            if val is None or val == "" or val == []:
                missing_recommended.append(field_name)

        # Source authority consistency
        if self._canonical_sources:
            canonical_src_set = self._canonical_sources
        else:
            from integration.normalizer import CANONICAL_SOURCES
            canonical_src_set = CANONICAL_SOURCES
        source_auth = canonical_data.get("source_authority")
        if source_auth and source_auth not in canonical_src_set:
            issues.append(f"Non-canonical source_authority: {source_auth}")

        # Completeness ratio
        all_fields = schema.get("required", []) + schema.get("recommended", [])
        present = sum(
            1 for f in all_fields
            if canonical_data.get(f) is not None
            and canonical_data.get(f) != ""
            and canonical_data.get(f) != []
        )
        completeness = present / len(all_fields) if all_fields else 1.0

        # Annotate record metadata with validation results
        ctx.metadata["validation"] = {
            "issues": issues,
            "missing_required": missing_required,
            "missing_recommended": missing_recommended,
            "completeness": round(completeness, 3),
        }

        # In strict mode, block records missing required fields
        if missing_required and self.config.pipeline.hitl_mode == "strict":
            return HookResult(
                action="block",
                message=f"Validation failed: missing required fields {missing_required}",
                data={"missing_required": missing_required, "completeness": completeness},
            )

        return HookResult(
            action="continue",
            data={"completeness": completeness, "issues_count": len(issues)},
        )


class HITLEscalationHook(PipelineHook):
    """
    When entity resolution confidence is low, creates a review item.
    """

    name = "hitl_escalation"
    hook_points = ["ON_QUALITY_FAIL"]

    def __init__(self, db, config):
        self.db = db
        self.config = config

    def execute(self, ctx: HookContext) -> HookResult:
        severity = ctx.metadata.get("severity", "warning")
        priority_map = {"critical": 10, "error": 20, "warning": 40, "info": 80}
        priority = priority_map.get(severity, 50)

        self.db.execute(
            """
            INSERT INTO hitl_review_queue
                (review_type, entity_type, entity_id, priority, payload, source_etl_run_id)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT DO NOTHING
            """,
            [
                ctx.metadata.get("review_type", "quality_failure"),
                ctx.entity_type, ctx.entity_id, priority,
                json.dumps(ctx.metadata),
                ctx.etl_run_id,
            ],
        )

        return HookResult(action="continue", message=f"HITL item created (priority={priority})")


class UnresolvedProcessorHook(PipelineHook):
    """
    At the end of each pipeline run, processes the top-100 highest-confidence
    unresolved entities. Creates aliases, marks resolved, and logs to audit.
    """

    name = "unresolved_processor"
    hook_points = ["ON_RUN_COMPLETE"]

    def __init__(self, db, config):
        self.db = db
        self.config = config

    def execute(self, ctx: HookContext) -> HookResult:
        # Fetch top-100 high-confidence unresolved entities
        rows = self.db.fetch_all(
            """
            SELECT id, raw_value, record_type, source_type,
                   suggested_match_id, suggested_confidence
            FROM unresolved_entities
            WHERE resolved = FALSE
              AND (status IS NULL OR status = 'pending')
              AND suggested_confidence >= 0.85
              AND suggested_match_id IS NOT NULL
            ORDER BY suggested_confidence DESC
            LIMIT 100
            """
        )

        resolved_count = 0
        for row in rows:
            try:
                # Create alias
                self.db.execute(
                    """
                    INSERT INTO entity_aliases
                        (entity_type, entity_id, alias_text, source_type, confidence, verified)
                    VALUES (%s, %s, %s, 'pipeline_auto', %s, FALSE)
                    ON CONFLICT (entity_type, alias_text, source_type) DO NOTHING
                    """,
                    [row["record_type"], row["suggested_match_id"],
                     row["raw_value"], row["suggested_confidence"]],
                )

                # Mark resolved
                self.db.execute(
                    """
                    UPDATE unresolved_entities
                    SET resolved = TRUE, status = 'resolved',
                        resolution_method = 'pipeline_auto_resolve'
                    WHERE id = %s
                    """,
                    [row["id"]],
                )

                # Audit log
                self.db.execute(
                    """
                    INSERT INTO resolution_audit
                        (raw_value, entity_type, resolved_entity_id, resolution_method,
                         confidence, reasoning, source_type, source_record_id, accepted)
                    VALUES (%s, %s, %s, 'pipeline_auto', %s, %s, %s, %s, true)
                    """,
                    [
                        row["raw_value"], row["record_type"],
                        row["suggested_match_id"], row["suggested_confidence"],
                        f"Auto-resolved during pipeline run {ctx.etl_run_id}",
                        row.get("source_type", "unknown"), str(row["id"]),
                    ],
                )
                resolved_count += 1
            except Exception as e:
                logger.warning("Failed to auto-resolve unresolved %s: %s", row["id"], e)

        return HookResult(
            action="continue",
            message=f"Processed {resolved_count} unresolved entities",
            data={"resolved_count": resolved_count},
        )


# ─── HITL Review Workflow ────────────────────

class HITLReviewManager:
    """
    Manages the human-in-the-loop review queue.

    Usage:
        mgr = HITLReviewManager(db)
        pending = mgr.get_pending(limit=10)
        mgr.resolve(review_id, 'approved', {'reasoning': '...'}, resolved_by='analyst')
    """

    def __init__(self, db):
        self.db = db

    def get_pending(self, review_type: str = None, limit: int = 20) -> list[dict]:
        """Get pending review items, ordered by priority."""
        if review_type:
            return self.db.fetch_all(
                """
                SELECT * FROM hitl_review_queue
                WHERE status = 'pending' AND review_type = %s
                ORDER BY priority ASC, created_at ASC
                LIMIT %s
                """,
                [review_type, limit],
            )
        return self.db.fetch_all(
            """
            SELECT * FROM hitl_review_queue
            WHERE status = 'pending'
            ORDER BY priority ASC, created_at ASC
            LIMIT %s
            """,
            [limit],
        )

    def resolve(self, review_id: str, action: str, resolution: dict = None, resolved_by: str = "system"):
        """
        Resolve a review item.

        Actions: approved, rejected, merged, reassigned, deferred
        """
        self.db.execute(
            """
            UPDATE hitl_review_queue
            SET status = %s,
                resolution = %s::jsonb,
                assigned_to = %s,
                resolved_at = NOW()
            WHERE id = %s
            """,
            [action, json.dumps(resolution or {}), resolved_by, review_id],
        )

        # If approved and it's an entity resolution, create alias
        if action == "approved":
            item = self.db.fetch_one(
                "SELECT * FROM hitl_review_queue WHERE id = %s", [review_id]
            )
            if item and item["review_type"] == "entity_resolution":
                payload = item["payload"] if isinstance(item["payload"], dict) else json.loads(item["payload"])
                raw_value = payload.get("raw_value")
                entity_id = item["entity_id"]
                entity_type = item["entity_type"]
                if raw_value and entity_id:
                    self.db.execute(
                        """
                        INSERT INTO entity_aliases (entity_type, entity_id, alias_text, source_type, confidence, verified)
                        VALUES (%s, %s, %s, 'hitl_review', 1.0, TRUE)
                        ON CONFLICT (entity_type, alias_text, source_type) DO NOTHING
                        """,
                        [entity_type, entity_id, raw_value],
                    )

    def get_stats(self) -> dict:
        """Summary stats for the review queue."""
        rows = self.db.fetch_all(
            """
            SELECT status, review_type, count(*) as c
            FROM hitl_review_queue
            GROUP BY status, review_type
            ORDER BY status, review_type
            """
        )
        stats: dict = {}
        for r in rows:
            status = r["status"]
            if status not in stats:
                stats[status] = {}
            stats[status][r["review_type"]] = r["c"]
        return stats


# ─── Quality Monitor Hook ─────────────────────────


class QualityMonitorHook(PipelineHook):
    """
    Phase 5.3: Monitors quality delta after each pipeline run.

    Fires ON_RUN_COMPLETE. Computes quality score delta vs previous run,
    logs warning if quality drops, tracks metrics in pipeline_quality_history.
    """

    name = "quality_monitor"
    hook_points = ["ON_RUN_COMPLETE"]

    def __init__(self, db, quality_drop_threshold: float = 0.05,
                 new_entity_threshold: int = 100):
        self.db = db
        self.quality_drop_threshold = quality_drop_threshold
        self.new_entity_threshold = new_entity_threshold

    def execute(self, ctx: HookContext) -> HookResult:
        """Compute quality delta and log/alert."""
        source = ctx.source_type or "unknown"
        etl_run_id = ctx.etl_run_id

        try:
            # Get current quality scores
            current = self._compute_quality_snapshot()

            # Get previous snapshot
            previous = self._get_previous_snapshot()

            # Compute delta
            delta = {}
            alerts = []
            for entity_type, score in current.items():
                prev_score = previous.get(entity_type, score)
                change = score - prev_score
                delta[entity_type] = round(change, 4)
                if change < -self.quality_drop_threshold:
                    alerts.append(
                        f"{entity_type} quality dropped {abs(change):.1%} "
                        f"({prev_score:.1%} → {score:.1%})"
                    )

            # Check new entity count
            new_entities = ctx.metadata.get("records_inserted", 0)
            if new_entities > self.new_entity_threshold:
                alerts.append(
                    f"{new_entities} new entities created (threshold: {self.new_entity_threshold})"
                )

            # Store snapshot
            self._store_snapshot(current, delta, source, etl_run_id, alerts)

            if alerts:
                for alert in alerts:
                    logger.warning("Quality alert [%s]: %s", source, alert)
                return HookResult(
                    action="continue",
                    message=f"Quality alerts: {len(alerts)}",
                    data={"alerts": alerts, "delta": delta},
                )

            return HookResult(
                action="continue",
                message="Quality stable",
                data={"delta": delta},
            )

        except Exception as e:
            logger.error("Quality monitor failed: %s", e)
            return HookResult(action="continue", message=f"Monitor error: {e}")

    def _compute_quality_snapshot(self) -> dict[str, float]:
        """Compute current average quality score per entity type."""
        try:
            rows = self.db.fetch_all(
                """
                SELECT entity_type, ROUND(AVG(score)::numeric, 4) AS avg_score
                FROM data_quality_results
                GROUP BY entity_type
                """
            )
            return {r["entity_type"]: float(r["avg_score"]) for r in rows}
        except Exception:
            return {}

    def _get_previous_snapshot(self) -> dict[str, float]:
        """Get the most recent quality snapshot."""
        try:
            row = self.db.fetch_one(
                """
                SELECT quality_scores FROM pipeline_quality_history
                ORDER BY created_at DESC LIMIT 1
                """
            )
            if row and row.get("quality_scores"):
                scores = row["quality_scores"]
                if isinstance(scores, str):
                    scores = json.loads(scores)
                return {k: float(v) for k, v in scores.items()}
        except Exception:
            pass
        return {}

    def _store_snapshot(self, scores: dict, delta: dict, source: str,
                        etl_run_id: str, alerts: list[str]) -> None:
        """Store quality snapshot in history table."""
        try:
            # Create table if not exists (idempotent)
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS pipeline_quality_history (
                    id SERIAL PRIMARY KEY,
                    source_type TEXT,
                    etl_run_id TEXT,
                    quality_scores JSONB,
                    quality_delta JSONB,
                    alerts TEXT[],
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )
            self.db.execute(
                """
                INSERT INTO pipeline_quality_history
                    (source_type, etl_run_id, quality_scores, quality_delta, alerts)
                VALUES (%s, %s, %s::jsonb, %s::jsonb, %s)
                """,
                [source, etl_run_id, json.dumps(scores), json.dumps(delta), alerts],
            )
        except Exception as e:
            logger.warning("Failed to store quality snapshot: %s", e)
