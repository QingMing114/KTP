"""LLM-driven PROSAIL scene parameter extraction with rule-based fallback.

Phase A.3 of the V2 refactoring: replaces the purely rule-based keyword
matching in prosail_reasoning.py with an LLM-first approach when the
provider is available.  Falls back to the existing rule-based logic when
the LLM is absent or returns unusable (confidence < 0.4) results.
"""

from __future__ import annotations

import logging

from schemas.runtime import SceneParameters

logger = logging.getLogger(__name__)

# ── PROSAIL domain knowledge injected into the LLM system prompt ──

_SCENE_SYSTEM_PROMPT = """你是一名遥感定量反演领域专家，专门为 PROSAIL 辐射传输模型的
LUT（查找表）反演推断场景参数。

## 角色

根据用户查询中的作物类型、地理位置、季节/月份、生长阶段等信息，
推断合理的 PROSAIL 参数搜索范围，用于缩小 LUT 匹配空间以提升反演精度和速度。

## PROSAIL 参数说明

1. **LAI（叶面积指数）** 0–10 m²/m²
   — 单位地表面积上叶片总面积
   — 苗期/分蘖期   0.3–2.0
   — 拔节/抽穗期   1.5–5.0
   — 开花/灌浆旺盛  3.0–7.0
   — 成熟/衰老期   0.3–3.0

2. **Cab（叶绿素 a+b 含量）** 0–100 μg/cm²
   — 健康营养充足   40–80
   — 轻度胁迫      20–40
   — 严重胁迫/衰老   5–20

3. **LIDFa（叶倾角）** 0–90°
   — 水平型（planophile，如阔叶作物）   10–35
   — 球面型（spherical，通用）         57–65
   — 直立型（erectophile，如禾本科）    55–80
   — 常见作物：玉米 40–65 | 小麦 50–75 | 水稻 50–70

4. **psoil（土壤亮度参数）** 0–1
   — 深色/湿润土壤  0.1–0.3
   — 中等土壤       0.3–0.6
   — 浅色/干燥土壤  0.5–0.8

## 推理指引

- 从用户消息中提取：作物类型 → 地区 → 月份/季节 → 生长阶段
- 根据作物 + 生长阶段确定合理参数范围（宁宽勿窄）
- 若信息不足，使用该作物的全生育期默认范围
- 不确定的参数设为 null

## 置信度规则

| 置信度 | 条件 |
|--------|------|
| ≥0.8   | 作物类型 + 地区 + 月份/生长阶段均明确 |
| 0.6–0.8| 其中两个因素明确 |
| 0.4–0.6| 仅一个因素明确 |
| <0.4   | 主要靠默认值猜测 |

## 输出要求

只返回结构化 JSON，符合 SceneParameters schema。
不要包含任何额外文字。
推理过程用 reasoning 字段简洁说明。
"""


def _build_user_prompt(
    *,
    query: str,
    image_path: str | None,
    region: str | None,
    crop_type: str | None,
) -> str:
    """Build the user-specific prompt fragment."""
    parts = [f"用户消息：{query or '（无）'}"]
    if image_path:
        parts.append(f"影像文件：{image_path}")
    if region:
        parts.append(f"已检测地区：{region}")
    if crop_type:
        parts.append(f"已检测作物：{crop_type}")
    parts.append("\n请根据上述信息推断 PROSAIL 场景参数。")
    return "\n".join(parts)


def extract_scene_parameters(
    *,
    llm_provider,
    query: str,
    image_path: str | None,
    region: str | None,
    crop_type: str | None,
) -> SceneParameters:
    """Extract PROSAIL scene parameters, LLM-first with rule-based fallback.

    If *llm_provider* is ``None`` or the LLM returns a result with
    confidence < 0.4, falls back to the rule-based keyword matching in
    ``prosail_reasoning.prosail_scene_reasoning``.

    Returns a ``SceneParameters`` instance — never ``None``.
    """
    # ── LLM path ──
    if llm_provider is not None:
        try:
            result: SceneParameters = llm_provider.generate_structured(
                system_prompt=_SCENE_SYSTEM_PROMPT,
                user_prompt=_build_user_prompt(
                    query=query,
                    image_path=image_path,
                    region=region,
                    crop_type=crop_type,
                ),
                response_model=SceneParameters,
            )
            if result.confidence >= 0.4:
                logger.info(
                    "scene_extractor_llm_ok | confidence=%.2f | crop=%s | region=%s",
                    result.confidence,
                    result.crop_type,
                    result.region,
                )
                return result
            logger.warning(
                "scene_extractor_low_confidence | confidence=%.2f — falling back to rules",
                result.confidence,
            )
        except Exception:
            logger.exception("scene_extractor_llm_failed — falling back to rules")

    # ── Rule-based fallback ──
    return _rule_based_extract(query, image_path, crop_type=crop_type, region=region)


def _rule_based_extract(
    query: str,
    image_path: str | None,
    crop_type: str | None = None,
    region: str | None = None,
) -> SceneParameters:
    """Fallback using the existing keyword-matching logic."""
    from v2.tools.prosail_reasoning import prosail_scene_reasoning

    result = prosail_scene_reasoning(query, image_path)
    c = result.constraints  # {"lai_range": [...], "cab_range": [...], ...}
    return SceneParameters(
        crop_type=crop_type or c.get("crop_type"),
        region=region or c.get("region"),
        lai_range=tuple(c.get("lai_range", [0.0, 7.0])) if "lai_range" in c else None,
        cab_range=tuple(c.get("cab_range", [20, 80])) if "cab_range" in c else None,
        lidfa_range=tuple(c.get("lidfa_range", [30, 70])) if "lidfa_range" in c else None,
        psoil_range=tuple(c.get("psoil_range", [0.1, 0.6])) if "psoil_range" in c else None,
        confidence=0.3,
        reasoning="基于规则关键词匹配（LLM 不可用或返回低置信度时的回退方案）",
    )
