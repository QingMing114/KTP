# Claude Code Architecture Comparison

## Purpose

This note compares the public `collection-claude-code-source-code` / `claw-code` research repos with KTP, so we can decide what is worth borrowing and what should stay separate.

This is a **reference and architecture judgment** document, not an implementation plan.

## Short Answer

- Yes, KTP can **borrow ideas** from the Claude Code ecosystem.
- No, KTP should **not be rebuilt on top of** the leaked/archive repository directly.
- The public Claude Code-style projects are **not LangChain-first** systems.
- They look much more like a **custom agent runtime / harness**:
  - custom query loop
  - custom tool system
  - custom command system
  - custom permission model
  - custom bridge/plugin/skill/task subsystems

For KTP, the right move is:

- keep the current FastAPI + LangGraph + Temporal architecture
- selectively absorb the strong runtime patterns
- do **not** replace KTP's domain workflow backbone with a terminal-agent codebase

## What The Referenced Repos Appear To Be

From the public README / structure descriptions, the collection contains two different things:

1. `claude-code-source-code`
- a source archive / exploration artifact
- large TypeScript/Bun codebase
- terminal-first coding agent
- original code should be treated as research material, not a production dependency

2. `claw-code`
- a clean-room Python rewrite effort
- smaller, easier to study
- closer to an architecture reference than a drop-in platform

## Does It Use LangChain?

No clear sign that it is built on LangChain.

Public descriptions point to:

- Bun runtime
- TypeScript
- React + Ink terminal UI
- Commander.js CLI
- Zod schemas
- MCP / LSP integration
- a large custom `QueryEngine`
- a custom tool registry and command registry

That means the architecture is closer to:

- **self-built agent runtime**

not:

- LangChain agent stack
- LangGraph-first orchestration
- generic framework-managed tool loop

## High-Level Architecture Pattern

The Claude Code-style runtime looks roughly like this:

1. CLI / REPL entrypoint
2. Query engine
3. Tool registry and tool implementations
4. Command registry
5. Service integrations
6. IDE bridge
7. Permission checks
8. Plugins / skills / sub-agents / tasks / state

In other words, it is a **product runtime for an interactive coding agent**, not a business workflow platform.

## Module Comparison

| Claude Code-style area | What it does | Closest KTP area | Should KTP borrow it? |
|---|---|---|---|
| `main.tsx`, terminal UI, CLI parser | REPL / CLI / terminal rendering | FastAPI gateway + possible future admin CLI | Partial only |
| `QueryEngine` | central LLM/tool loop, streaming, retries | `apps/orchestrator/chat_graph/`, planner/executor runtime | Yes, strongly |
| `Tool.ts`, `tools.ts`, `src/tools/` | tool contracts + tool registry + per-tool execution | `services/tool_registry/`, `shared/schemas/agent_runtime.py` | Yes |
| `commands.ts`, `src/commands/` | slash commands / operator commands | future KTP ops/admin commands | Maybe |
| `src/services/` | integrations, token counting, compacting, auth, plugins | KTP `services/` and `infra/` | Yes, pattern only |
| `bridge/` | IDE integration | not core to KTP today | No, unless IDE integration becomes a goal |
| permission hooks | allow/deny before tool execution | KTP runtime policy / high-risk tool guard | Yes |
| `coordinator/`, teams, agents | sub-agent orchestration | future bounded executor/team tools | Maybe later |
| `skills/`, `plugins/` | reusable workflows / external extension | future KTP tool packs or domain plugins | Yes, later |
| persistent memory / tasks / remote sessions | long-lived interactive agent UX | conversation store, future session layer | Partial |

## What KTP Should Borrow

### 1. Stronger agent runtime loop

Worth borrowing conceptually:

- planner/executor/observation loop discipline
- clean runtime state transitions
- bounded retries
- explicit trace/audit

This fits directly into:

- `apps/orchestrator/chat_graph/`

### 2. Richer tool metadata

Worth borrowing:

- per-tool descriptions
- strict schemas
- usage rules
- permission hints
- discovery / retrieval of relevant tools only

This fits directly into:

- `services/tool_registry/`
- `shared/schemas/agent_runtime.py`

### 3. Permission and risk guard layer

Worth borrowing:

- pre-tool execution checks
- operator approval hooks for sensitive actions
- structured denials

For KTP this matters when tools can:

- trigger training
- register models
- call external services
- write artifacts

### 4. Better operator/developer ergonomics

Worth borrowing later:

- debug commands
- runtime introspection
- trace viewers
- tool inventory inspection

This should be added as **ops tooling**, not as the main product architecture.

## What KTP Should Not Borrow Directly

### 1. The repository as a base platform

Do not try to make KTP “inherit from” that codebase.

Why:

- wrong product shape
- different responsibilities
- terminal-agent assumptions
- legal / provenance risk around archived source materials
- would disrupt KTP's current bounded service architecture

### 2. Terminal-first assumptions

Claude Code is built around:

- local repo access
- terminal control
- editor bridges
- coding workflows

KTP is built around:

- domain workflows
- model registry
- inference/training/report/confidence services
- HTTP APIs
- long-running Temporal jobs

Those are different system centers.

### 3. “One giant query engine owns everything”

KTP should keep:

- business workflows in LangGraph
- long-running jobs in Temporal
- services behind adapters
- explicit schemas across boundaries

The runtime can become smarter, but it should not collapse the whole platform into one giant agent loop.

## Recommended Strategy For KTP

### Good strategy

Use the Claude Code-style projects as a **runtime design reference**:

1. strengthen chat/runtime loop design
2. improve tool registry richness
3. add permission/policy gates
4. improve auditability and operator tooling

### Bad strategy

Do not:

- fork it and build KTP directly on top
- import its leaked/archive code into KTP
- replace LangGraph/Temporal with a CLI agent loop

## Recommended Mapping Into KTP

If we borrow anything, it should land in these places:

- `apps/orchestrator/chat_graph/`
  - runtime loop ideas
  - observation handling
  - bounded planning/execution structure

- `services/tool_registry/`
  - richer tool catalog
  - tool capability discovery
  - policy metadata

- `shared/schemas/agent_runtime.py`
  - more expressive planner/executor/tool contracts

- `agents/core_70b/`
  - planner prompt/runtime refinement

- `agents/executor_30b/`
  - executor validation and recovery behavior

## Environment Guidance

The user mentioned `conda activate rsys`.

Recommended usage:

- use `rsys` to inspect or prototype against external research repos
- keep KTP runtime and regression execution in the KTP-controlled environment

Reason:

- avoids dependency conflicts
- prevents FastAPI / Pydantic / LangGraph / CLI runtime packages from drifting
- keeps KTP acceptance tests reproducible

For KTP itself, continue using the established project interpreter when running the platform and its tests.

## Final Recommendation

KTP should evolve like this:

- **keep** current architecture:
  - FastAPI
  - LangGraph
  - Temporal
  - planner/executor
  - toolized RAG/workflow

- **borrow** from Claude Code-style systems:
  - runtime quality
  - tool system depth
  - permission gating
  - traceability
  - operator ergonomics

- **avoid**:
  - direct codebase adoption
  - replacing domain workflows with a coding-agent shell

That gives us the upside of the architecture ideas without destabilizing KTP's production direction.
