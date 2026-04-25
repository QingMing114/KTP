"""Smoke tests for the final chat-runtime acceptance runner."""

from __future__ import annotations

from scripts import run_agent_runtime_acceptance as acceptance_script


def test_run_agent_runtime_acceptance_main_runs_expected_commands(monkeypatch) -> None:
    calls: list[list[str]] = []

    def _capture(command: list[str], *, cwd) -> None:
        calls.append(command)

    monkeypatch.setattr(acceptance_script, "_run_command", _capture)

    exit_code = acceptance_script.main(["--eval-cases", "tests/data/chat_runtime_eval_cases.json"])

    assert exit_code == 0
    assert len(calls) == 2
    assert calls[0][0:3] == [acceptance_script.sys.executable, "-m", "pytest"]
    assert calls[1][0:2] == [acceptance_script.sys.executable, "scripts/evaluate_chat_runtime.py"]


def test_run_agent_runtime_acceptance_main_can_skip_pytest(monkeypatch) -> None:
    calls: list[list[str]] = []

    def _capture(command: list[str], *, cwd) -> None:
        calls.append(command)

    monkeypatch.setattr(acceptance_script, "_run_command", _capture)

    exit_code = acceptance_script.main(
        ["--skip-pytest", "--eval-cases", "tests/data/chat_runtime_eval_cases.json"]
    )

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0][0:2] == [acceptance_script.sys.executable, "scripts/evaluate_chat_runtime.py"]
