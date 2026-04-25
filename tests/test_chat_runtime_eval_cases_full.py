"""Validation for the broader bounded chat-runtime evaluation case file."""

from __future__ import annotations

from pathlib import Path

from shared.chat_runtime_eval import load_eval_cases


def test_full_eval_case_file_contains_broad_categories() -> None:
    cases = load_eval_cases(Path("tests/data/chat_runtime_eval_cases_full.json"))

    categories = {case.category for case in cases}
    assert len(cases) >= 8
    assert {"routing", "workflow", "explicit_mode", "rag", "normalization"}.issubset(categories)
