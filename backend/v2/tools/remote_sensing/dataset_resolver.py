"""Resolve contract dataset references against trusted request context."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from schemas.runtime import RequestContextV2
from v2.tools.remote_sensing.contract import AlgorithmToolInput, ToolExecutionContext
from v2.tools.remote_sensing.errors import AlgorithmToolExecutionError
from v2.tools.remote_sensing.contract import AlgorithmErrorCode


@dataclass(frozen=True)
class ResolvedAlgorithmDataset:
    dataset_id: str
    role: str
    path: Path
    content_type: str | None
    size_bytes: int


class AlgorithmDatasetResolver:
    """Resolve only canonical-boundary datasets; never consume caller paths."""

    def resolve(
        self,
        tool_input: AlgorithmToolInput,
        request_context: RequestContextV2,
        execution_context: ToolExecutionContext,
        *,
        allowed_suffixes: set[str] | None = None,
        allowed_media_types: set[str] | None = None,
        max_bytes: int | None = None,
        required_roles: set[str] | None = None,
    ) -> list[ResolvedAlgorithmDataset]:
        if "dataset:read" not in execution_context.permissions:
            raise AlgorithmToolExecutionError(
                AlgorithmErrorCode.DATASET_FORBIDDEN,
                "Dataset read permission is required.",
            )
        available = {dataset.dataset_id: dataset for dataset in request_context.datasets}
        resolved: list[ResolvedAlgorithmDataset] = []
        roles: set[str] = set()
        normalized_suffixes = {suffix.lower() for suffix in (allowed_suffixes or set())}
        for ref in tool_input.dataset_refs:
            dataset = available.get(ref.dataset_id)
            if dataset is None:
                raise AlgorithmToolExecutionError(
                    AlgorithmErrorCode.DATASET_NOT_FOUND,
                    "A referenced dataset is not available in this request.",
                    detail={"dataset_id": ref.dataset_id},
                )
            try:
                path = Path(dataset.local_path).resolve(strict=True)
            except (OSError, RuntimeError) as exc:
                raise AlgorithmToolExecutionError(
                    AlgorithmErrorCode.DATASET_NOT_FOUND,
                    "A referenced dataset could not be opened.",
                    detail={"dataset_id": ref.dataset_id},
                ) from exc
            if not path.is_file():
                raise AlgorithmToolExecutionError(
                    AlgorithmErrorCode.DATASET_NOT_FOUND,
                    "A referenced dataset is not a file.",
                    detail={"dataset_id": ref.dataset_id},
                )
            media_type = ref.media_type or dataset.content_type
            if normalized_suffixes and path.suffix.lower() not in normalized_suffixes:
                raise AlgorithmToolExecutionError(
                    AlgorithmErrorCode.UNSUPPORTED_FORMAT,
                    "Dataset file format is not supported by this tool.",
                    detail={"dataset_id": ref.dataset_id, "suffix": path.suffix.lower()},
                )
            if allowed_media_types and media_type not in allowed_media_types:
                raise AlgorithmToolExecutionError(
                    AlgorithmErrorCode.UNSUPPORTED_FORMAT,
                    "Dataset media type is not supported by this tool.",
                    detail={"dataset_id": ref.dataset_id, "media_type": media_type},
                )
            size_bytes = path.stat().st_size
            if max_bytes is not None and size_bytes > max_bytes:
                raise AlgorithmToolExecutionError(
                    AlgorithmErrorCode.RESOURCE_EXHAUSTED,
                    "Dataset exceeds this tool's configured size limit.",
                    detail={"dataset_id": ref.dataset_id, "max_bytes": max_bytes},
                )
            roles.add(ref.role)
            resolved.append(ResolvedAlgorithmDataset(
                dataset_id=ref.dataset_id,
                role=ref.role,
                path=path,
                content_type=media_type,
                size_bytes=size_bytes,
            ))
        missing_roles = (required_roles or set()) - roles
        if missing_roles:
            raise AlgorithmToolExecutionError(
                AlgorithmErrorCode.INVALID_INPUT,
                "Required dataset roles are missing.",
                detail={"missing_roles": sorted(missing_roles)},
            )
        return resolved


__all__ = ["AlgorithmDatasetResolver", "ResolvedAlgorithmDataset"]
