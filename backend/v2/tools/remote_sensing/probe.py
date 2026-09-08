"""Internal deterministic probe for validating the algorithm tool contract."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from v2.tools.remote_sensing.bridge import algorithm_result_to_runtime
from v2.tools.remote_sensing.contract import (
    AlgorithmArtifact,
    AlgorithmError,
    AlgorithmErrorCode,
    AlgorithmProvenance,
    AlgorithmRuntimeRecord,
    AlgorithmToolInput,
    AlgorithmToolResult,
    AlgorithmValidation,
)


@dataclass
class ContractProbeState:
    last_workspace: Path | None = None
    cleanup_completed: bool = False


def build_contract_probe_handler(state: ContractProbeState):
    """Return a legacy-signature handler backed by the strict result contract."""

    def handler(**tool_input):
        validated_input = AlgorithmToolInput.model_validate(tool_input)
        execution_id = f"probe-{uuid4().hex}"
        trace_id = f"trace-{uuid4().hex}"
        started = datetime.now(UTC)
        started_clock = time.perf_counter()
        workspace = Path(tempfile.mkdtemp(prefix="ktp_contract_probe_"))
        state.last_workspace = workspace
        state.cleanup_completed = False
        try:
            payload = json.dumps(
                validated_input.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
            if validated_input.parameters.get("fail") is True:
                result = AlgorithmToolResult(
                    status="failed",
                    summary="Contract probe failed as requested.",
                    validation=AlgorithmValidation(passed=True),
                    runtime=_runtime_record(execution_id, trace_id, started, started_clock),
                    error=AlgorithmError(
                        code=AlgorithmErrorCode.INFERENCE_FAILED,
                        message="Controlled contract probe failure.",
                        retryable=False,
                    ),
                )
            else:
                result = AlgorithmToolResult(
                    status="succeeded",
                    summary="Algorithm contract probe completed.",
                    metrics={"dataset_count": len(validated_input.dataset_refs)},
                    predictions={"probe": "ok"},
                    artifacts=[
                        AlgorithmArtifact(
                            artifact_id=f"artifact-{uuid4().hex}",
                            role="contract_probe",
                            runtime_kind="text_card",
                            media_type="application/json",
                            filename="contract-probe.json",
                            access_url=f"/internal/contract-probes/{execution_id}",
                            checksum_sha256=hashlib.sha256(payload).hexdigest(),
                            size_bytes=len(payload),
                        )
                    ],
                    provenance=AlgorithmProvenance(
                        capability_name="remote_sensing.contract_probe",
                        tool_version="1.0.0",
                        algorithm_name="deterministic-contract-probe",
                        algorithm_version="1.0.0",
                        dataset_versions={ref.dataset_id: "test" for ref in validated_input.dataset_refs},
                    ),
                    validation=AlgorithmValidation(
                        passed=True,
                        checks=[{"name": "input_schema", "passed": True}],
                    ),
                    runtime=_runtime_record(execution_id, trace_id, started, started_clock),
                )
            return algorithm_result_to_runtime(result)
        finally:
            shutil.rmtree(workspace, ignore_errors=False)
            state.cleanup_completed = True

    return handler


def _runtime_record(
    execution_id: str,
    trace_id: str,
    started: datetime,
    started_clock: float,
) -> AlgorithmRuntimeRecord:
    finished = datetime.now(UTC)
    return AlgorithmRuntimeRecord(
        execution_id=execution_id,
        trace_id=trace_id,
        started_at=started.isoformat(),
        finished_at=finished.isoformat(),
        duration_ms=max(0, round((time.perf_counter() - started_clock) * 1000)),
        device="cpu",
    )


__all__ = ["ContractProbeState", "build_contract_probe_handler"]
