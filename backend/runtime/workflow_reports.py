"""Persist readable, immutable reports for map analysis results."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from runtime.artifact_store import ArtifactStore
from runtime.workflow_report_design import render_report

REPORT_VERSION = "map-report-v2"


def _number(value: Any, decimals: int = 1) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        return "—"
    return f"{value:,.{decimals}f}"


def _fraction(value: Any) -> str:
    return f"{_number(value * 100)}%" if isinstance(value, (int, float)) else "—"


def register_crop_report(
    artifacts: ArtifactStore, *, run_id: str, output_dir: Path,
    imagery_item_id: str, observed_at: str, area_hectares: float | None,
    result: dict[str, Any],
) -> dict[str, str]:
    model = result.get("model") or {}
    prediction = result.get("predicted_class") or {}
    classes = sorted(result.get("class_scores") or [], key=lambda item: item.get("score", 0), reverse=True)
    valid_pixels = (result.get("input") or {}).get("valid_pixels")
    return register_map_report(
        artifacts, run_id=run_id, output_dir=output_dir,
        kind="crop_classification_report", title="农作物识别分析报告",
        context={"分析 ID": run_id, "影像 ID": imagery_item_id,
                 "观测日期": observed_at[:10], "选区面积": f"{_number(area_hectares, 2)} ha",
                 "模型": model.get("name"), "权重 SHA-256": model.get("sha256")},
        highlights=[{"label": "识别最高类别", "value": prediction.get("name_zh") or "未知"},
                    {"label": "最高模型分数", "value": _fraction(prediction.get("score"))},
                    {"label": "参与比较类别", "value": str(len(classes))},
                    {"label": "有效影像像元", "value": str(valid_pixels) if valid_pixels is not None else "—"}],
        visuals=[{"type": "bars", "title": "六类模型分数", "hint": "按模型输出分数降序排列 · 分数未经校准",
                  "items": [{"label": item.get("name_zh") or item.get("name") or "未知",
                             "value": item.get("score", 0), "display": _fraction(item.get("score"))}
                            for item in classes]}],
        sections=[{"title": "结果说明",
                   "rows": [["识别范围", "整个选区的一种作物类别"],
                            ["影像输入", "Sentinel-2 L2A RGB"],
                            ["模型输入", "224 × 224 RGB 图像"]],
                   "notes": result.get("warnings") or [
                       "模型分数不是经过实地校准的置信度，也不代表逐像元作物分类。"]}],
    )


def register_growth_report(
    artifacts: ArtifactStore, *, workflow_id: str, output_dir: Path,
    imagery_item_id: str, observed_at: str, area_hectares: float | None,
    result: dict[str, Any],
) -> dict[str, str]:
    quality = result.get("quality") or {}
    fraction = quality.get("valid_pixel_fraction")
    return register_map_report(
        artifacts, run_id=workflow_id, output_dir=output_dir,
        kind="growth_observation_report", title="作物长势观测指标报告",
        context={"工作流 ID": workflow_id, "影像 ID": imagery_item_id,
                 "观测日期": observed_at[:10], "选区面积": f"{_number(area_hectares, 2)} ha",
                 "方法": result.get("method")},
        highlights=[{"label": "LAI 选区均值", "value": _number(result.get("lai_mean"), 2), "unit": "m²/m²"},
                    {"label": "植被比例", "value": _number(result.get("vegetation_ratio")), "unit": "%"},
                    {"label": "LAI 有效像元", "value": str(quality.get("valid_pixel_count", "—"))},
                    {"label": "选区有效覆盖率", "value": _fraction(fraction)}],
        visuals=[{"type": "bars", "title": "观测数据覆盖", "hint": "覆盖率反映可用像元，不是长势评分",
                  "items": [{"label": "LAI 有效覆盖", "value": fraction or 0,
                             "display": _fraction(fraction)}]}],
        sections=[{"title": "解读边界",
                   "rows": [["分析性质", "单景影像观测指标汇总"],
                            ["LAI 有效像元", quality.get("valid_pixel_count", "—")],
                            ["AOI 内栅格像元", quality.get("total_pixel_count", "—")]],
                   "notes": [result.get("warning") or
                             "尚未按作物生育期建立长势等级，不代表未来生长趋势。"]}],
    )


def register_potential_report(
    artifacts: ArtifactStore, *, workflow_id: str, output_dir: Path,
    imagery_item_id: str, observed_at: str, area_hectares: float | None,
    result: dict[str, Any],
) -> dict[str, str]:
    return register_map_report(
        artifacts, run_id=workflow_id, output_dir=output_dir,
        kind="canopy_index_report", title="遥感冠层状态试验报告",
        context={"工作流 ID": workflow_id, "影像 ID": imagery_item_id,
                 "观测日期": observed_at[:10], "选区面积": f"{_number(area_hectares, 2)} ha",
                 "方法版本": result.get("method")},
        highlights=[{"label": "冠层指数", "value": _number(result.get("canopy_index")), "unit": "/ 100"},
                    {"label": "NDVI 中位数", "value": _number(result.get("ndvi_median"), 3)},
                    {"label": "LAI 均值", "value": _number(result.get("lai_mean"), 2), "unit": "m²/m²"},
                    {"label": "LAI 有效覆盖", "value": _fraction(result.get("lai_valid_fraction"))}],
        visuals=[{"type": "bars", "title": "指标构成", "hint": "仅表示当期冠层信号，不是产量百分比",
                  "items": [{"label": "LAI 分量", "value": result.get("lai_component", 0),
                             "display": _number(result.get("lai_component"), 3)},
                            {"label": "NDVI 分量", "value": result.get("ndvi_component", 0),
                             "display": _number(result.get("ndvi_component"), 3)}]}],
        sections=[{"title": "计算与解释",
                   "rows": [["LAI 分量", "1 − exp(−0.5 × LAI)"],
                            ["NDVI 分量", "clip((NDVI − 0.2) / 0.6, 0, 1)"],
                            ["冠层指数", "100 × √(LAI 分量 × NDVI 分量)"],
                            ["作物识别", (result.get("crop_prediction") or {}).get("name_zh", "未知")]],
                   "notes": [note for note in (result.get("signal_warning"),
                                                result.get("uncertainty_note")) if note]}],
    )


def register_yield_report(
    artifacts: ArtifactStore, *, workflow_id: str, output_dir: Path,
    imagery_item_id: str, observed_at: str, area_hectares: float | None,
    result: dict[str, Any],
) -> dict[str, str]:
    bounds = result.get("constrained_yield_range_t_ha") or []
    provenance = result.get("input_provenance") or {}
    count = result.get("scenario_count") or 0
    accepted = result.get("accepted_count") or 0
    return register_map_report(
        artifacts, run_id=workflow_id, output_dir=output_dir,
        kind="apsim_report", title="APSIM 地块情景估产报告",
        context={"工作流 ID": workflow_id, "影像 ID": imagery_item_id,
                 "LAI 观测日期": observed_at[:10], "选区面积": f"{_number(area_hectares, 2)} ha",
                 "地块数据集": provenance.get("dataset_id"), "核验人": provenance.get("verified_by")},
        highlights=[{"label": "LAI 约束估产", "value": _number(result.get("constrained_yield_t_ha"), 2), "unit": "t/ha"},
                    {"label": "基线模拟产量", "value": _number(result.get("baseline_yield_t_ha"), 2), "unit": "t/ha"},
                    {"label": "情景范围", "value": (
                        f"{_number(bounds[0], 2)}–{_number(bounds[1], 2)}" if len(bounds) == 2 else "—"),
                     "unit": "t/ha"},
                    {"label": "入选情景", "value": f"{accepted} / {count}"}],
        visuals=[{"type": "bars", "title": "模拟情景筛选", "hint": "按观测日 LAI 约束；并非实收产量验证",
                  "items": [{"label": "入选情景", "value": accepted / count if count else 0,
                             "display": f"{accepted} / {count}"}]}],
        sections=[{"title": "输入与方法",
                   "rows": [["作物", provenance.get("crop_type", "—")],
                            ["品种", provenance.get("cultivar", "—")],
                            ["播种日期", provenance.get("sowing_date", "—")],
                            ["气象覆盖", " 至 ".join(provenance.get("weather_period") or [])],
                            ["LAI 约束容差", _number(result.get("lai_tolerance"), 3)]],
                   "notes": [result.get("uncertainty_note") or
                             "这是基于已核验输入的模型情景值，仍需实收产量验证。"]}],
    )


def register_simple_yield_report(artifacts: ArtifactStore, *, workflow_id: str, output_dir: Path,
                               imagery_item_id: str, observed_at: str, area_hectares: float | None,
                               result: dict[str, Any]) -> dict[str, str]:
    season, parameters = result.get("season") or {}, result.get("parameters") or {}
    bounds = result.get("parameter_scenario_range_t_ha") or []
    weather = result.get("weather_provenance") or {}
    observations = result.get("observations") or []
    return register_map_report(
        artifacts, run_id=workflow_id, output_dir=output_dir, kind="simple_yield_report",
        title="小麦/玉米自动简化估产（试验）",
        context={"工作流 ID": workflow_id, "作物": result.get("crop_label"),
                 "选区面积": f"{_number(area_hectares, 2)} ha", "所选影像日期": observed_at[:10],
                 "遥感有效生长期": f"{season.get('start', '—')} 至 {season.get('end', '—')}"},
        highlights=[{"label": "粮食干重试验估计", "value": _number(result.get("estimated_yield_t_ha"), 2), "unit": "t/ha"},
                    {"label": "参数情景范围", "value": f"{_number(bounds[0], 2)}–{_number(bounds[1], 2)}" if len(bounds) == 2 else "—", "unit": "t/ha"},
                    {"label": "季内清晰观测", "value": str(season.get("observations", 0))},
                    {"label": "本地实收校准", "value": "尚未校准"}],
        visuals=[{"type": "bars", "title": "季节 NDVI 观测", "hint": "选区云掩膜后的时序；不代表逐像元产量",
                  "items": [{"label": row["date"], "value": max(0, row["ndvi"]), "display": _number(row["ndvi"], 3)}
                            for row in observations if season.get("start", "") <= row["date"] <= season.get("end", "")]}],
        sections=[{"title": "估产依据", "rows": [
            ["算法", "逐日辐射 × 0.48 × FPAR × 辐射利用效率 × 收获指数"],
            ["辐射利用效率 g/MJ", parameters.get("rue_g_dm_per_mj_apar")],
            ["收获指数", parameters.get("harvest_index")],
            ["FPAR", parameters.get("fpar_relation")],
            ["最大季内观测间隔", f"{season.get('max_observation_gap_days', '—')} 天"],
            ["公开气象来源", weather.get("provider")],
            ["空间支撑", weather.get("spatial_support")],
            ["产量口径", "粮食干重；未换算为特定含水率的实收重量"]],
            "notes": [result.get("uncertainty_note") or "试验估计，尚需本地实收验证。"]},
            {"title": "参数与数据参考", "rows": [[row["title"], row["url"]] for row in result.get("references", [])],
             "notes": ["参数范围为文献启发的实验情景，不能解释为统计置信区间。"]}],
    )


def register_map_report(
    artifacts: ArtifactStore, *, run_id: str, output_dir: Path, kind: str,
    title: str, context: dict[str, Any], sections: list[dict[str, Any]],
    highlights: list[dict[str, Any]] | None = None,
    visuals: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    """Return public artifact references; never expose local paths in results."""
    payload = {"report_version": REPORT_VERSION, "kind": kind, "title": title,
               "context": context, "highlights": highlights or [],
               "visuals": visuals or [], "sections": sections}
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / f"{kind}_{digest}.html"
    json_path = output_dir / f"{kind}_{digest}.json"
    if not html_path.exists():
        html_path.write_text(render_report(payload), encoding="utf-8")
    if not json_path.exists():
        json_path.write_text(body, encoding="utf-8")
    report_id = artifacts.register(run_id, SimpleNamespace(
        pack_name="remote_sensing", artifact_type=kind, title=title,
        uri=str(html_path), content=None, content_type="text/html; charset=utf-8",
    ))
    data_id = artifacts.register(run_id, SimpleNamespace(
        pack_name="remote_sensing", artifact_type="analysis_result_json",
        title=f"{title} · 结构化结果", uri=str(json_path), content=None,
        content_type="application/json",
    ))
    return {"report_artifact_id": report_id,
            "report_uri": f"/api/product/v1/artifacts/{report_id}/render",
            "report_kind": kind, "report_version": REPORT_VERSION,
            "report_data_artifact_id": data_id,
            "report_data_uri": f"/api/product/v1/artifacts/{data_id}/content"}


def register_result_json(
    artifacts: ArtifactStore, *, run_id: str, output_dir: Path,
    title: str, result: dict[str, Any],
) -> dict[str, str]:
    """Register a public-safe result snapshot alongside an existing HTML report."""
    allowed = {key: value for key, value in result.items()
               if not key.endswith("_path") and key not in {"report_uri", "report_artifact_id"}}
    body = json.dumps({"report_version": REPORT_VERSION, "result": allowed},
                      ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"analysis_result_{digest}.json"
    if not path.exists():
        path.write_text(body, encoding="utf-8")
    artifact_id = artifacts.register(run_id, SimpleNamespace(
        pack_name="remote_sensing", artifact_type="analysis_result_json",
        title=f"{title} · 结构化结果", uri=str(path), content=None,
        content_type="application/json",
    ))
    return {"report_data_artifact_id": artifact_id,
            "report_data_uri": f"/api/product/v1/artifacts/{artifact_id}/content"}
