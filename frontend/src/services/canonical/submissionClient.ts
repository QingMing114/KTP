/** Canonical submission client — submission lifecycle + SSE event stream.
 *
 * This is the most significant module — it introduces the canonical
 * submission-based async flow, replacing the synchronous V2 send pattern.
 */

import { canonicalJson, canonicalEventStream } from './request'
import type { SubmissionSseEvent } from './request'

export interface CreateSubmissionRequest {
  message: string
  dataset_refs?: Array<{ type: 'dataset'; id: string }>
  context?: { inherit?: 'latest' | 'none'; inherit_run_id?: string }
  mode?: { interaction?: 'task' | 'chat'; delivery?: 'async' }
  preferences?: Record<string, unknown>
  client?: { name?: string; version?: string }
}

export interface SubmissionResponse {
  submission_id: string
  conversation_id: string
  run_id?: string
  status: string
  stage: string
  created_at: string
  completed_at?: string
}

export async function createSubmission(
  conversationId: string,
  req: CreateSubmissionRequest,
): Promise<SubmissionResponse> {
  return canonicalJson<SubmissionResponse>(
    `/conversations/${encodeURIComponent(conversationId)}/submissions`,
    {
      method: 'POST',
      body: JSON.stringify({
        input: {
          message: req.message,
          refs: req.dataset_refs ?? [],
        },
        context: req.context,
        mode: req.mode,
        preferences: req.preferences,
        client: req.client,
      }),
    },
  )
}

export async function getSubmission(submissionId: string): Promise<SubmissionResponse> {
  return canonicalJson<SubmissionResponse>(`/submissions/${encodeURIComponent(submissionId)}`)
}

export async function cancelSubmission(submissionId: string): Promise<SubmissionResponse> {
  return canonicalJson<SubmissionResponse>(`/submissions/${encodeURIComponent(submissionId)}/cancel`, {
    method: 'POST',
  })
}

export type SubmissionEventCallback = (event: SubmissionSseEvent) => void
export type SubmissionErrorCallback = (error: Error) => void

export function subscribeSubmissionEvents(
  submissionId: string,
  onEvent: SubmissionEventCallback,
  onError?: SubmissionErrorCallback,
  signal?: AbortSignal,
): void {
  canonicalEventStream(
    `/submissions/${encodeURIComponent(submissionId)}/events`,
    { method: 'GET' },
    onEvent,
    onError,
    signal,
  )
}

export type { SubmissionSseEvent }
