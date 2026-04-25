from shared.request_normalization import (
    detect_crop_type_from_text,
    detect_region_from_text,
    detect_task_type_from_text,
    normalize_crop_type,
    normalize_region,
)


def test_baldness_domain_aliases_are_normalized() -> None:
    assert normalize_region("scalp") == "scalp"
    assert normalize_region("头皮") == "scalp"
    assert normalize_crop_type("hair") == "hair"
    assert normalize_crop_type("头发") == "hair"


def test_baldness_domain_aliases_are_detected_from_text() -> None:
    text = "请对这张头皮多光谱影像做真实斑秃识别，并分析头发区域。"

    assert detect_region_from_text(text) == "scalp"
    assert detect_crop_type_from_text(text) == "hair"
    assert detect_task_type_from_text(text) == "baldness_detection"
