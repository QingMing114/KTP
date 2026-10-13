/** Canonical run client — GET /api/product/v1/runs. */

import { canonicalJson } from './request'
import type { CanonicalAssistantPart } from './workspaceClient'

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
  assistant?: { summary?: string; parts?: CanonicalAssistantPart[] }
  input_message?: string
  created_at?: string
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
  const items: CanonicalRun[] = []
  let cursor: string | undefined
  do {
    const resp = await canonicalJson<{ items: CanonicalRun[]; has_more?: boolean; next_cursor?: string }>(
      `/conversations/${encodeURIComponent(conversationId)}/runs${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''}`,
    )
    items.push(...resp.items)
    cursor = resp.has_more ? resp.next_cursor : undefined
  } while (cursor)
  return items
}
