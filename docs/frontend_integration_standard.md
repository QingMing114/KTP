# KTP Frontend Integration Standard

## Goal

This document defines how any first-party frontend should integrate with `ktp_product`.

Use this as the implementation standard for:
- custom web frontend
- desktop shell
- future mobile or embedded frontend

Do not couple new frontend code to current `/v2` payload details.  
The stable contract is the canonical product protocol:

- [canonical_product_protocol.md](canonical_product_protocol.md)

## Current Backend Status

Backend canonical protocol is already available and should be treated as the source of truth:

- base path: `/api/product/v1`

Current adapter paths still exist:
- `/v2/*`: product/debug adapter
- `/v1/models`
- `/v1/chat/completions`: OpenAI-compatible adapter for LibreChat and similar clients

For a new first-party frontend, **use `/api/product/v1` as the primary API**.

## Frontend Design Rules

### 1. Protocol Rule

Frontend must only treat these as stable:
- canonical resources
- canonical enums
- canonical error envelope
- canonical artifact URLs

Frontend must not depend on:
- internal specialist names
- tool invocation internals
- current trace shape
- local filesystem paths
- current `/v2` debug-only fields

### 2. Compatibility Rule

Frontend must ignore unknown fields in all responses.

That means:
- backend may add fields later
- frontend must not break on additive changes

### 3. Task Delivery Rule

Frontend should treat the backend as:
- `async-first` for dataset-backed or long-running tasks
- `manifest-driven` for optional features
- `resource-oriented` instead of RPC-shaped

## Canonical Resource Model

Frontend should build its state model around these objects:

### Manifest
Capability negotiation and feature discovery.

### Dataset
Stable reference to large local inputs.

### Conversation
Conversation container and history anchor.

### Submission
Async accepted task handle.

### Run
Final execution result.

### Artifact
Stable result resource.

## Primary Frontend Flows

### Flow A: App Boot

On app startup:

1. `GET /api/product/v1/manifest`
2. cache:
   - `protocol_version`
   - `delivery_modes`
   - `supported_preferences`
   - `artifact_kinds`
   - `compat_adapters`
   - `features`

Frontend should render capability-driven UI, not hard-coded assumptions.

### Flow B: Create Conversation

Use:

- `POST /api/product/v1/conversations`

Minimal request:

```json
{
  "title": "New Conversation"
}
```

### Flow C: Register Large Dataset

Large raster inputs must be registered first.

Use:

- `POST /api/product/v1/datasets`

Example:

```json
{
  "source": {
    "kind": "local_path",
    "uri": "/abs/path/to/file.tif"
  },
  "display_name": "file.tif",
  "defaults": {
    "region": "scalp",
    "crop_type": "hair",
    "task_type": "baldness_detection"
  },
  "metadata": {},
  "tags": []
}
```

Important rule:
- local path exists only at ingestion time
- after registration, frontend should only use `dataset_id`

### Flow D: Submit Work

Use:

- `POST /api/product/v1/conversations/{conversation_id}/submissions`

Example:

```json
{
  "input": {
    "message": "请对 dataset:ds_xxx 做真实斑秃识别，并生成分析报告、置信度说明和可视化。",
    "refs": [
      { "type": "dataset", "id": "ds_xxx" }
    ]
  },
  "context": {
    "inherit": "latest",
    "inherit_run_id": null
  },
  "mode": {
    "interaction": "task",
    "delivery": "async"
  },
  "preferences": {
    "include_visualization": true,
    "include_knowledge": true
  },
  "client": {
    "name": "custom-ui",
    "version": "1.0.0"
  }
}
```

### Flow E: Track Progress

Preferred:

- `GET /api/product/v1/submissions/{submission_id}/events`

Fallback:

- `GET /api/product/v1/submissions/{submission_id}`

Frontend should always support both.

### Flow F: Read Final Result

After `submission.status` reaches terminal state:

- read `run_id`
- call `GET /api/product/v1/runs/{run_id}`

Main render inputs:
- `assistant.summary`
- `assistant.parts`
- `artifacts`
- `workflow_summary`
- `termination_reason`

### Flow G: Open Artifacts

Never build local file paths on the frontend.

Use:
- `artifact.view_url`
- `artifact.download_url`

Canonical frontend should treat `artifact_id` and artifact URLs as the only stable artifact reference.

## Frontend State Machine

Frontend submission status handling should use only these values:

### submission.status
- `queued`
- `running`
- `cancelling`
- `cancelled`
- `completed`
- `failed`

### submission.stage
- `accepted`
- `processing`
- `finalizing`
- `completed`
- `failed`

Do not display internal runtime phases like planner/delegate/tool step as the primary UI phase.  
Those are debug concerns.

## Conversation Context Rules

Frontend should use canonical inheritance instead of guessing context behavior.

### Continue previous context

```json
{
  "context": {
    "inherit": "latest"
  }
}
```

### Explicitly no inheritance

```json
{
  "context": {
    "inherit": "none"
  }
}
```

### Inherit a specific run

```json
{
  "context": {
    "inherit": "latest",
    "inherit_run_id": "run_xxx"
  }
}
```

Rule:
- frontend should not try to reconstruct prior runtime context client-side
- backend is the source of truth for inheritance

## SSE Standard

Use:

- `GET /api/product/v1/submissions/{submission_id}/events`

Wire format:

```text
id: evt_003
event: run.progress
data: {"submission_id":"job_xxx","run_id":"run_xxx","stage":"processing"}
```

Reconnect rule:
- send `Last-Event-ID`
- backend will replay if possible
- otherwise backend emits a fresh `submission.updated` snapshot and continues

Frontend requirement:
- SSE disconnect must not break the task page
- always implement polling fallback

## Error Handling Standard

All non-2xx responses use:

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

Frontend should:
- show `message` to the user
- log `code`
- attach `request_id` to error reporting
- use `code` for conditional handling

Examples:
- `UNAUTHORIZED`
- `DATASET_NOT_FOUND`
- `CONVERSATION_NOT_FOUND`
- `RUN_NOT_FOUND`
- `UPSTREAM_LLM_TIMEOUT`
- `UPSTREAM_LLM_OVERLOADED`
- `TOOL_EXECUTION_FAILED`
- `ALREADY_TERMINAL`

## Auth Standard

Canonical frontend should send:

```http
Authorization: Bearer <token>
```

Do not invent a different auth scheme in frontend code.

## Idempotency Standard

For create or submit actions, frontend should generate an idempotency key:

```http
Idempotency-Key: <uuid>
```

Use it for:
- dataset registration
- conversation creation
- submission creation
- cancel submission

This protects frontend retries from creating duplicate resources.

## Required Frontend Modules

Any new frontend should be structured around these modules:

### 1. `manifestClient`
Responsibilities:
- fetch manifest
- cache supported capabilities

### 2. `datasetClient`
Responsibilities:
- register dataset
- fetch dataset
- list datasets
- patch dataset
- delete dataset

### 3. `conversationClient`
Responsibilities:
- create conversation
- fetch conversation
- list conversations
- patch conversation
- archive conversation

### 4. `submissionClient`
Responsibilities:
- create submission
- fetch submission
- cancel submission
- subscribe to SSE
- poll fallback

### 5. `runClient`
Responsibilities:
- fetch run
- fetch conversation runs

### 6. `artifactClient`
Responsibilities:
- resolve artifact cards
- open `view_url`
- open `download_url`

### 7. `debugClient`
Optional, separate from main product UI:
- trace
- state
- replay

## Frontend Rendering Rules

### Main Conversation Thread

Render from:
- `assistant.summary`
- `assistant.parts`

Supported assistant part types:
- `text`
- `status`
- `artifact_ref`
- `warning`
- `error`

### Result Area

Render from:
- `artifacts`

Recommended default prominence:
- report
- visualization
- mask / inference output
- confidence summary

### Debug Area

Do not mix debug details into the main conversation thread.

Debug-only data should live in:
- separate debug drawer
- separate debug panel
- separate inspector route

Read from:
- `/api/product/v1/debug/...`

## What Frontend Must Not Do

- Do not use local file path as a stable artifact reference
- Do not parse trace to determine task success
- Do not rely on internal specialist names
- Do not rely on current `/v2` artifact path conventions
- Do not assume future backends will keep the current QueryEngine implementation
- Do not send undeclared preferences

## Recommended TypeScript Shapes

These are the minimal stable frontend-side types to mirror.

```ts
type SubmissionStatus =
  | "queued"
  | "running"
  | "cancelling"
  | "cancelled"
  | "completed"
  | "failed";

type SubmissionStage =
  | "accepted"
  | "processing"
  | "finalizing"
  | "completed"
  | "failed";

type AssistantPartType =
  | "text"
  | "status"
  | "artifact_ref"
  | "warning"
  | "error";
```

Frontend should keep its internal types additive-friendly and ignore unknown fields from the backend.

## Recommended Implementation Order

1. Implement `manifest` fetch on boot
2. Implement conversation create/list/get
3. Implement dataset register/get/list
4. Implement submission create/get
5. Implement SSE + polling fallback
6. Implement run fetch and artifact rendering
7. Add cancel
8. Add debug drawer on top of canonical flow

## Practical Boundary

Use canonical protocol for:
- your own frontend
- internal product UI
- future replacement frontend

Use adapters for:
- LibreChat
- OpenAI-compatible clients
- temporary legacy `/v2` product shell

If you keep this boundary, backend and frontend can evolve independently without re-binding to internal runtime details.
