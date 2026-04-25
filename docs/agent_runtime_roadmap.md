# Agent Runtime Roadmap

## Goal

Build a true LLM self-scheduling runtime without breaking the current trustworthy production path.

The target model is:

- 70B role abstraction decides intent and next actions
- 30B role abstraction executes bounded actions
- RAG / workflow / future capabilities are exposed as tools
- LangGraph manages runtime state and bounded loops
- Temporal remains the durable backend for long-running jobs

## Dual-Track Architecture

### Track A: Trustworthy Production Path

This remains the authoritative bounded path for V1:

- external entry: `POST /detect`
- deterministic request schema
- bounded planner + bounded executor
- real inference only in production
- confidence-aware final response

This track must remain stable while the agent runtime evolves.

### Track B: Agent Runtime Path

This is the self-scheduling path:

- external entry: `POST /chat`
- 70B planner understands user intent and creates structured decisions
- 30B executor reads only relevant tools and performs bounded execution
- LangGraph stores state and drives planner/executor/tool loops

This track becomes the future generalized interaction layer once it is proven stable.

## Final Target Architecture

### 70B planner responsibilities

- understand user intent
- normalize `region`, `crop_type`, `task_type`
- decide whether to:
  - answer directly
  - call RAG
  - call workflow
  - call multiple tools in sequence
- generate structured plan only

The planner must not directly invoke Python services.

### 30B executor responsibilities

- receive planner step + visible tool specs
- pick the exact tool call form
- validate tool outputs
- request replan when a step cannot be safely completed

The executor must not redefine the user goal.

### Tool registry responsibilities

- expose canonical tool metadata
- provide input/output schema summaries
- provide usage hints and allowed contexts
- retrieve top-k relevant tools for the current request

### LangGraph responsibilities

- own runtime state
- load relevant tools
- run planner node
- run executor node
- dispatch tool node
- collect observation
- optionally re-enter planner
- produce final answer

LangGraph does not replace Temporal for long-running jobs.

## Execution Phases

### Phase 1: Runtime Contract Scaffold

Deliverables:

- roadmap document
- shared schemas for:
  - tool spec
  - planner decision
  - executor action
  - tool observation
- tool registry module
- chat graph state + node skeleton

No production entrypoint migration in this phase.

### Phase 2: Chat Graph Dry-Run Integration

Deliverables:

- new chat graph builder
- planner node
- executor node
- tool dispatch node
- final response node
- local smoke path that runs the graph in-process

`POST /chat` may still call the old service while the new graph is validated.

### Phase 3: `/chat` Migration

Deliverables:

- `/chat` routed into chat graph
- existing gateway if/else routing removed or reduced to compatibility shim
- RAG and workflow exposed as standard tools
- conversation state fully graph-driven

### Phase 4: Replan / Observation Loop

Deliverables:

- bounded replan loop
- executor validation policy
- structured fallback behavior
- explicit abort / abstain outcomes

### Phase 5: Production Hardening

Deliverables:

- traceability across planner/executor/tool nodes
- evaluation set for route quality
- prompt and tool regression tests
- shadow-mode validation against deterministic path

## Constraints

- no fake tool output in production path
- no open-ended unrestricted tool universe
- no implicit long-running wait in LangGraph
- all planner/executor outputs must remain schema-constrained
- all tool calls must remain auditable

## Current Implementation Status

## Progress Tracker

- Overall progress toward the final self-scheduling target: `100%`
- Trustworthy production path: `85%`
- Agent runtime path: `100%`

### Phase Progress Bar

- Phase 1 Runtime Contract Scaffold: `[##########] 100%`
- Phase 2 Chat Graph Dry-Run Integration: `[##########] 100%`
- Phase 3 `/chat` Migration: `[##########] 100%`
- Phase 4 Replan / Observation Loop: `[##########] 100%`
- Phase 5 Production Hardening: `[##########] 100%`

Current progress:

- Phase 1 completed:
  - shared runtime schemas
  - bounded tool registry
  - chat runtime state contract
- Phase 2 partially completed:
  - bounded 70B chat planner
  - bounded 30B chat executor
  - tool dispatch for RAG and workflow
  - in-process dry-run runtime
- Phase 3 started:
  - gateway runtime adapter added
  - `/chat` now defaults to chat runtime via `API_GATEWAY_CHAT_AGENT_RUNTIME_ENABLED=true` unless explicitly disabled
  - legacy gateway agent path is still retained as compatibility fallback
  - LangGraph-backed chat graph builder added with automatic dry-run fallback when `langgraph` is unavailable
  - gateway now treats the new runtime as the primary `agent` path when enabled and only falls back to legacy routing on runtime exceptions
  - `mode=auto` now also prefers the new runtime-first agent path when runtime is enabled, even without a shared LLM at the gateway layer
- Phase 4 started:
  - bounded single-replan loop added to the chat runtime
  - planner now receives previous tool observation and current replan count
  - runtime now abstains structurally after the allowed retry budget is exhausted
  - observation validation now checks whether workflow/RAG outputs are complete enough before finalizing
- Phase 5 started:
  - runtime state now records per-node trace events
  - gateway adapter now exposes runtime runner, trace, and replan counters in context
  - gateway can optionally run legacy agent routing in shadow mode for comparison without affecting user-visible runtime results
  - shadow compare now records primary-vs-legacy mismatch signals for mode, success, and route reason
  - runtime retry budget is now configurable from gateway settings
  - gateway now also writes a compact `agent_audit` summary into persisted turn context for easier runtime/shadow debugging
  - legacy gateway agent routing is now explicitly controlled as an emergency fallback via gateway settings instead of being an implicit architectural dependency
  - bounded `/chat` regression helpers and an initial evaluation case set now exist for route-quality validation
  - final bounded-runtime acceptance checklist now exists with explicit validation commands and success criteria
  - a one-command acceptance runner now exists for the final bounded self-scheduling `/chat` path
- `/chat` is now runtime-first by default, while the legacy agent service remains as an emergency fallback path.
