# KTP Canonical Product Protocol v1.1

## Positioning

- Canonical protocol base path: `/api/product/v1`
- Stable contract: frontend, backend runtime, `/v2`, and `/v1` adapters may evolve independently
- Current adapters:
  - `/v2/*`: product/debug adapter
  - `/v1/models` and `/v1/chat/completions`: OpenAI-compatible adapter for LibreChat and similar shells

The canonical protocol is the only long-term product contract. New frontend work should target it instead of binding to current `/v2` payload shapes.

Workspace extension (2026-10-12): [workspace assistant integration](workspace_assistant_integration.md) defines workspace context, product-facing plans/parameters/actions, and links to analysis workflows. These additive capabilities are advertised by the manifest; old clients may ignore them. Internal trace remains debug-only.

### Workspace assistant extension

- Manifest features: `workspace_context`, `workspace_assistant_actions`, `analysis_parameter_cards`.
- `PUT /workspaces/{workspace_id}/context`: synchronize the current typed workspace snapshot. A stale revision or conflicting snapshot returns 409. Workspace state is scoped to the authenticated owner.
- `GET /workspaces/{workspace_id}/workflows`: recover that owner's associated workflows.
- Submissions accept optional `context.workspace`; ordinary Chat submissions continue to use the existing runtime path.
- `context.workspace_ui` optionally includes the original workbench's current card content: farm/AOI summaries, imagery candidates and explicit selection, task options and checked tasks, parameters, workflow status, and historical plan cards. It is a bounded observation object, separate from the versioned execution snapshot; its contents cannot authorize execution or invalidate a task merely because a progress card updated.
- The planner also receives recent persisted structured plans, labelled by whether their AOI and imagery still match. The current workspace snapshot and checked tasks take priority over historical missing-input messages.
- The active task card sends `input.workspace_action = {action_id, task_ids}` to explicitly confirm the synchronized draft; its task set must match `context.workspace.draft_task_ids`. This path does not call the model. Older cards may also include `source_run_id`; the server validates their originating conversation, action ID and map inputs. Both paths use the same verified workflow service as natural-language execution.
- Assistant parts add `analysis_plan`, `parameter_set`, `action_card`, `workflow_reference`, each with a stable `part_id` and `data`. Status and explanation turns return text without generating new configuration cards.
- SSE adds `assistant.part.updated`, `action.updated`, `workflow.linked`; parts are also persisted in the final Run for reconnect and refresh recovery.
- `POST /analysis-workflows` accepts `Idempotency-Key` and optional `action_id`, `workspace_id`, `workspace_revision`, `conversation_id`. Durable action deduplication and an atomic start claim prevent duplicate workers.
- Workflow resources include a server-owned `parameters` snapshot. Fixed parameters are read-only; their values are shared by execution, cards and the workflow report.
- A completed conversation Run does not imply a completed analysis workflow. Cancelling a Submission stops the current assistant turn; an already submitted analysis remains independent.

## Resources

- `Manifest`
- `Dataset`
- `Conversation`
- `Submission`
- `Run`
- `Artifact`
- `Error`

## Auth

All canonical endpoints accept:

```http
Authorization: Bearer <token>
```

Current local default token is `sk-ktp-local`.

## Endpoints

### Manifest

- `GET /api/product/v1/manifest`

Returns:
- `protocol_version`
- `features`
- `delivery_modes`
- `supported_preferences`
- `artifact_kinds`
- `compat_adapters`
- `limits`
- `debug_extension`

### Datasets

- `POST /api/product/v1/datasets`
- `GET /api/product/v1/datasets`
- `GET /api/product/v1/datasets/{dataset_id}`
- `PATCH /api/product/v1/datasets/{dataset_id}`
- `DELETE /api/product/v1/datasets/{dataset_id}`

Notes:
- v1 currently supports `source.kind=local_path` only
- Dataset `defaults` are canonical task defaults and are inherited by later submissions
- `DELETE` removes the registry reference only; it does not delete the source file

### Conversations

- `POST /api/product/v1/conversations`
- `GET /api/product/v1/conversations`
- `GET /api/product/v1/conversations/{conversation_id}`
- `PATCH /api/product/v1/conversations/{conversation_id}`
- `DELETE /api/product/v1/conversations/{conversation_id}`
- `GET /api/product/v1/conversations/{conversation_id}/runs`

Notes:
- `DELETE` is a soft archive
- `PATCH` currently supports `title` and `archived`

### Submissions

- `POST /api/product/v1/conversations/{conversation_id}/submissions`
- `GET /api/product/v1/submissions/{submission_id}`
- `GET /api/product/v1/submissions/{submission_id}/events`
- `POST /api/product/v1/submissions/{submission_id}/cancel`

Canonical mode:
- v1 requires `delivery=async`
- `sync` and `stream` remain optional adapter capabilities, not core v1 guarantees

Context inheritance:
- `context.inherit=latest`: inherit the latest run in the conversation
- `context.inherit=none`: do not inherit previous run context
- `context.inherit_run_id=<run_id>`: inherit a specific run

### Runs

- `GET /api/product/v1/runs/{run_id}`

Frontend should primarily render:
- `assistant.summary`
- `assistant.parts`
- `artifacts`
- `workflow_summary`
- `termination_reason`

### Artifacts

- `GET /api/product/v1/artifacts/{artifact_id}`
- `GET /api/product/v1/artifacts/{artifact_id}/content`

Canonical protocol exposes artifact resources, not local filesystem paths.

### Debug Extension

- `GET /api/product/v1/debug/runs/{run_id}/trace`
- `GET /api/product/v1/debug/runs/{run_id}/state`
- `POST /api/product/v1/debug/runs/{run_id}/replay`

Debug endpoints are intentionally separate from the stable product contract.

## Submission Lifecycle

`Submission.status` values:

- `queued`
- `running`
- `cancelling`
- `cancelled`
- `completed`
- `failed`

`Submission.stage` values:

- `accepted`
- `processing`
- `finalizing`
- `completed`
- `failed`

The stage field is intentionally coarse. Internal planner, delegation, and tool phases remain debug details.

## SSE

Event stream endpoint:

- `GET /api/product/v1/submissions/{submission_id}/events`

Canonical event types:

- `submission.accepted`
- `submission.updated`
- `run.started`
- `run.progress`
- `artifact.available`
- `run.completed`
- `run.failed`
- `submission.cancelled`

Wire format:

```text
id: evt_003
event: run.progress
data: {"submission_id":"job_xxx","run_id":"run_xxx","stage":"processing"}
```

Reconnect:
- client sends `Last-Event-ID`
- server replays subsequent events when possible
- if the event is no longer available, server emits a fresh `submission.updated` snapshot and continues

## Pagination

List endpoints use cursor pagination:

```json
{
  "items": [],
  "next_cursor": "10",
  "has_more": true
}
```

Cursor pagination is used by:
- `GET /datasets`
- `GET /conversations`
- `GET /conversations/{conversation_id}/runs`

## Idempotency

These endpoints support:

```http
Idempotency-Key: client-generated-uuid
```

Supported routes:
- `POST /datasets`
- `POST /conversations`
- `POST /conversations/{conversation_id}/submissions`
- `POST /submissions/{submission_id}/cancel`

If the same key is reused with a different request body, the server returns `409 IDEMPOTENCY_CONFLICT`.

## Errors

Non-2xx responses use the canonical envelope:

```json
{
  "error": {
    "code": "DATASET_NOT_FOUND",
    "message": "Dataset ds_xxx not found",
    "detail": {},
    "request_id": "req_xxx"
  }
}
```

Representative error codes:
- `INVALID_REQUEST`
- `UNAUTHORIZED`
- `DATASET_NOT_FOUND`
- `DATASET_SOURCE_NOT_FOUND`
- `CONVERSATION_NOT_FOUND`
- `SUBMISSION_NOT_FOUND`
- `RUN_NOT_FOUND`
- `ARTIFACT_NOT_FOUND`
- `UNSUPPORTED_SOURCE_KIND`
- `UNSUPPORTED_DELIVERY_MODE`
- `INVALID_REFERENCE`
- `IDEMPOTENCY_CONFLICT`
- `UPSTREAM_LLM_TIMEOUT`
- `UPSTREAM_LLM_OVERLOADED`
- `SCHEMA_MISMATCH`
- `TOOL_EXECUTION_FAILED`
- `REPLAN_BUDGET_EXCEEDED`
- `CANCELLATION_NOT_SUPPORTED`
- `ALREADY_TERMINAL`
- `INTERNAL_ERROR`

## Recommended Frontend Usage

Map workspace yield extension (2026-10-12): `yield_simple` is an independent experimental grain dry-matter estimate for wheat/maize, with automatic optical season detection and public radiation. It depends on `crop`, requires no manual planting/harvest dates, and publishes `simple_yield_report`. Manifest declares `simple_yield_estimation`. `yield` remains APSIM; `potential` remains a dimensionless canopy index. See [method, inputs and output contract](simple_yield_estimation.md).

### Large dataset flow

1. Register a dataset once through `POST /datasets`
2. Create a conversation
3. Submit work through `POST /conversations/{id}/submissions`
4. Poll `GET /submissions/{id}` or subscribe to `GET /submissions/{id}/events`
5. Read the final `Run`
6. Render `Artifact` resources by `artifact_id`

### Third-party chat shells

LibreChat and other OpenAI-style shells should continue to use `/v1/chat/completions`. The adapter maps those requests into canonical `Submission` semantics.
