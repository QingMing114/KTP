"""Re-export bridge — all V2 models now live in schemas/.

This file is kept for backward compatibility.  New code should import
directly from schemas.runtime / schemas.canonical.

.. note::

    Only ``schemas.runtime`` is re-exported here to preserve Pydantic
    class identity (runtime models imported via this bridge are the same
    Python class as their definitions in ``schemas.runtime``).

    Canonical API models (``schemas.canonical``) must be imported
    explicitly: ``from schemas.canonical import SessionDetail``.
"""

from schemas.runtime import *  # noqa: F401, F403, E402
