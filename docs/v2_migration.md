# V2 Migration Notes

## Intended Migration Path

V1 and V2 are separated conceptually:

- V1 remains the external host shell and compatibility surface
- V2 is the new runtime/platform baseline
- the public KTP single-agent path now runs through the V1 gateway host with the V2 runtime mounted in-process

## Short-Term Policy

- do not remove existing V1 code yet
- route new mainline `/chat`, `/detect`, and `/v2/ui` traffic into V2
- keep old orchestrator/chat-runtime code as transition-era code until pack/runtime contracts and operational playbooks are stable
- preserve explicit failure behavior when real dependencies are unavailable; do not reintroduce silent automatic mock fallback on the public path

## Migration Milestones

1. V2 runtime works independently
2. V2 web UI works independently
3. KTP pack exposes current domain capabilities through V2 tools
4. `/chat` compatibility shim translates to V2
5. `/detect` compatibility shim translates to V2
6. Gateway serves V2 UI as the main human-facing entrypoint

## Current Migration Status

- milestone 1: reached
- milestone 2: reached
- milestone 3: reached for the first bounded KTP pack flow
  - `ktp.retrieve_knowledge` is live
  - model lookup, inference, training, report, confidence, and visualization are exposed as bounded V2 pack tools
  - KTP requests can now run as a bounded multi-tool `pack_flow`
- milestone 4: reached
  - `POST /chat` now bridges directly into the V2 runtime
  - `conversation_id` is reused as the V2 `session_id`
  - `/chat` returns the unified `GatewayAgentResponse`
- milestone 5: reached
  - `POST /detect` now bridges directly into the V2 runtime
  - each detect request creates a fresh V2 session
  - `/detect` returns the unified `GatewayAgentResponse`
- milestone 6: reached
  - `GET /v2/ui` is the main product UI
  - `GET /chat/ui` now redirects to `/v2/ui`

## Current Runtime Policy

- public gateway host should stay separate from the model host; the recommended local default is `18080`
- gateway-mounted V2 runtime is the main execution path
- standalone `18180` V2 API remains available for isolated testing
- `8000` is reserved by default for the OpenAI-compatible shared model endpoint
- real dependency failures surface as run failures
- `ktp.trigger_training` is explicit-only and is not auto-triggered from normal chat/detect flows
- mock execution is opt-in through request context and is not automatic on the public path

## Git Freeze Note

The implementation plan assumes a future V1 maintenance branch and tag.
From the current workspace session, the directory is not attached to a discoverable Git repository root, so branch/tag creation is not performed here.
