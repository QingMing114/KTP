# Runbook

## Local setup

```bash
cd /home/D/liumeng/ktp_product
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
```

## Start backend

```bash
cd /home/D/liumeng/ktp_product
python scripts/start_product_backend.py
```

Default runtime data stays under:

- `var/runtime`
- `var/gateway`
- `var/artifacts`
- `var/rag`
- `var/training`
- `var/ml`

## Shared model service

Default OpenAI-compatible upstream:

- `http://127.0.0.1:8000/v1`

Override via `.env`.

