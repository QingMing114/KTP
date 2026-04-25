"""Unit tests for bounded chat-runtime regression helpers."""

from __future__ import annotations

from pathlib import Path

from shared.chat_runtime_eval import (
    evaluate_chat_response,
    load_eval_cases,
    summarize_eval_results,
)


def test_load_eval_cases_reads_json_list() -> None:
    cases = load_eval_cases(Path("tests/data/chat_runtime_eval_cases.json"))

    assert len(cases) >= 2
    assert cases[0].name == "workflow_report_case"


def test_evaluate_chat_response_detects_mismatch() -> None:
    case = load_eval_cases(Path("tests/data/chat_runtime_eval_cases.json"))[0]

    result = evaluate_chat_response(
        case,
        {
            "mode": "agent",
            "success": True,
            "route_reason": "explicit:agent:chat_graph:direct_answer",
            "answer": "直接回答。",
        },
    )

    assert result.passed is False
    assert any("expected mode" in item for item in result.mismatches) or any(
        "route_reason missing" in item for item in result.mismatches
    )


def test_summarize_eval_results_counts_failures() -> None:
    cases = load_eval_cases(Path("tests/data/chat_runtime_eval_cases.json"))
    results = [
        evaluate_chat_response(
            cases[0],
            {
                "mode": "workflow",
                "success": True,
                "route_reason": "explicit:agent:chat_graph:workflow",
                "answer": "已生成报告。",
            },
        ),
        evaluate_chat_response(
            cases[1],
            {
                "mode": "agent",
                "success": False,
                "route_reason": "explicit:qa",
                "answer": "失败。",
            },
        ),
    ]

    summary = summarize_eval_results(results)

    assert summary.total == 2
    assert summary.passed == 1
    assert summary.failed == 1
