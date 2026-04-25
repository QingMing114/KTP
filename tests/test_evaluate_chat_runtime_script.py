"""Smoke tests for the bounded chat-runtime evaluation script."""

from __future__ import annotations

import json

from scripts import evaluate_chat_runtime as eval_script
from shared.chat_runtime_eval import ChatRuntimeEvalCase


def test_evaluate_chat_runtime_main_reports_success(monkeypatch, capsys) -> None:
    cases = [
        ChatRuntimeEvalCase(
            name="case-1",
            message="NDVI 和 EVI 有什么区别？",
            mode="agent",
            expected_mode="agent",
            expected_success=True,
        )
    ]
    monkeypatch.setattr(eval_script, "load_eval_cases", lambda _path: cases)
    monkeypatch.setattr(
        eval_script,
        "_post_chat",
        lambda **_kwargs: {
            "mode": "agent",
            "success": True,
            "route_reason": "explicit:agent:chat_graph:direct_answer",
            "answer": "这是直接回答。",
        },
    )

    exit_code = eval_script.main(["--cases", "unused.json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["passed"] == 1
    assert payload["failed"] == 0


def test_evaluate_chat_runtime_main_reports_failure(monkeypatch, capsys) -> None:
    cases = [
        ChatRuntimeEvalCase(
            name="case-1",
            message="请分析河北省小麦病害情况，并生成报告和置信度说明。",
            mode="agent",
            expected_mode="workflow",
            expected_route_reason_contains=["chat_graph:workflow"],
        )
    ]
    monkeypatch.setattr(eval_script, "load_eval_cases", lambda _path: cases)
    monkeypatch.setattr(
        eval_script,
        "_post_chat",
        lambda **_kwargs: {
            "mode": "agent",
            "success": True,
            "route_reason": "explicit:agent:chat_graph:direct_answer",
            "answer": "这是直接回答。",
        },
    )

    exit_code = eval_script.main(["--cases", "unused.json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert payload["passed"] == 0
    assert payload["failed"] == 1
