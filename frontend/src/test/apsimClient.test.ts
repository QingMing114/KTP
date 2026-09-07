// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  createApsimYieldReport,
  loadApsimReportObjectUrl,
} from '../services/canonical/apsimClient'

afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})

describe('APSIM canonical client', () => {
  it('posts a deterministic yield-report request', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      status: 'success',
      mode: 'demo',
      summary: 'done',
      metrics: {
        estimated_yield_t_ha: 6.51,
        peak_lai: 5.591,
        max_biomass_g_m2: 1399.6,
        simulation_days: 241,
      },
      parameters: {},
      artifact: {
        artifact_id: 'art_demo',
        kind: 'apsim_report',
        title: 'APSIM report',
        view_url: '/api/product/v1/artifacts/art_demo/render',
      },
    }), { status: 200 }))

    const response = await createApsimYieldReport({
      mode: 'demo',
      crop_type: 'wheat',
      region: 'henan',
      start_year: 2024,
      end_year: 2025,
      cultivar: '',
      sowing_date: '',
    })

    expect(response.metrics.estimated_yield_t_ha).toBe(6.51)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/product/v1/apsim/yield-reports',
      expect.objectContaining({ method: 'POST' }),
    )
    const request = fetchMock.mock.calls[0][1] as RequestInit
    const payload = JSON.parse(String(request.body))
    expect(payload).toMatchObject({ mode: 'demo', crop_type: 'wheat' })
    expect(payload).not.toHaveProperty('cultivar')
    expect(payload).not.toHaveProperty('sowing_date')
  })

  it('loads protected report HTML into an object URL', async () => {
    localStorage.setItem('ktp_v2_api_key', 'test-key')
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('<html>report</html>', { status: 200, headers: { 'Content-Type': 'text/html' } }),
    )
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:apsim-report')

    const url = await loadApsimReportObjectUrl('/api/product/v1/artifacts/art_demo/render')

    expect(url).toBe('blob:apsim-report')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/product/v1/artifacts/art_demo/render',
      { headers: { Authorization: 'Bearer test-key' } },
    )
  })
})
