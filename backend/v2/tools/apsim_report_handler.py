"""APSIM crop simulation → self-contained HTML yield report tool."""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from v2.shared.schemas import ObservationV2, PackArtifactView
from v2.tools.apsim_adapter import (
    _CULTIVAR_MAP,
    _build_apsimx_from_template,
    _generate_met_file,
    _resolve_crop_model,
    _resolve_region_info,
    _run_apsim_simulation,
)

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PROJECT_ROOT = _BACKEND_ROOT.parent
_DEFAULT_REPORT_DIR = _PROJECT_ROOT / "reports"
_ENV_REPORT_DIR = os.environ.get("APSIM_REPORT_OUTPUT_DIR", "")

_STAGE_NAMES = {
    1: "出苗", 2: "分蘖", 3: "拔节", 4: "抽穗",
    5: "开花", 6: "灌浆", 7: "乳熟", 8: "蜡熟", 9: "完熟",
}

_DEMO_DB = (
    Path(__file__).resolve().parents[3]
    / "ApsimX" / "Tests" / "Validation" / "Wheat" / "GxExM" / "GxExM.db"
)


def _parse_db(db_path: Path, sim_id: int | None = None) -> dict[str, Any]:
    """Read time series from an ApsimX SQLite output file."""
    result: dict[str, Any] = {"dates": [], "lai": [], "biomass": [], "grain_wt": [], "stage": []}
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()

        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall() if not r[0].startswith("_")]

        daily_table = None
        for t in tables:
            cur.execute(f'PRAGMA table_info("{t}")')
            cols = [r[1] for r in cur.fetchall()]
            # prefer table that has both LAI and Grain
            if any("lai" in c.lower() for c in cols) and any("grain" in c.lower() for c in cols):
                daily_table = t
                break
        if not daily_table:
            for t in tables:
                cur.execute(f'PRAGMA table_info("{t}")')
                cols = [r[1] for r in cur.fetchall()]
                if any("lai" in c.lower() for c in cols):
                    daily_table = t
                    break
        if not daily_table and tables:
            daily_table = tables[0]

        if not daily_table:
            conn.close()
            return result

        cur.execute(f'PRAGMA table_info("{daily_table}")')
        col_names = [r[1] for r in cur.fetchall()]

        # Column heuristics
        def _find(keywords: list[str], exclude: list[str] | None = None) -> str | None:
            kw_low = [k.lower() for k in keywords]
            ex_low = [e.lower() for e in (exclude or [])]
            for c in col_names:
                cl = c.lower()
                if any(k in cl for k in kw_low) and not any(e in cl for e in ex_low):
                    return c
            return None

        date_col  = _find(["clock.today", "today", "date"])
        lai_col   = _find(["leaf.lai", ".lai", "lai"], exclude=["ndvi"])
        bio_col   = _find(["aboveground.wt", "aboveground.w", "biomass", "total.wt"])
        grain_col = _find(["grain.wt"])
        stage_col = _find(["phenology.stage", "stage"], exclude=["stagename", "currentstage"])

        # Pick simulation: either given sim_id, or the one with the highest max grain/biomass
        if "SimulationID" in col_names:
            if sim_id is None:
                grain_col_exists = grain_col and grain_col in col_names
                bio_col_exists = bio_col and bio_col in col_names
                rank_col = grain_col if grain_col_exists else (bio_col if bio_col_exists else None)
                if rank_col:
                    cur.execute(
                        f'SELECT SimulationID FROM "{daily_table}" GROUP BY SimulationID '
                        f'ORDER BY MAX("{rank_col}") DESC LIMIT 1'
                    )
                else:
                    cur.execute(f'SELECT DISTINCT SimulationID FROM "{daily_table}" LIMIT 1')
                row = cur.fetchone()
                sim_id = row[0] if row else None
            if sim_id is not None:
                cur.execute(f'SELECT * FROM "{daily_table}" WHERE SimulationID=? ORDER BY rowid', (sim_id,))
            else:
                cur.execute(f'SELECT * FROM "{daily_table}" ORDER BY rowid')
        else:
            cur.execute(f'SELECT * FROM "{daily_table}" ORDER BY rowid')

        rows = cur.fetchall()
        conn.close()

        for row in rows:
            d = dict(zip(col_names, row))
            result["dates"].append(str(d.get(date_col, "") or "")[:10])
            result["lai"].append(_safe_float(d.get(lai_col) if lai_col else 0))
            result["biomass"].append(_safe_float(d.get(bio_col) if bio_col else 0))
            result["grain_wt"].append(_safe_float(d.get(grain_col) if grain_col else 0))
            result["stage"].append(_safe_float(d.get(stage_col) if stage_col else 0))

    except Exception as exc:
        logger.warning("apsim_db_read_failed | %s", exc)
    return result


def _parse_timeseries(work_dir: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"dates": [], "lai": [], "biomass": [], "grain_wt": [], "stage": []}

    db_files = list(work_dir.glob("*.db"))
    if not db_files:
        # fallback: try CSV
        csv_files = list(work_dir.glob("*.csv"))
        for csv_path in csv_files:
            try:
                lines = csv_path.read_text(encoding="utf-8").strip().split("\n")
                if len(lines) < 2:
                    continue
                headers = [h.strip() for h in lines[0].split(",")]
                date_col = next((h for h in headers if "today" in h.lower() or h.lower() == "date"), None)
                lai_col = next((h for h in headers if "lai" in h.lower()), None)
                bio_col = next((h for h in headers if "biomass" in h.lower() or "bio" in h.lower()), None)
                grain_col = next((h for h in headers if "grain" in h.lower() and "wt" in h.lower()), None)
                stage_col = next((h for h in headers if "stage" in h.lower()), None)
                if not date_col:
                    continue
                for line in lines[1:]:
                    vals = [v.strip() for v in line.split(",")]
                    if len(vals) < len(headers):
                        continue
                    d = dict(zip(headers, vals))
                    result["dates"].append(str(d.get(date_col, ""))[:10])
                    result["lai"].append(_safe_float(d.get(lai_col, 0)))
                    result["biomass"].append(_safe_float(d.get(bio_col, 0)))
                    result["grain_wt"].append(_safe_float(d.get(grain_col, 0)))
                    result["stage"].append(_safe_float(d.get(stage_col, 0)))
                if result["dates"]:
                    break
            except Exception:
                logger.debug("apsim_csv_parse_failed", exc_info=True)
        return result

    db_path = db_files[0]
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall() if not row[0].startswith("_")]

        daily_table = None
        for t in tables:
            cursor.execute(f'PRAGMA table_info("{t}")')
            cols = [row[1] for row in cursor.fetchall()]
            if any("lai" in c.lower() or "LAI" in c for c in cols):
                daily_table = t
                break

        if not daily_table and tables:
            daily_table = tables[0]

        if daily_table:
            cursor.execute(f'PRAGMA table_info("{daily_table}")')
            col_names = [row[1] for row in cursor.fetchall()]
            cursor.execute(f'SELECT * FROM "{daily_table}"')
            rows = cursor.fetchall()

            date_col = next((c for c in col_names if "today" in c.lower() or c.lower() == "date"), None)
            lai_col = next((c for c in col_names if "lai" in c.lower() or c == "LAI"), None)
            bio_col = next((c for c in col_names if "biomass" in c.lower() or "bio" in c.lower()), None)
            grain_col = next((c for c in col_names if "grain" in c.lower() and "wt" in c.lower()), None)
            stage_col = next((c for c in col_names if "stage" in c.lower()), None)

            for row in rows:
                d = dict(zip(col_names, row))
                result["dates"].append(str(d.get(date_col, ""))[:10] if date_col else "")
                result["lai"].append(_safe_float(d.get(lai_col, 0) if lai_col else 0))
                result["biomass"].append(_safe_float(d.get(bio_col, 0) if bio_col else 0))
                result["grain_wt"].append(_safe_float(d.get(grain_col, 0) if grain_col else 0))
                result["stage"].append(_safe_float(d.get(stage_col, 0) if stage_col else 0))

        conn.close()
    except Exception as exc:
        logger.warning("apsim_db_parse_failed | %s", exc)

    return result


def _safe_float(v: Any) -> float:
    try:
        return round(float(v or 0), 4)
    except (TypeError, ValueError):
        return 0.0


def _build_report_data(ts: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    lai = ts["lai"]
    biomass = ts["biomass"]
    grain_wt = ts["grain_wt"]
    stage = ts["stage"]

    peak_lai = max(lai) if lai else 0.0
    max_biomass = max(biomass) if biomass else 0.0
    # Use max grain weight (harvest peak), not last-day value which may be 0 post-harvest
    final_grain = max(grain_wt) if grain_wt else 0.0
    # g/m² → t/ha: × 0.01
    final_yield_t_ha = round(final_grain * 0.01, 3)
    sim_days = len([d for d in ts["dates"] if d])

    # Downsample if too many points (keep ≤ 500)
    def _ds(lst: list, n: int = 500) -> list:
        if len(lst) <= n:
            return lst
        step = len(lst) / n
        return [lst[int(i * step)] for i in range(n)]

    n = len(ts["dates"])
    if n > 500:
        idx = [int(i * n / 500) for i in range(500)]
        ts_out = {k: [v[i] for i in idx] for k, v in ts.items()}
    else:
        ts_out = ts

    return {
        "meta": {
            "peak_lai": round(peak_lai, 3),
            "max_biomass": round(max_biomass, 1),
            "final_yield_t_ha": final_yield_t_ha,
            "sim_days": sim_days,
            **params,
        },
        "dates": ts_out["dates"],
        "lai": ts_out["lai"],
        "biomass": ts_out["biomass"],
        "grain_wt": ts_out["grain_wt"],
        "stage": ts_out["stage"],
    }


def _build_html(report_data: dict[str, Any]) -> str:
    inline_json = json.dumps(report_data, separators=(",", ":"), ensure_ascii=False)
    meta = report_data.get("meta", {})
    crop_type = meta.get("crop_type", "wheat")
    region = meta.get("region", "")
    start_year = meta.get("start_year", "")
    end_year = meta.get("end_year", "")
    cultivar = meta.get("cultivar", "—")
    peak_lai = meta.get("peak_lai", 0)
    max_biomass = meta.get("max_biomass", 0)
    final_yield = meta.get("final_yield_t_ha", 0)
    sim_days = meta.get("sim_days", 0)
    subtitle = f"{crop_type.upper()} · {region} · {start_year}~{end_year} · 品种 {cultivar}"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>APSIM 作物生长模拟报告 — {crop_type} {region}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:"Noto Sans SC","PingFang SC","Microsoft YaHei",sans-serif;background:#0f1117;color:#e0e6ef;min-height:100vh}}
.hdr{{background:linear-gradient(135deg,#1a2744 0%,#0d1b33 100%);padding:28px 32px;border-bottom:1px solid #1e3a5f}}
.hdr h1{{font-size:22px;font-weight:700;color:#e8f4ff}}
.hdr .sub{{margin-top:6px;font-size:13px;color:#7a9cbf}}
.wrap{{max-width:1100px;margin:0 auto;padding:24px 18px}}
.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:24px}}
@media(max-width:700px){{.cards{{grid-template-columns:repeat(2,1fr)}}}}
.card{{background:#141b2e;border:1px solid #1e3a5f;border-radius:10px;padding:16px 18px}}
.card .lbl{{font-size:11px;color:#7a9cbf;text-transform:uppercase;letter-spacing:.8px;margin-bottom:6px}}
.card .val{{font-size:26px;font-weight:700;color:#4fc3f7}}
.card .unit{{font-size:12px;color:#5a7fa0;margin-left:3px}}
.card .desc{{font-size:11px;color:#5a7fa0;margin-top:3px}}
.panel{{background:#141b2e;border:1px solid #1e3a5f;border-radius:10px;padding:18px;margin-bottom:18px}}
.ptitle{{font-size:12px;font-weight:600;color:#7a9cbf;margin-bottom:14px;text-transform:uppercase;letter-spacing:.8px}}
.tabs{{display:flex;gap:0;margin-bottom:16px;background:#0f1117;border-radius:7px;padding:3px}}
.tab{{flex:1;padding:7px 10px;text-align:center;font-size:12px;cursor:pointer;border-radius:5px;color:#5a7fa0;transition:all .15s}}
.tab.on{{background:#1e3a5f;color:#4fc3f7;font-weight:600}}
canvas{{display:block;width:100%!important}}
.sbar{{display:flex;height:26px;border-radius:6px;overflow:hidden;margin-top:8px}}
.sseg{{display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:600;overflow:hidden;white-space:nowrap;padding:0 3px}}
.pgrid{{display:grid;grid-template-columns:repeat(2,1fr);gap:7px}}
@media(max-width:600px){{.pgrid{{grid-template-columns:1fr}}}}
.prow{{display:flex;justify-content:space-between;padding:7px 11px;background:#0f1117;border-radius:6px;font-size:12px}}
.pk{{color:#7a9cbf}}.pv{{color:#c8d8f0;font-weight:500}}
</style>
</head>
<body>
<div class="hdr">
  <h1>🌾 APSIM 作物生长模拟报告</h1>
  <div class="sub">{subtitle}</div>
</div>
<div class="wrap">
  <div class="cards">
    <div class="card"><div class="lbl">估算产量</div>
      <div class="val">{final_yield:.3f}<span class="unit">t/ha</span></div>
      <div class="desc">子粒最终干重换算</div></div>
    <div class="card"><div class="lbl">峰值 LAI</div>
      <div class="val">{peak_lai:.3f}<span class="unit">m²/m²</span></div>
      <div class="desc">最大叶面积指数</div></div>
    <div class="card"><div class="lbl">最大生物量</div>
      <div class="val">{max_biomass:.0f}<span class="unit">g/m²</span></div>
      <div class="desc">地上部总干重峰值</div></div>
    <div class="card"><div class="lbl">有效天数</div>
      <div class="val">{sim_days}<span class="unit">天</span></div>
      <div class="desc">模拟记录天数</div></div>
  </div>

  <div class="panel">
    <div class="ptitle">生长曲线</div>
    <div class="tabs">
      <div class="tab on" onclick="showTab(0)">LAI 时序</div>
      <div class="tab" onclick="showTab(1)">生物量</div>
      <div class="tab" onclick="showTab(2)">子粒重</div>
    </div>
    <canvas id="chart" height="280"></canvas>
  </div>

  <div class="panel">
    <div class="ptitle">生长阶段时间轴</div>
    <div class="sbar" id="sbar"></div>
    <div style="display:flex;gap:14px;margin-top:8px;flex-wrap:wrap;font-size:11px" id="sleg"></div>
  </div>

  <div class="panel">
    <div class="ptitle">模拟参数</div>
    <div class="pgrid" id="pgrid"></div>
  </div>
</div>

<script>
const D = {inline_json};
const SC = ['#2563a8','#0d9488','#059669','#7c3aed','#b45309','#dc2626','#0891b2','#9333ea','#1d6fa8','#065f46'];
const SN = {{1:'出苗',2:'分蘖',3:'拔节',4:'抽穗',5:'开花',6:'灌浆',7:'乳熟',8:'蜡熟',9:'完熟',10:'收获'}};
let curTab = 0;

function showTab(i) {{
  curTab = i;
  document.querySelectorAll('.tab').forEach((t,j) => t.classList.toggle('on', i===j));
  drawChart();
}}

function drawChart() {{
  const cv = document.getElementById('chart');
  const ctx = cv.getContext('2d');
  const W = cv.offsetWidth; const H = 280;
  cv.width = W; cv.height = H;
  const [series, lbl, col, unit] = [
    [D.lai,'LAI','#4fc3f7','m²/m²'],
    [D.biomass,'生物量','#34d399','g/m²'],
    [D.grain_wt,'子粒重','#f59e0b','g/m²'],
  ][curTab];
  const pad = {{l:54,r:16,t:18,b:46}};
  const pw = W-pad.l-pad.r, ph = H-pad.t-pad.b;
  ctx.clearRect(0,0,W,H);
  ctx.fillStyle='#141b2e'; ctx.fillRect(0,0,W,H);
  const valid = series.filter(v=>v>0);
  const mx = valid.length ? Math.max(...valid)*1.08 : 1;
  // grid
  for(let i=0;i<=4;i++) {{
    const y = pad.t+ph-(i/4)*ph;
    ctx.strokeStyle='#1e3a5f'; ctx.lineWidth=1;
    ctx.beginPath(); ctx.moveTo(pad.l,y); ctx.lineTo(pad.l+pw,y); ctx.stroke();
    ctx.fillStyle='#4a6a8a'; ctx.font='10px sans-serif'; ctx.textAlign='right';
    ctx.fillText((mx*i/4).toFixed(mx<10?2:0), pad.l-4, y+3);
  }}
  // x labels
  ctx.fillStyle='#4a6a8a'; ctx.font='10px sans-serif'; ctx.textAlign='center';
  const xs = Math.max(1, Math.floor(D.dates.length/7));
  for(let i=0;i<D.dates.length;i+=xs) {{
    ctx.fillText((D.dates[i]||'').slice(5), pad.l+(i/(D.dates.length-1||1))*pw, H-pad.b+13);
  }}
  // line + fill
  ctx.beginPath(); ctx.strokeStyle=col; ctx.lineWidth=2;
  let first=true;
  for(let i=0;i<series.length;i++) {{
    const x=pad.l+(i/(series.length-1||1))*pw;
    const y=pad.t+ph-(series[i]/mx)*ph;
    first?(ctx.moveTo(x,y),first=false):ctx.lineTo(x,y);
  }}
  ctx.stroke();
  const lx=pad.l+(series.length-1)/(series.length-1||1)*pw;
  ctx.lineTo(lx,pad.t+ph); ctx.lineTo(pad.l,pad.t+ph); ctx.closePath();
  ctx.fillStyle=col+'1a'; ctx.fill();
  ctx.fillStyle=col; ctx.font='bold 11px sans-serif'; ctx.textAlign='left';
  ctx.fillText(lbl+' ('+unit+')', pad.l+4, pad.t+14);
}}

function drawStageBar() {{
  const stages = D.stage;
  if(!stages.length) return;
  const bar = document.getElementById('sbar');
  const leg = document.getElementById('sleg');
  const segs=[]; let cur=Math.floor(stages[0]), st=0;
  for(let i=1;i<stages.length;i++) {{
    const s=Math.floor(stages[i]);
    if(s!==cur){{ segs.push({{s:cur,a:st,b:i}}); cur=s; st=i; }}
  }}
  segs.push({{s:cur,a:st,b:stages.length}});
  bar.innerHTML=segs.map(s=>{{
    const w=((s.b-s.a)/stages.length*100).toFixed(1);
    const c=SC[s.s%SC.length], n=SN[s.s]||('S'+s.s);
    return `<div class="sseg" style="width:${{w}}%;background:${{c}};color:#fff">${{w>5?n:''}}</div>`;
  }}).join('');
  const seen=new Set();
  leg.innerHTML=segs.filter(s=>!seen.has(s.s)&&seen.add(s.s)).map(s=>{{
    const c=SC[s.s%SC.length], n=SN[s.s]||('Stage '+s.s);
    const d1=(D.dates[s.a]||'').slice(5), d2=(D.dates[Math.min(s.b,D.dates.length-1)]||'').slice(5);
    return `<span style="color:#7a9cbf"><span style="display:inline-block;width:9px;height:9px;background:${{c}};border-radius:2px;margin-right:3px"></span>${{n}} ${{d1}}–${{d2}}</span>`;
  }}).join('');
}}

function drawParams() {{
  const m = D.meta||{{}};
  const rows = [
    ['作物类型', m.crop_type||'—'],['品种', m.cultivar||'—'],
    ['模拟区域', m.region||'—'],['气象站', m.station||'—'],
    ['纬度 / 经度', (m.latitude||'?')+'°N / '+(m.longitude||'?')+'°E'],
    ['模拟期', (m.start_year||'?')+' ~ '+(m.end_year||'?')],
    ['播种日', m.sowing_doy?'第 '+m.sowing_doy+' 天':'—'],
    ['峰值 LAI', (m.peak_lai||0).toFixed(3)+' m²/m²'],
    ['最大生物量', (m.max_biomass||0).toFixed(0)+' g/m²'],
    ['估算产量', (m.final_yield_t_ha||0).toFixed(3)+' t/ha'],
  ];
  document.getElementById('pgrid').innerHTML=rows.map(([k,v])=>
    `<div class="prow"><span class="pk">${{k}}</span><span class="pv">${{v}}</span></div>`
  ).join('');
}}

window.addEventListener('load',()=>{{ drawChart(); drawStageBar(); drawParams(); }});
window.addEventListener('resize',()=>drawChart());
</script>
</body>
</html>"""


def _apsim_bin_available() -> bool:
    from v2.tools.apsim_adapter import _APSIM_MODELS_BIN
    return Path(_APSIM_MODELS_BIN).exists()


def _finish_report(
    ts: dict[str, Any],
    params: dict[str, Any],
    *,
    crop_type: str,
    region: str,
    start_year: int,
    note: str = "",
) -> tuple[ObservationV2, list[PackArtifactView]]:
    report_data = _build_report_data(ts, params)
    html = _build_html(report_data)
    out_dir = Path(_ENV_REPORT_DIR) if _ENV_REPORT_DIR else _DEFAULT_REPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    ts_stamp = int(time.time())
    filename = f"apsim_report_{crop_type}_{region}_{ts_stamp}.html"
    (out_dir / filename).write_text(html, encoding="utf-8")
    meta = report_data["meta"]
    suffix = f"  {note}" if note else ""
    logger.info("apsim_yield_report_saved | %s", filename)
    return (
        ObservationV2(
            source="apsim.yield_report",
            status="success",
            summary=(
                f"APSIM 产量报告生成完成。作物: {params.get('crop_model', crop_type)}，"
                f"估算产量: {meta['final_yield_t_ha']:.3f} t/ha，"
                f"峰值 LAI: {meta['peak_lai']:.3f}，模拟 {meta['sim_days']} 天。{suffix}"
            ),
            payload=meta,
        ),
        [
            PackArtifactView(
                pack_name="apsim",
                artifact_type="apsim_report",
                title=f"APSIM 产量模拟报告 — {crop_type.upper()} {region} {start_year}",
                content=json.dumps(meta, ensure_ascii=False),
                uri=f"/v2/reports/{filename}",
            )
        ],
    )


def run_apsim_yield_report(
    *,
    crop_type: str = "wheat",
    region: str = "henan",
    start_year: int | None = None,
    end_year: int | None = None,
    cultivar: str | None = None,
    sowing_date: str | None = None,
    db_path: str | None = None,
    query: str | None = None,
    **_unused: object,
) -> tuple[ObservationV2, list[PackArtifactView]]:
    """Run APSIM crop simulation and generate a self-contained HTML yield report.

    Args:
        crop_type:   Crop name (wheat, maize, soybean, …)
        region:      Region key (henan, shandong, …)
        start_year:  Simulation start year (defaults to last year)
        end_year:    Simulation end year (defaults to current year)
        cultivar:    Cultivar name (uses regional default if omitted)
        sowing_date: ISO date string for sowing (e.g. "2024-10-15")
        db_path:     Path to an existing ApsimX .db output file. If provided,
                     skip running a new simulation and read data directly.
        query:       Original user query (kept for interface compatibility)
    """
    # --- Mode A: read from existing .db file (no simulation needed) ---
    if db_path or (_DEMO_DB.exists() and not _apsim_bin_available()):
        resolved_db = Path(db_path).expanduser().resolve() if db_path else _DEMO_DB
        if not resolved_db.exists():
            return (
                ObservationV2(
                    source="apsim.yield_report",
                    status="error",
                    summary=f"指定的 .db 文件不存在: {resolved_db}",
                    payload={"db_path": str(resolved_db)},
                ),
                [],
            )
        ts = _parse_db(resolved_db)
        if not ts["dates"]:
            return (
                ObservationV2(
                    source="apsim.yield_report",
                    status="error",
                    summary=f"无法从 {resolved_db.name} 读取日报数据，请确认文件包含带 LAI 列的日报表",
                    payload={"db_path": str(resolved_db)},
                ),
                [],
            )
        # Infer metadata from db path / filename
        db_name = resolved_db.stem
        _ct = crop_type or ("maize" if "maize" in db_name.lower() else "wheat")
        _region = region or "demo"
        _cy = start_year or datetime.now().year - 1
        _ey = end_year or datetime.now().year
        _cv = cultivar or "GxExM"
        params: dict[str, Any] = {
            "crop_type": _ct, "crop_model": _ct.capitalize(),
            "cultivar": _cv, "region": _region, "station": "Demo",
            "latitude": "—", "longitude": "—",
            "start_year": _cy, "end_year": _ey, "sowing_doy": "—",
            "data_source": resolved_db.name,
        }
        return _finish_report(ts, params, crop_type=_ct, region=_region,
                              start_year=_cy, note=f"数据来源: {resolved_db.name}")

    # --- Mode B: run a fresh simulation ---
    current_year = datetime.now().year
    if start_year is None:
        start_year = current_year - 1
    if end_year is None:
        end_year = current_year

    crop_model = _resolve_crop_model(crop_type)
    region_info = _resolve_region_info(region)
    latitude = region_info["latitude"]
    longitude = region_info["longitude"]
    station = region_info["station"]
    tav = region_info.get("tav", 14.5)
    amp = region_info.get("amp", 13.0)

    if cultivar is None:
        cultivar = _CULTIVAR_MAP.get(crop_model, "Yitpi")

    sowing_doy = 288
    if sowing_date:
        try:
            parts = sowing_date.split("-")
            month, day = int(parts[1]), int(parts[2])
            days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
            sowing_doy = sum(days_in_month[: month - 1]) + day
        except Exception:
            logger.debug("apsim_report_sowing_date_parse_failed", exc_info=True)

    work_dir = Path(tempfile.mkdtemp(prefix="apsim_rpt_"))
    t0 = time.time()
    try:
        met_path = _generate_met_file(
            work_dir, station, latitude, longitude, tav, amp, start_year, end_year
        )

        apsimx_path = _build_apsimx_from_template(
            work_dir,
            crop_model,
            str(met_path),
            f"{start_year}-01-01",
            f"{end_year}-12-31",
            cultivar,
            sowing_doy,
        )

        success, output = _run_apsim_simulation(apsimx_path, work_dir)

        if not success:
            return (
                ObservationV2(
                    source="apsim.yield_report",
                    status="error",
                    summary=f"APSIM 模拟失败: {output[:300]}",
                    payload={"crop_type": crop_type, "region": region, "error": output[:500]},
                ),
                [],
            )

        ts = _parse_timeseries(work_dir)

        if not ts["dates"]:
            return (
                ObservationV2(
                    source="apsim.yield_report",
                    status="error",
                    summary="APSIM 模拟完成但未解析到输出数据，请检查模板 .apsimx 中的 Report 节点配置",
                    payload={"crop_type": crop_type, "region": region},
                ),
                [],
            )

        params: dict[str, Any] = {
            "crop_type": crop_type,
            "crop_model": crop_model,
            "cultivar": cultivar,
            "region": region,
            "station": station,
            "latitude": latitude,
            "longitude": longitude,
            "start_year": start_year,
            "end_year": end_year,
            "sowing_doy": sowing_doy,
        }
        elapsed = round(time.time() - t0, 1)
        return _finish_report(ts, params, crop_type=crop_type, region=region,
                              start_year=start_year, note=f"模拟耗时 {elapsed}s")

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
