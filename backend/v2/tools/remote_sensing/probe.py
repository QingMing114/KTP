"""Internal deterministic probe for validating the algorithm tool contract."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from v2.tools.remote_sensing.contract import (
    AlgorithmArtifact,
    AlgorithmError,
    AlgorithmErrorCode,
    AlgorithmExecutionControl,
    AlgorithmProvenance,
    AlgorithmRuntimeRecord,
    AlgorithmToolInput,
    AlgorithmToolResult,
    AlgorithmValidation,
    ToolExecutionContext,
)
from v2.tools.remote_sensing.workspace import AlgorithmWorkspace


@dataclass
class ContractProbeState:
    last_workspace: Path | None = None
    cleanup_completed: bool = False


def build_contract_probe_handler(state: ContractProbeState):
    """Return a strict handler backed by runtime context and control."""

    def handler(
        validated_input: AlgorithmToolInput,
        execution_context: ToolExecutionContext,
        execution_control: AlgorithmExecutionControl,
    ) -> AlgorithmToolResult:
        execution_id = execution_context.execution_id
        trace_id = execution_context.trace_id
        started = datetime.now(UTC)
        started_clock = time.perf_counter()
        state.cleanup_completed = False
        try:
            with AlgorithmWorkspace() as workspace:
                state.last_workspace = workspace.path
                execution_control.raise_if_cancelled()
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
            return result
        finally:
            state.cleanup_completed = state.last_workspace is not None and not state.last_workspace.exists()

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
