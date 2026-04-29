import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useAppContext } from '../context/AppContext'
import { MessageSquare, Loader2, Trash2, AlertTriangle, Pencil, Check, X, Search } from 'lucide-react'
import { escapeHtml, formatRelativeTime } from '../utils'
import * as api from '../services/api'

function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  onConfirm,
  onCancel,
}: {
  open: boolean
  title: string
  message: string
  confirmLabel: string
  onConfirm: () => void
  onCancel: () => void
}) {
  const dialogRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onCancel()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [open, onCancel])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-stone-900/20 backdrop-blur-sm"
      onClick={onCancel}
    >
      <div
        ref={dialogRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-desc"
        className="bg-white rounded-xl shadow-xl border border-stone-200 w-full max-w-xs mx-4 p-5"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center gap-2.5 mb-3">
          <div className="p-1.5 bg-red-50 text-red-400 rounded-lg">
            <AlertTriangle size={16} />
          </div>
          <h3 id="confirm-title" className="text-sm font-semibold text-stone-700">{title}</h3>
        </div>
        <p id="confirm-desc" className="text-[13px] text-stone-500 mb-5 leading-relaxed">{message}</p>
        <div className="flex gap-2">
          <button
            onClick={onCancel}
            className="flex-1 py-2 text-[13px] bg-stone-100 hover:bg-stone-200 text-stone-600 rounded-lg transition-colors"
          >
            取消
          </button>
          <button
            onClick={onConfirm}
            className="flex-1 py-2 text-[13px] bg-red-500 hover:bg-red-600 text-white rounded-lg transition-colors"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

const SessionList: React.FC = () => {
  const { state, selectSession, deleteSession, refreshSessions } = useAppContext()
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [multiSelectMode, setMultiSelectMode] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const editInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    setSelectedIds(prev => {
      const validIds = new Set(state.sessions.map(s => s.session_id))
      const newSelected = new Set<string>()
      prev.forEach(id => {
        if (validIds.has(id)) newSelected.add(id)
      })
      return newSelected
    })
  }, [state.sessions])

  const handleDeleteConfirm = useCallback(async () => {
    if (pendingDeleteId === 'batch') {
      setDeleting(true)
      try {
        await Promise.all(Array.from(selectedIds).map(id => deleteSession(id)))
        setSelectedIds(new Set())
        setMultiSelectMode(false)
      } catch (err) {
        console.error('Failed to delete sessions:', err)
      } finally {
        setDeleting(false)
        setPendingDeleteId(null)
      }
      return
    }
    if (!pendingDeleteId) return
    setDeleting(true)
    try {
      await deleteSession(pendingDeleteId)
    } finally {
      setDeleting(false)
      setPendingDeleteId(null)
    }
  }, [pendingDeleteId, selectedIds, deleteSession])

  const handleDeleteCancel = useCallback(() => {
    if (pendingDeleteId === 'batch') {
      setPendingDeleteId(null)
      return
    }
    setPendingDeleteId(null)
  }, [pendingDeleteId])

  useEffect(() => {
    if (editingId && editInputRef.current) {
      editInputRef.current.focus()
      editInputRef.current.select()
    }
  }, [editingId])

  const handleRenameClick = useCallback((sessionId: string, currentTitle: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditingId(sessionId)
    setEditValue(currentTitle)
  }, [])

  const handleRenameConfirm = useCallback(async () => {
    if (!editingId || !editValue.trim()) {
      setEditingId(null)
      return
    }
    try {
      await api.updateSession(editingId, editValue.trim())
      await refreshSessions({ preferredSessionId: editingId })
    } catch (err) {
      console.error('Failed to rename session:', err)
    } finally {
      setEditingId(null)
    }
  }, [editingId, editValue, refreshSessions])

  const handleRenameCancel = useCallback(() => {
    setEditingId(null)
    setEditValue('')
  }, [])

  const handleRenameKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleRenameConfirm()
    } else if (e.key === 'Escape') {
      handleRenameCancel()
    }
  }, [handleRenameConfirm, handleRenameCancel])

  const handleToggleSelect = useCallback((sessionId: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(sessionId)) {
        next.delete(sessionId)
      } else {
        next.add(sessionId)
      }
      return next
    })
  }, [])

  const handleCancelMultiSelect = useCallback(() => {
    setMultiSelectMode(false)
    setSelectedIds(new Set())
  }, [])

  if (state.loading.sessions) {
    return (
      <div className="flex items-center justify-center py-4 px-4">
        <Loader2 size={12} className="text-stone-400 animate-spin mr-2" />
        <span className="text-[12px] text-stone-400">加载中...</span>
      </div>
    )
  }

  if (state.sessions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8 px-3">
        <div className="w-8 h-8 rounded-full bg-stone-100 flex items-center justify-center mb-2">
          <MessageSquare size={14} className="text-stone-300" />
        </div>
        <p className="text-[12px] text-stone-400">暂无会话</p>
        <p className="text-[11px] text-stone-300 mt-0.5">点击上方按钮新建对话</p>
      </div>
    )
  }

  function handleDeleteClick(sessionId: string, e: React.MouseEvent | React.KeyboardEvent) {
    e.stopPropagation()
    setPendingDeleteId(sessionId)
  }

  return (
    <>
      <div className="px-2.5 mb-2">
        <div className="relative">
          <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-stone-300" />
          <input
            type="text"
            placeholder="搜索会话..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className="w-full text-[12px] bg-stone-100 border border-stone-200/60 rounded-lg pl-7 pr-2 py-1.5 outline-none focus:border-stone-300 focus:bg-white transition-colors placeholder:text-stone-300"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-1.5 top-1/2 -translate-y-1/2 text-stone-300 hover:text-stone-500"
            >
              <X size={10} />
            </button>
          )}
        </div>
      </div>
      <div className="flex items-center justify-between px-2.5 mb-2">
        {multiSelectMode ? (
          <>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={selectedIds.size === state.sessions.length && state.sessions.length > 0}
                onChange={() => {
                  if (selectedIds.size === state.sessions.length) {
                    setSelectedIds(new Set())
                  } else {
                    setSelectedIds(new Set(state.sessions.map(s => s.session_id)))
                  }
                }}
                className="rounded border-stone-300"
              />
              <span className="text-[11px] text-stone-400">已选择 {selectedIds.size} 项</span>
            </div>
            <div className="flex gap-2">
              <button
                onClick={handleCancelMultiSelect}
                className="text-[11px] text-stone-400 hover:text-stone-600"
              >
                取消
              </button>
              <button
                onClick={() => setPendingDeleteId('batch')}
                className="text-[11px] text-red-400 hover:text-red-600"
              >
                删除
              </button>
            </div>
          </>
        ) : (
          <button
            onClick={() => setMultiSelectMode(true)}
            className="text-[11px] text-stone-400 hover:text-stone-600"
          >
            选择
          </button>
        )}
      </div>

      <div className="space-y-0.5">
        {state.sessions
          .filter(s => !searchQuery || (s.title || '').toLowerCase().includes(searchQuery.toLowerCase()))
          .map((session) => {
          const active = session.session_id === state.selectedSessionId
          const relTime = formatRelativeTime(session.updated_at || session.created_at)
          return (
            <div
              key={session.session_id}
              className={`w-full flex items-center space-x-2 px-2.5 py-2 rounded-lg transition-colors cursor-pointer group text-left ${active ? "bg-white text-stone-800 shadow-sm border border-stone-200/60" : "text-stone-500 hover:bg-stone-200/40 hover:text-stone-600 border border-transparent"}`}
              onClick={() => {
                if (multiSelectMode) {
                  handleToggleSelect(session.session_id)
                } else {
                  selectSession(session.session_id)
                }
              }}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (multiSelectMode ? handleToggleSelect(session.session_id) : selectSession(session.session_id))}
            >
              {multiSelectMode && (
                <input
                  type="checkbox"
                  checked={selectedIds.has(session.session_id)}
                  onChange={() => handleToggleSelect(session.session_id)}
                  onClick={(e) => e.stopPropagation()}
                  className="rounded border-stone-300 shrink-0"
                />
              )}
              <MessageSquare size={13} className="shrink-0 opacity-40" />
              <div className="flex-1 min-w-0">
                {editingId === session.session_id ? (
                  <input
                    ref={editInputRef}
                    type="text"
                    value={editValue}
                    onChange={(e) => setEditValue(e.target.value)}
                    onKeyDown={handleRenameKeyDown}
                    onBlur={handleRenameConfirm}
                    className="w-full text-[13px] bg-white border border-stone-300 rounded px-1 py-0.5 outline-none"
                    onClick={(e) => e.stopPropagation()}
                  />
                ) : (
                  <div className="text-[13px] truncate">{escapeHtml(session.title)}</div>
                )}
                {relTime && <div className="text-[10px] text-stone-400 mt-0.5">{relTime}</div>}
              </div>
              {!multiSelectMode && (
                <>
                  {editingId === session.session_id ? (
                    <>
                      <span
                        role="button"
                        onClick={(e) => { e.stopPropagation(); handleRenameConfirm() }}
                        className="p-0.5 text-emerald-500 hover:text-emerald-600 rounded opacity-100 transition-all shrink-0 cursor-pointer"
                        title="确认"
                        tabIndex={0}
                      >
                        <Check size={11} />
                      </span>
                      <span
                        role="button"
                        onClick={(e) => { e.stopPropagation(); handleRenameCancel() }}
                        className="p-0.5 text-stone-300 hover:text-stone-500 rounded opacity-100 transition-all shrink-0 cursor-pointer"
                        title="取消"
                        tabIndex={0}
                      >
                        <X size={11} />
                      </span>
                    </>
                  ) : (
                    <>
                      <span
                        role="button"
                        onClick={(e) => handleRenameClick(session.session_id, session.title, e)}
                        className="p-0.5 text-stone-300 hover:text-stone-500 rounded opacity-0 group-hover:opacity-100 focus:opacity-100 sm:opacity-0 sm:group-hover:opacity-100 sm:focus:opacity-100 transition-all shrink-0 cursor-pointer"
                        title="重命名会话"
                        tabIndex={0}
                      >
                        <Pencil size={11} />
                      </span>
                      <span
                        role="button"
                        onClick={(e) => handleDeleteClick(session.session_id, e)}
                        className="p-0.5 text-stone-300 hover:text-red-400 rounded opacity-0 group-hover:opacity-100 focus:opacity-100 sm:opacity-0 sm:group-hover:opacity-100 sm:focus:opacity-100 transition-all shrink-0 cursor-pointer"
                        title="删除会话"
                        aria-label={`删除会话 ${session.title}`}
                        tabIndex={0}
                        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && handleDeleteClick(session.session_id, e)}
                      >
                        <Trash2 size={11} />
                      </span>
                    </>
                  )}
                </>
              )}
            </div>
          )
        })}
      </div>

      <ConfirmDialog
        open={pendingDeleteId !== null}
        title={pendingDeleteId === 'batch' ? '批量删除会话' : '删除会话'}
        message={pendingDeleteId === 'batch'
          ? `确定要删除选中的 ${selectedIds.size} 个会话吗？此操作不可撤销，会话中的所有消息和结果将被永久删除。`
          : '确定要删除这个会话吗？此操作不可撤销，会话中的所有消息和结果将被永久删除。'}
        confirmLabel={deleting ? '删除中...' : '确认删除'}
        onConfirm={handleDeleteConfirm}
        onCancel={handleDeleteCancel}
      />
    </>
  )
}

export default React.memo(SessionList)
