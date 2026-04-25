"""Validation for the extended bounded chat-runtime evaluation case file."""

from __future__ import annotations

from pathlib import Path

from shared.chat_runtime_eval import load_eval_cases


def test_extended_eval_case_file_contains_wider_coverage() -> None:
    cases = load_eval_cases(Path("tests/data/chat_runtime_eval_cases_extended.json"))

    categories = {case.category for case in cases}
    assert len(cases) >= 12
    assert {
        "routing",
        "workflow",
        "explicit_mode",
        "rag",
        "normalization",
        "task_type",
    }.issubset(categories)
