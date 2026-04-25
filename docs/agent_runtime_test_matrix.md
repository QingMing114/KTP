# Agent Runtime Test Matrix

## Scope

This matrix treats the bounded `/chat` self-scheduling runtime like a software product under test.

Coverage goals:

- routing correctness
- tool selection correctness
- workflow compatibility
- explicit mode compatibility
- normalization coverage
- fallback behavior
- retry / replan behavior
- trace / audit visibility
- conversation isolation
- acceptance readiness

## Legend

- `AUTO`: can be driven by evaluation scripts or pytest
- `MANUAL`: requires a live gateway, failure injection, or multi-turn setup
- `P0`: release-blocking
- `P1`: important
- `P2`: useful hardening

## Matrix

| ID | Priority | Type | Category | Scenario | Preconditions | Expected Result |
|---|---|---|---|---|---|---|
| AR-001 | P0 | AUTO | Routing | Agent general knowledge question | runtime enabled | mode=`agent`, route contains `chat_graph:direct_answer` |
| AR-002 | P0 | AUTO | Routing | Auto general knowledge question | runtime enabled | `auto` also resolves through runtime-first direct answer |
| AR-003 | P0 | AUTO | Workflow | Agent workflow + report + confidence | runtime enabled | mode=`workflow`, route contains `chat_graph:workflow` |
| AR-004 | P0 | AUTO | Workflow | Auto workflow + report + confidence | runtime enabled | `auto` self-schedules to workflow |
| AR-005 | P1 | AUTO | Workflow | Workflow request with visualization wording | runtime enabled | still routes to workflow |
| AR-006 | P0 | AUTO | Explicit mode | Explicit `qa` compatibility | none | mode=`qa`, success true |
| AR-007 | P0 | AUTO | Explicit mode | Explicit `workflow` compatibility | none | mode=`workflow` |
| AR-008 | P0 | AUTO | RAG | Chinese grounded question with “知识库/资料/来源” | runtime enabled | mode=`qa`, route contains `chat_graph:rag_qa` |
| AR-009 | P1 | AUTO | RAG | English grounded question with `sources` | runtime enabled | mode=`qa`, route contains `chat_graph:rag_qa` |
| AR-010 | P1 | AUTO | Normalization | 河北 + 小麦 | runtime enabled | workflow route |
| AR-011 | P1 | AUTO | Normalization | 河南 + 水稻 | runtime enabled | workflow route |
| AR-012 | P1 | AUTO | Task type | Yield estimation wording | runtime enabled | workflow route |
| AR-013 | P1 | AUTO | Task type | LAI inversion wording | runtime enabled | workflow route |
| AR-014 | P0 | MANUAL | Shadow compare | runtime result and legacy comparison both recorded | `API_GATEWAY_CHAT_AGENT_SHADOW_COMPARE_ENABLED=true` | `shadow_compare` present; comparison flags present |
| AR-015 | P0 | MANUAL | Fallback | Legacy fallback disabled after runtime failure | `API_GATEWAY_CHAT_AGENT_LEGACY_FALLBACK_ENABLED=false` | structured agent failure, no silent legacy answer |
| AR-016 | P1 | MANUAL | Fallback | Legacy fallback enabled after runtime failure | fallback enabled | answer returns from legacy path; `agent_audit.path=legacy_fallback` |
| AR-017 | P1 | MANUAL | Retry budget | Max replans honored | `API_GATEWAY_CHAT_AGENT_MAX_REPLANS=2` | `replan_count <= max_replans`, bounded stop |
| AR-018 | P1 | MANUAL | Validation | Incomplete workflow artifact triggers validation failure | failing/incomplete workflow stub | bounded replan or abstain |
| AR-019 | P1 | MANUAL | Traceability | Workflow request yields full runtime trace | runtime enabled | trace contains planner/executor/tool/validate/finalize |
| AR-020 | P0 | MANUAL | Conversation | Conversation isolation by `(user_id, conversation_id)` | two users, same conversation id | no cross-user leakage |
| AR-021 | P1 | MANUAL | Conversation | Workflow follow-up inherits prior context | same conversation id | follow-up uses previous workflow context |
| AR-022 | P1 | MANUAL | Conversation | QA follow-up inherits prior retrieval context | same conversation id | query is augmented from prior QA turn |
| AR-023 | P2 | MANUAL | Audit | `agent_audit` is compact and readable | runtime enabled | compact audit summary present in turn context |
| AR-024 | P2 | MANUAL | Compare | Shadow compare mismatch signals reflect divergence | shadow compare enabled + induced divergence | mismatch booleans flip as expected |
| AR-025 | P0 | AUTO | Acceptance | One-command acceptance runner | none | `python scripts/run_agent_runtime_acceptance.py` succeeds |

## Automated Assets

### Minimal regression set

- [tests/data/chat_runtime_eval_cases.json](/home/D/liumeng/ktp/tests/data/chat_runtime_eval_cases.json)

### Broader regression set

- [tests/data/chat_runtime_eval_cases_full.json](/home/D/liumeng/ktp/tests/data/chat_runtime_eval_cases_full.json)

Run the broader set:

```bash
python scripts/evaluate_chat_runtime.py --cases tests/data/chat_runtime_eval_cases_full.json
```

## Manual Test Guidance

For manual cases, use the live gateway with:

```bash
export API_GATEWAY_CHAT_AGENT_RUNTIME_ENABLED=true
export API_GATEWAY_CHAT_AGENT_SHADOW_COMPARE_ENABLED=true
export API_GATEWAY_CHAT_AGENT_LEGACY_FALLBACK_ENABLED=false
export API_GATEWAY_CHAT_AGENT_MAX_REPLANS=2
/tmp/ktp-py311/bin/python scripts/start_gateway_qwen_local.py --port 18080
```

Then validate:

- live eval:

```bash
python scripts/evaluate_chat_runtime.py --base-url http://127.0.0.1:18080 --cases tests/data/chat_runtime_eval_cases_full.json
```

- one-command acceptance:

```bash
python scripts/run_agent_runtime_acceptance.py
```

## Recommendation

For regular regression:

1. run the automated broader set
2. run the acceptance runner
3. spot-check at least:
   - one workflow case
   - one direct-answer case
   - one shadow-compare case
   - one fallback-disabled case
