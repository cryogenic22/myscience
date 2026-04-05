# Agentic System Design Principles
### Technical Guidelines for Teams Building Agent-Based Pipelines

> **Purpose:** This document translates lessons from production-grade agentic system internals into concrete design principles and implementation guidance for our engineering teams. It is intended as a living reference — consult it when designing new agent systems, reviewing existing ones, or establishing sprint gates for agentic delivery.

---

## Table of Contents

1. [The 80/20 Rule of Agent Development](#1-the-8020-rule-of-agent-development)
2. [Module 1 — Tool Registry](#2-module-1--tool-registry)
3. [Module 2 — Permission System and Trust Tiers](#3-module-2--permission-system-and-trust-tiers)
4. [Module 3 — Session Persistence](#4-module-3--session-persistence)
5. [Module 4 — State Architecture](#5-module-4--state-architecture)
6. [Module 5 — Token Budget Management](#6-module-5--token-budget-management)
7. [Module 6–8 — Observability Layer](#7-module-68--observability-layer)
8. [Module 9 — Tool Pool Assembly and Compaction](#8-module-9--tool-pool-assembly-and-compaction)
9. [Agent Types and Responsibilities](#9-agent-types-and-responsibilities)
10. [The Agentic Harness Pattern](#10-the-agentic-harness-pattern)
11. [Modular Architecture Checklist](#11-modular-architecture-checklist)
12. [Guiding Principles Summary](#12-guiding-principles-summary)

---

## 1. The 80/20 Rule of Agent Development

> **Building agents is approximately 80% infrastructure and plumbing — not model prompting.**

This is the most important reframe for teams new to agentic system design. The temptation is to focus on prompt quality, model selection, and output evaluation. These matter — but they sit on top of a foundation that must be built deliberately first.

The infrastructure layer includes:

- How tools are registered, discovered, and invoked
- How permissions and trust are enforced at the boundary of each action
- How sessions survive failures, restarts, and partial completions
- How workflow state is separated from conversational context
- How token budgets are tracked and respected before each turn
- How events are streamed, logged, and verified at runtime
- How the tool pool is assembled, pruned, and compacted for each context

**If this infrastructure is implicit, inconsistent, or missing — the system will be fragile regardless of how well the model is prompted.**

---

## 2. Module 1 — Tool Registry

### What it is

A centralised, metadata-first registry that defines every tool available to an agent: its name, description, input schema, output schema, side-effect profile, and trust requirements.

### Why it matters

Without a registry, tool definitions are scattered, duplicated, and inconsistently described. The model receives different tool descriptions in different contexts, leading to unreliable invocation behaviour. Teams also lose the ability to audit, version, or govern tool usage at scale.

### Design guidance

**Metadata-first means the registry entry is the source of truth — not the implementation.**

Each tool registration should declare:

```yaml
tool:
  name: extract_table
  version: "1.2.0"
  description: >
    Extracts structured tabular data from a document section.
    Use when the input contains a delimited or visually structured table.
    Do NOT use for free-form prose or unstructured lists.
  input_schema:
    type: object
    properties:
      document_id: { type: string }
      section_hint: { type: string, optional: true }
  output_schema:
    type: object
    properties:
      rows: { type: array }
      confidence: { type: number }
  side_effects: none           # none | read | write | external
  trust_tier: standard         # public | standard | elevated | system
  timeout_ms: 5000
  retryable: true
```

**Implementation rules:**

- All tool descriptions must be written from the model's perspective — describe *when* to use it and *when not* to use it, not just what it does
- Side effect profiles (`none`, `read`, `write`, `external`) must be declared explicitly and enforced at runtime
- Tools are versioned; consumers pin to a version range, not `latest`
- The registry is queryable — agents can discover available tools at runtime without hardcoding the full set

### Anti-patterns to avoid

- Defining tools inline in prompt strings
- Copy-pasting tool definitions across agent configurations
- Omitting negative guidance (when NOT to use a tool)
- Undeclared side effects

---

## 3. Module 2 — Permission System and Trust Tiers

### What it is

A layered permission model that assigns every tool invocation to a trust tier, and enforces those tiers at the execution boundary — not just at the prompt level.

### Why it matters

Models can be manipulated. A permission system that exists only in the system prompt is not a permission system — it is an aspiration. Real enforcement happens in the harness, before any tool call is executed.

### Trust tier model

Define a minimum of four tiers:

| Tier | Description | Example tools | Requires human approval |
|---|---|---|---|
| `public` | Read-only, no external calls, fully reversible | Search index, in-memory lookup | No |
| `standard` | Read from live systems, no writes | Fetch document, query database | No |
| `elevated` | Writes to internal systems | Update record, create file | Configurable |
| `system` | Destructive, irreversible, or external | Delete, email, API call to third party | Yes (by default) |

### Design guidance

**At the harness level, before any tool is invoked:**

```python
def execute_tool(tool_name: str, args: dict, session_context: SessionContext):
    tool = registry.get(tool_name)
    
    # Tier enforcement — not negotiable
    if tool.trust_tier == "system" and not session_context.has_approval(tool_name):
        raise PermissionDenied(f"{tool_name} requires explicit approval for this session")
    
    if tool.trust_tier == "elevated" and session_context.mode == "autonomous":
        queue_for_review(tool_name, args, session_context)
        return PendingApproval()
    
    return tool.execute(args)
```

**Additional rules:**

- Trust tier cannot be overridden by the model — only by the orchestration layer with authenticated context
- Approval workflows for `elevated` and `system` tiers must be logged with the approver identity and timestamp
- Sessions operating in fully autonomous mode must have their accessible tool pool restricted at assembly time — do not rely on the model to self-limit

### Anti-patterns to avoid

- "The prompt says not to delete things" as a security control
- Mixing `system`-tier tools into the standard tool pool without scoping
- Implicit trust based on agent type rather than tool-level declaration

---

## 4. Module 3 — Session Persistence

### What it is

A durable session layer that captures enough state to resume an agent run after a crash, timeout, restart, or deployment — without re-running completed steps.

### Why it matters

Long-running agentic tasks fail. Networks drop. Containers restart. Without persistence, a failure at step 47 of a 50-step pipeline means starting over. With it, the system resumes from a known checkpoint.

### Design guidance

**A session record must capture:**

```json
{
  "session_id": "sess_abc123",
  "created_at": "2026-04-03T09:00:00Z",
  "last_checkpoint": "2026-04-03T09:14:32Z",
  "status": "in_progress",
  "current_step": 12,
  "completed_steps": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
  "step_outputs": { "step_1": {...}, "step_2": {...} },
  "tool_call_log": [...],
  "context_snapshot": { ... },
  "error_log": []
}
```

**Checkpoint cadence:**

- Write a checkpoint after every tool call that has side effects
- Write a checkpoint after every completed step in a multi-step workflow
- Do not checkpoint mid-stream during a pure inference turn (wasteful)

**Recovery logic:**

```python
def resume_or_start(session_id: str) -> Session:
    existing = store.get(session_id)
    if existing and existing.status == "in_progress":
        log.info(f"Resuming session {session_id} from step {existing.current_step}")
        return Session.from_checkpoint(existing)
    return Session.new(session_id)
```

**Storage requirements:**

- Session store must be external to the agent process (database, object store — not in-memory)
- Checkpoints must be atomic writes — partial writes corrupt recovery
- Retention policy: keep completed sessions for the audit window, not indefinitely

### Anti-patterns to avoid

- Storing session state in the conversation history only
- Assuming a container or process will stay alive for the duration of a long task
- Not writing a checkpoint before any `elevated` or `system` tier tool call

---

## 5. Module 4 — State Architecture

### What it is

A strict separation between **workflow state** (where are we in the task?) and **conversation state** (what has been said?).

### Why it matters

These two things are fundamentally different in nature, lifecycle, and storage requirements. Conflating them is one of the most common architectural mistakes in agentic systems.

| | Workflow state | Conversation state |
|---|---|---|
| **Purpose** | Track task progress, step outputs, decisions made | Provide the model with context for its next turn |
| **Lifecycle** | Persists across the entire task, survives restarts | Valid for the current turn or session window |
| **Storage** | Durable external store | In-memory or short-lived cache |
| **Size** | Grows with task complexity | Bounded by context window limits |
| **Owner** | Orchestration layer | Context assembly layer |

### Design guidance

**Never pass workflow state directly into the conversation history.** Instead, summarise the relevant parts of workflow state into the context for each turn.

```python
def build_turn_context(workflow_state: WorkflowState, conversation_history: list) -> list:
    # Summarise workflow state into a structured context block
    workflow_summary = {
        "role": "user",
        "content": f"[WORKFLOW CONTEXT]\nCurrent step: {workflow_state.current_step}\n"
                   f"Completed: {workflow_state.completed_steps}\n"
                   f"Available outputs: {list(workflow_state.step_outputs.keys())}"
    }
    return [workflow_summary] + conversation_history[-N_TURNS:]
```

**Key rules:**

- Workflow state is the ground truth — not the conversation
- If the conversation and workflow state disagree, trust workflow state
- Keep conversation history windowed — do not grow it unboundedly
- Step outputs referenced in a turn should be injected selectively, not dumped wholesale

### Anti-patterns to avoid

- Encoding workflow progress as a series of assistant messages
- Using conversation length as a proxy for task progress
- Passing the entire step output history into every context window

---

## 6. Module 5 — Token Budget Management

### What it is

Proactive tracking and enforcement of token limits, applied *before* each turn — not reactively when the model hits a wall.

### Why it matters

Context window truncation mid-task is silent and dangerous. The model loses context without knowing it has lost context. Pre-turn checks prevent this.

### Design guidance

**Track a budget object throughout the session:**

```python
@dataclass
class TokenBudget:
    model_max: int           # Hard limit from provider
    reserved_for_output: int # Tokens held back for generation
    reserved_for_tools: int  # Estimated tool definition overhead
    used_so_far: int         # Accumulated input tokens this session
    
    @property
    def available(self) -> int:
        return self.model_max - self.reserved_for_output - self.reserved_for_tools - self.used_so_far
    
    def check(self, estimated_input: int) -> BudgetStatus:
        if estimated_input > self.available:
            return BudgetStatus.EXCEED
        if estimated_input > self.available * 0.8:
            return BudgetStatus.WARNING
        return BudgetStatus.OK
```

**Pre-turn check pattern:**

```python
def prepare_turn(context: list, tool_pool: list, budget: TokenBudget):
    estimated = estimate_tokens(context) + estimate_tokens(tool_pool)
    status = budget.check(estimated)
    
    if status == BudgetStatus.EXCEED:
        context = compact_context(context)           # Summarise or prune
        tool_pool = reduce_tool_pool(tool_pool)      # Drop lower-priority tools
        
    elif status == BudgetStatus.WARNING:
        log.warning(f"Approaching token limit: {budget.available} remaining")
        
    return context, tool_pool
```

**Estimation rules:**

- Over-estimate tool definitions — they cost more than they look
- Reserve at minimum 15–20% of the context window for model output
- Track cumulative usage across turns, not just per-turn

### Anti-patterns to avoid

- Discovering context overflow at inference time
- Using character count as a token proxy without calibration
- Not accounting for tool definition tokens in the budget

---

## 7. Module 6–8 — Observability Layer

### What it is

Three distinct but related concerns: **streaming events** (real-time visibility into what the agent is doing), **structured logging** (durable audit trail), and **verification** (post-execution checks on outputs and actions).

### Why it matters

An agent that cannot be observed cannot be debugged, governed, or improved. In regulated or enterprise contexts, the observability layer is also your audit log — it must be complete and tamper-evident.

### 6: Streaming events

Every meaningful state transition should emit an event:

```python
class AgentEventType(Enum):
    TURN_START = "turn_start"
    TOOL_INVOKED = "tool_invoked"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"
    STEP_COMPLETED = "step_completed"
    BUDGET_WARNING = "budget_warning"
    APPROVAL_REQUESTED = "approval_requested"
    SESSION_CHECKPOINT = "session_checkpoint"
    SESSION_COMPLETED = "session_completed"
    SESSION_FAILED = "session_failed"
```

Events should be emitted to a stream (message bus, SSE endpoint, or webhook) that downstream consumers — dashboards, alerting, human review queues — can subscribe to.

### 7: Structured logging

Every log entry should be structured, not free text:

```json
{
  "timestamp": "2026-04-03T09:14:32.441Z",
  "session_id": "sess_abc123",
  "step": 12,
  "event": "tool_invoked",
  "tool": "extract_table",
  "trust_tier": "standard",
  "input_token_estimate": 1240,
  "args_hash": "sha256:abc...",
  "trace_id": "trace_xyz789"
}
```

**Logging requirements:**

- Every tool invocation must be logged with its arguments hash (not the raw arguments if they contain sensitive data)
- Tool failures must log the error type, not just the message
- All `elevated` and `system` tier approvals must be logged with approver identity
- Logs must be immutable once written — no update or delete

### 8: Verification

Post-execution checks are a separate concern from logging. Implement a verification layer that runs after each tool call and after each step:

```python
def verify_step_output(step_id: str, output: dict, spec: StepSpec) -> VerificationResult:
    checks = [
        schema_check(output, spec.output_schema),
        confidence_check(output, spec.min_confidence),
        completeness_check(output, spec.required_fields),
    ]
    failures = [c for c in checks if not c.passed]
    return VerificationResult(passed=len(failures) == 0, failures=failures)
```

Verification failures should trigger either a retry (with budget), a fallback path, or a human review request — not silent continuation.

### Anti-patterns to avoid

- Free-text log messages that cannot be queried or parsed
- Logging only on failure — you need the success path too
- Treating verification as optional or "nice to have"
- Not separating observability concerns from business logic

---

## 8. Module 9 — Tool Pool Assembly and Compaction

### What it is

The deliberate process of assembling the right set of tools for each agent turn — and compacting or pruning that set as the context fills up.

### Why it matters

Sending every available tool to the model on every turn is wasteful, noisy, and expensive. Tool definitions consume tokens. Irrelevant tools create noise that degrades model decision-making. As a session progresses and context fills, the tool pool must be actively managed.

### Design guidance

**Assembly — match tools to the current step:**

```python
def assemble_tool_pool(current_step: StepSpec, session_context: SessionContext) -> list:
    candidate_tools = registry.get_by_tags(current_step.required_tool_tags)
    
    # Filter by trust tier given current session mode
    permitted_tools = [t for t in candidate_tools 
                       if session_context.permits(t.trust_tier)]
    
    # Rank by relevance to current step
    ranked_tools = rank_by_relevance(permitted_tools, current_step)
    
    # Cap at token budget
    return select_within_budget(ranked_tools, budget.tools_allocation)
```

**Compaction — when the budget is under pressure:**

```python
def compact_tool_pool(tool_pool: list, budget_remaining: int) -> list:
    # Drop tools already successfully used this step
    active_pool = [t for t in tool_pool if not already_completed(t)]
    
    # Drop tools below priority threshold
    priority_pool = [t for t in active_pool if t.priority >= COMPACTION_THRESHOLD]
    
    # If still over budget, truncate descriptions (not schemas)
    return truncate_descriptions_to_fit(priority_pool, budget_remaining)
```

**Key principles:**

- Tool pool assembly is a first-class operation, not an afterthought
- Never send the full registry to the model — curate per step
- Tool descriptions can be shortened under compaction; input/output schemas must be preserved intact
- Log every compaction event — it affects model behaviour

### Anti-patterns to avoid

- Static tool pools that never change across a multi-step workflow
- Dropping tools silently without logging the compaction
- Truncating tool schemas (as opposed to descriptions) under budget pressure

---

## 9. Agent Types and Responsibilities

### Why typed agents matter

An untyped agent is an agent with unclear responsibilities. When any agent can do anything, there are no clean boundaries, no sensible defaults, and no way to audit which agent was responsible for which decision.

Assign every agent in your system a type, and constrain its tool access and behaviour accordingly.

### Recommended base types

| Agent type | Primary responsibility | Typical tool access | State ownership |
|---|---|---|---|
| **Orchestrator** | Decompose goals, assign sub-tasks, track progress | Workflow tools, delegation only | Workflow state |
| **Executor** | Carry out a specific bounded task | Step-specific tool pool | Step output only |
| **Retriever** | Fetch and filter information from sources | Read-only, `public` and `standard` tiers | None (stateless) |
| **Verifier** | Check outputs against specifications | Read-only, schema validation tools | Verification result |
| **Reviewer** | Present outputs to a human and collect approval | Notification tools, UI surface | Approval state |
| **Summariser** | Compress content for context efficiency | Read-only, internal only | None (stateless) |

### Handoff contracts

Every handoff between agent types must have an explicit contract:

```python
@dataclass
class HandoffContract:
    from_agent_type: str
    to_agent_type: str
    payload_schema: dict       # What is passed
    preconditions: list[str]   # What must be true before handoff
    postconditions: list[str]  # What must be true after receipt
    on_failure: str            # "retry" | "escalate" | "abort"
```

Do not handoff unverified outputs. The verifier agent type exists to sit between executor and orchestrator — use it.

---

## 10. The Agentic Harness Pattern

### What it is

A harness is the infrastructure wrapper around one or more agents that provides all of the above — registry access, permission enforcement, session persistence, state management, budget tracking, observability, and tool pool assembly — as a reusable, configurable layer separate from agent business logic.

### Why it matters

Without a harness, every team re-implements (or skips) these concerns independently. A shared harness makes the infrastructure consistent, governable, and improvable across all agent implementations.

### Minimal harness interface

```python
class AgentHarness:
    def __init__(
        self,
        registry: ToolRegistry,
        session_store: SessionStore,
        event_stream: EventStream,
        permission_engine: PermissionEngine,
        token_budget: TokenBudget,
    ): ...

    def run(
        self,
        session_id: str,
        agent_type: str,
        goal: str,
        initial_context: dict,
    ) -> SessionResult:
        session = self.session_store.resume_or_start(session_id)
        
        while not session.is_complete():
            tool_pool = self.assemble_tool_pool(session)
            context = self.build_context(session)
            self.budget.check_pre_turn(context, tool_pool)
            
            response = self.invoke_model(context, tool_pool)
            
            for tool_call in response.tool_calls:
                self.permission_engine.enforce(tool_call, session)
                result = self.execute_tool(tool_call)
                self.event_stream.emit(tool_call, result)
                session.record(tool_call, result)
                self.session_store.checkpoint(session)
            
            verification = self.verify(session.current_step_output)
            if not verification.passed:
                session.handle_failure(verification)
                
        return session.result()
```

### Harness configuration

A harness should be configurable per deployment context, not hardcoded:

```yaml
harness:
  session:
    store: postgres          # postgres | redis | s3
    checkpoint_on: [tool_call, step_complete]
    retention_days: 90
  
  permissions:
    default_mode: standard   # autonomous | standard | supervised
    elevated_requires: approval
    system_requires: explicit_approval
  
  budget:
    model_max_tokens: 200000
    output_reserve: 0.20
    tools_reserve: 0.15
    warning_threshold: 0.80
  
  observability:
    events: true
    log_destination: structured_json
    verification: strict     # strict | lenient | off
  
  tool_pool:
    max_tools_per_turn: 20
    compaction_strategy: priority_ranked
```

---

## 11. Modular Architecture Checklist

Use this checklist when reviewing a new or existing agent design. Every item should have a clear answer or a documented decision to defer.

### Tool registry
- [ ] Are all tools registered centrally with metadata, not defined inline?
- [ ] Does every tool have a declared side-effect profile?
- [ ] Are tool descriptions written from the model's perspective, including negative guidance?
- [ ] Are tools versioned with explicit consumer pinning?

### Permission and trust
- [ ] Is every tool assigned a trust tier?
- [ ] Is tier enforcement in the harness, not only the prompt?
- [ ] Are approval workflows in place for `elevated` and `system` tier tools?
- [ ] Are autonomous-mode sessions restricted to `public` and `standard` tier tools by default?

### Session persistence
- [ ] Is session state stored externally to the agent process?
- [ ] Are checkpoints written atomically after every side-effecting tool call?
- [ ] Is there a tested recovery path from mid-session failure?

### State architecture
- [ ] Is workflow state separate from conversation state?
- [ ] Is conversation history windowed, not unbounded?
- [ ] Is workflow state the ground truth, not the conversation?

### Token budget
- [ ] Is a token budget tracked across the session, not just per turn?
- [ ] Is a pre-turn check in place before every model invocation?
- [ ] Is context compaction logic implemented and tested?

### Observability
- [ ] Are all state transitions emitting structured events?
- [ ] Are all tool invocations logged with arguments hash and tier?
- [ ] Is there a post-execution verification layer?
- [ ] Are verification failures handled, not silently swallowed?

### Tool pool assembly
- [ ] Is the tool pool assembled per step, not sent as the full registry?
- [ ] Is there a compaction strategy for budget-constrained turns?
- [ ] Are tool schemas preserved intact during compaction?

### Agent types
- [ ] Does every agent have a declared type with defined responsibilities?
- [ ] Are handoff contracts explicit with preconditions and failure modes?
- [ ] Is there a verifier step between executor and orchestrator?

---

## 12. Guiding Principles Summary

These are the principles that should underpin all agentic system design decisions. Return to these when facing ambiguous architectural choices.

**1. Infrastructure before intelligence.** Build the plumbing first. A well-designed harness makes a mediocre model reliable. A poor harness makes a great model unpredictable.

**2. Explicit over implicit.** Trust tiers, side effects, session boundaries, state ownership — declare all of these explicitly in code and configuration, never leave them implied.

**3. Persistence is not optional.** Any agent task that takes more than one model turn must be recoverable. Design for failure, not the happy path.

**4. Separate what changes at different rates.** Workflow state, conversation state, tool definitions, and session configuration change for different reasons and at different cadences. Keep them separate.

**5. Budget is a first-class constraint.** Token limits are not an edge case. Pre-turn budget checks are as important as input validation on an API endpoint.

**6. Observe everything, assume nothing.** You cannot improve what you cannot measure. Every event, every tool call, every verification result is data you will need later.

**7. Curate, don't dump.** The model is not a search engine. Give it the right tools for the current step, not everything that might ever be relevant. Tool pool assembly is a design decision.

**8. Type your agents.** Untyped agents are monoliths. Named types with defined responsibilities create clear contracts, enable parallel development, and make failure attribution tractable.

**9. Enforce at the boundary.** Permissions enforced in prompts are suggestions. Permissions enforced in the harness are guarantees. Never rely solely on the model's compliance.

**10. Verify before you hand off.** Every step output should be verified before it is passed to the next agent or used as a tool argument. Garbage in, amplified garbage out.

---

*Last updated: April 2026. Raise questions, challenge assumptions, and propose revisions via the agent architecture review thread. This document should evolve with the systems we build.*