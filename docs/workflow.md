# Workflow Draft

## Current Main Flow

The current LangGraph workflow models the platform's primary business chain as a replaceable state graph:

request -> parse_request -> check_model_registry -> run_inference or trigger_training -> run_rag -> build_report -> evaluate_confidence -> end

The workflow is no longer fully mock. It now uses:

- a real local model registry lookup adapter backed by the registry database
- a real local inference adapter backed by `services/inference_service`
- a real local RAG adapter backed by `services/rag_service`
- a real local report adapter backed by `services/report_service`
- a real local confidence adapter backed by `services/confidence_service`
- a configurable training adapter:
  - `mock` backend for lightweight local runs
  - `temporal` backend for real workflow start requests

The workflow is currently exercised through:

- direct orchestrator calls in unit and integration tests
- `LocalOrchestratorClient` from the API gateway
- `scripts/demo_end_to_end.py` for a local MVP request

The planner and executor can now share one local-model backend through `infra/llm`, while the graph order and service clients remain unchanged.

## Why LangGraph

LangGraph is used here because the system needs explicit state transitions, conditional branches, and future subgraph composition. It provides a clear way to model:

- shared workflow state
- replaceable node implementations
- routing after registry checks
- future insertion of subgraphs and new task branches

This keeps workflow logic out of prompts and out of FastAPI route handlers.

## Node Responsibilities

- `parse_request`: calls the planner role to turn a raw query into structured planning fields
- `check_model_registry`: queries the latest ready model through the model registry service layer and decides the next branch
- `run_inference`: executes the integrated inference service when a model exists
- `trigger_training`: either executes the mock training adapter or starts a real Temporal workflow, depending on orchestrator config
- `run_rag`: queries the local RAG service and returns traceable knowledge snippets
- `build_report`: generates a persisted HTML report when the plan asks for it
- `evaluate_confidence`: computes image/text/workflow confidence and returns a fused result

Each node reads from and writes back to the same workflow state object so later phases can swap implementations without changing the graph contract.

## Current Integrated Inputs

The workflow request now supports these additional inference-related fields:

- `image_path`: optional local image path forwarded to the inference service
- `use_mock`: optional flag to force mock or real inference
- `extra_params`: optional structured parameters forwarded to downstream services such as inference, training, and RAG

If `use_mock=true` and no `image_path` is provided, the orchestrator generates a small local demo image so the mock inference path stays runnable for local development.

When `ORCHESTRATOR_TRAINING_BACKEND=temporal`, the training branch uses `extra_params` for optional overrides such as:

- `dataset_uri`
- `base_model_name`
- `output_model_name`
- `output_model_version`
- `trigger_reason`

## Planner and Executor Roles

- Planner role: understands the user request and produces a structured plan
- Executor role: receives structured tasks and dispatches to service adapters

Neither role owns the whole workflow. The LangGraph orchestrator remains the source of process order and branching.

## Future Integration Path

The current MVP is already integrated end to end, but several boundaries remain intentionally replaceable for the next stage:

- planner and executor can later be backed by your real large model endpoints
- local service clients can later be replaced by HTTP or RPC clients without changing node contracts
- training completion semantics can be expanded from "workflow started" to richer lifecycle monitoring
- additional task types can be added as graph branches or subgraphs

Because each boundary already uses explicit schemas and node-specific clients, these replacements can happen incrementally without redesigning the workflow graph.
