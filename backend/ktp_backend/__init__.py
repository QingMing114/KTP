"""Standalone backend composition root for the KTP chat-first agent."""

from ktp_backend.api import create_backend_app, install_backend_api
from ktp_backend.gateway_bridge import GatewayRuntimeBridge
from ktp_backend.runtime_host import BackendRuntimeHost, build_backend_runtime_host, install_backend_runtime_host

__all__ = [
    "BackendRuntimeHost",
    "GatewayRuntimeBridge",
    "build_backend_runtime_host",
    "create_backend_app",
    "install_backend_api",
    "install_backend_runtime_host",
]

