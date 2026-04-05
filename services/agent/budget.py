"""Token Budget Manager for the Agent Harness.

Tracks token usage across a session and enforces budget limits to prevent
context window overflows. Provides pre-turn checks, usage recording, and
context compaction when approaching limits.

Usage:
    budget = TokenBudget()
    status = budget.check_pre_turn(context, tool_pool=tools)
    if status == BudgetStatus.EXCEED:
        context = budget.compact_context(context)
    # ... call model ...
    budget.record_usage(input_tokens=resp.usage.input, output_tokens=resp.usage.output)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class BudgetStatus(Enum):
    OK = "ok"
    WARNING = "warning"
    EXCEED = "exceed"


@dataclass
class TokenBudgetConfig:
    """Configuration for token budget management."""

    model_max_tokens: int = 200_000
    output_reserve_pct: float = 0.20   # reserve 20% for model output
    tools_reserve_pct: float = 0.15    # reserve 15% for tool definitions
    warning_threshold_pct: float = 0.80  # warn at 80% usage

    @property
    def available_for_context(self) -> int:
        """Tokens available for context (after output + tools reserves)."""
        reserved = self.model_max_tokens * (self.output_reserve_pct + self.tools_reserve_pct)
        return int(self.model_max_tokens - reserved)

    @property
    def warning_threshold(self) -> int:
        return int(self.available_for_context * self.warning_threshold_pct)


class TokenBudget:
    """Tracks token usage across a session and enforces budget limits."""

    def __init__(self, config: TokenBudgetConfig | None = None):
        self.config = config or TokenBudgetConfig()
        self._total_used: int = 0
        self._turn_count: int = 0

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Rough token estimate: ~4 chars per token for English text."""
        return max(1, len(text) // 4)

    @staticmethod
    def estimate_tool_tokens(tool_definitions: list[dict]) -> int:
        """Estimate tokens consumed by tool definitions."""
        total = 0
        for tool in tool_definitions:
            # Tool defs are verbose JSON -- overestimate slightly
            total += len(json.dumps(tool)) // 3
        return total

    def check_pre_turn(self, context: str, tool_pool: list[dict] | None = None) -> BudgetStatus:
        """Check budget BEFORE a model invocation.

        Returns:
            BudgetStatus.OK -- proceed normally
            BudgetStatus.WARNING -- approaching limit, consider compaction
            BudgetStatus.EXCEED -- over budget, must compact before proceeding
        """
        context_tokens = self.estimate_tokens(context)
        tool_tokens = self.estimate_tool_tokens(tool_pool or [])
        total_estimated = context_tokens + tool_tokens
        available = self.config.available_for_context

        if total_estimated > available:
            logger.warning(
                "Token budget EXCEEDED: estimated=%d, available=%d (turn %d)",
                total_estimated, available, self._turn_count + 1,
            )
            return BudgetStatus.EXCEED

        if total_estimated > self.config.warning_threshold:
            logger.info(
                "Token budget WARNING: estimated=%d, threshold=%d (turn %d)",
                total_estimated, self.config.warning_threshold, self._turn_count + 1,
            )
            return BudgetStatus.WARNING

        return BudgetStatus.OK

    def record_usage(self, input_tokens: int, output_tokens: int) -> None:
        """Record actual token usage after a model call."""
        self._total_used += input_tokens + output_tokens
        self._turn_count += 1

    @property
    def total_used(self) -> int:
        return self._total_used

    @property
    def turn_count(self) -> int:
        return self._turn_count

    @property
    def remaining(self) -> int:
        """Estimated remaining tokens for this session."""
        return max(0, self.config.model_max_tokens - self._total_used)

    def compact_context(self, context: str, target_tokens: int | None = None) -> str:
        """Compact context to fit within budget.

        Strategy: truncate from the middle, preserving start (system prompt)
        and end (recent context).
        """
        if target_tokens is None:
            target_tokens = self.config.available_for_context

        current = self.estimate_tokens(context)
        if current <= target_tokens:
            return context

        # Keep first 20% and last 60%, truncate middle
        chars = len(context)
        keep_start = int(chars * 0.20)
        keep_end = int(chars * 0.60)

        truncated = (
            context[:keep_start]
            + "\n\n[... context truncated for token budget ...]\n\n"
            + context[-keep_end:]
        )

        logger.info(
            "Context compacted: %d -> %d tokens (kept %d%% of %d chars)",
            current, self.estimate_tokens(truncated),
            int(len(truncated) / chars * 100), chars,
        )
        return truncated

    def get_stats(self) -> dict:
        """Get budget statistics."""
        return {
            "model_max_tokens": self.config.model_max_tokens,
            "available_for_context": self.config.available_for_context,
            "warning_threshold": self.config.warning_threshold,
            "total_used": self._total_used,
            "turn_count": self._turn_count,
            "remaining": self.remaining,
        }
