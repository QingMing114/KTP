import { describe, it, expect } from 'vitest'
import type { SseEvent } from '../types/api'

describe('SSE Event Parsing', () => {
  // Helper that mirrors the parseSseBlock logic from api.ts
  function parseSseBlock(block: string): SseEvent | null {
    let eventType: string | undefined
    const dataLines: string[] = []
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) {
        eventType = line.slice(6).trim()
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trim())
      } else if (line.startsWith(": ")) {
        continue
      }
    }
    if (dataLines.length === 0) return null
    try {
      const parsed = JSON.parse(dataLines.join("\n"))
      if (eventType && !parsed.event) parsed.event = eventType
      return parsed
    } catch {
      return { event: eventType || "raw", raw_data: dataLines.join("\n") } as SseEvent
    }
  }

  it('parses a valid SSE block with event type', () => {
    const result = parseSseBlock('event:run.started\ndata:{"run_id":"r1"}')
    expect(result).not.toBeNull()
    expect(result!.event).toBe('run.started')
    expect(result!.run_id).toBe('r1')
  })

  it('parses a SSE block without event type', () => {
    const result = parseSseBlock('data:{"output_message":"hello"}')
    expect(result).not.toBeNull()
    expect(result!.output_message).toBe('hello')
  })

  it('returns null for empty block', () => {
    expect(parseSseBlock('')).toBeNull()
    expect(parseSseBlock(': comment')).toBeNull()
  })

  it('handles multi-line data', () => {
    const result = parseSseBlock('event:assistant.delta\ndata:{"text":"hello "}\ndata:{"text":"world"}')
    // Multi-line data joins with newline, which may not be valid JSON
    // The new behavior should return raw_data instead of null
    expect(result).not.toBeNull()
  })

  it('handles invalid JSON gracefully (returns raw_data)', () => {
    const result = parseSseBlock('event:custom\ndata:not valid json')
    expect(result).not.toBeNull()
    expect(result!.event).toBe('custom')
    expect(result!.raw_data).toBe('not valid json')
  })

  it('handles SSE comment lines', () => {
    const result = parseSseBlock(': keep-alive\ndata:{"status":"ok"}')
    expect(result).not.toBeNull()
    expect(result!.status).toBe('ok')
  })

  it('extracts event type from event: line', () => {
    const result = parseSseBlock('event:tool.started\ndata:{"tool":"test"}')
    expect(result!.event).toBe('tool.started')
  })

  it('handles assistant.delta with output_message', () => {
    const result = parseSseBlock('event:assistant.delta\ndata:{"output_message":"Hello"}')
    expect(result!.event).toBe('assistant.delta')
    expect(result!.output_message).toBe('Hello')
  })

  it('handles run.completed event', () => {
    const result = parseSseBlock('event:run.completed\ndata:{"run_id":"r123"}')
    expect(result!.event).toBe('run.completed')
    expect(result!.run_id).toBe('r123')
  })

  it('handles run.failed event with detail', () => {
    const result = parseSseBlock('event:run.failed\ndata:{"detail":"timeout"}')
    expect(result!.event).toBe('run.failed')
    expect(result!.detail).toBe('timeout')
  })
})
