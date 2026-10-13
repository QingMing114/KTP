"""Map reports must be readable, stable, and free of internal file paths."""

from runtime.artifact_store import ArtifactStore
from runtime.workflow_reports import register_crop_report, register_map_report, register_result_json


def test_report_escapes_model_text_and_reuses_identical_snapshot(tmp_path):
    artifacts = ArtifactStore(db_path=str(tmp_path / "reports.sqlite3"))
    try:
        kwargs = dict(
            run_id="workflow-1", output_dir=tmp_path / "reports",
            kind="workflow_summary_report", title="测试报告",
            context={"影像": "<script>alert(1)</script>"},
            sections=[{"title": "识别结果", "rows": [["类别", "<img src=x>"]]}],
        )
        first = register_map_report(artifacts, **kwargs)
        second = register_map_report(artifacts, **kwargs)
        assert first == second
        html = artifacts.get(first["report_artifact_id"]).content_path
        text = open(html, encoding="utf-8").read()
        assert "<script>" not in text and "<img src=x>" not in text
        assert "&lt;script&gt;" in text and "&lt;img src=x&gt;" in text

        data = register_result_json(
            artifacts, run_id="workflow-1", output_dir=tmp_path / "reports",
            title="结果", result={"score": 0.8, "report_path": "/secret/report.html"},
        )
        payload = open(artifacts.get(data["report_data_artifact_id"]).content_path,
                       encoding="utf-8").read()
        assert "score" in payload and "/secret/report.html" not in payload
    finally:
        artifacts.close()


def test_crop_report_uses_lai_style_layout_and_real_class_scores(tmp_path):
    artifacts = ArtifactStore(db_path=str(tmp_path / "reports.sqlite3"))
    try:
        report = register_crop_report(
            artifacts, run_id="crop-1", output_dir=tmp_path / "crop",
            imagery_item_id="sentinel-scene", observed_at="2026-07-22T10:00:00Z",
            area_hectares=2.48,
            result={
                "model": {"name": "KDD2020", "sha256": "abc"},
                "predicted_class": {"name_zh": "春小麦", "score": 0.327},
                "class_scores": [
                    {"name_zh": "大豆", "score": 0.289},
                    {"name_zh": "春小麦", "score": 0.327},
                ],
                "input": {"valid_pixels": 42},
                "warnings": ["模型分数未经实地校准。"],
            },
        )
        html = open(artifacts.get(report["report_artifact_id"]).content_path,
                    encoding="utf-8").read()
        assert report["report_version"] == "map-report-v2"
        assert "class='stats-grid'" in html
        assert "class='bar-row'" in html
        assert html.index("春小麦</div>") < html.index("大豆</div>")
        assert "32.7%" in html and "28.9%" in html
        assert "模型分数未经实地校准。" in html
        assert "sentinel-scene" in html
    finally:
        artifacts.close()
