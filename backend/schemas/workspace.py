"""Product-facing map context and bounded assistant intents."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from schemas.analysis_workflow import TaskId
from schemas.spatial import AoiGeometry, ImageryCandidate


class WorkspaceContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=120)
    revision: int = Field(ge=0)
    execution_mode: Literal["live", "demo"] = "live"
    farm_id: str | None = None
    aoi: AoiGeometry | None = None
    imagery_item_id: str | None = None
    imagery_snapshot: ImageryCandidate | None = None
    active_workflow_id: str | None = None
    draft_task_ids: list[TaskId] = Field(default_factory=list)


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
    candidate_ids: list[str] = Field(default_factory=list, max_length=5)
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
    imagery_candidates: list[WorkspaceUiCandidate] = Field(default_factory=list, max_length=5)
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
    unsupported_parameters: list[str] = Field(default_factory=list)
