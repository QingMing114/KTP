"""Schema tests for the training workflow layer."""

from __future__ import annotations

from services.training_service.schemas import (
    DatasetPreparationResult,
    EvaluationResult,
    ModelRegistrationResult,
    TrainingRequest,
    TrainingRunResult,
    TrainingWorkflowResult,
)


def test_training_workflow_schema_instantiation() -> None:
    request = TrainingRequest(
        request_id="req-training-schema",
        region="henan",
        crop_type="wheat",
        task_type="baldness_detection",
        dataset_uri="mock://datasets/raw",
        base_model_name="unet_base",
        output_model_name="unet_rs_baldness",
        output_model_version="v4",
        trigger_reason="model_missing",
    )
    dataset_result = DatasetPreparationResult(
        prepared_dataset_uri="mock://datasets/prepared",
        sample_count=2048,
        status="prepared",
    )
    training_result = TrainingRunResult(
        run_id="train-001",
        artifact_uri="mock://artifacts/model.pt",
        train_status="completed",
        epochs=25,
        framework="mock-pytorch",
    )
    evaluation_result = EvaluationResult(
        eval_status="completed",
        metrics={"miou": 0.84, "f1": 0.88},
        passed=True,
    )
    registration_result = ModelRegistrationResult(
        registered=True,
        model_id=101,
        model_version="v4",
        status="ready",
    )
    workflow_result = TrainingWorkflowResult(
        workflow_id="training-req-training-schema-henan-wheat-v4",
        request_id=request.request_id,
        region=request.region,
        crop_type=request.crop_type,
        task_type=request.task_type,
        success=True,
        training_triggered=True,
        artifact_uri=training_result.artifact_uri,
        metrics=evaluation_result.metrics,
        registration_result=registration_result,
        message="Training workflow completed successfully.",
    )

    assert dataset_result.status == "prepared"
    assert training_result.train_status == "completed"
    assert evaluation_result.passed is True
    assert workflow_result.registration_result.model_id == 101
    assert set(workflow_result.model_dump().keys()) == {
        "workflow_id",
        "request_id",
        "region",
        "crop_type",
        "task_type",
        "success",
        "training_triggered",
        "artifact_uri",
        "metrics",
        "registration_result",
        "message",
    }
