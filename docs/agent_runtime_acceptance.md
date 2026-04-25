# Agent Runtime Acceptance

## Goal

This document defines how to validate that the bounded `/chat` self-scheduling runtime is ready for practical use.

## Preconditions

- Gateway runtime is enabled:
  - `API_GATEWAY_CHAT_AGENT_RUNTIME_ENABLED=true`
- Optional compare mode is enabled when you want side-by-side observation:
  - `API_GATEWAY_CHAT_AGENT_SHADOW_COMPARE_ENABLED=true`
- Legacy emergency fallback can be disabled for stricter validation:
  - `API_GATEWAY_CHAT_AGENT_LEGACY_FALLBACK_ENABLED=false`
- Retry budget is explicitly set for the validation run:
  - `API_GATEWAY_CHAT_AGENT_MAX_REPLANS=2`

## Required Validation Steps

### 0. One-command acceptance runner

Run:

```bash
python scripts/run_agent_runtime_acceptance.py
```

This executes:

- the bounded runtime regression pytest suite
- the in-process `/chat` evaluation script

If you only want the evaluation phase:

```bash
python scripts/run_agent_runtime_acceptance.py --skip-pytest
```

### 1. Unit and integration regression

Run:

```bash
pytest \
  tests/test_tool_registry.py \
  tests/test_chat_runtime_scaffold.py \
  tests/test_chat_runtime_phase2.py \
  tests/test_chat_runtime_adapter.py \
  tests/test_orchestrator_nodes.py \
  tests/test_agent_llm_provider.py \
  tests/test_planner_agent.py \
  tests/test_chat_service.py \
  tests/test_chat_runtime_eval.py \
  tests/test_evaluate_chat_runtime_script.py -q
```

Expected:

- all tests pass

### 2. In-process bounded runtime evaluation

Run:

```bash
python scripts/evaluate_chat_runtime.py
```

Expected:

- JSON output
- `failed == 0`

### 3. Live gateway evaluation

Start the gateway:

```bash
export API_GATEWAY_CHAT_AGENT_RUNTIME_ENABLED=true
export API_GATEWAY_CHAT_AGENT_SHADOW_COMPARE_ENABLED=true
export API_GATEWAY_CHAT_AGENT_LEGACY_FALLBACK_ENABLED=false
export API_GATEWAY_CHAT_AGENT_MAX_REPLANS=2
/tmp/ktp-py311/bin/python scripts/start_gateway_qwen_local.py --port 18080
```

Then run:

```bash
python scripts/evaluate_chat_runtime.py --base-url http://127.0.0.1:18080
```

Expected:

- JSON output
- `failed == 0`

### 4. Manual workflow path spot-check

Send:

```bash
curl -X POST http://127.0.0.1:18080/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "request_id": "acceptance-workflow-001",
    "user_id": "acceptance-user",
    "message": "请分析河北省小麦病害情况，并生成报告和置信度说明。",
    "mode": "agent",
    "extra_params": {}
  }'
```

Expected:

- runtime-first route
- `mode` resolves to workflow-backed response
- conversation context contains:
  - `agent_audit`
  - `runtime_trace`
- if compare mode is enabled:
  - `shadow_compare`

### 5. Manual direct-answer spot-check

Send:

```bash
curl -X POST http://127.0.0.1:18080/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "request_id": "acceptance-direct-001",
    "user_id": "acceptance-user",
    "message": "NDVI 和 EVI 有什么区别？",
    "mode": "agent",
    "extra_params": {}
  }'
```

Expected:

- runtime-first route
- no fake workflow result
- if compare mode is enabled, compare metadata is present

## Acceptance Criteria

The bounded chat runtime can be considered ready when:

- regression tests pass
- evaluation script passes in-process
- evaluation script passes against the live gateway
- workflow and direct-answer spot-checks both behave as expected
- persisted turn context contains `agent_audit`
- no uncontrolled legacy routing occurs when fallback is disabled
