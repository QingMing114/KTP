/** Canonical debug client — trace / state / replay. */

import { canonicalJson } from './request'

export interface DebugTrace {
  node?: string
  event: string
  detail?: string
}

export interface DebugState {
  run?: Record<string, unknown>
  policy?: Record<string, unknown>
  visible_tools?: Array<Record<string, unknown>>
}

export interface ReplayResult {
  run_id: string
  status: string
  original_state?: Record<string, unknown>
  replayed_state?: Record<string, unknown>
  comparison?: Record<string, unknown>
}

export async function getRunTrace(runId: string): Promise<DebugTrace[]> {
  return canonicalJson<DebugTrace[]>(`/debug/runs/${encodeURIComponent(runId)}/trace`)
}

export async function getRunState(runId: string): Promise<DebugState> {
  return canonicalJson<DebugState>(`/debug/runs/${encodeURIComponent(runId)}/state`)
}

export async function replayRun(runId: string): Promise<ReplayResult> {
  return canonicalJson<ReplayResult>(`/debug/runs/${encodeURIComponent(runId)}/replay`, {
    method: 'POST',
  })
}
