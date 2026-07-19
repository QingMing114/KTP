/** Canonical run client — GET /api/product/v1/runs. */

import { canonicalJson } from './request'

export interface CanonicalArtifactRef {
  artifact_id: string
  kind: string
  title: string
  view_url: string
  download_url?: string
}

export interface CanonicalRun {
  run_id: string
  conversation_id: string
  status: string
  assistant?: { summary?: string; parts?: Array<{ type: string; text?: string; artifact_id?: string }> }
  artifacts?: CanonicalArtifactRef[]
  workflow_summary?: string
  termination_reason?: string
}

export interface PaginatedRuns {
  items: CanonicalRun[]
  next_cursor?: string
  has_more?: boolean
}

export async function getRun(runId: string): Promise<CanonicalRun> {
  return canonicalJson<CanonicalRun>(`/runs/${encodeURIComponent(runId)}`)
}

export async function listRuns(cursor?: string): Promise<PaginatedRuns> {
  const qs = cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''
  return canonicalJson<PaginatedRuns>(`/runs${qs}`)
}

export async function getConversationRuns(conversationId: string): Promise<CanonicalRun[]> {
  const resp = await canonicalJson<{ items: CanonicalRun[]; has_more?: boolean }>(
    `/conversations/${encodeURIComponent(conversationId)}/runs`,
  )
  return resp.items
}
