"""Versioned contract for algorithm tools executed by the bounded runtime."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
import re
from typing import Any, Literal, Protocol, runtime_checkable

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from schemas.runtime import ToolSpecV2


ALGORITHM_TOOL_CONTRACT_VERSION = "algorithm-tool/v1"


class ContractSchemaError(ValueError):
    """Raised when a tool publishes an invalid JSON Schema document."""


class ContractInputError(ValueError):
    """Raised when a tool invocation does not satisfy its input schema."""


class AlgorithmErrorCode(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    DATASET_NOT_FOUND = "DATASET_NOT_FOUND"
    DATASET_FORBIDDEN = "DATASET_FORBIDDEN"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    BAND_MISMATCH = "BAND_MISMATCH"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    INFERENCE_FAILED = "INFERENCE_FAILED"
    ARTIFACT_PERSIST_FAILED = "ARTIFACT_PERSIST_FAILED"
    CONTRACT_VERSION_MISMATCH = "CONTRACT_VERSION_MISMATCH"


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AlgorithmDatasetRef(_ContractModel):
    dataset_id: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=80)
    pair_key: str | None = Field(default=None, max_length=200)
    media_type: str | None = Field(default=None, max_length=160)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AlgorithmOutputOptions(_ContractModel):
    artifact_roles: list[str] = Field(default_factory=list)
    formats: list[str] = Field(default_factory=list)
    include_visualization: bool = True
    include_statistics: bool = True


class AlgorithmToolInput(_ContractModel):
    dataset_refs: list[AlgorithmDatasetRef] = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    output_options: AlgorithmOutputOptions = Field(default_factory=AlgorithmOutputOptions)


class AlgorithmRuntimeRequirements(_ContractModel):
    devices: list[Literal["cpu", "cuda", "mps"]] = Field(min_length=1)
    timeout_seconds: int = Field(gt=0, le=86400)
    supports_cancellation: bool
    max_concurrency: int = Field(default=1, ge=1)
    minimum_memory_mb: int | None = Field(default=None, ge=1)


class AlgorithmImplementation(_ContractModel):
    algorithm: str = Field(min_length=1)
    version: str = Field(min_length=1)
    adapter_version: str = Field(default="1.0.0", min_length=1)
    model: str | None = None
    model_version: str | None = None


class ToolExecutionContext(_ContractModel):
    """Trusted context injected by the runtime, never authored by the LLM."""

    execution_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    tenant_id: str | None = None
    conversation_id: str | None = None
    run_id: str | None = None
    permissions: list[str] = Field(default_factory=list)
    deadline_at: str | None = None


class AlgorithmProgressEvent(_ContractModel):
    contract_version: Literal[ALGORITHM_TOOL_CONTRACT_VERSION] = ALGORITHM_TOOL_CONTRACT_VERSION
    execution_id: str = Field(min_length=1)
    stage: Literal["validating", "preparing", "running", "persisting", "finalizing"]
    progress: float = Field(ge=0.0, le=1.0)
    message: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class AlgorithmExecutionControl(Protocol):
    """Runtime-owned cooperative cancellation and progress interface."""

    def raise_if_cancelled(self) -> None: ...

    def emit_progress(self, event: AlgorithmProgressEvent) -> None: ...


class SpatialMetadata(_ContractModel):
    crs: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    resolution: tuple[float, float] | None = None
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    bands: list[str] = Field(default_factory=list)
    classes: dict[str, str] = Field(default_factory=dict)


class AlgorithmArtifact(_ContractModel):
    _internal_path: Path | None = PrivateAttr(default=None)

    artifact_id: str = Field(min_length=1)
    role: str = Field(min_length=1, max_length=100)
    runtime_kind: Literal[
        "classification_result",
        "segmentation_mask",
        "segmentation_preview",
        "statistics_table",
        "provenance_record",
        "text_card",
        "visualization_card",
    ]
    media_type: str = Field(min_length=1, max_length=160)
    filename: str = Field(min_length=1, max_length=255)
    access_url: str = Field(min_length=1)
    download_url: str | None = None
    checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=0)
    spatial: SpatialMetadata | None = None

    def attach_internal_path(self, path: Path) -> None:
        """Attach a runtime-only persisted path that is never serialized."""

        self._internal_path = path


class AlgorithmProvenance(_ContractModel):
    capability_name: str = Field(pattern=r"^remote_sensing\.[a-z][a-z0-9_]*$")
    tool_version: str = Field(min_length=1)
    algorithm_name: str = Field(min_length=1)
    algorithm_version: str = Field(min_length=1)
    model_name: str | None = None
    model_version: str | None = None
    model_checksum: str | None = None
    dataset_versions: dict[str, str] = Field(default_factory=dict)
    parameter_checksum: str | None = None
    environment: dict[str, str] = Field(default_factory=dict)


class AlgorithmValidation(_ContractModel):
    passed: bool
    checks: list[dict[str, Any]] = Field(default_factory=list)


class AlgorithmRuntimeRecord(_ContractModel):
    execution_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    started_at: str
    finished_at: str
    duration_ms: int = Field(ge=0)
    device: str | None = None


class AlgorithmError(_ContractModel):
    code: AlgorithmErrorCode
    message: str = Field(min_length=1)
    detail: dict[str, Any] = Field(default_factory=dict)
    retryable: bool = False


class AlgorithmToolResult(_ContractModel):
    contract_version: Literal[ALGORITHM_TOOL_CONTRACT_VERSION] = ALGORITHM_TOOL_CONTRACT_VERSION
    status: Literal["succeeded", "failed", "cancelled", "unavailable"]
    summary: str = Field(min_length=1)
    metrics: dict[str, Any] = Field(default_factory=dict)
    predictions: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[AlgorithmArtifact] = Field(default_factory=list)
    provenance: AlgorithmProvenance | None = None
    validation: AlgorithmValidation
    warnings: list[str] = Field(default_factory=list)
    runtime: AlgorithmRuntimeRecord
    error: AlgorithmError | None = None

    @model_validator(mode="after")
    def validate_status_error_pair(self) -> "AlgorithmToolResult":
        if self.status == "succeeded" and self.error is not None:
            raise ValueError("succeeded results must not contain an error")
        if self.status != "succeeded" and self.error is None:
            raise ValueError("non-succeeded results must contain an error")
        return self


def validate_schema_document(schema: dict[str, Any]) -> None:
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ContractSchemaError(str(exc)) from exc


def validate_contract_input(schema: dict[str, Any], value: dict[str, Any]) -> None:
    validate_schema_document(schema)
    sensitive_location = _find_sensitive_input(value)
    if sensitive_location is not None:
        raise ContractInputError(
            f"algorithm tool input contains a forbidden path, command, or credential at {sensitive_location}"
        )
    try:
        Draft202012Validator(schema).validate(value)
    except ValidationError as exc:
        path = ".".join(str(part) for part in exc.absolute_path) or "$"
        raise ContractInputError(f"invalid algorithm tool input at {path}: {exc.message}") from exc


def build_algorithm_tool_spec(
    *,
    capability_name: str,
    display_name: str,
    description: str,
    produces_artifacts: list[str],
    permissions: list[str],
    runtime_requirements: dict[str, Any],
    implementation: dict[str, Any],
    availability: Literal["available", "unavailable", "disabled"] = "available",
    unavailable_reason: str | None = None,
    visibility: Literal["public", "bounded", "internal"] = "bounded",
    surface_visibility: Literal["all", "web", "api", "debug", "internal"] = "all",
) -> ToolSpecV2:
    if re.fullmatch(r"remote_sensing\.[a-z][a-z0-9_]*", capability_name) is None:
        raise ValueError("algorithm capability names must use remote_sensing.<snake_case>")
    if availability != "available" and not unavailable_reason:
        raise ValueError("unavailable and disabled tools must explain why")
    if not permissions:
        raise ValueError("algorithm tools must declare at least one permission")

    validated_requirements = AlgorithmRuntimeRequirements.model_validate(runtime_requirements)
    validated_implementation = AlgorithmImplementation.model_validate(implementation)

    input_schema = AlgorithmToolInput.model_json_schema()
    output_schema = AlgorithmToolResult.model_json_schema()
    validate_schema_document(input_schema)
    validate_schema_document(output_schema)
    return ToolSpecV2(
        name=capability_name,
        display_name=display_name,
        description=description,
        visibility=visibility,
        category="remote_sensing",
        pack_name="remote_sensing",
        usage_hint=f"Use the {capability_name} capability only with registered dataset references.",
        input_schema=input_schema,
        output_schema=output_schema,
        contract_version=ALGORITHM_TOOL_CONTRACT_VERSION,
        availability=availability,
        unavailable_reason=unavailable_reason,
        permissions=permissions,
        runtime_requirements=validated_requirements.model_dump(mode="json"),
        implementation=validated_implementation.model_dump(mode="json"),
        enabled_by_default=availability == "available",
        capabilities=[capability_name],
        requires_context=["user_id", "trace_id", "dataset_permissions"],
        produces_artifacts=produces_artifacts,
        surface_visibility=surface_visibility,
    )


_FORBIDDEN_INPUT_KEYS = frozenset({
    "command",
    "credential",
    "credentials",
    "local_path",
    "model_path",
    "password",
    "path",
    "secret",
    "shell",
    "token",
    "weights_path",
})


def _find_sensitive_input(value: Any, location: str = "$") -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_location = f"{location}.{key}"
            if str(key).lower() in _FORBIDDEN_INPUT_KEYS:
                return child_location
            found = _find_sensitive_input(child, child_location)
            if found is not None:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _find_sensitive_input(child, f"{location}[{index}]")
            if found is not None:
                return found
    elif isinstance(value, str):
        if value.startswith(("/", "file://", "file:\\")) or re.match(r"^[A-Za-z]:[\\/]", value):
            return location
    return None


__all__ = [
    "ALGORITHM_TOOL_CONTRACT_VERSION",
    "AlgorithmArtifact",
    "AlgorithmDatasetRef",
    "AlgorithmError",
    "AlgorithmErrorCode",
    "AlgorithmExecutionControl",
    "AlgorithmOutputOptions",
    "AlgorithmProgressEvent",
    "AlgorithmProvenance",
    "AlgorithmImplementation",
    "AlgorithmRuntimeRequirements",
    "AlgorithmRuntimeRecord",
    "AlgorithmToolInput",
    "AlgorithmToolResult",
    "AlgorithmValidation",
    "ContractInputError",
    "ContractSchemaError",
    "SpatialMetadata",
    "ToolExecutionContext",
    "build_algorithm_tool_spec",
    "validate_contract_input",
    "validate_schema_document",
]
