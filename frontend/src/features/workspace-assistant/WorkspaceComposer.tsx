import { Send, Square, Zap, SlidersHorizontal } from 'lucide-react'
import { useState, type FormEvent, type KeyboardEvent } from 'react'

interface WorkspaceComposerProps {
  isSending: boolean
  isLaunching?: boolean
  blocked?: boolean
  autoExecute?: boolean
  professionalMode?: boolean
  onProfessionalMode?: (enabled: boolean) => void
  onAutoExecute?: (enabled: boolean) => void
  hint?: string
  error: string
  onSend: (message: string) => Promise<void>
  onCancel: () => Promise<void>
}

export default function WorkspaceComposer({ isSending, isLaunching = false, blocked = false, autoExecute = false, professionalMode = false, onAutoExecute, onProfessionalMode, hint, error, onSend, onCancel }: WorkspaceComposerProps) {
  const [message, setMessage] = useState('')

  const submit = (event?: FormEvent) => {
    event?.preventDefault()
    const trimmedMessage = message.trim()
    if (!trimmedMessage || isSending || isLaunching || blocked) return
    setMessage('')
    void onSend(trimmedMessage)
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return <form onSubmit={submit} className="border-t border-white/10 bg-[#091a15]/80 px-4 py-3">
    {(onAutoExecute || onProfessionalMode) && <div aria-label="执行方式" className="mb-2 flex flex-wrap items-center gap-2">
      {onProfessionalMode && <button type="button" role="switch" aria-checked={professionalMode} aria-label="专业模式" onClick={() => { if (!professionalMode) onAutoExecute?.(false); onProfessionalMode(!professionalMode) }} className={`flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] transition ${professionalMode ? 'border-cyan-300/50 bg-cyan-400/15 text-cyan-200' : 'border-white/15 text-slate-400 hover:text-slate-200'}`}><SlidersHorizontal size={12} />专业模式<span>{professionalMode ? '已开启' : '已关闭'}</span></button>}
      {onAutoExecute &&
      <button type="button" role="switch" aria-checked={autoExecute} aria-label="自动执行" onClick={() => { if (!autoExecute) onProfessionalMode?.(false); onAutoExecute(!autoExecute) }} className={`flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] transition ${autoExecute ? 'border-emerald-300/50 bg-emerald-400/15 text-emerald-200' : 'border-white/15 text-slate-400 hover:text-slate-200'}`}>
        <Zap size={12} fill={autoExecute ? 'currentColor' : 'none'} />自动执行<span>{autoExecute ? '已开启' : '已关闭'}</span>
      </button>}
      <span className="w-full text-[9px] leading-4 text-slate-400" title="切换方式不会取消已启动的任务；待确认的专业操作仍需确认。">{professionalMode ? '推荐参数先展示，可编辑并确认后执行' : autoExecute ? '自动搜索、选片和分析，完成后提醒' : '选择专业模式或自动执行，也可按原流程操作'}</span>
    </div>}
    <div className="flex items-end gap-2 rounded-lg border border-white/10 bg-black/10 p-2 focus-within:border-emerald-300/35 focus-within:bg-emerald-400/[0.04]">
      <textarea
        value={message}
        onChange={(event) => setMessage(event.target.value)}
        onKeyDown={handleKeyDown}
        disabled={isSending || isLaunching || blocked}
        rows={1}
        aria-label="向遥感分析助手提问"
        placeholder={hint?.includes('后台') ? '询问任务进度或结果…' : '告诉我想做什么，例如：做 LAI 反演…'}
        className="max-h-24 min-h-5 flex-1 resize-none bg-transparent px-1 py-0.5 text-[11px] leading-5 text-slate-100 outline-none placeholder:text-slate-500 disabled:cursor-not-allowed disabled:opacity-60"
      />
      {isSending
        ? <button type="button" disabled={isLaunching} onClick={() => void onCancel()} aria-label="取消问答" className="grid h-7 w-7 shrink-0 place-items-center rounded-md border border-amber-300/25 bg-amber-300/10 text-amber-100 hover:bg-amber-300/20 disabled:opacity-30"><Square size={12} fill="currentColor" /></button>
        : <button type="submit" disabled={isLaunching || blocked || !message.trim()} aria-label="发送问题" className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-emerald-400 text-[#06261b] transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-35"><Send size={13} /></button>}
    </div>
    <div className="mt-1.5 flex min-h-4 items-center justify-between gap-2 px-1 text-[9px] text-slate-500"><span>{isLaunching ? '正在提交，请等待任务状态同步' : isSending ? '助手正在处理，可停止本轮问答' : hint ?? 'Enter 发送，Shift + Enter 换行'}</span>{error && <span className="truncate text-rose-300" title={error}>{error}</span>}</div>
  </form>
}
