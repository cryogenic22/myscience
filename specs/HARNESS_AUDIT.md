# Market Zero — Agentic Harness Audit

*Date: 2026-04-01*
*Against: Agentic System Design Principles (specs/TESTING_GUIDE.md)*

---

## Current State vs Harness Checklist

### Module 1: Tool Registry

| Criterion | Status | Where |
|-----------|--------|-------|
| Tools registered centrally with metadata | **Partial** | `services/agent/tools/` has BaseTool + 4 tools (GraphTool, MetricsTool, RAGTool, SQLTool) with name/description. But chat handlers, connectors, and steward actions are NOT registered as tools. |
| Side-effect profile declared | **No** | No tool declares `side_effects: read/write/none` |
| Descriptions from model's perspective | **Partial** | Agent tools have descriptions. Connectors don't have LLM-facing descriptions. |
| Tools versioned | **No** | No versioning on any tool |

**Gap**: We have 4 agent tools but ~20+ implicit tools (connectors, pipeline hooks, steward actions) that are NOT in a registry. The Data Steward, Research Agent, and Entity Agents all "do things" but aren't formalized as tool invocations.

### Module 2: Permission System

| Criterion | Status | Where |
|-----------|--------|-------|
| Trust tiers assigned | **No** | No tier system exists |
| Tier enforcement in harness | **No** | No enforcement layer |
| Approval workflows | **Partial** | HITL review queue exists for entity resolution, but no general approval system |
| Autonomous mode restricted | **No** | Steward runs in autonomous mode with full DB write access |

**Gap**: The Data Steward writes to the DB autonomously with no permission checks. Connector runs can modify 100K+ records with no approval gate. This is the biggest architectural gap.

### Module 3: Session Persistence

| Criterion | Status | Where |
|-----------|--------|-------|
| Session state stored externally | **Partial** | `services/workspace.py` has session save/load, `etl_runs` tracks pipeline sessions. But steward/agent loops have NO session persistence. |
| Checkpoints after side-effects | **No** | Pipeline records per-record results but doesn't checkpoint mid-run. A crash at record 500 of 2000 means re-processing all 2000. |
| Tested recovery path | **No** | No recovery mechanism for interrupted agent runs |

**Gap**: The background agent loop (`app.py`) runs steward + connectors every 2 hours. If it crashes mid-run, there's no checkpoint — it starts over. The chunked FAERS fetch helps but isn't true session persistence.

### Module 4: State Architecture

| Criterion | Status | Where |
|-----------|--------|-------|
| Workflow state separate from conversation | **Yes** | `PipelineResult` tracks ETL state, `StewardLoopSummary` tracks steward state, separate from chat `ConversationMemory` |
| Conversation history windowed | **Yes** | `ConversationMemory` has token-budgeted eviction, chat uses last 6 messages |
| Workflow state is ground truth | **Yes** | `etl_runs` table, `data_change_log`, `steward_actions` are the source of truth |

**Status**: This is one of our stronger areas.

### Module 5: Token Budget Management

| Criterion | Status | Where |
|-----------|--------|-------|
| Budget tracked across session | **Partial** | `ConversationMemory` tracks token usage. But LLM calls in `services/llm.py` don't check budget before invocation. |
| Pre-turn check before model invocation | **No** | `LLMSynthesizer.synthesize()` truncates context but doesn't check budget proactively |
| Context compaction logic | **Partial** | CTX context builder has compression. Conversation memory has eviction. But no unified budget system. |

**Gap**: We truncate inputs but don't track cumulative cost or refuse calls when budget is exhausted.

### Module 6-8: Observability

| Criterion | Status | Where |
|-----------|--------|-------|
| State transitions emit events | **Partial** | SSE streaming for chat. `services/telemetry.py` logs CTX events. Pipeline logs to `etl_runs`. But no unified event stream. |
| Tool invocations logged with hash | **Partial** | Pipeline logs source + record count. But individual tool calls aren't logged with argument hashes. |
| Post-execution verification | **Partial** | `verify_narrative_numbers()` checks LLM output. `check_response()` verifies entity presence. But no general verification layer. |
| Verification failures handled | **Partial** | Unverified bold numbers are stripped. But many failures are logged-only, not acted upon. |

**Gap**: No unified event bus. Observability is scattered across telemetry, pipeline logs, and steward actions. No way to subscribe to "all agent events" from one stream.

### Module 9: Tool Pool Assembly

| Criterion | Status | Where |
|-----------|--------|-------|
| Tool pool assembled per step | **No** | Agent tools are static — all 4 sent every turn |
| Compaction strategy | **No** | No tool pool pruning |
| Schemas preserved during compaction | **N/A** | No compaction exists |

### Agent Types

| Criterion | Status | Where |
|-----------|--------|-------|
| Typed agents with responsibilities | **Partial** | `AutonomousResearchAgent`, `DataSteward`, `EntityAgentOrchestrator` have defined roles. But they're classes, not typed with explicit contracts. |
| Handoff contracts | **No** | No formal handoff between agents |
| Verifier between executor and orchestrator | **No** | No verifier agent type |

---

## What We Already Have (Strengths)

1. **State separation** is good — workflow state (etl_runs, change_log, steward_actions) is cleanly separate from conversation state
2. **Observability partial** — telemetry service, CTX metrics, pipeline result logging exist
3. **Multiple agent types** — DataSteward, ResearchAgent, EntityAgents, FeedbackLoops — but they need formal contracts
4. **HITL queue** — exists for entity resolution, could be generalized
5. **Token budgeting** — ConversationMemory has eviction, CTX builder has compression

## What's Missing (Priority Order)

### P0: Agent Harness Foundation
1. **Tool Registry** — centralize all tools (agent tools, connector actions, steward actions, curation actions) into a single registry with metadata
2. **Permission Engine** — trust tiers for tool invocations, especially for write operations
3. **Session Persistence** — checkpoint-based recovery for long-running agent loops

### P1: Observability
4. **Unified Event Stream** — single event bus for all agent activity (tool calls, state changes, errors)
5. **Structured Logging** — replace scattered `logger.info` with structured events
6. **Verification Layer** — post-execution checks on every tool call output

### P2: Budget & Assembly
7. **Token Budget Manager** — pre-turn budget checks, cumulative tracking
8. **Tool Pool Assembly** — curate tools per step, not static

### P3: Contracts
9. **Agent Type Registry** — formal type declarations with tool access and state ownership
10. **Handoff Contracts** — explicit pre/postconditions between agent types

---

## Recommended First Steps

### Step 1: Formalize the Tool Registry (2-3 days)

Create `services/agent/registry.py`:

```python
@dataclass
class ToolDefinition:
    name: str
    version: str
    description: str
    input_schema: dict
    output_schema: dict
    side_effects: str  # none | read | write | external
    trust_tier: str    # public | standard | elevated | system
    timeout_ms: int = 5000
    retryable: bool = True

class ToolRegistry:
    def register(self, tool: ToolDefinition) -> None
    def get(self, name: str) -> ToolDefinition
    def get_by_tags(self, tags: list[str]) -> list[ToolDefinition]
    def get_by_tier(self, max_tier: str) -> list[ToolDefinition]
```

Register existing tools:
- `graph_search` (read, standard)
- `metrics_query` (read, standard)
- `rag_search` (read, standard)
- `sql_query` (read, elevated)
- `pipeline_run` (write, elevated)
- `steward_curate` (write, standard)
- `entity_merge` (write, elevated)
- `source_refresh` (write, standard)

### Step 2: Add Permission Enforcement (1-2 days)

Wrap the background agent loop with permission checks:

```python
# In app.py background agent loop:
if tool.trust_tier == "elevated":
    log_elevated_action(tool.name, args)
if tool.trust_tier == "system":
    raise PermissionDenied("System-tier tools require explicit approval")
```

### Step 3: Session Checkpointing (2-3 days)

Add a `session_checkpoints` table and checkpoint after every N records in the pipeline:

```sql
CREATE TABLE agent_sessions (
    id UUID PRIMARY KEY,
    agent_type TEXT NOT NULL,
    status TEXT DEFAULT 'running',
    current_step INT DEFAULT 0,
    checkpoint_data JSONB,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    last_checkpoint TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);
```

### Step 4: Unified Event Stream (2-3 days)

Create `services/agent/event_stream.py`:

```python
class AgentEvent:
    event_type: AgentEventType
    session_id: str
    agent_type: str
    tool_name: str | None
    trust_tier: str | None
    args_hash: str | None
    result_status: str
    timestamp: datetime

class EventStream:
    def emit(self, event: AgentEvent) -> None
    def subscribe(self, handler: Callable) -> None
```

Wire into the steward loop, pipeline runner, and background agents.

---

*This audit is a starting point for discussion. The harness principles document is excellent — it gives us a clear target architecture. The question is sequencing: what do we build first to get the most governance and reliability improvement?*
