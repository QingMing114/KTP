"""One-way compatibility bridge from algorithm contract v1 to legacy runtime views."""

from __future__ import annotations

from schemas.runtime import ObservationV2, PackArtifactView
from v2.tools.remote_sensing.contract import AlgorithmToolResult


def algorithm_result_to_runtime(
    result: AlgorithmToolResult,
) -> tuple[ObservationV2, list[PackArtifactView]]:
    """Convert a strict result at the tool boundary; never convert legacy output back."""

    payload = result.model_dump(mode="json")
    artifacts = [
        PackArtifactView(
            pack_name="remote_sensing",
            artifact_type=artifact.runtime_kind,
            title=artifact.filename,
            uri=artifact.access_url,
            artifact_id=artifact.artifact_id,
            content_type=artifact.media_type,
            checksum_sha256=artifact.checksum_sha256,
            size_bytes=artifact.size_bytes,
            provenance=(result.provenance.model_dump(mode="json") if result.provenance else {}),
            internal_path=(str(artifact._internal_path) if artifact._internal_path else None),
        )
        for artifact in result.artifacts
    ]
    return (
        ObservationV2(
            source=(
                result.provenance.capability_name
                if result.provenance is not None
                else "remote_sensing.algorithm"
            ),
            status="success" if result.status == "succeeded" else "error",
            summary=result.summary,
            payload={"algorithm_result": payload},
        ),
        artifacts,
    )


__all__ = ["algorithm_result_to_runtime"]
