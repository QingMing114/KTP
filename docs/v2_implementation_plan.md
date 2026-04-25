# V2 Implementation Plan

## Current Stage

Implemented in this round:

- V1 snapshot docs
- V2 repository skeleton
- V2 shared schemas/settings/logging
- V2 in-memory runtime store
- V2 SQLite-backed persistent runtime store
- V2 registries for agents, tools, policies, and packs
- V2 API skeleton
- V2 runnable frontend product UI
  - chat-first product shell inspired by Claude / GPT / Gemini
  - left-side conversation rail and new-chat creation
  - central conversation thread and bottom composer
  - inline `assistant_message.parts` rendering for text, tool calls, tool results, and artifacts
  - local path chips in the composer for KTP image/task inputs
  - KTP-oriented quick prompts
  - collapsed debug drawer for run inspector, tool chain, trace, replay, and tool catalog
  - checked-in browser-ready `dist/` assets so the UI can run without Node
- V2 bounded runtime core
  - chat-first LLM planner loop with structured `AgentStepV2`
  - no deterministic direct-answer fallback on public chat requests
  - recent-session context injection plus previous task digest
  - inline assistant parts for tool calls, tool results, artifacts, status, and errors
  - Claude-style incremental run events for `assistant.delta`, `tool.*`, `artifact.available`, and terminal run states
- V2 read-side improvements
  - global run listing through `/v2/runs`
  - richer deterministic replay comparison across executor action, tools, artifacts, counters, and trace sequence
- richer tool registry metadata
  - `display_name`
  - `category`
  - `input_schema`
  - `safety_level`
  - `surface_visibility`
  - `user_confirmation_required`
  - `enabled_by_default`
  - `is_macro`
  - `capabilities`
  - `requires_context`
  - `produces_artifacts`
- V2 request context and run persistence
  - `RequestContextV2`
  - `SendMessageRequest.context`
  - `RunDetail.input_context`
  - `conversation_mode`
  - `attachments`
  - `client_capabilities`
  - `assistant_message`
- KTP pack expansion
  - `ktp.analysis_pipeline`
  - `ktp.explain_knowledge`
  - `ktp.trigger_training`
  - `workspace.search`
  - `workspace.read_file`
  - `knowledge.search_local`
- bounded KTP pack flow
  - `lookup_model_registry -> run_inference_workflow -> retrieve_knowledge? -> build_report -> evaluate_confidence -> build_visualization?`
  - explicit failure when real dependencies are unavailable
  - no automatic mock fallback on the public path
  - clarification-style response when a real analysis request omits `image_path`
  - auto-extraction of local image paths from free-form user messages
- Gateway host integration
  - V1 gateway now installs the V2 API in-process
  - `GET /v2/ui` is the main UI
  - `GET /chat/ui` redirects to `/v2/ui`
  - `POST /chat` and `POST /detect` now bridge directly into the V2 runtime
  - both routes return unified `GatewayAgentResponse`
- V2 smoke tests

## How To Run

Start the main gateway host on `18080`:

```bash
cd /home/D/liumeng/ktp
/tmp/ktp-py311/bin/python -m uvicorn apps.api_gateway.main:app --host 0.0.0.0 --port 18080
```

Main checks:

```bash
curl http://127.0.0.1:18080/health
curl http://127.0.0.1:18080/v2/tools
curl http://127.0.0.1:18080/v2/agents
curl http://127.0.0.1:18080/v2/domain-packs
```

Open the product UI:

```text
http://127.0.0.1:18080/v2/ui
```

Recommended local port split:

- `8000` for the OpenAI-compatible shared model service
- `18080` for the gateway and V2 UI

Standalone V2 API is still available for isolated work:

```bash
cd /home/D/liumeng/ktp
/tmp/ktp-py311/bin/python -m uvicorn v2.apps.api.main:app --host 0.0.0.0 --port 18180
```

Start the V2 API with persistent SQLite storage:

```bash
cd /home/D/liumeng/ktp
export V2_API_STORE_BACKEND=sqlite
export V2_API_SQLITE_PATH=/tmp/ktp_v2_runtime.sqlite3
/tmp/ktp-py311/bin/python -m uvicorn v2.apps.api.main:app --host 0.0.0.0 --port 18180
```

Standalone V2 health check:

```bash
curl http://127.0.0.1:18180/health
curl http://127.0.0.1:18180/v2/sessions
curl http://127.0.0.1:18180/v2/tools
curl http://127.0.0.1:18180/v2/agents
curl http://127.0.0.1:18180/v2/domain-packs
```

Create a session directly on the V2 API:

```bash
curl -X POST http://127.0.0.1:18180/v2/sessions \
  -H 'Content-Type: application/json' \
  -d '{"title":"Smoke Session","user_id":"demo-user"}'
```

Send a normal chat message:

```bash
curl -X POST http://127.0.0.1:18180/v2/sessions/<session_id>/messages \
  -H 'Content-Type: application/json' \
  -d '{"message":"你知道 Claude 吗？","user_id":"demo-user"}'
```

Send a knowledge-grounded message:

```bash
curl -X POST http://127.0.0.1:18180/v2/sessions/<session_id>/messages \
  -H 'Content-Type: application/json' \
  -d '{"message":"请解释 NDVI 和 EVI 的区别，并附上资料来源。","user_id":"demo-user"}'
```

Send a KTP analysis message:

```bash
curl -X POST http://127.0.0.1:18180/v2/sessions/<session_id>/messages \
  -H 'Content-Type: application/json' \
  -d '{"message":"请分析 /data/henan_wheat.tif，并给我一版结论摘要。","user_id":"demo-user","context":{"entrypoint":"v2_ui","conversation_mode":"chat","image_path":"/data/henan_wheat.tif","attachments":[{"kind":"local_path","path":"/data/henan_wheat.tif","name":"henan_wheat.tif"}]}}'
```

Inspect session state and run metadata:

```bash
curl http://127.0.0.1:18180/v2/sessions/<session_id>
curl http://127.0.0.1:18180/v2/sessions/<session_id>/state
curl http://127.0.0.1:18180/v2/sessions/<session_id>/runs
curl http://127.0.0.1:18180/v2/runs
curl http://127.0.0.1:18180/v2/runs/<run_id>
curl http://127.0.0.1:18180/v2/runs/<run_id>/trace
curl http://127.0.0.1:18180/v2/runs/<run_id>/state
curl -X POST http://127.0.0.1:18180/v2/runs/<run_id>/replay
```

Stream one run as SSE events:

```bash
curl -N -X POST http://127.0.0.1:18180/v2/sessions/<session_id>/messages/stream \
  -H 'Content-Type: application/json' \
  -H 'Accept: text/event-stream' \
  -d '{"message":"请分析河南小麦长势并生成报告，影像路径是 /data/henan_wheat.tif","context":{"entrypoint":"v2_ui","conversation_mode":"chat","image_path":"/data/henan_wheat.tif","attachments":[{"kind":"local_path","path":"/data/henan_wheat.tif","name":"henan_wheat.tif"}],"extra_params":{}}}'
```

Replay now performs a deterministic dry run:

- it re-executes the bounded runtime
- it compares original vs replayed outputs plus deeper execution metadata
- it returns mismatch field names when replay diverges
- it does not write new messages into the session
- it does not persist a new run

Frontend skeleton TypeScript check:

```bash
cd /home/D/liumeng/ktp/v2/apps/web
npm install
npm run check
```

Frontend demo without Node:

```bash
cd /home/D/liumeng/ktp/v2/apps/web
python -m http.server 4173
```

## How To Test

Run the main gateway/V2 regression subset:

```bash
cd /home/D/liumeng/ktp
/tmp/ktp-py311/bin/pytest \
  v2/tests/test_api_smoke.py \
  v2/tests/test_registry_smoke.py \
  v2/tests/test_ktp_pack_smoke.py \
  tests/test_api_gateway_chat.py \
  tests/test_api_gateway_chat_ui.py \
  tests/test_api_gateway_detect.py \
  -q
```

## Next Stages

1. Enrich tool metadata and permission/risk policy for KTP and non-KTP tools
2. Add richer session memory and fact persistence on top of `input_context`
3. Add reviewer hints and specialist delegation chains on top of the current bounded multi-tool runtime
4. Expand pack-specific renderer contracts beyond generic artifact cards

## Documentation Discipline

Every new V2 module must update:

- [docs/system_manual.md](/home/D/liumeng/ktp/docs/system_manual.md)
- this file
- the relevant API/frontend/pack docs
