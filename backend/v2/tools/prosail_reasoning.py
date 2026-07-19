"""PROSAIL scene reasoning — domain-level inference of search-space parameters.

Phase A.3: Extracted from ``v2/runtime/executor.py`` into its own domain module.
This is pure remote-sensing logic with no I/O or LLM dependencies.

.. note::

    The current implementation uses **rule-based keyword matching** for crop type,
    location, and growth-stage detection.  This is a placeholder — a production
    version should use the LLM or a structured knowledge base to infer scene
    parameters from free-form user queries.  See pending issue: "prosail scene
    reasoning should use LLM instead of rule-based keyword matching".
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SceneReasoningResult:
    """Structured result from PROSAIL scene parameter inference.

    Attributes:
        steps:       Display-oriented (label, detail) pairs for the DebugDrawer.
        constraints: Machine-readable parameter ranges for LUT filtering.
                     Keys: lai_range, cab_range, lidfa_range, psoil_range.
    """
    steps: list[tuple[str, str]] = field(default_factory=list)
    constraints: dict = field(default_factory=dict)


def prosail_scene_reasoning(query: str, image_path: str | None) -> SceneReasoningResult:
    """Return scene parameter inference with both display steps and constraints.

    Detects crop type, geographic location, season/month, and growth stage
    from the user query, then maps them to plausible PROSAIL parameter
    search ranges (LAI, Cab, LIDFa, psoil).
    """
    q = (query or "").lower()
    img_name = (image_path or "").replace("\\", "/").split("/")[-1]

    # Crop detection
    if any(k in q for k in ("玉米", "corn", "maize")):
        crop, crop_en = "玉米", "Maize"
    elif any(k in q for k in ("冬小麦", "小麦", "wheat")):
        crop, crop_en = "小麦", "Wheat"
    elif any(k in q for k in ("水稻", "稻", "rice")):
        crop, crop_en = "水稻", "Rice"
    elif any(k in q for k in ("棉花", "cotton")):
        crop, crop_en = "棉花", "Cotton"
    else:
        crop, crop_en = "作物（未指定）", "Crop"

    # Location detection
    if any(k in q for k in ("张掖", "zhangye", "甘肃")):
        loc, climate = "张掖（西北干旱区）", "大陆性干旱气候，辐射强，昼夜温差大"
    elif any(k in q for k in ("山东", "shandong")):
        loc, climate = "山东", "暖温带季风气候"
    elif any(k in q for k in ("河南", "henan")):
        loc, climate = "河南", "温带季风气候"
    elif any(k in q for k in ("东北", "黑龙江", "吉林")):
        loc, climate = "东北", "温带大陆性气候"
    elif any(k in q for k in ("新疆", "xinjiang")):
        loc, climate = "新疆（西北干旱区）", "温带大陆性干旱气候"
    elif any(k in q for k in ("内蒙", "inner mongolia")):
        loc, climate = "内蒙古", "温带大陆性气候"
    else:
        loc, climate = "未指定地区", "—"

    # Season / month detection
    month = None
    for m, kws in {
        1: ("1月", "january", "一月"),
        3: ("3月", "march", "三月"),
        4: ("4月", "april", "四月"),
        5: ("5月", "may", "五月"),
        6: ("6月", "june", "六月"),
        7: ("7月", "july", "七月"),
        8: ("8月", "august", "八月"),
        9: ("9月", "september", "九月"),
        10: ("10月", "october", "十月"),
    }.items():
        if any(k in q for k in kws):
            month = m
            break
    if month is None and any(k in q for k in ("夏", "summer")):
        month = 7
    elif month is None and any(k in q for k in ("春", "spring")):
        month = 4
    elif month is None and any(k in q for k in ("秋", "autumn")):
        month = 9

    # Growth stage inference
    if crop_en == "Maize":
        if month and 5 <= month <= 6:
            stage, lai_range, cab_range = "苗期-拔节期", (0.5, 3.5), (35, 65)
        elif month and 7 <= month <= 8:
            stage, lai_range, cab_range = "抽穗-灌浆旺盛期", (3.0, 7.0), (45, 80)
        elif month and 9 <= month <= 10:
            stage, lai_range, cab_range = "灌浆-成熟期", (1.5, 5.0), (25, 55)
        else:
            stage, lai_range, cab_range = "生长期（月份未知）", (0.5, 7.0), (30, 80)
    elif crop_en == "Wheat":
        if month and 3 <= month <= 4:
            stage, lai_range, cab_range = "返青-拔节期", (1.0, 4.5), (35, 65)
        elif month and month == 5:
            stage, lai_range, cab_range = "抽穗-开花期", (2.0, 5.5), (40, 70)
        elif month and 6 <= month <= 7:
            stage, lai_range, cab_range = "灌浆-成熟期", (1.0, 4.0), (20, 50)
        else:
            stage, lai_range, cab_range = "生长期（月份未知）", (0.5, 6.0), (20, 70)
    elif crop_en == "Rice":
        stage, lai_range, cab_range = "分蘖-拔节期", (0.3, 4.5), (35, 70)
    else:
        stage, lai_range, cab_range = "通用植被", (0.0, 7.0), (20, 80)

    lidfa_range = (40, 70) if crop_en == "Maize" else (30, 65)
    psoil_range = (0.1, 0.6)

    # Build display-oriented steps (same as before)
    scene_desc = f"{loc} · {crop} · {(str(month) + '月') if month else '月份未知'}"
    if climate != "—":
        scene_desc += f"  [{climate}]"

    param_lines = (
        f"根据场景 [{scene_desc}] 推断 PROSAIL 参数搜索空间：\n"
        f"  · 生长阶段: {stage}\n"
        f"  · LAI      [{lai_range[0]:.1f}, {lai_range[1]:.1f}]  m²/m²\n"
        f"  · Cab      [{cab_range[0]}, {cab_range[1]}]  μg/cm²   （叶绿素含量）\n"
        f"  · LIDFa    [{lidfa_range[0]}, {lidfa_range[1]}]°      （叶倾角分布）\n"
        f"  · psoil    [{psoil_range[0]:.1f}, {psoil_range[1]:.1f}]         （土壤亮度）\n"
        f"  · 波段输入: B2 / B3 / B4 / B7 / B8（Sentinel-2 五波段）"
    )

    steps = [
        (
            "识别工具: PROSAIL LUT 反演模型",
            f"读取 prosail.lai_html_report 工具规格。\n"
            f"选择策略: LUT 查表法（Top-1% 均值）\n"
            f"输入文件: {img_name or '卫星图像'}\n"
            f"参数库:   LUT_test.txt（13 列 · LAI / 反射率 / 冠层结构参数）",
        ),
        (
            f"推理参数范围（{scene_desc.split('[')[0].strip()}）",
            param_lines,
        ),
        (
            "执行 PROSAIL LUT 逐像元反演",
            "逐行扫描影像，对每个像元计算与 LUT 的 MSE，\n"
            "取 Top-1% 最优匹配条目的 LAI 均值作为估算结果。",
        ),
    ]

    # Build machine-readable constraints for LUT filtering
    constraints = {
        "lai_range":   [float(lai_range[0]),   float(lai_range[1])],
        "cab_range":   [float(cab_range[0]),   float(cab_range[1])],
        "lidfa_range": [float(lidfa_range[0]), float(lidfa_range[1])],
        "psoil_range": [float(psoil_range[0]), float(psoil_range[1])],
    }

    return SceneReasoningResult(steps=steps, constraints=constraints)
