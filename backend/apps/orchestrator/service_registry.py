"""Dependency wiring for orchestrator-local service adapters."""

from __future__ import annotations

from functools import lru_cache

from apps.orchestrator.clients.confidence_service_client import ConfidenceServiceClient
from apps.orchestrator.clients.inference_service_client import InferenceServiceClient
from apps.orchestrator.clients.model_registry_client import ModelRegistryClient
from apps.orchestrator.clients.rag_service_client import RAGServiceClient
from apps.orchestrator.clients.report_service_client import ReportServiceClient
from apps.orchestrator.clients.training_service_client import TrainingServiceClient
from apps.orchestrator.clients.visualization_service_client import VisualizationServiceClient
from agents.core_70b.agent import PlannerAgent
from agents.executor_30b.agent import ExecutorAgent
from agents.executor_30b.reasoner import ExecutorReasoner
from agents.executor_30b.tool_executor import ToolExecutor
from apps.orchestrator.config import get_orchestrator_runtime_config
from infra.llm.config import get_agent_llm_config
from infra.llm.provider import get_agent_llm_provider
from services.inference_service.config import (
    InferenceServiceConfig,
    get_inference_service_config,
)
from services.mock_services import MockTrainingService
from services.confidence_service.config import get_confidence_service_config
from services.rag_service.config import get_rag_service_config
from services.report_service.config import get_report_service_config
from services.training_service.config import get_training_service_config
from services.visualization_service.config import get_visualization_service_config


@lru_cache(maxsize=1)
def get_model_registry_lookup_client() -> ModelRegistryClient:
    """Return a cached local model registry client for workflow lookups."""
    config = get_orchestrator_runtime_config()
    return ModelRegistryClient(database_url=config.database_url)


@lru_cache(maxsize=1)
def get_orchestrator_tool_executor() -> ToolExecutor:
    """Return the executor wiring used by the orchestrator graph nodes."""
    orchestrator_config = get_orchestrator_runtime_config()
    confidence_config = get_confidence_service_config()
    base_inference_config = get_inference_service_config()
    rag_config = get_rag_service_config()
    report_config = get_report_service_config()
    training_config = get_training_service_config()
    visualization_config = get_visualization_service_config()
    inference_config = InferenceServiceConfig(
        inference_service_name=base_inference_config.inference_service_name,
        model_registry_url=base_inference_config.model_registry_url,
        default_task_type=base_inference_config.default_task_type,
        default_use_mock=orchestrator_config.default_use_mock,
        mask_output_dir=orchestrator_config.inference_mask_output_dir,
        real_predictor_backend=base_inference_config.real_predictor_backend,
        baldness_rf_source_root=base_inference_config.baldness_rf_source_root,
        baldness_rf_default_model_path=base_inference_config.baldness_rf_default_model_path,
        baldness_rf_work_dir=base_inference_config.baldness_rf_work_dir,
        inference_http_timeout_seconds=base_inference_config.inference_http_timeout_seconds,
    )
    if orchestrator_config.training_backend == "temporal":
        training_service = TrainingServiceClient(
            config=training_config,
            dataset_uri_root=orchestrator_config.training_dataset_uri_root,
            output_model_prefix=orchestrator_config.training_model_prefix,
        )
    else:
        training_service = MockTrainingService()
    return ToolExecutor(
        training_service=training_service,
        inference_service=InferenceServiceClient(
            config=inference_config,
            database_url=orchestrator_config.database_url,
            default_image_path=orchestrator_config.default_image_path,
        ),
        rag_service=RAGServiceClient(config=rag_config),
        report_service=ReportServiceClient(config=report_config),
        confidence_service=ConfidenceServiceClient(config=confidence_config),
        visualization_service=VisualizationServiceClient(config=visualization_config),
    )


@lru_cache(maxsize=1)
def get_orchestrator_planner_agent() -> PlannerAgent:
    """Return a cached planner agent configured for the orchestrator workflow."""
    agent_llm_config = get_agent_llm_config()
    llm_provider = get_agent_llm_provider() if agent_llm_config.planner_enabled else None
    return PlannerAgent(llm_provider=llm_provider)


@lru_cache(maxsize=1)
def get_orchestrator_executor_agent() -> ExecutorAgent:
    """Return a cached executor agent configured for the orchestrator workflow."""
    agent_llm_config = get_agent_llm_config()
    llm_provider = get_agent_llm_provider() if agent_llm_config.executor_enabled else None
    return ExecutorAgent(
        tool_executor=get_orchestrator_tool_executor(),
        reasoner=ExecutorReasoner(
            llm_provider=llm_provider,
            enabled=agent_llm_config.executor_enabled,
        ),
    )
