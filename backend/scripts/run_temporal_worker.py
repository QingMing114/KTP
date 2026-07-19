"""Start the Temporal worker for the training workflow."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.training_service.workers.training_worker import run_training_worker


def main() -> None:
    asyncio.run(run_training_worker())


if __name__ == "__main__":
    main()
