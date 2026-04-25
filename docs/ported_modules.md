# Ported Modules

This file tracks modules whose implementation or structure was influenced by the upstream Claude-like reference.

Current status:

- No direct runtime imports from `references/`
- Runtime code remains in local product modules
- Architecture and compatibility layering were aligned at the system-shape level
- Upstream mirror is available at `references/claude_code_like/`

Future entries should record:

- upstream path
- upstream purpose
- local destination
- whether the result was clean-room rewritten or selectively ported
