# Migration

This directory is intended to become the only runnable product backend.

Current migration rule:

- old source tree may remain for history
- new work lands in `ktp_product/`
- startup should use `app.main:app`
- compatibility routes remain, but should be treated as adapters over the product backend

