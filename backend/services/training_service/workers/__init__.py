"""Worker entrypoints for the training service."""

from services.training_service.workers.training_worker import run_training_worker

__all__ = ["run_training_worker"]
