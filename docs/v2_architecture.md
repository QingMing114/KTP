# V2 Architecture

## Goal

V2 evolves KTP from a single bounded remote-sensing system into a general multi-agent platform with:

- a reusable runtime core
- agent profiles
- bounded tool orchestration
- domain packs
- product-facing web UI
- API-first interaction

In the current delivery, the public gateway host can mount this V2 runtime in-process for the KTP single-agent experience. The recommended local split is:

- `8000` for the OpenAI-compatible shared model endpoint
- `18080` for the gateway/V2 product host

V2 is therefore both:

- the future platform baseline
- the current runtime behind the main KTP product entrypoints

## Principles

- clean-room implementation
- bounded agent behavior
- explicit schemas
- auditable tool execution
- product frontend as a first-class surface
- Python services remain the execution substrate for ML- and domain-heavy workloads

## Target Layers

### API Surface

- public host surface:
  - `POST /chat`
  - `POST /detect`
  - `GET /v2/ui`
  - `GET /chat/ui` as a redirect shim
- `/v2/sessions`
- `/v2/sessions/{session_id}`
- `/v2/sessions/{session_id}/state`
- `/v2/sessions/{session_id}/runs`
- `/v2/sessions/{session_id}/messages/stream`
- `/v2/runs`
- `/v2/runs/{run_id}`
- `/v2/runs/{run_id}/trace`
- `/v2/runs/{run_id}/state`
- `/v2/runs/{run_id}/replay`
- `/v2/tools`
- `/v2/agents`
- `/v2/domain-packs`

### Runtime

- session state
- run state
- planner / executor loop
- incremental run-event emission for planner/tool/artifact/assistant milestones
- tool dispatch
- bounded pack-flow execution
- observation validation
- bounded replan
- bounded delegation
- trace and audit

### Registries

- agent profile registry
- tool registry
- policy registry
- domain pack registry

### Domain Packs

- `ktp` becomes a pack, not the platform core
- a non-KTP demo/general pack is used to prove platform generality
- current status:
  - `demo` pack is the bounded local proof pack
  - `ktp` pack now includes:
    - `ktp.lookup_model_registry`
    - `ktp.run_inference_workflow`
    - `ktp.trigger_training`
    - `ktp.retrieve_knowledge`
    - `ktp.build_report`
    - `ktp.evaluate_confidence`
    - `ktp.build_visualization`
  - KTP pack execution now defaults to real bounded service calls and explicit failure when dependencies are unavailable
  - mock execution remains available only through explicit request context such as `use_mock=true`

### Frontend

- conversation-style shell with session rail, main message thread, and bottom composer
- chat/session detail
- product-style result view
- Claude-style live event feed in the main conversation thread
- artifact/result panels
- collapsed debug drawer for:
  - run timeline
  - tool invocation chain
  - agent decisions
  - trace visualization
  - replay inspection

## Current Runtime Status

The current V2 delivery has completed Phase 0/1/2, has a usable Phase 3 API surface, and now backs the main gateway/V2 product host. It already includes:

- repository skeleton
- V2 contracts and registries
- in-memory session/run store
- standalone V2 FastAPI API skeleton
- product web UI served under `/v2/ui`
- a clean-room bounded runtime core
  - deterministic planner
  - deterministic executor
  - model-backed direct-answer generation when a shared LLM provider is configured
  - bounded tool invocation
  - bounded KTP pack flow
  - bounded delegation
  - observation handling
  - bounded replan after non-KTP tool failure
  - traceable run lifecycle
- gateway bridge for:
  - unified `POST /chat`
  - unified `POST /detect`
  - unified `GatewayAgentResponse`

The current runtime is intentionally small and deterministic. It now proves both:

- the platform shape
- the first broader KTP domain-pack bridge through bounded model/inference/report/confidence/visualization adapters
- that a V1 host can be re-rooted onto the V2 runtime without local loopback HTTP

## Current Storage Model

V2 now supports two storage backends behind the same runtime-store contract:

- `memory`
  - default for quick local smoke work
- `sqlite`
  - first persistent backend for Phase 3
  - stores sessions and runs as structured JSON payloads
  - allows app restarts while preserving V2 session/run history

The API selects the backend through V2 API settings rather than embedding storage logic in route handlers.

## Read Surface And Public Host

V2 now exposes a usable read/query surface for frontend and operator tooling:

- list sessions
- fetch session detail
- fetch session state with latest run
- list runs belonging to one session
- stream one run turn as SSE events
- list runs across the whole V2 runtime
- fetch run detail
- fetch run trace
- fetch run state with visible tools/agents/policy
- deterministically replay a stored run without mutating persisted session/run state

The gateway host builds on top of this read surface and adds:

- `GET /v2/ui` as the main user-facing product page
- `/chat` and `/detect` responses that link back to:
  - session detail
  - run detail
  - trace
  - replay
  - UI deep links

Current replay behavior is intentionally bounded:

- replay is **deterministic dry replay**
- it re-executes the bounded runtime using:
  - the stored run input message
  - the stored `input_context`
  - the current deterministic planner/executor
  - the default policy
  - visible tools
  - visible agents
- it returns:
  - original run state
  - replayed run state
  - comparison summary
  - mismatch field names when replay diverges
- it does **not** append session messages or persist a new run
- current comparison now checks:
  - executor action parity
  - observation source/status/summary/payload parity
  - tool invocation sequence parity
  - artifact sequence parity
  - replan and delegation counters
  - trace length and trace sequence parity

## Phase 2 Boundaries

Current bounded runtime behavior supports five actions:

- direct answer
- tool invocation
- KTP pack flow
- delegation to a visible agent profile
- abstain / safe stop

Current demo scope:

- `demo.pack_answer` proves pack-backed tool execution
- `demo.fail` proves bounded replan and safe fallback
- `reviewer` proves bounded delegation plumbing
- `ktp` proves that an existing vertical system can be re-expressed as a pack rather than as the runtime core
- `/chat` and `/detect` prove that a legacy public host can be bridged into V2 without preserving the old orchestrator/chat main path

Still intentionally deferred:

- richer tool risk metadata and permission policy
- reviewer hints/rewrite loops
- specialist delegation chains
- broader pack renderer contracts
- full non-KTP second-pack acceptance
