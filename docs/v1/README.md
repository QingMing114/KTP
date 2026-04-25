# V1 Snapshot

## Purpose

This directory preserves the current KTP V1 system boundary as a readable snapshot while V2 is developed on the main line.

V1 remains:

- the bounded remote-sensing platform
- FastAPI gateway + LangGraph orchestrator
- service-oriented inference / training / RAG / report / confidence / visualization
- trustworthy production path oriented around `/detect`

## Source of Truth

For the live V1 technical description, use:

- [../system_manual.md](/home/D/liumeng/ktp/docs/system_manual.md)
- [../workflow.md](/home/D/liumeng/ktp/docs/workflow.md)
- [../integration.md](/home/D/liumeng/ktp/docs/integration.md)
- [../mvp_runbook.md](/home/D/liumeng/ktp/docs/mvp_runbook.md)

## Freeze Notes

- V1 is treated as frozen from an architecture perspective.
- Only critical fixes should land against a dedicated V1 maintenance line.
- New platform/runtime work belongs to V2.

## V1 Validation Commands

Core V1 gateway/orchestrator workflow:

```bash
cd /home/D/liumeng/ktp
/tmp/ktp-py311/bin/python scripts/start_gateway_qwen_local.py --port 18080
```

Health:

```bash
curl http://127.0.0.1:18080/health
curl http://127.0.0.1:18080/services/health
```

Regression:

```bash
/tmp/ktp-py311/bin/pytest tests/integration tests/e2e
```
