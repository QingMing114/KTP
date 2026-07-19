import React, { useState, useEffect, useCallback } from 'react'
import { BookOpen, Plus, Trash2, Search, Loader2, FileText, X, Upload, ChevronDown, ChevronRight, AlertCircle, Sparkles, Filter } from 'lucide-react'
import { KnowledgeDocument, KnowledgeQueryResult } from '../types'
import * as api from '../services/api'

const KnowledgePage: React.FC = () => {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([])
  const [loading, setLoading] = useState(true)
  const [filterQuery, setFilterQuery] = useState('')
  const [semanticQuery, setSemanticQuery] = useState('')
  const [searchResults, setSearchResults] = useState<KnowledgeQueryResult[]>([])
  const [searching, setSearching] = useState(false)
  const [searchDone, setSearchDone] = useState(false)
  const [showIngest, setShowIngest] = useState(false)
  const [ingesting, setIngesting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)
  const [expandedDoc, setExpandedDoc] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [ingestFile, setIngestFile] = useState<File | null>(null)
  const [ingestForm, setIngestForm] = useState({
    document_id: '',
    title: '',
    source: 'web-upload',
    text: '',
  })

  const loadDocuments = useCallback(async () => {
    setLoading(true)
    try {
      const docs = await api.listKnowledgeDocuments()
      setDocuments(docs)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载文档失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadDocuments()
  }, [loadDocuments])

  const handleSemanticSearch = async () => {
    if (!semanticQuery.trim()) return
    setSearching(true)
    setSearchResults([])
    setSearchDone(false)
    setError(null)
    try {
      const result = await api.queryKnowledge({ query: semanticQuery, top_k: 5 })
      setSearchResults(result.results || [])
    } catch (err) {
      setError('语义搜索失败: ' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setSearching(false)
      setSearchDone(true)
    }
  }

  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)

  const handleDelete = (documentId: string) => {
    setConfirmDeleteId(documentId)
  }

  const confirmDelete = async () => {
    if (!confirmDeleteId) return
    const documentId = confirmDeleteId
    setConfirmDeleteId(null)
    setDeleting(documentId)
    try {
      await api.deleteKnowledgeDocument(documentId)
      setDocuments(docs => docs.filter(d => d.document_id !== documentId))
      setSuccessMsg('文档已删除')
      setTimeout(() => setSuccessMsg(null), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除失败')
    } finally {
      setDeleting(null)
    }
  }

  const handleIngest = async () => {
    if (!ingestForm.document_id.trim() || !ingestForm.title.trim() || !ingestForm.text.trim()) {
      setError('文档ID、标题和文本内容为必填项')
      return
    }
    setIngesting(true)
    setError(null)
    try {
      const result = await api.ingestKnowledgeDocument({
        document_id: ingestForm.document_id.trim(),
        title: ingestForm.title.trim(),
        source: ingestForm.source || 'web-upload',
        text: ingestForm.text,
        metadata: {},
      })
      setSuccessMsg(`文档摄取成功，共 ${result.chunk_count} 个分块`)
      setShowIngest(false)
      setIngestForm({ document_id: '', title: '', source: 'web-upload', text: '' })
      setIngestFile(null)
      loadDocuments()
      setTimeout(() => setSuccessMsg(null), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : '摄取失败')
    } finally {
      setIngesting(false)
    }
  }

  const handleFileUpload = async () => {
    if (!ingestFile) return
    setIngesting(true)
    setError(null)
    try {
      const text = await ingestFile.text()
      const docId = ingestFile.name.replace(/\.[^.]+$/, '').replace(/[^a-zA-Z0-9_-]/g, '_')
      const autoForm = {
        document_id: ingestForm.document_id || docId,
        title: ingestForm.title || ingestFile.name,
        text: ingestForm.text || text,
        source: 'web-upload',
      }
      setIngestForm(autoForm)
      await api.ingestKnowledgeDocument(autoForm)
      setSuccessMsg(`文档 "${autoForm.title}" 上传并摄取成功`)
      setIngestFile(null)
      setIngestForm({ document_id: '', title: '', text: '', source: 'web-upload' })
      loadDocuments()
      setTimeout(() => setSuccessMsg(null), 3000)
    } catch (err) {
      setError('文件上传失败: ' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setIngesting(false)
    }
  }

  const filteredDocs = documents.filter(doc => {
    if (!filterQuery.trim()) return true
    const q = filterQuery.toLowerCase()
    return (
      doc.title.toLowerCase().includes(q) ||
      doc.source.toLowerCase().includes(q) ||
      doc.document_id.toLowerCase().includes(q)
    )
  })

  const totalChunks = documents.reduce((sum, d) => sum + (d.chunk_count || 0), 0)

  return (
    <div className="flex-1 overflow-auto bg-stone-50">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <BookOpen size={24} className="text-stone-500" />
            <h1 className="text-xl font-semibold text-stone-800">知识库管理</h1>
          </div>
          <button
            onClick={() => setShowIngest(true)}
            className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-white bg-stone-700 hover:bg-stone-800 rounded-lg transition-colors"
          >
            <Plus size={14} />
            添加文档
          </button>
        </div>

        {error && (
          <div className="mb-4 flex items-center gap-2 px-3 py-2.5 bg-red-50 text-red-600 text-sm rounded-lg border border-red-200/60">
            <AlertCircle size={14} />
            <span className="flex-1">{error}</span>
            <button onClick={() => setError(null)} className="text-red-400 hover:text-red-600"><X size={14} /></button>
          </div>
        )}

        {successMsg && (
          <div className="mb-4 flex items-center gap-2 px-3 py-2.5 bg-emerald-50 text-emerald-600 text-sm rounded-lg border border-emerald-200/60">
            <span>{successMsg}</span>
          </div>
        )}

        <div className="grid grid-cols-3 gap-3 mb-6">
          <div className="bg-white rounded-lg border border-stone-200/60 p-4">
            <p className="text-2xl font-semibold text-stone-800">{documents.length}</p>
            <p className="text-xs text-stone-400 mt-1">文档总数</p>
          </div>
          <div className="bg-white rounded-lg border border-stone-200/60 p-4">
            <p className="text-2xl font-semibold text-stone-800">{totalChunks}</p>
            <p className="text-xs text-stone-400 mt-1">知识分块</p>
          </div>
          <div className="bg-white rounded-lg border border-stone-200/60 p-4">
            <p className="text-2xl font-semibold text-stone-800">{searchResults.length}</p>
            <p className="text-xs text-stone-400 mt-1">搜索结果</p>
          </div>
        </div>

        <div className="mb-6 bg-white rounded-xl border border-stone-200/60 p-4">
          <div className="flex items-center gap-2 mb-3">
            <Sparkles size={14} className="text-stone-500" />
            <span className="text-sm font-medium text-stone-700">语义搜索</span>
            <span className="text-[10px] text-stone-400">基于向量相似度，理解自然语言含义</span>
          </div>
          <div className="flex gap-2">
            <div className="flex-1 relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-300" />
              <input
                type="text"
                value={semanticQuery}
                onChange={(e) => setSemanticQuery(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleSemanticSearch() }}
                placeholder="输入自然语言查询，如：小麦生长的最佳温度是多少？"
                className="w-full pl-9 pr-3 py-2.5 text-sm bg-white border border-stone-200 rounded-lg text-stone-600 placeholder:text-stone-300 focus:border-stone-400 outline-none"
              />
            </div>
            <button
              onClick={handleSemanticSearch}
              disabled={searching || !semanticQuery.trim()}
              className="px-4 py-2.5 text-sm font-medium text-white bg-stone-700 hover:bg-stone-800 rounded-lg transition-colors disabled:opacity-50 flex items-center gap-1.5 shrink-0"
            >
              {searching ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
              搜索
            </button>
          </div>

          {searching && (
            <div className="mt-3 flex items-center gap-2 text-xs text-stone-400">
              <Loader2 size={12} className="animate-spin" />
              正在搜索知识库...
            </div>
          )}

          {searchDone && !searching && searchResults.length > 0 && (
            <div className="mt-3 space-y-2">
              <p className="text-xs text-stone-500 font-medium">找到 {searchResults.length} 条相关结果</p>
              {searchResults.map((result, idx) => (
                <div key={result.chunk_id} className="bg-stone-50 rounded-lg p-3 border border-stone-100">
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="text-xs font-medium text-stone-500">#{idx + 1}</span>
                    <span className="text-xs text-stone-400">来源: {result.source}</span>
                    <span className="text-xs text-stone-400">文档: {result.document_id}</span>
                    <span className="text-xs text-stone-400 ml-auto">相关度: {(result.score * 100).toFixed(1)}%</span>
                  </div>
                  <p className="text-sm text-stone-600 leading-relaxed whitespace-pre-wrap">{result.text}</p>
                </div>
              ))}
            </div>
          )}

          {searchDone && !searching && searchResults.length === 0 && semanticQuery && (
            <div className="mt-3 text-center py-4">
              <p className="text-xs text-stone-400">未找到与 "{semanticQuery}" 相关的内容</p>
              <p className="text-[10px] text-stone-300 mt-1">尝试使用不同的关键词或更具体的描述</p>
            </div>
          )}
        </div>

        <div className="mb-3">
          <div className="flex items-center gap-2">
            <Filter size={12} className="text-stone-400" />
            <span className="text-xs text-stone-500">文档列表</span>
            <div className="flex-1 relative">
              <input
                type="text"
                value={filterQuery}
                onChange={(e) => setFilterQuery(e.target.value)}
                placeholder="按标题/ID/来源过滤..."
                className="w-full px-3 py-1.5 text-xs bg-white border border-stone-200 rounded-lg text-stone-600 placeholder:text-stone-300 focus:border-stone-400 outline-none"
              />
            </div>
          </div>
        </div>

        {loading ? (
          <div className="space-y-3 p-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="bg-white rounded-lg border border-stone-200/60 p-4 space-y-2">
                <div className="animate-pulse bg-stone-200 rounded h-4 w-2/3" />
                <div className="animate-pulse bg-stone-200 rounded h-3 w-full" />
                <div className="animate-pulse bg-stone-200 rounded h-3 w-1/2" />
              </div>
            ))}
          </div>
        ) : filteredDocs.length === 0 ? (
          <div className="text-center py-12">
            <BookOpen size={32} className="mx-auto text-stone-300 mb-3" />
            <p className="text-sm text-stone-400">
              {filterQuery ? '没有找到匹配的文档' : '知识库为空，点击"添加文档"开始'}
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {filteredDocs.map((doc) => (
              <div key={doc.document_id} className="bg-white rounded-lg border border-stone-200/60 overflow-hidden">
                <div
                  className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-stone-50/50 transition-colors"
                  onClick={() => setExpandedDoc(expandedDoc === doc.document_id ? null : doc.document_id)}
                >
                  {expandedDoc === doc.document_id ? (
                    <ChevronDown size={14} className="text-stone-400 shrink-0" />
                  ) : (
                    <ChevronRight size={14} className="text-stone-400 shrink-0" />
                  )}
                  <FileText size={14} className="text-stone-400 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-stone-700 truncate">{doc.title}</p>
                    <p className="text-xs text-stone-400 truncate">{doc.document_id}</p>
                  </div>
                  <span className="text-xs text-stone-400 shrink-0">{doc.chunk_count || 0} 分块</span>
                  <span className="text-xs text-stone-400 shrink-0 hidden sm:inline">{doc.source}</span>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDelete(doc.document_id) }}
                    disabled={deleting === doc.document_id}
                    className="p-1.5 text-stone-300 hover:text-red-500 rounded transition-colors disabled:opacity-50 shrink-0"
                    title="删除文档"
                  >
                    {deleting === doc.document_id ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Trash2 size={14} />
                    )}
                  </button>
                </div>
                {expandedDoc === doc.document_id && (
                  <div className="px-4 pb-3 pt-1 border-t border-stone-100">
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div>
                        <span className="text-stone-400">文档ID: </span>
                        <span className="text-stone-600">{doc.document_id}</span>
                      </div>
                      <div>
                        <span className="text-stone-400">来源: </span>
                        <span className="text-stone-600">{doc.source}</span>
                      </div>
                      <div>
                        <span className="text-stone-400">分块数: </span>
                        <span className="text-stone-600">{doc.chunk_count}</span>
                      </div>
                      {doc.metadata && Object.keys(doc.metadata).length > 0 && (
                        <div className="col-span-2">
                          <span className="text-stone-400">元数据: </span>
                          <span className="text-stone-600">{JSON.stringify(doc.metadata)}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {showIngest && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-stone-900/30 backdrop-blur-sm">
            <div className="bg-white rounded-xl shadow-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
              <div className="flex items-center justify-between px-5 py-4 border-b border-stone-100">
                <h2 className="text-base font-semibold text-stone-800">添加知识文档</h2>
                <button onClick={() => { setShowIngest(false); setIngestFile(null) }} className="p-1 text-stone-400 hover:text-stone-600 rounded"><X size={16} /></button>
              </div>
              <div className="px-5 py-4 space-y-4">
                <div>
                  <label className="block text-xs font-medium text-stone-500 mb-1.5">上传文件（可选）</label>
                  <div className="flex gap-2">
                    <input
                      type="file"
                      accept=".txt,.md,.csv,.json"
                      onChange={(e) => setIngestFile(e.target.files?.[0] || null)}
                      className="flex-1 text-sm text-stone-600 file:mr-2 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-stone-100 file:text-stone-600 hover:file:bg-stone-200"
                    />
                    <button
                      onClick={handleFileUpload}
                      disabled={!ingestFile}
                      className="px-3 py-1.5 text-xs font-medium text-stone-600 bg-stone-100 hover:bg-stone-200 rounded-lg transition-colors disabled:opacity-50 flex items-center gap-1"
                    >
                      <Upload size={12} />
                      填入
                    </button>
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-medium text-stone-500 mb-1.5">文档ID <span className="text-red-400">*</span></label>
                  <input
                    type="text"
                    value={ingestForm.document_id}
                    onChange={(e) => setIngestForm(prev => ({ ...prev, document_id: e.target.value }))}
                    placeholder="唯一标识符，如 wheat-growth-guide"
                    className="w-full px-3 py-2 text-sm bg-white border border-stone-200 rounded-lg text-stone-600 placeholder:text-stone-300 focus:border-stone-400 outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-stone-500 mb-1.5">标题 <span className="text-red-400">*</span></label>
                  <input
                    type="text"
                    value={ingestForm.title}
                    onChange={(e) => setIngestForm(prev => ({ ...prev, title: e.target.value }))}
                    placeholder="文档标题"
                    className="w-full px-3 py-2 text-sm bg-white border border-stone-200 rounded-lg text-stone-600 placeholder:text-stone-300 focus:border-stone-400 outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-stone-500 mb-1.5">来源</label>
                  <input
                    type="text"
                    value={ingestForm.source}
                    onChange={(e) => setIngestForm(prev => ({ ...prev, source: e.target.value }))}
                    placeholder="来源标识"
                    className="w-full px-3 py-2 text-sm bg-white border border-stone-200 rounded-lg text-stone-600 placeholder:text-stone-300 focus:border-stone-400 outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-stone-500 mb-1.5">文本内容 <span className="text-red-400">*</span></label>
                  <textarea
                    value={ingestForm.text}
                    onChange={(e) => setIngestForm(prev => ({ ...prev, text: e.target.value }))}
                    placeholder="输入或粘贴文档文本内容..."
                    rows={8}
                    className="w-full px-3 py-2 text-sm bg-white border border-stone-200 rounded-lg text-stone-600 placeholder:text-stone-300 focus:border-stone-400 outline-none resize-y"
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2 px-5 py-4 border-t border-stone-100">
                <button
                  onClick={() => { setShowIngest(false); setIngestFile(null) }}
                  className="px-4 py-2 text-sm font-medium text-stone-600 bg-stone-100 hover:bg-stone-200 rounded-lg transition-colors"
                >
                  取消
                </button>
                <button
                  onClick={handleIngest}
                  disabled={ingesting}
                  className="px-4 py-2 text-sm font-medium text-white bg-stone-700 hover:bg-stone-800 rounded-lg transition-colors disabled:opacity-50 flex items-center gap-1.5"
                >
                  {ingesting ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                  摄取文档
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {confirmDeleteId && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={() => setConfirmDeleteId(null)}>
          <div className="bg-white rounded-xl shadow-lg p-6 max-w-sm mx-4" onClick={e => e.stopPropagation()}>
            <h3 className="text-base font-semibold text-stone-800 mb-2">确认删除</h3>
            <p className="text-sm text-stone-500 mb-4">确定删除文档 &ldquo;{confirmDeleteId}&rdquo; 吗？此操作不可撤销。</p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setConfirmDeleteId(null)} className="px-3 py-1.5 text-sm text-stone-600 bg-stone-100 hover:bg-stone-200 rounded-lg">取消</button>
              <button onClick={confirmDelete} className="px-3 py-1.5 text-sm text-white bg-red-600 hover:bg-red-700 rounded-lg">删除</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default KnowledgePage
