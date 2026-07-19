import React, { useState, useRef } from 'react'
import { Layers, Plus, Trash2, Play, Loader2, AlertCircle, CheckCircle, XCircle, X, Upload } from 'lucide-react'
import * as api from '../services/api'
import { REGIONS, CROP_TYPES, TASK_TYPES } from '../constants/agriculture'

interface BatchTask {
  id: string
  region: string
  crop_type: string
  task_type: string
  image_path: string
  use_mock: boolean
  status: 'pending' | 'running' | 'completed' | 'failed'
  message?: string
  confidence?: number
}

const BatchAnalysisPage: React.FC = () => {
  const [tasks, setTasks] = useState<BatchTask[]>([])
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [batchResult, setBatchResult] = useState<{ total: number; succeeded: number; failed: number } | null>(null)
  const taskIdRef = useRef(0)

  const addTask = () => {
    taskIdRef.current++
    setTasks(prev => [...prev, {
      id: `task-${taskIdRef.current}`,
      region: 'henan',
      crop_type: 'wheat',
      task_type: 'crop_health_detection',
      image_path: '',
      use_mock: false,
      status: 'pending',
    }])
  }

  const addMultipleTasks = () => {
    const newTasks: BatchTask[] = []
    for (const region of REGIONS.slice(0, 3)) {
      for (const crop of CROP_TYPES.slice(0, 2)) {
        taskIdRef.current++
        newTasks.push({
          id: `task-${taskIdRef.current}`,
          region: region.id,
          crop_type: crop.id,
          task_type: 'crop_health_detection',
          image_path: '',
          use_mock: false,
          status: 'pending',
        })
      }
    }
    setTasks(prev => [...prev, ...newTasks])
  }

  const removeTask = (id: string) => {
    setTasks(prev => prev.filter(t => t.id !== id))
  }

  const updateTask = (id: string, field: string, value: string | boolean) => {
    setTasks(prev => prev.map(t => t.id === id ? { ...t, [field]: value } : t))
  }

  const handleFileSelect = (id: string, file: File) => {
    updateTask(id, 'image_path', file.name)
  }

  const runBatch = async () => {
    if (tasks.length === 0) return
    setRunning(true)
    setError(null)
    setBatchResult(null)

    setTasks(prev => prev.map(t => ({ ...t, status: 'pending' as const })))

    const taskPayloads = tasks.map(t => ({
      region: t.region,
      crop_type: t.crop_type,
      task_type: t.task_type,
      image_path: t.image_path || undefined,
      use_mock: t.use_mock,
    }))

    try {
      setTasks(prev => prev.map(t => ({ ...t, status: 'running' as const })))
      const result = await api.batchInference(taskPayloads)
      setBatchResult({ total: result.total, succeeded: result.succeeded, failed: result.failed })

      setTasks(prev => prev.map((t, idx) => {
        const r = result.results[idx]
        if (!r) return t
        return {
          ...t,
          status: r.success ? 'completed' as const : 'failed' as const,
          message: r.message,
          confidence: r.result ? (r.result as Record<string, unknown>).confidence as number : undefined,
        }
      }))
    } catch (err) {
      setError('批量分析失败: ' + (err instanceof Error ? err.message : String(err)))
      setTasks(prev => prev.map(t => t.status === 'running' ? { ...t, status: 'failed' as const, message: '请求失败' } : t))
    } finally {
      setRunning(false)
    }
  }

  const clearAll = () => {
    setTasks([])
    setBatchResult(null)
    setError(null)
  }

  const pendingCount = tasks.filter(t => t.status === 'pending').length
  const completedCount = tasks.filter(t => t.status === 'completed').length
  const failedCount = tasks.filter(t => t.status === 'failed').length

  return (
    <div className="flex-1 overflow-auto bg-stone-50">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Layers size={24} className="text-stone-500" />
            <h1 className="text-xl font-semibold text-stone-800">批量分析</h1>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={addMultipleTasks}
              className="px-3 py-2 text-sm font-medium text-stone-600 bg-stone-100 hover:bg-stone-200 rounded-lg transition-colors"
            >
              快速添加示例
            </button>
            <button
              onClick={addTask}
              className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-white bg-stone-700 hover:bg-stone-800 rounded-lg transition-colors"
            >
              <Plus size={14} />
              添加任务
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-4 flex items-center gap-2 px-3 py-2.5 bg-red-50 text-red-600 text-sm rounded-lg border border-red-200/60">
            <AlertCircle size={14} />
            <span className="flex-1">{error}</span>
            <button onClick={() => setError(null)} className="text-red-400 hover:text-red-600"><X size={14} /></button>
          </div>
        )}

        {batchResult && (
          <div className="mb-4 grid grid-cols-3 gap-3">
            <div className="bg-stone-50 rounded-lg border border-stone-200/60 p-3 text-center">
              <p className="text-lg font-semibold text-stone-800">{batchResult.total}</p>
              <p className="text-xs text-stone-400">总任务</p>
            </div>
            <div className="bg-emerald-50 rounded-lg border border-emerald-200/60 p-3 text-center">
              <p className="text-lg font-semibold text-emerald-700">{batchResult.succeeded}</p>
              <p className="text-xs text-emerald-500">成功</p>
            </div>
            <div className="bg-red-50 rounded-lg border border-red-200/60 p-3 text-center">
              <p className="text-lg font-semibold text-red-700">{batchResult.failed}</p>
              <p className="text-xs text-red-500">失败</p>
            </div>
          </div>
        )}

        {!batchResult && tasks.length > 0 && (
          <div className="mb-4 grid grid-cols-3 gap-3">
            <div className="bg-white rounded-lg border border-stone-200/60 p-3 text-center">
              <p className="text-lg font-semibold text-stone-800">{pendingCount}</p>
              <p className="text-xs text-stone-400">待执行</p>
            </div>
            <div className="bg-white rounded-lg border border-stone-200/60 p-3 text-center">
              <p className="text-lg font-semibold text-stone-800">{completedCount}</p>
              <p className="text-xs text-stone-400">已完成</p>
            </div>
            <div className="bg-white rounded-lg border border-stone-200/60 p-3 text-center">
              <p className="text-lg font-semibold text-stone-800">{failedCount}</p>
              <p className="text-xs text-stone-400">失败</p>
            </div>
          </div>
        )}

        {tasks.length > 0 && (
          <div className="mb-4 flex items-center gap-2">
            <button
              onClick={runBatch}
              disabled={running || pendingCount === 0}
              className="flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium text-white bg-stone-700 hover:bg-stone-800 rounded-lg transition-colors disabled:opacity-50"
            >
              {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
              {running ? '执行中...' : `执行全部 (${pendingCount})`}
            </button>
            <button
              onClick={clearAll}
              className="px-4 py-2.5 text-sm font-medium text-stone-600 bg-stone-100 hover:bg-stone-200 rounded-lg transition-colors"
            >
              清空
            </button>
          </div>
        )}

        {tasks.length === 0 ? (
          <div className="text-center py-16">
            <Layers size={32} className="mx-auto text-stone-300 mb-3" />
            <p className="text-sm text-stone-400 mb-1">暂无批量任务</p>
            <p className="text-xs text-stone-300">点击"添加任务"或"快速添加示例"开始</p>
          </div>
        ) : (
          <div className="space-y-2">
            {tasks.map(task => (
              <div key={task.id} className={`bg-white rounded-lg border p-3 flex items-center gap-3 ${task.status === 'completed' ? 'border-emerald-200/60' : task.status === 'failed' ? 'border-red-200/60' : 'border-stone-200/60'}`}>
                <div className="shrink-0">
                  {task.status === 'pending' && <div className="w-2 h-2 bg-stone-300 rounded-full" />}
                  {task.status === 'running' && <Loader2 size={14} className="animate-spin text-blue-500" />}
                  {task.status === 'completed' && <CheckCircle size={14} className="text-emerald-500" />}
                  {task.status === 'failed' && <XCircle size={14} className="text-red-500" />}
                </div>
                <div className="flex-1 grid grid-cols-5 gap-2 items-center">
                  <select
                    value={task.region}
                    onChange={(e) => updateTask(task.id, 'region', e.target.value)}
                    disabled={running}
                    className="px-2 py-1.5 text-xs bg-white border border-stone-200 rounded text-stone-600 focus:border-stone-400 outline-none disabled:opacity-50"
                  >
                    {REGIONS.map(r => <option key={r.id} value={r.id}>{r.label}</option>)}
                  </select>
                  <select
                    value={task.crop_type}
                    onChange={(e) => updateTask(task.id, 'crop_type', e.target.value)}
                    disabled={running}
                    className="px-2 py-1.5 text-xs bg-white border border-stone-200 rounded text-stone-600 focus:border-stone-400 outline-none disabled:opacity-50"
                  >
                    {CROP_TYPES.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}
                  </select>
                  <select
                    value={task.task_type}
                    onChange={(e) => updateTask(task.id, 'task_type', e.target.value)}
                    disabled={running}
                    className="px-2 py-1.5 text-xs bg-white border border-stone-200 rounded text-stone-600 focus:border-stone-400 outline-none disabled:opacity-50"
                  >
                    {TASK_TYPES.map(t => <option key={t.id} value={t.id}>{t.label}</option>)}
                  </select>
                  <label className="flex items-center gap-1.5 px-2 py-1.5 text-xs border border-stone-200 rounded cursor-pointer hover:bg-stone-50 overflow-hidden disabled:opacity-50">
                    <Upload size={10} className="shrink-0 text-stone-400" />
                    <span className="truncate text-stone-500">{task.image_path || '选择影像'}</span>
                    <input
                      type="file"
                      accept=".tif,.tiff,.png,.jpg,.jpeg"
                      onChange={(e) => {
                        const f = e.target.files?.[0]
                        if (f) handleFileSelect(task.id, f)
                      }}
                      disabled={running}
                      className="hidden"
                    />
                  </label>
                  <div className="flex items-center gap-2">
                    <label className="flex items-center gap-1 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={task.use_mock}
                        onChange={(e) => updateTask(task.id, 'use_mock', e.target.checked)}
                        disabled={running}
                        className="w-3 h-3 rounded border-stone-300"
                      />
                      <span className="text-[10px] text-stone-400">模拟</span>
                    </label>
                    {task.confidence !== undefined && (
                      <span className="text-[10px] text-stone-400">{(task.confidence * 100).toFixed(1)}%</span>
                    )}
                    {task.message && task.status === 'failed' && (
                      <span className="text-[10px] text-red-400 truncate max-w-[100px]" title={task.message}>{task.message}</span>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => removeTask(task.id)}
                  disabled={running}
                  className="p-1 text-stone-300 hover:text-red-500 rounded transition-colors disabled:opacity-50 shrink-0"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default BatchAnalysisPage
