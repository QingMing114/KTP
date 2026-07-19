"""Re-export bridge — SubmissionStore now lives in runtime/submission_store.py.

This file is kept for backward compatibility.  New code should import
directly from runtime.submission_store.
"""

from runtime.submission_store import SubmissionStore  # noqa: F401, E402
