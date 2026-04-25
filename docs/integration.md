# Integration

## Current MVP Chain

The repository now supports a local MVP chain:

`API Gateway -> Orchestrator -> model_registry -> inference/training -> rag -> report -> confidence -> visualization`

The full outward-facing flow now works in one request:

1. `POST /detect`
2. gateway delegates to the orchestrator client
3. orchestrator runs the LangGraph chain
4. gateway returns a stable structured response
5. `GET /workflow/{request_id}` can retrieve the cached workflow result
6. `GET /workflow/{request_id}/visualization` returns the rendered HTML dashboard
7. `GET /services/health` aggregates service health snapshots

## Connection Strategy

Current integration uses local client adapters rather than external network calls.
This keeps tests deterministic while preserving service boundaries.

- Gateway calls the orchestrator through `LocalOrchestratorClient`
- Orchestrator nodes call client wrappers under `apps/orchestrator/clients/`
- Those wrappers currently delegate to service-local clients or service layers

This means the boundaries are already explicit and can later switch to HTTP/gRPC/message queues without rewriting the graph nodes.

## Client Boundaries

- `apps/api_gateway/clients/orchestrator_client.py`: gateway-to-orchestrator boundary
- `apps/orchestrator/clients/model_registry_client.py`: registry lookup boundary
- `apps/orchestrator/clients/training_service_client.py`: training trigger boundary
- `apps/orchestrator/clients/inference_service_client.py`: inference boundary
- `apps/orchestrator/clients/rag_service_client.py`: retrieval boundary
- `apps/orchestrator/clients/report_service_client.py`: report generation boundary
- `apps/orchestrator/clients/confidence_service_client.py`: confidence evaluation boundary
- `apps/orchestrator/clients/visualization_service_client.py`: workflow dashboard boundary

## What Is Real vs Mock

Currently real local integrations:

- model registry
- inference service
- RAG service
- report service
- confidence service
- visualization service
- Temporal training client trigger

Still simplified or heuristic:

- planner logic
- training execution semantics after workflow start
- confidence scoring heuristics
- report visual design and charting depth
- dashboard visual design is local HTML rather than a dedicated web frontend

## Integration Test Coverage

The repository now includes:

- `tests/integration/test_gateway_to_orchestrator.py`
- `tests/integration/test_orchestrator_service_chain.py`
- `tests/integration/test_end_to_end_mock_flow.py`
- `tests/e2e/test_demo_request.py`

These cover:

- gateway to orchestrator wiring
- existing-model path
- local demo request execution
- aggregated service health
- report and confidence completion in the final response
- visualization generation and dashboard retrieval through the gateway

## Gateway Responsibilities

Gateway now exposes:

- `POST /detect`
- `GET /workflow/{request_id}`
- `GET /workflow/{request_id}/visualization`
- `GET /services/health`

The gateway does not orchestrate business logic directly. It delegates to the orchestrator client and only shapes external API responses.

## Next Integration Step

The next practical stage is not another infrastructure module. It is replacing the deterministic planner/executor internals with your real large-model backend while keeping the current schemas and service boundaries stable.
