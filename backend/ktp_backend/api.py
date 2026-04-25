"""HTTP API surface for the standalone KTP backend runtime."""

from __future__ import annotations

import asyncio
import json
import logging
from threading import Thread
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from infra.llm.provider import AgentLLMProvider
from ktp_backend.runtime_host import (
    BackendRuntimeHost,
    build_backend_runtime_host,
    install_backend_runtime_host,
)
from v2.apps.api.config import V2ApiSettings, get_v2_api_settings
from v2.shared.logging import configure_v2_logging
from v2.shared.schemas import (
    AgentProfile,
    CreateSessionRequest,
    CreateSessionResponse,
    DomainPackSummary,
    HealthResponse,
    ReplayResponseV2,
    RunDetail,
    RunEventV2,
    RunStateV2,
    RunSummary,
    SendMessageRequest,
    SessionDetail,
    SessionStateV2,
    SessionSummary,
    ToolSpecV2,
    TraceEventV2,
    UpdateSessionRequest,
)

settings = get_v2_api_settings()
configure_v2_logging(settings.log_level)
logger = logging.getLogger(__name__)


def install_backend_api(
    app: FastAPI,
    *,
    settings_override: V2ApiSettings | None = None,
    include_root_health: bool = True,
    runtime_host_override: BackendRuntimeHost | None = None,
    runtime_store_override=None,
    tool_registry_override=None,
    agent_registry_override=None,
    policy_registry_override=None,
    pack_registry_override=None,
    llm_provider_override: AgentLLMProvider | None = None,
) -> None:
    resolved_settings = settings_override or settings
    logger.info(
        "backend_api_install | host=%s | port=%s | store_backend=%s | include_root_health=%s",
        resolved_settings.host,
        resolved_settings.port,
        resolved_settings.store_backend,
        include_root_health,
    )
    runtime_host = runtime_host_override or build_backend_runtime_host(
        settings_override=resolved_settings,
        runtime_store_override=runtime_store_override,
        tool_registry_override=tool_registry_override,
        agent_registry_override=agent_registry_override,
        policy_registry_override=policy_registry_override,
        pack_registry_override=pack_registry_override,
        llm_provider_override=llm_provider_override,
    )
    install_backend_runtime_host(app, runtime_host)

    if include_root_health:

        @app.get("/health", response_model=HealthResponse, tags=["system"])
        async def health() -> HealthResponse:
            return HealthResponse(status="ok", service="ktp-backend", version=resolved_settings.version)

    @app.get("/v2/health", response_model=HealthResponse, tags=["system"])
    async def health_v2() -> HealthResponse:
        return HealthResponse(status="ok", service="ktp-backend", version=resolved_settings.version)

    @app.post("/v2/sessions", response_model=CreateSessionResponse, tags=["sessions"])
    async def create_session(payload: CreateSessionRequest) -> CreateSessionResponse:
        session = app.state.runtime_store.create_session(
            session_id=str(uuid4()),
            title=payload.title or "New Session",
            created_by=payload.user_id,
        )
        logger.info("backend_session_created | session_id=%s", session.session_id)
        return CreateSessionResponse(session=session)

    @app.get("/v2/sessions", response_model=list[SessionSummary], tags=["sessions"])
    async def list_sessions() -> list[SessionSummary]:
        return app.state.runtime_store.list_sessions()

    @app.get("/v2/sessions/{session_id}", response_model=SessionDetail, tags=["sessions"])
    async def get_session(session_id: str) -> SessionDetail:
        session = app.state.runtime_store.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session_not_found")
        return session

    @app.delete("/v2/sessions/{session_id}", status_code=204, tags=["sessions"])
    async def delete_session(session_id: str) -> None:
        session = app.state.runtime_store.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session_not_found")
        app.state.runtime_store.delete_session(session_id)

    @app.patch("/v2/sessions/{session_id}", response_model=SessionDetail, tags=["sessions"])
    async def update_session(session_id: str, payload: UpdateSessionRequest) -> SessionDetail:
        session = app.state.runtime_store.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session_not_found")
        if payload.title is not None:
            session.title = payload.title
        app.state.runtime_store.save_session(session)
        return session

    @app.get("/v2/sessions/{session_id}/state", response_model=SessionStateV2, tags=["sessions"])
    async def get_session_state(session_id: str) -> SessionStateV2:
        session = app.state.runtime_store.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session_not_found")
        latest_run = None
        if session.latest_run_id is not None:
            latest_run = app.state.runtime_store.get_run(session.latest_run_id)
        return SessionStateV2(session=session, latest_run=latest_run)

    @app.get("/v2/sessions/{session_id}/runs", response_model=list[RunSummary], tags=["sessions"])
    async def list_session_runs(session_id: str) -> list[RunSummary]:
        session = app.state.runtime_store.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session_not_found")
        return app.state.runtime_store.list_runs_for_session(session_id)

    @app.get("/v2/runs", response_model=list[RunSummary], tags=["runs"])
    async def list_runs() -> list[RunSummary]:
        return app.state.runtime_store.list_runs()

    @app.post("/v2/sessions/{session_id}/messages", response_model=RunDetail, tags=["sessions"])
    async def send_message(session_id: str, payload: SendMessageRequest) -> RunDetail:
        try:
            run = app.state.runtime_engine.run(
                session_id=session_id,
                user_message=payload.message,
                user_id=payload.user_id,
                request_context=payload.context,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="session_not_found") from exc
        except RuntimeError as exc:
            logger.error("backend_run_failed | session_id=%s | error=%s", session_id, exc)
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except Exception as exc:
            logger.error("backend_run_unexpected_error | session_id=%s | error=%s", session_id, exc)
            raise HTTPException(status_code=500, detail="internal_runtime_error") from exc
        logger.info("backend_run_completed | session_id=%s | run_id=%s", session_id, run.run_id)
        return run

    @app.post("/v2/sessions/{session_id}/messages/stream", tags=["sessions"])
    async def stream_message(session_id: str, payload: SendMessageRequest) -> StreamingResponse:
        session = app.state.runtime_store.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session_not_found")

        async def event_stream():
            queue: asyncio.Queue[str | None] = asyncio.Queue()
            event_loop = asyncio.get_running_loop()

            def worker() -> None:
                def push(encoded: str | None) -> None:
                    asyncio.run_coroutine_threadsafe(queue.put(encoded), event_loop).result()

                try:
                    for event in app.state.runtime_engine.stream(
                        session_id=session_id,
                        user_message=payload.message,
                        user_id=payload.user_id,
                        request_context=payload.context,
                    ):
                        push(_encode_sse(event))
                except Exception as exc:  # pragma: no cover
                    error_event = RunEventV2(
                        sequence=0,
                        event="run.error",
                        run_id="pending",
                        session_id=session_id,
                        detail=str(exc),
                        run_status="failed",
                    )
                    push(_encode_sse(error_event))
                finally:
                    push(None)

            worker_thread = Thread(target=worker, daemon=True)
            worker_thread.start()
            try:
                while True:
                    try:
                        item = await asyncio.wait_for(queue.get(), timeout=15.0)
                    except asyncio.TimeoutError:
                        yield ": heartbeat\n\n"
                        continue
                    if item is None:
                        break
                    yield item
            finally:
                worker_thread.join(timeout=1)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/v2/runs/{run_id}", response_model=RunDetail, tags=["runs"])
    async def get_run(run_id: str) -> RunDetail:
        run = app.state.runtime_store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run_not_found")
        return run

    @app.get("/v2/runs/{run_id}/trace", response_model=list[TraceEventV2], tags=["runs"])
    async def get_run_trace(run_id: str) -> list[TraceEventV2]:
        run = app.state.runtime_store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run_not_found")
        return run.trace

    @app.get("/v2/runs/{run_id}/state", response_model=RunStateV2, tags=["runs"])
    async def get_run_state(run_id: str) -> RunStateV2:
        try:
            return app.state.runtime_engine.build_run_state(run_id=run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run_not_found") from exc

    @app.post("/v2/runs/{run_id}/replay", response_model=ReplayResponseV2, tags=["runs"])
    async def replay_run(run_id: str) -> ReplayResponseV2:
        try:
            return app.state.runtime_engine.replay(run_id=run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run_not_found") from exc

    @app.get("/v2/tools", response_model=list[ToolSpecV2], tags=["metadata"])
    async def list_tools() -> list[ToolSpecV2]:
        return app.state.tool_registry.list_tools()

    @app.get("/v2/agents", response_model=list[AgentProfile], tags=["metadata"])
    async def list_agents() -> list[AgentProfile]:
        return app.state.agent_registry.list_profiles()

    @app.get("/v2/domain-packs", response_model=list[DomainPackSummary], tags=["metadata"])
    async def list_packs() -> list[DomainPackSummary]:
        return app.state.pack_registry.list_packs()


def create_backend_app(
    *,
    settings_override: V2ApiSettings | None = None,
    runtime_host_override: BackendRuntimeHost | None = None,
    runtime_store_override=None,
    tool_registry_override=None,
    agent_registry_override=None,
    policy_registry_override=None,
    pack_registry_override=None,
    llm_provider_override: AgentLLMProvider | None = None,
) -> FastAPI:
    resolved_settings = settings_override or settings
    logger.info(
        "backend_api_create_app | host=%s | port=%s | store_backend=%s",
        resolved_settings.host,
        resolved_settings.port,
        resolved_settings.store_backend,
    )
    app = FastAPI(
        title=resolved_settings.title,
        version=resolved_settings.version,
        description="Standalone backend API for the KTP chat-first agent.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins_list(),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_backend_api(
        app,
        settings_override=resolved_settings,
        include_root_health=True,
        runtime_host_override=runtime_host_override,
        runtime_store_override=runtime_store_override,
        tool_registry_override=tool_registry_override,
        agent_registry_override=agent_registry_override,
        policy_registry_override=policy_registry_override,
        pack_registry_override=pack_registry_override,
        llm_provider_override=llm_provider_override,
    )
    return app


def _encode_sse(event: RunEventV2) -> str:
    payload = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
    return f"event: {event.event}\ndata: {payload}\n\n"

