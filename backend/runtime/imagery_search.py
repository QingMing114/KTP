"""Single implementation of the Sentinel-2 imagery search capability.

The search endpoint and the registered tool both call this module, so the
provider call, the search id, and the candidate normalization live in one
place. Search is read-only and side-effect free; failures propagate as
``ImagerySearchError`` for the caller to map (HTTP 502 or a tool error).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from infra.imagery.stac_provider import ImagerySearchError
from schemas.spatial import ImageryCandidate, ImagerySearchRequest


@dataclass(frozen=True)
class ImagerySearchOutcome:
    """One completed search over a provider."""

    items: list[ImageryCandidate]
    search_id: str


def search_imagery(provider: Any, request: ImagerySearchRequest) -> ImagerySearchOutcome:
    """Search one provider and attach the stable id for this result set."""
    if provider is None:
        raise ImagerySearchError("imagery provider is not configured")
    candidates = provider.search(request)
    return ImagerySearchOutcome(items=list(candidates), search_id=str(uuid4()))
