"""Shared visual template for self-contained map analysis reports."""

from __future__ import annotations

import html
import math
from typing import Any


_CSS = """
*{box-sizing:border-box}html{font-size:16px}body{margin:0;background:#f5f4f0;color:#1a1a18;font-family:'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;line-height:1.55}
.page{max-width:1000px;margin:0 auto;padding:2rem 2rem 4rem}.report-header{border-bottom:1px solid #d8d6cc;padding-bottom:1.2rem;margin-bottom:1.8rem}
.badge,.section-label,.mono,.panel-hint,.footer{font-family:'Courier New',monospace}.badge{display:inline-block;font-size:10px;letter-spacing:.12em;background:#eceae3;border:1px solid #ccc9be;border-radius:4px;padding:2px 8px;color:#666;margin-bottom:.6rem}
h1{font-size:24px;line-height:1.3;font-weight:600;margin:0 0 .3rem;color:#111}.sub{font-size:13px;color:#777;overflow-wrap:anywhere}.section-label{font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:#aaa;margin:1.55rem 0 .65rem}
.stats-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.stat-card{background:#eceae3;border-radius:8px;padding:.85rem 1rem;min-height:84px}.stat-card .label{font-size:11px;color:#777;margin-bottom:5px}.stat-card .value{font:500 22px/1.25 'Courier New',monospace;overflow-wrap:anywhere}.stat-card .unit{font:11px 'Courier New',monospace;color:#777;margin-left:4px}
.panel{background:#fff;border:1px solid #dddbd2;border-radius:12px;overflow:hidden;margin-bottom:12px}.panel-head{padding:.65rem 1rem;border-bottom:1px solid #eceae3;display:flex;justify-content:space-between;gap:12px;align-items:baseline;background:#faf9f7}.panel-title{font-size:13px;font-weight:600}.panel-hint{font-size:11px;color:#aaa}.panel-body{padding:1rem}.bar-row{display:grid;grid-template-columns:minmax(90px,145px) 1fr 58px;align-items:center;gap:12px;margin:.45rem 0}.bar-label{font-size:12px;color:#444}.bar-track{height:9px;background:#eeede7;border-radius:999px;overflow:hidden}.bar-fill{height:100%;background:#29955d;border-radius:999px}.bar-row:first-child .bar-fill{background:#176d43}.bar-value{text-align:right;font:12px 'Courier New',monospace;color:#555}
.data-table{width:100%;border-collapse:collapse}.data-table th,.data-table td{padding:8px 6px;border-bottom:1px solid #f0efe9;vertical-align:top;text-align:left;font-size:12px}.data-table th{width:31%;color:#777;font-weight:500}.data-table td{color:#333;overflow-wrap:anywhere}.data-table tr:last-child th,.data-table tr:last-child td{border:0}
.note-list{margin:0;padding:0;list-style:none}.note-list li{font-size:12px;color:#6a5623;line-height:1.65;padding:.45rem .7rem;margin:.4rem 0;background:#fdf8e8;border-left:3px solid #d6b74a;border-radius:4px}.note-list li:first-child{margin-top:0}.note-list li:last-child{margin-bottom:0}
.context-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));column-gap:24px}.context-item{padding:.5rem 0;border-bottom:1px solid #f0efe9;min-width:0}.context-key{font-size:10px;color:#999;letter-spacing:.06em}.context-value{font-size:12px;color:#444;overflow-wrap:anywhere}.status-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:8px}.status-card{padding:.75rem;border:1px solid #dddbd2;border-radius:8px;background:#faf9f7}.status-card .name{font-size:11px;color:#777}.status-card .state{font:500 20px 'Courier New',monospace;margin-top:4px}.status-card.ok{background:#eaf4e8;border-color:#b8ddb5}.status-card.warn{background:#fdf8e8;border-color:#f0e4b0}.status-card.fail{background:#fbeeee;border-color:#efcccc}
.footer{display:flex;justify-content:space-between;gap:16px;border-top:1px solid #d8d6cc;padding-top:1rem;margin-top:2rem;font-size:10px;color:#999}.empty{font-size:12px;color:#999}
@media(max-width:700px){.page{padding:1.2rem 1rem 3rem}.stats-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.context-grid{grid-template-columns:1fr}.bar-row{grid-template-columns:90px 1fr 48px;gap:8px}.panel-hint{display:none}}
@media print{body{background:#fff}.page{max-width:none;padding:0}.panel,.stat-card{break-inside:avoid}.footer{margin-top:1rem}}
"""


def _safe(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _panel(title: str, hint: str, body: str) -> str:
    return (f"<section class='panel'><div class='panel-head'><span class='panel-title'>{title}</span>"
            f"<span class='panel-hint'>{hint}</span></div><div class='panel-body'>{body}</div></section>")


def render_report(payload: dict[str, Any]) -> str:
    """Render LAI-style header, statistics, charts, details, and provenance."""
    kind = payload.get("kind")
    badge = {"crop_classification_report": "KDD2020 · 作物识别",
             "growth_observation_report": "SENTINEL-2 · 长势观测",
             "canopy_index_report": "NDVI + LAI · 冠层状态",
             "apsim_report": "APSIM NG · 地块情景",
             "workflow_summary_report": "MAP WORKSPACE · 综合分析"}.get(kind, "遥感分析 · 结果报告")
    context = payload["context"]
    subtitle = " · ".join(str(context[key]) for key in ("观测日期", "LAI 观测日期", "选区面积", "影像 ID")
                          if context.get(key))
    stats = "".join(
        f"<div class='stat-card'><div class='label'>{_safe(item['label'])}</div>"
        f"<div class='value'>{_safe(item['value'])}<span class='unit'>{_safe(item.get('unit', ''))}</span></div></div>"
        for item in payload.get("highlights", [])
    )
    visuals = []
    for visual in payload.get("visuals", []):
        if visual.get("type") == "bars":
            bars = []
            for item in visual.get("items", []):
                raw = item.get("value", 0)
                width = min(100.0, max(0.0, float(raw) * 100)) if isinstance(raw, (int, float)) and math.isfinite(raw) else 0.0
                bars.append(
                    f"<div class='bar-row'><div class='bar-label'>{_safe(item.get('label', ''))}</div>"
                    f"<div class='bar-track' role='img' aria-label='{_safe(item.get('label', ''))} {_safe(item.get('display', ''))}'>"
                    f"<div class='bar-fill' style='width:{width:.2f}%'></div></div>"
                    f"<div class='bar-value'>{_safe(item.get('display', ''))}</div></div>"
                )
            visuals.append(_panel(_safe(visual.get("title", "结果分布")),
                                  _safe(visual.get("hint", "")), "".join(bars)))
        elif visual.get("type") == "statuses":
            cards = []
            for item in visual.get("items", []):
                state = str(item.get("state", ""))
                tone = "ok" if state == "completed" else "fail" if state == "failed" else "warn"
                display = {"completed": "完成", "blocked": "待补充", "failed": "失败",
                           "planned": "等待", "running": "执行中"}.get(state, state)
                cards.append(f"<div class='status-card {tone}'><div class='name'>{_safe(item.get('label', ''))}</div>"
                             f"<div class='state'>{_safe(display)}</div></div>")
            visuals.append(_panel(_safe(visual.get("title", "任务状态")), "",
                                  f"<div class='status-grid'>{''.join(cards)}</div>"))
    context_html = "".join(
        f"<div class='context-item'><div class='context-key'>{_safe(key)}</div>"
        f"<div class='context-value'>{_safe(value)}</div></div>"
        for key, value in context.items() if value is not None
    )
    sections = []
    for section in payload["sections"]:
        rows = "".join(f"<tr><th>{_safe(label)}</th><td>{_safe(value)}</td></tr>"
                       for label, value in section.get("rows", []))
        notes = "".join(f"<li>{_safe(note)}</li>" for note in section.get("notes", []) if note)
        body = f"<table class='data-table'>{rows}</table>" if rows else ""
        body += f"<ul class='note-list'>{notes}</ul>" if notes else ""
        sections.append(_panel(_safe(section["title"]), "", body or "<p class='empty'>暂无数据</p>"))
    highlights_html = ("<div class='section-label'>核心结果</div><div class='stats-grid'>"
                       + stats + "</div>") if stats else ""
    visuals_html = "<div class='section-label'>结果分布与质量</div>" + "".join(visuals) if visuals else ""
    source_html = _panel("分析来源", "", f"<div class='context-grid'>{context_html}</div>")
    return ("<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{_safe(payload['title'])}</title><style>{_CSS}</style></head><body>"
            f"<main class='page'><header class='report-header'><div class='badge'>{_safe(badge)}</div>"
            f"<h1>{_safe(payload['title'])}</h1><div class='sub'>{_safe(subtitle)}</div></header>"
            f"{highlights_html}{visuals_html}<div class='section-label'>分析详情</div>{''.join(sections)}"
            f"<div class='section-label'>数据来源与复现</div>{source_html}"
            f"<footer class='footer'><span>KTP · 遥感分析工作台</span>"
            f"<span>{_safe(payload['report_version'])}</span></footer></main></body></html>")
