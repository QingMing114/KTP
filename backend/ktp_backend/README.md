# KTP Backend

This directory is the new backend-only composition root for the KTP chat-first agent.

Files:

- `runtime_host.py`: runtime/container assembly
- `api.py`: standalone HTTP API for sessions, runs, streaming, tools, and metadata
- `gateway_bridge.py`: compatibility bridge used by `/chat`, `/detect`, and `/v1/*`
- `ARCHITECTURE.md`: backend layering, boundaries, and extension rules
- `ENGINEERING_STANDARDS.md`: test, documentation, and change-management bar

Rule:

- New backend work should land here first.
- Existing `apps/api_gateway/*` and `v2/apps/api/*` should stay as thin wrappers or compatibility shells.
