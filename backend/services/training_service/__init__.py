"""Temporal-based training service package.

Keep package import side-effect free so Temporal workflow sandbox validation can
import submodules such as ``services.training_service.schemas`` safely.
"""

__all__: list[str] = []
