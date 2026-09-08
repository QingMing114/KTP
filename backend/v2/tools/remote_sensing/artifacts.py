"""Persist algorithm outputs before invocation workspaces are removed."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

from v2.tools.remote_sensing.contract import AlgorithmArtifact, SpatialMetadata
from v2.tools.remote_sensing.errors import AlgorithmToolExecutionError
from v2.tools.remote_sensing.contract import AlgorithmErrorCode


class AlgorithmArtifactManager:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def persist(
        self,
        source: str | Path,
        *,
        workspace: str | Path,
        role: str,
        runtime_kind: str,
        media_type: str,
        filename: str | None = None,
        spatial: SpatialMetadata | None = None,
    ) -> AlgorithmArtifact:
        source_path = Path(source).resolve(strict=True)
        workspace_path = Path(workspace).resolve(strict=True)
        if workspace_path not in source_path.parents or not source_path.is_file():
            raise AlgorithmToolExecutionError(
                AlgorithmErrorCode.ARTIFACT_PERSIST_FAILED,
                "Artifact source must be a file inside the invocation workspace.",
            )
        safe_name = Path(filename or source_path.name).name
        if not safe_name or safe_name in {".", ".."}:
            raise AlgorithmToolExecutionError(
                AlgorithmErrorCode.ARTIFACT_PERSIST_FAILED,
                "Artifact filename is invalid.",
            )
        artifact_id = "art_" + uuid4().hex
        artifact_dir = (self.root / artifact_id).resolve()
        if self.root not in artifact_dir.parents:
            raise AlgorithmToolExecutionError(
                AlgorithmErrorCode.ARTIFACT_PERSIST_FAILED,
                "Artifact destination is outside the controlled root.",
            )
        artifact_dir.mkdir(parents=False, exist_ok=False)
        destination = artifact_dir / safe_name
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=artifact_dir, delete=False) as handle:
                temporary = Path(handle.name)
                with source_path.open("rb") as source_handle:
                    shutil.copyfileobj(source_handle, handle)
            os.replace(temporary, destination)
            checksum, size_bytes = _fingerprint(destination)
        except Exception as exc:
            shutil.rmtree(artifact_dir, ignore_errors=True)
            if isinstance(exc, AlgorithmToolExecutionError):
                raise
            raise AlgorithmToolExecutionError(
                AlgorithmErrorCode.ARTIFACT_PERSIST_FAILED,
                "Artifact could not be persisted.",
                retryable=True,
            ) from exc
        try:
            artifact = AlgorithmArtifact(
                artifact_id=artifact_id,
                role=role,
                runtime_kind=runtime_kind,
                media_type=media_type,
                filename=safe_name,
                access_url=f"/api/product/v1/artifacts/{artifact_id}",
                download_url=f"/api/product/v1/artifacts/{artifact_id}/content",
                checksum_sha256=checksum,
                size_bytes=size_bytes,
                spatial=spatial,
            )
        except Exception:
            shutil.rmtree(artifact_dir, ignore_errors=True)
            raise
        artifact.attach_internal_path(destination)
        return artifact


def _fingerprint(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest(), path.stat().st_size


__all__ = ["AlgorithmArtifactManager"]
