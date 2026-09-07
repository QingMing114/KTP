# KTP Backend Architecture

## Goal

`ktp_backend/` is the backend composition root for the KTP chat-first agent. It exists to keep runtime, protocol, and gateway compatibility logic in one place so frontend changes do not force backend rewrites.

## Layers

1. `runtime_host.py`
   Assembles the backend container.
   Owns runtime store, tool registry, pack registry, policy registry, agent registry, runtime engine, and shared LLM provider.

2. `api.py`
   Exposes the backend HTTP contract.
   Owns session, run, replay, metadata, and SSE endpoints.

3. `gateway_bridge.py`
   Adapts public compatibility surfaces into the backend runtime.
   Owns `/chat`, `/detect`, and OpenAI-compatible request translation.

4. `v2/runtime/*`
   Owns planner, execution loop, run lifecycle, and persistence semantics.

5. `v2/tools/*` and `v2/adapters/*`
   Own tool metadata, tool handlers, and Python service integration.

6. `services/*` and `ml/*`
   Own real domain execution, model lookup, inference, report, confidence, visualization, training, and algorithm implementation.

## Hard Boundaries

- Frontend code must not import `services/*` or `ml/*` directly.
- Gateway routers should not contain runtime business logic.
- Runtime business logic should not depend on HTML, templates, or browser-specific state.
- Tool metadata and tool handlers must stay in the tool layer, not in routers.
- Compatibility wrappers can delegate inward, but new product logic should not be added to wrappers.

## Extension Rules

- New backend protocol surfaces go in `ktp_backend/` first.
- New tool families extend `v2/tools/registry.py` and `v2/tools/handlers.py`.
- New domain workflows extend `services/*` and are exposed upward through tool adapters.
- New frontend shells should prefer `/v2/*` or `/v1/*` contracts and should not bypass the backend runtime.

## Claude-Style Alignment

This backend is intentionally moving toward the same high-level shape used by modern agent products:

- a single runtime container
- a unified tool registry
- protocol adapters at the edge
- thin transport wrappers
- a chat-first execution loop

The alignment target is architectural shape, not code copying.

## Current Compatibility Shells

- Production ASGI target: `apps.api_gateway.main:app`.  It constructs one
  `BackendRuntimeHost`, mounts canonical `/api/product/v1`, and then mounts
  compatibility routes onto that same host.
- `app/main.py` is a deprecated import shell for old local commands; it is not
  a second deployable application design.
- `v2/apps/api/main.py`
  Deprecated thin wrapper over `ktp_backend.api`, retained for `/v2/*` test and
  debug compatibility only.
- `apps/api_gateway/services/gateway_agent_service.py`
  Thin wrapper over `ktp_backend.gateway_bridge`
- `apps/api_gateway/main.py`
  Product gateway shell that mounts the backend runtime and keeps legacy/public routes alive
