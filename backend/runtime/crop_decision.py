"""LLM-assisted crop judgement built on top of the KDD2020 model scores.

The KDD2020 classifier was trained on NAIP RGB field chips and is applied to
Sentinel-2 imagery, so its single-chip scores cannot be treated as a calibrated
probability for a Chinese field.  This module keeps those scores as measured
evidence and asks the configured LLM to combine them with the observation date
and the field location (agronomic prior knowledge) into one explicit decision.

Rules:
- the model prediction is never overwritten; it stays in ``predicted_class``;
- the LLM returns one class id plus a short structured rationale, never raw
  chain-of-thought;
- any LLM failure (missing provider, timeout, invalid output) falls back to the
  legacy behaviour: the model top-1 plus the 0.60 / 0.15 score gates;
- the decision and its inputs are persisted so retries cannot silently flip it.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from infra.imagery.crop_spatial import CLASS_NAMES, CLASS_NAMES_ZH

logger = logging.getLogger(__name__)

PROMPT_VERSION = "crop-decision-v1"
MIN_TOP_SCORE = 0.60
MIN_SCORE_MARGIN = 0.15
DECISION_SOURCES = ("llm", "model_fallback", "user_confirmed")
CONFIDENCE_LEVELS = ("high", "medium", "low")

SYSTEM_PROMPT = """你是遥感作物判读的判定层。你会收到一个地块的观测日期、地理位置和一套遥感作物分类模型的六类分数。

任务：结合该地区在该时节的农事历（播种、生长、收获窗口）和模型分数，判定该地块最可能的作物，从以下六类中选一个：
0 玉米 / 1 棉花 / 2 大豆 / 3 春小麦 / 4 冬小麦 / 5 大麦

必须遵守：
1. 只输出一个类别；若证据不足，仍然给出最可能的一类，但把 confidence 标为 low，并在 rationale 中说明不确定的原因。
2. rationale 用一到三句中文说明判定依据：地点、时节、物候窗口、模型分数如何支持该结论；不要编造没有依据的产量、精度或实地数据。
3. 模型分数是证据，不是校准后的概率；不要声称它是准确率。
4. 若模型最高分类别与该地区该时节的物候明显冲突，要以物候为主并说明冲突。
5. 不要输出推理过程原文，只输出结论与简明依据。
6. 地点判断以“行政区（按 AOI 质心反查）”和经纬度为准。若“位置一致性”提示 AOI 不在所选农场范围内，不要使用农场预设名称作为地点依据。

输出必须是一个 JSON 对象，字段如下（不要改名、不要嵌套额外对象）：
- final_class_id: 0-5 的整数
- confidence: "high" | "medium" | "low"
- phenology: 字符串，一句话物候判断
- rationale: 字符串，1-3 句中文判定依据
- excluded_classes: 数组，每项必须是 {"class_id": 0-5 的整数, "reason": "排除原因字符串"}，不要省略 reason"""

CORRECTIVE_SUFFIX = """

上一次输出未通过结构校验。请严格按以下要点重新输出，只输出 JSON：
- final_class_id 必须是 0-5 的整数；
- excluded_classes 每一项都必须同时包含 class_id（整数）和 reason（非空字符串）；
- 不要输出额外字段，不要输出 Markdown。"""


class ExcludedClass(BaseModel):
    """Tolerant on purpose: a missing per-class reason must not sink the whole judgement."""

    model_config = ConfigDict(extra="ignore")

    class_id: int = Field(ge=0, le=5)
    reason: str = Field(default="", max_length=200)
    name_zh: str | None = None


class CropDecisionOutput(BaseModel):
    """Structured LLM answer. Field order keeps the prior reasoning first."""

    model_config = ConfigDict(extra="ignore")

    final_class_id: int = Field(ge=0, le=5)
    confidence: str = "medium"
    phenology: str = Field(default="", max_length=200)
    rationale: str = Field(default="", max_length=600)
    excluded_classes: list[ExcludedClass] = Field(default_factory=list)

    @field_validator("confidence")
    @classmethod
    def _confidence(cls, value: str) -> str:
        normalized = value.strip().lower()
        return normalized if normalized in CONFIDENCE_LEVELS else "medium"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def class_label(class_id: int | None) -> str:
    if type(class_id) is int and 0 <= class_id < len(CLASS_NAMES_ZH):
        return CLASS_NAMES_ZH[class_id]
    return "未知"


def resolve_location(farm_id: str | None, geometry: dict | None) -> dict[str, Any]:
    """Resolve where the AOI actually is, preferring coordinates over the farm preset."""
    from shapely.geometry import shape

    from runtime.geo_location import reverse_geocode

    location: dict[str, Any] = {
        "label": None, "admin_hint": None, "province": None, "city": None,
        "lat": None, "lon": None, "source": "coordinates_only",
        "farm_label": None, "farm_name": None, "farm_mismatch": False,
    }
    centroid = None
    if geometry:
        try:
            centroid = shape(geometry).centroid
            location["lat"] = round(float(centroid.y), 5)
            location["lon"] = round(float(centroid.x), 5)
        except Exception:
            logger.warning("crop_decision_centroid_unavailable")
    if centroid is not None:
        geocoded = reverse_geocode(location["lat"], location["lon"])
        if geocoded:
            location["province"] = geocoded.get("province")
            location["admin_hint"] = geocoded.get("province")
    farm = None
    if farm_id:
        try:
            from runtime.farm_store import FarmStore

            farm = FarmStore().get_farm(farm_id)
        except Exception:  # pragma: no cover - farm presets are optional context
            farm = None
    if farm is not None:
        location["farm_label"] = farm.location_label
        location["farm_name"] = farm.name
        inside = False
        if centroid is not None:
            try:
                farm_geometry = (farm.geometry.model_dump() if hasattr(farm.geometry, "model_dump")
                                 else farm.geometry)
                inside = shape(farm_geometry).covers(centroid)
            except Exception:
                inside = False
        if inside:
            location["label"] = farm.location_label
            location["source"] = "farm_preset+admin_boundary" if location["province"] else "farm_preset"
        else:
            # A selected demo farm must never label an AOI drawn elsewhere.
            location["farm_mismatch"] = True
            location["label"] = location["province"]
            location["source"] = "admin_boundary" if location["province"] else "coordinates_only"
    else:
        location["label"] = location["province"]
        location["source"] = "admin_boundary" if location["province"] else "coordinates_only"
    return location


def decision_input_hash(model_result: dict[str, Any], observed_at: str, location: dict[str, Any]) -> str:
    scores = [
        (item.get("class_id"), item.get("score"))
        for item in model_result.get("class_scores") or []
        if isinstance(item, dict)
    ]
    payload = {
        "prompt_version": PROMPT_VERSION,
        "observed_at": observed_at,
        "location": {key: location.get(key) for key in ("label", "admin_hint", "lat", "lon")},
        "scores": scores,
        "model": (model_result.get("model") or {}).get("sha256"),
    }
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def model_evidence_sufficient(model_result: dict[str, Any]) -> bool:
    """Legacy 0.60 / 0.15 gate, kept only for the fallback path."""
    prediction = model_result.get("predicted_class") or {}
    score = prediction.get("score")
    scores = sorted(
        (row.get("score", 0) for row in model_result.get("class_scores") or []
         if isinstance(row, dict) and isinstance(row.get("score"), (int, float))),
        reverse=True,
    )
    if not isinstance(score, (int, float)):
        return False
    if score < MIN_TOP_SCORE:
        return False
    if len(scores) >= 2 and scores[0] - scores[1] < MIN_SCORE_MARGIN:
        return False
    return True


def _base_decision(model_result: dict[str, Any], *, source: str) -> dict[str, Any] | None:
    prediction = model_result.get("predicted_class") or {}
    class_id = prediction.get("class_id")
    if type(class_id) is not int or not 0 <= class_id < len(CLASS_NAMES):
        return None
    return {
        "final_class_id": class_id,
        "final_name_zh": class_label(class_id),
        "source": source,
        "confidence": "high" if model_evidence_sufficient(model_result) else "low",
        "rationale": "",
        "phenology": "",
        "location": {},
        "observed_at": "",
        "excluded_classes": [],
        "model_prediction": {
            "class_id": class_id,
            "name": prediction.get("name"),
            "name_zh": prediction.get("name_zh"),
            "score": prediction.get("score"),
        },
        "fallback_reason": None,
        "fallback_detail": None,
        "prompt_version": PROMPT_VERSION,
        "llm_model": None,
        "llm_attempts": 0,
        "input_hash": None,
        "decided_at": _now(),
    }


def _failure_detail(llm_provider: Any, exc: BaseException, stage: str) -> dict[str, Any]:
    """Keep the actionable failure facts so the fallback is explainable later."""
    excerpt = getattr(exc, "response_body_excerpt", None)
    return {
        "stage": stage,
        "error_type": type(exc).__name__,
        "category": getattr(exc, "category", None),
        "status_code": getattr(exc, "status_code", None),
        "provider": getattr(llm_provider, "model_name", None) or type(llm_provider).__name__,
        "message": (str(exc) or type(exc).__name__)[:600],
        "upstream_excerpt": str(excerpt)[:400] if excerpt else None,
    }


_SCHEMA_RETRY_HINTS = (
    "did not match", "structured validation", "schema", "contract",
    "not contain json", "incomplete json", "json decoding",
)


def _is_schema_failure(exc: BaseException) -> bool:
    if (getattr(exc, "category", "") or "") == "schema_mismatch":
        return True
    text = str(exc).lower()
    return any(hint in text for hint in _SCHEMA_RETRY_HINTS)


def model_fallback_decision(
    model_result: dict[str, Any], reason: str, *, observed_at: str = "",
    location: dict[str, Any] | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    decision = _base_decision(model_result, source="model_fallback")
    if decision is None:
        return None
    decision["rationale"] = "大模型判定不可用，沿用 KDD2020 模型最高分结果；分数未经校准，请结合实际情况复核。"
    decision["location"] = dict(location or {})
    decision["observed_at"] = observed_at
    decision["fallback_reason"] = reason[:300]
    decision["fallback_detail"] = detail
    decision["input_hash"] = decision_input_hash(model_result, observed_at, decision["location"])
    return decision


def decide_crop(
    llm_provider: Any,
    *,
    model_result: dict[str, Any],
    observed_at: str,
    farm_id: str | None,
    geometry: dict | None,
    area_hectares: float | None = None,
) -> dict[str, Any] | None:
    """Judge the final crop class. Returns ``None`` only when nothing usable exists."""
    location = resolve_location(farm_id, geometry)
    if llm_provider is None:
        return model_fallback_decision(
            model_result, "大模型未配置", observed_at=observed_at, location=location,
            detail={"stage": "provider_lookup", "error_type": "ProviderMissing",
                    "message": "服务端未配置可用的大模型 provider", "category": "provider_missing"},
        )
    scores = [
        {"class_id": item.get("class_id"), "name_zh": item.get("name_zh"), "score": item.get("score")}
        for item in model_result.get("class_scores") or [] if isinstance(item, dict)
    ]
    month = observed_at[:7] if observed_at else ""
    user_prompt = json.dumps({
        "地点": location.get("label"),
        "行政区（按AOI质心反查）": location.get("province"),
        "经纬度": {"lat": location.get("lat"), "lon": location.get("lon")},
        "农场预设名称": location.get("farm_label"),
        "位置一致性": ("AOI 位于所选农场范围内" if location.get("source", "").startswith("farm_preset")
                       else "AOI 不在所选农场范围内，农场名称不可作为地点依据，请以坐标与行政区为准"),
        "观测日期": observed_at,
        "观测月份": month,
        "选区面积_公顷": area_hectares,
        "模型": (model_result.get("model") or {}).get("name"),
        "模型训练与输入": "NAIP RGB 训练，当前输入 Sentinel-2 L2A；跨传感器结果未经实地验证",
        "模型六类分数": scores,
        "模型最高分": model_result.get("predicted_class"),
        "类别编号": "0 玉米 / 1 棉花 / 2 大豆 / 3 春小麦 / 4 冬小麦 / 5 大麦",
        "输出字段要求": {
            "final_class_id": "0-5 的整数",
            "confidence": "high | medium | low",
            "phenology": "字符串",
            "rationale": "1-3 句中文判定依据",
            "excluded_classes": [{"class_id": "0-5 的整数", "reason": "排除原因字符串（必填）"}],
        },
    }, ensure_ascii=False)
    validated: CropDecisionOutput | None = None
    failure: dict[str, Any] | None = None
    attempts = 0
    for attempt in (1, 2):
        attempts = attempt
        system_prompt = SYSTEM_PROMPT if attempt == 1 else SYSTEM_PROMPT + CORRECTIVE_SUFFIX
        try:
            answer = llm_provider.generate_structured(
                system_prompt=system_prompt, user_prompt=user_prompt, response_model=CropDecisionOutput,
            )
        except Exception as exc:  # LLM unavailable, timeout, invalid payload ...
            failure = _failure_detail(llm_provider, exc, "llm_call")
            logger.warning("crop_decision_llm_failed | attempt=%s | category=%s | message=%s",
                           attempt, failure.get("category"), str(failure.get("message"))[:200])
            if attempt == 1 and _is_schema_failure(exc):
                continue
            break
        try:
            validated = CropDecisionOutput.model_validate(
                answer.model_dump() if isinstance(answer, BaseModel) else answer
            )
        except Exception as exc:
            failure = _failure_detail(llm_provider, exc, "schema_validation")
            logger.warning("crop_decision_output_invalid | attempt=%s | message=%s",
                           attempt, str(failure.get("message"))[:200])
            if attempt == 1:
                continue
            break
        failure = None
        break
    if validated is None:
        reason = f"大模型判定失败：{(failure or {}).get('message') or '未知原因'}"
        return model_fallback_decision(
            model_result, reason, observed_at=observed_at, location=location,
            detail={**(failure or {}), "attempts": attempts},
        )
    rationale = validated.rationale.strip() or validated.phenology.strip() or f"大模型判定为{class_label(validated.final_class_id)}，未返回具体依据。"
    decision = _base_decision(model_result, source="llm")
    if decision is None:
        # The model prediction is unusable; the LLM answer alone is enough to continue.
        decision = {
            "final_class_id": validated.final_class_id,
            "final_name_zh": class_label(validated.final_class_id),
            "source": "llm",
            "confidence": validated.confidence,
            "rationale": rationale,
            "phenology": validated.phenology.strip(),
            "location": {},
            "observed_at": "",
            "excluded_classes": [],
            "model_prediction": {},
            "fallback_reason": None,
            "fallback_detail": None,
            "prompt_version": PROMPT_VERSION,
            "llm_model": None,
            "llm_attempts": attempts,
            "input_hash": None,
            "decided_at": _now(),
        }
    decision.update({
        "final_class_id": validated.final_class_id,
        "final_name_zh": class_label(validated.final_class_id),
        "confidence": validated.confidence,
        "rationale": rationale,
        "phenology": validated.phenology.strip(),
        "location": location,
        "observed_at": observed_at,
        "excluded_classes": [item.model_dump() for item in validated.excluded_classes][:6],
        "llm_model": getattr(llm_provider, "model_name", None) or type(llm_provider).__name__,
        "llm_attempts": attempts,
        "fallback_detail": None,
        "input_hash": decision_input_hash(model_result, observed_at, location),
        "decided_at": _now(),
    })
    return decision


def resolve_crop_class(step_result: dict[str, Any] | None) -> tuple[int | None, dict[str, Any] | None]:
    """Read the effective crop class, tolerating workflows saved before this change."""
    result = step_result or {}
    decision = result.get("crop_decision")
    if isinstance(decision, dict) and type(decision.get("final_class_id")) is int:
        return decision["final_class_id"], decision
    prediction = result.get("predicted_class") or {}
    class_id = prediction.get("class_id") if isinstance(prediction, dict) else None
    return (class_id if type(class_id) is int else None), None


def needs_score_gate(decision: dict[str, Any] | None) -> bool:
    """Only legacy/fallback decisions still depend on the raw model score gates."""
    return decision is None or decision.get("source") == "model_fallback"
