# Training Workflow Draft

## Why Temporal

Training is the first genuinely long-running path in the system. It needs retries, durable state, and clean recovery if a process dies midway. Temporal fits that requirement better than keeping the training chain inside FastAPI handlers or inside the LangGraph node itself.

## Current Chain

The current workflow is:

training request -> prepare_dataset -> launch_training -> evaluate_model -> register_model -> return workflow result

At this stage every execution step is still mock-backed, but the workflow and activity boundaries are real.

## Workflow vs Activity Split

- workflow: owns orchestration, ordering, retry policy, and final structured result
- activities: own concrete work such as preparing data, launching training, evaluating output, and registering the model

This keeps Temporal workflow code thin and future-proof while allowing each activity to be replaced independently.

## Temporal Sandbox Note

Temporal validates workflow imports inside a sandboxed runtime. Because of that, the
`services/training_service/__init__.py` package entrypoint is intentionally kept
side-effect free. Runtime-only pieces such as settings loading and Temporal client
creation stay in `client.py` and `config.py`, while workflow-safe schemas stay in
`schemas.py`.

## Relation to Orchestrator

The LangGraph orchestrator should not train models directly. Its `trigger_training` step will eventually package a `TrainingRequest`, start this Temporal workflow, and keep only workflow metadata such as workflow id or job id in its own state.

## Relation to Model Registry

The training workflow ends by calling the model registry through a dedicated HTTP adapter. That keeps registry integration out of the Temporal workflow body and leaves a clean boundary for future replacement with an internal SDK.

## Current Mock Nature and Future Swap

The current `TrainerAdapter` is deterministic and returns stable fake outputs for:

- dataset preparation
- training launch
- model evaluation

Later this adapter can be replaced with a real PyTorch pipeline, GPU scheduling, artifact upload, and richer evaluation logic without changing the workflow contract or the HTTP API surface of the training service.
