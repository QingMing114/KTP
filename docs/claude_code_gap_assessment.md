# Claude Code Gap Assessment

## Purpose

This document records the **current** gap between `ktp_product` and a Claude Code-style backend runtime.

It is not asking whether KTP should copy Claude Code product surfaces one-for-one.  
It answers a narrower and more useful question:

- how close are we to the **runtime shape**
- what is already complete
- what is still missing
- what should happen next

This document should be read together with:

- [claude_code_architecture_comparison.md](/home/D/liumeng/ktp_product/docs/claude_code_architecture_comparison.md)
- [multi_agent_single_entry.md](/home/D/liumeng/ktp_product/docs/multi_agent_single_entry.md)
- [canonical_product_protocol.md](/home/D/liumeng/ktp_product/docs/canonical_product_protocol.md)
- [frontend_integration_standard.md](/home/D/liumeng/ktp_product/docs/frontend_integration_standard.md)

## Executive Summary

### Current judgment

Estimated completion against our own target:

- backend target completion: **85% - 90%**
- Claude Code-style backend runtime similarity: **70% - 75%**
- Claude Code full product similarity: **45% - 55%**

### Why this is the current judgment

The backend now already has:

- one public entry surface
- one composition root
- one model-driven query engine
- internal specialist delegation
- explicit tool registry
- compatibility adapters at the edge
- canonical product protocol
- async submission model for large jobs
- dataset-backed task flow

This means the hard architectural part is mostly in place.

What is **not** in place yet is mainly:

- governance and approval
- public extension ecosystem
- broader third-party file semantics
- richer operator tooling
- Claude Code-specific CLI and IDE surfaces

## Areas Where We Are Already Close

### 1. Single public entry, internal specialization

Status: **close**

Implemented:

- one public entry agent: `ktp_frontdesk`
- backend-internal specialists:
  - `ktp_analysis_specialist`
  - `ktp_knowledge_specialist`
  - `ktp_training_specialist`
  - `ktp_workspace_specialist`
- frontend remains single-entry

Why this matters:

- matches the Claude-style “single public agent, internal specialization” shape
- keeps frontend simple
- lets backend evolve without multiplying frontend models

### 2. Query engine as the product core

Status: **close**

Implemented:

- model-driven query loop
- bounded execution budget
- specialist delegation
- tool execution loop
- replay and run-state support
- trace and tool invocation history

Main files:

- `ktp_backend/query_engine/loop.py`
- `ktp_backend/query_engine/scheduler.py`
- `ktp_backend/query_engine/executor.py`
- `ktp_backend/query_engine/state.py`

Why this matters:

- this is the closest architectural analogue to the Claude Code QueryEngine
- transport no longer owns execution semantics

### 3. Tool registry and bounded tool visibility

Status: **close**

Implemented:

- canonical tool registry
- tool metadata
- owned tools by internal specialist
- public vs internal tool visibility
- dangerous tool modeling

Why this matters:

- Claude Code-style systems are not just “LLM + prompt”; they are tool-runtime products
- we now have the same core boundary

### 4. Transport adapters at the edge

Status: **close**

Implemented:

- `/api/product/v1` as the canonical protocol
- `/v2/*` as product/debug adapter
- `/v1/chat/completions` as OpenAI-compatible adapter

Why this matters:

- frontend, LibreChat, and backend no longer need to share one accidental payload shape
- this is a major maturity step

### 5. Large file / long task handling

Status: **good enough for current stage**

Implemented:

- dataset registration
- dataset defaults
- async submissions
- submission polling
- SSE events
- artifact resources

Why this matters:

- large TIFF workflow is now a product concept, not an ad hoc prompt trick
- this is more mature than a pure chat UI integration

## Main Gaps

## 1. Governance and approval

Status: **partial**

Implemented:

- dangerous tools are modeled
- blocked / approval-required states exist
- canonical protocol has clear error envelopes

Missing:

- real approval workflow
- approver identity and approval records
- audit trail
- multi-user auth
- RBAC / tenant boundaries
- policy administration UX

Impact:

- current system is usable in single-user or controlled internal mode
- not yet a governed multi-user production platform

Priority: **high**

## 2. Public extension and plugin surface

Status: **partial**

Implemented:

- internal tool registry
- internal pack registry
- internal specialist model

Missing:

- public extension SDK
- stable plugin contract
- MCP-grade extension lifecycle
- install/enable/disable/versioning model
- third-party tool sandbox model

Impact:

- backend is extensible by internal engineers
- not yet extensible as a platform

Priority: **high**

## 3. OpenAI-compatible and third-party frontend parity

Status: **good, but not complete**

Implemented:

- `/v1/models`
- `/v1/chat/completions`
- dataset-backed OpenAI-compatible flow
- LibreChat compatibility path
- artifact-aware output

Missing or partial:

- broader third-party file semantics
- richer attachment modes
- object storage ingestion semantics
- more generic third-party frontend expectations

Impact:

- LibreChat works as an integration path
- broader ecosystem compatibility still needs hardening

Priority: **medium-high**

## 4. Operator and observability tooling

Status: **partial**

Implemented:

- run detail
- trace
- replay
- debug extension
- artifact pages

Missing:

- operator dashboard
- run search/filtering
- approval inbox
- policy inspection UI
- system health / queue visibility
- governance reporting

Impact:

- engineering can debug
- operators do not yet have a strong management surface

Priority: **medium**

## 5. Claude Code-specific product surfaces

Status: **intentionally not built**

Missing:

- CLI-first shell
- slash commands
- IDE bridge
- terminal UI
- local repo coding workflow

Decision:

- this is intentional
- these surfaces should not be copied unless they directly improve the KTP product

Impact:

- we are not trying to become a Claude Code clone
- this gap is real, but not necessarily a product problem

Priority: **low unless product direction changes**

## 6. Deeper runtime hardening

Status: **good foundation, not finished**

Implemented:

- bounded loop
- internal delegation
- dataset-backed async runs
- canonical protocol
- replay

Missing:

- stronger persistence model for all runtime state
- more advanced cancellation semantics
- queue isolation / resource controls
- better retry classification
- stronger resumability for interrupted long jobs
- higher confidence distributed execution story

Impact:

- current runtime is strong enough for product iteration
- still needs hardening before claiming backend maturity is “done”

Priority: **medium-high**

## What Has Changed Recently

Compared to earlier gap assessments, these major gaps have already been reduced:

- canonical product protocol now exists
- `/v2` is no longer the only practical contract
- dataset-backed async flow is established
- backend single-entry / multi-specialist architecture is implemented
- QueryEngine is now the actual core execution shape

That means the project is no longer in “architecture exploration” mode.  
It is now in “protocol hardening and productization” mode.

## Recommended Development Direction

The right path is **not**:

- copy Claude Code feature-for-feature
- rebuild around a terminal shell
- replace domain workflows with a coding-agent product surface

The right path is:

1. keep the current backend runtime direction
2. finish protocol and frontend alignment
3. harden adapters and artifact UX
4. add approval/governance
5. add extension seams
6. only then decide whether any CLI or IDE surface is worth adding

## Recommended Roadmap

## Phase 1: Protocol-first frontend alignment

Goal:

- make `/api/product/v1` the real frontend contract

Deliver:

- first-party frontend uses canonical protocol
- `/v2` becomes adapter/debug shell, not source of truth
- artifact rendering uses artifact resources only
- frontend state model aligns to:
  - `Manifest`
  - `Dataset`
  - `Conversation`
  - `Submission`
  - `Run`
  - `Artifact`

Exit criteria:

- frontend no longer depends on `/v2`-specific payload quirks

Priority: **immediate**

## Phase 2: Product hardening

Goal:

- make the backend operationally strong enough for daily product use

Deliver:

- stronger queue / cancellation semantics
- better long-job lifecycle handling
- better dataset lifecycle management
- stronger artifact UX
- improved third-party frontend compatibility

Exit criteria:

- long-running workflows are boring and predictable

Priority: **immediate**

## Phase 3: Governance and approvals

Goal:

- move beyond single-user trusted mode

Deliver:

- approval workflow
- approver audit trail
- operator UI
- RBAC foundations
- policy visibility

Exit criteria:

- dangerous actions are governed, not just modeled

Priority: **high**

## Phase 4: Extension surface

Goal:

- make the system extensible without core code edits

Deliver:

- public extension contract
- plugin lifecycle
- bounded external tool model
- versioned extension metadata

Exit criteria:

- new capabilities can be added through extension seams instead of backend surgery

Priority: **high**

## Phase 5: Optional developer surfaces

Goal:

- evaluate whether a CLI or IDE bridge actually adds value

Possible deliverables:

- admin CLI
- operator slash commands
- IDE-assisted review/debug bridge

Decision rule:

- only build these if they improve KTP operator productivity
- do not build them just to resemble Claude Code

Priority: **later**

## Bottom Line

The backend is no longer far from the target architecture.

The remaining gap is no longer “do we have the right core runtime shape?”

The remaining gap is:

- governance
- extension surface
- operator tooling
- adapter hardening
- product UX around the canonical protocol

That is a much better place to be.

If we stay disciplined and keep `/api/product/v1` as the stable center, backend and frontend can now evolve independently without re-arguing the core architecture every week.
