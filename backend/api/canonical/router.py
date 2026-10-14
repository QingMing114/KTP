"""Canonical product API router (/api/product/v1).

Thin adapter over the V2 runtime — translates canonical product protocol
requests into internal V2 calls and maps responses back.

Design:
  conversation_id ≡ session_id  (the V2 runtime calls them "sessions")
  submission      = engine.stream() wrapped with an SSE event queue
  run             = RunDetail (mapped)
  artifact        = PackArtifactView (mapped)
  dataset         = local file reference registered with stable id
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import threading
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone
from typing import AsyncIterator
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware

from runtime.artifact_store import ArtifactRecord, ArtifactStore
from runtime.dataset_store import DatasetStore
from runtime.farm_store import FarmStore
from runtime.idempotency_store import IdempotencyStore
from runtime.submission_store import SubmissionStore
from runtime.lai_analysis_store import LaiAnalysisStore
from runtime.crop_analysis_store import CropAnalysisStore
from runtime.analysis_workflow_store import AnalysisWorkflowStore
from runtime.analysis_workflow_runner import ensure_workflow_reports, run_analysis_workflow
from runtime.workspace_assistant import (plan_workspace, workspace_parts, can_rebase_preview, TASK_LABELS,
                                         automatic_imagery_request, choose_automatic_imagery)
from runtime.workspace_lai import workspace_lai_query
from schemas.workspace import WorkspaceContext, WorkspaceIntent, ProfessionalReview, ConfirmProfessionalReviewRequest
from runtime.professional_review import create_review, review_part, validate_lai_lut_ranges
from schemas.runtime import SceneParameters
from runtime.workflow_reports import REPORT_VERSION, register_crop_report
from runtime.yield_input_assessment import assess_yield_inputs
from infra.imagery.stac_provider import ImagerySearchError, SentinelStacProvider
from infra.imagery.aoi_band_reader import AoiBandReadError, read_prosail_reflectance_aoi
from schemas.canonical import (
    ApsimYieldMetrics,
    ApsimYieldReportResponse,
    CanonicalArtifact,
    CanonicalAssistantPart,
    CanonicalConversation,
    CanonicalDataset,
    CanonicalRunResponse,
    ConversationListResponse,
    CreateConversationRequest,
    CreateApsimYieldReportRequest,
    CreateDatasetRequest,
    CreateSubmissionRequest,
    DatasetListResponse,
    DatasetSource,
    ManifestResponse,
    PaginatedRunsResponse,
    SessionDetail,
    SubmissionContext,
    SubmissionEventKind,
    SubmissionResponse,
    SubmissionStage,
    UpdateConversationRequest,
    UpdateDatasetRequest,
)
from schemas.errors import ErrorCode, canonical_error_response
from schemas.spatial import FarmListResponse
from schemas.spatial import CreateLaiAnalysisRequest, LaiAnalysisSummary, CreateCropAnalysisRequest, CropAnalysisSummary, ImagerySearchRequest, ImagerySearchResponse
from schemas.analysis_workflow import (
    AnalysisWorkflowEventsResponse, AnalysisWorkflowSummary, CreateAnalysisWorkflowRequest,
    RetryAnalysisWorkflowRequest,
    UpdateYieldInputsRequest,
)
from shared.config.paths import get_lai_report_dir
from v2.tools.lai_report_handler import run_lai_html_report
from infra.imagery.crop_spatial import CropInferenceError, run_crop_spatial_analysis, verify_crop_model
from v2.tools.apsim_report_handler import get_apsim_demo_db_path, run_apsim_yield_report
from v2.runtime.engine import BoundedRuntimeEngine
from v2.runtime.store import RuntimeStore
from schemas.runtime import (
    RequestContextV2,
    ResolvedDatasetV2,
    RunDetail,
    RunEventV2,
    SessionMessage,
)

logger = logging.getLogger(__name__)

_PRODUCT_ARTIFACT_ROOT = (Path(__file__).resolve().parents[2] / "var" / "artifacts").resolve()
_CANONICAL_ALGORITHM_PERMISSIONS = frozenset({"dataset:read", "artifact:write"})


class CanonicalProtocolMiddleware(BaseHTTPMiddleware):
    """Own canonical authentication and normalize every canonical error response."""

    _PUBLIC_ENDPOINTS = {
        ("GET", "/api/product/v1/manifest"),
        ("GET", "/api/product/v1/farms"),
        ("POST", "/api/product/v1/imagery/search"),
    }

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/product/v1"):
            return await call_next(request)

        auth_error = self._authenticate(request)
        if auth_error is not None:
            return auth_error
        response = await call_next(request)
        if response.status_code < 400:
            return response

        body = b"".join([chunk async for chunk in response.body_iterator])
        try:
            payload = json.loads(body) if body else {}
        except (TypeError, ValueError):
            payload = {"detail": body.decode("utf-8", errors="replace")}
        headers = {
            key: value for key, value in response.headers.items()
            if key.lower() in {"www-authenticate", "retry-after"}
        }
        if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
            return JSONResponse(status_code=response.status_code, content=payload, headers=headers)
        detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
        code = {
            401: ErrorCode.UNAUTHORIZED,
            404: ErrorCode.INVALID_REQUEST,
            409: ErrorCode.INVALID_REQUEST,
            422: ErrorCode.INVALID_REQUEST,
        }.get(response.status_code, ErrorCode.INTERNAL_ERROR if response.status_code >= 500 else ErrorCode.INVALID_REQUEST)
        return canonical_error_response(
            response.status_code,
            code=code,
            message=self._error_message(detail, response.status_code),
            detail={"validation": detail} if detail else {},
            request_id=str(uuid4()),
            headers=headers,
        )

    @classmethod
    def _authenticate(cls, request: Request) -> JSONResponse | None:
        required = bool(getattr(request.app.state, "product_auth_required", False))
        authorization = request.headers.get("Authorization", "")
        token = authorization.removeprefix("Bearer ").strip()
        if not token:
            if not required or (request.method, request.url.path) in cls._PUBLIC_ENDPOINTS:
                request.state.product_principal = "anonymous"
                return None
            return canonical_error_response(
                401,
                code=ErrorCode.UNAUTHORIZED,
                message="Authentication is required for this canonical endpoint",
                request_id=str(uuid4()),
                headers={"WWW-Authenticate": "Bearer"},
            )
        configured_token = str(getattr(request.app.state, "product_auth_token", "") or "")
        if configured_token and hmac.compare_digest(token, configured_token):
            request.state.product_principal = "api-key"
            return None
        try:
            from ktp_backend.auth import decode_jwt
            payload = decode_jwt(token)
            request.state.product_principal = payload.user_id
            return None
        except Exception:
            return canonical_error_response(
                401,
                code=ErrorCode.UNAUTHORIZED,
                message="The supplied bearer token is invalid or expired",
                request_id=str(uuid4()),
                headers={"WWW-Authenticate": "Bearer"},
            )

    @staticmethod
    def _error_message(detail: object, status_code: int) -> str:
        if isinstance(detail, str) and detail:
            return detail
        if status_code == 422:
            return "Request validation failed"
        return f"Canonical request failed with HTTP {status_code}"


def _lai_pixel_progress(processed: int, total: int) -> tuple[str, dict[str, int]]:
    """Map numerical inversion progress to a user-facing detail and typed data."""
    total_pixels = max(0, int(total))
    processed_pixels = min(max(0, int(processed)), total_pixels)
    if total_pixels == 0:
        detail = "AOI 中没有可反演的有效像元，正在汇总结果"
        current_pixel = 0
    elif processed_pixels == 0:
        current_pixel = 1
        detail = f"正在反演第 1 / {total_pixels} 个有效像元"
    elif processed_pixels >= total_pixels:
        current_pixel = total_pixels
        detail = f"已完成 {total_pixels} / {total_pixels} 个有效像元，正在汇总结果"
    else:
        current_pixel = processed_pixels + 1
        detail = (
            f"已完成 {processed_pixels} / {total_pixels} 个有效像元，"
            f"正在处理第 {current_pixel} 个"
        )
    return detail, {
        "processed_pixels": processed_pixels,
        "current_pixel": current_pixel,
        "total_pixels": total_pixels,
    }


def _lai_product_result(
    payload: dict,
    *,
    report_artifact_id: str,
    raster_artifact_id: str,
    preview_artifact_id: str,
) -> dict:
    """Build the stable result contract consumed by the map workspace."""
    result = dict(payload)
    result["report_artifact_id"] = report_artifact_id
    result["report_uri"] = f"/api/product/v1/artifacts/{report_artifact_id}/render"
    result["lai_raster_artifact_id"] = raster_artifact_id
    result["lai_raster_uri"] = f"/api/product/v1/artifacts/{raster_artifact_id}/content"
    result["lai_preview_artifact_id"] = preview_artifact_id
    result["lai_preview_uri"] = f"/api/product/v1/artifacts/{preview_artifact_id}/content"
    result["map_overlay"] = {
        "url": result["lai_preview_uri"],
        "bounds": result.get("bounds_wgs84"),
        "opacity": 0.72,
        "color_scale": result.get("color_scale"),
    }
    return result

# Endpoints that support Idempotency-Key (from canonical_api_spec.md)
_IDEMPOTENT_POST_ENDPOINTS = {
    "/datasets",
    "/conversations",
    "/conversations/{conversation_id}/submissions",
    "/submissions/{submission_id}/cancel",
    "/analysis-workflows",
}


# ── Router factory ──

def build_canonical_router() -> APIRouter:
    """Build and return the canonical product API router.

    Call ``app.include_router(router, prefix="/api/product/v1")`` to mount.
    """
    router = APIRouter(tags=["product"])

    # ── Dependency helpers ──

    def _store(request: Request) -> RuntimeStore:
        return request.app.state.runtime_store

    def _engine(request: Request) -> BoundedRuntimeEngine:
        return request.app.state.runtime_engine

    # Artifact kinds whose content is renderable HTML.
    _HTML_ARTIFACT_KINDS: set[str] = {
        "lai_html_report", "apsim_report", "simple_yield_report", "canopy_index_report",
        "crop_classification_report", "growth_observation_report", "workflow_summary_report",
        "workflow_demo_step_report",
    }
    _BINARY_ARTIFACT_KINDS: set[str] = {
        "lai_raster",
        "lai_preview",
        "reflectance_tif",
        "analysis_result_json",
        "classification_result",
        "segmentation_mask",
        "segmentation_preview",
        "statistics_table",
        "provenance_record",
    }

    def _binary_artifact_path(record: ArtifactRecord, request: Request) -> Path | None:
        """Resolve a registered local artifact without allowing arbitrary file access."""
        if record.artifact_type not in _BINARY_ARTIFACT_KINDS or not record.content_path:
            return None
        candidate = Path(record.content_path)
        if not candidate.is_absolute():
            return None
        candidate = candidate.resolve()
        configured_root = getattr(request.app.state, "product_artifact_root", None)
        roots = [_PRODUCT_ARTIFACT_ROOT]
        if configured_root is not None:
            roots.append(Path(configured_root).resolve())
        if not any(candidate.is_relative_to(root) for root in roots):
            return None
        return candidate if candidate.is_file() else None

    def _submission_store(request: Request) -> SubmissionStore:
        store: SubmissionStore | None = getattr(request.app.state, "product_submission_store", None)
        assert store is not None, "submission_store not initialized"
        return store

    def _dataset_store(request: Request) -> DatasetStore:
        store: DatasetStore | None = getattr(request.app.state, "product_dataset_store", None)
        assert store is not None, "dataset_store not initialized"
        return store

    def _artifact_store(request: Request) -> ArtifactStore:
        store: ArtifactStore | None = getattr(request.app.state, "product_artifact_store", None)
        assert store is not None, "artifact_store not initialized"
        return store

    def _check_map_report_owner(record: ArtifactRecord, request: Request) -> None:
        if record.artifact_type not in {
            "crop_classification_report", "growth_observation_report",
            "workflow_summary_report", "canopy_index_report", "apsim_report", "simple_yield_report",
            "analysis_result_json",
            "workflow_demo_step_report",
        }:
            return
        owner = _analysis_workflow_store(request).owner_of(record.run_id)
        if owner is None:
            crop_analysis = _crop_analysis_store(request).get(record.run_id)
            if crop_analysis is not None and crop_analysis.owner_id is None:
                return  # Historical crop analyses were stored without an owner.
            owner = crop_analysis.owner_id if crop_analysis is not None else None
        if owner is None and record.artifact_type == "apsim_report":
            return  # Existing independent APSIM demo reports have no map workflow owner.
        if owner is None or owner != _extract_user(request):
            raise HTTPException(status_code=404, detail="Artifact not found")

    def _idempotency_store(request: Request) -> IdempotencyStore:
        store: IdempotencyStore | None = getattr(request.app.state, "product_idempotency_store", None)
        assert store is not None, "idempotency_store not initialized"
        return store

    def _farm_store(request: Request) -> FarmStore:
        store: FarmStore | None = getattr(request.app.state, "product_farm_store", None)
        assert store is not None, "farm_store not initialized"
        return store

    def _imagery_provider(request: Request) -> SentinelStacProvider:
        provider: SentinelStacProvider | None = getattr(request.app.state, "sentinel_stac_provider", None)
        assert provider is not None, "sentinel_stac_provider not initialized"
        return provider

    def _lai_analysis_store(request: Request) -> LaiAnalysisStore:
        store: LaiAnalysisStore | None = getattr(request.app.state, "lai_analysis_store", None)
        assert store is not None, "lai_analysis_store not initialized"
        return store

    def _crop_analysis_store(request: Request) -> CropAnalysisStore:
        store: CropAnalysisStore | None = getattr(request.app.state, "crop_analysis_store", None)
        assert store is not None, "crop_analysis_store not initialized"
        return store

    def _analysis_workflow_store(request: Request) -> AnalysisWorkflowStore:
        store: AnalysisWorkflowStore | None = getattr(request.app.state, "analysis_workflow_store", None)
        assert store is not None, "analysis_workflow_store not initialized"
        return store

    def _extract_user(request: Request) -> str:
        """Extract user identity from Authorization header, or return 'anonymous'."""
        principal = getattr(request.state, "product_principal", None)
        if isinstance(principal, str) and principal:
            return principal
        auth = request.headers.get("Authorization", "")
        token = auth.replace("Bearer ", "").strip()
        if not token:
            return "anonymous"
        try:
            from ktp_backend.auth import decode_jwt
            payload = decode_jwt(token)
            return payload.get("user_id", "anonymous")
        except Exception:
            return "anonymous"

    def _req_id() -> str:
        """Generate a request_id for error tracing."""
        return str(uuid4())

    # ── Idempotency helpers ──

    async def _idempotency_result(
        request: Request,
        idempotency_key: str | None,
        endpoint: str,
        body_bytes: bytes,
    ) -> JSONResponse | None:
        """Claim a persistent key, replay a completed response, or reject conflicts."""
        if idempotency_key is None:
            return None
        principal = _extract_user(request)
        request_hash = hashlib.sha256(body_bytes).hexdigest()
        store = _idempotency_store(request)
        claim = store.claim(
            principal=principal,
            key=idempotency_key,
            endpoint=endpoint,
            request_hash=request_hash,
        )
        if claim.status == "in_progress":
            claim = await asyncio.to_thread(
                store.wait_for_completion,
                principal=principal,
                key=idempotency_key,
                endpoint=endpoint,
                request_hash=request_hash,
            )
        if claim.status == "replay":
            logger.info("idempotency_replay | principal=%s | key=%s", principal, idempotency_key[:8])
            return JSONResponse(status_code=claim.response_status or 200, content=claim.response_body)
        if claim.status == "conflict":
            return canonical_error_response(
                409,
                code=ErrorCode.IDEMPOTENCY_CONFLICT,
                message="Idempotency-Key was already used with a different endpoint or request body",
                request_id=_req_id(),
            )
        if claim.status == "in_progress":
            return canonical_error_response(
                409,
                code=ErrorCode.IDEMPOTENCY_CONFLICT,
                message="An identical request with this Idempotency-Key is still processing",
                request_id=_req_id(),
                headers={"Retry-After": "1"},
            )
        request.state._idempotency_claim = (principal, idempotency_key, endpoint, request_hash)
        return None

    def _cache_idempotency(
        request: Request,
        response_status: int,
        response_body: dict | list,
    ) -> None:
        claim = getattr(request.state, "_idempotency_claim", None)
        if claim is None:
            return
        principal, key, endpoint, request_hash = claim
        _idempotency_store(request).complete(
            principal=principal,
            key=key,
            endpoint=endpoint,
            request_hash=request_hash,
            response_status=response_status,
            response_body=response_body,
        )

    def _release_idempotency(request: Request) -> None:
        claim = getattr(request.state, "_idempotency_claim", None)
        if claim is None:
            return
        principal, key, endpoint, request_hash = claim
        _idempotency_store(request).release(
            principal=principal,
            key=key,
            endpoint=endpoint,
            request_hash=request_hash,
        )

    async def _read_body_bytes(request: Request) -> bytes:
        """Read and cache the request body as bytes."""
        cached = getattr(request.state, "_body_bytes", None)
        if cached is not None:
            return cached
        body_bytes = await request.body()
        request.state._body_bytes = body_bytes
        return body_bytes

    # ── Mappers ──

    def _session_to_conversation(session: SessionDetail) -> CanonicalConversation:
        return CanonicalConversation(
            conversation_id=session.session_id,
            title=session.title,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )

    def _build_artifact_list(run: RunDetail, art_store: ArtifactStore | None) -> list[CanonicalArtifact]:
        """Build the canonical artifact list for *run*, preferring stable UUIDs."""
        if art_store is not None:
            records = art_store.list_by_run(run.run_id)
            if records:
                return [_record_to_canonical(r) for r in records]
        # Fallback to legacy enumerate (backward-compatible, store not available)
        return [_artifact_to_canonical(a, artifact_index=i) for i, a in enumerate(run.artifacts)]

    def _artifact_to_canonical(artifact, *, artifact_index: int = 0) -> CanonicalArtifact:
        artifact_id = f"{artifact.pack_name}:{artifact.artifact_type}:{artifact_index}"
        # Phase C.1: HTML artifacts get a renderable view_url; non-HTML artifacts
        # get the metadata JSON endpoint as their view_url.
        if artifact.artifact_type in _HTML_ARTIFACT_KINDS:
            view_url = f"/api/product/v1/artifacts/{artifact_id}/render"
        else:
            view_url = f"/api/product/v1/artifacts/{artifact_id}"
        return CanonicalArtifact(
            artifact_id=artifact_id,
            kind=artifact.artifact_type,
            title=artifact.title,
            view_url=view_url,
            download_url=f"/api/product/v1/artifacts/{artifact_id}/content",
            content=artifact.content,
        )

    def _record_to_canonical(record: ArtifactRecord) -> CanonicalArtifact:
        """Convert an ArtifactRecord (stable UUID) to a CanonicalArtifact."""
        if record.artifact_type in _HTML_ARTIFACT_KINDS:
            view_url = f"/api/product/v1/artifacts/{record.artifact_id}/render"
        elif record.artifact_type == "lai_preview":
            view_url = f"/api/product/v1/artifacts/{record.artifact_id}/content"
        else:
            view_url = f"/api/product/v1/artifacts/{record.artifact_id}"
        return CanonicalArtifact(
            artifact_id=record.artifact_id,
            kind=record.kind,
            title=record.title,
            view_url=view_url,
            download_url=f"/api/product/v1/artifacts/{record.artifact_id}/content",
            content=record.content_inline,
        )

    def _run_to_canonical(run: RunDetail, art_store: ArtifactStore | None = None) -> CanonicalRunResponse:
        assistant_parts: list[CanonicalAssistantPart] = []
        assistant_summary = run.output_message
        if run.assistant_message is not None:
            for part in run.assistant_message.parts:
                if part.type == "artifact":
                    if part.artifact is None:
                        continue  # skip incomplete artifact parts
                    canonical_art = _artifact_to_canonical(part.artifact)
                    mapped = CanonicalAssistantPart(type="artifact_ref", artifact_id=canonical_art.artifact_id)
                elif part.type == "error":
                    mapped = CanonicalAssistantPart(type="error", text=part.text or part.status or "")
                elif part.type == "text":
                    mapped = CanonicalAssistantPart(type="text", text=part.text or "")
                else:
                    mapped = CanonicalAssistantPart(type="status", text=part.text or part.status or part.type)
                assistant_parts.append(mapped)
            text_parts = [p.text for p in assistant_parts if p.text]
            if text_parts:
                assistant_summary = "\n".join(text_parts)

        return CanonicalRunResponse(
            run_id=run.run_id,
            conversation_id=run.session_id,
            status=run.status,
            assistant={"summary": assistant_summary, "parts": run.product_parts or assistant_parts},
            input_message=run.input_message,
            created_at=run.product_created_at,
            artifacts=_build_artifact_list(run, art_store),
            workflow_summary=run.observation.summary if run.observation else None,
            termination_reason=run.observation.payload.get("error") if run.observation and run.observation.status == "error" else None,
        )

    def _map_internal_event_to_ss_event(event: RunEventV2, submission_id: str) -> dict | None:
        """Translate an internal RunEventV2 into a canonical SSE event dict."""
        base = {
            "submission_id": submission_id,
            "run_id": event.run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        event_name = event.event

        if event_name == "run_started":
            return {**base, "event": "run.started", "stage": "processing", "detail": event.detail}
        if event_name == "run_completed":
            return {**base, "event": "run.completed", "stage": "completed", "detail": event.detail}
        if event_name == "run_failed":
            return {**base, "event": "run.failed", "stage": "failed", "detail": event.detail}
        if event_name in ("planner_decision", "planner_start"):
            return {**base, "event": "run.progress", "stage": "processing", "detail": event.detail}
        if event_name in ("tool_call_started", "tool_call_completed"):
            tool = event.tool_invocation
            return {
                **base,
                "event": "run.progress",
                "stage": "processing",
                "detail": f"{event_name}: {tool.tool_name if tool else 'unknown'}",
                "data": {
                    "tool_name": tool.tool_name if tool else None,
                    "tool_call_id": tool.call_id if tool else None,
                },
            }
        if event_name == "artifact_created" and event.artifact is not None:
            return {
                **base,
                "event": "artifact.available",
                "stage": "processing",
                "detail": f"Artifact ready: {event.artifact.title}",
                "data": {"artifact_type": event.artifact.artifact_type, "artifact_title": event.artifact.title},
            }
        if event_name == "assistant_message" and event.assistant_part is not None:
            return {
                **base,
                "event": "run.progress",
                "stage": "processing",
                "detail": "Assistant message part received",
                "data": {"assistant_part_type": event.assistant_part.type, "assistant_part_text": event.assistant_part.text},
            }

        logger.debug("unmapped_internal_event %r → run.progress", event_name)
        return {**base, "event": "run.progress", "stage": "processing", "detail": event.detail or event_name}

    def _inherit_context(
        store: RuntimeStore,
        conversation_id: str,
        context: SubmissionContext | None,
    ) -> RequestContextV2:
        """Build a RequestContextV2, optionally inheriting from the latest run.

        Per canonical_api_spec.md §context.inherit:
          - "latest": inherit region / crop_type / task_type / image_path
            from the conversation's most recent run
          - "none" / absent: no inheritance
        """
        if context and context.inherit == "latest":
            # Runtime RunDetail deliberately has no created_at field. The
            # session's latest_run_id is the authoritative runtime pointer.
            session = store.get_session(conversation_id)
            latest = (
                store.get_run(session.latest_run_id)
                if session and session.latest_run_id
                else None
            )

            # Older persisted sessions may predate latest_run_id. Both store
            # implementations return runs in insertion order, so keep a safe
            # compatibility fallback for those records.
            if latest is None:
                runs = store.list_runs_for_session(conversation_id)
                latest = runs[-1] if runs else None

            if latest is not None:
                prev_ctx = latest.input_context
                if prev_ctx is not None:
                    return RequestContextV2(
                        entrypoint="api",
                        conversation_mode=prev_ctx.conversation_mode,
                        region=prev_ctx.region,
                        crop_type=prev_ctx.crop_type,
                        task_type=prev_ctx.task_type,
                        image_path=prev_ctx.image_path,
                        use_mock=prev_ctx.use_mock,
                        attachments=prev_ctx.attachments,
                        datasets=prev_ctx.datasets,
                        client_capabilities=prev_ctx.client_capabilities,
                        extra_params={"inherit_from_run": latest.run_id},
                    )
        return RequestContextV2(entrypoint="api", conversation_mode="chat")

    # ═══════════════════════════════════════════════════════════
    #  Manifest
    # ═══════════════════════════════════════════════════════════

    @router.get("/manifest", response_model=ManifestResponse)
    async def get_manifest(request: Request) -> ManifestResponse:
        """GET /api/product/v1/manifest — capability negotiation."""
        return ManifestResponse(
            protocol_version="1.1",
            features={
                "async_submission": True,
                "sse_events": True,
                "cursor_pagination": True,
                "datasets": True,
                "idempotency": True,
                "multi_agent": True,
                "map_workspace": True,
                "workspace_context": True,
                "workspace_card_context": True,
                "workspace_assistant_actions": True,
                "workspace_auto_execution": True,
                "workspace_professional_reviews": True,
                "simple_yield_estimation": True,
                "analysis_parameter_cards": True,
                "demo_farms": True,
                "apsim_yield_report": True,
            },
            delivery_modes=["async"],
            supported_preferences=["include_visualization", "include_knowledge"],
            artifact_kinds=["lai_html_report", "lai_raster", "lai_preview", "apsim_report", "simple_yield_report", "inference_card", "report_card", "visualization"],
            compat_adapters=["/v2", "/v1"],
            limits={"max_file_mb": 500},
            debug_extension=True,
        )

    # ── APSIM yield estimation ────────────────────────────────────────

    @router.post("/apsim/yield-reports", response_model=ApsimYieldReportResponse)
    async def create_apsim_yield_report(
        body: CreateApsimYieldReportRequest,
        request: Request,
    ) -> ApsimYieldReportResponse:
        """Run APSIM deterministically and return a renderable report artifact."""
        if body.end_year < body.start_year:
            raise HTTPException(status_code=422, detail="结束年份不能早于开始年份")

        if body.mode == "demo":
            demo_db = get_apsim_demo_db_path()
            if not demo_db.is_file():
                raise HTTPException(status_code=503, detail="内置 APSIM Wheat 验证数据不可用")
            tool_params = {
                "crop_type": "wheat",
                "region": "australia-gxexm",
                "start_year": 2014,
                "end_year": 2015,
                "cultivar": "Hartog",
                "db_path": str(demo_db),
                "allow_demo_fallback": False,
                "query": "生成 APSIM 小麦验证数据产量报告",
            }
        else:
            tool_params = {
                "crop_type": body.crop_type,
                "region": body.region,
                "start_year": body.start_year,
                "end_year": body.end_year,
                "cultivar": body.cultivar,
                "sowing_date": body.sowing_date,
                "allow_demo_fallback": False,
                "query": "运行 APSIM 模拟并生成产量估计报告",
            }

        observation, generated = await asyncio.to_thread(
            lambda: run_apsim_yield_report(**tool_params)
        )
        if observation.status != "success" or not generated:
            raise HTTPException(status_code=503, detail=observation.summary)

        artifact_store = _artifact_store(request)
        artifact_id = artifact_store.register(
            run_id=f"apsim_yield_{uuid4().hex}",
            artifact=generated[0],
        )
        record = artifact_store.get(artifact_id)
        if record is None:
            raise HTTPException(status_code=500, detail="APSIM 报告产物注册失败")

        payload = observation.payload
        return ApsimYieldReportResponse(
            status="success",
            mode=body.mode,
            summary=observation.summary,
            metrics=ApsimYieldMetrics(
                estimated_yield_t_ha=float(payload.get("final_yield_t_ha", 0)),
                peak_lai=float(payload.get("peak_lai", 0)),
                max_biomass_g_m2=float(payload.get("max_biomass", 0)),
                simulation_days=int(payload.get("sim_days", 0)),
            ),
            parameters=dict(payload),
            artifact=_record_to_canonical(record),
        )

    # ── Map workspace: demo farms ──────────────────────────────────────

    @router.get("/farms", response_model=FarmListResponse)
    async def list_farms(request: Request) -> FarmListResponse:
        """Return project-owned demo farm boundaries for the map workspace."""
        farms = _farm_store(request).list_farms(user_id=_extract_user(request))
        return FarmListResponse(items=farms)

    @router.post("/imagery/search", response_model=ImagerySearchResponse)
    async def search_imagery(
        body: ImagerySearchRequest,
        request: Request,
    ) -> ImagerySearchResponse:
        """Search Sentinel-2 L2A candidates without downloading imagery."""
        try:
            candidates = await asyncio.to_thread(_imagery_provider(request).search, body)
        except ImagerySearchError as exc:
            return canonical_error_response(
                502,
                code=ErrorCode.IMAGERY_SEARCH_FAILED,
                message="Sentinel imagery search is temporarily unavailable.",
                detail={"reason": str(exc)},
                request_id=_req_id(),
            )
        return ImagerySearchResponse(items=candidates, search_id=str(uuid4()))

    def _launch_analysis_workflow(
        request: Request, workflow: AnalysisWorkflowSummary, selected_item: dict,
        run_task_ids: set[str],
    ) -> AnalysisWorkflowSummary:
        workflows = _analysis_workflow_store(request)
        owner_id = workflow.owner_id
        artifact_root = Path(getattr(request.app.state, "product_artifact_root", _PRODUCT_ARTIFACT_ROOT)).resolve()
        if not workflows.claim_start(workflow.workflow_id, owner_id=owner_id):
            return workflows.get(workflow.workflow_id, owner_id=owner_id) or workflow

        def worker() -> None:
            try:
                run_analysis_workflow(
                    workflow.workflow_id, owner_id=owner_id, selected_item=selected_item,
                    artifact_root=artifact_root, workflows=workflows,
                    crops=_crop_analysis_store(request), lais=_lai_analysis_store(request),
                    artifacts=_artifact_store(request), make_lai_result=_lai_product_result,
                    run_task_ids=run_task_ids,
                    llm_provider=getattr(getattr(request.app.state, "runtime_engine", None), "llm_provider", None),
                )
            except Exception:
                logger.exception("analysis_workflow_unhandled_failure | workflow_id=%s", workflow.workflow_id)
                current = workflows.get(workflow.workflow_id, owner_id=owner_id)
                if current is not None:
                    for step in current.steps:
                        if step.status == "running":
                            workflows.update_step(workflow.workflow_id, step.step_id, owner_id=owner_id,
                                                  status="failed", detail="任务执行意外中断，请重试该步骤。")
                    workflows.update_status(workflow.workflow_id, owner_id=owner_id,
                                            status="failed", detail="工作流执行意外中断，请重试失败步骤。")

        threading.Thread(target=worker, daemon=True, name=f"workflow-{workflow.workflow_id[:8]}").start()
        updated = workflows.get(workflow.workflow_id, owner_id=owner_id)
        assert updated is not None
        return updated

    async def _create_verified_workflow(
        body: CreateAnalysisWorkflowRequest, request: Request,
        workspace: WorkspaceContext | None = None,
        cancellation_event=None,
    ) -> AnalysisWorkflowSummary:
        """Shared application service for card buttons and assistant actions."""
        if workspace is None and body.workspace_id:
            workspace = _analysis_workflow_store(request).get_workspace(body.workspace_id, owner_id=_extract_user(request))
            if workspace is None or workspace.revision != body.workspace_revision or workspace.aoi != body.aoi or workspace.imagery_item_id != body.imagery_item_id:
                raise HTTPException(409, "工作台上下文已变化，请重新提交当前任务。")
            if workspace.execution_mode != "live":
                raise HTTPException(400, "演示模式不能创建真实工作流")
        if body.conversation_id:
            session = _store(request).get_session(body.conversation_id)
            if session is None or session.created_by != _extract_user(request):
                raise HTTPException(404, "Conversation not found")
        if body.imagery_snapshot is None:
            raise HTTPException(400, "A server-issued imagery_snapshot is required for a workflow")
        if body.data_mode == "demo":
            if body.imagery_snapshot.item_id != body.imagery_item_id:
                raise HTTPException(400, "演示任务选片信息不一致")
            if cancellation_event is not None and cancellation_event.is_set():
                raise HTTPException(409, "本次问答已取消，任务未启动。")
            try:
                workflow = _analysis_workflow_store(request).create(body, owner_id=_extract_user(request), workspace=workspace)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
            return _launch_analysis_workflow(request, workflow, {}, set()) if body.start_immediately else workflow
        provider = _imagery_provider(request)
        try:
            selected_item = await asyncio.to_thread(provider.get_item, body.imagery_item_id)
        except ImagerySearchError:
            raise HTTPException(502, "The selected Sentinel item cannot be verified")
        try:
            verified_snapshot = provider.validate_selection(
                body.imagery_snapshot, selected_item,
                body.aoi.geometry.model_dump(mode="json"),
            )
        except ImagerySearchError:
            raise HTTPException(400, "The selected imagery snapshot is invalid or no longer matches this AOI")
        verified_body = body.model_copy(update={"imagery_snapshot": verified_snapshot})
        if cancellation_event is not None and cancellation_event.is_set():
            raise HTTPException(409, "本次问答已取消，任务未启动。")
        try:
            workflow = _analysis_workflow_store(request).create(
                verified_body, owner_id=_extract_user(request), workspace=workspace,
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        if not body.start_immediately:
            return workflow
        return _launch_analysis_workflow(
            request, workflow, selected_item,
            set(workflow.effective_task_ids) & {"crop", "lai"},
        )

    @router.post("/analysis-workflows", status_code=201, response_model=AnalysisWorkflowSummary)
    async def create_analysis_workflow(
        body: CreateAnalysisWorkflowRequest, request: Request,
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    ) -> AnalysisWorkflowSummary:
        if body.workspace_id:
            current = _analysis_workflow_store(request).get_workspace(body.workspace_id, owner_id=_extract_user(request))
            if current and current.professional_mode:
                raise HTTPException(409, "专业模式请先在助手中生成并确认参数卡片")
        replay = await _idempotency_result(request, idempotency_key, "/analysis-workflows", await _read_body_bytes(request))
        if replay is not None:
            return replay
        if idempotency_key and body.action_id is None:
            body = body.model_copy(update={"action_id": idempotency_key})
        result = await _create_verified_workflow(body, request)
        _cache_idempotency(request, 201, result.model_dump(mode="json"))
        return result

    @router.put("/workspaces/{workspace_id}/context", response_model=WorkspaceContext)
    async def sync_workspace_context(workspace_id: str, body: WorkspaceContext, request: Request):
        if body.workspace_id != workspace_id:
            raise HTTPException(400, "Workspace ID does not match")
        if body.active_workflow_id and _analysis_workflow_store(request).get(body.active_workflow_id, owner_id=_extract_user(request)) is None:
            raise HTTPException(404, "Analysis workflow not found")
        try:
            _analysis_workflow_store(request).sync_workspace(body, owner_id=_extract_user(request))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return body

    @router.get("/workspaces/{workspace_id}/workflows", response_model=list[AnalysisWorkflowSummary])
    async def list_workspace_workflows(workspace_id: str, request: Request):
        return _analysis_workflow_store(request).list_for_workspace(workspace_id, owner_id=_extract_user(request))

    @router.get("/workspaces/{workspace_id}/professional-reviews", response_model=list[ProfessionalReview])
    async def list_professional_reviews(workspace_id: str, request: Request):
        return _analysis_workflow_store(request).list_reviews(workspace_id, owner_id=_extract_user(request))

    @router.post("/professional-reviews/{review_id}/decision")
    async def decide_professional_review(review_id: str, body: ConfirmProfessionalReviewRequest, request: Request,
                                          idempotency_key: str | None = Header(None, alias="Idempotency-Key")):
        replay = await _idempotency_result(request, idempotency_key, f"/professional-reviews/{review_id}/decision", await _read_body_bytes(request))
        if replay is not None:
            return replay
        try:
            return await _perform_professional_review_decision(review_id, body, request)
        except Exception:
            _release_idempotency(request)
            raise

    async def _perform_professional_review_decision(review_id, body, request):
        owner_id = _extract_user(request)
        workflows = _analysis_workflow_store(request)
        review = workflows.get_review(review_id, owner_id=owner_id)
        if review is None:
            raise HTTPException(404, "确认卡片不存在")
        next_review = None
        created = None
        # Validate everything before consuming the durable confirmation.
        selected = None
        selected_item = None
        search = None
        tasks = body.task_ids or review.intent.task_ids or review.context.draft_task_ids
        mode = body.apsim_mode or review.intent.apsim_mode or review.context.apsim_mode
        if body.decision == "confirm":
            if review.phase == "search":
                search_values = review.search.model_dump(exclude={"aoi"})
                if body.search:
                    search_values.update(body.search.model_dump(mode="json", exclude_none=True, exclude_unset=True))
                search = ImagerySearchRequest(aoi=review.context.aoi, **search_values)
            elif review.phase == "workflow":
                selected = next((item for item in review.candidates if item.item_id == (body.imagery_item_id or review.selected_imagery_id)), None)
                if selected is None or not tasks or len(set(tasks)) != len(tasks):
                    raise HTTPException(400, "请选择卡片中的有效影像及不重复的分析任务")
            else:
                if body.scene is None:
                    raise HTTPException(400, "请提交完整的 LAI 参数范围配置")
                try:
                    await asyncio.to_thread(validate_lai_lut_ranges, body.scene.model_dump())
                except ValueError as exc:
                    raise HTTPException(400, str(exc)) from exc
                flow = workflows.get(review.workflow_id, owner_id=owner_id)
                if flow is None:
                    raise HTTPException(404, "工作流不存在")
                try:
                    selected_item = await asyncio.to_thread(_imagery_provider(request).get_item, flow.imagery_item_id)
                    _imagery_provider(request).validate_selection(flow.imagery_snapshot, selected_item, flow.aoi.geometry.model_dump(mode="json"))
                except ImagerySearchError as exc:
                    raise HTTPException(400, "影像信息已失效，请重新搜索和确认") from exc
        try:
            workflows.claim_review(review_id, body.context, owner_id=owner_id, parameters=body.model_dump(mode="json", exclude={"context"}), cancelling=body.decision == "cancel")
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        try:
            if body.decision == "cancel":
                review = workflows.finish_review(review_id, owner_id=owner_id, status="cancelled", detail="用户已取消本次操作")
                if review.phase == "lai":
                    workflows.update_status(review.workflow_id, owner_id=owner_id, status="cancelled", detail="用户取消了后续 LAI 分析，已完成步骤保留")
            elif review.phase == "search":
                try:
                    candidates = await asyncio.to_thread(_imagery_provider(request).search, search)
                except ImagerySearchError as exc:
                    raise HTTPException(502, "影像搜索暂不可用，请稍后重试") from exc
                workflows.check_workspace(body.context, owner_id=owner_id)
                from runtime.workspace_assistant import choose_automatic_imagery
                recommended = choose_automatic_imagery(candidates, search)
                if not candidates:
                    raise HTTPException(400, "未找到符合条件的影像，请修改搜索参数")
                candidates = [item.model_copy(update={"is_recommended": recommended is not None and item.item_id == recommended.item_id}) for item in candidates]
                next_review = create_review(workflows, owner_id=owner_id, context=body.context,
                    intent=review.intent.model_copy(update={"imagery_search": None}), run_id=review.source_run_id,
                    conversation_id=review.conversation_id, phase="workflow", candidates=candidates, search=search)
                review = workflows.finish_review(review_id, owner_id=owner_id, status="confirmed", next_review_id=next_review.review_id,
                                                  detail="已按确认的参数搜索，等待确认影像与任务")
            elif review.phase == "workflow":
                apsim_example = "yield" in tasks and mode == "example"
                created = await _create_verified_workflow(CreateAnalysisWorkflowRequest(
                    professional_mode=True, aoi=review.context.aoi, farm_id=review.context.farm_id,
                    imagery_item_id=selected.item_id, imagery_snapshot=selected, requested_task_ids=tasks,
                    workspace_id=body.context.workspace_id, workspace_revision=body.context.revision,
                    action_id=f"professional-{review_id}", run_id=review.source_run_id, conversation_id=review.conversation_id,
                    lai_query=review.intent.summary + "\n" + (_store(request).get_run(review.source_run_id).input_message if _store(request).get_run(review.source_run_id) else ""),
                    data_mode="demo" if review.intent.yield_demo_crop else "apsim_example" if apsim_example else "live",
                    demo_crop=review.intent.yield_demo_crop,
                ), request, workspace=body.context)
                review = workflows.finish_review(review_id, owner_id=owner_id, status="confirmed", workflow_id=created.workflow_id,
                                                  detail="已按确认的影像与任务启动工作流")
            else:
                scene = SceneParameters.model_validate({**review.proposed_scene, **body.scene.model_dump(), "source": "user_confirmed"}).model_dump(mode="json")
                scene.update(context=review.proposed_scene.get("context"), recommendation=review.proposed_scene, confirmation_review_id=review_id)
                workflows.update_step(review.workflow_id, "lai", owner_id=owner_id, status="planned", progress_percent=0,
                                      result={"scene_parameters": scene, "parameters_confirmed": True}, detail="参数已由用户确认，等待反演")
                flow = workflows.update_status(review.workflow_id, owner_id=owner_id, status="planned", detail="正在使用用户确认的参数继续执行")
                review = workflows.finish_review(review_id, owner_id=owner_id, status="confirmed", detail="已按确认的参数继续 LAI 反演")
                created = _launch_analysis_workflow(request, flow, selected_item, {"lai"})
        except Exception as exc:
            # Retryable preparation errors preserve the editor and its proposal.
            workflows.finish_review(review_id, owner_id=owner_id, status="pending", detail=exc.detail if isinstance(exc, HTTPException) else "操作未完成，请重试")
            raise
        result = {"review": review.model_dump(mode="json"), "next_review": next_review.model_dump(mode="json") if next_review else None,
                  "workflow": created.model_dump(mode="json") if created else None}
        _cache_idempotency(request, 200, result)
        return result

    @router.post("/analysis-workflows/{workflow_id}/start", status_code=202, response_model=AnalysisWorkflowSummary)
    async def start_analysis_workflow(workflow_id: str, request: Request) -> AnalysisWorkflowSummary:
        owner_id = _extract_user(request)
        workflow = _analysis_workflow_store(request).get(workflow_id, owner_id=owner_id)
        if workflow is None:
            raise HTTPException(status_code=404, detail="Analysis workflow not found")
        if workflow.status != "planned":
            raise HTTPException(status_code=409, detail="Only a planned workflow can be started")
        if workflow.data_mode == "demo":
            return _launch_analysis_workflow(request, workflow, {}, set())
        provider = _imagery_provider(request)
        try:
            selected_item = await asyncio.to_thread(provider.get_item, workflow.imagery_item_id)
            provider.validate_selection(workflow.imagery_snapshot, selected_item,
                                        workflow.aoi.geometry.model_dump(mode="json"))
        except ImagerySearchError:
            raise HTTPException(status_code=400, detail="Selected imagery must be searched again")
        return _launch_analysis_workflow(
            request, workflow, selected_item,
            set(workflow.effective_task_ids) & {"crop", "lai"},
        )

    @router.post("/analysis-workflows/{workflow_id}/retry", status_code=202, response_model=AnalysisWorkflowSummary)
    async def retry_analysis_workflow_step(
        workflow_id: str, body: RetryAnalysisWorkflowRequest, request: Request,
    ) -> AnalysisWorkflowSummary:
        owner_id = _extract_user(request)
        workflows = _analysis_workflow_store(request)
        workflow = workflows.get(workflow_id, owner_id=owner_id)
        if workflow is None:
            raise HTTPException(status_code=404, detail="Analysis workflow not found")
        if workflow.status == "running":
            raise HTTPException(status_code=409, detail="Workflow is already running")
        if workflow.professional_mode and any(review.workflow_id == workflow_id and review.status in {"pending", "processing"}
                                               for review in workflows.list_reviews(workflow.workspace_id, owner_id=owner_id)):
            raise HTTPException(409, "专业参数等待确认，请使用确认卡片继续或取消")
        target = next((step for step in workflow.steps if step.step_id == body.step_id), None)
        if target is None or target.status not in {"failed", "blocked"}:
            raise HTTPException(status_code=409, detail="Only a failed or blocked step can be retried")
        image = next(step for step in workflow.steps if step.step_id == "imagery")
        if body.step_id != "imagery" and image.status != "completed":
            raise HTTPException(status_code=409, detail="Retry imagery preparation before this step")
        if workflow.data_mode == "demo":
            workflows.update_step(workflow_id, body.step_id, owner_id=owner_id, status="planned", progress_percent=0, result={}, detail="等待重新演示")
            workflows.update_status(workflow_id, owner_id=owner_id, status="planned", detail="等待重新演示")
            return _launch_analysis_workflow(request, workflows.get(workflow_id, owner_id=owner_id), {}, set())
        provider = _imagery_provider(request)
        try:
            selected_item = await asyncio.to_thread(provider.get_item, workflow.imagery_item_id)
            provider.validate_selection(workflow.imagery_snapshot, selected_item,
                                        workflow.aoi.geometry.model_dump(mode="json"))
        except ImagerySearchError:
            raise HTTPException(status_code=400, detail="Selected imagery must be searched again")
        run_tasks = ({body.step_id} & {"crop", "lai"}) if body.step_id != "imagery" else set(workflow.effective_task_ids) & {"crop", "lai"}
        if body.step_id == "potential" and any(
            step.status != "completed" for step in workflow.steps if step.step_id in {"crop", "lai"}
        ):
            raise HTTPException(status_code=409, detail="Complete crop recognition and LAI before retrying canopy index")
        reset_steps = {body.step_id} if body.step_id != "imagery" else {"imagery", *run_tasks}
        for step_id in reset_steps:
            previous_step = next(step for step in workflow.steps if step.step_id == step_id)
            saved_scene = previous_step.result.get("scene_parameters") if step_id == "lai" else None
            workflows.update_step(workflow_id, step_id, owner_id=owner_id,
                                  status="planned", progress_percent=0, detail="等待重新执行",
                                  result={"scene_parameters": saved_scene} if saved_scene else {}, analysis_id=None)
        refreshed = workflows.get(workflow_id, owner_id=owner_id)
        assert refreshed is not None
        workflows.update_status(workflow_id, owner_id=owner_id, status="planned", detail="等待重新执行")
        return _launch_analysis_workflow(request, refreshed, selected_item, run_tasks)

    @router.get("/analysis-workflows/{workflow_id}", response_model=AnalysisWorkflowSummary)
    async def get_analysis_workflow(
        workflow_id: str, request: Request,
    ) -> AnalysisWorkflowSummary:
        owner_id = _extract_user(request)
        workflows = _analysis_workflow_store(request)
        item = workflows.get(workflow_id, owner_id=owner_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Analysis workflow not found")
        if item.status in {"completed", "blocked", "failed"} and (
            not item.report_uri or item.report_version != REPORT_VERSION or any(
                step.status == "completed" and (
                    step.step_id in {"crop", "growth", "potential", "yield_simple", "yield"} and
                    step.result.get("report_version") != REPORT_VERSION
                    or step.step_id == "lai" and
                    step.result.get("report_uri") and not step.result.get("report_data_uri")
                ) for step in item.steps
            )
        ):
            try:
                ensure_workflow_reports(
                    workflows, workflow_id, owner_id,
                    Path(getattr(request.app.state, "product_artifact_root", _PRODUCT_ARTIFACT_ROOT)).resolve(),
                    _artifact_store(request),
                )
                item = workflows.get(workflow_id, owner_id=owner_id) or item
            except Exception:
                logger.exception("analysis_workflow_report_backfill_failed | workflow_id=%s", workflow_id)
        return item

    @router.put("/analysis-workflows/{workflow_id}/yield-inputs", response_model=AnalysisWorkflowSummary)
    async def update_analysis_workflow_yield_inputs(
        workflow_id: str, body: UpdateYieldInputsRequest, request: Request,
    ) -> AnalysisWorkflowSummary:
        owner_id = _extract_user(request)
        workflows = _analysis_workflow_store(request)
        workflow = workflows.get(workflow_id, owner_id=owner_id)
        if workflow is None:
            raise HTTPException(status_code=404, detail="Analysis workflow not found")
        if not set(workflow.effective_task_ids) & {"yield", "yield_simple"}:
            raise HTTPException(status_code=409, detail="Workflow has no yield task")
        if workflow.status == "running":
            raise HTTPException(status_code=409, detail="Wait for the running workflow to finish")
        if "yield_simple" in workflow.effective_task_ids and "yield" not in workflow.effective_task_ids:
            from runtime.simple_yield_runner import resolve_simple_yield_crop
            from runtime.simple_yield import SimpleYieldError
            try:
                resolve_simple_yield_crop(workflow.model_copy(update={"yield_inputs": body.yield_inputs}))
            except SimpleYieldError as exc:
                raise HTTPException(409, str(exc)) from exc
            simple = next(step for step in workflow.steps if step.step_id == "yield_simple")
            if simple.status == "completed":
                if workflow.yield_inputs != body.yield_inputs:
                    raise HTTPException(409, "已完成估产的输入不可修改，请创建新的分析任务。")
                return workflow
        updated = workflows.update_yield_inputs(workflow_id, owner_id=owner_id, inputs=body.yield_inputs)
        simple_step = next((step for step in updated.steps if step.step_id == "yield_simple"), None)
        if simple_step and simple_step.status == "blocked" and "yield" not in updated.effective_task_ids:
            from runtime.simple_yield_runner import resolve_simple_yield_crop
            from runtime.simple_yield import SimpleYieldError
            try:
                resolve_simple_yield_crop(updated)
            except SimpleYieldError as exc:
                raise HTTPException(409, str(exc)) from exc
            provider = _imagery_provider(request)
            try:
                selected_item = await asyncio.to_thread(provider.get_item, updated.imagery_item_id)
                provider.validate_selection(updated.imagery_snapshot, selected_item, updated.aoi.geometry.model_dump(mode="json"))
            except ImagerySearchError:
                raise HTTPException(400, "Selected imagery must be searched again")
            workflows.update_step(workflow_id, "yield_simple", owner_id=owner_id,
                                  status="planned", progress_percent=0, detail="已确认作物，等待简化估产", result={})
            workflows.update_status(workflow_id, owner_id=owner_id, status="planned", detail="已确认作物，等待执行")
            return _launch_analysis_workflow(request, workflows.get(workflow_id, owner_id=owner_id), selected_item, set())
        if "yield" not in updated.effective_task_ids:
            return updated
        yield_step = next(step for step in updated.steps if step.step_id == "yield")
        if yield_step.status == "blocked":
            assessment = assess_yield_inputs(updated)
            if assessment.status == "ready":
                provider = _imagery_provider(request)
                try:
                    selected_item = await asyncio.to_thread(provider.get_item, updated.imagery_item_id)
                    provider.validate_selection(updated.imagery_snapshot, selected_item,
                                                updated.aoi.geometry.model_dump(mode="json"))
                except ImagerySearchError:
                    raise HTTPException(status_code=400, detail="Selected imagery must be searched again")
                workflows.update_step(workflow_id, "yield", owner_id=owner_id,
                                      status="planned", progress_percent=0, detail="APSIM 输入已核验，等待模拟", result={})
                refreshed = workflows.get(workflow_id, owner_id=owner_id)
                assert refreshed is not None
                workflows.update_status(workflow_id, owner_id=owner_id, status="planned", detail="APSIM 输入已核验")
                return _launch_analysis_workflow(request, refreshed, selected_item, set())
            updated = workflows.update_step(
                workflow_id, "yield", owner_id=owner_id, status="blocked",
                detail=f"产量估计尚有 {len(assessment.issues)} 项启动条件未满足",
                result={"input_assessment": assessment.model_dump(mode="json")},
            )
            try:
                ensure_workflow_reports(
                    workflows, workflow_id, owner_id,
                    Path(getattr(request.app.state, "product_artifact_root", _PRODUCT_ARTIFACT_ROOT)).resolve(),
                    _artifact_store(request), force_summary=True,
                )
                updated = workflows.get(workflow_id, owner_id=owner_id) or updated
            except Exception:
                logger.exception("analysis_workflow_report_refresh_failed | workflow_id=%s", workflow_id)
        return updated

    @router.get("/analysis-workflows/{workflow_id}/events", response_model=AnalysisWorkflowEventsResponse)
    async def list_analysis_workflow_events(
        workflow_id: str, request: Request,
    ) -> AnalysisWorkflowEventsResponse:
        items = _analysis_workflow_store(request).list_events(
            workflow_id, owner_id=_extract_user(request),
        )
        if items is None:
            raise HTTPException(status_code=404, detail="Analysis workflow not found")
        return AnalysisWorkflowEventsResponse(items=items)

    @router.post("/crop-analyses", status_code=202, response_model=CropAnalysisSummary)
    async def create_crop_analysis(body: CreateCropAnalysisRequest, request: Request) -> CropAnalysisSummary:
        try:
            verify_crop_model()
        except CropInferenceError as exc:
            return canonical_error_response(503, code=ErrorCode.INVALID_REFERENCE,
                                            message=str(exc), request_id=_req_id())
        if body.imagery_snapshot is None:
            return canonical_error_response(400, code=ErrorCode.INVALID_REFERENCE,
                                            message="A server-issued imagery_snapshot is required for crop recognition",
                                            request_id=_req_id())
        provider = _imagery_provider(request)
        try:
            item = await asyncio.to_thread(provider.get_item, body.imagery_item_id)
            snapshot = provider.validate_selection(
                body.imagery_snapshot, item, body.aoi.geometry.model_dump(mode="json")
            )
        except ImagerySearchError as exc:
            return canonical_error_response(400, code=ErrorCode.INVALID_REFERENCE,
                                            message="The selected imagery snapshot is invalid or unavailable",
                                            detail={"reason": str(exc)}, request_id=_req_id())
        body = body.model_copy(update={"imagery_snapshot": snapshot})
        analyses = _crop_analysis_store(request)
        analysis = analyses.create(body, owner_id=_extract_user(request))
        artifact_root = Path(getattr(request.app.state, "product_artifact_root", _PRODUCT_ARTIFACT_ROOT)).resolve()

        def worker() -> None:
            try:
                analyses.update(analysis.analysis_id, status="running", stage="imagery",
                                progress_percent=5, detail="正在读取所选 Sentinel 影像")

                def progress(detail: str, percent: int) -> None:
                    analyses.update(analysis.analysis_id,
                                    stage="inference" if percent >= 90 else "preparing" if percent >= 85 else "imagery",
                                    progress_percent=min(95, 5 + round(percent * 0.9)), detail=detail)

                result = run_crop_spatial_analysis(
                    item=item, geometry=body.aoi.geometry.model_dump(mode="json"),
                    output_dir=artifact_root / "crop" / analysis.analysis_id, progress_callback=progress,
                )
                result["imagery_provenance"] = {
                    "item_id": snapshot.item_id, "collection": snapshot.collection,
                    "acquired_at": snapshot.acquired_at, "cloud_cover": snapshot.cloud_cover,
                    "asset_fingerprint": snapshot.asset_fingerprint,
                }
                result.update(register_crop_report(
                    _artifact_store(request), run_id=analysis.analysis_id,
                    output_dir=artifact_root / "crop" / analysis.analysis_id,
                    imagery_item_id=body.imagery_item_id,
                    observed_at=snapshot.acquired_at,
                    area_hectares=body.aoi.area_hectares, result=result,
                ))
                analyses.update(analysis.analysis_id, status="completed", stage="completed",
                                progress_percent=100, detail="作物识别已完成", result=result,
                                completed_at=datetime.now(timezone.utc).isoformat())
            except (CropInferenceError, AoiBandReadError) as exc:
                logger.warning("crop_analysis_failed | analysis_id=%s | reason=%s", analysis.analysis_id, type(exc).__name__)
                analyses.update(analysis.analysis_id, status="failed", stage="failed",
                                detail=str(exc), result={"error": str(exc)},
                                completed_at=datetime.now(timezone.utc).isoformat())
            except Exception:
                logger.exception("crop_analysis_failed | analysis_id=%s", analysis.analysis_id)
                detail = "作物识别执行失败，请稍后重试或选择其他影像。"
                analyses.update(analysis.analysis_id, status="failed", stage="failed",
                                detail=detail, result={"error": detail},
                                completed_at=datetime.now(timezone.utc).isoformat())

        threading.Thread(target=worker, daemon=True, name=f"crop-{analysis.analysis_id[:8]}").start()
        return analysis

    @router.get("/crop-analyses/{analysis_id}", response_model=CropAnalysisSummary)
    async def get_crop_analysis(analysis_id: str, request: Request) -> CropAnalysisSummary:
        analysis = _crop_analysis_store(request).get(analysis_id)
        if analysis is None or (analysis.owner_id is not None and analysis.owner_id != _extract_user(request)):
            raise HTTPException(status_code=404, detail="Crop analysis not found")
        if analysis.status == "completed" and analysis.result.get("report_version") != REPORT_VERSION:
            try:
                report_refs = register_crop_report(
                    _artifact_store(request), run_id=analysis.analysis_id,
                    output_dir=Path(getattr(request.app.state, "product_artifact_root", _PRODUCT_ARTIFACT_ROOT)).resolve()
                    / "crop" / analysis.analysis_id,
                    imagery_item_id=analysis.imagery_item_id,
                    observed_at=analysis.imagery_snapshot.acquired_at if analysis.imagery_snapshot else "",
                    area_hectares=analysis.aoi.area_hectares,
                    result=analysis.result,
                )
                analysis = _crop_analysis_store(request).update(
                    analysis_id, result={**analysis.result, **report_refs},
                )
            except Exception:
                logger.exception("crop_report_backfill_failed | analysis_id=%s", analysis_id)
        return analysis

    @router.post("/lai-analyses", status_code=202, response_model=LaiAnalysisSummary)
    async def create_lai_analysis(body: CreateLaiAnalysisRequest, request: Request) -> LaiAnalysisSummary:
        analyses, artifacts = _lai_analysis_store(request), _artifact_store(request)
        imagery_provider = _imagery_provider(request)
        if body.imagery_snapshot is None:
            return canonical_error_response(
                400,
                code=ErrorCode.INVALID_REFERENCE,
                message="A server-issued imagery_snapshot is required for LAI analysis",
                request_id=_req_id(),
            )
        try:
            selected_item = await asyncio.to_thread(imagery_provider.get_item, body.imagery_item_id)
        except ImagerySearchError as exc:
            return canonical_error_response(
                502,
                code=ErrorCode.IMAGERY_SEARCH_FAILED,
                message="The selected Sentinel item cannot be verified",
                detail={"reason": str(exc)},
                request_id=_req_id(),
            )
        try:
            verified_snapshot = imagery_provider.validate_selection(
                body.imagery_snapshot,
                selected_item,
                body.aoi.geometry.model_dump(mode="json"),
            )
        except ImagerySearchError as exc:
            return canonical_error_response(
                400,
                code=ErrorCode.INVALID_REFERENCE,
                message="The selected imagery snapshot is invalid or no longer matches this AOI",
                detail={"reason": str(exc)},
                request_id=_req_id(),
            )
        body = body.model_copy(update={"imagery_snapshot": verified_snapshot})
        analysis = analyses.create(body)
        artifact_root = Path(
            getattr(request.app.state, "product_artifact_root", _PRODUCT_ARTIFACT_ROOT)
        ).resolve()
        last_progress_event: tuple[str, str, int | None] | None = None

        def event(
            kind: str,
            stage: str,
            detail: str,
            progress: int | None = None,
            data: dict | None = None,
            state_update: dict[str, object] | None = None,
        ) -> None:
            nonlocal last_progress_event
            marker = (stage, detail, progress)
            if kind == "progress" and marker == last_progress_event:
                return
            if kind == "progress":
                last_progress_event = marker
            timestamp = datetime.now(timezone.utc).isoformat()
            update_fields: dict[str, object] = {"stage": stage, "detail": detail, "updated_at": timestamp}
            if progress is not None:
                update_fields["progress_percent"] = progress
            if kind == "progress":
                update_fields["progress_data"] = data or {}
            update_fields.update(state_update or {})
            analyses.update_and_push_event(analysis.analysis_id, {
                "event_id": str(uuid4()),
                "analysis_id": analysis.analysis_id,
                "kind": kind,
                "stage": stage,
                "detail": detail,
                "progress_percent": progress,
                "data": data or {},
                "timestamp": timestamp,
            }, **update_fields)

        def user_error_detail(exc: Exception) -> str:
            if isinstance(exc, AoiBandReadError):
                return str(exc)
            if isinstance(exc, ImagerySearchError):
                if "no longer available" in str(exc).lower():
                    return "所选 Sentinel 影像已不可用，请重新搜索并选择其他影像。"
                return "无法获取所选 Sentinel 影像，请检查网络后重试。"
            message = str(exc).strip()
            return f"LAI 反演失败：{message}" if message else "LAI 反演失败，请更换影像后重试。"

        def worker() -> None:
            try:
                analyses.update(analysis.analysis_id, status="running", stage="imagery")
                event("progress", "imagery", "正在获取已选 Sentinel 影像元数据", 5)
                item = selected_item
                event("progress", "imagery", "影像元数据已就绪，正在解析波段资源", 8)
                work_dir = artifact_root / "lai" / analysis.analysis_id
                reflectance = read_prosail_reflectance_aoi(
                    item=item,
                    geometry=body.aoi.geometry.model_dump(mode="json"),
                    output_path=work_dir / "reflectance.tif",
                    target_resolution_m=body.parameters.target_resolution_m,
                    progress_callback=lambda detail, percent: event(
                        "progress",
                        "imagery",
                        detail,
                        8 + round(26 * percent / 100),
                    ),
                )
                event("progress", "inversion", "AOI 波段已就绪，正在执行 PROSAIL LAI 反演", 35)

                def inversion_progress(processed: int, total: int) -> None:
                    detail, progress_data = _lai_pixel_progress(processed, total)
                    event(
                        "progress",
                        "inversion",
                        detail,
                        35 + int(50 * processed / max(total, 1)),
                        progress_data,
                    )

                observation, report_artifacts = run_lai_html_report(
                    image_path=str(reflectance),
                    artifact_output_dir=str(work_dir),
                    progress_callback=inversion_progress,
                )
                if observation.status != "success":
                    raise RuntimeError(observation.summary)
                event("progress", "report", "正在注册分析报告", 90)
                payload = dict(observation.payload or {})
                for path_key in ("report_path", "lai_raster_path", "lai_preview_path"):
                    path_value = payload.get(path_key)
                    if not isinstance(path_value, str) or not Path(path_value).is_file():
                        raise RuntimeError(f"LAI 产物生成后未能通过文件校验: {path_key}")

                registered: list[str] = []
                report_artifact_id: str | None = None
                raster_artifact_id: str | None = None
                preview_artifact_id: str | None = None
                for artifact in report_artifacts:
                    artifact_id = artifacts.register(analysis.analysis_id, artifact)
                    registered.append(artifact_id)
                    if artifact.artifact_type == "lai_html_report":
                        report_artifact_id = artifact_id
                    elif artifact.artifact_type == "lai_raster":
                        raster_artifact_id = artifact_id
                    elif artifact.artifact_type == "lai_preview":
                        preview_artifact_id = artifact_id
                if report_artifact_id is None or raster_artifact_id is None or preview_artifact_id is None:
                    raise RuntimeError("LAI 分析产物生成后未能完整注册")

                reflectance_id = artifacts.register(analysis.analysis_id, SimpleNamespace(pack_name="sentinel", artifact_type="reflectance_tif", title="AOI Sentinel reflectance", uri=str(reflectance), content=None))
                payload = _lai_product_result(
                    payload,
                    report_artifact_id=report_artifact_id,
                    raster_artifact_id=raster_artifact_id,
                    preview_artifact_id=preview_artifact_id,
                )
                payload["imagery_provenance"] = {
                    "item_id": verified_snapshot.item_id,
                    "collection": verified_snapshot.collection,
                    "acquired_at": verified_snapshot.acquired_at,
                    "cloud_cover": verified_snapshot.cloud_cover,
                    "coverage_percent": verified_snapshot.coverage_percent,
                    "platform": verified_snapshot.platform,
                    "item_version": verified_snapshot.item_version,
                    "asset_fingerprint": verified_snapshot.asset_fingerprint,
                }
                event(
                    "result",
                    "completed",
                    "LAI 反演和报告已完成",
                    100,
                    {"artifact_ids": [reflectance_id, *registered], **payload},
                    state_update={
                        "status": "completed",
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "artifact_ids": [reflectance_id, *registered],
                        "result": payload,
                    },
                )
            except (ImagerySearchError, AoiBandReadError, RuntimeError) as exc:
                detail = user_error_detail(exc)
                logger.warning("lai_analysis_failed | analysis_id=%s | reason=%s", analysis.analysis_id, type(exc).__name__)
                event("error", "failed", detail, state_update={
                    "status": "failed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "result": {"error": detail},
                })
            except Exception as exc:
                logger.exception("lai_analysis_failed | analysis_id=%s", analysis.analysis_id)
                detail = "LAI 分析执行失败，请更换影像或稍后重试。"
                event("error", "failed", detail, state_update={
                    "status": "failed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "result": {"error": detail},
                })
            finally:
                analyses.close(analysis.analysis_id)
        threading.Thread(target=worker, daemon=True, name=f"lai-{analysis.analysis_id[:8]}").start()
        return analysis

    @router.get("/lai-analyses/{analysis_id}", response_model=LaiAnalysisSummary)
    async def get_lai_analysis(analysis_id: str, request: Request) -> LaiAnalysisSummary:
        analysis = _lai_analysis_store(request).get(analysis_id)
        if analysis is None:
            raise HTTPException(status_code=404, detail="LAI analysis not found")
        return analysis

    @router.get("/lai-analyses/{analysis_id}/events")
    async def stream_lai_analysis_events(
        analysis_id: str,
        request: Request,
        last_event_id: str | None = Header(None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        analyses = _lai_analysis_store(request)
        analyses.bind_loop(asyncio.get_running_loop())
        queue = analyses.subscribe(analysis_id)
        if queue is None:
            raise HTTPException(status_code=404, detail="LAI analysis not found")
        after_sequence = analyses.event_sequence(analysis_id, last_event_id)

        def encode_event(item: dict) -> str:
            return (
                f"id: {item['event_id']}\n"
                "event: analysis.event\n"
                f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
            )

        async def stream() -> AsyncIterator[str]:
            last_sequence = after_sequence
            try:
                yield "retry: 3000\n\n"
                for item in analyses.list_events(analysis_id, after_sequence=last_sequence):
                    last_sequence = int(item["sequence"])
                    yield encode_event(item)
                if analyses.is_terminal(analysis_id):
                    return
                while True:
                    try:
                        item = await asyncio.wait_for(queue.get(), timeout=15)
                    except asyncio.TimeoutError:
                        if await request.is_disconnected():
                            break
                        yield ": heartbeat\n\n"
                        continue
                    if item is None:
                        break
                    sequence = int(item.get("sequence", 0))
                    if sequence <= last_sequence:
                        continue
                    last_sequence = sequence
                    yield encode_event(item)
            finally:
                analyses.unsubscribe(analysis_id, queue)
        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    # ═══════════════════════════════════════════════════════════
    #  Datasets
    # ═══════════════════════════════════════════════════════════

    @router.post("/datasets", status_code=201, response_model=CanonicalDataset)
    async def create_dataset(
        body: CreateDatasetRequest,
        request: Request,
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    ) -> CanonicalDataset:
        """POST /api/product/v1/datasets."""
        ds_store: DatasetStore = _dataset_store(request)
        body_bytes = await _read_body_bytes(request)

        # Validate source kind
        if body.source.kind != "local_path":
            return canonical_error_response(
                400,
                code=ErrorCode.UNSUPPORTED_SOURCE_KIND,
                message=f"Only 'local_path' source kind is supported, got '{body.source.kind}'",
                request_id=_req_id(),
            )

        # Validate source file exists
        if not os.path.isfile(body.source.uri):
            return canonical_error_response(
                400,
                code=ErrorCode.DATASET_SOURCE_NOT_FOUND,
                message=f"Source file not found: {body.source.uri}",
                request_id=_req_id(),
            )

        # Idempotency
        idem_resp = await _idempotency_result(request, idempotency_key, "/datasets", body_bytes)
        if idem_resp is not None:
            return idem_resp

        dataset = ds_store.create_dataset(
            source=body.source,
            display_name=body.display_name,
            defaults=body.defaults,
            metadata=body.metadata,
            tags=body.tags,
            idempotency_key=None,
        )

        resp_body = dataset.model_dump(mode="json")
        _cache_idempotency(request, 201, resp_body)
        return dataset

    @router.get("/datasets", response_model=DatasetListResponse)
    async def list_datasets(
        request: Request,
        cursor: str | None = None,
        limit: int = 20,
    ) -> DatasetListResponse:
        """GET /api/product/v1/datasets."""
        ds_store: DatasetStore = _dataset_store(request)
        all_datasets = sorted(ds_store.list_datasets(), key=lambda d: d.created_at or "")
        offset = int(cursor) if cursor else 0
        page = all_datasets[offset : offset + limit]
        next_offset = offset + len(page)
        return DatasetListResponse(
            items=page,
            next_cursor=str(next_offset) if len(page) == limit and next_offset < len(all_datasets) else None,
            has_more=len(page) == limit and next_offset < len(all_datasets),
        )

    @router.get("/datasets/{dataset_id}", response_model=CanonicalDataset)
    async def get_dataset(
        dataset_id: str,
        request: Request,
    ) -> CanonicalDataset:
        """GET /api/product/v1/datasets/{dataset_id}."""
        ds_store: DatasetStore = _dataset_store(request)
        dataset = ds_store.get_dataset(dataset_id)
        if dataset is None:
            return canonical_error_response(
                404, code=ErrorCode.DATASET_NOT_FOUND,
                message=f"Dataset {dataset_id} not found", request_id=_req_id())
        return dataset

    @router.patch("/datasets/{dataset_id}", response_model=CanonicalDataset)
    async def update_dataset(
        dataset_id: str,
        body: UpdateDatasetRequest,
        request: Request,
    ) -> CanonicalDataset:
        """PATCH /api/product/v1/datasets/{dataset_id}."""
        ds_store: DatasetStore = _dataset_store(request)
        updated = ds_store.update_dataset(
            dataset_id,
            display_name=body.display_name,
            defaults=body.defaults,
            metadata=body.metadata,
            tags=body.tags,
        )
        if updated is None:
            return canonical_error_response(
                404, code=ErrorCode.DATASET_NOT_FOUND,
                message=f"Dataset {dataset_id} not found", request_id=_req_id())
        return updated

    @router.delete("/datasets/{dataset_id}", status_code=204)
    async def delete_dataset(
        dataset_id: str,
        request: Request,
    ) -> JSONResponse:
        """DELETE /api/product/v1/datasets/{dataset_id}."""
        ds_store: DatasetStore = _dataset_store(request)
        if not ds_store.delete_dataset(dataset_id):
            return canonical_error_response(
                404, code=ErrorCode.DATASET_NOT_FOUND,
                message=f"Dataset {dataset_id} not found", request_id=_req_id())
        return JSONResponse(status_code=204, content=None)

    # ═══════════════════════════════════════════════════════════
    #  Conversations
    # ═══════════════════════════════════════════════════════════

    @router.post("/conversations", status_code=201, response_model=CanonicalConversation)
    async def create_conversation(
        body: CreateConversationRequest,
        request: Request,
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    ) -> CanonicalConversation:
        """POST /api/product/v1/conversations."""
        store: RuntimeStore = _store(request)
        user_id = _extract_user(request)
        body_bytes = await _read_body_bytes(request)

        idem_resp = await _idempotency_result(request, idempotency_key, "/conversations", body_bytes)
        if idem_resp is not None:
            return idem_resp

        conversation_id = str(uuid4())
        session = store.create_session(
            session_id=conversation_id,
            title=body.title or "Untitled",
            created_by=user_id,
        )
        result = _session_to_conversation(session)
        _cache_idempotency(request, 201, result.model_dump(mode="json"))
        return result

    @router.get("/conversations", response_model=ConversationListResponse)
    async def list_conversations(
        request: Request,
        cursor: str | None = None,
        limit: int = 20,
    ) -> ConversationListResponse:
        """GET /api/product/v1/conversations."""
        store: RuntimeStore = _store(request)
        sessions = sorted(store.list_sessions(), key=lambda s: s.created_at or "")
        offset = int(cursor) if cursor else 0
        page = sessions[offset : offset + limit]
        items = [_session_to_conversation(s) for s in page]
        next_offset = offset + len(items)
        return ConversationListResponse(
            items=items,
            next_cursor=str(next_offset) if len(items) == limit and next_offset < len(sessions) else None,
            has_more=len(items) == limit and next_offset < len(sessions),
        )

    @router.get("/conversations/{conversation_id}", response_model=CanonicalConversation)
    async def get_conversation(
        conversation_id: str,
        request: Request,
    ) -> CanonicalConversation:
        """GET /api/product/v1/conversations/{conversation_id}."""
        store: RuntimeStore = _store(request)
        session = store.get_session(conversation_id)
        if session is None:
            return canonical_error_response(
                404, code=ErrorCode.CONVERSATION_NOT_FOUND,
                message=f"Conversation {conversation_id} not found", request_id=_req_id())
        return _session_to_conversation(session)

    @router.patch("/conversations/{conversation_id}", response_model=CanonicalConversation)
    async def update_conversation(
        conversation_id: str,
        body: UpdateConversationRequest,
        request: Request,
    ) -> CanonicalConversation:
        """PATCH /api/product/v1/conversations/{conversation_id}."""
        store: RuntimeStore = _store(request)
        session = store.get_session(conversation_id)
        if session is None:
            return canonical_error_response(
                404, code=ErrorCode.CONVERSATION_NOT_FOUND,
                message=f"Conversation {conversation_id} not found", request_id=_req_id())
        if body.title is not None:
            updated = session.model_copy(update={"title": body.title})
            store.save_session(updated)
            return _session_to_conversation(updated)
        return _session_to_conversation(session)

    @router.delete("/conversations/{conversation_id}", status_code=204)
    async def delete_conversation(
        conversation_id: str,
        request: Request,
    ) -> JSONResponse:
        """DELETE /api/product/v1/conversations/{conversation_id}."""
        store: RuntimeStore = _store(request)
        session = store.get_session(conversation_id)
        if session is None:
            return canonical_error_response(
                404, code=ErrorCode.CONVERSATION_NOT_FOUND,
                message=f"Conversation {conversation_id} not found", request_id=_req_id())
        store.delete_session(conversation_id)
        return JSONResponse(status_code=204, content=None)

    @router.get("/conversations/{conversation_id}/runs", response_model=PaginatedRunsResponse)
    async def list_conversation_runs(
        conversation_id: str,
        request: Request,
        cursor: str | None = None,
        limit: int = 20,
    ) -> PaginatedRunsResponse:
        """GET /api/product/v1/conversations/{conversation_id}/runs."""
        store: RuntimeStore = _store(request)
        art_store: ArtifactStore = _artifact_store(request)
        session = store.get_session(conversation_id)
        if session is None:
            return canonical_error_response(
                404, code=ErrorCode.CONVERSATION_NOT_FOUND,
                message=f"Conversation {conversation_id} not found", request_id=_req_id())
        runs = store.list_runs_for_session(conversation_id)
        if any(run.product_parts for run in runs) and session.created_by != _extract_user(request):
            raise HTTPException(404, "Conversation not found")
        offset = int(cursor) if cursor else 0
        page = runs[offset : offset + limit]
        items = [_run_to_canonical(r, art_store) for r in page]
        next_offset = offset + len(items)
        return PaginatedRunsResponse(
            items=items,
            next_cursor=str(next_offset) if len(items) == limit and next_offset < len(runs) else None,
            has_more=len(items) == limit and next_offset < len(runs),
        )

    # ═══════════════════════════════════════════════════════════
    #  Submissions
    # ═══════════════════════════════════════════════════════════

    async def _run_workspace_submission(request, body, conversation_id, submission_id, cancellation_event):
        context = body.context.workspace
        owner_id = _extract_user(request)
        workflows = _analysis_workflow_store(request)
        store = _store(request)
        subs = _submission_store(request)
        run_id = str(uuid4())
        run_context = RequestContextV2(entrypoint="api", extra_params={
            "workspace": context.model_dump(mode="json"),
            "workspace_ui": body.context.workspace_ui.model_dump(mode="json") if body.context.workspace_ui else None,
        })
        run = RunDetail(run_id=run_id, session_id=conversation_id, status="running",
                        input_message=body.input.message, input_context=run_context, output_message="",
                        product_created_at=datetime.now(timezone.utc).isoformat())
        store.save_run(run)
        subs.update_submission(submission_id, run_id=run_id)
        store.append_message(conversation_id, SessionMessage(role="user", content=body.input.message))
        _emit_event(subs, submission_id, "run.progress", run_id=run_id, stage="processing", detail="正在核对当前选区、影像和任务配置")
        active = workflows.get(context.active_workflow_id, owner_id=owner_id) if context.active_workflow_id else None
        try:
            if body.input.workspace_action:
                action = body.input.workspace_action
                if action.source_run_id:
                    source = store.get_run(action.source_run_id)
                    if source is None or source.session_id != conversation_id or not source.input_context:
                        raise HTTPException(404, "任务草案不存在")
                    original = WorkspaceContext.model_validate(source.input_context.extra_params.get("workspace"))
                    fields = {"workspace_id", "execution_mode", "farm_id", "aoi", "imagery_item_id", "imagery_snapshot", "apsim_mode"}
                    if original.model_dump(include=fields) != context.model_dump(include=fields):
                        raise HTTPException(409, "选区或影像已变化，请在当前分析卡片重新启动。")
                    if not any(p.get("type") == "action_card" and p.get("data", {}).get("action_id") == action.action_id for p in source.product_parts):
                        raise HTTPException(400, "无效的任务卡片动作")
                elif len(action.task_ids) != len(set(action.task_ids)) or set(action.task_ids) != set(context.draft_task_ids):
                    # The active card confirms the synchronized draft directly;
                    # historical card actions still validate their source Run.
                    raise HTTPException(409, "任务选择已变化，请确认当前分析卡片后重试。")
                intent = WorkspaceIntent(intent="execute", explicit_execution=True,
                    yield_demo_crop=action.yield_demo_crop,
                    task_ids=body.input.workspace_action.task_ids, summary="正在核验任务输入。",
                    rationale="按你在任务卡片中选择的任务执行。")
                action_id = body.input.workspace_action.action_id
            else:
                intent = await asyncio.to_thread(plan_workspace, _engine(request).llm_provider,
                    body.input.message, context, store.get_session(conversation_id).messages[:-1], active,
                    body.context.workspace_ui,
                    [previous for previous in store.list_runs_for_session(conversation_id) if previous.run_id != run_id and previous.status == "completed"])
                action_id = submission_id
            if cancellation_event.is_set():
                store.save_run(run.model_copy(update={"status": "cancelled", "output_message": "已停止本次问答。专业任务状态请查看任务卡片。"}))
                return
            try:
                workflows.check_workspace(context, owner_id=owner_id)
            except ValueError:
                latest = workflows.get_workspace(context.workspace_id, owner_id=owner_id)
                # Only read-only planning may follow a selection made while the
                # model was answering. Execution always requires its original snapshot.
                if latest is None or intent.intent == "execute" or not can_rebase_preview(context, latest):
                    raise
                context = latest
                active = workflows.get(context.active_workflow_id, owner_id=owner_id) if context.active_workflow_id else None
                run_context = run_context.model_copy(update={"extra_params": {**run_context.extra_params, "workspace": context.model_dump(mode="json")}})
                run = run.model_copy(update={"input_context": run_context})
                if intent.intent == "advise" and context.imagery_item_id:
                    intent = intent.model_copy(update={"summary": "已读取最新选片状态，可在当前任务卡片继续选择分析任务。"})
            # Keep authorization bound to the submitted snapshot. Automatic
            # selection is a derived input, never a client workspace mutation.
            authorized_context = context
            automatic = context.auto_execute and intent.intent == "execute" and not body.input.workspace_action
            selection_note = ""
            if automatic:
                intent = intent.model_copy(update={"explicit_execution": True})
            if (automatic and context.execution_mode == "live" and context.aoi is not None
                    and (intent.task_ids or context.draft_task_ids) and not intent.unsupported_parameters
                    and not (active and active.status in {"planned", "running"})
                    and (not context.imagery_item_id or context.imagery_snapshot is None or intent.imagery_search is not None)):
                search = automatic_imagery_request(context, intent)
                _emit_event(subs, submission_id, "run.progress", run_id=run_id, stage="processing",
                            detail=f"自动执行：正在搜索 {search.start_date} 至 {search.end_date} 的影像")
                try:
                    candidates = await asyncio.to_thread(_imagery_provider(request).search, search)
                except ImagerySearchError as exc:
                    raise HTTPException(502, "自动搜索影像暂不可用，本次任务未启动，请稍后重试。") from exc
                workflows.check_workspace(authorized_context, owner_id=owner_id)
                if cancellation_event.is_set():
                    store.save_run(run.model_copy(update={"status": "cancelled", "output_message": "已停止自动执行，任务未启动。"}))
                    return
                selected = choose_automatic_imagery(candidates, search)
                if selected is None:
                    raise HTTPException(400, "未找到符合日期、云量和区域覆盖要求的影像，本次任务未启动。请调整搜索条件后重试。")
                context = context.model_copy(update={"imagery_item_id": selected.item_id, "imagery_snapshot": selected})
                selection_note = f"已自动选择 {selected.acquired_at[:10]} 的影像（云量 {selected.cloud_cover:g}%），在指定日期范围内优先低云量，同等云量优先较新影像。"
                run = run.model_copy(update={"input_context": run_context.model_copy(update={"extra_params": {
                    **run_context.extra_params, "effective_workspace": context.model_dump(mode="json"),
                    "automatic_imagery_search": search.model_dump(mode="json"),
                }})})
                _emit_event(subs, submission_id, "run.progress", run_id=run_id, stage="processing", detail=selection_note)
            summary, parts = workspace_parts(intent, context, action_id, active)
            if (context.professional_mode and context.execution_mode == "live" and intent.intent == "execute"
                    and context.aoi is not None and (intent.task_ids or context.draft_task_ids)
                    and not intent.unsupported_parameters and not (active and active.status in {"planned", "running"})):
                review = create_review(workflows, owner_id=owner_id, context=context, intent=intent,
                                       run_id=run_id, conversation_id=conversation_id)
                parts.append(review_part(review))
                parts[2]["data"]["can_execute"] = False
                summary = "已生成推荐配置。请在确认卡片中编辑参数，点击“确认并执行”后继续。"
                intent = intent.model_copy(update={"explicit_execution": False})
            if selection_note:
                parts[0]["data"]["rationale"] = selection_note + parts[0]["data"]["rationale"]
                for parameter in parts[1]["data"]["parameters"]:
                    if parameter["name"] == "影像":
                        parameter["source"] = "automatic"
            plan = parts[0]["data"] if parts else {}
            for part in parts:
                _emit_event(subs, submission_id, "assistant.part.updated", run_id=run_id, stage="processing", data={"part": part})
            if intent.intent == "execute" and intent.explicit_execution and plan["requested_task_ids"] and not plan["missing_inputs"]:
                if context.execution_mode == "live":
                    if cancellation_event.is_set():
                        store.save_run(run.model_copy(update={"status": "cancelled", "output_message": "已停止本次问答。"}))
                        return
                    created = await _create_verified_workflow(CreateAnalysisWorkflowRequest(
                        aoi=context.aoi, imagery_item_id=context.imagery_item_id, imagery_snapshot=context.imagery_snapshot,
                        farm_id=context.farm_id, requested_task_ids=plan["requested_task_ids"],
                        action_id=action_id, workspace_id=context.workspace_id, workspace_revision=context.revision,
                        conversation_id=conversation_id, run_id=run_id,
                        lai_query=workspace_lai_query(
                            body.input.message, context,
                            [previous for previous in store.list_runs_for_session(conversation_id) if previous.run_id != run_id],
                        ),
                        data_mode=plan["data_mode"], demo_crop=intent.yield_demo_crop,
                    ), request, workspace=authorized_context, cancellation_event=cancellation_event)
                    parts[1]["data"]["state"] = "effective"
                    reference = {"type": "workflow_reference", "part_id": f"{action_id}:workflow", "data": {
                        "workflow_id": created.workflow_id, "plan_id": action_id, "execution_mode": "live",
                        "workspace_id": context.workspace_id, "revision": context.revision, "status": created.status,
                        "data_mode": created.data_mode, "demo_crop": created.demo_crop,
                        "auto_execute": automatic,
                    }}
                    parts.append(reference)
                    parts[2]["data"]["can_execute"] = False
                    parts[2]["data"]["executed"] = True
                    summary = "已启动" + "、".join(TASK_LABELS[t] for t in created.requested_task_ids) + "。左侧分析面板可查看进度和结果。"
                    if automatic:
                        summary = selection_note + "已自动启动" + "、".join(TASK_LABELS[t] for t in created.requested_task_ids) + "，完成后会在此提醒你。"
                    if created.data_mode == "demo":
                        summary = "已启动" + ("小麦" if created.demo_crop == "wheat" else "玉米") + "估产模拟演示。左侧可查看进度、示例结果及 APSIM 模板报告；数值不代表实际产量。"
                    _emit_event(subs, submission_id, "workflow.linked", run_id=run_id, stage="processing", data={"part": reference})
                else:
                    parts[2]["data"]["demo_started"] = True
                    parts[2]["data"]["can_execute"] = False
                    summary = "已准备 LAI 演示流程，下方进度和配置均为演示数据。"
                    _emit_event(subs, submission_id, "action.updated", run_id=run_id, stage="processing", data={"part": parts[2]})
            run = run.model_copy(update={"status": "completed", "output_message": summary, "product_parts": parts})
            store.save_run(run)
            store.append_message(conversation_id, SessionMessage(role="assistant", content=summary))
            session = store.get_session(conversation_id)
            session.latest_run_id = run_id
            store.save_session(session)
            for part in parts:
                _emit_event(subs, submission_id, "assistant.part.updated", run_id=run_id, stage="finalizing", data={"part": part})
            completed = subs.update_submission(submission_id, status="completed", stage="completed", completed_at=datetime.now(timezone.utc).isoformat())
            if completed.status == "completed":
                _emit_event(subs, submission_id, "run.completed", run_id=run_id, stage="completed", data={"assistant_part_text": summary})
        except Exception as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            run = run.model_copy(update={"status": "failed", "output_message": detail,
                "product_parts": [{"type": "error", "text": detail}]})
            store.save_run(run)
            raise

    @router.post("/conversations/{conversation_id}/submissions", status_code=201, response_model=SubmissionResponse)
    async def create_submission(
        conversation_id: str,
        body: CreateSubmissionRequest,
        request: Request,
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    ) -> SubmissionResponse:
        """POST /api/product/v1/conversations/{conversation_id}/submissions."""
        store: RuntimeStore = _store(request)
        engine: BoundedRuntimeEngine = _engine(request)
        sub_store: SubmissionStore = _submission_store(request)
        sub_store.bind_loop(asyncio.get_running_loop())
        ds_store: DatasetStore = _dataset_store(request)
        art_store: ArtifactStore = _artifact_store(request)
        user_id = _extract_user(request)
        body_bytes = await _read_body_bytes(request)

        # Validate conversation exists
        session = store.get_session(conversation_id)
        if session is None:
            return canonical_error_response(
                404, code=ErrorCode.CONVERSATION_NOT_FOUND,
                message=f"Conversation {conversation_id} not found", request_id=_req_id())

        if body.context and body.context.workspace:
            if session.created_by != user_id:
                raise HTTPException(404, "Conversation not found")
            context = body.context.workspace
            if context.active_workflow_id and _analysis_workflow_store(request).get(context.active_workflow_id, owner_id=user_id) is None:
                raise HTTPException(404, "Analysis workflow not found")
            try:
                _analysis_workflow_store(request).check_workspace(context, owner_id=user_id)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
        elif body.input.workspace_action:
            raise HTTPException(400, "A workspace action requires the current workspace context")
        elif body.context and body.context.workspace_ui:
            raise HTTPException(400, "Workspace card context requires the current workspace snapshot")

        # Validate delivery mode
        mode = body.mode
        delivery = mode.delivery if mode else "async"
        if delivery != "async":
            return canonical_error_response(
                400, code=ErrorCode.UNSUPPORTED_DELIVERY_MODE,
                message=f"Only 'async' delivery mode is supported, got '{delivery}'",
                request_id=_req_id())

        interaction = mode.interaction if mode else "chat"

        # Extract message and refs
        user_message = body.input.message
        refs = body.input.refs

        # Resolve dataset references into explicit Runtime context.  The user
        # message remains verbatim: local paths must never be smuggled through
        # natural-language text.
        resolved_datasets: list[ResolvedDatasetV2] = []
        for ref in refs:
            if ref.type == "dataset":
                ds = ds_store.get_dataset(ref.id)
                if ds is None:
                    return canonical_error_response(
                        404, code=ErrorCode.DATASET_NOT_FOUND,
                        message=f"Referenced dataset {ref.id} not found",
                        request_id=_req_id())
                defaults = ds.defaults
                resolved_datasets.append(ResolvedDatasetV2(
                    dataset_id=ds.dataset_id,
                    display_name=ds.display_name,
                    local_path=ds.source.uri,
                    region=defaults.region,
                    crop_type=defaults.crop_type,
                    task_type=defaults.task_type,
                    content_type=ds.metadata.get("content_type") if isinstance(ds.metadata.get("content_type"), str) else None,
                ))

        # Build RequestContextV2 with context inheritance
        request_context = _inherit_context(store, conversation_id, body.context)
        effective_datasets = resolved_datasets or request_context.datasets
        primary_dataset = effective_datasets[0] if effective_datasets else None
        request_context = request_context.model_copy(update={
            "conversation_mode": "task" if interaction == "task" else "chat",
            "region": request_context.region or (primary_dataset.region if primary_dataset else None),
            "crop_type": request_context.crop_type or (primary_dataset.crop_type if primary_dataset else None),
            "task_type": request_context.task_type or (primary_dataset.task_type if primary_dataset else None),
            "datasets": effective_datasets,
            "extra_params": {
                "submission_id": "",
                "refs": [ref.model_dump(mode="json") for ref in refs],
                "preferences": body.preferences.model_dump(mode="json", exclude_none=True) if body.preferences else {},
                "client": body.client.model_dump(mode="json", exclude_none=True) if body.client else {},
            },
        })

        # Claim idempotency only after validation, immediately before the mutation.
        idem_resp = await _idempotency_result(
            request,
            idempotency_key,
            f"/conversations/{conversation_id}/submissions",
            body_bytes,
        )
        if idem_resp is not None:
            return idem_resp

        # Create submission in "queued" state
        now = datetime.now(timezone.utc).isoformat()
        submission = sub_store.create_submission(conversation_id=conversation_id)
        submission_id = submission.submission_id
        sub_store.update_submission(submission_id, status="queued", stage="accepted")

        _emit_event(sub_store, submission_id, "submission.accepted", stage="accepted")
        cancellation_event = sub_store.get_cancellation_event(submission_id)

        # Launch worker thread
        def worker() -> None:
            try:
                if sub_store.is_cancel_requested(submission_id):
                    return
                # queued → running
                running_submission = sub_store.update_submission(
                    submission_id, status="running", stage="processing"
                )
                if running_submission is None or running_submission.status != "running":
                    return
                _emit_event(sub_store, submission_id, "run.started", stage="processing")

                if body.context and body.context.workspace:
                    asyncio.run(_run_workspace_submission(request, body, conversation_id, submission_id, cancellation_event))
                    return

                for internal_event in engine.stream(
                    session_id=conversation_id,
                    user_message=user_message,
                    user_id=user_id,
                    request_context=request_context,
                    cancellation_event=cancellation_event,
                    granted_permissions=_CANONICAL_ALGORITHM_PERMISSIONS,
                ):
                    if sub_store.is_cancel_requested(submission_id):
                        break
                    ss_event = _map_internal_event_to_ss_event(internal_event, submission_id)
                    if ss_event is not None:
                        sub_store.push_event(submission_id, ss_event)
                    if internal_event.run_id:
                        sub_store.update_submission(submission_id, run_id=internal_event.run_id)

                    # Transition to finalizing before completion
                    if internal_event.event in ("run.completed", "run.failed"):
                        sub_store.update_submission(submission_id, stage="finalizing")
                        _emit_event(sub_store, submission_id, "run.progress", stage="finalizing",
                                     detail="Finalizing results", run_id=internal_event.run_id)

                    if internal_event.event == "run.completed":
                        completed_submission = sub_store.update_submission(
                            submission_id,
                            status="completed",
                            stage="completed",
                            completed_at=datetime.now(timezone.utc).isoformat(),
                        )
                        if completed_submission is None or completed_submission.status != "completed":
                            break
                        # Register artifacts only after the completed terminal state wins the race.
                        run = internal_event.run or store.get_run(internal_event.run_id)
                        if run is not None and run.artifacts:
                            for artifact in run.artifacts:
                                art_store.register(run_id=internal_event.run_id, artifact=artifact)
                        _emit_event(sub_store, submission_id, "run.completed", stage="completed",
                                     run_id=internal_event.run_id)
                    elif internal_event.event == "run.failed":
                        failed_submission = sub_store.update_submission(
                            submission_id,
                            status="failed",
                            stage="failed",
                            completed_at=datetime.now(timezone.utc).isoformat(),
                        )
                        if failed_submission is None or failed_submission.status != "failed":
                            break
                        _emit_event(sub_store, submission_id, "run.failed", stage="failed",
                                     run_id=internal_event.run_id)
            except Exception as exc:
                if not sub_store.is_cancel_requested(submission_id):
                    logger.exception("submission_worker_failed | submission_id=%s", submission_id)
                    failed_submission = sub_store.update_submission(
                        submission_id,
                        status="failed",
                        stage="failed",
                        completed_at=datetime.now(timezone.utc).isoformat(),
                    )
                    if failed_submission is not None and failed_submission.status == "failed":
                        _emit_event(sub_store, submission_id, "run.failed", stage="failed", detail=str(exc))
            finally:
                sub_store.close_submission(submission_id)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        result = SubmissionResponse(
            submission_id=submission_id,
            conversation_id=conversation_id,
            run_id=None,
            status="queued",
            stage="accepted",
            created_at=now,
            completed_at=None,
        )
        _cache_idempotency(request, 201, result.model_dump(mode="json"))
        return result

    @router.get("/submissions/{submission_id}", response_model=SubmissionResponse)
    async def get_submission(
        submission_id: str,
        request: Request,
    ) -> SubmissionResponse:
        """GET /api/product/v1/submissions/{submission_id}."""
        sub_store: SubmissionStore = _submission_store(request)
        submission = sub_store.get_submission(submission_id)
        if submission is None:
            return canonical_error_response(
                404, code=ErrorCode.SUBMISSION_NOT_FOUND,
                message=f"Submission {submission_id} not found", request_id=_req_id())
        return submission

    @router.get("/submissions/{submission_id}/events")
    async def stream_submission_events(
        submission_id: str,
        request: Request,
        last_event_id: str | None = Header(None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        """GET /api/product/v1/submissions/{submission_id}/events — SSE stream.

        Supports reconnection via ``Last-Event-ID`` header.  When provided, the
        server emits a ``submission.updated`` snapshot before continuing.
        """
        sub_store: SubmissionStore = _submission_store(request)
        submission = sub_store.get_submission(submission_id)
        if submission is None:
            return canonical_error_response(
                404, code=ErrorCode.SUBMISSION_NOT_FOUND,
                message=f"Submission {submission_id} not found", request_id=_req_id())

        queue = sub_store.subscribe(submission_id)
        if queue is None:
            return canonical_error_response(
                500, code=ErrorCode.INTERNAL_ERROR,
                message="Event queue not available", request_id=_req_id())

        last_seq = 0
        if last_event_id and last_event_id.startswith("evt_"):
            try:
                last_seq = int(last_event_id.split("_")[1])
            except (ValueError, IndexError):
                pass

        async def event_generator() -> AsyncIterator[str]:
            seq = last_seq
            try:
                # Persisted events make reconnects exact rather than a synthetic snapshot.
                for event_data in sub_store.list_events(submission_id, after_sequence=seq):
                    seq = event_data["sequence"]
                    yield _encode_submission_sse_event(event_data)

                if sub_store.is_terminal(submission_id):
                    return

                while True:
                    try:
                        event_data = await asyncio.wait_for(queue.get(), timeout=15.0)
                    except asyncio.TimeoutError:
                        yield ": heartbeat\n\n"
                        continue

                    if event_data is None:
                        break
                    if event_data["sequence"] <= seq:
                        continue
                    seq = event_data["sequence"]
                    yield _encode_submission_sse_event(event_data)
            finally:
                sub_store.unsubscribe(submission_id, queue)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.post("/submissions/{submission_id}/cancel", response_model=SubmissionResponse)
    async def cancel_submission(
        submission_id: str,
        request: Request,
        idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    ) -> SubmissionResponse:
        """POST /api/product/v1/submissions/{submission_id}/cancel."""
        sub_store: SubmissionStore = _submission_store(request)
        body_bytes = await _read_body_bytes(request)

        submission = sub_store.get_submission(submission_id)
        if submission is None:
            return canonical_error_response(
                404, code=ErrorCode.SUBMISSION_NOT_FOUND,
                message=f"Submission {submission_id} not found", request_id=_req_id())

        idem_resp = await _idempotency_result(
            request,
            idempotency_key,
            f"/submissions/{submission_id}/cancel",
            body_bytes,
        )
        if idem_resp is not None:
            return idem_resp

        if submission.status in ("completed", "failed", "cancelled"):
            _release_idempotency(request)
            return canonical_error_response(
                409, code=ErrorCode.ALREADY_TERMINAL,
                message=f"Submission {submission_id} is already in terminal state: {submission.status}",
                request_id=_req_id())
        if submission.status == "cancelling":
            _release_idempotency(request)
            return canonical_error_response(
                409, code=ErrorCode.ALREADY_TERMINAL,
                message="Cancellation already in progress", request_id=_req_id())

        accepted = sub_store.cancel_submission(submission_id)
        if not accepted:
            _release_idempotency(request)
            return canonical_error_response(
                409, code=ErrorCode.CANCELLATION_NOT_SUPPORTED,
                message="Cancellation not supported for this submission", request_id=_req_id())

        _emit_event(sub_store, submission_id, "submission.cancelled", stage="cancelled", detail="Cancelled by user")
        sub_store.update_submission(submission_id, status="cancelled", stage="cancelled",
                                    completed_at=datetime.now(timezone.utc).isoformat())
        sub_store.close_submission(submission_id)

        updated = sub_store.get_submission(submission_id)
        result = updated if updated else submission
        _cache_idempotency(request, 200, result.model_dump(mode="json"))
        return result

    # ═══════════════════════════════════════════════════════════
    #  Runs
    # ═══════════════════════════════════════════════════════════

    @router.get("/runs/{run_id}", response_model=CanonicalRunResponse)
    async def get_run(
        run_id: str,
        request: Request,
    ) -> CanonicalRunResponse:
        """GET /api/product/v1/runs/{run_id}."""
        store: RuntimeStore = _store(request)
        art_store: ArtifactStore = _artifact_store(request)
        run = store.get_run(run_id)
        if run is None:
            return canonical_error_response(
                404, code=ErrorCode.RUN_NOT_FOUND,
                message=f"Run {run_id} not found", request_id=_req_id())
        if run.product_parts and store.get_session(run.session_id).created_by != _extract_user(request):
            raise HTTPException(404, "Run not found")
        return _run_to_canonical(run, art_store)

    @router.get("/runs", response_model=PaginatedRunsResponse)
    async def list_runs(
        request: Request,
        cursor: str | None = None,
        limit: int = 20,
    ) -> PaginatedRunsResponse:
        """GET /api/product/v1/runs."""
        store: RuntimeStore = _store(request)
        art_store: ArtifactStore = _artifact_store(request)
        runs = store.list_runs()
        offset = int(cursor) if cursor else 0
        page = runs[offset : offset + limit]
        items = [_run_to_canonical(r, art_store) for r in page]
        next_offset = offset + len(items)
        return PaginatedRunsResponse(
            items=items,
            next_cursor=str(next_offset) if len(items) == limit and next_offset < len(runs) else None,
            has_more=len(items) == limit and next_offset < len(runs),
        )

    # ═══════════════════════════════════════════════════════════
    #  Artifacts
    # ═══════════════════════════════════════════════════════════

    @router.delete("/management/artifacts/{artifact_id}", status_code=204)
    async def delete_artifact_registration(artifact_id: str, request: Request) -> Response:
        """Delete an artifact registration through the explicit management surface.

        This endpoint deliberately retains the underlying file.  Archival and
        physical deletion need an operator-owned retention workflow rather than
        normal request or SSE cleanup.
        """
        if not artifact_id.startswith("art_"):
            return canonical_error_response(
                404, code=ErrorCode.ARTIFACT_NOT_FOUND,
                message=f"Artifact {artifact_id} not found", request_id=_req_id())
        if not _artifact_store(request).delete_registration(artifact_id):
            return canonical_error_response(
                404, code=ErrorCode.ARTIFACT_NOT_FOUND,
                message=f"Artifact {artifact_id} not found", request_id=_req_id())
        return Response(status_code=204)

    @router.get("/artifacts/{artifact_id}", response_model=CanonicalArtifact)
    async def get_artifact(
        artifact_id: str,
        request: Request,
    ) -> CanonicalArtifact:
        """GET /api/product/v1/artifacts/{artifact_id}."""
        art_store: ArtifactStore = _artifact_store(request)

        # Stable UUID lookup (new path)
        if artifact_id.startswith("art_"):
            record = art_store.get(artifact_id)
            if record is not None:
                _check_map_report_owner(record, request)
                return _record_to_canonical(record)
            return canonical_error_response(
                404, code=ErrorCode.ARTIFACT_NOT_FOUND,
                message=f"Artifact {artifact_id} not found", request_id=_req_id())

        # Backward-compatible legacy index-based lookup
        store: RuntimeStore = _store(request)
        parts = artifact_id.rsplit(":", 2)
        if len(parts) < 2:
            return canonical_error_response(
                404, code=ErrorCode.ARTIFACT_NOT_FOUND,
                message=f"Artifact {artifact_id} not found", request_id=_req_id())

        for run in store.list_runs():
            for i, artifact in enumerate(run.artifacts):
                if f"{artifact.pack_name}:{artifact.artifact_type}:{i}" == artifact_id:
                    return _artifact_to_canonical(artifact, artifact_index=i)

        return canonical_error_response(
            404, code=ErrorCode.ARTIFACT_NOT_FOUND,
            message=f"Artifact {artifact_id} not found", request_id=_req_id())

    @router.get("/artifacts/{artifact_id}/content")
    async def get_artifact_content(
        artifact_id: str,
        request: Request,
    ) -> Response:
        """GET /api/product/v1/artifacts/{artifact_id}/content."""
        art_store: ArtifactStore = _artifact_store(request)

        # Stable UUID lookup (new path)
        if artifact_id.startswith("art_"):
            record = art_store.get(artifact_id)
            if record is not None:
                _check_map_report_owner(record, request)
                binary_path = _binary_artifact_path(record, request)
                if binary_path is not None:
                    return FileResponse(
                        binary_path,
                        media_type=record.content_type or "application/octet-stream",
                        filename=binary_path.name,
                    )
                if record.artifact_type in _BINARY_ARTIFACT_KINDS:
                    return canonical_error_response(
                        404, code=ErrorCode.ARTIFACT_NOT_FOUND,
                        message=f"Artifact {artifact_id} file is unavailable",
                        request_id=_req_id())
                if record.content_inline is not None:
                    return JSONResponse(status_code=200, content={"content": record.content_inline})
                return canonical_error_response(
                    404, code=ErrorCode.ARTIFACT_NOT_FOUND,
                    message=f"Artifact {artifact_id} has no inline content; use download_url",
                    request_id=_req_id())
            return canonical_error_response(
                404, code=ErrorCode.ARTIFACT_NOT_FOUND,
                message=f"Artifact {artifact_id} not found", request_id=_req_id())

        # Backward-compatible legacy index-based lookup
        store: RuntimeStore = _store(request)
        parts = artifact_id.rsplit(":", 2)
        if len(parts) < 2:
            return canonical_error_response(
                404, code=ErrorCode.ARTIFACT_NOT_FOUND,
                message=f"Artifact {artifact_id} not found", request_id=_req_id())

        for run in store.list_runs():
            for i, artifact in enumerate(run.artifacts):
                if f"{artifact.pack_name}:{artifact.artifact_type}:{i}" == artifact_id:
                    if artifact.content is not None:
                        return JSONResponse(status_code=200, content={"content": artifact.content})
                    return canonical_error_response(
                        404, code=ErrorCode.ARTIFACT_NOT_FOUND,
                        message=f"Artifact {artifact_id} has no inline content; use download_url",
                        request_id=_req_id())

        return canonical_error_response(
            404, code=ErrorCode.ARTIFACT_NOT_FOUND,
            message=f"Artifact {artifact_id} not found", request_id=_req_id())

    @router.get("/artifacts/{artifact_id}/render")
    async def get_artifact_render(
        artifact_id: str,
        request: Request,
    ) -> HTMLResponse:
        """GET /api/product/v1/artifacts/{artifact_id}/render — renderable HTML.

        Returns the artifact content as ``text/html`` so it can be used
        directly in an ``<iframe>`` or opened in a browser tab.
        Only supported for artifact kinds listed in ``_HTML_ARTIFACT_KINDS``.
        """
        art_store: ArtifactStore = _artifact_store(request)

        # Stable UUID lookup (new path)
        if artifact_id.startswith("art_"):
            record = art_store.get(artifact_id)
            if record is None:
                raise HTTPException(status_code=404, detail=f"Artifact {artifact_id} not found")
            _check_map_report_owner(record, request)
            if record.artifact_type not in _HTML_ARTIFACT_KINDS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Artifact {artifact_id} is not a renderable HTML artifact",
                )
            if record.content_path is not None:
                report_prefix = "/v2/reports/"
                if record.content_path.startswith(report_prefix):
                    report_root = get_lai_report_dir()
                    file_path = (report_root / record.content_path.removeprefix(report_prefix)).resolve()
                    try:
                        file_path.relative_to(report_root)
                    except ValueError:
                        raise HTTPException(status_code=404, detail=f"Render file not found for {artifact_id}")
                    if file_path.is_file():
                        return HTMLResponse(status_code=200, content=file_path.read_text(encoding="utf-8"))
                else:
                    file_path = Path(record.content_path).resolve()
                    configured_root = Path(
                        getattr(request.app.state, "product_artifact_root", _PRODUCT_ARTIFACT_ROOT)
                    ).resolve()
                    allowed_roots = (_PRODUCT_ARTIFACT_ROOT, configured_root, get_lai_report_dir())
                    if any(file_path.is_relative_to(root) for root in allowed_roots) and file_path.is_file():
                        return HTMLResponse(status_code=200, content=file_path.read_text(encoding="utf-8"))
                raise HTTPException(status_code=404, detail=f"Render file not found for {artifact_id}")
            if record.content_inline is not None:
                return HTMLResponse(status_code=200, content=record.content_inline)
            raise HTTPException(
                status_code=404,
                detail=f"Artifact {artifact_id} has no inline content",
            )

        # Backward-compatible legacy index-based lookup
        store: RuntimeStore = _store(request)
        parts = artifact_id.rsplit(":", 2)
        if len(parts) < 2:
            raise HTTPException(status_code=404, detail=f"Artifact {artifact_id} not found")

        for run in store.list_runs():
            for i, artifact in enumerate(run.artifacts):
                if f"{artifact.pack_name}:{artifact.artifact_type}:{i}" == artifact_id:
                    if artifact.artifact_type not in _HTML_ARTIFACT_KINDS:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Artifact {artifact_id} is not a renderable HTML artifact",
                        )
                    if artifact.content is None:
                        raise HTTPException(
                            status_code=404,
                            detail=f"Artifact {artifact_id} has no inline content",
                        )
                    return HTMLResponse(status_code=200, content=artifact.content)

        raise HTTPException(status_code=404, detail=f"Artifact {artifact_id} not found")

    # ═══════════════════════════════════════════════════════════
    #  Debug
    # ═══════════════════════════════════════════════════════════

    @router.get("/debug/runs/{run_id}/trace")
    async def get_run_trace(
        run_id: str,
        request: Request,
    ) -> JSONResponse:
        """GET /api/product/v1/debug/runs/{run_id}/trace — raw trace events."""
        store: RuntimeStore = _store(request)
        run = store.get_run(run_id)
        if run is None:
            return canonical_error_response(
                404, code=ErrorCode.RUN_NOT_FOUND,
                message=f"Run {run_id} not found", request_id=_req_id())
        return JSONResponse(status_code=200, content={
            "run_id": run_id,
            "trace": [t.model_dump(mode="json") for t in run.trace],
        })

    @router.get("/debug/runs/{run_id}/state")
    async def get_run_state(
        run_id: str,
        request: Request,
    ) -> JSONResponse:
        """GET /api/product/v1/debug/runs/{run_id}/state — full RunStateV2."""
        store: RuntimeStore = _store(request)
        art_store: ArtifactStore = _artifact_store(request)
        run = store.get_run(run_id)
        if run is None:
            return canonical_error_response(
                404, code=ErrorCode.RUN_NOT_FOUND,
                message=f"Run {run_id} not found", request_id=_req_id())

        try:
            engine: BoundedRuntimeEngine = _engine(request)
            visible_tools = getattr(engine, "tool_registry", None)
            visible_agents = getattr(engine, "agent_registry", None)

            tools_list = []
            if visible_tools is not None:
                tools_list = [t.model_dump(mode="json") for t in getattr(visible_tools, "list_tools", lambda: [])()]
            agents_list = []
            if visible_agents is not None:
                agents_list = [a.model_dump(mode="json") for a in getattr(visible_agents, "list_profiles", lambda: [])()]
        except Exception:
            tools_list, agents_list = [], []

        return JSONResponse(status_code=200, content={
            "run": _run_to_canonical(run, art_store).model_dump(mode="json"),
            "visible_tools": tools_list,
            "visible_agents": agents_list,
        })

    @router.post("/debug/runs/{run_id}/replay")
    async def replay_run(
        run_id: str,
        request: Request,
    ) -> JSONResponse:
        """POST /api/product/v1/debug/runs/{run_id}/replay — deterministic dry replay."""
        store: RuntimeStore = _store(request)
        art_store: ArtifactStore = _artifact_store(request)
        original = store.get_run(run_id)
        if original is None:
            return canonical_error_response(
                404, code=ErrorCode.RUN_NOT_FOUND,
                message=f"Run {run_id} not found", request_id=_req_id())

        engine: BoundedRuntimeEngine = _engine(request)
        try:
            replayed = engine.run(
                session_id=original.session_id,
                user_message=original.input_message,
                user_id="debug-replay",
                request_context=original.input_context,
                granted_permissions=_CANONICAL_ALGORITHM_PERMISSIONS,
            )

            return JSONResponse(status_code=200, content={
                "replay_mode": "deterministic_dry_replay",
                "notes": "Replay completed. Compare original vs replayed fields.",
                "original": _run_to_canonical(original, art_store).model_dump(mode="json"),
                "replayed": _run_to_canonical(replayed, art_store).model_dump(mode="json"),
                "comparison": {
                    "overall_match": original.output_message == replayed.output_message and original.status == replayed.status,
                    "status_match": original.status == replayed.status,
                    "output_message_match": original.output_message == replayed.output_message,
                    "artifact_count_match": len(original.artifacts) == len(replayed.artifacts),
                    "mismatch_fields": _diff_runs(original, replayed),
                },
            })
        except Exception as exc:
            logger.exception("debug_replay_failed | run_id=%s", run_id)
            return canonical_error_response(
                500, code=ErrorCode.INTERNAL_ERROR,
                message=f"Replay failed: {exc}", request_id=_req_id())

    return router


# ── Install helper ──

def install_canonical_product_api(
    app,
    db_path: str | None = None,
    *,
    auth_required: bool | None = None,
    auth_token: str | None = None,
) -> APIRouter:
    """Install the canonical product API router on *app*.

    Usage::

        from api.canonical.router import install_canonical_product_api
        install_canonical_product_api(app)

    Initializes product stores on ``app.state`` at install time (not lazily on
    first request), avoiding race conditions under concurrent startup.

    All three stores share the same SQLite database file via *db_path* for
    persistence across restarts.  When ``None``, defaults to
    ``data/ktp_v2_runtime.sqlite3`` relative to the backend directory.

    Idempotent: calling multiple times on the same app is safe.
    """
    existing_router: APIRouter | None = getattr(app.state, "canonical_product_router", None)
    if existing_router is not None:
        logger.debug("canonical_product_api_already_installed_on_app — skipping duplicate")
        return existing_router
    # Eager initialization — not on first request (see BUG-03).
    # Share the same db_path across all product stores so they populate
    # the same SQLite database file (product_submissions / product_datasets
    # / product_artifacts tables).
    app.state.product_submission_store = SubmissionStore(db_path=db_path)
    app.state.product_dataset_store = DatasetStore(db_path=db_path)
    app.state.product_artifact_store = ArtifactStore(db_path=db_path)
    app.state.product_idempotency_store = IdempotencyStore(db_path=db_path)
    app.state.product_farm_store = FarmStore()
    app.state.sentinel_stac_provider = SentinelStacProvider()
    app.state.lai_analysis_store = LaiAnalysisStore(db_path=db_path)
    app.state.crop_analysis_store = CropAnalysisStore(db_path=db_path)
    app.state.analysis_workflow_store = AnalysisWorkflowStore(db_path=db_path)
    if auth_required is None:
        auth_required = os.getenv("APP_AUTH_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    app.state.product_auth_required = auth_required
    app.state.product_auth_token = auth_token if auth_token is not None else os.getenv("APP_AUTH_TOKEN", "")
    app.add_middleware(CanonicalProtocolMiddleware)
    router = build_canonical_router()
    app.include_router(router, prefix="/api/product/v1")
    app.state.canonical_product_router = router

    async def cleanup_expired_product_resources() -> None:
        # Event history and artifact files are intentionally retained; only
        # disconnected/terminal in-memory queues are eligible for cleanup.
        app.state.product_submission_store.cleanup_terminal_resources()
        app.state.lai_analysis_store.cleanup_terminal_resources()

    async def close_product_stores() -> None:
        await cleanup_expired_product_resources()
        stores_and_methods = (
            (app.state.product_submission_store, "close"),
            (app.state.product_dataset_store, "close"),
            (app.state.product_artifact_store, "close"),
            (app.state.product_idempotency_store, "close"),
            (app.state.lai_analysis_store, "close_store"),
            (app.state.crop_analysis_store, "close"),
            (app.state.analysis_workflow_store, "close"),
        )
        for store, method_name in stores_and_methods:
            try:
                getattr(store, method_name)()
            except Exception:
                logger.exception("canonical_product_store_close_failed | store=%s", type(store).__name__)

    app.router.add_event_handler("startup", cleanup_expired_product_resources)
    app.router.add_event_handler("shutdown", close_product_stores)
    logger.info("canonical_product_api_installed | prefix=/api/product/v1")
    return router


# ── Internal helpers ──

def _emit_event(
    sub_store: SubmissionStore,
    submission_id: str,
    event: SubmissionEventKind,
    *,
    stage: SubmissionStage | None = None,
    run_id: str | None = None,
    detail: str = "",
    data: dict | None = None,
) -> None:
    """Emit a canonical SSE event through the submission store."""
    sub_store.push_event(submission_id, {
        "event": event,
        "submission_id": submission_id,
        "run_id": run_id,
        "stage": stage,
        "detail": detail,
        "data": data or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


def _encode_submission_sse_event(event_data: dict) -> str:
    """Encode one persisted submission event with its durable event sequence."""
    sequence = int(event_data["sequence"])
    event_name = event_data.get("event", "message")
    payload = {key: value for key, value in event_data.items() if key not in ("event", "sequence")}
    return (
        f"id: evt_{sequence:04d}\n"
        f"event: {event_name}\n"
        f"data: {json.dumps(payload)}\n"
        f"\n"
    )


def _diff_runs(original: RunDetail, replayed: RunDetail) -> list[str]:
    """Return a list of field names that differ between two runs."""
    mismatches: list[str] = []
    if original.status != replayed.status:
        mismatches.append("status")
    if original.output_message != replayed.output_message:
        mismatches.append("output_message")
    if len(original.artifacts) != len(replayed.artifacts):
        mismatches.append("artifact_count")
    if len(original.trace) != len(replayed.trace):
        mismatches.append("trace_event_count")
    if original.replan_count != replayed.replan_count:
        mismatches.append("replan_count")
    if original.delegation_count != replayed.delegation_count:
        mismatches.append("delegation_count")
    return mismatches
