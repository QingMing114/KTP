"""Temporal worker bootstrap for the training workflow."""

from __future__ import annotations

import logging

from temporalio.client import Client as TemporalClient
from temporalio.worker import Worker

from services.training_service.activities import (
    evaluate_model_activity,
    launch_training_activity,
    prepare_dataset_activity,
    register_model_activity,
)
from services.training_service.config import get_training_service_config
from services.training_service.workflows import TrainingWorkflow

logger = logging.getLogger(__name__)


async def run_training_worker() -> None:
    """Run the Temporal worker for the training workflow and activities."""
    config = get_training_service_config()
    logger.info(
        "training_worker_starting | temporal_server=%s | task_queue=%s",
        config.temporal_server_url,
        config.temporal_task_queue,
    )
    client = await TemporalClient.connect(
        config.temporal_server_url,
        namespace=config.temporal_namespace,
    )
    worker = Worker(
        client,
        task_queue=config.temporal_task_queue,
        workflows=[TrainingWorkflow],
        activities=[
            prepare_dataset_activity,
            launch_training_activity,
            evaluate_model_activity,
            register_model_activity,
        ],
    )
    logger.info("training_worker_started | task_queue=%s", config.temporal_task_queue)
    await worker.run()
