import pytest

from ktp_backend.api import KnowledgeIngestPayload, KnowledgeQueryPayload, InferenceRunPayload, InferenceBatchPayload


class TestKnowledgeIngestPayload:
    def test_defaults(self):
        p = KnowledgeIngestPayload()
        assert p.document_id == ""
        assert p.title == ""
        assert p.source == "web-upload"
        assert p.text == ""
        assert p.metadata == {}

    def test_custom_values(self):
        p = KnowledgeIngestPayload(
            document_id="doc-001",
            title="Test Doc",
            source="api",
            text="Hello world",
            metadata={"key": "value"},
        )
        assert p.document_id == "doc-001"
        assert p.title == "Test Doc"
        assert p.source == "api"
        assert p.metadata == {"key": "value"}


class TestKnowledgeQueryPayload:
    def test_defaults(self):
        p = KnowledgeQueryPayload()
        assert p.query == ""
        assert p.top_k is None
        assert p.task_type is None
        assert p.region is None
        assert p.crop_type is None
        assert p.context == {}

    def test_custom_values(self):
        p = KnowledgeQueryPayload(
            query="小麦LAI",
            top_k=5,
            task_type="lai_estimation",
            region="henan",
            crop_type="wheat",
        )
        assert p.query == "小麦LAI"
        assert p.top_k == 5


class TestInferenceRunPayload:
    def test_defaults(self):
        p = InferenceRunPayload()
        assert p.region == "henan"
        assert p.crop_type == "wheat"
        assert p.task_type is None
        assert p.image_path is None
        assert p.use_mock is False
        assert p.extra_params == {}

    def test_real_inference_mode(self):
        p = InferenceRunPayload(
            region="shandong",
            crop_type="corn",
            task_type="crop_health_detection",
            use_mock=False,
        )
        assert p.use_mock is False
        assert p.region == "shandong"


class TestInferenceBatchPayload:
    def test_with_tasks(self):
        tasks = [
            InferenceRunPayload(region="henan", crop_type="wheat"),
            InferenceRunPayload(region="shandong", crop_type="corn"),
        ]
        p = InferenceBatchPayload(tasks=tasks)
        assert len(p.tasks) == 2

    def test_empty_tasks(self):
        p = InferenceBatchPayload(tasks=[])
        assert len(p.tasks) == 0
