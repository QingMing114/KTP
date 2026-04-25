"""Start the Temporal worker for the training workflow."""

from __future__ import annotations

import asyncio

from services.training_service.workers.training_worker import run_training_worker


def main() -> None:
    asyncio.run(run_training_worker())


if __name__ == "__main__":
    main()
