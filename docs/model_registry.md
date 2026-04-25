# Model Registry Draft

## Responsibilities

The model registry is the system of record for model metadata. It does not train models and it does not run inference. Its job is to answer questions such as:

- does a usable model already exist for a region, crop type, and task type
- what is the latest ready model
- what lifecycle state is a model currently in
- where is the model artifact stored

This keeps orchestration and execution layers from guessing model availability.

## Why It Is a Separate Service

The registry is a distinct concern from training and inference:

- training creates or updates model entries
- inference consumes ready model entries
- orchestrator only needs lookup semantics

Separating this service gives the rest of the system one stable API for model facts and avoids embedding registry logic inside LangGraph nodes or prompts.

## Data Model

The registry stores one row per model version in `registered_models` with these core fields:

- `region`
- `crop_type`
- `task_type`
- `model_name`
- `model_version`
- `artifact_uri`
- `metrics_json`
- `status`
- `description`
- `created_at`
- `updated_at`

This structure supports multiple versions for the same region, crop, and task combination.

## Status Rules

The service uses a small lifecycle state machine:

- `training`: model is being prepared and cannot be used for inference
- `ready`: model is available for inference lookup
- `failed`: model training failed and cannot be used
- `deprecated`: historical model retained for audit but not recommended for use

Lookup only returns the latest `ready` model. If only `training`, `failed`, or `deprecated` versions exist, the lookup response reports `model_exists=false`.

## API Summary

- `GET /health`: health payload for the service
- `POST /models`: register a new model version
- `GET /models/lookup`: find the latest ready model for `region + crop_type + task_type`
- `GET /models/{model_id}`: fetch a model by id
- `PATCH /models/{model_id}/status`: update lifecycle status
- `GET /models`: list models with basic filtering

Responses are Pydantic-based and the lookup response is intentionally shaped so the orchestrator can consume it directly later.

## Future Integration

The planned integration path is:

- training service: registers new versions and transitions models from `training` to `ready` or `failed`
- inference service: resolves the latest ready model and its artifact URI before inference
- orchestrator: replaces the current mock registry lookup in `check_model_registry` with this service

This phase only establishes the service boundary, schemas, and lifecycle behavior.
