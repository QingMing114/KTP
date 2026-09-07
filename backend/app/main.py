"""Deprecated import compatibility entry point.

Deploy with ``apps.api_gateway.main:app``.  This module remains only for
existing local commands and must not receive new routes or application setup.
"""

from apps.api_gateway.main import create_app

app = create_app()

__deprecated__ = "Use apps.api_gateway.main:app for deployment."
