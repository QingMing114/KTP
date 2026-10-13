"""Typed contract for a map analysis workflow and its planned dependencies."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from schemas.spatial import AoiGeometry, ImageryCandidate

TaskId = Literal["crop", "lai", "growth", "potential", "yield_simple", "yield"]
StepId = Literal["imagery", "crop", "lai", "growth", "potential", "yield_simple", "yield"]
WorkflowStatus = Literal["planned", "running", "completed", "blocked", "failed", "cancelled"]
StepStatus = Literal["planned", "waiting", "running", "completed", "blocked", "failed", "skipped"]

TASK_ORDER: tuple[TaskId, ...] = ("crop", "lai", "growth", "potential", "yield_simple", "yield")


class CreateAnalysisWorkflowRequest(BaseModel):
    data_mode: Literal["live", "demo"] = "live"
    demo_crop: Literal["wheat", "maize"] | None = None
    aoi: AoiGeometry
    imagery_item_id: str = Field(min_length=1)
    imagery_snapshot: ImageryCandidate | None = None
    farm_id: str | None = None
    requested_task_ids: list[TaskId] = Field(min_length=1)
    start_immediately: bool = True
    action_id: str | None = Field(default=None, min_length=1, max_length=200)
    workspace_id: str | None = None
    workspace_revision: int | None = None
    conversation_id: str | None = None
    run_id: str | None = None
    yield_inputs: "YieldAgronomicInputs" = Field(default_factory=lambda: YieldAgronomicInputs())

    @model_validator(mode="after")
    def validate_demo(self):
        if self.data_mode == "demo":
            if not self.demo_crop or not set(self.requested_task_ids) <= {"yield", "yield_simple"}:
                raise ValueError("模拟演示仅支持小麦/玉米估产任务，请单独选择估产任务")
        elif self.demo_crop is not None:
            raise ValueError("demo_crop requires data_mode=demo")
        return self

    @field_validator("requested_task_ids")
    @classmethod
    def unique_tasks(cls, value: list[TaskId]) -> list[TaskId]:
        if len(value) != len(set(value)):
            raise ValueError("requested_task_ids must not contain duplicates")
        return value


class WorkflowStep(BaseModel):
    step_id: StepId
    depends_on: list[StepId] = Field(default_factory=list)
    status: StepStatus = "planned"
    progress_percent: int = Field(default=0, ge=0, le=100)
    analysis_id: str | None = None
    detail: str = ""
    result: dict[str, Any] = Field(default_factory=dict)
    updated_at: str | None = None


class AnalysisWorkflowSummary(BaseModel):
    data_mode: Literal["live", "demo"] = "live"
    demo_crop: Literal["wheat", "maize"] | None = None
    workflow_id: str
    owner_id: str
    action_id: str | None = None
    workspace_id: str | None = None
    workspace_revision: int | None = None
    conversation_id: str | None = None
    run_id: str | None = None
    parameters: dict[str, Any] = Field(default_factory=lambda: {
        "target_resolution_m": 20,
        "reflectance_bands": ["B02", "B03", "B04", "B07", "B08"],
        "parameter_source": "algorithm_fixed",
    })
    status: WorkflowStatus = "planned"
    detail: str = "工作流已登记，等待启动"
    aoi: AoiGeometry
    imagery_item_id: str
    imagery_snapshot: ImageryCandidate
    farm_id: str | None = None
    yield_inputs: "YieldAgronomicInputs" = Field(default_factory=lambda: YieldAgronomicInputs())
    requested_task_ids: list[TaskId]
    effective_task_ids: list[TaskId]
    steps: list[WorkflowStep]
    created_at: str
    updated_at: str
    completed_at: str | None = None
    report_artifact_id: str | None = None
    report_uri: str | None = None
    report_kind: str | None = None
    report_version: str | None = None
    report_data_artifact_id: str | None = None
    report_data_uri: str | None = None


class AnalysisWorkflowEvent(BaseModel):
    event_id: str
    workflow_id: str
    sequence: int
    kind: Literal["created", "step_updated", "status_updated"]
    step_id: StepId | None = None
    detail: str
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    timestamp: str


class AnalysisWorkflowEventsResponse(BaseModel):
    items: list[AnalysisWorkflowEvent]


class RetryAnalysisWorkflowRequest(BaseModel):
    step_id: Literal["imagery", "crop", "lai", "potential", "yield_simple", "yield"]


class YieldAgronomicInputs(BaseModel):
    """Farmer supplied inputs. Weather, soil and management remain server verified sources."""

    confirmed_crop_class_id: int | None = Field(default=None, ge=0, le=5)
    field_dataset_id: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$")
    cultivar: str | None = Field(default=None, min_length=1, max_length=120)
    sowing_date: date | None = None


class YieldInputIssue(BaseModel):
    code: str
    field: str
    message: str


class YieldInputAssessment(BaseModel):
    contract_version: Literal["yield-input-v1"] = "yield-input-v1"
    status: Literal["blocked", "ready"] = "blocked"
    resolved_crop: str | None = None
    crop_source: Literal["model", "user_confirmed", "unresolved"] = "unresolved"
    crop_model_score: float | None = None
    crop_score_margin: float | None = None
    imagery_acquired_at: str | None = None
    aoi_source: str = "verified_workflow_aoi"
    lai_observation: dict[str, Any] | None = None
    lai_use: Literal["same_day_simulated_lai_constraint_v1"] = "same_day_simulated_lai_constraint_v1"
    field_dataset: dict[str, Any] | None = None
    sources: dict[str, str] = Field(default_factory=dict)
    issues: list[YieldInputIssue] = Field(default_factory=list)


class UpdateYieldInputsRequest(BaseModel):
    yield_inputs: YieldAgronomicInputs


def planned_steps(requested: list[TaskId]) -> tuple[list[TaskId], list[WorkflowStep]]:
    effective = set(requested)
    if "yield_simple" in effective:
        effective.add("crop")
    if "yield" in effective:
        effective.update(("crop", "lai"))
    if "potential" in effective:
        effective.update(("crop", "lai"))
    if "growth" in effective:
        effective.add("lai")
    ordered = [task for task in TASK_ORDER if task in effective]
    steps: list[WorkflowStep] = [WorkflowStep(step_id="imagery")]
    for task in ordered:
        dependencies: list[StepId] = {
            "crop": ["imagery"], "lai": ["imagery"],
            "growth": ["lai"], "potential": ["crop", "lai"], "yield_simple": ["crop"], "yield": ["crop", "lai"],
        }[task]
        steps.append(WorkflowStep(step_id=task, depends_on=dependencies))
    return ordered, steps
