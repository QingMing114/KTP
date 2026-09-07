"""Schema package with explicit protocol boundaries.

Import product contracts from ``schemas.canonical`` / ``schemas.spatial`` and
internal engine contracts from ``schemas.runtime``.  This package deliberately
does not wildcard-re-export models whose names can collide across boundaries.
"""

from schemas import canonical, runtime, spatial
from schemas.errors import CanonicalError, ErrorCode, ErrorResponse, canonical_error_response

__all__ = [
    "CanonicalError",
    "ErrorCode",
    "ErrorResponse",
    "canonical",
    "canonical_error_response",
    "runtime",
    "spatial",
]
