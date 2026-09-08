"""Shared contracts for remote-sensing algorithm tools.

Real algorithm adapters are added only after STD-001 is frozen.  This package
currently contains the versioned contract, the legacy-runtime bridge, and an
internal probe used by contract tests.
"""

from v2.tools.remote_sensing.contract import (
    ALGORITHM_TOOL_CONTRACT_VERSION,
    AlgorithmArtifact,
    AlgorithmDatasetRef,
    AlgorithmError,
    AlgorithmErrorCode,
    AlgorithmExecutionControl,
    AlgorithmImplementation,
    AlgorithmProgressEvent,
    AlgorithmProvenance,
    AlgorithmRuntimeRecord,
    AlgorithmRuntimeRequirements,
    AlgorithmToolInput,
    AlgorithmToolResult,
    AlgorithmValidation,
    ToolExecutionContext,
    build_algorithm_tool_spec,
)
from v2.tools.remote_sensing.artifacts import AlgorithmArtifactManager
from v2.tools.remote_sensing.dataset_resolver import AlgorithmDatasetResolver, ResolvedAlgorithmDataset
from v2.tools.remote_sensing.errors import AlgorithmDeadlineExceeded, AlgorithmToolExecutionError
from v2.tools.remote_sensing.execution import RuntimeAlgorithmExecutionControl
from v2.tools.remote_sensing.model_runtime import ModelRuntimeManager
from v2.tools.remote_sensing.workspace import AlgorithmWorkspace

__all__ = [
    "ALGORITHM_TOOL_CONTRACT_VERSION",
    "AlgorithmArtifact",
    "AlgorithmArtifactManager",
    "AlgorithmDatasetResolver",
    "AlgorithmDeadlineExceeded",
    "AlgorithmDatasetRef",
    "AlgorithmError",
    "AlgorithmErrorCode",
    "AlgorithmExecutionControl",
    "AlgorithmToolExecutionError",
    "AlgorithmImplementation",
    "AlgorithmProgressEvent",
    "AlgorithmProvenance",
    "AlgorithmRuntimeRecord",
    "AlgorithmRuntimeRequirements",
    "AlgorithmToolInput",
    "AlgorithmToolResult",
    "AlgorithmValidation",
    "AlgorithmWorkspace",
    "ModelRuntimeManager",
    "ResolvedAlgorithmDataset",
    "RuntimeAlgorithmExecutionControl",
    "ToolExecutionContext",
    "build_algorithm_tool_spec",
]
