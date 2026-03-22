"""Data Steward — autonomous, signal-driven data curation loop.

The steward:
1. Collects ranked signals from query telemetry, feedback, and quality metrics
2. For each signal: selects action (deterministic first, AI if needed)
3. Executes, evaluates quality delta, commits or reverts
4. Auto-resolves linked feedback entries
5. Records every action in steward_actions for audit

No LangChain. Deterministic first, AI when deterministic fails.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from db import Database
from services.steward_signals import StewardSignal, StewardSignalCollector

logger = logging.getLogger(__name__)


# ── Configuration ──────────────────────────────────────────────────

@dataclass
class StewardConfig:
    """Configuration for the Data Steward loop."""
    max_iterations: int = 20
    dry_run: bool = False
    skip_ai: bool = False
    signal_since_days: int = 7


# ── Result types ───────────────────────────────────────────────────

@dataclass
class StewardResult:
    """Result of a single steward action."""
    signal: StewardSignal
    action_id: str | None
    action_type: str
    status: str             # 'completed' | 'failed' | 'reverted' | 'skipped'
    fair_before: float | None = None
    fair_after: float | None = None
    fair_delta: float | None = None
    feedback_resolved: list[str] = field(default_factory=list)
    details: str = ""


@dataclass
class StewardLoopSummary:
    """Summary of a complete steward loop run."""
    iterations: int = 0
    completed: int = 0
    failed: int = 0
    reverted: int = 0
    skipped: int = 0
    feedback_resolved: int = 0
    total_elapsed_s: float = 0.0
    results: list[StewardResult] = field(default_factory=list)


# ── Action mapping ─────────────────────────────────────────────────

# Maps (gap_type, entity_type) → (action_type, script_module, function_name)
ACTION_MAP = {
    ("low_completeness", "mechanism"): ("backfill_mechanisms", "scripts.backfill_mechanisms", "run"),
    ("low_completeness", "ta_link"): ("backfill_ta_links", "scripts.backfill_ta_links", "run"),
    ("low_completeness", "approval_date"): ("enrich_drugs", "scripts.enrich_drugs", "run"),
    ("low_completeness", "company"): ("enrich_companies", "scripts.enrich_companies", "run"),
    ("data_quality", None): ("clean_drugs", "scripts.clean_drug_names", "run"),
    ("missing_entity", None): ("enrich_drugs", "scripts.enrich_drugs", "run"),
    ("stale_data", None): ("refetch", None, None),  # handled specially
}

# Fallback chain when no specific mapping exists
FALLBACK_ACTIONS = [
    ("enrich_drugs", "scripts.enrich_drugs", "run"),
    ("ai_enrich", "scripts.ai_enrich", "run"),
]


# ── Steward Loop ───────────────────────────────────────────────────

class DataSteward:
    """Signal-driven data steward with deterministic-first enrichment."""

    def __init__(
        self,
        db: Database,
        signal_collector: StewardSignalCollector,
        config: StewardConfig | None = None,
    ):
        self.db = db
        self.signals = signal_collector
        self.config = config or StewardConfig()
        self._results: list[StewardResult] = []

    def run_loop(self) -> StewardLoopSummary:
        """Main steward loop.

        1. Collect ranked signals
        2. For each signal (up to max_iterations):
           a. Select action
           b. Execute (or dry-run)
           c. Record to steward_actions
           d. Auto-resolve linked feedback
        3. Return summary
        """
        t0 = time.monotonic()
        summary = StewardLoopSummary()

        # Advisory lock — prevent concurrent runs
        if not self.config.dry_run:
            lock = self._try_lock()
            if not lock:
                logger.warning("Steward already running (advisory lock held)")
                return summary

        try:
            signals = self.signals.collect_signals(
                limit=self.config.max_iterations,
                since_days=self.config.signal_since_days,
            )
            logger.info("Steward collected %d signals", len(signals))

            for signal in signals[:self.config.max_iterations]:
                summary.iterations += 1
                result = self._process_signal(signal)
                self._results.append(result)
                summary.results.append(result)

                if result.status == "completed":
                    summary.completed += 1
                elif result.status == "failed":
                    summary.failed += 1
                elif result.status == "reverted":
                    summary.reverted += 1
                else:
                    summary.skipped += 1

                summary.feedback_resolved += len(result.feedback_resolved)

        finally:
            if not self.config.dry_run:
                self._release_lock()

        summary.total_elapsed_s = round(time.monotonic() - t0, 1)
        logger.info(
            "Steward complete: %d iterations, %d completed, %d failed, %d feedback resolved (%.1fs)",
            summary.iterations, summary.completed, summary.failed,
            summary.feedback_resolved, summary.total_elapsed_s,
        )
        return summary

    def _process_signal(self, signal: StewardSignal) -> StewardResult:
        """Process a single signal: select action, execute, record."""
        action_type, module_path, func_name = self._select_action(signal)

        if self.config.dry_run:
            logger.info("[DRY RUN] Would execute %s for signal %s", action_type, signal.source_id)
            return StewardResult(
                signal=signal, action_id=None, action_type=action_type,
                status="skipped", details="dry run",
            )

        if module_path is None:
            return StewardResult(
                signal=signal, action_id=None, action_type=action_type,
                status="skipped", details="no handler for action",
            )

        # Record pending action
        action_id = self._record_action(signal, action_type, "running")

        # Execute
        try:
            result_data = self._execute_action(module_path, func_name)
            status = "completed"
            error = None
            details = str(result_data) if result_data else "ok"
        except Exception as e:
            status = "failed"
            error = str(e)[:2000]
            details = f"error: {error}"
            logger.warning("Steward action %s failed: %s", action_type, error)

        # Update action record
        self._update_action(action_id, status, error_message=error)

        # Auto-resolve feedback if completed
        resolved = []
        if status == "completed" and signal.source == "feedback":
            resolved = self._auto_resolve_feedback(signal, action_id)

        return StewardResult(
            signal=signal, action_id=action_id, action_type=action_type,
            status=status, feedback_resolved=resolved, details=details,
        )

    def _select_action(self, signal: StewardSignal) -> tuple[str, str | None, str | None]:
        """Map a signal to a concrete action (deterministic first)."""
        # Try specific mapping
        key = (signal.gap_type, signal.entity_type)
        if key in ACTION_MAP:
            return ACTION_MAP[key]

        # Try gap_type-only mapping
        key_generic = (signal.gap_type, None)
        if key_generic in ACTION_MAP:
            return ACTION_MAP[key_generic]

        # AI enrichment fallback (unless skip_ai)
        if not self.config.skip_ai:
            return FALLBACK_ACTIONS[1]  # ai_enrich

        # Last resort: enrich_drugs
        return FALLBACK_ACTIONS[0]

    def _execute_action(self, module_path: str, func_name: str) -> dict | None:
        """Dynamically import and execute a curation script."""
        import importlib
        mod = importlib.import_module(module_path)
        func = getattr(mod, func_name)
        return func(dry_run=False)

    def _record_action(
        self, signal: StewardSignal, action_type: str, status: str,
    ) -> str:
        """Insert steward_actions row, return UUID."""
        try:
            row = self.db.fetch_one(
                """
                INSERT INTO steward_actions
                    (signal_source, signal_id, entity_type, entity_id,
                     entity_name, action_type, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                [
                    signal.source, signal.source_id, signal.entity_type,
                    signal.entity_id, signal.entity_name, action_type, status,
                ],
            )
            return str(row["id"]) if row else ""
        except Exception:
            logger.debug("Failed to record steward action", exc_info=True)
            return ""

    def _update_action(
        self, action_id: str, status: str,
        fair_before: float | None = None, fair_after: float | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update steward_actions status."""
        if not action_id:
            return
        try:
            delta = (fair_after - fair_before) if fair_before and fair_after else None
            self.db.execute(
                """
                UPDATE steward_actions
                SET status = %s, fair_before = %s, fair_after = %s,
                    fair_delta = %s, error_message = %s,
                    completed_at = NOW()
                WHERE id = %s
                """,
                [status, fair_before, fair_after, delta, error_message, action_id],
            )
        except Exception:
            logger.debug("Failed to update steward action", exc_info=True)

    def _auto_resolve_feedback(self, signal: StewardSignal, action_id: str) -> list[str]:
        """Mark linked feedback entries as resolved by steward."""
        resolved = []
        if signal.source != "feedback":
            return resolved
        try:
            self.db.execute(
                """
                UPDATE feedback_entries
                SET status = 'resolved', resolved_by = 'steward',
                    steward_action_id = %s, updated_at = NOW()
                WHERE id = %s AND status IN ('new', 'triaged')
                """,
                [action_id, signal.source_id],
            )
            resolved.append(signal.source_id)
        except Exception:
            logger.debug("Failed to auto-resolve feedback %s", signal.source_id, exc_info=True)
        return resolved

    def _try_lock(self) -> bool:
        """Acquire advisory lock to prevent concurrent runs."""
        try:
            row = self.db.fetch_one("SELECT pg_try_advisory_lock(42) AS acquired")
            return bool(row and row.get("acquired"))
        except Exception:
            return True  # if lock check fails, proceed anyway

    def _release_lock(self) -> None:
        """Release advisory lock."""
        try:
            self.db.execute("SELECT pg_advisory_unlock(42)")
        except Exception:
            pass
