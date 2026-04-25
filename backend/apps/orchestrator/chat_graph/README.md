## Chat Graph Status

This package is the bounded self-scheduling chat runtime for the future `/chat` path.

Current status:

- state contract exists
- tool loading node exists
- planner / executor / dispatch / finalize nodes are implemented
- observation validation node is implemented
- LangGraph-backed builder exists with lazy import
- in-process dry-run fallback exists for environments without `langgraph`
- bounded single-replan loop exists for tool failure recovery
- runtime state now records per-node trace events for later debugging and audit
- gateway can route into this runtime behind `API_GATEWAY_CHAT_AGENT_RUNTIME_ENABLED=true`
- `/chat` has not yet fully migrated here by default

Planned runtime:

1. load tool registry
2. planner decides
3. executor prepares exact tool invocation
4. tool dispatch executes bounded capability
5. observation validation checks whether bounded outputs are complete enough to trust
6. bounded replan loop may retry once before abstaining
