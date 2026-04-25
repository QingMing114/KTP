"""Shared normalization helpers for intent, region, and crop extraction."""

from __future__ import annotations

import re
from typing import Iterable

_REGION_ALIASES: dict[str, tuple[str, ...]] = {
    "scalp": ("scalp", "scalp region", "地表", "裸地"),
    "lai": ("lai", "叶面积", "通用"),
    "beijing": ("beijing", "beijing province", "北京", "北京市"),
    "tianjin": ("tianjin", "天津", "天津市"),
    "hebei": ("hebei", "hebei province", "河北", "河北省"),
    "shanxi": ("shanxi", "shanxi province", "山西", "山西省"),
    "inner_mongolia": (
        "inner mongolia",
        "inner_mongolia",
        "neimenggu",
        "内蒙古",
        "内蒙古自治区",
    ),
    "liaoning": ("liaoning", "liaoning province", "辽宁", "辽宁省"),
    "jilin": ("jilin", "jilin province", "吉林", "吉林省"),
    "heilongjiang": ("heilongjiang", "heilongjiang province", "黑龙江", "黑龙江省"),
    "shanghai": ("shanghai", "上海", "上海市"),
    "jiangsu": ("jiangsu", "jiangsu province", "江苏", "江苏省"),
    "zhejiang": ("zhejiang", "zhejiang province", "浙江", "浙江省"),
    "anhui": ("anhui", "anhui province", "安徽", "安徽省"),
    "fujian": ("fujian", "fujian province", "福建", "福建省"),
    "jiangxi": ("jiangxi", "jiangxi province", "江西", "江西省"),
    "shandong": ("shandong", "shandong province", "山东", "山东省"),
    "henan": ("henan", "henan province", "河南", "河南省"),
    "hubei": ("hubei", "hubei province", "湖北", "湖北省"),
    "hunan": ("hunan", "hunan province", "湖南", "湖南省"),
    "guangdong": ("guangdong", "guangdong province", "广东", "广东省"),
    "guangxi": (
        "guangxi",
        "guangxi zhuang autonomous region",
        "广西",
        "广西壮族自治区",
    ),
    "hainan": ("hainan", "hainan province", "海南", "海南省"),
    "chongqing": ("chongqing", "重庆", "重庆市"),
    "sichuan": ("sichuan", "sichuan province", "四川", "四川省"),
    "guizhou": ("guizhou", "guizhou province", "贵州", "贵州省"),
    "yunnan": ("yunnan", "yunnan province", "云南", "云南省"),
    "tibet": ("tibet", "xizang", "西藏", "西藏自治区"),
    "shaanxi": ("shaanxi", "shaanxi province", "陕西", "陕西省"),
    "gansu": ("gansu", "gansu province", "甘肃", "甘肃省"),
    "qinghai": ("qinghai", "qinghai province", "青海", "青海省"),
    "ningxia": ("ningxia", "ningxia hui autonomous region", "宁夏", "宁夏回族自治区"),
    "xinjiang": (
        "xinjiang",
        "xinjiang uygur autonomous region",
        "新疆",
        "新疆维吾尔自治区",
    ),
    "hong_kong": ("hong kong", "hong_kong", "香港", "香港特别行政区"),
    "macau": ("macau", "macao", "澳门", "澳门特别行政区"),
    "taiwan": ("taiwan", "台湾", "台湾省"),
}

_CROP_ALIASES: dict[str, tuple[str, ...]] = {
    "hair": ("hair", "vegetation", "植被", "作物"),
    "lai": ("lai", "叶面积", "通用"),
    "wheat": ("wheat", "winter wheat", "spring wheat", "小麦"),
    "rice": ("rice", "paddy", "水稻", "稻田"),
    "maize": ("maize", "corn", "玉米"),
    "soybean": ("soybean", "soy bean", "大豆"),
    "cotton": ("cotton", "棉花"),
    "rapeseed": ("rapeseed", "canola", "油菜", "油菜籽"),
    "peanut": ("peanut", "groundnut", "花生"),
    "potato": ("potato", "土豆", "马铃薯"),
}

_TASK_TYPE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("yield_estimation", ("yield", "产量", "估产", "测产")),
    ("lai_inversion", ("lai", "叶面积指数", "反演")),
    ("land_cover_analysis", ("land cover", "landcover", "地表覆盖", "地物分类")),
    (
        "baldness_detection",
        ("baldness", "alopecia", "斑秃", "脱发", "秃发"),
    ),
    (
        "crop_health_detection",
        ("disease", "health", "stress", "病害", "长势", "检测", "识别", "分割"),
    ),
)

_TASK_TYPE_ALIASES: dict[str, str] = {
    "crop_health_detection": "crop_health_detection",
    "health_assessment": "crop_health_detection",
    "health_detection": "crop_health_detection",
    "disease_detection": "crop_health_detection",
    "yield_estimation": "yield_estimation",
    "lai_inversion": "lai_inversion",
    "land_cover_analysis": "land_cover_analysis",
    "baldness_detection": "baldness_detection",
}

_IMAGE_PATH_PATTERN = re.compile(
    r"""(?P<path>(?:[A-Za-z]:\\|/|~/|\./|\.\./)[^\s"'<>]+?\.(?:tif|tiff|png|jpg|jpeg|bmp|webp))""",
    re.IGNORECASE,
)


def normalize_region(region: str | None) -> str | None:
    """Normalize free-form region text into canonical registry keys."""
    if not region:
        return None
    return _normalize_alias(region, _REGION_ALIASES)


def normalize_crop_type(crop_type: str | None) -> str | None:
    """Normalize free-form crop text into canonical registry keys."""
    if not crop_type:
        return None
    return _normalize_alias(crop_type, _CROP_ALIASES)


def normalize_task_type(task_type: str | None) -> str | None:
    """Normalize free-form task text into canonical workflow keys."""
    if not task_type:
        return None
    normalized = _compact_english(task_type)
    normalized = normalized.replace("-", "_").replace(" ", "_")
    return _TASK_TYPE_ALIASES.get(normalized)


def detect_region_from_text(text: str) -> str | None:
    """Best-effort region detection from natural language text."""
    return _detect_alias_in_text(text, _REGION_ALIASES)


def detect_crop_type_from_text(text: str) -> str | None:
    """Best-effort crop detection from natural language text."""
    return _detect_alias_in_text(text, _CROP_ALIASES)


def detect_task_type_from_text(text: str, *, default: str | None = None) -> str | None:
    """Best-effort task detection from natural language text."""
    normalized = text.lower()
    compact = _compact_english(text)
    for task_type, keywords in _TASK_TYPE_KEYWORDS:
        if any(keyword in normalized or _compact_english(keyword) in compact for keyword in keywords):
            return task_type
    return default


def extract_image_path_from_text(text: str) -> str | None:
    """Extract a likely local image path from a free-form user message."""
    match = _IMAGE_PATH_PATTERN.search(text)
    if match is None:
        return None
    return match.group("path").strip()


def _normalize_alias(value: str, alias_groups: dict[str, tuple[str, ...]]) -> str | None:
    normalized = value.strip()
    compact = _compact_english(normalized)
    compact_cn = _compact_chinese(normalized)
    for canonical, aliases in alias_groups.items():
        for alias in aliases:
            if compact == _compact_english(alias) or compact_cn == _compact_chinese(alias):
                return canonical
    return None


def _detect_alias_in_text(text: str, alias_groups: dict[str, tuple[str, ...]]) -> str | None:
    normalized = text.lower()
    compact = _compact_english(text)
    compact_cn = _compact_chinese(text)
    for canonical, aliases in alias_groups.items():
        if _aliases_present(aliases, normalized, compact, compact_cn):
            return canonical
    return None


def _aliases_present(
    aliases: Iterable[str],
    normalized_text: str,
    compact_text: str,
    compact_chinese_text: str,
) -> bool:
    for alias in aliases:
        alias_lower = alias.lower()
        if alias_lower in normalized_text:
            return True
        compact_alias = _compact_english(alias)
        if compact_alias and compact_alias in compact_text:
            return True
        compact_cn_alias = _compact_chinese(alias)
        if compact_cn_alias and compact_cn_alias in compact_chinese_text:
            return True
    return False


def _compact_english(value: str) -> str:
    lowered = value.lower().strip()
    replacements = (
        " province",
        " city",
        " autonomous region",
        " special administrative region",
        "_",
        "-",
        " ",
    )
    for token in replacements:
        lowered = lowered.replace(token, "")
    return lowered


def _compact_chinese(value: str) -> str:
    compact = value.strip().replace(" ", "")
    suffixes = (
        "特别行政区",
        "维吾尔自治区",
        "壮族自治区",
        "回族自治区",
        "自治区",
        "省",
        "市",
    )
    for suffix in suffixes:
        compact = compact.replace(suffix, "")
    return compact
