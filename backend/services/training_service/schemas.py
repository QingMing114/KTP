"""Schemas for the Temporal training workflow."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from shared.schemas.common import BaseSchema


class TrainingRequest(BaseSchema):
    """Input payload for starting a training workflow."""

    request_id: str = Field(..., description="Request identifier from the orchestrator.")
    region: str = Field(..., description="Target region for the training request.")
    crop_type: str = Field(..., description="Target crop type.")
    task_type: str = Field(..., description="Task type to train.")
    dataset_uri: str = Field(..., description="Raw dataset location.")
    base_model_name: str | None = Field(
        default=None,
        description="Optional base model to fine-tune from.",
    )
    output_model_name: str = Field(..., description="Name of the output model.")
    output_model_version: str = Field(..., description="Version for the output model.")
    trigger_reason: str = Field(..., description="Why training was triggered.")


class DatasetPreparationResult(BaseSchema):
    """Result of the dataset preparation activity."""

    prepared_dataset_uri: str = Field(..., description="Prepared dataset URI.")
    sample_count: int = Field(..., description="Number of prepared samples.")
    status: str = Field(..., description="Dataset preparation status.")


class TrainingRunResult(BaseSchema):
    """Result of the training launch activity."""

    run_id: str = Field(..., description="Training run identifier.")
    artifact_uri: str = Field(..., description="Model artifact URI.")
    train_status: str = Field(..., description="Training status.")
    epochs: int = Field(..., description="Epoch count used in training.")
    framework: str = Field(..., description="Training framework identifier.")


class EvaluationResult(BaseSchema):
    """Result of the evaluation activity."""

    eval_status: str = Field(..., description="Evaluation status.")
    metrics: dict[str, float] = Field(
        default_factory=dict,
        description="Evaluation metrics payload.",
    )
    passed: bool = Field(..., description="Whether the model passed evaluation.")


class ModelRegistrationResult(BaseSchema):
    """Result of registering the trained model into the registry."""

    registered: bool = Field(..., description="Whether registration succeeded.")
    model_id: int | None = Field(default=None, description="Registry model identifier.")
    model_version: str = Field(..., description="Registered model version.")
    status: str = Field(..., description="Registration or final model status.")


class TrainingWorkflowResult(BaseSchema):
    """Final workflow result returned by the Temporal workflow."""

    workflow_id: str = Field(..., description="Temporal workflow identifier.")
    request_id: str = Field(..., description="Original request identifier.")
    region: str = Field(..., description="Target region.")
    crop_type: str = Field(..., description="Target crop type.")
    task_type: str = Field(..., description="Target task type.")
    success: bool = Field(..., description="Whether the workflow completed successfully.")
    training_triggered: bool = Field(..., description="Whether training was started.")
    artifact_uri: str | None = Field(default=None, description="Produced artifact URI.")
    metrics: dict[str, float] = Field(
        default_factory=dict,
        description="Evaluation metrics from the workflow.",
    )
    registration_result: ModelRegistrationResult = Field(
        ...,
        description="Result of registering the model.",
    )
    message: str = Field(..., description="High-level workflow outcome message.")


class TrainingWorkflowStartResponse(BaseSchema):
    """Response returned when a Temporal workflow is started."""

    workflow_id: str = Field(..., description="Temporal workflow identifier.")
    run_id: str | None = Field(default=None, description="Temporal run identifier.")
    request_id: str = Field(..., description="Original request identifier.")
    task_queue: str = Field(..., description="Temporal task queue used.")
    status: str = Field(..., description="Workflow start status.")


class RegisterModelActivityInput(BaseSchema):
    """Input payload for the register-model activity."""

    request: TrainingRequest = Field(..., description="Original training request.")
    training_result: TrainingRunResult = Field(
        ...,
        description="Training run result to register.",
    )
    evaluation_result: EvaluationResult = Field(
        ...,
        description="Evaluation outcome for the trained model.",
    )


class ActivityFailureResult(BaseSchema):
    """Structured failure payload for internal activity handling."""

    stage: str = Field(..., description="Activity stage that failed.")
    message: str = Field(..., description="Failure reason.")
    details: dict[str, Any] = Field(default_factory=dict, description="Extra context.")
