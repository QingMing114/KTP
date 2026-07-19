/** Canonical artifact client — GET /api/product/v1/artifacts. */

import { canonicalJson } from './request'
import { getApiBaseUrl } from '../api'

export interface CanonicalArtifact {
  artifact_id: string
  kind: string
  title: string
  view_url: string
  download_url?: string
  content?: string
}

export async function getArtifact(artifactId: string): Promise<CanonicalArtifact> {
  return canonicalJson<CanonicalArtifact>(`/artifacts/${encodeURIComponent(artifactId)}`)
}

export async function getArtifactContent(artifactId: string): Promise<string> {
  const resp = await canonicalJson<{ content: string }>(
    `/artifacts/${encodeURIComponent(artifactId)}/content`,
  )
  return resp.content
}

/** Return the absolute URL for rendering an HTML artifact in an iframe. */
export function getArtifactRenderUrl(artifactId: string): string {
  const base = getApiBaseUrl()
  const path = `/api/product/v1/artifacts/${encodeURIComponent(artifactId)}/render`
  return base ? new URL(path, base.replace(/\/+$/, '') + '/').toString() : path
}
