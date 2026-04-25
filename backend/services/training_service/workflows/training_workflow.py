"""Temporal workflow coordinating the durable training flow."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from services.training_service.schemas import (
        DatasetPreparationResult,
        EvaluationResult,
        ModelRegistrationResult,
        RegisterModelActivityInput,
        TrainingRequest,
        TrainingRunResult,
        TrainingWorkflowResult,
    )


@workflow.defn(name="training-workflow")
class TrainingWorkflow:
    """Durable training workflow for model preparation and registration."""

    @workflow.run
    async def run(self, request_payload: dict[str, Any]) -> dict[str, Any]:
        """Execute the training workflow and return a structured result."""
        request = TrainingRequest.model_validate(request_payload)
        workflow_id = workflow.info().workflow_id
        workflow.logger.info(
            "training_workflow_started | workflow_id=%s | request_id=%s",
            workflow_id,
            request.request_id,
        )

        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=1),
            backoff_coefficient=2.0,
            maximum_attempts=3,
        )

        training_result: TrainingRunResult | None = None
        evaluation_result: EvaluationResult | None = None
        registration_result = ModelRegistrationResult(
            registered=False,
            model_id=None,
            model_version=request.output_model_version,
            status="not_started",
        )

        try:
            dataset_payload = await workflow.execute_activity(
                "prepare_dataset_activity",
                request.model_dump(),
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=retry_policy,
            )
            dataset_result = DatasetPreparationResult.model_validate(dataset_payload)

            training_payload = await workflow.execute_activity(
                "launch_training_activity",
                {
                    "request": request.model_dump(),
                    "dataset_result": dataset_result.model_dump(),
                },
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=retry_policy,
            )
            training_result = TrainingRunResult.model_validate(training_payload)

            evaluation_payload = await workflow.execute_activity(
                "evaluate_model_activity",
                {
                    "request": request.model_dump(),
                    "training_result": training_result.model_dump(),
                },
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=retry_policy,
            )
            evaluation_result = EvaluationResult.model_validate(evaluation_payload)

            registration_payload = await workflow.execute_activity(
                "register_model_activity",
                RegisterModelActivityInput(
                    request=request,
                    training_result=training_result,
                    evaluation_result=evaluation_result,
                ).model_dump(),
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=retry_policy,
            )
            registration_result = ModelRegistrationResult.model_validate(registration_payload)

            success = evaluation_result.passed and registration_result.registered
            message = (
                "Training workflow completed successfully."
                if success
                else "Training completed but model registration was skipped or failed."
            )
            result = TrainingWorkflowResult(
                workflow_id=workflow_id,
                request_id=request.request_id,
                region=request.region,
                crop_type=request.crop_type,
                task_type=request.task_type,
                success=success,
                training_triggered=True,
                artifact_uri=training_result.artifact_uri,
                metrics=evaluation_result.metrics,
                registration_result=registration_result,
                message=message,
            )
            workflow.logger.info(
                "training_workflow_succeeded | workflow_id=%s | request_id=%s | success=%s",
                workflow_id,
                request.request_id,
                success,
            )
            return result.model_dump()
        except Exception as exc:
            workflow.logger.exception(
                "training_workflow_failed | workflow_id=%s | request_id=%s",
                workflow_id,
                request.request_id,
            )
            result = TrainingWorkflowResult(
                workflow_id=workflow_id,
                request_id=request.request_id,
                region=request.region,
                crop_type=request.crop_type,
                task_type=request.task_type,
                success=False,
                training_triggered=True,
                artifact_uri=training_result.artifact_uri if training_result else None,
                metrics=evaluation_result.metrics if evaluation_result else {},
                registration_result=registration_result,
                message=f"Training workflow failed: {exc}",
            )
            return result.model_dump()
