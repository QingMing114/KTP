"""Refresh saved LAI report display data, retaining URLs and inversion results.

Run with --apply after reviewing the default dry-run result. Every replaced
HTML file and affected artifact metadata record is backed up first.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3

from v2.tools.lai_report_data import prepare_report_data
from v2.tools.lai_report_handler import _build_html


INLINE = re.compile(r"const __INLINE_DATA__ = (.*?);\s*async function loadData", re.S)


def refresh_reports(reports_dir: Path, backup_dir: Path, db_path: Path | None = None,
                    artifact_root: Path | None = None, *, apply: bool = False) -> dict:
    sources = {}
    db = sqlite3.connect(db_path) if db_path else None
    if db and artifact_root:
        for (payload,) in db.execute("SELECT payload_json FROM product_analysis_workflows"):
            workflow = json.loads(payload)
            for step in workflow["steps"]:
                path = step.get("result", {}).get("report_path")
                if step["step_id"] == "lai" and path:
                    sources[Path(path).name] = artifact_root / "workflows" / workflow["workflow_id"] / "reflectance.tif"
    updated, skipped, hashes = [], [], {}
    for path in sorted(reports_dir.glob("lai_report_*.html")):
        html = path.read_text(encoding="utf-8")
        match = INLINE.search(html)
        if not match:
            skipped.append(path.name)
            continue
        data = json.loads(match.group(1))
        if data["meta"].get("pixel_data_version") == 2:
            continue
        data = prepare_report_data(data)
        source = sources.get(path.name)
        if source and source.is_file():
            import rasterio
            with rasterio.open(source) as src:
                data["meta"].update(transform=list(src.transform)[:6], crs=src.crs.to_string(),
                                     resolution=list(src.res), coordinate_unit="m" if src.crs.is_projected and src.crs.linear_units == "metre" else "°" if src.crs.is_geographic else None)
        rendered = _build_html(data, data["meta"].get("source_file", "未记录"), data["meta"].get("lut_file", "未记录"))
        updated.append({"file": path.name, "thumbnail": [data["meta"]["thumb_w"], data["meta"]["thumb_h"]]})
        if apply:
            backup = backup_dir / "reports" / path.name
            if backup.exists():
                raise FileExistsError(f"Backup already exists: {backup}")
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)
            temporary = path.with_suffix(".refreshing")
            temporary.write_text(rendered, encoding="utf-8")
            temporary.replace(path)
            hashes[path.name] = (hashlib.sha256(rendered.encode()).hexdigest(), len(rendered.encode()))
    records = []
    if db and apply and hashes:
        for artifact_id, payload in db.execute("SELECT artifact_id,payload_json FROM product_artifacts").fetchall():
            record = json.loads(payload)
            if record.get("artifact_type") != "lai_html_report":
                continue
            name = Path(record.get("content_path") or "").name
            if name not in hashes:
                continue
            records.append({"artifact_id": artifact_id, "payload_json": payload})
            checksum, size = hashes[name]
            record.update(checksum=checksum, size_bytes=size, version=record.get("version", 1) + 1)
            record.setdefault("provenance", {})["display_data_version"] = 2
            db.execute("UPDATE product_artifacts SET payload_json=? WHERE artifact_id=?",
                       (json.dumps(record, ensure_ascii=False), artifact_id))
        (backup_dir / "artifact-records.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        db.commit()
    if db:
        db.close()
    return {"applied": apply, "updated_reports": updated, "skipped_reports": skipped,
            "artifact_metadata_updated": len(records), "backup": str(backup_dir) if apply else None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-dir", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(refresh_reports(args.reports_dir, args.backup_dir, args.db, args.artifact_root,
                                     apply=args.apply), ensure_ascii=False))
