# API

Primary product protocols:

- `/v2/*`
  Internal and product-facing session/run/runtime protocol
- `/chat`
  Gateway compatibility chat entry
- `/detect`
  Gateway compatibility task entry
- `/v1/models`
- `/v1/chat/completions`
  OpenAI-compatible adapter for LibreChat integration

Artifacts:

- `/v2/artifacts/open?path=...`

This product root keeps `/v2` as the primary runtime protocol and `/v1` as the frontend compatibility protocol.

