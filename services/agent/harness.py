"""MarketZeroHarness — unified agent execution wrapper.

Wraps ToolRegistry, PermissionEngine, SessionStore, EventStream, and
TokenBudget into a single structured execution model for any agent task.

Usage:
    harness = MarketZeroHarness(db=db)
    result = harness.run(
        agent_type="data_steward",
        goal="Run curation cycle",
        steps=[
            ("steward_curate", {"max_iterations": 20}),
            ("mv_refresh", {}),
        ],
    )
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from services.agent.registry import ToolRegistry, ToolDefinition, create_default_registry
from services.agent.permissions import PermissionEngine, PermissionDenied, SessionMode
from services.agent.session_store import SessionStore, AgentSession
from services.agent.event_stream import EventStream, AgentEventType, AgentEvent
from services.agent.budget import TokenBudget, TokenBudgetConfig, BudgetStatus

logger = logging.getLogger(__name__)


@dataclass
class HarnessConfig:
    """Configuration for the agent harness."""
    session_mode: SessionMode = SessionMode.STANDARD
    max_steps: int = 50
    checkpoint_every: int = 1  # checkpoint after every N steps
    budget: TokenBudgetConfig = field(default_factory=TokenBudgetConfig)


@dataclass
class StepResult:
    """Result of a single harness step."""
    step: int
    tool_name: str
    status: str  # ok | error | denied | skipped
    duration_ms: float = 0
    error: Optional[str] = None
    output: Optional[dict] = None


@dataclass
class HarnessResult:
    """Result of a full harness run."""
    session_id: str
    agent_type: str
    status: str  # completed | failed | partial
    steps_completed: int = 0
    steps_failed: int = 0
    steps_denied: int = 0
    total_duration_ms: float = 0
    step_results: list[StepResult] = field(default_factory=list)
    error: Optional[str] = None


class MarketZeroHarness:
    """Unified agent execution harness.

    Wraps: ToolRegistry, PermissionEngine, SessionStore, EventStream, TokenBudget.

    Usage:
        harness = MarketZeroHarness(db=db)
        result = harness.run(
            agent_type="data_steward",
            goal="Run curation cycle",
            steps=[
                ("steward_curate", {"max_iterations": 20}),
                ("mv_refresh", {}),
            ],
        )
    """

    def __init__(
        self,
        db=None,
        config: HarnessConfig = None,
        registry: ToolRegistry = None,
        permissions: PermissionEngine = None,
        session_store: SessionStore = None,
        event_stream: EventStream = None,
        budget: TokenBudget = None,
    ):
        self.config = config or HarnessConfig()
        self.registry = registry or create_default_registry()
        self.permissions = permissions or PermissionEngine(default_mode=self.config.session_mode)
        self.session_store = session_store or SessionStore(db=db)
        self.event_stream = event_stream or EventStream(db=db)
        self.budget = budget or TokenBudget(self.config.budget)
        self._tool_executors: dict[str, Callable] = {}

    def register_executor(self, tool_name: str, executor: Callable) -> None:
        """Register an executor function for a tool.

        The executor is a callable that takes (args: dict) -> dict.
        """
        self._tool_executors[tool_name] = executor

    def run(
        self,
        agent_type: str,
        goal: str = "",
        steps: list[tuple[str, dict]] = None,
        executor: Callable = None,
    ) -> HarnessResult:
        """Execute a structured agent run through the harness.

        Args:
            agent_type: Type of agent (data_steward, research_agent, etc.)
            goal: Human-readable description of the goal
            steps: List of (tool_name, args) tuples to execute
            executor: Optional single executor for all steps (overrides registered executors)

        Returns:
            HarnessResult with status, step results, and timing.
        """
        steps = steps or []
        start_time = time.time()

        # Start session
        session = self.session_store.start(
            agent_type=agent_type,
            goal=goal,
            total_steps=len(steps),
        )

        self.event_stream.emit(AgentEvent(
            event_type=AgentEventType.TURN_START,
            session_id=session.id,
            agent_type=agent_type,
            metadata={"goal": goal, "total_steps": len(steps)},
        ))

        result = HarnessResult(
            session_id=session.id,
            agent_type=agent_type,
            status="completed",  # optimistic; overridden on failure
        )

        try:
            for i, (tool_name, args) in enumerate(steps):
                if i >= self.config.max_steps:
                    logger.warning("Max steps (%d) reached for session %s", self.config.max_steps, session.id)
                    break

                step_result = self._execute_step(
                    session=session,
                    step_num=i + 1,
                    tool_name=tool_name,
                    args=args,
                    executor=executor,
                )
                result.step_results.append(step_result)

                if step_result.status == "ok":
                    result.steps_completed += 1
                elif step_result.status == "denied":
                    result.steps_denied += 1
                else:
                    result.steps_failed += 1

                # Checkpoint
                if (i + 1) % self.config.checkpoint_every == 0:
                    self.session_store.checkpoint(
                        session.id,
                        step=i + 1,
                        data={"last_tool": tool_name, "status": step_result.status},
                    )
                    self.event_stream.emit(AgentEvent(
                        event_type=AgentEventType.SESSION_CHECKPOINT,
                        session_id=session.id,
                        agent_type=agent_type,
                        metadata={"step": i + 1},
                    ))

            # Complete
            result.status = "completed"
            self.session_store.complete(session.id)
            self.event_stream.emit(AgentEvent(
                event_type=AgentEventType.SESSION_COMPLETED,
                session_id=session.id,
                agent_type=agent_type,
                metadata={
                    "completed": result.steps_completed,
                    "failed": result.steps_failed,
                    "denied": result.steps_denied,
                },
            ))

        except Exception as e:
            result.status = "failed"
            result.error = str(e)
            self.session_store.fail(session.id, str(e))
            self.event_stream.emit(AgentEvent(
                event_type=AgentEventType.SESSION_FAILED,
                session_id=session.id,
                agent_type=agent_type,
                result_status="error",
                metadata={"error": str(e)[:500]},
            ))

        result.total_duration_ms = (time.time() - start_time) * 1000
        return result

    def _execute_step(
        self,
        session: AgentSession,
        step_num: int,
        tool_name: str,
        args: dict,
        executor: Callable = None,
    ) -> StepResult:
        """Execute a single step through the harness pipeline."""
        start = time.time()

        # 1. Look up tool
        tool_def = self.registry.get(tool_name)
        if not tool_def:
            return StepResult(
                step=step_num, tool_name=tool_name,
                status="error", error=f"Unknown tool: {tool_name}",
            )

        # 2. Permission check
        try:
            self.permissions.enforce(tool_name, tool_def.trust_tier)
        except PermissionDenied as e:
            self.event_stream.emit(AgentEvent(
                event_type=AgentEventType.PERMISSION_DENIED,
                session_id=session.id,
                agent_type=session.agent_type,
                tool_name=tool_name,
                trust_tier=tool_def.trust_tier,
                result_status="denied",
            ))
            return StepResult(
                step=step_num, tool_name=tool_name,
                status="denied", error=str(e),
            )

        # 3. Emit tool_invoked event
        self.event_stream.emit_tool_invoked(
            session_id=session.id,
            agent_type=session.agent_type,
            tool_name=tool_name,
            trust_tier=tool_def.trust_tier,
            args=args,
        )

        # 4. Execute
        try:
            exec_fn = executor or self._tool_executors.get(tool_name)
            if exec_fn:
                output = exec_fn(args)
            else:
                # No executor registered — log and skip
                logger.info("No executor for tool %s — skipping execution", tool_name)
                output = {"skipped": True, "reason": "no executor registered"}

            duration = (time.time() - start) * 1000

            # 5. Emit tool_completed
            self.event_stream.emit_tool_completed(
                session_id=session.id,
                agent_type=session.agent_type,
                tool_name=tool_name,
                metadata={"duration_ms": round(duration, 1)},
            )

            return StepResult(
                step=step_num, tool_name=tool_name,
                status="ok", duration_ms=duration, output=output,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000

            self.event_stream.emit_tool_failed(
                session_id=session.id,
                agent_type=session.agent_type,
                tool_name=tool_name,
                error=str(e),
            )

            return StepResult(
                step=step_num, tool_name=tool_name,
                status="error", duration_ms=duration, error=str(e),
            )
