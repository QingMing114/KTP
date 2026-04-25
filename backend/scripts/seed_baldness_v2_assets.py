"""Seed the current V2 environment with baldness model and knowledge assets."""

from __future__ import annotations

import argparse

from apps.orchestrator.config import get_orchestrator_runtime_config
from scripts.demo_baldness_real_flow import seed_baldness_real_assets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed the active registry/RAG environment with the migrated baldness RF assets.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Explicit registry database URL. Defaults to the current orchestrator runtime database.",
    )
    parser.add_argument(
        "--model-path",
        default="/home/D/liumeng/bantushibie/test/api_storage/models/rf_model.pkl",
        help="Local RF model artifact path registered as artifact_uri.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    runtime_config = get_orchestrator_runtime_config()
    database_url = args.database_url or runtime_config.database_url
    seed_baldness_real_assets(
        database_url=database_url,
        artifact_uri=args.model_path,
    )
    print(f"Seeded baldness V2 assets into {database_url}")
    print(f"Registered artifact_uri={args.model_path}")
    print("Lookup key: region=scalp crop_type=hair task_type=baldness_detection")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
