import React, { useRef, useEffect, useState, useCallback, useLayoutEffect, useMemo } from 'react'
import { useAppContext } from '../context/AppContext'
import { useArtifactClick } from '../hooks/useArtifactClick'
import { Link } from 'react-router-dom'
import { Bot, ExternalLink, X, Sparkles, AlertTriangle, ArrowUp, StopCircle, Paperclip, Loader2, RefreshCw, ArrowDown, Download, Keyboard, MessageSquare, Zap, FileText, FileJson, FileDown } from 'lucide-react'
import { escapeHtml, buildArtifactOpenHref, isMockArtifact, getArtifactLabel } from '../utils'
import { SessionMessage, Run, RunPart, PendingSubmission, Attachment, Tool } from '../types'
import MarkdownRenderer from './MarkdownRenderer'
import ToolCallBlock from './ToolCallBlock'
import ToolResultBlock from './ToolResultBlock'
import StreamingMarkdown from './StreamingMarkdown'
import DebugDrawer from './DebugDrawer'
import TokenUsageBadge from './TokenUsageBadge'
import ShortcutsOverlay from './ShortcutsOverlay'
import SimulationArtifact from './SimulationArtifact'
import * as api from '../services/api'
import { createDataset } from '../services/canonical'

function formatMessageTime(dateStr?: string): string {
  if (!dateStr) return ""
  const date = new Date(dateStr)
  if (isNaN(date.getTime())) return ""
  return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })
}

const CATEGORY_EMOJIS: Record<string, string> = {
  analysis: "📊",
  knowledge: "📚",
  workspace: "🗂️",
  training: "🎓",
  report: "📝",
  visualization: "📈",
  conversation: "💬",
  debug: "🔧",
  remote_sensing: "🛰️",
  crop_simulation: "🌾",
  web: "🌐",
}

function getDynamicShortcuts(tools: Tool[]): { emoji: string; title: string; desc: string; prompt: string }[] {
  const webTools = tools.filter(t =>
    t.visibility === 'web' &&
    t.safety_level !== 'dangerous' &&
    t.tool_name !== 'direct_answer'
  )
  const selected = webTools.slice(0, 3)
  if (selected.length === 0) {
    return [
      { emoji: "💬", title: "开始对话", desc: "向 KTP 助手提问", prompt: "你好，请介绍一下你能做什么" },
    ]
  }
  return selected.map(t => ({
    emoji: CATEGORY_EMOJIS[t.category || ''] || "⚡",
    title: t.display_name || t.name || t.tool_name,
    desc: t.description || "",
    prompt: `请使用 ${t.display_name || t.name || t.tool_name} 帮我分析`,
  }))
}

const ChatInterface: React.FC = () => {
  const {
    state,
    sendMessage,
    retryLastMessage,
    stopGeneration,
    handleMessageChange,
    handlePromptClick,
    handleAttachmentRemove,
    addAttachment,
    clearError,
    refreshAll,
    setConversationMode,
  } = useAppContext()

  const { artifactError, handleArtifactClick, clearArtifactError } = useArtifactClick()
  const isEmpty = state.sessionMessages.length === 0 && !state.pendingSubmission
  const scrollRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [showScrollBottom, setShowScrollBottom] = useState(false)
  const [showShortcuts, setShowShortcuts] = useState(false)
  const uploadErrorTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const messageCount = state.sessionMessages.length
  const pendingPartsCount = state.pendingSubmission?.parts.length ?? 0
  const prevMessageCountRef = useRef(messageCount)
  const prevSessionIdRef = useRef(state.selectedSessionId)

  const handleScroll = useCallback(() => {
    if (!scrollRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight
    setShowScrollBottom(distanceFromBottom > 120)
  }, [])

  useEffect(() => {
    const sessionChanged = state.selectedSessionId !== prevSessionIdRef.current
    prevSessionIdRef.current = state.selectedSessionId
    const newMessageArrived = messageCount > prevMessageCountRef.current
    prevMessageCountRef.current = messageCount

    if (!scrollRef.current) return

    if (sessionChanged) {
      requestAnimationFrame(() => {
        if (scrollRef.current) {
          scrollRef.current.scrollTop = scrollRef.current.scrollHeight
        }
      })
      return
    }

    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight
    if (distanceFromBottom < 200 || newMessageArrived) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messageCount, pendingPartsCount, state.selectedSessionId])

  useLayoutEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 160) + 'px'
    }
  }, [state.composer.message])

  useEffect(() => {
    function handleGlobalKeyDown(e: KeyboardEvent) {
      const isMod = e.ctrlKey || e.metaKey
      if (isMod && e.key === 'n') {
        e.preventDefault()
        refreshAll({})
      }
      if (isMod && e.key === 'k') {
        e.preventDefault()
        textareaRef.current?.focus()
      }
      if (e.key === 'Escape') {
        if (state.pendingSubmission) stopGeneration()
        setShowShortcuts(false)
      }
      if (isMod && e.shiftKey && e.key === 'P') {
        e.preventDefault()
        setShowShortcuts(prev => !prev)
      }
    }
    window.addEventListener('keydown', handleGlobalKeyDown)
    return () => window.removeEventListener('keydown', handleGlobalKeyDown)
  }, [state.pendingSubmission, stopGeneration, refreshAll])

  useEffect(() => {
    return () => {
      if (uploadErrorTimerRef.current) clearTimeout(uploadErrorTimerRef.current)
    }
  }, [])

  function scrollToBottom() {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      sendMessage()
    }
  }

  const MAX_UPLOAD_SIZE_MB = 100

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files
    if (!files || files.length === 0) return
    for (let i = 0; i < files.length; i++) {
      if (files[i].size > MAX_UPLOAD_SIZE_MB * 1024 * 1024) {
        setUploadError(`文件 ${files[i].name} 超过 ${MAX_UPLOAD_SIZE_MB}MB 限制`)
        if (uploadErrorTimerRef.current) clearTimeout(uploadErrorTimerRef.current)
        uploadErrorTimerRef.current = setTimeout(() => setUploadError(null), 5000)
        if (fileInputRef.current) fileInputRef.current.value = ""
        return
      }
    }
    setUploading(true)
    try {
      for (let i = 0; i < files.length; i++) {
        const file = files[i]
        const result = await api.uploadFile(file)
        try {
          const dataset = await createDataset({
            source: { kind: 'local_path', uri: result.path },
            display_name: result.name,
            defaults: { task_type: 'lai_inversion' },
          })
          addAttachment({
            kind: 'local_path',
            path: result.path,
            name: result.name,
            size: result.size,
            dataset_id: dataset.dataset_id,
          })
        } catch {
          // Dataset registration failed — still add attachment without dataset_id (graceful degradation)
          addAttachment({ kind: 'local_path', path: result.path, name: result.name, size: result.size })
        }
      }
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "上传失败"
      setUploadError(msg)
      if (uploadErrorTimerRef.current) clearTimeout(uploadErrorTimerRef.current)
      uploadErrorTimerRef.current = setTimeout(() => setUploadError(null), 5000)
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ""
    }
  }

  function exportConversation() {
    const messages = state.sessionMessages
    if (messages.length === 0) return
    const lines = messages.map(m => {
      const role = m.role === 'user' ? '**用户**' : '**KTP**'
      let content = m.content
      if (m.parts && m.parts.length > 0) {
        const toolParts = m.parts.filter((p: RunPart) => p.type === 'tool_call' || p.type === 'tool_result')
        if (toolParts.length > 0) {
          const toolsText = toolParts
            .map((p: RunPart) => `  - [${p.type}] ${p.tool_invocation?.display_name || p.tool_invocation?.tool_name || '工具'}${p.text ? ': ' + p.text.slice(0, 200) : ''}`)
            .join('\n')
          content += `\n\n<details><summary>工具调用 (${toolParts.length}次)</summary>\n\n${toolsText}\n\n</details>`
        }
      }
      return `${role}:\n\n${content}\n`
    })
    const text = `# KTP 对话记录\n\n导出时间: ${new Date().toLocaleString('zh-CN')}\n\n${lines.join('\n---\n\n')}`
    const blob = new Blob([text], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `ktp-chat-${new Date().toISOString().slice(0, 10)}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  function exportAsHtml() {
    const messages = state.sessionMessages
    if (messages.length === 0) return
    const bodyLines = messages.map(m => {
      const role = m.role === 'user' ? '用户' : 'KTP'
      const roleClass = m.role === 'user' ? 'color:#1a1a1a;font-weight:600' : 'color:#2563eb;font-weight:600'
      let content = m.content.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      content = content.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      content = content.replace(/`(.*?)`/g, '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px;font-size:0.9em">$1</code>')
      content = content.replace(/\n/g, '<br>')
      return `<div style="margin-bottom:16px;padding:12px;border-radius:8px;background:${m.role === 'user' ? '#fafaf9' : '#f0f9ff'}"><div style="${roleClass};margin-bottom:4px;font-size:0.9em">${role}</div><div style="font-size:0.9em;line-height:1.6">${content}</div></div>`
    })
    const html = `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>KTP 对话报告</title><style>body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;max-width:800px;margin:0 auto;padding:20px;color:#1a1a1a;background:#fff}h1{font-size:1.4em;color:#1a1a1a;border-bottom:1px solid #e5e5e5;padding-bottom:8px}.meta{color:#6b7280;font-size:0.8em;margin-bottom:20px}</style></head><body><h1>KTP 对话报告</h1><div class="meta">导出时间: ${new Date().toLocaleString('zh-CN')}</div>${bodyLines.join('\n')}</body></html>`
    const blob = new Blob([html], { type: 'text/html' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `ktp-report-${new Date().toISOString().slice(0, 10)}.html`
    a.click()
    URL.revokeObjectURL(url)
  }

  function exportAsJson() {
    const messages = state.sessionMessages
    if (messages.length === 0) return
    const data = {
      export_time: new Date().toISOString(),
      session_id: state.selectedSessionId,
      messages: messages.map(m => ({
        role: m.role,
        content: m.content,
        timestamp: m.timestamp,
        parts: m.parts?.filter((p: RunPart) => p.type === 'tool_call' || p.type === 'tool_result').map((p: RunPart) => ({
          type: p.type,
          tool_name: p.tool_invocation?.tool_name,
          display_name: p.tool_invocation?.display_name,
          status: p.tool_invocation?.status,
        })),
      })),
    }
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `ktp-chat-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  function renderComposer() {
    return (
      <div className="w-full max-w-2xl mx-auto px-4 pb-4">
        {uploadError && (
          <div className="mx-4 mt-2 px-3 py-1.5 text-xs text-red-600 bg-red-50 border border-red-100 rounded-lg">
            {uploadError}
          </div>
        )}
        {state.composer.attachments.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-1.5 px-4 pt-3">
            {state.composer.attachments.map((attachment, index) => (
              <div key={index} className="bg-stone-100 text-stone-500 rounded-md px-2 py-0.5 text-xs flex items-center gap-1">
                {escapeHtml(attachment.name ?? attachment.path ?? '')}
                {attachment.dataset_id
                  ? <span title="已注册为 Dataset" className="text-green-500 ml-0.5">✓</span>
                  : <span title="注册中或未注册" className="text-stone-400 ml-0.5">○</span>
                }
                <button type="button" className="text-stone-300 hover:text-stone-500" onClick={() => handleAttachmentRemove(index)}>
                  <X size={10} />
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="relative flex items-end bg-white rounded-2xl border border-stone-200/80 focus-within:border-stone-300 focus-within:shadow-sm transition-all">
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept=".tif,.tiff,.png,.jpg,.jpeg,.bmp,.img,.txt,.csv,.json"
            multiple
            onChange={handleFileUpload}
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="ml-3 mb-2.5 p-1.5 rounded-lg text-stone-300 hover:text-stone-500 hover:bg-stone-100 transition-colors shrink-0"
            title="上传文件"
            aria-label="上传文件"
          >
            {uploading ? <Loader2 size={16} className="animate-spin" /> : <Paperclip size={16} />}
          </button>
          <textarea
            ref={textareaRef}
            value={state.composer.message}
            onChange={handleMessageChange}
            onKeyDown={handleKeyDown}
            placeholder="给 KTP 发送消息... (Ctrl+K 聚焦)"
            aria-label="消息输入框"
            rows={1}
            style={{ color: '#44403c', backgroundColor: 'transparent', border: 'none' }}
            className="flex-1 px-3 py-3 text-sm outline-none resize-none max-h-[160px] placeholder:text-stone-300"
          />
          {state.pendingSubmission ? (
            <button
              type="button"
              onClick={stopGeneration}
              className="mr-2.5 mb-2 p-1.5 bg-stone-400 text-white rounded-lg hover:bg-stone-500 transition-colors shrink-0"
              title="停止生成 (Esc)"
            >
              <StopCircle size={16} />
            </button>
          ) : (
            <button
              type="submit"
              className="mr-2.5 mb-2 p-1.5 bg-stone-700 text-white rounded-lg hover:bg-stone-800 transition-colors disabled:opacity-20 disabled:cursor-not-allowed shrink-0"
              disabled={state.loading.sendMessage || !state.composer.message.trim()}
              title="发送 (Enter)"
            >
              <ArrowUp size={16} />
            </button>
          )}
        </div>
        <div className="flex items-center justify-between mt-2">
          <div className="flex items-center gap-2">
            <p className="text-[11px] text-stone-300">KTP 可能会犯错，请核实重要信息。</p>
            <button
              type="button"
              onClick={() => setConversationMode(state.conversationMode === 'chat' ? 'task' : 'chat')}
              className={`text-[11px] px-1.5 py-0.5 rounded transition-colors flex items-center gap-1 ${
                state.conversationMode === 'task'
                  ? 'text-amber-600 bg-amber-50 border border-amber-200/60'
                  : 'text-stone-300 hover:text-stone-500'
              }`}
              title={state.conversationMode === 'task' ? '任务模式：优先调用分析工具' : '聊天模式：优先直接回答'}
            >
              {state.conversationMode === 'task' ? <Zap size={10} /> : <MessageSquare size={10} />}
              {state.conversationMode === 'task' ? '任务' : '聊天'}
            </button>
          </div>
          <div className="flex items-center gap-2">
            {state.sessionMessages.length > 0 && (
              <div className="relative group">
                <button
                  type="button"
                  className="text-[11px] text-stone-300 hover:text-stone-500 transition-colors flex items-center gap-1"
                  title="导出"
                >
                  <Download size={10} /> 导出
                </button>
                <div className="absolute right-0 top-full mt-1 w-36 bg-white border border-stone-200 rounded-lg shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-20">
                  <button
                    onClick={exportConversation}
                    className="w-full flex items-center gap-2 px-3 py-2 text-xs text-stone-600 hover:bg-stone-50 rounded-t-lg"
                  >
                    <FileText size={12} /> Markdown
                  </button>
                  <button
                    onClick={exportAsHtml}
                    className="w-full flex items-center gap-2 px-3 py-2 text-xs text-stone-600 hover:bg-stone-50"
                  >
                    <FileDown size={12} /> HTML 报告
                  </button>
                  <button
                    onClick={exportAsJson}
                    className="w-full flex items-center gap-2 px-3 py-2 text-xs text-stone-600 hover:bg-stone-50 rounded-b-lg"
                  >
                    <FileJson size={12} /> JSON 数据
                  </button>
                </div>
              </div>
            )}
            <button
              type="button"
              onClick={() => setShowShortcuts(prev => !prev)}
              className="text-[11px] text-stone-300 hover:text-stone-500 transition-colors flex items-center gap-1"
              title="快捷键"
            >
              <Keyboard size={10} /> 快捷键
            </button>
          </div>
        </div>
      </div>
    )
  }

  const messagePairs = useMemo(() => {
    const messages = state.sessionMessages.filter(m => m.role === 'user' || m.role === 'assistant')
    const pairs: { user: SessionMessage; assistant?: SessionMessage; key: string }[] = []
    let i = 0
    while (i < messages.length) {
      const user = messages[i]
      if (user.role === 'user') {
        const assistant = messages[i + 1]?.role === 'assistant' ? messages[i + 1] : undefined
        pairs.push({ user, assistant, key: `msg-${i}` })
        i += assistant ? 2 : 1
      } else {
        i++
      }
    }

    const runBySessionIndex = new Map<number, Run>()
    for (const run of state.sessionRuns) {
      const idx = run.session_message_index
      if (typeof idx === 'number' && idx >= 0) {
        runBySessionIndex.set(idx, run)
      }
    }
    const runByInputMessage = new Map<string, Run>()
    for (const run of state.sessionRuns) {
      const key = (run.input_message || '').trim()
      if (key) {
        runByInputMessage.set(key, run)
      }
    }

    return { pairs, messages, runBySessionIndex, runByInputMessage }
  }, [state.sessionMessages, state.sessionRuns])

  function renderSessionMessages() {
    const { pairs, messages, runBySessionIndex, runByInputMessage } = messagePairs

    return pairs.map(({ user, assistant, key }, pairIndex) => {
      const userContent = user.content.trim()
      const msgIndex = messages.indexOf(user)
      const run = runBySessionIndex.get(msgIndex) || runByInputMessage.get(userContent)
      const isLast = pairIndex === pairs.length - 1
      const isFailed = run?.status === "failed" || (assistant?.parts?.some((p: RunPart) => p.type === "error"))
      return (
        <React.Fragment key={key}>
          {renderUserMessage(user.content, run?.input_context?.attachments ?? [], key, user.timestamp)}
          {assistant && (run ? renderAssistantMessage(run, assistant, isLast && isFailed) : renderSimpleAssistantMessage(assistant.content, assistant.parts, assistant.timestamp, assistant.run_id))}
        </React.Fragment>
      )
    })
  }

  function renderSimpleAssistantMessage(content: string, parts?: RunPart[], timestamp?: string, run_id?: string) {
    const filteredParts = parts
      ? parts.filter((p: RunPart) => {
          if (p.type === "tool_call" || p.type === "tool_result") return false
          if (p.type === "artifact" && p.artifact?.artifact_type !== "simulation_data") return false
          return true
        })
      : parts
    return (
      <div className="flex gap-3">
        <div className="w-7 h-7 rounded-full bg-stone-200 flex items-center justify-center shrink-0 mt-0.5">
          <Bot size={14} className="text-stone-500" />
        </div>
        <div className="flex-1 min-w-0">
          {run_id && <DebugDrawer run_id={run_id} isLoading={false} />}
          {filteredParts && filteredParts.length > 0 ? (
            <div className="space-y-3">
              {filteredParts.map((part: RunPart, index: number) => renderAssistantPart(part, index, true))}
            </div>
          ) : !run_id ? (
            <div className="text-[15px] text-stone-800 leading-relaxed">
              <MarkdownRenderer content={content} />
            </div>
          ) : null}
          {timestamp && <div className="text-[10px] text-stone-300 mt-1">{formatMessageTime(timestamp)}</div>}
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {state.errorMessage && (
        <div className="mx-auto max-w-2xl w-full px-4 pt-3">
          <div className="bg-red-50 border border-red-200/60 text-red-600 px-4 py-2.5 rounded-xl text-sm flex items-center justify-between">
            <span className="flex-1 text-[13px]">{escapeHtml(state.errorMessage)}</span>
            <button onClick={clearError} className="ml-3 text-red-300 hover:text-red-500 shrink-0"><X size={14} /></button>
          </div>
        </div>
      )}
      {artifactError && (
        <div className="mx-auto max-w-2xl w-full px-4 pt-3">
          <div className="bg-amber-50 border border-amber-200/60 text-amber-600 px-4 py-2.5 rounded-xl text-sm flex items-center justify-between">
            <span className="flex items-center gap-2 text-[13px]"><AlertTriangle size={13} />{artifactError.message}</span>
            <button onClick={clearArtifactError} className="ml-3 text-amber-300 hover:text-amber-500 shrink-0"><X size={14} /></button>
          </div>
        </div>
      )}
      {isEmpty ? (
        <div className="flex-1 min-h-0 flex flex-col items-center justify-center px-6">
          <div className="mb-8 text-center">
            <h1 className="text-2xl font-semibold text-stone-700 mb-2">你好，有什么可以帮你的？</h1>
            <p className="text-stone-400 text-sm">选择一个快捷操作，或直接输入你的问题</p>
          </div>
          <div className="w-full max-w-xl mb-6">
            <form onSubmit={(e) => { e.preventDefault(); sendMessage() }}>
              {renderComposer()}
            </form>
          </div>
          <div className="grid grid-cols-2 gap-2.5 w-full max-w-xl">
            {getDynamicShortcuts(state.tools).map((item) => (
              <button
                key={item.title}
                onClick={() => handlePromptClick(item.prompt)}
                className="text-left p-4 bg-white border border-stone-200/80 rounded-xl hover:bg-stone-50 hover:border-stone-300 transition-all"
              >
                <span className="text-sm font-medium text-stone-700">{item.emoji} {item.title}</span>
                <p className="text-xs text-stone-400 mt-1 line-clamp-2">{item.desc}</p>
              </button>
            ))}
            <Link
              to="/skills"
              className="text-left p-4 bg-white border border-stone-200/80 rounded-xl hover:bg-stone-50 hover:border-stone-300 transition-all"
            >
              <span className="text-sm font-medium text-stone-700">🛠️ 查看全部技能</span>
              <p className="text-xs text-stone-400 mt-1">浏览所有可用的分析技能</p>
            </Link>
          </div>
        </div>
      ) : (
        <>
          <div className="flex-1 min-h-0 overflow-y-auto relative" ref={scrollRef} onScroll={handleScroll} role="log" aria-live="polite">
            <div className="max-w-2xl mx-auto px-4 py-6 space-y-6">
              {renderSessionMessages()}
              {state.pendingSubmission && state.pendingSubmission.conversation_id === state.selectedSessionId && (
                <React.Fragment key="pending">
                  {renderUserMessage(state.pendingSubmission.message, state.pendingSubmission.attachments, "pending-user")}
                  {renderPendingAssistantMessage(state.pendingSubmission)}
                </React.Fragment>
              )}
            </div>
            {showScrollBottom && (
              <button
                onClick={scrollToBottom}
                className="fixed bottom-28 right-8 z-20 w-8 h-8 bg-white border border-stone-200 rounded-full shadow-sm flex items-center justify-center text-stone-400 hover:text-stone-600 hover:shadow transition-all"
                title="滚动到底部"
                aria-label="滚动到底部"
              >
                <ArrowDown size={14} />
              </button>
            )}
          </div>
          <div className="shrink-0 bg-gradient-to-t from-stone-50 via-stone-50 to-transparent pt-2">
            <form onSubmit={(e) => { e.preventDefault(); sendMessage() }}>
              {renderComposer()}
            </form>
          </div>
        </>
      )}
      {showShortcuts && <ShortcutsOverlay onClose={() => setShowShortcuts(false)} />}
    </div>
  )

  function renderUserMessage(message: string, attachments: Attachment[], key: string, timestamp?: string) {
    return (
      <div className="flex justify-end" key={key}>
        <div className="max-w-[85%]">
          <div className="bg-stone-100 rounded-2xl px-4 py-2.5 text-[15px] text-stone-700 leading-relaxed whitespace-pre-wrap">
            {escapeHtml(message)}
          </div>
          {attachments && attachments.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-1.5 justify-end">
              {attachments.map((item, index) => (
                <div key={index} className="bg-stone-100 rounded-md px-2 py-0.5 text-xs text-stone-400">
                  {escapeHtml(item.name ?? item.path ?? '')}
                </div>
              ))}
            </div>
          )}
          {timestamp && <div className="text-[10px] text-stone-300 mt-1 text-right">{formatMessageTime(timestamp)}</div>}
        </div>
      </div>
    )
  }

  function renderAssistantMessage(run: Run, sessionMsg?: SessionMessage, showRetry?: boolean) {
    const parts = run.assistant_message?.parts?.length
      ? run.assistant_message.parts
      : sessionMsg?.parts?.length
        ? sessionMsg.parts
        : [{ type: run.status === "failed" ? "error" as const : "text" as const, text: run.output_message, status: run.status }]
    const debugRunId = sessionMsg?.run_id ?? run.run_id
    const filteredParts = parts.filter((p: RunPart) => {
      if (p.type === "tool_call" || p.type === "tool_result") return false
      if (p.type === "artifact" && p.artifact?.artifact_type !== "simulation_data") return false
      return true
    })
    return (
      <div className="flex gap-3">
        <div className="w-7 h-7 rounded-full bg-stone-200 flex items-center justify-center shrink-0 mt-0.5">
          <Bot size={14} className="text-stone-500" />
        </div>
        <div className="flex-1 min-w-0 space-y-3">
          {debugRunId && <DebugDrawer run_id={debugRunId} isLoading={false} />}
          {filteredParts.map((part: RunPart, index: number) => renderAssistantPart(part, index, true))}
          <TokenUsageBadge usage={run.token_usage} />
          {showRetry && (
            <button
              onClick={retryLastMessage}
              className="inline-flex items-center gap-1.5 text-[12px] text-stone-400 hover:text-stone-600 transition-colors mt-1"
            >
              <RefreshCw size={11} />
              <span>重新生成</span>
            </button>
          )}
        </div>
      </div>
    )
  }

  function renderPendingAssistantMessage(pending: PendingSubmission) {
    const hasParts = pending.parts.length > 0
    const filteredParts = pending.parts.filter((p: RunPart) => {
      if (p.type === "tool_call" || p.type === "tool_result") return false
      if (p.type === "artifact" && p.artifact?.artifact_type !== "simulation_data") return false
      return true
    })

    return (
      <div className="flex gap-3">
        <div className="w-7 h-7 rounded-full bg-stone-200 flex items-center justify-center shrink-0 mt-0.5">
          <Bot size={14} className="text-stone-500" />
        </div>
        <div className="flex-1 min-w-0 space-y-3">
          {!hasParts && (
            <div className="flex items-center gap-1.5 py-1">
              <div className="w-1.5 h-1.5 bg-stone-300 rounded-full animate-bounce"></div>
              <div className="w-1.5 h-1.5 bg-stone-300 rounded-full animate-bounce" style={{ animationDelay: '0.15s' }}></div>
              <div className="w-1.5 h-1.5 bg-stone-300 rounded-full animate-bounce" style={{ animationDelay: '0.3s' }}></div>
            </div>
          )}
          {filteredParts.map((part: RunPart, index: number) => renderAssistantPart(part, index, false))}
          <DebugDrawer run_id={pending.run_id} isLoading={true} />
        </div>
      </div>
    )
  }

  function renderAssistantPart(part: RunPart, index: number, isHistory: boolean = false) {
    if (part.type === "artifact" && part.artifact) {
      if (part.artifact.artifact_type === "simulation_data" && part.artifact.content) {
        return (
          <div key={index} className="my-1">
            <SimulationArtifact title={part.artifact.title} content={part.artifact.content} />
          </div>
        )
      }
      const openHref = buildArtifactOpenHref(part.artifact)
      const mock = isMockArtifact(part.artifact)
      const label = getArtifactLabel(part.artifact)
      return (
        <div key={index} className={`border rounded-lg p-3 ${mock ? 'bg-amber-50/40 border-amber-200/60' : 'bg-stone-50/60 border-stone-200/60'}`}>
          <div className="flex items-center gap-2 mb-1.5">
            <Sparkles size={13} className={mock ? "text-amber-400" : "text-stone-400"} />
            <span className="font-medium text-[13px] text-stone-700">{escapeHtml(part.artifact.title)}</span>
            {mock && <span className="text-[10px] bg-amber-100/60 text-amber-600 px-1.5 py-0.5 rounded-full font-medium">Mock</span>}
          </div>
          {part.artifact.content && <div className="text-[13px] text-stone-500 whitespace-pre-wrap mb-2">{escapeHtml(part.artifact.content)}</div>}
          {openHref && (
            <button
              onClick={() => handleArtifactClick(openHref)}
              className="inline-flex items-center gap-1.5 text-[13px] font-medium text-stone-500 hover:text-stone-700 transition-colors"
            >
              <ExternalLink size={12} /> {label}
            </button>
          )}
          {mock && !openHref && (
            <span className="text-[11px] text-stone-400">模拟产物，关闭模拟后可生成真实文件</span>
          )}
        </div>
      )
    }
    if (part.type === "tool_call" && part.tool_invocation) {
      return <ToolCallBlock key={index} part={part} isHistory={isHistory} />
    }
    if (part.type === "tool_result" && part.tool_invocation) {
      return <ToolResultBlock key={index} part={part} isHistory={isHistory} />
    }
    if (part.type === "error") {
      return (
        <div key={index} className="text-[15px] text-red-500 leading-relaxed">
          {isHistory ? <MarkdownRenderer content={part.text ?? ""} /> : <StreamingMarkdown content={part.text ?? ""} />}
        </div>
      )
    }
    return (
      <div key={index} className="text-[15px] text-stone-800 leading-relaxed">
        {isHistory ? <MarkdownRenderer content={part.text ?? ""} /> : <StreamingMarkdown content={part.text ?? ""} />}
      </div>
    )
  }
}

export default ChatInterface
