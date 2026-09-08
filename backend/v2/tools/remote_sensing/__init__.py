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

__all__ = [
    "ALGORITHM_TOOL_CONTRACT_VERSION",
    "AlgorithmArtifact",
    "AlgorithmDatasetRef",
    "AlgorithmError",
    "AlgorithmErrorCode",
    "AlgorithmExecutionControl",
    "AlgorithmImplementation",
    "AlgorithmProgressEvent",
    "AlgorithmProvenance",
    "AlgorithmRuntimeRecord",
    "AlgorithmRuntimeRequirements",
    "AlgorithmToolInput",
    "AlgorithmToolResult",
    "AlgorithmValidation",
    "ToolExecutionContext",
    "build_algorithm_tool_spec",
]
