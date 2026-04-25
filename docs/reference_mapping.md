# Reference Mapping

Upstream reference root:

- `references/claude_code_like/`
- upstream repository: `Ringmast4r/civil-engineering-cloud-claude-code-source-v2.1.88`
- mirrored commit: `988438af9293b198b03b8c01f97ee5556d2c74e2`

Borrowed architecture ideas:

- single product root
- single composition root
- protocol adapters at the edge
- runtime core separated from transport
- explicit tool and compatibility layers

Not adopted:

- direct runtime dependency on upstream source tree
- upstream package naming
- upstream provider-specific implementation assumptions
