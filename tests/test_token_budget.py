"""Tests for the Token Budget Manager (services/agent/budget.py).

Validates budget configuration defaults, pre-turn checks, usage tracking,
context compaction, and statistics reporting.
"""

from __future__ import annotations

import pytest

from services.agent.budget import BudgetStatus, TokenBudget, TokenBudgetConfig


class TestTokenBudgetConfig:
    """Test configuration defaults and derived properties."""

    def test_default_values(self):
        cfg = TokenBudgetConfig()
        assert cfg.model_max_tokens == 200_000
        assert cfg.output_reserve_pct == 0.20
        assert cfg.tools_reserve_pct == 0.15
        assert cfg.warning_threshold_pct == 0.80

    def test_available_for_context(self):
        """200K * (1 - 0.20 - 0.15) = 130K."""
        cfg = TokenBudgetConfig()
        assert cfg.available_for_context == 130_000

    def test_warning_threshold(self):
        """130K * 0.80 = 104K."""
        cfg = TokenBudgetConfig()
        assert cfg.warning_threshold == 104_000


class TestTokenBudget:
    """Test the TokenBudget tracker."""

    def test_estimate_tokens(self):
        """'hello world' is 11 chars -> 11 // 4 = 2 tokens (min 1)."""
        result = TokenBudget.estimate_tokens("hello world")
        assert result == 2  # 11 chars // 4 = 2

    def test_estimate_tokens_empty(self):
        assert TokenBudget.estimate_tokens("") == 1

    def test_estimate_tool_tokens(self):
        tools = [{"name": "search", "parameters": {"q": "string"}}]
        result = TokenBudget.estimate_tool_tokens(tools)
        assert result > 0

    def test_check_ok(self):
        """Small context should return OK."""
        budget = TokenBudget()
        status = budget.check_pre_turn("short context string")
        assert status == BudgetStatus.OK

    def test_check_warning(self):
        """Context near the warning threshold returns WARNING."""
        # Default warning threshold = 104K tokens -> ~416K chars
        cfg = TokenBudgetConfig()
        budget = TokenBudget(config=cfg)
        # Create text that estimates to just above 104K tokens
        # 104001 tokens * 4 chars = 416004 chars
        big_context = "x" * 416_004
        status = budget.check_pre_turn(big_context)
        assert status == BudgetStatus.WARNING

    def test_check_exceed(self):
        """Context over the available budget returns EXCEED."""
        cfg = TokenBudgetConfig()
        budget = TokenBudget(config=cfg)
        # 130001 tokens * 4 chars = 520004 chars
        huge_context = "x" * 520_004
        status = budget.check_pre_turn(huge_context)
        assert status == BudgetStatus.EXCEED

    def test_record_usage(self):
        """record_usage updates total_used and turn_count."""
        budget = TokenBudget()
        assert budget.total_used == 0
        assert budget.turn_count == 0

        budget.record_usage(input_tokens=1000, output_tokens=500)
        assert budget.total_used == 1500
        assert budget.turn_count == 1

        budget.record_usage(input_tokens=2000, output_tokens=300)
        assert budget.total_used == 3800
        assert budget.turn_count == 2

    def test_remaining_decreases(self):
        """remaining goes down after recording usage."""
        budget = TokenBudget()
        initial_remaining = budget.remaining
        assert initial_remaining == 200_000

        budget.record_usage(input_tokens=5000, output_tokens=3000)
        assert budget.remaining == 200_000 - 8000
        assert budget.remaining < initial_remaining

    def test_remaining_never_negative(self):
        budget = TokenBudget()
        budget.record_usage(input_tokens=300_000, output_tokens=0)
        assert budget.remaining == 0

    def test_compact_context(self):
        """Long context gets truncated with middle removed."""
        budget = TokenBudget()
        # Create context that exceeds available budget (130K tokens = 520K chars)
        long_context = "A" * 100 + "B" * 400 + "C" * 520_100
        # Target fewer tokens than the text has
        result = budget.compact_context(long_context, target_tokens=1000)
        assert len(result) < len(long_context)
        assert "[... context truncated for token budget ...]" in result

    def test_compact_preserves_short(self):
        """Short context that fits the budget is returned unchanged."""
        budget = TokenBudget()
        short = "This is a short context."
        result = budget.compact_context(short)
        assert result == short

    def test_compact_preserves_start_and_end(self):
        """Compaction keeps the beginning and end of the context."""
        cfg = TokenBudgetConfig(model_max_tokens=1000)
        budget = TokenBudget(config=cfg)
        start = "START_MARKER_" * 10
        middle = "M" * 5000
        end = "END_MARKER_" * 10
        context = start + middle + end
        result = budget.compact_context(context, target_tokens=100)
        assert result.startswith("START_MARKER_")
        assert result.endswith("END_MARKER_" * 5 + "END_MARKER_")

    def test_get_stats(self):
        """get_stats returns all expected fields."""
        budget = TokenBudget()
        budget.record_usage(input_tokens=100, output_tokens=50)

        stats = budget.get_stats()
        assert stats["model_max_tokens"] == 200_000
        assert stats["available_for_context"] == 130_000
        assert stats["warning_threshold"] == 104_000
        assert stats["total_used"] == 150
        assert stats["turn_count"] == 1
        assert stats["remaining"] == 200_000 - 150

    def test_custom_config(self):
        """Custom config propagates correctly."""
        cfg = TokenBudgetConfig(
            model_max_tokens=100_000,
            output_reserve_pct=0.10,
            tools_reserve_pct=0.10,
            warning_threshold_pct=0.90,
        )
        budget = TokenBudget(config=cfg)
        # available = 100K * (1 - 0.10 - 0.10) = 80K
        assert budget.config.available_for_context == 80_000
        # warning = 80K * 0.90 = 72K
        assert budget.config.warning_threshold == 72_000
