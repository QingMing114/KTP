// @vitest-environment node
import { describe, expect, it } from 'vitest'
import { extractAssistantText } from '../features/workspace-assistant/useWorkspaceConversation'

describe('extractAssistantText', () => {
  it('uses the persisted assistant summary after a completed submission', () => {
    expect(extractAssistantText({
      run_id: 'run-1',
      conversation_id: 'conv-1',
      status: 'completed',
      assistant: { summary: '已完成影像质量说明。' },
    }, 'partial response')).toBe('已完成影像质量说明。')
  })

  it('falls back to assistant parts and then streamed text', () => {
    expect(extractAssistantText({
      run_id: 'run-1',
      conversation_id: 'conv-1',
      status: 'completed',
      assistant: { parts: [{ type: 'text', text: '第一段' }, { type: 'text', text: '第二段' }] },
    }, 'partial response')).toBe('第一段\n\n第二段')
    expect(extractAssistantText(null, 'partial response')).toBe('partial response')
  })
})
