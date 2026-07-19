"""Chart context builder for report templates.

Generates structured data for inline SVG charts rendered in report.html.j2.
"""

from __future__ import annotations

from typing import Any

from services.report_service.schemas import ReportRequest


# Class distribution color palette (consistent with visualization service)
_CLASS_PALETTE: dict[int, str] = {
    0: "#7b8b8b",   # background – grey
    1: "#e07a2f",   # baldness / target – orange
    2: "#2d6a9f",   # water – blue
    3: "#4a9e5c",   # non-crop vegetation – green
    4: "#b5963a",   # sorghum – gold
}


def build_chart_context(request: ReportRequest) -> dict[str, Any]:
    """Build chart-ready context dictionaries for the report template.

    Returns a dict with keys consumed by ``report.html.j2``:
    - class_distribution_chart: list of bar descriptors
    - confidence_gauge: gauge descriptor for the final confidence score
    - area_breakdown: affected-area summary
    - sensors: sensor / weather metadata
    - positive_analysis / negative_analysis: dual-perspective analysis text
    - prescriptions: agricultural prescription texts
    - est_loss: estimated loss string
    - pixel_to_mu_ratio: pixel-to-mu conversion factor
    - gis_coords: GIS viewport center coordinates
    """
    extra = request.extra_metadata or {}
    return {
        "class_distribution_chart": _build_class_distribution_chart(request),
        "confidence_gauge": _build_confidence_gauge(request),
        "area_breakdown": _build_area_breakdown(request),
        "sensors": _build_sensors(request, extra),
        "positive_analysis": extra.get("positive_analysis", ""),
        "negative_analysis": extra.get("negative_analysis", ""),
        "prescriptions": _build_prescriptions(extra),
        "est_loss": extra.get("est_loss", ""),
        "pixel_to_mu_ratio": extra.get("pixel_to_mu_ratio", 0.1),
        "gis_coords": _build_gis_coords(request),
    }


def _build_class_distribution_chart(request: ReportRequest) -> list[dict[str, Any]]:
    """Return a list of bar descriptors for the class distribution SVG chart."""
    if request.inference is None:
        return []

    # Build from inference polygons / class data if available
    # The inference section carries model_name, affected_area, confidence, etc.
    # Class distribution details come from extra_metadata if populated.
    extra = request.extra_metadata or {}
    class_distribution = extra.get("class_distribution", [])
    class_labels = extra.get("class_labels", {})
    target_classes = set(extra.get("target_classes", []))

    if not class_distribution:
        # Fallback: single target bar from inference.affected_area
        if request.inference.affected_area > 0:
            return [
                {
                    "label": "斑秃区域",
                    "value": request.inference.affected_area,
                    "ratio": 1.0,
                    "color": _CLASS_PALETTE.get(1, "#e07a2f"),
                    "is_target": True,
                }
            ]
        return []

    bars: list[dict[str, Any]] = []
    max_count = max((item.get("count", 0) for item in class_distribution), default=1) or 1
    for item in class_distribution:
        class_value = int(item.get("class_value", 0))
        label = item.get("label") or class_labels.get(str(class_value), f"类别_{class_value}")
        count = int(item.get("count", 0))
        ratio = float(item.get("ratio", 0.0))
        bars.append(
            {
                "label": label,
                "value": count,
                "ratio": ratio,
                "color": _CLASS_PALETTE.get(class_value, "#999999"),
                "is_target": class_value in target_classes,
                "bar_height_pct": round(count / max_count * 100, 1),
            }
        )
    return bars


def _build_confidence_gauge(request: ReportRequest) -> dict[str, Any]:
    """Return a gauge descriptor for the final confidence score."""
    if request.confidence is None:
        # Fallback to inference confidence
        if request.inference is not None:
            value = request.inference.confidence
            return _gauge_descriptor(value, "推理置信度")
        return {"available": False}

    value = request.confidence.final_confidence
    label = request.confidence.final_label
    return _gauge_descriptor(value, label)


def _gauge_descriptor(value: float, label: str) -> dict[str, Any]:
    """Create a normalized gauge descriptor."""
    pct = max(0.0, min(1.0, value))
    if pct >= 0.8:
        level = "high"
        color = "#2d6a4f"
    elif pct >= 0.5:
        level = "medium"
        color = "#b5963a"
    else:
        level = "low"
        color = "#8d3740"
    return {
        "available": True,
        "value": round(pct, 4),
        "percent": round(pct * 100, 1),
        "label": label,
        "level": level,
        "color": color,
        "arc_dash": round(pct * 251.2, 1),  # 251.2 ≈ 2π×40 (SVG arc radius 40)
    }


def _build_area_breakdown(request: ReportRequest) -> dict[str, Any]:
    """Return affected-area breakdown for the report."""
    if request.inference is None:
        return {"available": False}

    affected = request.inference.affected_area
    positive_ratio = request.inference.positive_ratio

    return {
        "available": True,
        "affected_pixels": int(affected),
        "positive_ratio": round(positive_ratio, 4) if positive_ratio is not None else None,
        "positive_pct": round(positive_ratio * 100, 1) if positive_ratio is not None else None,
        "polygon_count": len(request.inference.polygons),
    }


# ── Sensor / weather metadata ──

_DEFAULT_SENSORS: dict[str, str] = {
    "opt": "Sentinel-2 MSI (10M)",
    "sar": "Sentinel-1 C-SAR (VV/VH)",
    "gdd": "+42.5 ℃·d (偏旺)",
    "sm": "24.8 % (适墒)",
}


def _build_sensors(request: ReportRequest, extra: dict) -> dict[str, str]:
    """Return sensor / weather metadata for the report header cards."""
    sensors = extra.get("sensors", {})
    return {key: sensors.get(key, _DEFAULT_SENSORS.get(key, "")) for key in _DEFAULT_SENSORS}


# ── Agricultural prescriptions ──

_DEFAULT_PRESCRIPTIONS: dict[str, str] = {
    "p1": "该区域作物新陈代谢活跃，当前无需额外的微量元素干预。宜贯彻既定长效底肥控释策略，根据气象周期，在后期灌浆期执行常态微湿灌溉，防范水分饱和引起根系自呼吸受阻，力争巩固原有丰产根基。",
    "p2": "由于光谱叶绿素反射波谷抬升，该带表现出明显的生理亚健康。须启动多旋翼无人植保机组对特定坐标地块进行变量追施速效尿素 6-8 公斤/亩，并在日落前灌溉浅水促根，打破养分输送物理瓶颈。",
    "p3": "对应反射区近红外陡落，水气吸收指数干枯。怀疑已遭受大面积侵染或物理性坏死，需要立刻调配高浓广谱高效药剂（如三环唑/吡唑醚菌酯）进行局部封闭式喷洒，杜绝大田级交叉感染损耗。",
}


def _build_prescriptions(extra: dict) -> dict[str, str]:
    """Return agricultural prescription texts."""
    prescriptions = extra.get("prescriptions", {})
    return {key: prescriptions.get(key, _DEFAULT_PRESCRIPTIONS.get(key, "")) for key in _DEFAULT_PRESCRIPTIONS}


# ── GIS viewport coordinates ──

_GIS_COORDS: dict[str, str] = {
    "henan": "34.0294° N, 113.4829° E",
    "shandong": "36.7868° N, 116.9972° E",
    "heilongjiang": "47.3421° N, 132.3698° E",
    "jilin": "43.8868° N, 125.3245° E",
    "hunan": "28.2282° N, 111.6943° E",
    "yunnan": "25.0453° N, 102.7097° E",
}


def _build_gis_coords(request: ReportRequest) -> str:
    """Return GIS viewport center coordinates based on region."""
    region = (request.region or "").lower()
    return _GIS_COORDS.get(region, "34.0294° N, 113.4829° E")
