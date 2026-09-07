# System Manual

## Overview

This repository implements a staged multi-agent system with explicit module boundaries. The current codebase now exposes a real public KTP single-agent product through the V1 gateway host, while using the V2 runtime as the internal execution core.

Recommended local host split:

- `8000` for the OpenAI-compatible shared model service
- `18080` for the gateway and V2 UI

The repository currently includes runnable foundations for:

- API gateway
- LangGraph orchestrator
- shared planner/executor local LLM integration
- model registry
- Temporal-based training workflow skeleton
- inference service, including the migrated baldness RF pipeline
- RAG service with FAISS-based local retrieval
- report service with Jinja2 HTML rendering
- confidence service with structured heuristic fusion
- visualization service with self-contained workflow dashboards
- agent-runtime scaffolding for future LLM self-scheduling chat
- V2 platform runtime for a Claude-style general agent system

## Module Guide

### `v2/`

- Holds the new V2 platform runtime.
- V2 is still the future general multi-agent platform baseline, but it is no longer only a parallel demo track.
- The current public gateway host mounts the V2 runtime and V2 product UI directly.
- Current V2 scope includes:
  - installable FastAPI `/v2/*` surface
  - product-facing KTP web UI
  - shared schemas/settings/logging
  - bounded runtime store/engine
  - tool/agent/policy/pack registries
  - smoke tests
- V2 now backs the public gateway `POST /chat` and `POST /detect` paths through an in-process bridge.

### `v2/apps/api/`

- Provides the V2 FastAPI surface and install hook.
- Exposes:
  - `GET /health`
  - `GET /v2/sessions`
  - `POST /v2/sessions`
  - `GET /v2/sessions/{session_id}`
  - `GET /v2/sessions/{session_id}/state`
  - `GET /v2/sessions/{session_id}/runs`
  - `POST /v2/sessions/{session_id}/messages`
  - `GET /v2/runs`
  - `GET /v2/runs/{run_id}`
  - `GET /v2/runs/{run_id}/trace`
  - `GET /v2/runs/{run_id}/state`
  - `POST /v2/runs/{run_id}/replay`
  - `GET /v2/tools`
  - `GET /v2/agents`
  - `GET /v2/domain-packs`
- Can run as a standalone V2 app or be installed directly into the V1 gateway via `install_v2_api(...)`.
- Uses an in-memory runtime store plus a bounded runtime engine so V2 can be exercised independently or through the main gateway host.
- The runtime store backend is configurable:
  - `memory` for smoke work
  - `sqlite` for local persistence across app restarts
- Keeps route handlers thin and delegates state changes to runtime/store components.
- `POST /v2/sessions/{session_id}/messages` now accepts `SendMessageRequest.context`, which carries `RequestContextV2`.
- The read-side API is now sufficient for:
  - session list pages
  - session detail pages
  - run list/detail pages
  - trace viewers
  - deterministic dry replay inspection
- Local run command:
  - `python -m uvicorn v2.apps.api.main:app --host 0.0.0.0 --port 18180`
- Main product host command:
  - `python -m uvicorn apps.api_gateway.main:app --host 0.0.0.0 --port 18080`

### `v2/apps/web/`

- Provides the current product-facing KTP single-agent UI.
- The gateway serves this UI at `GET /v2/ui` and mounts checked-in assets under `/v2/ui/dist`.
- Current UI capabilities include:
  - session creation and switching
  - message sending with KTP-oriented prompts
  - Claude-style activity guidance in the main pane, including "what it is doing now" and "what comes next" summaries during and after each run
  - current result panel
  - artifact viewer
  - run selection
  - collapsed debug drawer for planner/tool/trace/replay inspection
  - registry inventory panel
- The UI now defaults to same-origin API calls when hosted by the gateway. When served from port `4173`, it defaults to `http://127.0.0.1:18180`.
- `dist/` includes checked-in browser-ready files so the product page can run without a local Node toolchain.
- Local static demo run:
  - `cd frontend && python -m http.server 4173`
- Optional TypeScript rebuild when Node tooling exists:
  - `cd frontend && npm install && npm run build`

### `v2/runtime/`

- Provides the clean-room bounded runtime core for V2.
- `store.py` defines the runtime-store contract and the in-memory implementation.
- `sqlite_store.py` provides the first persistent runtime store using SQLite.
- `factory.py` selects the store backend from API settings.
- `store.py` also provides:
  - session listing
  - global run listing
  - run listing per session
- `planner.py` provides the deterministic Phase 2 planner.
- `executor.py` provides the deterministic Phase 2 executor.
- `engine.py` provides the bounded loop:
  - planner decision
  - executor action build
  - policy-guard validation
  - tool invocation
  - bounded KTP pack-flow execution
  - bounded replan
  - bounded delegation
  - final traceable run synthesis
- Current runtime actions:
  - direct answer
  - tool invocation
  - pack flow
  - delegation
  - abstain
- Direct-answer runs now prefer the configured shared LLM provider when one is available on the host.
- If no shared LLM is configured, or the provider fails, the runtime falls back to the bounded deterministic direct-answer message.
- `RunDetail` now also stores `input_context`, which preserves the normalized `RequestContextV2` used for one run.
- The KTP pack flow is a bounded multi-step execution chain:
  1. `ktp.lookup_model_registry`
  2. `ktp.run_inference_workflow`
  3. optional `ktp.retrieve_knowledge`
  4. `ktp.build_report`
  5. `ktp.evaluate_confidence`
  6. optional `ktp.build_visualization`
- Each KTP flow step is written into `tool_invocations` and `trace`.
- Real KTP analysis requires `image_path` unless the caller explicitly enables mock execution.
- When `image_path` is missing on a real analysis request, the planner now abstains early with user guidance instead of failing later inside inference.
- The planner can also auto-extract a local image path when it appears directly in the user message.
- KTP pack-flow failures are fail-fast:
  - the run ends as `failed`
  - the error is written into the observation payload and trace
  - the runtime does not silently fall back to mock execution
- Current replay support is deterministic dry replay:
  - re-executes the bounded runtime for the stored input
  - reuses the stored input message plus the stored `input_context`
  - compares original vs replayed outputs
  - compares executor action, observation details, tool/artifact sequence, counters, and trace sequence
  - returns mismatch field names when replay diverges
  - does not persist a new run
  - does not append session messages

### `v2/agents/`

- Provides the initial V2 agent profile registry.
- Current default profiles include:
  - `planner_70b`
  - `executor_30b`
  - `reviewer`

### `v2/tools/`

- Provides the initial V2 tool registry.
- Current default bounded demo tools include:
  - `direct_answer`
  - `demo.pack_answer`
  - `demo.fail`
- Current KTP pack tools include:
  - `ktp.lookup_model_registry`
  - `ktp.run_inference_workflow`
  - `ktp.trigger_training`
  - `ktp.retrieve_knowledge`
  - `ktp.build_report`
  - `ktp.evaluate_confidence`
  - `ktp.build_visualization`
- `handlers.py` contains the clean-room demo tool implementations used by Phase 2 smoke tests.
- `handlers.py` now also includes composite KTP-facing tool handlers, which turn KTP Python-service outputs into V2 observations and pack artifacts.
- KTP tool handlers no longer do automatic mock fallback. Mock execution remains available only through explicit `use_mock_backend=true` / `use_mock=true` request context.

### `v2/policies/`

- Provides the initial V2 policy registry.
- The default policy currently defines bounded replan and delegation budgets.
- `guard.py` enforces:
  - replan budget
  - delegation budget
  - visible-tool checks
  - visible-agent checks

### `v2/packs/`

- Provides the initial V2 domain-pack registry.
- Current default pack list includes:
  - `demo` pack, marked ready, exposing `demo.pack_answer` and `demo.fail`
  - `ktp` pack, marked partial, exposing model lookup, inference, training, retrieval, report, confidence, and visualization tools

### `v2/adapters/python_services/`

- Bridges V2 runtime tools into existing Python service implementations.
- `ktp_rag.py` is the first real adapter in this layer.
- It wraps the existing KTP local RAG client and lets V2 invoke bounded KTP knowledge retrieval through the pack/tool contract.
- When full RAG dependencies are unavailable, the default adapter now raises an explicit bounded error instead of silently degrading to fallback knowledge.
- `ktp_services.py` now adds the first broader KTP pack-service bundle:
  - model lookup
  - inference
  - training
  - report
  - confidence
  - visualization
- This adapter bundle prefers real local Python services and now fails explicitly when real dependencies are unavailable.
- Explicit mock execution is still supported for tests or development when the caller passes `use_mock_backend=true`.

### `v2/shared/`

- Holds V2-specific shared primitives.
- `schemas.py` defines initial V2 contracts for:
  - sessions
  - runs
  - trace events
  - agents
  - tools
  - policies
  - packs
  - planner decisions
  - executor actions
  - observations
  - delegation results
  - tool invocation views
  - pack artifact views
  - session state views
  - run state views
  - replay response views

### `docs/v1/`

- Holds V1 freeze-oriented snapshot notes so V1 can be reviewed independently while V2 evolves.
- The initial snapshot entry is `docs/v1/README.md`.

### `docs/ktp_pack.md`

- Documents the current V2 KTP domain-pack surface.
- Covers tool list, adapter strategy, inputs/outputs, run commands, tests, and current limits.

### `apps/api_gateway/`

- Provides the external FastAPI gateway.
- Exposes `/`, `/health`, `POST /chat`, `POST /detect`, `GET /v2/ui`, all `/v2/*` runtime routes, `GET /workflow/{request_id}`, `GET /workflow/{request_id}/visualization`, `GET /workflow/{request_id}/report`, and `GET /services/health`.
- Installs the V2 API directly in-process, so the gateway host reuses the same runtime store, runtime engine, and registries as the V2 app.
- Mounts the checked-in V2 web assets and serves the main product UI at `/v2/ui`.
- `GET /chat/ui` is now a redirect shim to `/v2/ui`.
- `POST /chat` and `POST /detect` both use `GatewayAgentService`, which bridges directly into the V2 runtime instead of the legacy chat/orchestrator main paths.
- For generic non-tool chat, the gateway-hosted V2 runtime now uses the configured shared LLM provider for direct-answer responses when available.
- `POST /chat` and `POST /detect` both return the unified `GatewayAgentResponse` shape:
  - `request_id`
  - `conversation_id`
  - `session_id`
  - `run_id`
  - `status`
  - `answer`
  - `artifacts`
  - `sources`
  - `tool_invocations`
  - `workflow`
  - `debug`
- `/chat` uses `conversation_id` as the V2 `session_id` and reuses that session for follow-up turns.
- `/detect` creates a fresh V2 session for each request.
- The gateway bridge merges prior run context into follow-up `/chat` turns so `region`, `crop_type`, `task_type`, `image_path`, `use_mock`, and `extra_params` can carry forward when omitted.
- Legacy `ChatService`, chat graph, and orchestrator-driven detect logic remain in the repository as transition-era code, but they are no longer the primary public execution path.

### `apps/orchestrator/`

- Defines the LangGraph main workflow.
- `graph/` contains the workflow state and node functions.
- `config.py` stores orchestrator-local runtime settings.
- `clients/` provides one client wrapper per internal service boundary.
- `service_registry.py` wires the orchestrator to model registry, training, inference, RAG, report, confidence, and visualization clients.
- `service_registry.py` also selects the orchestrator training backend, either mock or Temporal.
- `main.py` exposes `run_workflow_request()` for local runs and tests.

### `apps/orchestrator/chat_graph/`

- Holds the bounded self-scheduling chat runtime that is evolving separately from the production `/detect` workflow.
- `states.py` defines the runtime state contract for planner / executor / tool observations.
- `states.py` also carries bounded loop controls such as `replan_count` and `max_replans`.
- `states.py` now also carries `runtime_trace`, which records node-level execution breadcrumbs for debugging and audit.
- `nodes.py` now provides:
  - bounded tool loading
  - 70B planner node
  - 30B executor node
  - bounded tool dispatch for RAG and workflow
  - tool observation validation
  - final response synthesis
- `service_registry.py` wires the chat runtime to the planner/executor roles plus local RAG/orchestrator clients.
- `workflow.py` provides a LangGraph-backed builder with conditional routing and lazy dependency loading.
- `runtime.py` provides an in-process dry-run loop with a bounded single replan attempt so the planner -> executor -> tool -> observation -> planner/finalize path can be validated before `/chat` is migrated to the new graph.
- The runtime now validates tool outputs before finalization; incomplete workflow artifacts (for example missing requested report/confidence payloads) are treated as bounded failures and can trigger one replan attempt.
- `chat_runtime_adapter.py` maps runtime outcomes into gateway semantics, including explicit `abstain` results and runtime-runner tracing.
- Gateway-facing runtime context now includes:
  - `runtime_runner`
  - `runtime_trace`
  - `replan_count`
  - `max_replans`
  - optional `shadow_compare` result when shadow mode is enabled
- This package is not yet the live `/chat` execution path; it is the migration target for later phases.

### `apps/api_gateway/services/chat_runtime_adapter.py`

- Adapts the bounded chat runtime to gateway response semantics.
- Converts runtime state into:
  - gateway `ChatResponse`
  - persisted conversation turn context
- Lets `/chat` be migrated behind a feature flag instead of a hard switch.

### `agents/core_70b/`

- Holds the planner role facade.
- Uses the shared `infra/llm` provider when enabled.
- Falls back to the heuristic planner if the shared model runtime is unavailable or returns invalid structured output.
- Does not execute business actions directly.
- `chat_planner.py` adds the bounded chat planner used by the future self-scheduling runtime:
  - 70B role decides direct answer vs. tool sequence vs. abstain
  - extracts normalized `region`, `crop_type`, and `task_type`
  - emits structured `PlannerDecision` and ordered `PlannerStep` objects

### `agents/executor_30b/`

- Receives structured tasks from graph nodes.
- Dispatches those tasks to service adapters through `tool_executor.py`.
- Can use the shared `infra/llm` provider to rewrite the final executor message while keeping deterministic tool execution authoritative.
- Currently uses the real local inference adapter, a configurable training adapter, the real local RAG adapter, the real local report adapter, and the real local confidence adapter.
- Also uses the real local visualization adapter to render a dashboard after the main outputs are ready.
- `chat_executor.py` adds the bounded chat executor used by the future self-scheduling runtime:
  - 30B role receives one planner step plus bounded tool metadata
  - returns structured `ExecutorAction`
  - may request replan, return direct answer, or invoke one bounded tool

### `infra/llm/`

- Provides the shared local-model integration boundary for planner and executor.
- `config.py` stores the shared LLM runtime configuration.
- `provider.py` manages the cached provider and the persistent subprocess worker.
- `worker.py` is the external runtime entrypoint that loads `Qwen3-VL-30B-A3B-Instruct` once and serves structured generations over stdin/stdout.
- The same shared local model can back both the planner's "70B role abstraction" and the executor's "30B role abstraction"; the role split is logical, not tied to two different physical checkpoints.
- The provider now sends a compact field-contract prompt instead of a full Pydantic JSON schema and enforces a response timeout, so the shared 30B path degrades back to deterministic logic instead of hanging the workflow.
- The worker now performs a startup handshake and can fail fast when no supported accelerator is available; this avoids waiting through request timeouts on CPU-only runtimes.
- The shared worker can now be pinned to specific GPUs through `AGENT_LLM_CUDA_VISIBLE_DEVICES`, or set to `auto:<count>` for runtime GPU selection; the local workspace default is dynamic `auto:2`.
- This keeps heavy model runtime dependencies out of the main project environment.

### `services/model_registry/`

- Implements model registration, lookup, status updates, and listing.
- Uses SQLAlchemy for persistence.
- Supports PostgreSQL and SQLite.
- `local_client.py` lets the orchestrator and inference service read the same registry database without starting a separate HTTP server.
- `metrics_json` can carry model-specific metadata such as `prediction_class_semantics`, so future classifiers do not require hard-coded class rules in the inference layer.

### `services/training_service/`

- Provides the Temporal workflow skeleton for data preparation, training, evaluation, and model registration.
- Includes the client, worker, workflows, and activities needed for future durable training execution.
- `local_client.py` is the synchronous wrapper used by the orchestrator when `ORCHESTRATOR_TRAINING_BACKEND=temporal`.
- In the current MVP, the orchestrator can start a real Temporal workflow request when a server and worker are available, or stay on mock training for lightweight runs.

### `services/inference_service/`

- Provides the bounded inference pipeline: model lookup, model loading, preprocessing, prediction, and postprocessing.
- `client.py` is the sync wrapper used by the orchestrator.
- `adapters/local_model_registry_client.py` lets the service resolve registry records locally.
- For multi-class predictors, postprocessing now reads `prediction_class_semantics` from request params, model metadata, or optional config, then derives the target mask from `target_classes`.
- When a predictor returns a multi-class raster without class semantics, inference fails explicitly instead of silently collapsing `class > 0` into a false binary result.
- Supports two execution modes:
  - mock predictor path for local smoke runs
  - real `baldness_rf` path for migrated RF inference

### `services/rag_service/`

- Provides knowledge document ingestion and retrieval.
- Stores chunk metadata in local JSON and vectors in FAISS.
- Supports deterministic mock embeddings by default for local development.
- `client.py` is the local adapter currently used by the orchestrator.
- The V2 KTP runtime uses the same local adapter for knowledge-oriented requests and optional pack-flow enrichment.

### `services/report_service/`

- Renders structured workflow outputs into HTML reports.
- Persists reports to local disk.
- Uses Jinja2 templates and a dedicated builder layer.
- Generated local HTML reports now default to Chinese presentation text, while structured request/response payload keys remain unchanged.
- When inference artifacts are available, it now performs a local mask sanity inspection and surfaces warnings such as near-total positive coverage directly in the HTML summary and inference section.

### `services/confidence_service/`

- Computes image, text, and workflow confidence.
- Produces a fused confidence score, label, and explanation.
- `client.py` is the local adapter currently used by the orchestrator.
- The image-confidence branch now inspects the generated `mask_uri` and lowers confidence for degenerate outputs such as full-image positive masks.

### `services/visualization_service/`

- Renders one HTML dashboard per workflow run.
- Generated workflow dashboards now default to Chinese presentation text, while JSON snapshots and service schemas remain unchanged.
- Builds preview images for:
  - input image
  - raw class map
  - derived target mask
  - confidence map
- Surfaces workflow `stage_timings` so operators can see how long each LangGraph node took.
- Displays model metadata from the registry lookup, including status, description, and scalar metrics.
- Builds a class legend from inference `class_labels` and `class_distribution` instead of hard-coding task-specific categories.
- Embeds the generated report HTML directly into the dashboard so operators can compare the workflow summary and the final report in one page.
- Persists the dashboard plus a JSON workflow snapshot under `VISUALIZATION_OUTPUT_DIR/<request_id>/`.
- Embeds preview images directly into the HTML so the page stays portable when opened through the gateway route.
- The orchestrator generates this dashboard automatically at the end of each completed workflow unless `extra_params.enable_visualization=false`.

### `ml/baldness_rf/`

- Contains the migrated baldness RF algorithm core.
- `feature_extractor.py` extracts features from multiband imagery.
- `classifier.py` loads and runs the RF model.
- `pipeline.py` orchestrates the real prediction flow and writes raster outputs.
- `diagnostics.py` provides a bounded inspection path that summarizes raw bands, extracted features, model class structure, predicted class distribution, and preview PNGs for future visualization tooling.

### `shared/`

- Centralizes settings, logging, schemas, and sync/async utility helpers.
- Keeps reusable cross-service code out of route handlers and workflow nodes.
- `inference_sanity.py` provides reusable local artifact inspection so report and confidence can evaluate the same mask warnings consistently.
- `request_normalization.py` centralizes region / crop / task normalization and text extraction so gateway agent and planner use the same canonical registry keys.
- `schemas/agent_runtime.py` defines the shared runtime contracts for:
  - `ToolSpec`
  - `PlannerDecision`
  - `PlannerStep`
  - `ExecutorAction`
  - `ToolObservation`
- `chat_runtime_eval.py` defines reusable regression-case loading and response-evaluation helpers for the bounded `/chat` self-scheduling path.

### `services/tool_registry/`

- Provides the bounded tool catalog for the future self-scheduling runtime.
- Exposes:
  - full tool listing
  - single tool lookup
  - top-k relevant tool retrieval
- Current core runtime tools are:
  - `direct_answer`
  - `rag_search`
  - `run_remote_sensing_workflow`
- This registry is designed so the 70B planner and 30B executor can discover only a bounded relevant tool subset instead of seeing the entire tool universe.

### `scripts/`

- `check_agent_llm_runtime.py` probes the shared Qwen runtime and prints structured readiness info.
- `evaluate_chat_runtime.py` runs a bounded regression case file against `/chat`, either through an in-process FastAPI app or an external base URL, and prints a JSON summary of pass/fail results.
- `run_agent_runtime_acceptance.py` is the final acceptance runner; it chains the bounded pytest regression suite and the in-process `/chat` evaluation script.

### `tests/data/`

- `chat_runtime_eval_cases.json` is the seed evaluation set for `/chat` runtime route-quality regression.
- `chat_runtime_eval_cases_full.json` is the broader regression set covering direct-answer, RAG, workflow, normalization, and explicit compatibility paths.

### `docs/`

- `agent_runtime_acceptance.md` is the final acceptance checklist for the bounded self-scheduling `/chat` runtime, including gateway flags, regression commands, live checks, and acceptance criteria.
- `claude_code_architecture_comparison.md` compares the public Claude Code-style research repositories with KTP, explains that they are custom agent runtimes rather than LangChain-first systems, and documents what KTP should borrow versus avoid.
- `agent_runtime_test_cases.md` is the complete test-case catalog for the bounded `/chat` runtime, split into automated and manual cases.
- `agent_runtime_test_matrix.md` is the higher-level software-test matrix for `/chat`, organized by priority, category, and expected result.
- `v2_architecture.md` documents the V2 platform target and the current gateway-hosted V2 runtime shape.
- `v2_implementation_plan.md` tracks what has been implemented for V2 so far and what comes next.
- `v2_migration.md` records the migration policy from frozen V1 toward the future V2 platform.
- `ktp_pack.md` documents the first V2 domain pack, its flow, and its gateway/V2 testing surface.

### `scripts/`

- Contains local automation helpers.
- `seed_demo_models.py` seeds a ready model and one knowledge document.
- `demo_end_to_end.py` runs an in-process detect request through the gateway app.
- `demo_baldness_real_flow.py` runs the real baldness-detection chain with a cropped multispectral sample, the migrated RF model, report generation, and confidence output.
- The same real baldness demo now also writes a full workflow dashboard under the demo base directory.
- `diagnose_baldness_rf.py` runs a standalone RF diagnostic pass and writes `diagnostics.json` plus preview PNGs for the input, class map, confidence map, and per-class masks.
- `start_gateway_qwen_local.py` prepares local SQLite runtime state, seeds demo assets, enables the shared Qwen worker, and starts the live gateway.
- `start_gateway_qwen_local.py` now sets both `DATABASE_URL` and `ORCHESTRATOR_DATABASE_URL` to the same SQLite registry so the gateway-hosted V2 runtime and the older orchestrator adapters resolve the same demo model catalog.
- `check_agent_llm_runtime.py` probes the shared Qwen runtime and reports whether the local environment can actually start the 30B worker.

## Current Runtime Paths

### Agent runtime roadmap status

- The repository now maintains two parallel tracks:
  - the public KTP single-agent product on top of the V2 runtime
  - legacy orchestrator/chat-runtime code kept for migration safety
- The authoritative roadmap for the second track is documented in:
  - [docs/agent_runtime_roadmap.md](agent_runtime_roadmap.md)
- Current implementation status of that roadmap:
  - V2 shared schemas, registries, runtime store, and bounded engine are in place
  - the gateway now mounts V2 in-process and uses it as the live `/chat` and `/detect` path
  - KTP pack flow is implemented as a bounded multi-tool runtime action
  - `/v2/ui` is the current product UI and `/chat/ui` is only a redirect shim
  - legacy chat graph and orchestrator routes remain available for transition and service-level testing, but are not the primary public request path

### Gateway unified chat path

1. Gateway receives `POST /chat`.
2. `GatewayAgentService` resolves `conversation_id`:
   - when present, it is reused as the V2 `session_id`
   - when absent, one UUID is generated and used for both
3. The gateway builds `RequestContextV2(entrypoint="chat", ...)` from request fields such as `region`, `crop_type`, `task_type`, `image_path`, `use_mock`, and `extra_params`.
4. If the same conversation already has a latest V2 run, missing context fields are inherited from that run's `input_context`.
5. The gateway calls the in-process V2 runtime engine directly.
6. The deterministic planner chooses one bounded action:
   - direct answer
   - one tool call
   - KTP pack flow
   - delegation
   - abstain
7. If the request is KTP-analysis-like, the runtime executes the bounded KTP pack flow:
   - model lookup
   - inference
   - optional knowledge retrieval
   - report
   - confidence
   - optional visualization
8. The run is persisted in the V2 runtime store with:
   - `planner_decision`
   - `executor_action`
   - `tool_invocations`
   - `artifacts`
   - `trace`
   - `input_context`
9. The gateway returns `GatewayAgentResponse`, including debug links into `/v2/sessions`, `/v2/runs`, `/v2/runs/{run_id}/trace`, `/v2/runs/{run_id}/replay`, and `/v2/ui`.

### Gateway unified detect path

1. Gateway receives `POST /detect`.
2. `GatewayAgentService` creates a fresh V2 session for this request.
3. The gateway builds `RequestContextV2(entrypoint="detect", ...)`.
4. The V2 runtime executes one bounded run.
5. Detect requests default to the KTP pack-flow path and include visualization unless disabled upstream.
6. The gateway returns the same `GatewayAgentResponse` shape as `/chat`, including the V2 debug URLs.

### Gateway product UI path

1. Browser opens `GET /v2/ui`.
2. The gateway serves the V2 product page and static assets from `/v2/ui/dist`.
3. The UI defaults to same-origin API calls when hosted by the gateway.
4. Users interact through a conversation-style shell with a left session rail, a central message thread, and a bottom composer.
5. The main pane now consumes `/v2/sessions/{session_id}/messages/stream`, so users can see live run events such as planning, tool calls, artifacts, and the final assistant message.
6. Planner/tool/trace/replay data still live behind the collapsed debug drawer.
7. `GET /chat/ui` only redirects to `GET /v2/ui`.

### Gateway failure behavior

1. If model lookup fails, real dependencies are unavailable, inference fails, or a KTP tool raises, the V2 run ends as `failed`.
2. The error is written into the final run observation payload and trace.
3. The gateway returns that failed run through `GatewayAgentResponse`.
4. The runtime does not silently fall back to automatic mock execution.
5. Training is only started when the user explicitly asks for training; normal `/chat` and `/detect` requests do not auto-trigger training.

### Internal service health path

1. Gateway receives `GET /services/health`.
2. Gateway calls each internal service app through a local ASGI transport.
3. Each service returns its own `/health` payload.
4. Gateway aggregates the results and returns structured per-service status.

### Orchestrator existing-model path

1. Planner parses the request.
2. Orchestrator queries the registry database for a ready model.
3. Executor calls the inference service.
4. Executor calls the RAG service.
5. Executor calls the report service.
6. Executor calls the confidence service.
7. Executor calls the visualization service.

### Orchestrator missing-model path

1. Planner parses the request.
2. Registry lookup finds no ready model.
3. Workflow triggers either:
   - the mock training branch, or
   - a real Temporal workflow start request
4. Executor calls the RAG service.
5. Executor calls the report service.
6. Executor calls the confidence service.
7. Executor calls the visualization service.

## Key Environment Variables

- `DATABASE_URL`: database used by the model registry service.
- `ORCHESTRATOR_DATABASE_URL`: database URL used by the orchestrator local registry/inference integration.
- `ORCHESTRATOR_DEFAULT_USE_MOCK`: default inference mode for workflow runs.
- `ORCHESTRATOR_DEFAULT_IMAGE_PATH`: optional default image path for workflow runs.
- `ORCHESTRATOR_TRAINING_BACKEND`: `mock` or `temporal`.
- `ORCHESTRATOR_TRAINING_DATASET_URI_ROOT`: default dataset root used to derive training requests.
- `ORCHESTRATOR_TRAINING_MODEL_PREFIX`: default prefix used to derive output model names.
- `ORCHESTRATOR_INFERENCE_MASK_OUTPUT_DIR`: output directory for orchestrator-driven inference artifacts.
- `MASK_OUTPUT_DIR`: output directory used by the inference service itself for saved masks and derived target masks.
- `DEFAULT_PREDICTION_CLASS_SEMANTICS_JSON`: optional JSON fallback for model class semantics when metadata is unavailable.
- `AGENT_LLM_BACKEND`: `heuristic` or `subprocess_qwen`.
- `AGENT_LLM_MODEL_PATH`: local model directory used by planner and executor.
- `AGENT_LLM_RUNTIME_PYTHON`: Python executable used to run the external Qwen worker.
- `AGENT_LLM_PLANNER_ENABLED`: whether planner uses the shared model path.
- `AGENT_LLM_EXECUTOR_ENABLED`: whether executor uses the shared model path for result summarization.
- `VECTORSTORE_DIR`: local FAISS/document store directory for the RAG service.
- `USE_MOCK_EMBEDDING`: whether the RAG service uses deterministic mock embeddings.
- `REPORT_OUTPUT_DIR`: local HTML output directory for generated reports.
- `VISUALIZATION_OUTPUT_DIR`: local directory for generated workflow dashboards and preview artifacts.
- `VISUALIZATION_TEMPLATE_DIR`: Jinja2 template directory used by the visualization service.
- `VISUALIZATION_EMBED_HTML_IN_RESPONSE`: whether generated visualization HTML is embedded into structured responses.
- `CONFIDENCE_SERVICE_NAME`: service name for confidence evaluation.
- `BALDNESS_RF_DEFAULT_MODEL_PATH`: fallback local RF model path.
- `BALDNESS_RF_WORK_DIR`: working directory for real RF inference outputs.
- `V2_API_STORE_BACKEND`: V2 runtime store backend used by both standalone V2 API and the gateway-mounted V2 runtime.
- `V2_API_SQLITE_PATH`: SQLite file path used when `V2_API_STORE_BACKEND=sqlite`.

## Common Validation Commands

```bash
python -m uvicorn apps.api_gateway.main:app --host 0.0.0.0 --port 18080
python -m pytest v2/tests/test_api_smoke.py v2/tests/test_registry_smoke.py v2/tests/test_ktp_pack_smoke.py tests/test_api_gateway_chat.py tests/test_api_gateway_chat_ui.py tests/test_api_gateway_detect.py -q
python -m pytest tests/test_inference_api.py tests/test_baldness_rf_pipeline.py
python -m pytest tests/test_chunker.py tests/test_vectorstore.py tests/test_rag_api.py
python -m pytest tests/test_report_builder.py tests/test_report_api.py tests/test_confidence_service.py tests/test_confidence_api.py
python -m pytest tests/test_visualization_service.py tests/integration/test_gateway_to_orchestrator.py
```

## Local Notes

- For lightweight local runs, set `ORCHESTRATOR_DATABASE_URL` to a SQLite URL.
- The main human-facing entrypoint is now `GET /v2/ui` on the gateway host, typically `18080` in local runs.
- `POST /chat` is the recommended unified API entrypoint for conversational KTP use.
- `POST /detect` is the recommended unified API entrypoint for one-shot analysis tasks.
- `conversation_id` now maps directly onto the V2 `session_id`.
- When `conversation_id` is reused, follow-up requests inherit prior V2 run context such as `region`, `crop_type`, `task_type`, `image_path`, `use_mock`, and `extra_params` when omitted.
- Automatic mock fallback is disabled on the public single-agent path.
- Example chat request:

```json
{
  "request_id": "req-chat-qa-001",
  "message": "NDVI 和 EVI 有什么区别？",
  "extra_params": {}
}
```

- Example detect request:

```json
{
  "request_id": "req-detect-001",
  "user_query": "请分析这张影像并给出报告和可视化",
  "region": "henan",
  "crop_type": "wheat",
  "task_type": "crop_health_detection",
  "image_path": "/data/demo/sample.tif",
  "extra_params": {}
}
```

- Example follow-up request using the previous context:

```json
{
  "request_id": "req-chat-followup-001",
  "conversation_id": "conv-demo-001",
  "message": "那它更适合高植被覆盖区吗？",
  "mode": "auto",
  "extra_params": {}
}
```

- Example workflow request:

```json
{
  "request_id": "req-chat-wf-001",
  "message": "请分析河南小麦长势，并生成报告和置信度说明。",
  "mode": "auto",
  "region": "henan",
  "crop_type": "wheat",
  "use_mock": true,
  "extra_params": {}
}
```

- Browser playground:
  - Open `http://127.0.0.1:18080/v2/ui`
  - Default behavior is `mode="auto"`
  - Reuse of `conversation_id` is automatic inside the page
  - `Ctrl+Enter` or `Cmd+Enter` sends the current message

- To exercise the real baldness RF path, register a ready model whose `artifact_uri` points to a local `.pkl` file or `file://...` URI, and pass a multiband GeoTIFF as `image_path`.
- For any multi-class predictor, add `metrics_json.prediction_class_semantics` at model registration time; the minimum safe payload is `class_labels` plus `target_classes`.
- For a fully local MVP path, run `scripts/seed_demo_models.py` and then `scripts/demo_end_to_end.py`.
- To enable the shared Qwen planner/executor path, set `AGENT_LLM_BACKEND=subprocess_qwen`, point `AGENT_LLM_MODEL_PATH` to the local model directory, and use a Python runtime that already has `torch` and `transformers`.
- In the current local workspace, `.env` can set one shared 30B model as the default backend for both planner and executor.
- For the most repeatable live local run, use `scripts/start_gateway_qwen_local.py`, which avoids manual environment drift and seeds the SQLite demo runtime automatically.
- For a repeatable real baldness workflow check, use `scripts/demo_baldness_real_flow.py`, which crops a real sample, seeds the RF model in SQLite, runs real inference, and writes the final response JSON under the demo base directory.
- The current baldness demo seeds its own class semantics in model metadata rather than relying on any globally hard-coded class IDs.
- When the real baldness RF output is degenerate, expect the response JSON to contain `confidence_result.image_detail.warnings`, and expect the report HTML to include an inference sanity warning in the summary and inference table.
- To inspect why a real RF result looks wrong, run `scripts/diagnose_baldness_rf.py`; it writes reusable preview artifacts that can be compared directly against the workflow dashboard output.
- After any completed gateway request, open `GET /workflow/{request_id}/visualization` to view the generated dashboard in the browser, or read `visualization_result.visualization_uri` from the API response.
