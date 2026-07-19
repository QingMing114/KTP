import React, { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { History as HistoryIcon, Search, Clock, Loader2, ChevronLeft, ChevronRight, ArrowLeft, MessageSquare } from 'lucide-react'
import { escapeHtml, getStatusLabel, getStatusStyle, truncateId } from '../utils'
import { RunSummary, Run, Session } from '../types'
import SimulationArtifact from '../components/SimulationArtifact'
import * as api from '../services/api'
import { listConversations } from '../services/canonical'

const STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '失败' },
  { value: 'running', label: '运行中' },
]

const HistoryPage: React.FC = () => {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [sessions, setSessions] = useState<Map<string, Session>>(new Map())
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [page, setPage] = useState(0)
  const [selectedRun, setSelectedRun] = useState<Run | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const pageSize = 20

  const loadRuns = useCallback(async () => {
    setLoading(true)
    try {
      const [result, sessionList] = await Promise.all([
        api.getAllRuns(pageSize, page * pageSize),
        listConversations(),
      ])
      setRuns(result.items || [])
      setTotal(result.total || 0)
      const sessionMap = new Map<string, Session>()
      for (const s of sessionList) {
        sessionMap.set(s.conversation_id, { session_id: s.conversation_id, title: s.title })
      }
      setSessions(sessionMap)
    } catch {
      setRuns([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [page])

  useEffect(() => {
    loadRuns()
  }, [loadRuns])

  const filteredRuns = searchQuery || statusFilter
    ? runs.filter((run) => {
        if (statusFilter && run.status !== statusFilter) return false
        if (searchQuery) {
          const q = searchQuery.toLowerCase()
          const sessionTitle = run.session_id ? sessions.get(run.session_id)?.title || '' : ''
          return (run.input_message || '').toLowerCase().includes(q) ||
            (run.run_id || '').toLowerCase().includes(q) ||
            sessionTitle.toLowerCase().includes(q)
        }
        return true
      })
    : runs

  const totalPages = Math.ceil(total / pageSize)

  async function handleRunClick(runId: string) {
    setLoadingDetail(true)
    try {
      const detail = await api.getRunDetail(runId)
      setSelectedRun(detail)
    } catch {
      setSelectedRun(null)
    } finally {
      setLoadingDetail(false)
    }
  }

  function formatTime(dateStr?: string): string {
    if (!dateStr) return ""
    const date = new Date(dateStr)
    if (isNaN(date.getTime())) return ""
    return date.toLocaleString("zh-CN", {
      month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit"
    })
  }

  function getSessionTitle(sessionId?: string): string | null {
    if (!sessionId) return null
    return sessions.get(sessionId)?.title || null
  }

  return (
    <div className="flex-1 overflow-auto bg-stone-50">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <div className="mb-6 sm:mb-8">
          <h1 className="text-xl sm:text-2xl font-semibold text-stone-700 mb-1">运行历史</h1>
          <p className="text-sm text-stone-400">查看所有会话的运行记录和状态</p>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-6">
          <div className="bg-white p-3 rounded-xl border border-stone-200/60 flex items-center space-x-2.5">
            <div className="p-1.5 bg-stone-100 text-stone-500 rounded-lg">
              <HistoryIcon size={16} />
            </div>
            <div>
              <p className="text-[10px] text-stone-400">总运行</p>
              <p className="text-lg font-bold text-stone-700">{total}</p>
            </div>
          </div>
          <div className="bg-white p-3 rounded-xl border border-emerald-200/60 flex items-center space-x-2.5">
            <div className="p-1.5 bg-emerald-50 text-emerald-500 rounded-lg">
              <Clock size={16} />
            </div>
            <div>
              <p className="text-[10px] text-stone-400">成功</p>
              <p className="text-lg font-bold text-stone-700">{runs.filter(r => r.status === 'completed').length}</p>
            </div>
          </div>
          <div className="bg-white p-3 rounded-xl border border-red-200/60 flex items-center space-x-2.5 col-span-2 sm:col-span-1">
            <div className="p-1.5 bg-red-50 text-red-500 rounded-lg">
              <HistoryIcon size={16} />
            </div>
            <div>
              <p className="text-[10px] text-stone-400">失败</p>
              <p className="text-lg font-bold text-stone-700">{runs.filter(r => r.status === 'failed').length}</p>
            </div>
          </div>
        </div>

        <div className="flex gap-3 mb-6">
          <div className="relative flex-1">
            <Search className="absolute left-3.5 top-1/2 transform -translate-y-1/2 text-stone-300" size={16} />
            <input
              type="text"
              placeholder="搜索运行消息、ID 或会话标题..."
              className="w-full pl-10 pr-4 py-2.5 bg-white border border-stone-200/80 rounded-xl text-sm focus:border-stone-300 outline-none transition-all placeholder:text-stone-300"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-2.5 bg-white border border-stone-200/80 rounded-xl text-sm text-stone-600 focus:border-stone-300 outline-none transition-colors"
          >
            {STATUS_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={24} className="text-stone-400 animate-spin" />
          </div>
        ) : filteredRuns.length === 0 ? (
          <div className="bg-white border border-stone-200/60 rounded-xl p-12 text-center">
            <HistoryIcon size={32} className="text-stone-200 mx-auto mb-3" />
            <p className="text-stone-400 text-sm">
              {total === 0 ? '暂无运行记录，开始对话后将自动记录。' : '没有找到匹配的运行记录。'}
            </p>
          </div>
        ) : (
          <>
            <div className="space-y-2">
              {filteredRuns.map((run) => {
                const sessionTitle = getSessionTitle(run.session_id)
                return (
                  <button
                    key={run.run_id}
                    onClick={() => handleRunClick(run.run_id)}
                    className={`w-full text-left bg-white rounded-xl border transition-all p-4 hover:border-stone-300 ${selectedRun?.run_id === run.run_id ? 'border-stone-400 shadow-sm' : 'border-stone-200/60'}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <p className="text-[14px] font-medium text-stone-700 truncate">
                          {sessionTitle || escapeHtml(run.input_message || '未命名对话')}
                        </p>
                        <div className="flex items-center gap-3 mt-1.5 text-[11px] text-stone-300">
                          {sessionTitle && run.input_message && (
                            <span className="truncate max-w-[200px]" title={run.input_message}>{escapeHtml(run.input_message)}</span>
                          )}
                          <span className="font-mono">{truncateId(run.run_id)}</span>
                          {run.session_id && (
                            <span className="flex items-center gap-0.5">
                              <MessageSquare size={9} />
                              {truncateId(run.session_id)}
                            </span>
                          )}
                          {run.created_at && <span className="flex items-center gap-1"><Clock size={9} />{formatTime(run.created_at)}</span>}
                        </div>
                      </div>
                      <span className={`text-[11px] px-2 py-0.5 rounded-full shrink-0 ${getStatusStyle(run.status)}`}>
                        {getStatusLabel(run.status)}
                      </span>
                    </div>
                  </button>
                )
              })}
            </div>

            {totalPages > 1 && (
              <div className="flex items-center justify-center gap-2 mt-6">
                <button
                  onClick={() => setPage(Math.max(0, page - 1))}
                  disabled={page === 0}
                  className="p-2 text-stone-400 hover:text-stone-600 rounded-lg hover:bg-stone-100 transition-colors disabled:opacity-30"
                >
                  <ChevronLeft size={16} />
                </button>
                <span className="text-[13px] text-stone-500">
                  {page + 1} / {totalPages}
                </span>
                <button
                  onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
                  disabled={page >= totalPages - 1}
                  className="p-2 text-stone-400 hover:text-stone-600 rounded-lg hover:bg-stone-100 transition-colors disabled:opacity-30"
                >
                  <ChevronRight size={16} />
                </button>
              </div>
            )}
          </>
        )}

        {selectedRun && (
          <div className="mt-6 bg-white border border-stone-200/60 rounded-xl overflow-hidden">
            <div className="px-5 py-3 border-b border-stone-100 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-stone-700">运行详情</h3>
              <button onClick={() => setSelectedRun(null)} className="text-[12px] text-stone-400 hover:text-stone-600 transition-colors">关闭</button>
            </div>
            {loadingDetail ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 size={16} className="text-stone-400 animate-spin" />
              </div>
            ) : (
              <div className="p-5 space-y-3">
                <div className="grid grid-cols-2 gap-3 text-[13px]">
                  <div>
                    <p className="text-stone-400 text-[11px] mb-0.5">运行 ID</p>
                    <p className="text-stone-700 font-mono">{selectedRun.run_id}</p>
                  </div>
                  <div>
                    <p className="text-stone-400 text-[11px] mb-0.5">状态</p>
                    <span className={`text-[11px] px-2 py-0.5 rounded-full ${getStatusStyle(selectedRun.status)}`}>{getStatusLabel(selectedRun.status)}</span>
                  </div>
                  {selectedRun.session_id && (
                    <div>
                      <p className="text-stone-400 text-[11px] mb-0.5">会话</p>
                      <p className="text-stone-700">{getSessionTitle(selectedRun.session_id) || truncateId(selectedRun.session_id)}</p>
                    </div>
                  )}
                  {selectedRun.model_name && (
                    <div>
                      <p className="text-stone-400 text-[11px] mb-0.5">模型</p>
                      <p className="text-stone-700">{selectedRun.model_name}</p>
                    </div>
                  )}
                  {selectedRun.token_usage && (
                    <div>
                      <p className="text-stone-400 text-[11px] mb-0.5">Token 用量</p>
                      <p className="text-stone-700">↑{selectedRun.token_usage.input_tokens} ↓{selectedRun.token_usage.output_tokens}</p>
                    </div>
                  )}
                </div>
                {selectedRun.input_message && (
                  <div>
                    <p className="text-stone-400 text-[11px] mb-1">输入</p>
                    <p className="text-[13px] text-stone-600 bg-stone-50 rounded-lg p-3 whitespace-pre-wrap">{escapeHtml(selectedRun.input_message)}</p>
                  </div>
                )}
                {selectedRun.output_message && (
                  <div>
                    <p className="text-stone-400 text-[11px] mb-1">输出</p>
                    <p className="text-[13px] text-stone-600 bg-stone-50 rounded-lg p-3 max-h-48 overflow-y-auto whitespace-pre-wrap">{escapeHtml(selectedRun.output_message)}</p>
                  </div>
                )}
                {selectedRun.assistant_message?.parts?.filter(p => p.type === 'artifact' && p.artifact).length ? (
                  <div>
                    <p className="text-stone-400 text-[11px] mb-1">产物 ({selectedRun.assistant_message.parts.filter(p => p.type === 'artifact').length})</p>
                    <div className="space-y-1.5">
                      {selectedRun.assistant_message.parts.filter(p => p.type === 'artifact' && p.artifact).map((part, i) => (
                        part.artifact!.artifact_type === "simulation_data" && part.artifact!.content ? (
                          <SimulationArtifact key={i} title={part.artifact!.title} content={part.artifact!.content} />
                        ) : (
                          <div key={i} className="text-[12px] bg-stone-50 rounded-lg px-3 py-2 text-stone-600">
                            {escapeHtml(part.artifact!.title || '未命名产物')}
                            {part.artifact!.artifact_type && <span className="ml-2 text-stone-400">({part.artifact!.artifact_type})</span>}
                          </div>
                        )
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            )}
          </div>
        )}

        <div className="flex justify-between gap-4 mt-8">
          <Link
            to="/"
            className="flex items-center space-x-2 text-stone-400 hover:text-stone-600 rounded-lg text-[14px] font-medium transition-colors"
          >
            <ArrowLeft size={14} /> <span>返回对话</span>
          </Link>
        </div>
      </div>
    </div>
  )
}

export default HistoryPage
