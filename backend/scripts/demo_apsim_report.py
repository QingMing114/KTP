"""Generate a presentation-ready APSIM report from the bundled validation data.

Run from the repository root:

    python backend/scripts/demo_apsim_report.py --open
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
WORKSPACE_ROOT = PROJECT_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))


def _default_demo_db() -> Path:
    relative = Path("ApsimX/Tests/Validation/Wheat/GxExM/GxExM.db")
    candidates = (PROJECT_ROOT / relative, WORKSPACE_ROOT / relative)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    searched = "\n".join(f"  - {path}" for path in candidates)
    raise FileNotFoundError(f"未找到 APSIM 演示数据库，已检查：\n{searched}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="使用仓库自带的 APSIM Wheat GxExM 数据生成交互式 HTML 报告。"
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        help="可选：指定另一个 APSIM SQLite 输出文件。",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "reports",
        help="报告输出目录（默认：项目 reports/）。",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="生成完成后用默认浏览器打开报告（Windows）。",
    )
    args = parser.parse_args()

    db_path = args.db_path.resolve() if args.db_path else _default_demo_db()
    if not db_path.is_file():
        parser.error(f"APSIM 数据库不存在：{db_path}")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    os.environ["APSIM_REPORT_OUTPUT_DIR"] = str(output_dir)

    # Import after setting APSIM_REPORT_OUTPUT_DIR: the handler reads it at import time.
    from v2.tools.apsim_report_handler import run_apsim_yield_report

    observation, artifacts = run_apsim_yield_report(
        crop_type="wheat",
        region="australia-gxexm",
        start_year=2014,
        end_year=2015,
        cultivar="Hartog",
        db_path=str(db_path),
        query="生成一个可展示的 APSIM 小麦生长与产量报告",
    )

    if observation.status != "success" or not artifacts:
        print(f"生成失败：{observation.summary}", file=sys.stderr)
        return 1

    report_name = Path(artifacts[0].uri).name
    report_path = output_dir / report_name
    print(observation.summary)
    print(f"报告文件：{report_path}")
    print(f"数据来源：{db_path}")

    if args.open:
        if not hasattr(os, "startfile"):
            print("--open 当前仅支持 Windows；请手动打开上面的报告文件。")
        else:
            os.startfile(report_path)  # type: ignore[attr-defined]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
