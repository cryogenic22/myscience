# CTX + Harness: Market Zero's Unique Agent Architecture

*Date: 2026-04-01*

---

## The Thesis

Most AI agent systems have two problems:
1. **Context is unmanaged** — they stuff everything into the prompt and hope the model figures it out
2. **Infrastructure is implicit** — tool invocations, permissions, sessions, and state are ad hoc

Market Zero can solve both by combining **CTX** (a deterministic knowledge compiler) with a **structured Agent Harness** (infrastructure-first agent orchestration). This combination is unique — no existing pharma platform or data catalog has it.

---

## What CTX Brings (That Nobody Else Has)

### The Context Problem

Every LLM-powered system faces the same bottleneck: the context window. You have 200K tokens but the knowledge graph has 1.4M connections. What goes in? What stays out? How do you know the model saw the right data?

Current approach: stuff context and hope. Market Zero's current `CTXContextBuilder` uses L2 serialization to compress evidence. But CTX has 5 capabilities we're only using 5% of:

### CTX's Unique Capabilities

| Capability | What It Does | Why It Matters for Agents |
|-----------|-------------|--------------------------|
| **Hydrator** | Query-adaptive section retrieval. Pulls only relevant sections from a CTX document. O(1) lookup, ~3.9K tokens vs 92K stuffed | Agent tools get precisely the context they need per step, not everything |
| **EntityGraph** | Multi-hop BFS traversal and path finding from cross-references IN the context document | The agent can traverse the knowledge graph INSIDE its context without DB calls |
| **ContextGuard** | Detects hallucination by checking if model claims are grounded in the provided context | Post-execution verification (Module 8) with zero additional inference cost |
| **Grounding** | Sandwich prompt builder — TOP rules + context + BOTTOM verification checklist | Enforces grounding at the prompt level AND verification level |
| **AgentSession** | Token-budgeted conversation memory with automatic eviction | Module 5 (token budget) built into the context layer |
| **Packer Pipeline** | 6-stage compilation: Discovery → Parsing → Entity Resolution → Conflict Detection → Salience Scoring → Compression | Turns the entire knowledge graph into a compact, navigable, grounded context document |
| **14 Semantic Operators** | →, ¬, ★, ⚠, ≡, ⊥, ~>, >> etc. | Express relationships, contradictions, importance, warnings IN the context itself — the model understands these |

### Why This Is Different

Other systems (LangChain, CrewAI, AutoGen) have RAG — they retrieve chunks and stuff them into context. But:

- **RAG is dumb retrieval** — it finds similar text, not relevant structure
- **CTX is intelligent compilation** — it resolves entities, detects conflicts, scores salience, and compresses with semantic operators
- **RAG loses relationships** — chunks are flat text fragments
- **CTX preserves relationships** — the EntityGraph maintains cross-references inside the context

The combination: **CTX compiles the right context. The Harness executes the right tools. Together, the agent has the right information AND the right capabilities at every step.**

---

## What the Harness Brings

### The Infrastructure Layer

From the design principles document, the Harness provides:

1. **Tool Registry** — every agent action is a registered tool with metadata, side-effect profile, and trust tier
2. **Permission Engine** — trust tiers enforced at the execution boundary, not the prompt
3. **Session Persistence** — checkpoint-based recovery for long-running pipelines
4. **Token Budget Manager** — pre-turn checks with CTX-powered compaction
5. **Event Stream** — unified observability for all agent activity
6. **Verification Layer** — post-execution checks using CTX ContextGuard

### How They Combine

```
┌─────────────────────────────────────────────────────────────┐
│                    AGENT HARNESS                             │
│                                                              │
│  ┌──────────┐   ┌──────────────┐   ┌───────────────────┐   │
│  │  Tool     │   │  Permission  │   │  Session          │   │
│  │  Registry │   │  Engine      │   │  Persistence      │   │
│  └──────────┘   └──────────────┘   └───────────────────┘   │
│        │               │                    │               │
│        ▼               ▼                    ▼               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              CTX CONTEXT LAYER                       │   │
│  │                                                       │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │   │
│  │  │  Packer   │  │  Hydrator │  │  ContextGuard    │  │   │
│  │  │  Pipeline │  │  (query-  │  │  (hallucination  │  │   │
│  │  │  (compile │  │   adaptive│  │   detection +    │  │   │
│  │  │   KG →    │  │   section │  │   verification)  │  │   │
│  │  │   CTX)    │  │   fetch)  │  │                  │  │   │
│  │  └──────────┘  └──────────┘  └──────────────────┘  │   │
│  │                                                       │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │   │
│  │  │  Entity   │  │  Agent    │  │  Token Budget    │  │   │
│  │  │  Graph    │  │  Session  │  │  Manager         │  │   │
│  │  │  (in-ctx  │  │  (memory  │  │  (pre-turn       │  │   │
│  │  │   traversal│ │   with    │  │   compaction)    │  │   │
│  │  │          )│  │   eviction)│ │                  │  │   │
│  │  └──────────┘  └──────────┘  └──────────────────┘  │   │
│  └─────────────────────────────────────────────────────┘   │
│        │               │                    │               │
│        ▼               ▼                    ▼               │
│  ┌──────────┐   ┌──────────────┐   ┌───────────────────┐   │
│  │  Event    │   │  Verification│   │  Budget           │   │
│  │  Stream   │   │  (Guard +    │   │  Tracking         │   │
│  │           │   │   numbers)   │   │                   │   │
│  └──────────┘   └──────────────┘   └───────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### The Agent Turn Lifecycle (CTX + Harness)

```python
class MarketZeroHarness(AgentHarness):
    def execute_turn(self, session, step):
        # 1. ASSEMBLE — Harness selects tools for this step
        tool_pool = self.registry.get_by_step(step.type)
        
        # 2. COMPILE — CTX packs the knowledge graph into context
        ctx_doc = self.ctx_packer.pack(
            query=step.goal,
            entities=step.relevant_entities,
            budget=self.budget.available_for_context(),
        )
        
        # 3. HYDRATE — CTX pulls only the sections relevant to THIS step
        hydrated = self.ctx_hydrator.hydrate(ctx_doc, step.query)
        
        # 4. BUDGET — check we're within limits
        self.budget.check_pre_turn(hydrated, tool_pool)
        
        # 5. GROUND — CTX builds the grounding prompt
        prompt = self.ctx_grounding.build_prompt(
            system_rules=step.grounding_rules,
            context=hydrated,
            verification_checklist=step.verification_items,
        )
        
        # 6. INVOKE — call the model
        response = self.invoke_model(prompt, tool_pool)
        
        # 7. VERIFY — CTX ContextGuard checks for hallucination
        guard_result = self.ctx_guard.check(
            response=response,
            context=hydrated,
        )
        if not guard_result.passed:
            # Auto-rehydrate with additional context and retry
            rehydrated = self.ctx_hydrator.rehydrate(ctx_doc, guard_result.gaps)
            response = self.invoke_model(rehydrated_prompt, tool_pool)
        
        # 8. EXECUTE — run tool calls through permission engine
        for tool_call in response.tool_calls:
            self.permission_engine.enforce(tool_call, session)
            result = self.execute_tool(tool_call)
            self.event_stream.emit(tool_call, result)
            session.checkpoint()
        
        # 9. LOG — structured event with full provenance
        self.event_stream.emit(StepCompleted(
            session_id=session.id,
            step=step.id,
            guard_result=guard_result,
            tokens_used=response.usage,
        ))
```

---

## What Makes This Unique

### vs. LangChain/CrewAI
They have: tool calling + RAG + chains/crews
We have: **CTX-compiled context** (not chunks), **ContextGuard verification** (not hope), **structured harness** (not prompt-only)

### vs. Palantir Foundry
They have: data pipelines + governance + ontology
We have: **graph-native context** (EntityGraph in CTX), **LLM-native verification** (ContextGuard), **self-healing agents** (steward loop)

### vs. Causaly / BenchSci
They have: large pharma knowledge graphs + search
We have: **agent-driven curation** (steward enriches autonomously), **CTX-compressed traversal** (navigate the graph inside context), **multi-source provenance** (15 connectors with FAIR scoring)

### The Moat

The combination of CTX + Harness creates three capabilities nobody else has:

1. **Grounded Graph Intelligence** — the KG is compiled into context with relationship operators, not retrieved as flat chunks. The model sees structure, not text.

2. **Self-Verifying Agents** — ContextGuard checks every model output against the CTX context. Hallucinations are caught deterministically, not probabilistically.

3. **Budget-Aware Compilation** — CTX's packer pipeline respects token budgets natively. As context fills, sections are compressed or evicted by salience score, not randomly truncated.

---

## Implementation Roadmap

### Phase 1: Harness Foundation (Week 1-2)
- Tool Registry with all current tools formalized
- Permission Engine with trust tiers
- Session Persistence for background agent loop
- Event Stream for unified observability

### Phase 2: CTX Deep Integration (Week 3-4)
- Replace current `CTXContextBuilder` with full Packer Pipeline
- Wire Hydrator into chat handlers (query-adaptive context)
- Wire ContextGuard into verification layer (post-synthesis)
- Wire AgentSession into ConversationMemory

### Phase 3: Agent Harness (Week 5-6)
- `MarketZeroHarness` class wrapping the CTX + Harness lifecycle
- Agent type registry (DataSteward, ResearchAgent, QueryAgent, CurationAgent)
- Handoff contracts between agent types
- Verification gates between steps

### Phase 4: Governance (Week 7-8)
- Approval workflows for elevated-tier tools
- Full audit trail with immutable logging
- FAIR scoring integrated into agent decision-making
- Dashboard showing agent activity, budget usage, verification results

---

*The CTX + Harness architecture isn't just a technical choice — it's a product positioning. Market Zero doesn't just HAVE intelligence. It can PROVE its intelligence is grounded, verified, and governed. That's the difference between "AI-powered" and "AI-trustworthy."*
