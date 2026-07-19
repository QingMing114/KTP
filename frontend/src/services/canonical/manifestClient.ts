/** Canonical manifest client — GET /api/product/v1/manifest. */

import { canonicalJson } from './request'

export interface CanonicalManifest {
  protocol_version: string
  features: Record<string, boolean>
  delivery_modes: string[]
  supported_preferences: string[]
  artifact_kinds: string[]
  compat_adapters: string[]
  limits: Record<string, number>
  debug_extension: boolean
}

export async function fetchManifest(): Promise<CanonicalManifest> {
  return canonicalJson<CanonicalManifest>('/manifest')
}
