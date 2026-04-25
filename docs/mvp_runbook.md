# MVP Runbook

## Environment

```bash
cp .env.example .env
/tmp/ktp-py311/bin/pip install -e .[dev]
```

Recommended local overrides:

```bash
export ORCHESTRATOR_DATABASE_URL=sqlite:///./demo_registry.db
export VECTORSTORE_DIR=/tmp/ktp_rag_store
export REPORT_OUTPUT_DIR=/tmp/ktp_reports
export MASK_OUTPUT_DIR=/tmp/ktp_masks
export ORCHESTRATOR_INFERENCE_MASK_OUTPUT_DIR=/tmp/ktp_masks
export VISUALIZATION_OUTPUT_DIR=/tmp/ktp_visualizations
```

Default shared planner/executor model:

```bash
export AGENT_LLM_BACKEND=openai_compatible
export AGENT_LLM_OPENAI_API_BASE=http://127.0.0.1:8000/v1
export AGENT_LLM_OPENAI_API_KEY=sk-dummy
export AGENT_LLM_OPENAI_MODEL_NAME=/home/D/yuanshuai/.cache/modelscope/hub/models/Qwen/Qwen3.5-27B
export AGENT_LLM_CHAT_MAX_NEW_TOKENS=256
export AGENT_LLM_STRUCTURED_MAX_NEW_TOKENS=384
```

Optional dedicated interactive upstream:

```bash
bash scripts/start_interactive_qwen3_vllm.sh
export AGENT_LLM_OPENAI_API_BASE=http://127.0.0.1:8001/v1
```

If chat/runtime traffic shares the same `8000` upstream with batch jobs, expect overload and timeout failures under contention.

## Start Local Qwen Gateway

```bash
/tmp/ktp-py311/bin/python scripts/start_gateway_qwen_local.py --port 18080
```

This command:

- prepares a local SQLite registry
- prepares local RAG, report, mask, and visualization directories
- seeds one ready demo model
- seeds one local knowledge document
- enables the shared Qwen planner/executor backend
- starts the API gateway on `18080`

## Run Demo Request

```bash
curl -X POST http://127.0.0.1:18080/detect \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "req-demo-001",
    "user_query": "Assess wheat health in Henan and provide a report with confidence.",
    "region": "henan",
    "crop_type": "wheat",
    "task_type": "crop_health_detection",
    "use_mock": true,
    "extra_params": {}
  }'
```

Expected result:

- `success=true`
- `workflow_status=completed`
- `inference_result`, `rag_result`, `report_result`, `confidence_result`, and `visualization_result` all present

Open the dashboard:

```bash
curl http://127.0.0.1:18080/workflow/req-demo-001/visualization
```

## Run Real Baldness Demo

```bash
/tmp/ktp-py311/bin/python scripts/demo_baldness_real_flow.py
```

This path:

- crops a real multispectral sample from the external baldness dataset
- registers the real RF model in a local SQLite registry
- ingests one baldness interpretation document into the local RAG store
- runs `use_mock=false`
- writes the final structured response to `/tmp/ktp_baldness_real_flow/response.json`
- writes the workflow dashboard under `/tmp/ktp_baldness_real_flow/visualizations/<request_id>/dashboard.html`

## Start Gateway Manually

```bash
/tmp/ktp-py311/bin/python -m uvicorn apps.api_gateway.main:app --host 0.0.0.0 --port 18080
```

## Check Health

```bash
curl http://127.0.0.1:18080/health
curl http://127.0.0.1:18080/services/health
```

Example detect request:

The direct manual `uvicorn` route is still available, but then you must prepare all runtime env vars and seed assets yourself. The local starter script is the recommended path.

## Run Integration Tests

```bash
/tmp/ktp-py311/bin/pytest tests/integration tests/e2e
```
