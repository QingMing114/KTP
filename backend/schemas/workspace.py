"""Product-facing map context and bounded assistant intents."""
from typing import Literal
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schemas.analysis_workflow import TaskId
from schemas.spatial import AoiGeometry, ImageryCandidate, ImagerySearchRequest
from schemas.runtime import SceneParameters


class WorkspaceImagerySearch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_date: date | None = None
    end_date: date | None = None
    max_cloud_cover: float = Field(default=20, ge=0, le=100)


class WorkspaceContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=120)
    revision: int = Field(ge=0)
    execution_mode: Literal["live", "demo"] = "live"
    auto_execute: bool = False
    professional_mode: bool = False
    imagery_search: WorkspaceImagerySearch | None = None
    farm_id: str | None = None
    aoi: AoiGeometry | None = None
    imagery_item_id: str | None = None
    imagery_snapshot: ImageryCandidate | None = None
    active_workflow_id: str | None = None
    draft_task_ids: list[TaskId] = Field(default_factory=list)
    apsim_mode: Literal["field", "example"] = "field"

    @model_validator(mode="after")
    def exclusive_execution_modes(self):
        if self.auto_execute and self.professional_mode:
            raise ValueError("专业模式与自动执行不能同时开启")
        return self


class WorkspaceUiCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: str = Field(max_length=300)
    observed_at: str = Field(max_length=40)
    cloud: str = Field(max_length=40)
    recommended: bool = False
    selected: bool = False


class WorkspaceUiTaskOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: TaskId | Literal["forecast"]
    label: str = Field(max_length=80)
    available: bool
    status: str = Field(max_length=80)


class WorkspaceUiCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    card_id: str = Field(min_length=1, max_length=200)
    kind: Literal["farm", "aoi", "imagery_candidates", "imagery_selected", "task_selection", "analysis_plan", "parameter_set", "workflow"]
    title: str = Field(max_length=120)
    state: Literal["current", "historical"] = "current"
    summary: str = Field(default="", max_length=2500)
    task_ids: list[TaskId] = Field(default_factory=list, max_length=6)
    candidate_ids: list[str] = Field(default_factory=list, max_length=60)
    selected_candidate_id: str | None = None
    fields: dict[str, str] = Field(default_factory=dict, max_length=16)
    missing_inputs: list[str] = Field(default_factory=list, max_length=10)
    source_run_id: str | None = None
    workflow_id: str | None = None


class WorkspaceUiState(BaseModel):
    """Presentation observations are separate from the versioned execution snapshot."""
    model_config = ConfigDict(extra="forbid")
    stage: Literal["idle", "candidates", "ready", "running", "done"]
    cards: list[WorkspaceUiCard] = Field(default_factory=list, max_length=12)
    imagery_candidates: list[WorkspaceUiCandidate] = Field(default_factory=list, max_length=60)
    task_options: list[WorkspaceUiTaskOption] = Field(default_factory=list, max_length=7)


class WorkspaceIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{
        "intent": "advise", "task_ids": ["lai", "crop"],
        "summary": "可以先运行 LAI 反演与作物识别。", "rationale": "两项任务共用当前影像。",
        "explicit_execution": False, "unsupported_parameters": [],
    }]})
    intent: Literal["advise", "configure", "execute", "explain", "status"]
    task_ids: list[TaskId] = Field(default_factory=list)
    summary: str = Field(max_length=2000)
    rationale: str = Field(default="", max_length=2000)
    explicit_execution: bool = False
    yield_demo_crop: Literal["wheat", "maize"] | None = None
    apsim_mode: Literal["field", "example"] | None = None
    unsupported_parameters: list[str] = Field(default_factory=list)
    imagery_search: WorkspaceImagerySearch | None = None


class LaiParameterRanges(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lai_range: tuple[float, float] | None = None
    cab_range: tuple[float, float] | None = None
    lidfa_range: tuple[float, float] | None = None
    psoil_range: tuple[float, float] | None = None

    @model_validator(mode="after")
    def validate_ranges(self):
        SceneParameters.model_validate(self.model_dump())
        return self


class ProfessionalReview(BaseModel):
    review_id: str
    workspace_id: str
    source_run_id: str
    conversation_id: str | None = None
    phase: Literal["search", "workflow", "lai", "crop"]
    status: Literal["pending", "processing", "confirmed", "cancelled", "failed"] = "pending"
    title: str
    rationale: str = ""
    context: WorkspaceContext
    intent: WorkspaceIntent
    search: ImagerySearchRequest | None = None
    candidates: list[ImageryCandidate] = Field(default_factory=list)
    selected_imagery_id: str | None = None
    proposed_scene: dict | None = None
    proposed_crop: dict | None = None
    workflow_id: str | None = None
    step_version: str | None = None
    next_review_id: str | None = None
    created_at: str
    detail: str = "等待编辑参数并确认"
    confirmed_parameters: dict | None = None


class ConfirmProfessionalReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    context: WorkspaceContext
    decision: Literal["confirm", "cancel"] = "confirm"
    search: WorkspaceImagerySearch | None = None
    imagery_item_id: str | None = None
    task_ids: list[TaskId] | None = Field(default=None, min_length=1)
    apsim_mode: Literal["field", "example"] | None = None
    scene: LaiParameterRanges | None = None
    crop_class_id: int | None = Field(default=None, ge=0, le=5)
