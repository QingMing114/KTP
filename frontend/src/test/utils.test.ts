import { describe, it, expect } from 'vitest'
import {
  escapeHtml,
  formatRelativeTime,
  truncateId,
  getStatusLabel,
  getStatusStyle,
  getArtifactLabel,
  isMockArtifact,
} from '../utils'

describe('escapeHtml', () => {
  it('should escape ampersands', () => {
    expect(escapeHtml('a&b')).toBe('a&amp;b')
  })

  it('should escape angle brackets', () => {
    expect(escapeHtml('<script>')).toBe('&lt;script&gt;')
  })

  it('should escape quotes', () => {
    expect(escapeHtml('"hello"')).toBe('&quot;hello&quot;')
    expect(escapeHtml("'hello'")).toBe('&#39;hello&#39;')
  })

  it('should escape all special characters together', () => {
    expect(escapeHtml('<a href="x&y">z</a>')).toBe(
      '&lt;a href=&quot;x&amp;y&quot;&gt;z&lt;/a&gt;'
    )
  })

  it('should leave safe text unchanged', () => {
    expect(escapeHtml('hello world')).toBe('hello world')
  })
})

describe('formatRelativeTime', () => {
  it('should return empty string for undefined', () => {
    expect(formatRelativeTime(undefined)).toBe('')
  })

  it('should return empty string for invalid date', () => {
    expect(formatRelativeTime('not-a-date')).toBe('')
  })

  it('should return "刚刚" for recent times', () => {
    const now = new Date().toISOString()
    expect(formatRelativeTime(now)).toBe('刚刚')
  })

  it('should return minutes ago', () => {
    const fiveMinAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString()
    expect(formatRelativeTime(fiveMinAgo)).toBe('5分钟前')
  })

  it('should return hours ago', () => {
    const threeHoursAgo = new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString()
    expect(formatRelativeTime(threeHoursAgo)).toBe('3小时前')
  })

  it('should return days ago', () => {
    const twoDaysAgo = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString()
    expect(formatRelativeTime(twoDaysAgo)).toBe('2天前')
  })
})

describe('truncateId', () => {
  it('should truncate to 8 chars by default', () => {
    expect(truncateId('abcdefghijklmnop')).toBe('abcdefgh')
  })

  it('should return full string if shorter than length', () => {
    expect(truncateId('abc')).toBe('abc')
  })

  it('should respect custom length', () => {
    expect(truncateId('abcdefghij', 4)).toBe('abcd')
  })

  it('should handle empty string', () => {
    expect(truncateId('')).toBe('')
  })
})

describe('getStatusLabel', () => {
  it('should return Chinese labels for known statuses', () => {
    expect(getStatusLabel('completed')).toBe('完成')
    expect(getStatusLabel('failed')).toBe('失败')
    expect(getStatusLabel('streaming')).toBe('进行中')
    expect(getStatusLabel('pending')).toBe('等待中')
  })

  it('should return original status for unknown values', () => {
    expect(getStatusLabel('unknown')).toBe('unknown')
  })
})

describe('getStatusStyle', () => {
  it('should return emerald style for completed', () => {
    expect(getStatusStyle('completed')).toContain('emerald')
  })

  it('should return red style for failed', () => {
    expect(getStatusStyle('failed')).toContain('red')
  })

  it('should return yellow style for other statuses', () => {
    expect(getStatusStyle('pending')).toContain('yellow')
  })
})

describe('getArtifactLabel', () => {
  it('should return correct Chinese labels for known types', () => {
    expect(getArtifactLabel({ artifact_type: 'report_card' })).toBe('查看报告')
    expect(getArtifactLabel({ artifact_type: 'visualization_card' })).toBe('查看仪表盘')
    expect(getArtifactLabel({ artifact_type: 'inference_card' })).toBe('查看推理结果')
    expect(getArtifactLabel({ artifact_type: 'simulation_data' })).toBe('查看模拟数据')
    expect(getArtifactLabel({ artifact_type: 'simulation_log' })).toBe('查看运行日志')
  })

  it('should return default label for unknown type', () => {
    expect(getArtifactLabel({ artifact_type: 'unknown_type' })).toBe('打开产物')
  })

  it('should handle missing artifact_type', () => {
    expect(getArtifactLabel({})).toBe('打开产物')
  })
})

describe('isMockArtifact', () => {
  it('should return true for mock:// URIs', () => {
    expect(isMockArtifact({ uri: 'mock://something' })).toBe(true)
  })

  it('should return false for real URIs', () => {
    expect(isMockArtifact({ uri: 'http://example.com/file.csv' })).toBe(false)
    expect(isMockArtifact({ uri: '/data/file.csv' })).toBe(false)
  })

  it('should return false for missing URI', () => {
    expect(isMockArtifact({})).toBe(false)
    expect(isMockArtifact({ uri: '' })).toBe(false)
  })
})
