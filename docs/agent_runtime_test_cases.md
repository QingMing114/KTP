# Agent Runtime Test Cases

## Purpose

This document collects complete test cases for the bounded `/chat` self-scheduling runtime, organized like a software-test matrix.

The cases are split into two groups:

- automated cases: runnable through the regression script
- manual cases: require live gateway state, failure injection, or multi-turn observation

## Automated Case File

Primary files:

- minimal seed set:
  - [tests/data/chat_runtime_eval_cases.json](../tests/data/chat_runtime_eval_cases.json)
- broader regression set:
  - [tests/data/chat_runtime_eval_cases_full.json](../tests/data/chat_runtime_eval_cases_full.json)

Run the broad set:

```bash
python scripts/evaluate_chat_runtime.py --cases tests/data/chat_runtime_eval_cases_full.json
```

## Automated Test Matrix

### 1. Routing / direct answer

Case: `agent_direct_general_knowledge`

- input:
  - `mode=agent`
  - message: `NDVI 和 EVI 有什么区别？`
- goal:
  - verify agent runtime chooses direct answer
- expected:
  - `mode=agent`
  - `route_reason` contains `chat_graph:direct_answer`
  - `success=true`

Case: `auto_direct_general_knowledge`

- input:
  - `mode=auto`
  - message: `请介绍一下 VSCode 是什么。`
- goal:
  - verify auto mode is runtime-first, not gateway pre-routing
- expected:
  - `mode=agent`
  - `route_reason` contains `chat_graph:direct_answer`

### 2. Workflow routing

Case: `agent_workflow_report_confidence`

- input:
  - `mode=agent`
  - message: `请分析河北省小麦病害情况，并生成报告和置信度说明。`
- goal:
  - verify planner chooses workflow tool
- expected:
  - `mode=workflow`
  - `route_reason` contains `chat_graph:workflow`

Case: `auto_workflow_report_confidence`

- input:
  - `mode=auto`
  - same workflow message
- goal:
  - verify runtime-first auto mode still reaches workflow
- expected:
  - `mode=workflow`

### 3. Explicit compatibility

Case: `explicit_qa_case`

- input:
  - `mode=qa`
- goal:
  - verify explicit qa still works
- expected:
  - `mode=qa`
  - `success=true`

Case: `explicit_workflow_case`

- input:
  - `mode=workflow`
- goal:
  - verify explicit workflow still works
- expected:
  - `mode=workflow`

### 4. RAG tool selection

Case: `agent_rag_grounded_question`

- input:
  - `mode=agent`
  - message explicitly mentions `知识库资料` and `来源`
- goal:
  - verify runtime chooses RAG tool instead of direct answer
- expected:
  - `mode=qa`
  - `route_reason` contains `chat_graph:rag_qa`

### 5. Entity normalization

Case: `region_crop_normalization_workflow`

- input:
  - `mode=agent`
  - message uses `河北` and `小麦`
- goal:
  - verify planner extracts enough structure to route to workflow
- expected:
  - `mode=workflow`

## Manual Test Matrix

### 6. Shadow compare correctness

Setup:

```bash
export API_GATEWAY_CHAT_AGENT_SHADOW_COMPARE_ENABLED=true
```

Action:

- send one direct-answer request
- inspect persisted turn context

Expected:

- `context.shadow_compare` exists
- `context.shadow_compare.comparison` includes:
  - `mode_match`
  - `success_match`
  - `route_reason_match`
- `context.agent_audit.shadow_compare_enabled=true`

### 7. Legacy fallback disabled

Setup:

```bash
export API_GATEWAY_CHAT_AGENT_LEGACY_FALLBACK_ENABLED=false
```

Action:

- induce runtime failure
- send one agent request

Expected:

- no legacy answer is returned
- response is structured failure
- `route_reason` contains `legacy_disabled`
- `context.agent_audit.legacy_fallback_enabled=false`

### 8. Replan budget honored

Setup:

```bash
export API_GATEWAY_CHAT_AGENT_MAX_REPLANS=2
```

Action:

- induce one invalid tool observation or failing workflow
- inspect runtime context

Expected:

- `replan_count <= max_replans`
- final failure is bounded
- no unbounded loop

### 9. Runtime trace completeness

Action:

- send one workflow-style request

Expected:

- `runtime_trace` contains, in bounded order:
  - `load_tool_registry`
  - `planner`
  - `executor`
  - `tool_dispatch`
  - `validate_observation`
  - `finalize_response`

### 10. Multi-turn continuity

Action:

1. ask a workflow question
2. continue with a short follow-up using the same `conversation_id`

Expected:

- second turn reuses prior context
- conversation store isolates by `(user_id, conversation_id)`
- no cross-user leakage

## Recommended Execution Order

1. Run the broad in-process regression set:

```bash
python scripts/evaluate_chat_runtime.py --cases tests/data/chat_runtime_eval_cases_full.json
```

2. Run the full acceptance runner:

```bash
python scripts/run_agent_runtime_acceptance.py
```

3. Start the live gateway and rerun the same broad set against `--base-url`.
