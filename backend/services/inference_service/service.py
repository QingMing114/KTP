"""Business orchestration for the inference service."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field

from services.inference_service.adapters.model_registry_client import (
    ModelRegistryClient,
    ModelRegistryClientError,
)
from services.inference_service.config import (
    InferenceServiceConfig,
    get_inference_service_config,
)
from services.inference_service.loaders.model_loader import ModelLoader
from services.inference_service.postprocessing.postprocess import build_inference_result
from services.inference_service.predictors.mock_predictor import MockPredictor
from services.inference_service.predictors.real_predictor import RealPredictor
from services.inference_service.predictors.lai_predictor import LAIPredictor
from services.inference_service.preprocessing.preprocess import (
    preprocess_image,
    validate_image_path,
)
from services.inference_service.schemas import InferenceRequest, InferenceResponse

logger = logging.getLogger(__name__)


class LAIInferenceResponse:
    """Structured response for LAI inversion results."""

    def __init__(
        self,
        request_id: str,
        success: bool,
        lai: float = 0.0,
        confidence: float = 0.0,
        num_pixels: int = 0,
        mean_lai: float = 0.0,
        std_lai: float = 0.0,
        lut_path: str = "",
        method: str = "min_distance",
        message: str = "",
    ):
        self.request_id = request_id
        self.success = success
        self.lai = lai
        self.confidence = confidence
        self.num_pixels = num_pixels
        self.mean_lai = mean_lai
        self.std_lai = std_lai
        self.lut_path = lut_path
        self.method = method
        self.message = message

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "success": self.success,
            "lai": self.lai,
            "confidence": self.confidence,
            "num_pixels": self.num_pixels,
            "mean_lai": self.mean_lai,
            "std_lai": self.std_lai,
            "lut_path": self.lut_path,
            "method": self.method,
            "message": self.message,
        }


class InferenceService:
    """Primary business service for model lookup, prediction, and postprocessing."""

    TASK_TYPE_LAI = "lai_inversion"

    def __init__(
        self,
        *,
        config: InferenceServiceConfig | None = None,
        model_registry_client: ModelRegistryClient | None = None,
        model_loader: ModelLoader | None = None,
        mock_predictor: MockPredictor | None = None,
        real_predictor: RealPredictor | None = None,
        lai_predictor: LAIPredictor | None = None,
    ) -> None:
        self._config = config or get_inference_service_config()
        self._model_registry_client = model_registry_client or ModelRegistryClient(
            config=self._config
        )
        self._model_loader = model_loader or ModelLoader(config=self._config)
        self._mock_predictor = mock_predictor or MockPredictor()
        self._real_predictor = real_predictor or RealPredictor(config=self._config)
        self._lai_predictor = lai_predictor or LAIPredictor()

    async def run_inference(self, request: InferenceRequest) -> InferenceResponse:
        """Run the bounded inference chain and always return a structured response."""
        resolved_task_type = request.task_type or self._config.default_task_type

        if resolved_task_type == self.TASK_TYPE_LAI:
            return await self._run_lai_inference(request)

        return await self._run_standard_inference(request, resolved_task_type)

    async def _run_lai_inference(self, request: InferenceRequest) -> InferenceResponse:
        """Execute LAI inversion via PROSAIL without model registry."""
        logger.info(
            "lai_inference_started | request_id=%s | reflectance=%s",
            request.request_id,
            request.extra_params.get("reflectance"),
        )

        try:
            lai_output = self._lai_predictor.predict(
                image_array=None,
                model_metadata=None,
                loaded_model=None,
                extra_params=request.extra_params,
            )
            metadata = lai_output.metadata

            lai_response = LAIInferenceResponse(
                request_id=request.request_id,
                success=True,
                lai=metadata.get("primary_lai", 0.0),
                confidence=metadata.get("primary_confidence", 0.0),
                num_pixels=metadata.get("num_pixels", 0),
                mean_lai=metadata.get("mean_lai", 0.0),
                std_lai=metadata.get("std_lai", 0.0),
                lut_path=metadata.get("lut_path", ""),
                method=metadata.get("method", "min_distance"),
                message="LAI inversion completed successfully",
            )

            logger.info(
                "lai_inference_succeeded | request_id=%s | lai=%.3f | confidence=%.3f",
                request.request_id,
                lai_response.lai,
                lai_response.confidence,
            )

            return InferenceResponse(
                request_id=request.request_id,
                success=True,
                result=None,
                message=f"LAI={lai_response.lai:.3f}, confidence={lai_response.confidence:.3f}",
            )

        except Exception as exc:
            logger.exception("lai_inference_failed | request_id=%s", request.request_id)
            return self._failure_response(
                request_id=request.request_id,
                message=f"LAI inversion failed: {exc}",
            )

    async def _run_standard_inference(
        self, request: InferenceRequest, resolved_task_type: str
    ) -> InferenceResponse:
        """Execute standard image inference via model registry + predictor."""
        use_mock = (
            self._config.default_use_mock
            if request.use_mock is None
            else request.use_mock
        )
        logger.info(
            "inference_started | request_id=%s | region=%s | crop_type=%s | task_type=%s | use_mock=%s",
            request.request_id,
            request.region,
            request.crop_type,
            resolved_task_type,
            use_mock,
        )

        try:
            model_metadata = await self._model_registry_client.lookup_ready_model(
                region=request.region,
                crop_type=request.crop_type,
                task_type=resolved_task_type,
            )
        except ModelRegistryClientError as exc:
            logger.warning(
                "inference_failed | request_id=%s | stage=model_lookup | detail=%s",
                request.request_id,
                str(exc),
            )
            return self._failure_response(
                request_id=request.request_id,
                message=f"model registry lookup failed: {exc}",
            )

        if model_metadata is None:
            message = (
                "no ready model found for "
                f"region={request.region} crop_type={request.crop_type} task_type={resolved_task_type}"
            )
            logger.info(
                "inference_completed | request_id=%s | success=false | reason=no_ready_model",
                request.request_id,
            )
            return self._failure_response(request_id=request.request_id, message=message)

        if use_mock:
            try:
                image_array = preprocess_image(request.image_path)
            except Exception as exc:
                logger.exception(
                    "inference_failed | request_id=%s | stage=preprocess",
                    request.request_id,
                )
                return self._failure_response(
                    request_id=request.request_id,
                    message=f"unable to preprocess image_path {request.image_path}: {exc}",
                )
        else:
            try:
                validate_image_path(request.image_path)
            except Exception as exc:
                logger.exception(
                    "inference_failed | request_id=%s | stage=input_validation",
                    request.request_id,
                )
                return self._failure_response(
                    request_id=request.request_id,
                    message=f"invalid image_path {request.image_path}: {exc}",
                )

        try:
            if use_mock:
                loaded_model = self._model_loader.load_mock_model(model_metadata)
                predictor_output = self._mock_predictor.predict(
                    image_array=image_array,
                    model_metadata=model_metadata,
                    loaded_model=loaded_model,
                    extra_params=request.extra_params,
                )
            else:
                loaded_model = self._model_loader.load_real_model(model_metadata)
                predictor_output = self._real_predictor.predict(
                    image_array=None,
                    model_metadata=model_metadata,
                    loaded_model=loaded_model,
                    extra_params={
                        **request.extra_params,
                        "image_path": request.image_path,
                        "request_id": request.request_id,
                    },
                )
        except Exception as exc:
            logger.exception(
                "inference_failed | request_id=%s | stage=%s",
                request.request_id,
                "mock_predictor" if use_mock else "real_predictor",
            )
            return self._failure_response(
                request_id=request.request_id,
                message=f"predictor failed: {exc}",
            )

        try:
            result = build_inference_result(
                request_id=request.request_id,
                predictor_output=predictor_output,
                model_metadata=model_metadata,
                mask_output_dir=self._config.mask_output_dir,
                extra_params=request.extra_params,
                default_class_semantics_json=self._config.default_prediction_class_semantics_json,
            )
        except Exception as exc:
            logger.exception(
                "inference_failed | request_id=%s | stage=postprocess",
                request.request_id,
            )
            return self._failure_response(
                request_id=request.request_id,
                message=f"postprocessing failed: {exc}",
            )

        logger.info(
            "inference_succeeded | request_id=%s | model_name=%s | version=%s",
            request.request_id,
            result.model_name,
            result.model_version,
        )
        return InferenceResponse(
            request_id=request.request_id,
            success=True,
            result=result,
            message="inference completed",
        )

    def _failure_response(self, *, request_id: str, message: str) -> InferenceResponse:
        return InferenceResponse(
            request_id=request_id,
            success=False,
            result=None,
            message=message,
        )
