"""Import-boundary tests for the training service package."""

from __future__ import annotations

import importlib
import sys


def test_importing_schemas_does_not_pull_runtime_client_modules() -> None:
    for module_name in list(sys.modules):
        if module_name == "services.training_service" or module_name.startswith(
            "services.training_service."
        ):
            sys.modules.pop(module_name)

    importlib.import_module("services.training_service.schemas")

    assert "services.training_service.client" not in sys.modules
    assert "services.training_service.config" not in sys.modules
