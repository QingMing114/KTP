# Testing

## Full regression

```bash
cd /home/D/liumeng/ktp_product
python -m pytest -q tests v2/tests
```

## Critical suites

```bash
python -m pytest -q \
  tests/test_api_gateway_chat.py \
  tests/test_api_gateway_chat_ui.py \
  tests/test_gateway_agent_service.py \
  tests/test_openai_adapter.py \
  v2/tests/test_api_smoke.py
```

## Quality bar

- contract changes require tests
- runtime fallback regressions are blocking
- documentation changes ship with behavior changes

