/** Canonical dataset client — CRUD /api/product/v1/datasets. */

import { canonicalJson } from './request'

export interface CanonicalDataset {
  dataset_id: string
  source: { kind: string; uri: string }
  display_name: string
  defaults?: Record<string, unknown>
  metadata?: Record<string, unknown>
  tags?: string[]
  created_at?: string
}

export interface CreateDatasetRequest {
  source: { uri: string; kind?: string }
  display_name: string
  defaults?: Record<string, unknown>
  metadata?: Record<string, unknown>
  tags?: string[]
}

export interface UpdateDatasetRequest {
  display_name?: string
  defaults?: Record<string, unknown>
  metadata?: Record<string, unknown>
  tags?: string[]
}

export async function createDataset(req: CreateDatasetRequest): Promise<CanonicalDataset> {
  return canonicalJson<CanonicalDataset>('/datasets', {
    method: 'POST',
    body: JSON.stringify({
      source: { kind: req.source.kind ?? 'local_path', uri: req.source.uri },
      display_name: req.display_name,
      defaults: req.defaults,
      metadata: req.metadata,
      tags: req.tags,
    }),
  })
}

export async function listDatasets(): Promise<CanonicalDataset[]> {
  const resp = await canonicalJson<{ items: CanonicalDataset[] }>('/datasets')
  return resp.items
}

export async function getDataset(datasetId: string): Promise<CanonicalDataset> {
  return canonicalJson<CanonicalDataset>(`/datasets/${encodeURIComponent(datasetId)}`)
}

export async function updateDataset(datasetId: string, req: UpdateDatasetRequest): Promise<CanonicalDataset> {
  return canonicalJson<CanonicalDataset>(`/datasets/${encodeURIComponent(datasetId)}`, {
    method: 'PATCH',
    body: JSON.stringify(req),
  })
}

export async function deleteDataset(datasetId: string): Promise<void> {
  await canonicalJson(`/datasets/${encodeURIComponent(datasetId)}`, { method: 'DELETE' })
}
