/** Incremental SSE text framing that preserves incomplete network chunks. */
export class IncrementalSseDecoder<T> {
  private buffer = ''

  constructor(private readonly parseBlock: (block: string) => T | null) {}

  push(chunk: string): T[] {
    this.buffer += chunk
    const events: T[] = []
    let boundary = /(?:\r?\n){2}/.exec(this.buffer)

    while (boundary) {
      const block = this.buffer.slice(0, boundary.index).replace(/\r\n/g, '\n')
      this.buffer = this.buffer.slice(boundary.index + boundary[0].length)
      const event = this.parseBlock(block)
      if (event !== null) events.push(event)
      boundary = /(?:\r?\n){2}/.exec(this.buffer)
    }

    return events
  }

  finish(): T[] {
    const block = this.buffer.replace(/\r\n/g, '\n')
    this.buffer = ''
    if (!block.trim()) return []
    const event = this.parseBlock(block)
    return event === null ? [] : [event]
  }
}
