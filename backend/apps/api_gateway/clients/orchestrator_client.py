"""Local client used by the gateway to invoke the orchestrator."""

from __future__ import annotations

from collections import OrderedDict

from shared.schemas.orchestrator import WorkflowRequest, WorkflowResponse


class OrchestratorClientError(Exception):
    """Raised when the orchestrator cannot complete a gateway request."""


class _MaxSizeDict(OrderedDict):
    def __init__(self, maxsize: int = 1000):
        super().__init__()
        self._maxsize = maxsize

    def __setitem__(self, key, value):
        if key not in self and len(self) >= self._maxsize:
            self.popitem(last=False)
        super().__setitem__(key, value)


class LocalOrchestratorClient:
    """Gateway-facing client for local orchestrator execution."""

    def __init__(self, max_cached_results: int = 1000) -> None:
        self._results: _MaxSizeDict = _MaxSizeDict(maxsize=max_cached_results)

    def run_workflow(self, request: WorkflowRequest) -> WorkflowResponse:
        """Run a workflow and store the latest result by request id."""
        try:
            from apps.orchestrator.main import run_workflow_request

            response = run_workflow_request(request)
        except Exception as exc:  # pragma: no cover - passthrough branch
            raise OrchestratorClientError(str(exc)) from exc
        self._results[request.request_id] = response
        return response

    def get_workflow(self, request_id: str) -> WorkflowResponse | None:
        """Return a cached workflow response when available."""
        return self._results.get(request_id)
