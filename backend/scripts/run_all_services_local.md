# Run All Services Local

## Minimal Local Order

1. Prepare environment
2. Start the local Qwen gateway runtime
4. Send a demo `/detect` request

## Commands

```bash
cp .env.example .env
/tmp/ktp-py311/bin/pip install -e .[dev]
/tmp/ktp-py311/bin/python scripts/start_gateway_qwen_local.py --port 18080
```

In another shell:

```bash
curl -X POST http://127.0.0.1:18080/detect \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "req-manual-001",
    "user_query": "Assess wheat health in Henan and provide a report with confidence.",
    "region": "henan",
    "crop_type": "wheat",
    "task_type": "crop_health_detection",
    "use_mock": true,
    "extra_params": {}
  }'
```

For the standalone real baldness workflow demo:

```bash
/tmp/ktp-py311/bin/python scripts/demo_baldness_real_flow.py
```

## Optional Health Checks

```bash
curl http://127.0.0.1:18080/health
curl http://127.0.0.1:18080/services/health
```
