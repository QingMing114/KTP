"""Minimal FastAPI gateway for the scaffold phase."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from apps.api_gateway.config import get_api_gateway_config
from apps.api_gateway.routers.chat import router as chat_router
from apps.api_gateway.routers.conversation import router as conversation_router
from apps.api_gateway.routers.chat_ui import router as chat_ui_router
from apps.api_gateway.routers.detect import router as detect_router
from apps.api_gateway.routers.health import router as health_router
from apps.api_gateway.routers.v2_ui import router as v2_ui_router
from apps.api_gateway.routers.v2_artifacts import router as v2_artifacts_router
from apps.api_gateway.routers.openai_adapter import router as openai_adapter_router
from ktp_backend.auth import router as auth_router
from apps.api_gateway.services.conversation_service import ConversationService
from apps.api_gateway.services.conversation_store import ConversationStore
from infra.llm.provider import AgentLLMError, AgentLLMProvider, get_agent_llm_provider
from ktp_backend.api import install_backend_api
from ktp_backend.gateway_bridge import GatewayRuntimeBridge
from ktp_backend.runtime_host import build_backend_runtime_host, install_backend_runtime_host
from api.canonical.router import install_canonical_product_api
from shared.config.paths import get_lai_report_dir
from shared.config.settings import get_settings
from shared.logging import configure_logging
from shared.schemas.common import PingResponse


class RateLimiter:
    def __init__(self, max_requests: int = 60, window_seconds: int = 60, max_entries: int = 10000):
        self._max = max_requests
        self._window = window_seconds
        self._max_entries = max_entries
        self._requests: dict[str, list[float]] = {}

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        if key not in self._requests:
            if len(self._requests) >= self._max_entries:
                self.cleanup()
            self._requests[key] = []
        self._requests[key] = [t for t in self._requests[key] if now - t < self._window]
        if len(self._requests[key]) >= self._max:
            return False
        self._requests[key].append(now)
        return True

    def cleanup(self):
        now = time.time()
        expired = [k for k, v in self._requests.items() if not v or now - v[-1] > self._window]
        for k in expired:
            del self._requests[k]


settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROJECT_ROOT = _REPO_ROOT.parent
_V2_WEB_DIST_DIR = _PROJECT_ROOT / "frontend" / "dist"

_NO_AUTH_PATHS = {"/", "/health", "/docs", "/openapi.json", "/redoc", "/v2/artifacts/open", "/v2/auth/login", "/v2/auth/register"}
_LAI_REPORTS_DIR = get_lai_report_dir()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info(
        "api_gateway_starting | env=%s | host=%s | port=%s",
        settings.app_env,
        settings.app_host,
        settings.app_port,
    )
    logger.info("api_gateway_started | service=%s", settings.app_name)
    try:
        yield
    except Exception:
        logger.exception("api_gateway_failed")
        raise
    finally:
        logger.info("api_gateway_stopped | service=%s", settings.app_name)


def create_app(
    *,
    llm_provider_override: AgentLLMProvider | None = None,
) -> FastAPI:
    """Create the FastAPI application for the API gateway."""
    import sys
    from pathlib import Path
    _workspace = Path(__file__).resolve().parents[2]
    prosail_path = str(_workspace / "prosail_python")
    if prosail_path not in sys.path:
        sys.path.insert(0, prosail_path)

    gateway_config = get_api_gateway_config()
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        description="Scaffold API gateway for the remote sensing multi-agent system.",
        docs_url=None,
        redoc_url=None,
    )

    cors_origins = settings.get_cors_origins
    application.add_middleware(CORSMiddleware, allow_origins=cors_origins, allow_methods=["*"], allow_headers=["*"])

    rate_limiter = RateLimiter(max_requests=settings.app_rate_limit, window_seconds=settings.app_rate_window)

    if settings.app_auth_enabled:
        @application.middleware("http")
        async def auth_middleware(request, call_next):
            if request.url.path in _NO_AUTH_PATHS or request.url.path.startswith("/api/product/v1") or request.url.path.startswith("/v2/ui/dist") or request.url.path.startswith("/v2/reports/") or request.url.path.startswith("/v2/plugins/tools/") and request.url.path.endswith("/test"):
                return await call_next(request)
            token = request.headers.get("Authorization", "").replace("Bearer ", "")
            if not token:
                logger.warning("auth_failed_no_token | ip=%s | path=%s", request.client.host if request.client else "unknown", request.url.path)
                return JSONResponse(status_code=401, content={"error": "Unauthorized"})
            if settings.app_auth_token and token == settings.app_auth_token:
                return await call_next(request)
            try:
                from ktp_backend.auth import decode_jwt
                decode_jwt(token)
                return await call_next(request)
            except Exception:
                logger.warning("auth_failed | ip=%s | path=%s", request.client.host if request.client else "unknown", request.url.path)
                return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    else:
        logger.warning("API authentication is DISABLED. Set APP_AUTH_ENABLED=true for production.")

    @application.middleware("http")
    async def rate_limit_middleware(request, call_next):
        # 豁免无鉴权路径与长连接 SSE 流式端点：发消息/流式对话是核心动作，
        # 且单条长连接不应计入按请求数的限流，否则正常对话会被自己的限流挡掉。
        if request.url.path in _NO_AUTH_PATHS or request.url.path.endswith("/messages/stream") or (request.url.path.startswith("/api/product/v1/submissions/") and request.url.path.endswith("/events")):
            return await call_next(request)
        client_ip = request.client.host if request.client else "unknown"
        if not rate_limiter.is_allowed(client_ip):
            return JSONResponse(status_code=429, content={"error": "Rate limit exceeded. Try again later."})
        return await call_next(request)

    @application.middleware("http")
    async def request_size_middleware(request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            max_bytes = settings.app_max_request_body_mb * 1024 * 1024
            if int(content_length) > max_bytes:
                return JSONResponse(status_code=413, content={"error": f"Request body too large. Max {settings.app_max_request_body_mb}MB"})
        return await call_next(request)

    @application.middleware("http")
    async def error_handling_middleware(request, call_next):
        try:
            return await call_next(request)
        except Exception as e:
            logger.exception("unhandled_error | method=%s | path=%s | error=%s", request.method, request.url.path, e)
            return JSONResponse(status_code=500, content={"error": "Internal server error"})
    conversation_store = ConversationStore(
        db_path=gateway_config.conversation_db_path,
    )
    resolved_llm_provider = llm_provider_override
    if resolved_llm_provider is None:
        resolved_llm_provider = _resolve_optional_chat_llm_provider()
    runtime_host = build_backend_runtime_host(
        llm_provider_override=resolved_llm_provider,
    )
    install_backend_api(
        application,
        include_root_health=False,
        runtime_host_override=runtime_host,
    )
    application.state.conversation_service = ConversationService(
        conversation_store=conversation_store,
    )
    application.state.agent_llm_provider = resolved_llm_provider
    application.state.gateway_agent_service = GatewayRuntimeBridge(
        runtime_store=runtime_host.runtime_store,
        runtime_engine=runtime_host.runtime_engine,
    )
    application.state.chat_service = application.state.gateway_agent_service
    install_canonical_product_api(
        application,
        db_path=str(runtime_host.settings.sqlite_path),
        auth_required=settings.app_auth_enabled,
        auth_token=settings.app_auth_token,
    )
    application.include_router(health_router)
    application.include_router(v2_ui_router)
    application.include_router(v2_artifacts_router)
    application.include_router(chat_ui_router)
    application.include_router(chat_router)
    application.include_router(conversation_router)
    application.include_router(detect_router)
    application.include_router(openai_adapter_router, prefix="/v1")
    application.include_router(auth_router)

    if _V2_WEB_DIST_DIR.exists():
        application.mount(
            "/v2/ui/dist",
            StaticFiles(directory=str(_V2_WEB_DIST_DIR)),
            name="v2-ui-dist",
        )

    # Serve generated LAI HTML reports at /v2/reports/
    _LAI_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    application.mount(
        "/v2/reports",
        StaticFiles(directory=str(_LAI_REPORTS_DIR)),
        name="v2-lai-reports",
    )

    @application.get("/", response_model=PingResponse, tags=["system"])
    async def root() -> PingResponse:
        return PingResponse(
            message="pong",
            service=settings.app_name,
            environment=settings.app_env,
        )

    return application


def _resolve_optional_chat_llm_provider() -> AgentLLMProvider | None:
    try:
        return get_agent_llm_provider()
    except AgentLLMError:
        logger.exception("api_gateway_chat_llm_provider_unavailable")
        return None


try:
    app = create_app()
except ModuleNotFoundError:
    logger.warning("Full app creation failed — running in degraded mode")
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        description="Scaffold API gateway for the remote sensing multi-agent system.",
    )
