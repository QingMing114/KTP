# Multi-Agent Single Entry

`ktp_product` exposes a single public agent surface and keeps specialization inside the backend runtime.

## Public Surface

- The product exposes one public entry agent: `ktp_frontdesk`
- Third-party frontends should keep using one model or one assistant surface
- `/v1/chat/completions` and `/v2/*` both enter the same chat-first runtime

## Internal Specialists

The runtime may delegate internally to bounded specialist agents:

- `ktp_analysis_specialist`
- `ktp_knowledge_specialist`
- `ktp_training_specialist`
- `ktp_workspace_specialist`

These specialists are backend-internal orchestration units. They are not separate public products and should not become separate frontend models.

## Routing Rules

The backend agent router applies deterministic delegation based on the selected tool or task mode:

- analysis, report, confidence, visualization -> `ktp_analysis_specialist`
- local knowledge retrieval and explanation -> `ktp_knowledge_specialist`
- explicit training requests -> `ktp_training_specialist`
- bounded workspace read/search -> `ktp_workspace_specialist`

## Why This Shape

This keeps the frontend simple while preserving backend extensibility:

- one public agent contract
- one conversation history
- auditable delegation inside trace and run state
- future specialist growth without breaking frontend integrations

## Current Boundaries

- delegation is backend-internal and auditable
- approval flow is still partial for dangerous tools
- public frontend integrations should not orchestrate the internal agent graph directly
