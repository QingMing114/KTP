# KTP Pack

## Purpose

`ktp` is now the first real V2 domain pack instead of the platform core.

Its job is to expose existing KTP Python service capabilities through the V2 bounded tool contract so the runtime can treat KTP as one pack among many.

## Current Tools

- `ktp.lookup_model_registry`
- `ktp.run_inference_workflow`
- `ktp.trigger_training`
- `ktp.retrieve_knowledge`
- `ktp.build_report`
- `ktp.evaluate_confidence`
- `ktp.build_visualization`

## How It Works

Current implementation lives across:

- `v2/adapters/python_services/ktp_services.py`
- `v2/adapters/python_services/ktp_rag.py`
- `v2/tools/handlers.py`
- `v2/tools/registry.py`
- `v2/packs/demo_pack.py`
- `apps/api_gateway/services/gateway_agent_service.py`

The pack now uses a real-first bounded execution strategy:

- KTP knowledge retrieval goes through the existing local RAG adapter
- model lookup, inference, training, report, confidence, and visualization go through the KTP service bundle
- when a real backend is unavailable, the pack now raises an explicit bounded error instead of silently falling back
- mock execution remains available only when the caller explicitly passes `use_mock_backend=true` / `use_mock=true`

## Inputs And Outputs

Most current KTP V2 handlers accept:

- `query`
- optional `region`
- optional `crop_type`
- optional `task_type`
- optional `request_id`
- optional `use_mock_backend`
- optional `image_path`
- optional `extra_params`

Current default demo context is:

- `region=henan`
- `crop_type=wheat`
- `task_type=crop_health_detection`

The public gateway path sends the same fields through `RequestContextV2`, using:

- `entrypoint="chat"` for `POST /chat`
- `entrypoint="detect"` for `POST /detect`
- `entrypoint="v2_ui"` for `/v2/ui`

Each tool returns:

- one `ObservationV2`
- zero or more `PackArtifactView`

The observation payload includes:

- normalized KTP request context
- backend selection notes
- structured service results for model lookup, inference, RAG, training, report, confidence, and visualization when present

## Default Pack Flow

The bounded KTP pack flow used by the V2 runtime is:

1. `ktp.lookup_model_registry`
2. `ktp.run_inference_workflow`
3. optional `ktp.retrieve_knowledge`
4. `ktp.build_report`
5. `ktp.evaluate_confidence`
6. optional `ktp.build_visualization`

Flow rules:

- `/detect` includes visualization by default
- `/chat` only includes visualization when the user explicitly asks for it or `extra_params.include_visualization=true`
- knowledge retrieval only runs for explanation-style prompts or when `extra_params.include_knowledge=true`
- `ktp.trigger_training` is not part of the default pack flow and only runs on explicit training requests
- real analysis runs require `image_path` when `use_mock_backend=false`; if the caller omits it, the runtime abstains early and asks for a local image path instead of failing deep in inference
- the planner can auto-extract a local image path from natural-language messages such as `请分析河南小麦长势，影像路径是 /data/henan_wheat.tif`
- pack-flow failure ends the V2 run as `failed`

## Run

Start the main gateway host:

```bash
cd backend
python -m uvicorn apps.api_gateway.main:app --host 0.0.0.0 --port 18080
```

Open:

```text
http://127.0.0.1:18080/v2/ui
```

Recommended local split:

- `8000` keeps serving the OpenAI-compatible shared model endpoint
- `18080` serves the KTP gateway/V2 UI
- local starter scripts now also set `DATABASE_URL` to the same SQLite registry used by the gateway demo, so V2 KTP model lookup and the legacy orchestrator see the same seeded model catalog

Standalone V2 API is still available:

```bash
cd backend
python -m uvicorn v2.apps.api.main:app --host 0.0.0.0 --port 18180
```

Then use prompts such as:

- `please build a KTP report`
- `please build a KTP visualization dashboard`
- `please trigger training`
- `please run inference`
- `请用知识资料说明 NDVI 和 EVI 的区别，并给出 source`
- `请分析河南小麦长势并生成报告，影像路径是 /data/henan_wheat.tif`

## Test

Pack-focused tests:

```bash
cd backend
python -m pytest v2/tests/test_ktp_pack_smoke.py -q
```

Relevant API smoke:

```bash
python -m pytest v2/tests/test_api_smoke.py -q
```

Gateway bridge smoke:

```bash
python -m pytest tests/test_api_gateway_chat.py tests/test_api_gateway_chat_ui.py tests/test_api_gateway_detect.py -q
```

## Current Limits

- `ktp` is still marked `partial`; it is not the final pack contract
- real execution still depends on local model-registry, inference, report, confidence, visualization, and optional RAG dependencies being available
- tool metadata is still lightweight; richer permission/risk metadata lands next
- KTP pack UI renderers are still artifact-card based rather than fully specialized front-end panels
- multi-agent KTP specialist/reviewer delegation is still minimal

## Next Expansion

- enrich KTP tool metadata with risk and visibility hints
- add pack-level renderer contracts for report/confidence/visualization outputs
- connect KTP specialist agent profiles and bounded delegation into the pack path
