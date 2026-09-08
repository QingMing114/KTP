"""Per-invocation isolated temporary workspaces."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path


class AlgorithmWorkspace:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or tempfile.gettempdir()).resolve()
        self.path: Path | None = None

    def __enter__(self) -> "AlgorithmWorkspace":
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = Path(tempfile.mkdtemp(prefix="ktp_algorithm_", dir=self.root)).resolve()
        self._assert_contained(self.path)
        return self

    def resolve_output(self, relative_name: str) -> Path:
        if self.path is None:
            raise RuntimeError("algorithm workspace is not active")
        candidate = (self.path / relative_name).resolve()
        self._assert_contained(candidate, parent=self.path)
        candidate.parent.mkdir(parents=True, exist_ok=True)
        return candidate

    def _assert_contained(self, candidate: Path, *, parent: Path | None = None) -> None:
        expected = parent or self.root
        if candidate == expected or expected not in candidate.parents:
            raise ValueError("workspace path escapes the controlled root")

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        if self.path is not None:
            shutil.rmtree(self.path, ignore_errors=False)


__all__ = ["AlgorithmWorkspace"]
