"""Common API schemas used across services."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class BaseSchema(BaseModel):
    """Base schema with strict extra-field handling."""

    model_config = ConfigDict(extra="forbid")


class HealthResponse(BaseSchema):
    """Response payload for service health checks."""

    service: str = Field(..., description="Service name.")
    status: str = Field(..., description="Current service status.")
    environment: str = Field(..., description="Runtime environment.")
    checks: dict[str, str] = Field(
        default_factory=dict,
        description="Dependency probe placeholders for future health checks.",
    )


class ErrorResponse(BaseSchema):
    """Standard error response payload."""

    error_code: str = Field(..., description="Stable machine-readable error code.")
    detail: str = Field(..., description="Human-readable error description.")


class PingResponse(BaseSchema):
    """Simple liveness response payload."""

    message: str = Field(..., description="Liveness response message.")
    service: str = Field(..., description="Service name.")
    environment: str = Field(..., description="Runtime environment.")
