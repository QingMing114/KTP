# Report Service

## Scope

`report_service` renders structured workflow outputs into a standalone HTML report.

Current responsibilities:

- receive structured report input
- render HTML through Jinja2 templates
- persist the report to local disk
- return structured metadata for orchestrator and future front-end use

It does not rerun inference, retrieval, or confidence evaluation.

## Main Files

- `services/report_service/builder.py`: builds report context and renders Jinja2 templates
- `services/report_service/service.py`: handles generation, persistence, and structured responses
- `services/report_service/charts.py`: returns lightweight chart-ready context data
- `services/report_service/templates/`: HTML templates and partial sections
- `services/report_service/client.py`: local adapter currently used by the orchestrator

## Input / Output

Input is `ReportRequest`, which carries:

- task metadata
- summary text
- inference result
- RAG result
- optional confidence result

Output is `ReportResponse`, which includes:

- `report_id`
- `report_path`
- optional embedded HTML
- generated section list

## Why Separate It

This service is separate so template rendering stays out of:

- LangGraph nodes
- agent prompts
- gateway route handlers

That keeps rendering replaceable for future:

- front-end rendering
- PDF export
- richer chart generation

## Validation

```bash
/tmp/ktp-py311/bin/pytest tests/test_report_builder.py tests/test_report_api.py
```
