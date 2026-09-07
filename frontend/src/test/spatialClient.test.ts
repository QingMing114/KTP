// @vitest-environment node
import { describe, expect, it } from 'vitest'
import { readLaiAnalysisProducts } from '../services/spatialClient'

describe('readLaiAnalysisProducts', () => {
  it('reads the persisted LAI report, raster and map overlay contract', () => {
    const products = readLaiAnalysisProducts({
      report_uri: '/api/product/v1/artifacts/art_report/render',
      lai_raster_uri: '/api/product/v1/artifacts/art_raster/content',
      map_overlay: {
        url: '/api/product/v1/artifacts/art_preview/content',
        bounds: [100, 39.9, 100.1, 40],
        opacity: 0.72,
        color_scale: [[0, '#440154'], [7, '#fff7bc']],
      },
    })

    expect(products.reportUrl).toContain('art_report')
    expect(products.rasterUrl).toContain('art_raster')
    expect(products.overlay).toEqual({
      url: '/api/product/v1/artifacts/art_preview/content',
      bounds: [100, 39.9, 100.1, 40],
      opacity: 0.72,
      colorScale: [{ value: 0, color: '#440154' }, { value: 7, color: '#fff7bc' }],
    })
  })

  it('rejects an overlay with incomplete geographic bounds', () => {
    const products = readLaiAnalysisProducts({
      map_overlay: { url: '/preview.png', bounds: [100, 39.9, 100.1] },
    })

    expect(products.overlay).toBeNull()
  })
})
