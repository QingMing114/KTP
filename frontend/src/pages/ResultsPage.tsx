import React, { useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useAppContext } from '../context/AppContext'
import { useArtifactClick } from '../hooks/useArtifactClick'
import { Sparkles, ArrowLeft, Check, ExternalLink, Bot, Clock, AlertTriangle, X, Search, Loader2 } from 'lucide-react'
import { escapeHtml, buildArtifactOpenHref, isMockArtifact, getArtifactLabel, truncateId, getStatusLabel, getStatusStyle } from '../utils'
import SimulationArtifact from '../components/SimulationArtifact'

const ResultsPage: React.FC = () => {
  const { state } = useAppContext()
  const { artifactError, handleArtifactClick, clearArtifactError } = useArtifactClick()
  const [searchQuery, setSearchQuery] = useState('')

  const runsWithArtifacts = useMemo(() => {
    return (state.sessionRuns || []).filter((run) => {
      const parts = run.assistant_message?.parts || []
      return parts.some((part) => part.type === 'artifact' && part.artifact)
    })
  }, [state.sessionRuns])

  const filteredRuns = useMemo(() => {
    if (!searchQuery) return runsWithArtifacts
    const q = searchQuery.toLowerCase()
    return runsWithArtifacts.filter((run) => {
      if ((run.input_message || '').toLowerCase().includes(q)) return true
      if ((run.run_id || '').toLowerCase().includes(q)) return true
      const parts = run.assistant_message?.parts || []
      return parts.some((part) => {
        if (part.type === 'artifact' && part.artifact) {
          if ((part.artifact.title || '').toLowerCase().includes(q)) return true
          if ((part.artifact.content || '').toLowerCase().includes(q)) return true
        }
        return false
      })
    })
  }, [runsWithArtifacts, searchQuery])

  if (state.loading.sessions) {
    return (
      <div className="flex-1 flex items-center justify-center bg-stone-50">
        <div className="flex flex-col items-center gap-3">
          <Loader2 size={24} className="text-stone-400 animate-spin" />
          <span className="text-sm text-stone-400">加载结果中...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-auto bg-stone-50">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <div className="mb-6 sm:mb-8">
          <h1 className="text-xl sm:text-2xl font-semibold text-stone-700 mb-1">分析结果</h1>
          <p className="text-sm text-stone-400">查看所有分析产物和报告</p>
        </div>

        <div className="relative mb-6">
          <Search className="absolute left-3.5 top-1/2 transform -translate-y-1/2 text-stone-300" size={16} />
          <input
            type="text"
            placeholder="搜索结果、产物标题..."
            className="w-full pl-10 pr-4 py-2.5 bg-white border border-stone-200/80 rounded-xl text-sm focus:border-stone-300 outline-none transition-all placeholder:text-stone-300"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        {artifactError && (
          <div className="mb-4 bg-amber-50 border border-amber-200/60 text-amber-600 px-4 py-2.5 rounded-xl text-[13px] flex items-center justify-between">
            <span className="flex items-center gap-2"><AlertTriangle size={13} />{artifactError.message}</span>
            <button onClick={clearArtifactError} className="ml-3 text-amber-300 hover:text-amber-500 shrink-0"><X size={14} /></button>
          </div>
        )}

        {filteredRuns.length === 0 ? (
          <div className="bg-white border border-stone-200/60 rounded-xl p-12 text-center">
            <Sparkles size={32} className="text-stone-200 mx-auto mb-3" />
            <p className="text-stone-400 text-sm">
              {state.sessionRuns.length === 0
                ? '暂无分析结果，请先进行对话分析。'
                : searchQuery
                  ? '没有找到匹配的结果。'
                  : '当前会话暂无产物结果。'}
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {filteredRuns.map((run) => {
              const parts = run.assistant_message?.parts || []
              const artifacts = parts.filter((part) => part.type === 'artifact' && part.artifact)
              return (
                <div key={run.run_id} className="bg-white border border-stone-200/60 rounded-xl overflow-hidden">
                  <div className="px-4 sm:px-5 py-3 border-b border-stone-100 flex items-center justify-between">
                    <div className="flex items-center space-x-3 min-w-0">
                      <div className="p-1.5 bg-stone-100 text-stone-400 rounded-md shrink-0">
                        <Bot size={14} />
                      </div>
                      <div className="min-w-0">
                        <p className="text-[14px] font-medium text-stone-700 truncate">{escapeHtml(run.input_message || '未命名对话')}</p>
                        <div className="flex items-center space-x-3 mt-0.5">
                          <span className="text-[12px] text-stone-300 flex items-center"><Clock size={10} className="mr-1" />{truncateId(run.run_id)}</span>
                          <span className={`text-[11px] px-1.5 py-0.5 rounded-full ${getStatusStyle(run.status)}`}>{getStatusLabel(run.status)}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="p-4 sm:p-5">
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                      {artifacts.map((part, index) => {
                        const artifact = part.artifact!
                        if (artifact.artifact_type === "simulation_data" && artifact.content) {
                          return <SimulationArtifact key={index} title={artifact.title} content={artifact.content} />
                        }
                        const openHref = buildArtifactOpenHref(artifact)
                        const mock = isMockArtifact(artifact)
                        return (
                          <div key={index} className={`border rounded-lg p-3 transition-all ${mock ? 'border-amber-200/60 bg-amber-50/30' : 'border-stone-200/60 hover:border-stone-300'}`}>
                            <div className="flex items-center justify-between mb-2">
                              <div className={`p-1 rounded ${mock ? 'bg-amber-100/60 text-amber-400' : 'bg-stone-100 text-stone-400'}`}>
                                <Sparkles size={13} />
                              </div>
                              <div className="flex items-center gap-1">
                                {mock && <span className="text-[10px] bg-amber-100/60 text-amber-600 px-1.5 py-0.5 rounded-full font-medium">Mock</span>}
                                {artifact.artifact_type && !mock && (
                                  <span className="text-[10px] bg-stone-100 text-stone-400 px-1.5 py-0.5 rounded-full">{artifact.artifact_type}</span>
                                )}
                              </div>
                            </div>
                            <h4 className="text-[13px] font-medium text-stone-700 mb-1 truncate">{escapeHtml(artifact.title || '未命名产物')}</h4>
                            {artifact.content && (
                              <p className="text-[12px] text-stone-400 line-clamp-2 mb-2">{escapeHtml(artifact.content)}</p>
                            )}
                            {openHref && (
                              <button
                                onClick={() => handleArtifactClick(openHref)}
                                className="inline-flex items-center gap-1 text-[13px] font-medium text-stone-500 hover:text-stone-700 transition-colors"
                              >
                                <ExternalLink size={11} /> {getArtifactLabel(artifact)}
                              </button>
                            )}
                            {mock && !openHref && (
                              <span className="text-[11px] text-stone-400">模拟产物，关闭模拟后可生成真实文件</span>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}

        <div className="flex justify-between gap-4 mt-8">
          <Link
            to="/analysis"
            className="flex items-center space-x-2 text-stone-400 hover:text-stone-600 text-[14px] font-medium transition-colors"
          >
            <ArrowLeft size={14} /> <span>返回分析</span>
          </Link>
          <Link
            to="/"
            className="flex items-center space-x-2 bg-stone-700 text-white rounded-lg px-4 py-2 text-[14px] font-medium hover:bg-stone-800 transition-colors"
          >
            <span>完成</span> <Check size={14} />
          </Link>
        </div>
      </div>
    </div>
  )
}

export default ResultsPage
