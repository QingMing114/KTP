"""Run the bounded chat-runtime acceptance sequence."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


_TEST_ARGS = [
    "tests/test_tool_registry.py",
    "tests/test_chat_runtime_scaffold.py",
    "tests/test_chat_runtime_phase2.py",
    "tests/test_chat_runtime_adapter.py",
    "tests/test_orchestrator_nodes.py",
    "tests/test_agent_llm_provider.py",
    "tests/test_planner_agent.py",
    "tests/test_chat_service.py",
    "tests/test_chat_runtime_eval.py",
    "tests/test_evaluate_chat_runtime_script.py",
    "-q",
]


def main(argv: list[str] | None = None) -> int:
    """Run pytest plus the bounded in-process chat-runtime evaluation."""
    parser = argparse.ArgumentParser(
        description="Run the final bounded chat-runtime acceptance sequence.",
    )
    parser.add_argument(
        "--skip-pytest",
        action="store_true",
        help="Skip the pytest phase and run only the evaluation script.",
    )
    parser.add_argument(
        "--eval-cases",
        default="tests/data/chat_runtime_eval_cases.json",
        help="Path to the chat-runtime evaluation case file.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    if not args.skip_pytest:
        _run_command([sys.executable, "-m", "pytest", *_TEST_ARGS], cwd=repo_root)

    _run_command(
        [
            sys.executable,
            "scripts/evaluate_chat_runtime.py",
            "--cases",
            args.eval_cases,
        ],
        cwd=repo_root,
    )
    return 0


def _run_command(command: list[str], *, cwd: Path) -> None:
    subprocess.run(command, cwd=str(cwd), check=True)


if __name__ == "__main__":
    raise SystemExit(main())
