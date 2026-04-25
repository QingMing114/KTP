"""Compatibility wrapper for the new standalone gateway bridge."""

from ktp_backend.gateway_bridge import GatewayRuntimeBridge as GatewayAgentService

__all__ = ["GatewayAgentService"]
