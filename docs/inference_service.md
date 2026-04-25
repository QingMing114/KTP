# Inference Service Draft

## Scope

This phase adds a dedicated `inference_service` that owns one bounded job:

request -> lookup ready model -> preprocess image -> run predictor -> postprocess output -> return structured result

It does not decide whether training should happen, does not register models, does not render reports, and does not replace the LangGraph orchestrator.

## Why a Separate Service

Inference will eventually become one of the most volatile parts of the system. Model formats, preprocessing rules, output shapes, and performance strategies will all change. Keeping inference behind its own service boundary lets the orchestrator stay thin and lets future model backends evolve without pulling route handlers or agent prompts apart.

## API Contract

The service exposes:

- `GET /health`
- `POST /infer`
- `GET /`

`POST /infer` returns a structured payload that is already shaped for later orchestrator, report, and confidence stages:

```json
{
  "request_id": "req-001",
  "success": true,
  "result": {
    "mask_uri": "/tmp/ktp_masks/req-001_mask.png",
    "affected_area": 64.0,
    "confidence": 0.91,
    "polygons": [
      {
        "id": "poly-1",
        "points": [[5, 4], [13, 4], [13, 12], [5, 12]]
      }
    ],
    "model_name": "wheat-baldness_detection-rf",
    "model_version": "v5",
    "artifact_uri": "mock://models/henan/wheat/baldness_detection/v5/model.pkl"
  },
  "message": "inference completed"
}
```

If there is no ready model, the service still returns a structured payload with `success=false` and `result=null`.

## Main Components

- `adapters/model_registry_client.py`: looks up the latest ready model from `model_registry`
- `loaders/model_loader.py`: isolates mock and future real model loading
- `preprocessing/preprocess.py`: minimal Pillow + NumPy loading and normalization
- `predictors/mock_predictor.py`: deterministic predictor for phase-5 validation
- `predictors/real_predictor.py`: explicit real-backend placeholder
- `postprocessing/postprocess.py`: writes a mask file and normalizes predictor output into API schema
- `service.py`: coordinates the full chain and returns structured success or failure results

## Mock vs Real Predictor

`MockPredictor` remains the fast contract-validation path. It generates a stable mask, confidence, and bounding polygon directly from image intensity so the service contract can be validated end to end.

`RealPredictor` now executes a migrated RF pipeline under `ml/baldness_rf/`. That code was pulled from the external baldness project at the algorithm layer only:

- feature extraction
- RF classification
- pipeline orchestration

The old external API shell and graph shell were intentionally not copied over.

## Model Registry Relationship

Even in mock mode, inference still asks the model registry for a ready model. That keeps the control flow aligned with the real system:

1. resolve `region + crop_type + task_type`
2. find the latest ready model
3. use that metadata during load and prediction

This means the orchestrator can later call inference without needing separate model lookup logic.

## Baldness RF Integration

The external baldness project under `~/bantushibie` is still not used as a runtime service dependency. Instead, the algorithm core was migrated into this repository:

- `ml/baldness_rf/feature_extractor.py`
- `ml/baldness_rf/classifier.py`
- `ml/baldness_rf/pipeline.py`

`real_predictor.py` now calls this migrated pipeline. `model_loader.py` resolves a local RF model artifact path from the model registry metadata. In practice this means the model registry should return a local path or `file://...` URI for the RF `.pkl` artifact in the current environment.

The external repository still remains the source of truth for historical context and comparison, but not for production service wiring.

## Future Extension Path

Later phases can evolve this service without breaking its contract:

- keep Pillow loading for mock mode and use Rasterio/GDAL paths for real multispectral mode
- add PyTorch model loading for newer architectures
- emit richer masks, polygons, and statistics
- upload mask outputs to object storage instead of local disk
- add larger-image tiling and GPU-aware execution
