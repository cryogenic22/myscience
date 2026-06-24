"""
Integration pipeline for Market-Zero.

This is the central data flow: every RawRecord from every connector passes
through the same 5 steps regardless of source.

    fetch -> normalize -> resolve -> embed -> store -> cross_link

Each step is a separate module. This file orchestrates them and manages
the ETL run lifecycle (create run -> process records -> finalize run).

Pipeline hooks fire at defined lifecycle points to enable:
- Change detection (PRE_STORE)
- Quality gating (POST_STORE)
- HITL escalation (ON_QUALITY_FAIL, ON_NEW_ENTITY)
- Staleness tracking (ON_RUN_COMPLETE)
- Dataset catalog refresh (ON_RUN_COMPLETE)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from uuid import uuid4

from connectors.base import (
    BaseConnector,
    ConnectorError,
    RawRecord,
    RecordType,
    SourceType,
)
from integration.normalizer import Normalizer, NormalizedRecord
from integration.entity_resolver import EntityResolver, ResolvedRecord
from integration.embedder import Embedder, EmbeddedRecord
from integration.knowledge_store import KnowledgeStore, RecordSkipped
from integration.cross_linker import CrossLinker
from integration.data_quality import DataQualityEngine
from integration.pipeline_hooks import (
    HookRegistry,
    HookContext,
    ChangeDetectionHook,
    QualityGateHook,
    NewEntityReviewHook,
    StalenessHook,
    ValidationGateHook,
    UnresolvedProcessorHook,
)
from integration.dataset_catalog import DatasetCatalog
from domain.registry import DomainRegistry

logger = logging.getLogger(__name__)


# Fallback map when no domain pack is active
_DEFAULT_RECORD_TYPE_TO_ENTITY = {
    RecordType.DRUG: "drug",
    RecordType.COMPANY: "company",
    RecordType.TRIAL: "trial",
    RecordType.EVENT: "event",
    RecordType.LITERATURE: "literature",
}


class PipelineResult:
    """Summary of a pipeline run."""

    def __init__(self, etl_run_id: str, source_type: SourceType):
        self.etl_run_id = etl_run_id
        self.source_type = source_type
        self.records_processed = 0
        self.records_inserted = 0
        self.records_updated = 0
        self.records_skipped = 0
        self.records_unchanged = 0
        self.records_failed = 0
        self.links_created = 0
        self.hitl_items_created = 0
        self.quality_scores: list[float] = []
        self.errors: list[str] = []
        self.started_at = datetime.utcnow()
        self.completed_at: Optional[datetime] = None

    @property
    def success(self) -> bool:
        return self.records_failed == 0 and len(self.errors) == 0

    @property
    def avg_quality_score(self) -> Optional[float]:
        if self.quality_scores:
            return round(sum(self.quality_scores) / len(self.quality_scores), 3)
        return None

    def summary(self) -> dict:
        return {
            "etl_run_id": self.etl_run_id,
            "source": self.source_type.value,
            "processed": self.records_processed,
            "inserted": self.records_inserted,
            "updated": self.records_updated,
            "unchanged": self.records_unchanged,
            "skipped": self.records_skipped,
            "failed": self.records_failed,
            "links_created": self.links_created,
            "hitl_items": self.hitl_items_created,
            "avg_quality": self.avg_quality_score,
            "errors": self.errors[:10],  # cap for readability
            "duration_seconds": (
                (self.completed_at - self.started_at).total_seconds()
                if self.completed_at
                else None
            ),
        }


# Run-level outcome vocabulary (migration 088). Additive to the coarse `status`.
RUN_OUTCOME_LANDED = "SUCCESS_LANDED"
RUN_OUTCOME_NO_CHANGE = "SUCCESS_NO_CHANGE"
RUN_OUTCOME_ZERO_ROWS = "FAILURE_ZERO_ROWS"
RUN_OUTCOME_PARTIAL = "PARTIAL"
RUN_OUTCOME_FAILURE = "FAILURE"


def classify_run_outcome(
    success: bool,
    processed: int,
    inserted: int,
    updated: int,
    incremental: bool = False,
    has_history: bool = False,
) -> str:
    """Classify a finished run into the richer outcome vocabulary.

    Pure + deterministic (no DB) so it is a Lane-1 conservation gate. The point
    is to make the SILENT-ZERO visible: a run that "succeeds" but fetches nothing
    (the Open Targets / EMA / 105-day-stale signature) is FAILURE_ZERO_ROWS, not
    a green SUCCESS. A run that fetched rows but changed none is NO_CHANGE (a
    legitimate quiet cycle), distinct from one that landed fresh data.

    The 0-row case is two-faced, which is why ``incremental`` + ``has_history``
    exist: an INCREMENTAL fetch against a source that HAS landed before, returning
    0, is a legitimate no-change window — the source affirmatively had nothing new
    since the watermark (openFDA FAERS lags by months; drug labels rarely change).
    That is SUCCESS_NO_CHANGE, not a failure. A FULL fetch returning 0, or an
    incremental fetch against a source that never landed, is genuinely broken-empty
    → FAILURE_ZERO_ROWS. Crucially this does NOT re-hide the 105-day-stale disease:
    staleness (a feed that *should* have new data but doesn't) stays a
    connector_health Lane-2 verdict comparing table-age to the SLA (migration 088).
    Defaults are False so legacy call sites keep the strict silent-zero verdict.

    Tradeoff (named, accepted): for an incremental+has_history source these two
    sources now lean on the FLOW (table-age vs SLA) backstop for breakage
    detection rather than per-run E2E flagging — a real break is caught when the
    table ages past SLA (RED at ~2×SLA) instead of on the next run. That is the
    right call here (these sources emit ~30 false REDs/week and a 0-row fetch
    writes no rows, so retrieved_at does not advance and FLOW still ages).
    """
    if not success:
        return RUN_OUTCOME_PARTIAL
    if (inserted or 0) > 0 or (updated or 0) > 0:
        return RUN_OUTCOME_LANDED
    if (processed or 0) > 0:
        return RUN_OUTCOME_NO_CHANGE
    # processed == 0: legitimate quiet incremental window vs broken-empty.
    if incremental and has_history:
        return RUN_OUTCOME_NO_CHANGE
    return RUN_OUTCOME_ZERO_ROWS


class IntegrationPipeline:
    """
    Orchestrates the 5-step data flow for any connector.

    Usage:
        pipeline = IntegrationPipeline(db_session, config)
        result = pipeline.run(connector, since=last_run_time)
    """

    def __init__(self, db, config, domain_pack=None):
        self.db = db
        self.config = config

        # Domain pack: use explicit pack, or fall back to registry
        self.domain_pack = domain_pack or DomainRegistry.active()

        self.normalizer = Normalizer(domain_pack=self.domain_pack)

        # Initialize OpenAI client for embedding + LLM resolution strategies
        openai_client = None
        if config.embedding.api_key:
            try:
                from openai import OpenAI
                openai_client = OpenAI(api_key=config.embedding.api_key)
            except ImportError:
                logger.warning("openai package not installed; embedding/LLM resolution disabled")

        self.resolver = EntityResolver(db, config, openai_client=openai_client, domain_pack=self.domain_pack)
        self.embedder = Embedder(config)
        self.store = KnowledgeStore(db)
        self.linker = CrossLinker(db, domain_pack=self.domain_pack)

        # Data quality engine
        self.quality_engine = DataQualityEngine(db, config, domain_pack=self.domain_pack)

        # Dataset catalog
        self.catalog = DatasetCatalog(db, config)

        # Build record-type-to-entity mapping from domain pack
        if self.domain_pack:
            self._record_type_to_entity = self.domain_pack.get_record_type_to_entity_map()
        else:
            self._record_type_to_entity = {rt.value: et for rt, et in _DEFAULT_RECORD_TYPE_TO_ENTITY.items()}

        # Hook registry with built-in hooks
        self.hooks = HookRegistry(db, config)
        self.hooks.register(ValidationGateHook(db, config, domain_pack=self.domain_pack))
        self.hooks.register(ChangeDetectionHook(db, config))  # PRE_STORE: skip unchanged
        self.hooks.register(QualityGateHook(db, config, self.quality_engine))  # POST_STORE
        self.hooks.register(NewEntityReviewHook(db, config))  # ON_NEW_ENTITY
        self.hooks.register(StalenessHook(db, config, domain_pack=self.domain_pack))
        self.hooks.register(UnresolvedProcessorHook(db, config))  # ON_RUN_COMPLETE

    def run(
        self,
        connector: BaseConnector,
        since: Optional[datetime] = None,
    ) -> PipelineResult:
        """
        Execute the full pipeline for a single connector.

        Args:
            connector: The data source connector to run.
            since: If provided, only fetch records updated after this time.

        Returns:
            PipelineResult with counts and any errors.
        """
        source_type = connector.source_type()
        etl_run_id = str(uuid4())
        result = PipelineResult(etl_run_id, source_type)

        logger.info(
            "Pipeline starting: source=%s, run_id=%s, since=%s",
            source_type.value,
            etl_run_id,
            since,
        )

        # Create ETL run record
        self._create_etl_run(etl_run_id, source_type, connector)

        try:
            # Step 0: Fetch
            raw_records = self._fetch(connector, since, result)

            # Steps 1-5: Process each record
            for record in raw_records:
                try:
                    self._process_record(record, etl_run_id, result)
                    result.records_processed += 1
                except Exception as e:
                    result.records_failed += 1
                    result.errors.append(
                        f"Record {record.external_id}: {type(e).__name__}: {e}"
                    )
                    logger.warning(
                        "Failed to process record %s: %s",
                        record.external_id,
                        e,
                        exc_info=True,
                    )
                    # Persist to dead-letter queue for retry
                    self._dlq_insert(etl_run_id, record, e)

            # Finalize. `since is not None` => incremental run, so a 0-row fetch
            # against a source that has landed before is a quiet window, not a
            # broken-empty failure.
            result.completed_at = datetime.utcnow()
            self._finalize_etl_run(etl_run_id, result, incremental=since is not None)

            # Post-run hooks: staleness check
            run_complete_ctx = HookContext(
                hook_point="ON_RUN_COMPLETE",
                etl_run_id=etl_run_id,
                source_type=source_type.value,
                metadata={"records_processed": result.records_processed},
            )
            self.hooks.fire("ON_RUN_COMPLETE", run_complete_ctx)

            # Refresh dataset catalog after run
            try:
                self.catalog.refresh_all()
            except Exception as e:
                logger.warning("Catalog refresh failed: %s", e)

            logger.info(
                "Pipeline completed: source=%s, %s",
                source_type.value,
                result.summary(),
            )

        except ConnectorError as e:
            result.errors.append(str(e))
            result.completed_at = datetime.utcnow()
            self._fail_etl_run(etl_run_id, str(e))
            logger.error("Pipeline failed: source=%s, error=%s", source_type.value, e)

        except Exception as e:
            result.errors.append(f"Unexpected: {type(e).__name__}: {e}")
            result.completed_at = datetime.utcnow()
            self._fail_etl_run(etl_run_id, str(e))
            logger.error(
                "Pipeline crashed: source=%s", source_type.value, exc_info=True
            )

        return result

    def _fetch(
        self,
        connector: BaseConnector,
        since: Optional[datetime],
        result: PipelineResult,
    ) -> list[RawRecord]:
        """Step 0: Fetch raw records from the connector."""
        logger.info("Fetching from %s...", connector.source_type().value)
        records = connector.fetch(since=since)
        logger.info("Fetched %d records from %s", len(records), connector.source_type().value)
        return records

    def _process_record(
        self,
        record: RawRecord,
        etl_run_id: str,
        result: PipelineResult,
    ) -> None:
        """Steps 1-5 for a single record."""

        # Step 1: Normalize
        normalized = self.normalizer.normalize(record)

        # Step 2: Resolve entities
        resolved = self.resolver.resolve(normalized)

        # Check for auto-created entities from resolution and fire ON_NEW_ENTITY hooks
        if hasattr(resolved, 'resolved_links') and resolved.resolved_links:
            for link_key, link_info in resolved.resolved_links.items():
                if hasattr(link_info, 'method') and link_info.method == 'auto_create':
                    new_entity_ctx = HookContext(
                        hook_point="ON_NEW_ENTITY",
                        entity_type=self._record_type_to_entity.get(record.record_type.value),
                        entity_id=link_info.entity_id if hasattr(link_info, 'entity_id') else None,
                        etl_run_id=etl_run_id,
                        source_type=record.provenance.source_type.value,
                        metadata={
                            "confidence": getattr(link_info, 'confidence', 1.0),
                            "resolution_method": "auto_create",
                            "raw_value": getattr(link_info, 'raw_value', ''),
                        },
                    )
                    self.hooks.fire("ON_NEW_ENTITY", new_entity_ctx)

        # Step 3: Embed (if text_content present)
        embedded = self.embedder.embed(resolved)

        # Determine entity type for hooks
        record_type = record.record_type
        entity_type = self._record_type_to_entity.get(record_type.value)

        # PRE_STORE hook: change detection
        pre_ctx = HookContext(
            hook_point="PRE_STORE",
            record=embedded,
            entity_type=entity_type,
            entity_id=record.external_id,
            etl_run_id=etl_run_id,
            source_type=record.provenance.source_type.value,
            metadata={"canonical_data": normalized.canonical_data},
        )
        pre_results = self.hooks.fire("PRE_STORE", pre_ctx)

        # If change detection says skip (content unchanged)
        if self.hooks.has_block(pre_results):
            result.records_skipped += 1
            return

        # Check for unchanged content (skip action from ChangeDetectionHook)
        for pr in pre_results:
            if pr.action == "skip":
                result.records_unchanged += 1
                return

        # Step 4: Store
        try:
            stored_id, was_insert = self.store.store(embedded, etl_run_id)
        except RecordSkipped as skip:
            # Conservation: a deliberate, recorded skip (e.g. a name-less ontology
            # term) — count it, don't crash into the dead-letter queue.
            result.records_skipped += 1
            logger.info("Skipped record %s: %s", record.external_id, skip)
            return

        if was_insert:
            result.records_inserted += 1
        else:
            result.records_updated += 1

        # Step 5: Cross-link
        links = self.linker.cross_link(embedded, stored_id)
        result.links_created += len(links)

        # POST_STORE hook: quality gate
        if entity_type:
            post_ctx = HookContext(
                hook_point="POST_STORE",
                record=embedded,
                entity_type=entity_type,
                entity_id=stored_id,
                etl_run_id=etl_run_id,
                source_type=record.provenance.source_type.value,
            )
            post_results = self.hooks.fire("POST_STORE", post_ctx)

            # Track quality scores and HITL items
            for pr in post_results:
                if "quality_score" in pr.data:
                    result.quality_scores.append(pr.data["quality_score"])
                if pr.data.get("failures", 0) > 0:
                    result.hitl_items_created += 1

            # Enrichment queuing: if validation flagged missing recommended fields
            validation = pre_ctx.metadata.get("validation", {})
            missing_recommended = validation.get("missing_recommended", [])
            if missing_recommended and entity_type in ("drug", "company"):
                import json as _json
                try:
                    self.db.execute(
                        """
                        INSERT INTO hitl_review_queue
                            (review_type, entity_type, entity_id, priority, payload, source_etl_run_id)
                        VALUES ('enrichment_needed', %s, %s, 60, %s::jsonb, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        [
                            entity_type, stored_id,
                            _json.dumps({
                                "missing_fields": missing_recommended,
                                "completeness": validation.get("completeness", 0),
                                "source_type": record.provenance.source_type.value,
                            }),
                            etl_run_id,
                        ],
                    )
                except Exception:
                    pass  # Non-critical; don't fail the pipeline

    # ---- ETL run lifecycle ----

    def _dlq_insert(self, etl_run_id: str, record, error: Exception) -> None:
        """Insert a failed record into the dead-letter queue for retry."""
        import traceback as _tb
        import json as _json
        try:
            prov = {}
            if hasattr(record, 'provenance') and record.provenance:
                p = record.provenance
                prov = {
                    "source_type": p.source_type.value if hasattr(p.source_type, 'value') else str(p.source_type),
                    "api_endpoint": getattr(p, 'api_endpoint', ''),
                    "retrieved_at": p.retrieved_at.isoformat() if hasattr(p, 'retrieved_at') and p.retrieved_at else None,
                }
            self.db.execute(
                """INSERT INTO failed_records
                   (etl_run_id, source_type, external_id, record_type,
                    error_message, error_traceback, raw_payload, provenance)
                   VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)""",
                [
                    etl_run_id,
                    prov.get("source_type", "unknown"),
                    getattr(record, 'external_id', None),
                    getattr(record, 'record_type', None) and record.record_type.value if hasattr(record.record_type, 'value') else str(getattr(record, 'record_type', '')),
                    str(error)[:1000],
                    _tb.format_exc()[:2000],
                    _json.dumps(getattr(record, 'data', {}), default=str),
                    _json.dumps(prov, default=str),
                ],
            )
        except Exception as dlq_err:
            logger.debug("DLQ insert failed (table may not exist): %s", dlq_err)

    def _create_etl_run(
        self,
        run_id: str,
        source_type: SourceType,
        connector: BaseConnector,
    ) -> None:
        """Record the start of an ETL run."""
        self.db.execute(
            """
            INSERT INTO etl_runs (id, source_name, api_endpoint, query_params, status, started_at)
            VALUES (%s, %s, %s, %s, 'RUNNING', NOW())
            """,
            [run_id, source_type.value, "", "{}"],
        )

    def _source_has_landed_before(self, source_name: str, exclude_run_id: str) -> bool:
        """True if this source has EVER landed rows in a prior run — the signal that
        a current 0-row incremental fetch is a quiet window, not a never-landed
        broken source. DB read (kept out of the pure classifier)."""
        try:
            row = self.db.fetch_one(
                """
                SELECT 1 FROM etl_runs
                WHERE source_name = %s AND id <> %s
                  AND (outcome = %s OR COALESCE(records_inserted, 0) > 0)
                LIMIT 1
                """,
                [source_name, exclude_run_id, RUN_OUTCOME_LANDED],
            )
            return bool(row)
        except Exception:  # defensive: a health-classification query hiccup must
            # not crash run finalization. Fail CLOSED → no history → ZERO_ROWS
            # (the strict verdict), and log loudly (not debug) since a failing
            # health query is itself worth seeing.
            logger.warning("has-landed-before check failed for %s", source_name, exc_info=True)
            return False

    def _finalize_etl_run(
        self, run_id: str, result: PipelineResult, incremental: bool = False
    ) -> None:
        """Mark an ETL run as completed.

        `status` stays coarse (SUCCESS/PARTIAL) for backward-compatible consumers;
        `outcome` carries the richer signal (LANDED / NO_CHANGE / ZERO_ROWS) so a
        silent-zero run is no longer indistinguishable from a healthy one. An
        incremental 0-row run against a source that has landed before is a quiet
        window (SUCCESS_NO_CHANGE), not a failure — staleness stays Lane-2's job.
        """
        has_history = incremental and self._source_has_landed_before(
            result.source_type.value, run_id)
        outcome = classify_run_outcome(
            result.success,
            result.records_processed,
            result.records_inserted,
            result.records_updated,
            incremental=incremental,
            has_history=has_history,
        )
        self.db.execute(
            """
            UPDATE etl_runs
            SET status = %s,
                outcome = %s,
                records_processed = %s,
                records_inserted = %s,
                records_updated = %s,
                records_unchanged = %s,
                quality_score_avg = %s,
                hitl_items_created = %s,
                completed_at = NOW()
            WHERE id = %s
            """,
            [
                "SUCCESS" if result.success else "PARTIAL",
                outcome,
                result.records_processed,
                result.records_inserted,
                result.records_updated,
                result.records_unchanged,
                result.avg_quality_score,
                result.hitl_items_created,
                run_id,
            ],
        )

    def _fail_etl_run(self, run_id: str, error_message: str) -> None:
        """Mark an ETL run as failed."""
        self.db.execute(
            """
            UPDATE etl_runs
            SET status = 'FAILURE', outcome = %s, error_message = %s, completed_at = NOW()
            WHERE id = %s
            """,
            [RUN_OUTCOME_FAILURE, error_message[:2000], run_id],
        )
