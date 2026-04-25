"""Health endpoints for the API gateway."""

from __future__ import annotations

import time

from fastapi import APIRouter

from shared.config.settings import get_settings
from shared.schemas.common import HealthResponse

router = APIRouter(tags=["health"])

_startup_time: float = time.time()


@router.get("/health", response_model=HealthResponse, summary="Service health check")
async def health_check() -> HealthResponse:
    """Return the current service health status with real dependency checks."""
    settings = get_settings()
    checks: dict[str, str] = {}
    overall_ok = True

    db_status = _check_database()
    checks["database"] = db_status
    if db_status != "ok":
        overall_ok = False

    redis_status = _check_redis()
    checks["redis"] = redis_status
    if redis_status not in ("ok", "not_configured"):
        overall_ok = False

    uptime = time.time() - _startup_time
    checks["uptime_seconds"] = f"{uptime:.0f}"

    return HealthResponse(
        service=settings.app_name,
        status="ok" if overall_ok else "degraded",
        environment=settings.app_env,
        checks=checks,
    )


def _check_database() -> str:
    try:
        from sqlalchemy import create_engine, text
        db_url = getattr(get_settings(), "database_url", None)
        if not db_url:
            return "not_configured"
        engine = create_engine(str(db_url))
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return "ok"
    except Exception as exc:
        return f"error: {exc}"


def _check_redis() -> str:
    try:
        import redis
        redis_url = getattr(get_settings(), "redis_url", None)
        if not redis_url:
            return "not_configured"
        r = redis.from_url(str(redis_url))
        r.ping()
        r.close()
        return "ok"
    except ImportError:
        return "not_configured"
    except Exception as exc:
        return f"error: {exc}"
