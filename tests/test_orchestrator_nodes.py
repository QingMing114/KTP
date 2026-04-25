"""Unit tests for orchestrator nodes that consume gateway agent plans."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

import pytest


_service_registry_stub = types.ModuleType("apps.orchestrator.service_registry")
_service_registry_stub.get_orchestrator_planner_agent = lambda: None
_service_registry_stub.get_model_registry_lookup_client = lambda: None
sys.modules.setdefault("apps.orchestrator.service_registry", _service_registry_stub)


def _load_module(module_name: str, relative_path: str):
    module_path = Path(__file__).resolve().parents[2] / "backend" / relative_path
    if not module_path.exists():
        pytest.skip(f"Module file not found: {module_path}", allow_module_level=True)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_parse_request_module = _load_module(
    "test_parse_request_node_module",
    "apps/orchestrator/graph/nodes/parse_request.py",
)
_check_model_registry_module = _load_module(
    "test_check_model_registry_node_module",
    "apps/orchestrator/graph/nodes/check_model_registry.py",
)

parse_request_node = _parse_request_module.parse_request_node
route_after_model_check = _check_model_registry_module.route_after_model_check


class _StubPlan:
    def __init__(self) -> None:
        self.task_type = "crop_health_detection"
        self.region = "henan"
        self.crop_type = "wheat"
        self.need_training = False
        self.need_rag = False
        self.need_report = True
        self.need_confidence = True
        self.reasoning_summary = "stub planner result"

    def model_dump(self) -> dict[str, object]:
        return {
            "task_type": self.task_type,
            "region": self.region,
            "crop_type": self.crop_type,
            "need_training": self.need_training,
            "need_rag": self.need_rag,
            "need_report": self.need_report,
            "need_confidence": self.need_confidence,
            "reasoning_summary": self.reasoning_summary,
        }


class _StubPlannerAgent:
    def create_plan(self, *, request_id: str, user_query: str) -> _StubPlan:
        return _StubPlan()


def test_parse_request_node_prefers_gateway_agent_plan(monkeypatch) -> None:
    monkeypatch.setattr(_parse_request_module, "get_orchestrator_planner_agent", lambda: _StubPlannerAgent())

    result = parse_request_node(
        {
            "request_id": "req-node-001",
            "user_query": "请分析河北省小麦病害情况，并生成报告和置信度说明。",
            "extra_params": {
                "agent_plan": {
                    "task_type": "crop_health_detection",
                    "region": "hebei",
                    "crop_type": "wheat",
                    "need_training": False,
                    "need_rag": True,
                    "need_report": True,
                    "need_confidence": True,
                }
            },
            "stage_timings": [],
        }
    )

    assert result["task_type"] == "crop_health_detection"
    assert result["region"] == "hebei"
    assert result["crop_type"] == "wheat"
    assert result["need_rag"] is True
    assert result["planner_result"]["decision_source"] == "gateway_agent"


def test_route_after_model_check_prefers_explicit_training_request() -> None:
    branch = route_after_model_check(
        {
            "model_exists": True,
            "need_training": True,
        }
    )

    assert branch == "trigger_training"
