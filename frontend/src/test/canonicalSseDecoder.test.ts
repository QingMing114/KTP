// @vitest-environment node

import { describe, expect, it } from 'vitest'
import { IncrementalSseDecoder } from '../services/sseDecoder'
import { parseCanonicalSseBlock } from '../services/canonical/request'

function decoder() {
  return new IncrementalSseDecoder(parseCanonicalSseBlock)
}

describe('canonical incremental SSE decoder', () => {
  it('emits a fragmented event exactly once', () => {
    const stream = decoder()

    expect(stream.push('event: run.pro')).toEqual([])
    expect(stream.push('gress\ndata: {"event":"run.progress",')).toEqual([])
    expect(stream.push('"submission_id":"sub-1","timestamp":"now"}\n\n')).toEqual([
      expect.objectContaining({ event: 'run.progress', submission_id: 'sub-1' }),
    ])
    expect(stream.push('')).toEqual([])
  })

  it('handles multiple CRLF events and heartbeat comments', () => {
    const stream = decoder()
    const events = stream.push(
      ': heartbeat\r\n\r\n'
      + 'event: run.started\r\ndata: {"event":"run.started","submission_id":"sub-1","timestamp":"one"}\r\n\r\n'
      + 'event: run.completed\r\ndata: {"event":"run.completed","submission_id":"sub-1","timestamp":"two"}\r\n\r\n',
    )

    expect(events.map((event) => event.event)).toEqual(['run.started', 'run.completed'])
  })

  it('flushes one final event without a trailing blank line', () => {
    const stream = decoder()
    expect(stream.push(
      'event: run.completed\ndata: {"event":"run.completed","submission_id":"sub-1","timestamp":"now"}',
    )).toEqual([])

    expect(stream.finish()).toEqual([
      expect.objectContaining({ event: 'run.completed', submission_id: 'sub-1' }),
    ])
    expect(stream.finish()).toEqual([])
  })

  it('preserves UTF-8 characters split across byte chunks', () => {
    const stream = decoder()
    const text = 'event: run.progress\ndata: {"event":"run.progress","submission_id":"sub-1","detail":"正在反演","timestamp":"now"}\n\n'
    const bytes = new TextEncoder().encode(text)
    const splitAt = text.indexOf('正') + 1
    const textDecoder = new TextDecoder()

    const first = textDecoder.decode(bytes.slice(0, splitAt), { stream: true })
    const second = textDecoder.decode(bytes.slice(splitAt), { stream: true }) + textDecoder.decode()
    expect(stream.push(first)).toEqual([])
    expect(stream.push(second)).toEqual([
      expect.objectContaining({ detail: '正在反演' }),
    ])
  })
})
