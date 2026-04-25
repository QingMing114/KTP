# Confidence Service

## Scope

`confidence_service` evaluates structured confidence from three dimensions:

- image confidence
- text/RAG confidence
- workflow confidence

It then fuses them into a final score and explanation.

## Current Method

The current implementation is heuristic, not calibrated ML.

- `image_confidence.py`: starts from model confidence and adjusts with area/polygon signal
- `text_confidence.py`: scores retrieval support using source count, average retrieval score, and summary presence
- `workflow_confidence.py`: scores workflow stability from model availability, training fallback, errors, and final status
- `fusion.py`: applies weighted averaging and produces the final label

## Why Separate It

Confidence evaluation is kept outside orchestrator nodes because it will likely evolve into:

- calibrated scoring
- model consistency checks
- multi-sample LLM confidence
- reviewer-facing explanation layers

Keeping it isolated now avoids mixing those concerns into workflow glue code.

## Output

The service returns:

- three `SubConfidenceResult` blocks
- `final_confidence`
- `final_label`
- `explanation`

This structure is already consumable by:

- orchestrator
- report service
- future front-end views

## Validation

```bash
/tmp/ktp-py311/bin/pytest tests/test_confidence_service.py tests/test_confidence_api.py
```
