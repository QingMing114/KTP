import { describe, it, expect } from 'vitest'
import { REGIONS, CROP_TYPES, TASK_TYPES, getRegionLabel, getCropLabel, getTaskLabel } from '../constants/agriculture'

describe('REGIONS', () => {
  it('should have exactly 10 regions', () => {
    expect(REGIONS).toHaveLength(10)
  })

  it('each region should have id, label, lat, lng', () => {
    for (const r of REGIONS) {
      expect(r.id).toBeTruthy()
      expect(r.label).toBeTruthy()
      expect(typeof r.lat).toBe('number')
      expect(typeof r.lng).toBe('number')
    }
  })

  it('should contain key provinces', () => {
    const ids = REGIONS.map(r => r.id)
    expect(ids).toContain('henan')
    expect(ids).toContain('shandong')
    expect(ids).toContain('heilongjiang')
    expect(ids).toContain('xinjiang')
  })
})

describe('CROP_TYPES', () => {
  it('should have 6 crop types', () => {
    expect(CROP_TYPES).toHaveLength(6)
  })

  it('each crop type should have id and label', () => {
    for (const c of CROP_TYPES) {
      expect(c.id).toBeTruthy()
      expect(c.label).toBeTruthy()
    }
  })

  it('should contain wheat and corn', () => {
    const ids = CROP_TYPES.map(c => c.id)
    expect(ids).toContain('wheat')
    expect(ids).toContain('corn')
  })
})

describe('TASK_TYPES', () => {
  it('should have 5 task types', () => {
    expect(TASK_TYPES).toHaveLength(5)
  })

  it('each task type should have id and label', () => {
    for (const t of TASK_TYPES) {
      expect(t.id).toBeTruthy()
      expect(t.label).toBeTruthy()
    }
  })
})

describe('getRegionLabel', () => {
  it('should return Chinese label for known region', () => {
    expect(getRegionLabel('henan')).toBe('河南')
    expect(getRegionLabel('shandong')).toBe('山东')
  })

  it('should return id for unknown region', () => {
    expect(getRegionLabel('unknown')).toBe('unknown')
  })
})

describe('getCropLabel', () => {
  it('should return Chinese label for known crop', () => {
    expect(getCropLabel('wheat')).toBe('小麦')
    expect(getCropLabel('corn')).toBe('玉米')
  })

  it('should return id for unknown crop', () => {
    expect(getCropLabel('unknown')).toBe('unknown')
  })
})

describe('getTaskLabel', () => {
  it('should return Chinese label for known task', () => {
    expect(getTaskLabel('lai_estimation')).toBe('LAI估算')
    expect(getTaskLabel('crop_health_detection')).toBe('作物健康检测')
  })

  it('should return id for unknown task', () => {
    expect(getTaskLabel('unknown')).toBe('unknown')
  })
})
