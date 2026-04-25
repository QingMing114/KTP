"""Shared presentation helpers for Chinese-facing UI text."""

from __future__ import annotations

import re

TASK_TYPE_LABELS = {
    "baldness_detection": "斑秃识别",
    "crop_health_detection": "作物长势检测",
    "yield_estimation": "产量估算",
    "lai_inversion": "叶面积指数反演",
    "land_cover_analysis": "地物分类分析",
}

REGION_LABELS = {
    "scalp": "地表",
    "lai": "通用",
    "henan": "河南",
    "yunnan": "云南",
}

CROP_TYPE_LABELS = {
    "hair": "植被",
    "lai": "通用",
    "wheat": "小麦",
    "maize": "玉米",
}

STATUS_LABELS = {
    "completed": "已完成",
    "done": "已完成",
    "success": "已完成",
    "failed": "失败",
    "error": "失败",
    "running": "运行中",
    "started": "进行中",
    "triggered": "已触发",
    "pending": "待处理",
    "queued": "排队中",
    "skipped": "已跳过",
    "missing": "缺失",
}

CONFIDENCE_LABELS = {
    "high": "高",
    "medium": "中",
    "low": "低",
}

_TEXT_LABELS = {
    "class semantics loaded from model metadata": "类别语义已从模型元数据加载",
    "class semantics loaded from model.metrics_json.prediction_class_semantics": (
        "类别语义已从模型元数据字段 prediction_class_semantics 加载"
    ),
    "review boundary quality": "建议复核边界质量",
    "mask marks every valid pixel as positive": "掩膜将所有有效像素都标记为阳性",
    "mask coverage is near-total and should be reviewed manually": "掩膜覆盖率接近全图，建议人工复核",
    "mask contains a single positive value across the full image": "掩膜在整幅图像中仅包含单一阳性值",
    "mask artifact is missing on disk": "掩膜文件在磁盘上不存在",
    "mask artifact could not be decoded": "掩膜文件无法解码",
    "mask artifact contains no valid pixels": "掩膜文件不包含有效像素",
    "mask artifact was not provided": "未提供掩膜文件",
    "mask artifact could not be inspected because the file is missing": "掩膜文件缺失，无法完成检查",
    "mask artifact exists but could not be decoded for inspection": "掩膜文件存在，但无法解码并完成检查",
    "mask artifact was loaded but contains no valid pixels": "掩膜文件已加载，但不包含有效像素",
    "No relevant knowledge snippets were retrieved.": "未检索到相关知识片段。",
    "ready model found": "已找到可用模型",
    "enter training branch": "进入训练分支",
}

_MASK_SUMMARY_PATTERN = re.compile(
    r"mask covers (?P<positive>\d+) of (?P<total>\d+) valid pixels "
    r"\((?P<ratio>[^)]+) positive coverage\)(?:; (?P<warnings>.*))?"
)


def display_task_type(
    value: str | None,
    *,
    default: str = "未提供",
    include_raw: bool = False,
) -> str:
    """Return a localized task type label."""
    return _display_with_mapping(
        value,
        mapping=TASK_TYPE_LABELS,
        default=default,
        include_raw=include_raw,
    )


def display_region(
    value: str | None,
    *,
    default: str = "未提供",
    include_raw: bool = False,
) -> str:
    """Return a localized region label."""
    return _display_with_mapping(
        value,
        mapping=REGION_LABELS,
        default=default,
        include_raw=include_raw,
    )


def display_crop_type(
    value: str | None,
    *,
    default: str = "未提供",
    include_raw: bool = False,
) -> str:
    """Return a localized crop/object label."""
    return _display_with_mapping(
        value,
        mapping=CROP_TYPE_LABELS,
        default=default,
        include_raw=include_raw,
    )


def display_status(value: str | None, *, default: str = "未知") -> str:
    """Return a localized status label."""
    if value is None:
        return default
    normalized = str(value).strip()
    if not normalized:
        return default
    return STATUS_LABELS.get(normalized.lower(), normalized)


def display_confidence_label(value: str | None, *, default: str = "未评估") -> str:
    """Return a localized confidence label."""
    if value is None:
        return default
    normalized = str(value).strip()
    if not normalized:
        return default
    return CONFIDENCE_LABELS.get(normalized.lower(), normalized)


def display_bool(
    value: bool | None,
    *,
    true_label: str = "是",
    false_label: str = "否",
    none_label: str = "自动",
) -> str:
    """Return a localized boolean label."""
    if value is None:
        return none_label
    return true_label if value else false_label


def localize_runtime_text(value: str | None) -> str:
    """Translate known runtime warning/detail strings into Chinese."""
    if value is None:
        return ""
    normalized = str(value).strip()
    if not normalized:
        return ""

    exact = _TEXT_LABELS.get(normalized)
    if exact is not None:
        return exact

    lower_value = normalized.lower()
    for source_text, translated in _TEXT_LABELS.items():
        if lower_value == source_text.lower():
            return translated

    match = _MASK_SUMMARY_PATTERN.fullmatch(normalized)
    if match:
        warnings = match.group("warnings") or ""
        suffix = ""
        if warnings:
            localized_warnings = "；".join(
                localize_runtime_text(item.strip())
                for item in warnings.split(";")
                if item.strip()
            )
            if localized_warnings:
                suffix = f"；{localized_warnings}"
        return (
            f"掩膜覆盖 {match.group('total')} 个有效像素中的 {match.group('positive')} 个"
            f"（阳性覆盖率 {match.group('ratio')}）{suffix}"
        )

    if normalized.endswith(" sources"):
        count = normalized.removesuffix(" sources").strip()
        return f"{count} 条来源"
    if normalized.endswith(" source"):
        count = normalized.removesuffix(" source").strip()
        return f"{count} 条来源"

    return normalized


def _display_with_mapping(
    value: str | None,
    *,
    mapping: dict[str, str],
    default: str,
    include_raw: bool,
) -> str:
    if value is None:
        return default
    raw = str(value).strip()
    if not raw:
        return default
    localized = mapping.get(raw.lower())
    if localized is None:
        return raw
    if include_raw and localized != raw:
        return f"{localized}（{raw}）"
    return localized
