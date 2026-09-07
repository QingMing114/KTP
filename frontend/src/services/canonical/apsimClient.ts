import { buildUrl, getApiKey, getJwtToken } from '../api'
import { canonicalJson } from './request'
import type { CanonicalArtifact } from './artifactClient'

export interface ApsimYieldReportRequest {
  mode: 'demo' | 'simulation'
  crop_type: 'wheat' | 'maize' | 'soybean'
  region: string
  start_year: number
  end_year: number
  cultivar?: string
  sowing_date?: string
}

export interface ApsimYieldReportResponse {
  status: 'success'
  mode: 'demo' | 'simulation'
  summary: string
  metrics: {
    estimated_yield_t_ha: number
    peak_lai: number
    max_biomass_g_m2: number
    simulation_days: number
  }
  parameters: Record<string, unknown>
  artifact: CanonicalArtifact
}

export function createApsimYieldReport(
  request: ApsimYieldReportRequest,
): Promise<ApsimYieldReportResponse> {
  const payload = {
    ...request,
    cultivar: request.cultivar?.trim() || undefined,
    sowing_date: request.sowing_date?.trim() || undefined,
  }
  return canonicalJson<ApsimYieldReportResponse>('/apsim/yield-reports', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

/** Fetch protected report HTML and return a browser-local URL for iframe/open. */
export async function loadApsimReportObjectUrl(viewUrl: string): Promise<string> {
  const token = getJwtToken() || getApiKey()
  const response = await fetch(buildUrl(viewUrl), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) throw new Error(`报告加载失败（HTTP ${response.status}）`)
  return URL.createObjectURL(await response.blob())
}
