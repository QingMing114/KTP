import { describe, expect, it } from 'vitest'
import { formatAoiArea, formatLeafletArea, validateAoiGeometry } from '../utils/aoiGeometry'

describe('validateAoiGeometry', () => {
  it('normalizes an unclosed polygon and calculates its geodesic area', () => {
    const result = validateAoiGeometry({
      type: 'Polygon',
      coordinates: [[[100, 38], [100.01, 38], [100.01, 38.01], [100, 38.01]]],
    })

    expect(result.valid).toBe(true)
    if (!result.valid) return
    expect(result.geometry.coordinates[0]).toHaveLength(5)
    expect(result.geometry.coordinates[0][0]).toEqual(result.geometry.coordinates[0][4])
    expect(result.areaHectares).toBeGreaterThan(90)
    expect(result.areaHectares).toBeLessThan(110)
  })

  it('rejects a self-intersecting polygon', () => {
    const result = validateAoiGeometry({
      type: 'Polygon',
      coordinates: [[[100, 38], [100.01, 38.01], [100, 38.01], [100.01, 38], [100, 38]]],
    })

    expect(result).toEqual({ valid: false, reason: 'self_intersection' })
  })

  it('rejects a zero-area geometry', () => {
    const result = validateAoiGeometry({
      type: 'Polygon',
      coordinates: [[[100, 38], [100, 38], [100, 38], [100, 38]]],
    })

    expect(result).toEqual({ valid: false, reason: 'invalid_geometry' })
  })
})

describe('formatAoiArea', () => {
  it('formats small and large areas for the map status panel', () => {
    expect(formatAoiArea(8.256)).toBe('8.26 ha')
    expect(formatAoiArea(1286)).toBe('1,286 ha')
  })
})

describe('formatLeafletArea', () => {
  it('formats the live rectangle tooltip without relying on leaflet-draw globals', () => {
    expect(formatLeafletArea(204_000)).toBe('20.4 ha')
    expect(formatLeafletArea(625)).toBe('625 m²')
  })
})
