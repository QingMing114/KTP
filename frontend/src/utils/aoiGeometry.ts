export type AoiGeometry = {
  type: 'Polygon'
  coordinates: number[][][]
}

type Coordinate = [number, number]

export type AoiValidationResult =
  | { valid: true; geometry: AoiGeometry; areaHectares: number }
  | { valid: false; reason: 'invalid_geometry' | 'too_small' | 'self_intersection' }

const EARTH_RADIUS_METERS = 6_371_008.8
const MIN_AOI_HECTARES = 0.01

function sameCoordinate([firstX, firstY]: Coordinate, [secondX, secondY]: Coordinate): boolean {
  return firstX === secondX && firstY === secondY
}

function isCoordinate(value: unknown): value is Coordinate {
  if (!Array.isArray(value) || value.length < 2) return false
  const [longitude, latitude] = value
  return typeof longitude === 'number'
    && typeof latitude === 'number'
    && Number.isFinite(longitude)
    && Number.isFinite(latitude)
    && longitude >= -180
    && longitude <= 180
    && latitude >= -90
    && latitude <= 90
}

function orientation(first: Coordinate, second: Coordinate, third: Coordinate): number {
  return (second[0] - first[0]) * (third[1] - first[1]) - (second[1] - first[1]) * (third[0] - first[0])
}

function isOnSegment(first: Coordinate, second: Coordinate, point: Coordinate): boolean {
  return Math.min(first[0], second[0]) <= point[0]
    && point[0] <= Math.max(first[0], second[0])
    && Math.min(first[1], second[1]) <= point[1]
    && point[1] <= Math.max(first[1], second[1])
}

function segmentsIntersect(firstStart: Coordinate, firstEnd: Coordinate, secondStart: Coordinate, secondEnd: Coordinate): boolean {
  const first = orientation(firstStart, firstEnd, secondStart)
  const second = orientation(firstStart, firstEnd, secondEnd)
  const third = orientation(secondStart, secondEnd, firstStart)
  const fourth = orientation(secondStart, secondEnd, firstEnd)

  if ((first > 0) !== (second > 0) && (third > 0) !== (fourth > 0)) return true
  return (first === 0 && isOnSegment(firstStart, firstEnd, secondStart))
    || (second === 0 && isOnSegment(firstStart, firstEnd, secondEnd))
    || (third === 0 && isOnSegment(secondStart, secondEnd, firstStart))
    || (fourth === 0 && isOnSegment(secondStart, secondEnd, firstEnd))
}

function hasSelfIntersection(vertices: Coordinate[]): boolean {
  const segmentCount = vertices.length
  for (let firstIndex = 0; firstIndex < segmentCount; firstIndex += 1) {
    const firstStart = vertices[firstIndex]
    const firstEnd = vertices[(firstIndex + 1) % segmentCount]
    for (let secondIndex = firstIndex + 1; secondIndex < segmentCount; secondIndex += 1) {
      if ((firstIndex + 1) % segmentCount === secondIndex || (secondIndex + 1) % segmentCount === firstIndex) continue
      const secondStart = vertices[secondIndex]
      const secondEnd = vertices[(secondIndex + 1) % segmentCount]
      if (segmentsIntersect(firstStart, firstEnd, secondStart, secondEnd)) return true
    }
  }
  return false
}

function calculateSphericalAreaHectares(ring: Coordinate[]): number {
  let accumulator = 0
  for (let index = 0; index < ring.length - 1; index += 1) {
    const [longitudeA, latitudeA] = ring[index]
    const [longitudeB, latitudeB] = ring[index + 1]
    const radians = Math.PI / 180
    accumulator += (longitudeB - longitudeA) * radians
      * (2 + Math.sin(latitudeA * radians) + Math.sin(latitudeB * radians))
  }
  return Math.abs(accumulator * EARTH_RADIUS_METERS ** 2 / 2) / 10_000
}

export function validateAoiGeometry(value: unknown): AoiValidationResult {
  const candidate = value as { type?: unknown; coordinates?: unknown }
  if (candidate?.type !== 'Polygon' || !Array.isArray(candidate.coordinates) || !Array.isArray(candidate.coordinates[0])) {
    return { valid: false, reason: 'invalid_geometry' }
  }

  const sourceRing = candidate.coordinates[0]
  if (!sourceRing.every(isCoordinate)) return { valid: false, reason: 'invalid_geometry' }

  const vertices = sourceRing.map(([longitude, latitude]) => [longitude, latitude] as Coordinate)
  if (vertices.length > 1 && sameCoordinate(vertices[0], vertices[vertices.length - 1])) vertices.pop()

  const uniqueVertices = new Set(vertices.map(([longitude, latitude]) => `${longitude},${latitude}`))
  if (vertices.length < 3 || uniqueVertices.size < 3) return { valid: false, reason: 'invalid_geometry' }
  if (hasSelfIntersection(vertices)) return { valid: false, reason: 'self_intersection' }

  const ring = [...vertices, vertices[0]]
  const areaHectares = calculateSphericalAreaHectares(ring)
  if (!Number.isFinite(areaHectares) || areaHectares < MIN_AOI_HECTARES) return { valid: false, reason: 'too_small' }

  return {
    valid: true,
    geometry: { type: 'Polygon', coordinates: [ring] },
    areaHectares,
  }
}

export function formatAoiArea(areaHectares: number | null | undefined): string {
  if (areaHectares == null || !Number.isFinite(areaHectares)) return '--'
  if (areaHectares >= 1_000) return `${areaHectares.toLocaleString('zh-CN', { maximumFractionDigits: 0 })} ha`
  if (areaHectares >= 100) return `${areaHectares.toFixed(0)} ha`
  if (areaHectares >= 10) return `${areaHectares.toFixed(1)} ha`
  return `${areaHectares.toFixed(2)} ha`
}

interface AreaPrecision {
  ha?: number
  m?: number
  mi?: number
  ac?: number
  yd?: number
}

function formatMeasurement(value: number, maximumFractionDigits: number): string {
  return value.toLocaleString('zh-CN', { maximumFractionDigits })
}

export function formatLeafletArea(areaSquareMeters: number, isMetric = true, precision: AreaPrecision = {}): string {
  if (isMetric) {
    if (areaSquareMeters >= 10_000) return `${formatMeasurement(areaSquareMeters / 10_000, precision.ha ?? 2)} ha`
    return `${formatMeasurement(areaSquareMeters, precision.m ?? 0)} m²`
  }

  const squareYards = areaSquareMeters / 0.836127
  if (squareYards >= 3_097_600) return `${formatMeasurement(squareYards / 3_097_600, precision.mi ?? 2)} mi²`
  if (squareYards >= 4_840) return `${formatMeasurement(squareYards / 4_840, precision.ac ?? 2)} acres`
  return `${formatMeasurement(squareYards, precision.yd ?? 0)} yd²`
}
