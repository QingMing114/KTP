"""Structured, non-sensitive failures for algorithm tool execution."""

from __future__ import annotations

from typing import Any

from v2.tools.remote_sensing.contract import AlgorithmError, AlgorithmErrorCode


class AlgorithmToolExecutionError(RuntimeError):
    def __init__(
        self,
        code: AlgorithmErrorCode,
        message: str,
        *,
        detail: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.error = AlgorithmError(
            code=code,
            message=message,
            detail=detail or {},
            retryable=retryable,
        )


class AlgorithmDeadlineExceeded(AlgorithmToolExecutionError):
    def __init__(self) -> None:
        super().__init__(
            AlgorithmErrorCode.TIMEOUT,
            "Algorithm execution exceeded its configured deadline.",
            retryable=True,
        )


def normalized_algorithm_error(exc: Exception) -> AlgorithmError:
    """Map an exception to the public taxonomy without leaking host details."""

    if isinstance(exc, AlgorithmToolExecutionError):
        return exc.error
    if isinstance(exc, (MemoryError, OSError)):
        return AlgorithmError(
            code=AlgorithmErrorCode.RESOURCE_EXHAUSTED,
            message="Algorithm execution could not obtain the required runtime resource.",
            retryable=True,
        )
    return AlgorithmError(
        code=AlgorithmErrorCode.INFERENCE_FAILED,
        message="Algorithm execution failed.",
        detail={"exception_type": type(exc).__name__},
        retryable=False,
    )


__all__ = [
    "AlgorithmDeadlineExceeded",
    "AlgorithmToolExecutionError",
    "normalized_algorithm_error",
]
