import { useState } from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import WorkspaceComposer from '../features/workspace-assistant/WorkspaceComposer'

afterEach(cleanup)
it('keeps the adjacent professional and automatic choices mutually exclusive', () => {
  const send = vi.fn(async () => {})
  function Composer() {
    const [automatic, setAutomatic] = useState(false)
    const [professional, setProfessional] = useState(false)
    return <WorkspaceComposer isSending={false} error="" onSend={send} onCancel={vi.fn()} autoExecute={automatic} onAutoExecute={setAutomatic} professionalMode={professional} onProfessionalMode={setProfessional} />
  }
  render(<Composer />)
  const pro = screen.getByRole('switch', { name: '专业模式' }), auto = screen.getByRole('switch', { name: '自动执行' })
  fireEvent.click(auto)
  expect(auto).toHaveAttribute('aria-checked', 'true')
  fireEvent.click(pro)
  expect(auto).toHaveAttribute('aria-checked', 'false')
  expect(pro).toHaveAttribute('aria-checked', 'true')
  fireEvent.click(auto)
  expect(pro).toHaveAttribute('aria-checked', 'false')
  expect(auto).toHaveAttribute('aria-checked', 'true')
  expect(send).not.toHaveBeenCalled()
})
it('defaults automatic execution off and changes permission without submitting a task', () => {
  const send = vi.fn(async () => {})
  function Composer() {
    const [enabled, setEnabled] = useState(false)
    return <WorkspaceComposer isSending={false} error="" onSend={send} onCancel={vi.fn()} autoExecute={enabled} onAutoExecute={setEnabled} />
  }
  render(<Composer />)
  const toggle = screen.getByRole('switch', { name: '自动执行' })
  expect(toggle).toHaveAttribute('aria-checked', 'false')
  fireEvent.click(toggle)
  expect(toggle).toHaveAttribute('aria-checked', 'true')
  expect(send).not.toHaveBeenCalled()
  fireEvent.change(screen.getByRole('textbox'), { target: { value: '识别作物并分析长势' } })
  fireEvent.click(screen.getByRole('button', { name: '发送问题' }))
  expect(send).toHaveBeenCalledExactlyOnceWith('识别作物并分析长势')
  fireEvent.click(toggle)
  expect(toggle).toHaveAttribute('aria-checked', 'false')
})
