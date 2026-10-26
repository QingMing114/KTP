"""The LLM judgement layers regional phenology on top of the KDD2020 scores."""

from types import SimpleNamespace

import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_origin

from runtime.apsim_example import ApsimExampleError, select_example
from infra.llm.provider import AgentLLMError
from runtime.artifact_store import ArtifactStore
from runtime.crop_decision import (
    CropDecisionOutput, decide_crop, decision_input_hash, needs_score_gate, resolve_crop_class,
)
from runtime.simple_yield import SimpleYieldError
from runtime.simple_yield_runner import resolve_simple_yield_crop
from runtime.workflow_reports import register_crop_report
from runtime.yield_input_assessment import assess_yield_inputs
from schemas.analysis_workflow import CreateAnalysisWorkflowRequest
from test_analysis_workflow_api import AOI, SNAPSHOT, _app, _wait_for_terminal

MODEL_RESULT = {
    "predicted_class": {"class_id": 3, "name": "Spring Wheat", "name_zh": "春小麦", "score": 0.22},
    "class_scores": [
        {"class_id": 0, "name_zh": "玉米", "score": 0.29},
        {"class_id": 1, "name_zh": "棉花", "score": 0.09},
        {"class_id": 2, "name_zh": "大豆", "score": 0.12},
        {"class_id": 3, "name_zh": "春小麦", "score": 0.22},
        {"class_id": 4, "name_zh": "冬小麦", "score": 0.23},
        {"class_id": 5, "name_zh": "大麦", "score": 0.05},
    ],
    "model": {"name": "KDD2020 purely spatial VGG16", "sha256": "digest"},
    "warnings": ["跨传感器结果未经实地验证。"],
}


class AnswerProvider:
    def __init__(self, *, answer=None, error=None):
        self.answer = answer
        self.error = error
        self.calls: list[str] = []

    def generate_structured(self, *, system_prompt, user_prompt, response_model):
        self.calls.append(user_prompt)
        if self.error is not None:
            raise self.error
        assert response_model is CropDecisionOutput
        if isinstance(self.answer, dict):
            return self.answer
        return self.answer


def _decide(provider, observed_at="2026-07-12T03:20:00Z"):
    return decide_crop(
        provider, model_result=MODEL_RESULT, observed_at=observed_at,
        farm_id="farm-zouping", geometry=AOI["geometry"], area_hectares=2.48,
    )


def test_llm_decision_keeps_model_evidence_and_records_rationale():
    provider = AnswerProvider(answer=CropDecisionOutput(
        final_class_id=0, confidence="medium", phenology="冬小麦已收获，夏玉米苗期",
        rationale="7月山东邹平，冬小麦已收、夏玉米苗期；模型最高为玉米29%，与物候一致。",
        excluded_classes=[{"class_id": 4, "reason": "7月冬小麦已收获"}],
    ))
    decision = _decide(provider)
    assert decision["source"] == "llm"
    assert decision["final_class_id"] == 0 and decision["final_name_zh"] == "玉米"
    assert decision["model_prediction"]["class_id"] == 3  # model top-1 is untouched
    # The test AOI sits in Qinghai while a Shandong farm stays selected.
    assert decision["location"]["farm_mismatch"] is True
    assert decision["location"]["label"] == "青海省"
    assert decision["location"]["farm_label"] == "山东 · 邹平"
    assert decision["location"]["source"] == "admin_boundary"
    assert decision["rationale"].startswith("7月山东邹平")
    assert decision["excluded_classes"][0]["class_id"] == 4
    assert decision["input_hash"].startswith("sha256:")
    assert needs_score_gate(decision) is False
    assert "青海省" in provider.calls[0]
    assert "AOI 不在所选农场范围内" in provider.calls[0]


def test_location_inside_the_selected_farm_keeps_its_preset_label():
    hardcoded = {
        "type": "Polygon",
        "coordinates": [[[117.7960098, 36.9507297], [117.7958331, 36.9480382],
                         [117.8039052, 36.9478264], [117.8040377, 36.9505179], [117.7960098, 36.9507297]]],
    }
    decision = decide_crop(
        AnswerProvider(answer=CropDecisionOutput(final_class_id=0, rationale="物候一致")),
        model_result=MODEL_RESULT, observed_at="2026-07-12T03:20:00Z",
        farm_id="farm-zouping", geometry=hardcoded, area_hectares=21.4,
    )
    assert decision["location"]["farm_mismatch"] is False
    assert decision["location"]["label"] == "山东 · 邹平"
    assert decision["location"]["province"] == "山东省"
    assert decision["location"]["source"] == "farm_preset+admin_boundary"


def test_llm_failure_falls_back_to_model_with_legacy_gate():
    provider = AnswerProvider(error=RuntimeError("model outage"))
    decision = _decide(provider)
    assert decision["source"] == "model_fallback"
    assert decision["final_class_id"] == 3 and decision["final_name_zh"] == "春小麦"
    assert "model outage" in decision["fallback_reason"]
    detail = decision["fallback_detail"]
    assert detail["stage"] == "llm_call" and detail["error_type"] == "RuntimeError"
    assert detail["provider"] == "AnswerProvider" and detail["message"] == "model outage"
    assert detail["attempts"] == 1
    assert len(provider.calls) == 1  # hard failures are not retried
    assert needs_score_gate(decision) is True


def test_invalid_llm_output_retries_once_then_falls_back():
    provider = AnswerProvider(answer={"final_class_id": 9, "rationale": "越界类别"})
    decision = _decide(provider)
    assert decision["source"] == "model_fallback"
    assert decision["final_class_id"] == 3
    assert decision["fallback_detail"]["stage"] == "schema_validation"
    assert decision["fallback_detail"]["attempts"] == 2
    assert len(provider.calls) == 2


def test_schema_mismatch_is_retried_with_a_corrective_prompt():
    class RecoveringProvider(AnswerProvider):
        def generate_structured(self, *, system_prompt, user_prompt, response_model):
            self.calls.append(user_prompt)
            if len(self.calls) == 1:
                raise AgentLLMError(
                    "Upstream LLM returned a structured response that did not match the planner contract",
                    category="schema_mismatch", status_code=200,
                )
            return CropDecisionOutput(final_class_id=0, rationale="第二次按完整字段返回。")

    provider = RecoveringProvider()
    decision = _decide(provider)
    assert decision["source"] == "llm"
    assert decision["llm_attempts"] == 2
    assert len(provider.calls) == 2


def test_excluded_classes_without_reason_are_tolerated():
    """The observed Qwen answer omitted per-class reasons; that must not sink the judgement."""
    answer = {
        "final_class_id": 0, "confidence": "low",
        "rationale": "9月邹平为夏玉米成熟期。",
        "excluded_classes": [{"class_id": 1, "name_zh": "棉花"}, {"class_id": 2, "name_zh": "大豆"}],
    }
    decision = _decide(AnswerProvider(answer=answer))
    assert decision["source"] == "llm"
    assert decision["final_class_id"] == 0
    assert [item["class_id"] for item in decision["excluded_classes"]] == [1, 2]
    assert all(item["reason"] == "" for item in decision["excluded_classes"])


def test_missing_rationale_falls_back_to_phenology_text():
    decision = _decide(AnswerProvider(answer={"final_class_id": 0, "confidence": "low", "phenology": "夏玉米成熟期"}))
    assert decision["source"] == "llm"
    assert decision["rationale"] == "夏玉米成熟期"


def test_missing_provider_falls_back():
    decision = _decide(None)
    assert decision["source"] == "model_fallback"
    assert decision["fallback_reason"] == "大模型未配置"
    assert decision["fallback_detail"]["stage"] == "provider_lookup"


def test_decision_input_hash_is_stable_and_reacts_to_date():
    location = {"label": "山东 · 邹平", "admin_hint": "山东 · 邹平", "lat": 36.95, "lon": 117.8}
    first = decision_input_hash(MODEL_RESULT, "2026-07-12", location)
    assert first == decision_input_hash(MODEL_RESULT, "2026-07-12", location)
    assert first != decision_input_hash(MODEL_RESULT, "2026-08-12", location)


def test_resolve_crop_class_reads_legacy_results():
    class_id, decision = resolve_crop_class(MODEL_RESULT)
    assert class_id == 3 and decision is None
    upgraded = {**MODEL_RESULT, "crop_decision": {"final_class_id": 0, "source": "llm"}}
    assert resolve_crop_class(upgraded) == (0, upgraded["crop_decision"])
    assert resolve_crop_class({}) == (None, None)


def _workflow(tmp_path, *, decision=None, class_id=3, score=0.22):
    app = _app(tmp_path / "crop-decision.sqlite3")
    store = app.state.analysis_workflow_store
    workflow = store.create(CreateAnalysisWorkflowRequest.model_validate({
        "aoi": AOI, "imagery_item_id": "S2-workflow", "imagery_snapshot": SNAPSHOT,
        "requested_task_ids": ["yield_simple"], "start_immediately": False,
    }), owner_id="anonymous")
    result = {**MODEL_RESULT, "predicted_class": {"class_id": class_id, "score": score}}
    if decision is not None:
        result["crop_decision"] = decision
    store.update_step(workflow.workflow_id, "crop", owner_id="anonymous",
                      status="completed", result=result)
    return app, store, store.get(workflow.workflow_id, owner_id="anonymous")


def test_simple_yield_uses_llm_decision_over_model_top1(tmp_path):
    _, _, workflow = _workflow(tmp_path, decision={
        "final_class_id": 4, "final_name_zh": "冬小麦", "source": "llm", "rationale": "物候一致",
    })
    assert resolve_simple_yield_crop(workflow) == "winter_wheat"


def test_simple_yield_uses_llm_decision_even_with_low_model_score(tmp_path):
    _, _, workflow = _workflow(tmp_path, decision={
        "final_class_id": 0, "final_name_zh": "玉米", "source": "llm", "rationale": "物候一致",
    }, score=0.22)
    assert resolve_simple_yield_crop(workflow) == "maize"


def test_simple_yield_reports_unsupported_decided_crop(tmp_path):
    _, _, workflow = _workflow(tmp_path, decision={
        "final_class_id": 2, "final_name_zh": "大豆", "source": "llm", "rationale": "物候一致",
    })
    with pytest.raises(SimpleYieldError) as error:
        resolve_simple_yield_crop(workflow)
    assert error.value.code == "crop_class_unsupported"
    assert "大豆" in str(error.value)


def test_simple_yield_keeps_confirmation_gate_for_model_fallback(tmp_path):
    _, _, workflow = _workflow(tmp_path, decision={
        "final_class_id": 0, "final_name_zh": "玉米", "source": "model_fallback", "rationale": "回退",
    }, score=0.22)
    with pytest.raises(SimpleYieldError) as error:
        resolve_simple_yield_crop(workflow)
    assert error.value.code == "crop_confirmation_required"


def test_yield_input_assessment_skips_legacy_gate_for_llm_decision(tmp_path):
    app, store, workflow = _workflow(tmp_path, decision={
        "final_class_id": 0, "final_name_zh": "玉米", "source": "llm", "rationale": "物候一致",
    }, score=0.22)
    assessment = assess_yield_inputs(workflow)
    codes = {issue.code for issue in assessment.issues}
    assert "crop_confirmation_required" not in codes
    assert "crop_model_unsupported" not in codes
    assert assessment.crop_source == "llm"


def test_apsim_example_uses_llm_decision(tmp_path):
    _, _, workflow = _workflow(tmp_path, decision={
        "final_class_id": 2, "final_name_zh": "大豆", "source": "llm", "rationale": "物候一致",
    })
    (crop, model, label), _ = select_example(workflow)
    assert (crop, label) == ("soybean", "大豆")


def test_apsim_example_rejects_unsupported_decided_crop(tmp_path):
    _, _, workflow = _workflow(tmp_path, decision={
        "final_class_id": 1, "final_name_zh": "棉花", "source": "llm", "rationale": "物候一致",
    })
    with pytest.raises(ApsimExampleError, match="棉花"):
        select_example(workflow)


def test_crop_report_shows_decision_rationale(tmp_path):
    artifacts = ArtifactStore(db_path=str(tmp_path / "reports.sqlite3"))
    try:
        result = {**MODEL_RESULT, "crop_decision": {
            "final_class_id": 0, "final_name_zh": "玉米", "source": "llm",
            "rationale": "7月山东邹平，冬小麦已收、夏玉米苗期。",
            "phenology": "夏玉米苗期", "observed_at": "2026-07-12T03:20:00Z",
            "location": {"label": "山东 · 邹平"},
        }}
        report = register_crop_report(
            artifacts, run_id="crop-decision", output_dir=tmp_path / "crop",
            imagery_item_id="S2-workflow", observed_at="2026-07-12T03:20:00Z",
            area_hectares=2.48, result=result,
        )
        text = open(artifacts.get(report["report_artifact_id"]).content_path, encoding="utf-8").read()
        assert "判定依据" in text
        assert "7月山东邹平" in text
        assert "大模型结合地点与时序判定" in text
        assert "春小麦" in text  # raw model top-1 stays visible as evidence
    finally:
        artifacts.close()


def test_auto_mode_applies_llm_decision_without_pausing(tmp_path, monkeypatch):
    """Outside professional mode the judgement is used directly; nothing waits."""
    import runtime.analysis_workflow_runner as runner

    def fake_read(*, output_path, progress_callback, **_kwargs):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(output_path, "w", driver="GTiff", width=4, height=4, count=5,
                           dtype="float32", crs="EPSG:4326",
                           transform=from_origin(100, 38.01, 0.0025, 0.0025)) as dataset:
            dataset.write(np.full((5, 4, 4), 0.2, dtype="float32"))
        progress_callback("五波段影像已就绪", 100)
        return output_path

    def fake_crop(**_kwargs):
        return {**MODEL_RESULT}

    monkeypatch.setattr(runner, "read_prosail_reflectance_aoi", fake_read)
    monkeypatch.setattr(runner, "run_crop_spatial_analysis", fake_crop)
    app = _app(tmp_path / "auto-crop.sqlite3")
    app.state.product_artifact_root = tmp_path / "artifacts"
    app.state.runtime_engine = SimpleNamespace(llm_provider=AnswerProvider(answer=CropDecisionOutput(
        final_class_id=0, confidence="medium", phenology="夏玉米苗期",
        rationale="7月山东邹平，冬小麦已收、夏玉米苗期；模型最高为玉米29%。",
    )))
    with TestClient(app) as client:
        created = client.post("/api/product/v1/analysis-workflows", json={
            "aoi": AOI, "imagery_item_id": "S2-workflow", "imagery_snapshot": SNAPSHOT,
            "requested_task_ids": ["crop"],
        })
        assert created.status_code == 201
        final = _wait_for_terminal(client, created.json()["workflow_id"])
        crop = next(step for step in final["steps"] if step["step_id"] == "crop")
        assert crop["status"] == "completed"
        assert crop["result"]["predicted_class"]["class_id"] == 3  # raw evidence untouched
        assert crop["result"]["crop_decision"]["source"] == "llm"
        assert crop["result"]["crop_decision"]["final_class_id"] == 0
        assert final["status"] == "completed"
