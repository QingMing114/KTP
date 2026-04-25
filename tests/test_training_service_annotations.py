"""Annotation tests for Temporal payload compatibility."""

from __future__ import annotations

from typing import Any, get_args, get_origin, get_type_hints

from services.training_service.activities.evaluate_model import evaluate_model_activity
from services.training_service.activities.launch_training import launch_training_activity
from services.training_service.activities.prepare_dataset import prepare_dataset_activity
from services.training_service.activities.register_model import register_model_activity
from services.training_service.workflows.training_workflow import TrainingWorkflow


def _assert_dict_str_any(annotation: object) -> None:
    assert get_origin(annotation) is dict
    key_type, value_type = get_args(annotation)
    assert key_type is str
    assert value_type is Any


def test_temporal_payload_annotations_are_json_compatible() -> None:
    workflow_hints = get_type_hints(TrainingWorkflow.run)
    prepare_hints = get_type_hints(prepare_dataset_activity)
    launch_hints = get_type_hints(launch_training_activity)
    evaluate_hints = get_type_hints(evaluate_model_activity)
    register_hints = get_type_hints(register_model_activity)

    _assert_dict_str_any(workflow_hints["request_payload"])
    _assert_dict_str_any(workflow_hints["return"])
    _assert_dict_str_any(prepare_hints["request_payload"])
    _assert_dict_str_any(prepare_hints["return"])
    _assert_dict_str_any(launch_hints["payload"])
    _assert_dict_str_any(launch_hints["return"])
    _assert_dict_str_any(evaluate_hints["payload"])
    _assert_dict_str_any(evaluate_hints["return"])
    _assert_dict_str_any(register_hints["payload"])
    _assert_dict_str_any(register_hints["return"])
