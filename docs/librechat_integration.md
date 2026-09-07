# LibreChat Integration

Use `ktp_product` as a custom OpenAI-compatible provider behind a single public agent surface.

## What LibreChat Sees

LibreChat should only see one endpoint and one model:

- base URL: `http://127.0.0.1:18080/v1`
- model id: `ktp-multi-agent`

The backend keeps specialization internal:

- public entry agent: `ktp_frontdesk`
- internal specialists stay inside backend delegation

## Supported Provider Behavior

Current `/v1` support in `ktp_product`:

- `GET /v1/models`
- `POST /v1/chat/completions`
- multi-turn history mapping
- SSE streaming
- local attachment mapping from OpenAI-style content parts
- dataset reference mapping from `dataset:ds_xxx`, `metadata.dataset_id`, or `input_file.file_id=ds_xxx`
- artifact links rewritten to clickable backend routes

## Recommended LibreChat Config

Use the example file:

- `integrations/librechat/librechat.yaml.example`

Typical environment values:

```bash
KTP_PRODUCT_API_KEY=sk-ktp-local
KTP_PRODUCT_BASE_URL=http://127.0.0.1:18080/v1
```

If LibreChat runs on Windows while `ktp_product` runs on Ubuntu/Linux, use the Ubuntu host IP:

```bash
KTP_PRODUCT_API_KEY=sk-ktp-local
KTP_PRODUCT_BASE_URL=http://<UBUNTU_HOST_IP>:18080/v1
```

Do not use `127.0.0.1` from Windows unless the backend is also on that same Windows machine.

If LibreChat runs in Docker on the same Windows host as the backend, use:

```bash
KTP_PRODUCT_BASE_URL=http://host.docker.internal:18080/v1
```

If both services run inside the same Docker network, use the backend service name instead.

## Startup

Start the backend:

```bash
cd backend
python scripts/start_product_backend.py
```

Find the Ubuntu host IP for Windows clients:

```bash
hostname -I | awk '{print $1}'
```

Optional provider smoke check:

```bash
cd backend
python scripts/check_librechat_provider.py --api-key sk-ktp-local
```

Optional dataset-backed async workflow check:

```bash
cd backend
python scripts/check_dataset_async_flow.py \
  --api-key sk-ktp-local \
  --source-uri ./var/runtime/baldness_real_flow/inputs/req-baldness-real-001_crop.tif \
  --message "请对这张头皮多光谱影像做真实斑秃识别，并生成分析报告、置信度说明和可视化。" \
  --region scalp \
  --crop-type hair \
  --task-type baldness_detection
```

The dataset registration step now persists default task context. If you register with
`--region/--crop-type/--task-type`, later async submissions can rely on `dataset_id`
alone and do not need to repeat those fields on every request.

For `/v1/chat/completions`, the same dataset-backed flow can be triggered in three ways:

1. Put `dataset:ds_xxx` in the user message text.
2. Send `metadata.dataset_id=ds_xxx`.
3. Send an OpenAI-style content part such as:

```json
{
  "type": "input_file",
  "file_id": "ds_xxx"
}
```

If the registered dataset already stores `region/crop_type/task_type`, the frontend only needs to provide the dataset reference.

For LibreChat, prefer the text form first because it matches the normal composer UX best:

```text
请分析 dataset:ds_xxx，并生成报告、置信度说明和可视化。
```

The backend will resolve the dataset record and inherit stored `region/crop_type/task_type` automatically.

If you want a CLI-style smoke check that mimics LibreChat's `/v1` usage:

```bash
cd backend
python scripts/check_openai_dataset_chat.py \
  --client-name librechat \
  --ref-mode text \
  --api-key sk-ktp-local \
  --source-uri ./var/runtime/baldness_real_flow/inputs/req-baldness-real-001_crop.tif \
  --message "请对这张头皮多光谱影像做真实斑秃识别，并生成分析报告、置信度说明和可视化。" \
  --region scalp \
  --crop-type hair \
  --task-type baldness_detection
```

Quick Windows-side verification in PowerShell:

```powershell
$headers = @{ Authorization = "Bearer sk-ktp-local" }
Invoke-RestMethod -Uri "http://<UBUNTU_HOST_IP>:18080/v1/models" -Headers $headers
```

LibreChat should be configured with:

- `baseURL=http://<UBUNTU_HOST_IP>:18080/v1`
- `apiKey=sk-ktp-local`
- `model=ktp-multi-agent`

Planner-heavy turns can take longer than simple chat turns. The backend defaults are now:

- `AGENT_LLM_OPENAI_DIRECT_TIMEOUT_SECONDS=45`
- `AGENT_LLM_OPENAI_STRUCTURED_TIMEOUT_SECONDS=120`

If your upstream shared LLM is still overloaded, increase `AGENT_LLM_OPENAI_STRUCTURED_TIMEOUT_SECONDS` further in the backend `.env` and restart the backend.

## Notes

- `/v1` is a compatibility layer over the chat-first backend runtime
- richer runtime inspection remains available through `/v2/*`
- artifact links are returned through `/v2/artifacts/open`
- frontend should not orchestrate internal specialist agents directly
- `/v1` now enforces bearer auth when `KTP_PRODUCT_API_KEY` is configured

## Known Limits

- this is OpenAI-compatible, not full OpenAI feature parity
- approval workflow is still backend-internal and partial
- provider metadata is intentionally minimal: keep the frontend focused on one public model
