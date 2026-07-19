import React, { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { Database, Plus, ArrowLeft, X, Loader2, Search, MapPin, FileCode, Clock } from 'lucide-react'
import { escapeHtml, formatRelativeTime } from '../utils'
import { Dataset } from '../types'
import { listDatasets, createDataset } from '../services/canonical'

const DATA_TYPE_LABELS: Record<string, string> = {
  raster: '栅格影像',
  vector: '矢量数据',
  tabular: '表格数据',
  text: '文本数据',
  model: '模型文件',
  other: '其他',
}

const DatasetsPage: React.FC = () => {
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [showRegister, setShowRegister] = useState(false)
  const [registering, setRegistering] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [regForm, setRegForm] = useState({
    name: '',
    description: '',
    data_type: 'raster',
    region: '',
    source_path: '',
  })

  const loadDatasets = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listDatasets()
      setDatasets(data.map(d => ({
        dataset_id: d.dataset_id,
        name: d.display_name,
        description: (d.metadata as Record<string, unknown>)?.['description'] as string ?? undefined,
        data_type: (d.metadata as Record<string, unknown>)?.['data_type'] as string ?? undefined,
        region: (d.metadata as Record<string, unknown>)?.['region'] as string ?? undefined,
        source_path: d.source?.uri ?? undefined,
        created_at: d.created_at,
        updated_at: d.created_at,
      })))
    } catch {
      setDatasets([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadDatasets()
  }, [loadDatasets])

  const filteredDatasets = searchQuery
    ? datasets.filter((d) => {
        const q = searchQuery.toLowerCase()
        return d.name.toLowerCase().includes(q) ||
          (d.description || '').toLowerCase().includes(q) ||
          (d.region || '').toLowerCase().includes(q) ||
          (d.data_type || '').toLowerCase().includes(q)
      })
    : datasets

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault()
    if (!regForm.name.trim()) {
      setError('请输入数据集名称')
      return
    }
    setRegistering(true)
    setError(null)
    try {
      await createDataset({
        display_name: regForm.name.trim(),
        source: { uri: regForm.source_path.trim() || regForm.name.trim(), kind: 'local_path' },
        metadata: {
          description: regForm.description.trim() || undefined,
          data_type: regForm.data_type || undefined,
          region: regForm.region.trim() || undefined,
        } as Record<string, unknown>,
      })
      setRegForm({ name: '', description: '', data_type: 'raster', region: '', source_path: '' })
      setShowRegister(false)
      loadDatasets()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '操作失败')
    } finally {
      setRegistering(false)
    }
  }

  return (
    <div className="flex-1 overflow-auto bg-stone-50">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <div className="flex items-start justify-between mb-6 sm:mb-8">
          <div>
            <h1 className="text-xl sm:text-2xl font-semibold text-stone-700 mb-1">数据集</h1>
            <p className="text-sm text-stone-400">管理和浏览遥感数据集</p>
          </div>
          <button
            onClick={() => setShowRegister(true)}
            className="flex items-center gap-2 px-4 py-2 bg-stone-700 text-white rounded-lg text-[13px] font-medium hover:bg-stone-800 transition-colors"
          >
            <Plus size={14} />
            注册数据集
          </button>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-6">
          <div className="bg-white p-3 rounded-xl border border-stone-200/60 flex items-center space-x-2.5">
            <div className="p-1.5 bg-stone-100 text-stone-500 rounded-lg">
              <Database size={16} />
            </div>
            <div>
              <p className="text-[10px] text-stone-400">总数据集</p>
              <p className="text-lg font-bold text-stone-700">{datasets.length}</p>
            </div>
          </div>
          <div className="bg-white p-3 rounded-xl border border-stone-200/60 flex items-center space-x-2.5">
            <div className="p-1.5 bg-stone-100 text-stone-500 rounded-lg">
              <MapPin size={16} />
            </div>
            <div>
              <p className="text-[10px] text-stone-400">区域</p>
              <p className="text-lg font-bold text-stone-700">{new Set(datasets.filter(d => d.region).map(d => d.region)).size}</p>
            </div>
          </div>
          <div className="bg-white p-3 rounded-xl border border-stone-200/60 flex items-center space-x-2.5 col-span-2 sm:col-span-1">
            <div className="p-1.5 bg-stone-100 text-stone-500 rounded-lg">
              <FileCode size={16} />
            </div>
            <div>
              <p className="text-[10px] text-stone-400">类型</p>
              <p className="text-lg font-bold text-stone-700">{new Set(datasets.filter(d => d.data_type).map(d => d.data_type)).size}</p>
            </div>
          </div>
        </div>

        <div className="relative mb-6">
          <Search className="absolute left-3.5 top-1/2 transform -translate-y-1/2 text-stone-300" size={16} />
          <input
            type="text"
            placeholder="搜索数据集名称、区域、类型..."
            className="w-full pl-10 pr-4 py-2.5 bg-white border border-stone-200/80 rounded-xl text-sm focus:border-stone-300 outline-none transition-all placeholder:text-stone-300"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={24} className="text-stone-400 animate-spin" />
          </div>
        ) : filteredDatasets.length === 0 ? (
          <div className="bg-white border border-stone-200/60 rounded-xl p-12 text-center">
            <Database size={32} className="text-stone-200 mx-auto mb-3" />
            <p className="text-stone-400 text-sm">
              {datasets.length === 0 ? '暂无数据集，点击上方按钮注册。' : '没有找到匹配的数据集。'}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {filteredDatasets.map((dataset) => (
              <div key={dataset.dataset_id} className="bg-white rounded-xl border border-stone-200/60 hover:border-stone-300 transition-all p-4">
                <div className="flex items-start justify-between gap-2 mb-2">
                  <h3 className="font-medium text-stone-700 text-[14px] truncate">{escapeHtml(dataset.name)}</h3>
                  {dataset.data_type && (
                    <span className="text-[10px] bg-stone-100 text-stone-500 px-2 py-0.5 rounded-full shrink-0">
                      {DATA_TYPE_LABELS[dataset.data_type] || dataset.data_type}
                    </span>
                  )}
                </div>
                {dataset.description && (
                  <p className="text-[13px] text-stone-400 mb-3 line-clamp-2">{escapeHtml(dataset.description)}</p>
                )}
                <div className="flex items-center gap-3 text-[11px] text-stone-300">
                  {dataset.region && (
                    <span className="flex items-center gap-1"><MapPin size={10} />{escapeHtml(dataset.region)}</span>
                  )}
                  {dataset.created_at && (
                    <span className="flex items-center gap-1"><Clock size={10} />{formatRelativeTime(dataset.created_at)}</span>
                  )}
                  <span className="font-mono">{dataset.dataset_id.slice(0, 8)}</span>
                </div>
              </div>
            ))}
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

      {showRegister && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-stone-900/20 backdrop-blur-sm"
          onClick={() => setShowRegister(false)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="register-dataset-title"
            className="bg-white rounded-xl shadow-xl border border-stone-200 w-full max-w-md mx-4"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-stone-100">
              <h2 id="register-dataset-title" className="text-sm font-semibold text-stone-700">注册数据集</h2>
              <button onClick={() => setShowRegister(false)} className="p-1 text-stone-400 hover:text-stone-600 rounded-lg transition-colors" aria-label="关闭">
                <X size={16} />
              </button>
            </div>
            <form onSubmit={handleRegister} className="p-5 space-y-4">
              <div>
                <label htmlFor="ds-name" className="block text-[12px] font-medium text-stone-500 mb-1.5">名称 *</label>
                <input
                  id="ds-name"
                  type="text"
                  value={regForm.name}
                  onChange={(e) => setRegForm({ ...regForm, name: e.target.value })}
                  placeholder="如：河南小麦多光谱数据集"
                  className="w-full px-3 py-2 text-[13px] bg-stone-50 border border-stone-200 rounded-lg text-stone-700 placeholder:text-stone-300 focus:border-stone-400 focus:bg-white outline-none transition-colors"
                />
              </div>
              <div>
                <label htmlFor="ds-desc" className="block text-[12px] font-medium text-stone-500 mb-1.5">描述</label>
                <textarea
                  id="ds-desc"
                  value={regForm.description}
                  onChange={(e) => setRegForm({ ...regForm, description: e.target.value })}
                  placeholder="数据集的简要描述"
                  rows={2}
                  className="w-full px-3 py-2 text-[13px] bg-stone-50 border border-stone-200 rounded-lg text-stone-700 placeholder:text-stone-300 focus:border-stone-400 focus:bg-white outline-none transition-colors resize-none"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label htmlFor="ds-type" className="block text-[12px] font-medium text-stone-500 mb-1.5">数据类型</label>
                  <select
                    id="ds-type"
                    value={regForm.data_type}
                    onChange={(e) => setRegForm({ ...regForm, data_type: e.target.value })}
                    className="w-full px-3 py-2 text-[13px] bg-stone-50 border border-stone-200 rounded-lg text-stone-700 focus:border-stone-400 focus:bg-white outline-none transition-colors"
                  >
                    <option value="raster">栅格影像</option>
                    <option value="vector">矢量数据</option>
                    <option value="tabular">表格数据</option>
                    <option value="text">文本数据</option>
                    <option value="model">模型文件</option>
                    <option value="other">其他</option>
                  </select>
                </div>
                <div>
                  <label htmlFor="ds-region" className="block text-[12px] font-medium text-stone-500 mb-1.5">区域</label>
                  <input
                    id="ds-region"
                    type="text"
                    value={regForm.region}
                    onChange={(e) => setRegForm({ ...regForm, region: e.target.value })}
                    placeholder="如：河南省"
                    className="w-full px-3 py-2 text-[13px] bg-stone-50 border border-stone-200 rounded-lg text-stone-700 placeholder:text-stone-300 focus:border-stone-400 focus:bg-white outline-none transition-colors"
                  />
                </div>
              </div>
              <div>
                <label htmlFor="ds-path" className="block text-[12px] font-medium text-stone-500 mb-1.5">数据路径</label>
                <input
                  id="ds-path"
                  type="text"
                  value={regForm.source_path}
                  onChange={(e) => setRegForm({ ...regForm, source_path: e.target.value })}
                  placeholder="/data/datasets/..."
                  className="w-full px-3 py-2 text-[13px] bg-stone-50 border border-stone-200 rounded-lg text-stone-700 placeholder:text-stone-300 focus:border-stone-400 focus:bg-white outline-none transition-colors font-mono"
                />
              </div>
              {error && (
                <div className="text-[12px] text-red-500 bg-red-50 px-3 py-2 rounded-lg border border-red-100" role="alert">{error}</div>
              )}
              <button
                type="submit"
                disabled={registering}
                className="w-full flex items-center justify-center gap-2 py-2.5 text-[13px] font-medium text-white bg-stone-700 hover:bg-stone-800 rounded-lg transition-colors disabled:opacity-50"
              >
                {registering ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
                <span>{registering ? '注册中...' : '注册'}</span>
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

export default DatasetsPage
