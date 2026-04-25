"""Mock training adapter reserved for replacement with a real trainer."""

from __future__ import annotations

import logging

from services.training_service.schemas import (
    DatasetPreparationResult,
    EvaluationResult,
    TrainingRequest,
    TrainingRunResult,
)

logger = logging.getLogger(__name__)


class TrainerAdapter:
    """Mock adapter encapsulating dataset prep, training, and evaluation."""

    def _should_fail(self, request: TrainingRequest, stage: str) -> bool:
        return request.trigger_reason.strip().lower() == f"fail_{stage}"

    async def prepare_dataset(
        self,
        request: TrainingRequest,
    ) -> DatasetPreparationResult:
        """Prepare a dataset for training."""
        logger.info("trainer_prepare_dataset_started | request_id=%s", request.request_id)
        if self._should_fail(request, "prepare_dataset"):
            raise RuntimeError("mock dataset preparation failure requested")

        result = DatasetPreparationResult(
            prepared_dataset_uri=f"{request.dataset_uri.rstrip('/')}/prepared/{request.request_id}",
            sample_count=2048,
            status="prepared",
        )
        logger.info("trainer_prepare_dataset_succeeded | request_id=%s", request.request_id)
        return result

    async def launch_training(
        self,
        request: TrainingRequest,
        dataset_result: DatasetPreparationResult,
    ) -> TrainingRunResult:
        """Launch a mock training run."""
        logger.info("trainer_launch_training_started | request_id=%s", request.request_id)
        if self._should_fail(request, "launch_training"):
            raise RuntimeError("mock training launch failure requested")

        result = TrainingRunResult(
            run_id=f"train-{request.request_id}",
            artifact_uri=(
                f"mock://artifacts/{request.region}/{request.crop_type}/"
                f"{request.output_model_name}/{request.output_model_version}/model.pt"
            ),
            train_status="completed",
            epochs=25,
            framework="mock-pytorch",
        )
        logger.info(
            "trainer_launch_training_succeeded | request_id=%s | dataset_uri=%s",
            request.request_id,
            dataset_result.prepared_dataset_uri,
        )
        return result

    async def evaluate_model(
        self,
        request: TrainingRequest,
        training_result: TrainingRunResult,
    ) -> EvaluationResult:
        """Evaluate a mock training artifact."""
        logger.info("trainer_evaluate_model_started | request_id=%s", request.request_id)
        if self._should_fail(request, "evaluate_model"):
            raise RuntimeError("mock evaluation failure requested")

        metrics = {
            "miou": 0.84,
            "f1": 0.88,
            "precision": 0.87,
            "recall": 0.89,
        }
        passed = request.trigger_reason.strip().lower() != "evaluation_below_threshold"
        result = EvaluationResult(
            eval_status="completed",
            metrics=metrics,
            passed=passed,
        )
        logger.info(
            "trainer_evaluate_model_succeeded | request_id=%s | run_id=%s | passed=%s",
            request.request_id,
            training_result.run_id,
            passed,
        )
        return result
