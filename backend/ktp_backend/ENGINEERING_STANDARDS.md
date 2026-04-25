# KTP Backend Engineering Standards

## Change Bar

Backend changes must satisfy all of the following:

- clear module ownership
- explicit contract changes
- tests for new behavior
- documentation updates
- no hidden mock fallback in real mode

## Testing Standard

Every backend change should be covered at the smallest reasonable layer first.

1. Unit or contract tests
   For schemas, planners, tool normalization, protocol adapters, and response shaping.

2. Runtime tests
   For session lifecycle, tool flow, failure handling, and replay/trace behavior.

3. Gateway tests
   For `/chat`, `/detect`, `/v1/*`, and compatibility wrappers.

4. Full regression
   `python -m pytest -q tests v2/tests`

No backend refactor is complete without a green regression baseline.

## Documentation Standard

When behavior changes, update at least one of:

- module-local README or architecture note
- public API examples
- migration notes
- operational runbook

If a change affects operators or frontend integrators, document the failure mode and the expected recovery path.

## API Standard

- Prefer additive changes over silent breaking changes.
- If a field becomes deprecated, keep it readable until consumers migrate.
- Keep request normalization deterministic and observable.
- All failed runs must expose actionable error text.

## Tooling Standard

- Tool metadata must describe visibility, safety, artifact output, and required context.
- Dangerous or mutating tools must require an explicit approval path.
- Tool aliases and compatibility coercions must be tested.

## Runtime Standard

- The runtime must stay chat-first.
- LLM failure must be explicit, not silently replaced by fake success.
- Real task execution must use the same session and trace model as normal chat turns.

## Frontend Integration Standard

- Frontends integrate through backend contracts, not internal Python modules.
- OpenAI-compatible support is a compatibility layer, not the primary product contract.
- Frontend swaps should not require runtime rewrites.

## Release Gate

Before declaring a backend refactor complete:

- targeted tests pass
- full suite passes
- new architecture is documented
- compatibility shells still work
- migration risk is written down
