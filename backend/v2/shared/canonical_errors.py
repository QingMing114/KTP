"""Re-export bridge — canonical error models now live in schemas/errors.py.

This file is kept for backward compatibility.  New code should import
directly from schemas.errors.
"""

from schemas.errors import (  # noqa: F401, E402
    CanonicalError,
    ErrorCode,
    ErrorResponse,
    canonical_error_response,
)
