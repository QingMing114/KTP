import React, { useState, useRef } from 'react'
import { Image, Upload, Loader2, X, AlertCircle, CheckCircle, MapPin, BarChart3, Eye } from 'lucide-react'
import * as api from '../services/api'
import { REGIONS, CROP_TYPES, TASK_TYPES } from '../constants/agriculture'

interface InferenceResult {
  request_id: string
  success: boolean
  message: string
  result?: {
    mask_uri: string
    affected_area: number
    confidence: number
    model_name: string
    model_version: string
    artifact_uri: string
    class_distribution?: Array<{ class_value: number; label?: string; count: number; ratio: number; mean_confidence?: number }>
    class_labels?: Record<string, string>
    polygons?: Array<{ id: string; points: Array<[number, number]> }>
  }
}

const ImageAnalysisPage: React.FC = () => {
  const [uploadedFile, setUploadedFile] = useState<File | null>(null)
  const [uploadedPath, setUploadedPath] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [result, setResult] = useState<InferenceResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [form, setForm] = useState({
    region: 'henan',
    crop_type: 'wheat',
    task_type: 'baldness_detection',
    use_mock: false,
  })
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileSelect = async (file: File) => {
    setUploadedFile(file)
    setError(null)
    setResult(null)

    if (file.type.startsWith('image/')) {
      const url = URL.createObjectURL(file)
      setPreviewUrl(url)
    } else {
      setPreviewUrl(null)
    }

    setUploading(true)
    try {
      const uploadResult = await api.uploadFile(file)
      setUploadedPath(uploadResult.path)
    } catch (err) {
      setError('文件上传失败: ' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setUploading(false)
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file) handleFileSelect(file)
  }

  const handleAnalyze = async () => {
    if (!uploadedPath) {
      setError('请先上传影像文件')
      return
    }
    setAnalyzing(true)
    setError(null)
    setResult(null)
    try {
      const inferenceResult = await api.runInference({
        image_path: uploadedPath,
        region: form.region,
        crop_type: form.crop_type,
        task_type: form.task_type,
        use_mock: form.use_mock,
      })
      setResult(inferenceResult)
    } catch (err) {
      setError('分析失败: ' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setAnalyzing(false)
    }
  }

  const handleReset = () => {
    setUploadedFile(null)
    setUploadedPath(null)
    setPreviewUrl(null)
    setResult(null)
    setError(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const formatConfidence = (val: number) => {
    return (val * 100).toFixed(1) + '%'
  }

  return (
    <div className="flex-1 overflow-auto bg-stone-50">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-6">
        <div className="flex items-center gap-3 mb-6">
          <Image size={24} className="text-stone-500" />
          <h1 className="text-xl font-semibold text-stone-800">影像分析</h1>
        </div>

        {error && (
          <div className="mb-4 flex items-center gap-2 px-3 py-2.5 bg-red-50 text-red-600 text-sm rounded-lg border border-red-200/60">
            <AlertCircle size={14} />
            <span className="flex-1">{error}</span>
            <button onClick={() => setError(null)} className="text-red-400 hover:text-red-600"><X size={14} /></button>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="space-y-4">
            <div
              onDrop={handleDrop}
              onDragOver={(e) => e.preventDefault()}
              className="relative border-2 border-dashed border-stone-200 rounded-xl bg-white hover:border-stone-300 transition-colors cursor-pointer"
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".tif,.tiff,.png,.jpg,.jpeg,.bmp,.img"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) handleFileSelect(file)
                }}
              />
              {previewUrl ? (
                <div className="p-4">
                  <img src={previewUrl} alt="预览" className="max-h-64 mx-auto rounded-lg object-contain" />
                  <p className="text-xs text-stone-400 text-center mt-2">{uploadedFile?.name}</p>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-16 px-4">
                  <Upload size={32} className="text-stone-300 mb-3" />
                  <p className="text-sm text-stone-500 mb-1">拖拽或点击上传遥感影像</p>
                  <p className="text-xs text-stone-400">支持 TIFF/PNG/JPG/BMP 格式</p>
                </div>
              )}
              {uploading && (
                <div className="absolute inset-0 bg-white/80 flex items-center justify-center rounded-xl">
                  <Loader2 size={20} className="animate-spin text-stone-500" />
                </div>
              )}
            </div>

            {uploadedFile && (
              <div className="flex items-center gap-2 text-xs text-stone-500 bg-white px-3 py-2 rounded-lg border border-stone-200/60">
                <CheckCircle size={12} className="text-emerald-500" />
                <span className="flex-1 truncate">{uploadedFile.name}</span>
                <span>{(uploadedFile.size / 1024 / 1024).toFixed(1)} MB</span>
                <button onClick={handleReset} className="text-stone-400 hover:text-stone-600"><X size={12} /></button>
              </div>
            )}

            <div className="bg-white rounded-xl border border-stone-200/60 p-4 space-y-3">
              <h3 className="text-sm font-medium text-stone-700">分析参数</h3>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-stone-400 mb-1">区域</label>
                  <select
                    value={form.region}
                    onChange={(e) => setForm(prev => ({ ...prev, region: e.target.value }))}
                    className="w-full px-2.5 py-2 text-sm bg-white border border-stone-200 rounded-lg text-stone-600 focus:border-stone-400 outline-none"
                  >
                    {REGIONS.map(r => <option key={r.id} value={r.id}>{r.label}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-stone-400 mb-1">作物类型</label>
                  <select
                    value={form.crop_type}
                    onChange={(e) => setForm(prev => ({ ...prev, crop_type: e.target.value }))}
                    className="w-full px-2.5 py-2 text-sm bg-white border border-stone-200 rounded-lg text-stone-600 focus:border-stone-400 outline-none"
                  >
                    {CROP_TYPES.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-stone-400 mb-1">任务类型</label>
                  <select
                    value={form.task_type}
                    onChange={(e) => setForm(prev => ({ ...prev, task_type: e.target.value }))}
                    className="w-full px-2.5 py-2 text-sm bg-white border border-stone-200 rounded-lg text-stone-600 focus:border-stone-400 outline-none"
                  >
                    {TASK_TYPES.map(t => <option key={t.id} value={t.id}>{t.label}</option>)}
                  </select>
                </div>
                <div className="flex items-end">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={form.use_mock}
                      onChange={(e) => setForm(prev => ({ ...prev, use_mock: e.target.checked }))}
                      className="w-4 h-4 rounded border-stone-300 text-stone-600 focus:ring-stone-400"
                    />
                    <span className="text-xs text-stone-500">模拟模式</span>
                  </label>
                </div>
              </div>
              <button
                onClick={handleAnalyze}
                disabled={analyzing || !uploadedPath}
                className="w-full py-2.5 text-sm font-medium text-white bg-stone-700 hover:bg-stone-800 rounded-lg transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {analyzing ? <Loader2 size={14} className="animate-spin" /> : <Eye size={14} />}
                {analyzing ? '分析中...' : '开始分析'}
              </button>
            </div>
          </div>

          <div className="space-y-4">
            {result ? (
              <>
                <div className={`rounded-xl border p-4 ${result.success ? 'bg-emerald-50 border-emerald-200/60' : 'bg-red-50 border-red-200/60'}`}>
                  <div className="flex items-center gap-2 mb-2">
                    {result.success ? (
                      <CheckCircle size={16} className="text-emerald-500" />
                    ) : (
                      <AlertCircle size={16} className="text-red-500" />
                    )}
                    <span className={`text-sm font-medium ${result.success ? 'text-emerald-700' : 'text-red-700'}`}>
                      {result.success ? '分析完成' : '分析失败'}
                    </span>
                  </div>
                  <p className="text-xs text-stone-500">{result.message}</p>
                </div>

                {result.result && (
                  <>
                    <div className="bg-white rounded-xl border border-stone-200/60 p-4 space-y-3">
                      <h3 className="text-sm font-medium text-stone-700 flex items-center gap-2">
                        <BarChart3 size={14} />
                        分析结果
                      </h3>
                      <div className="grid grid-cols-2 gap-3">
                        <div className="bg-stone-50 rounded-lg p-3">
                          <p className="text-xs text-stone-400">置信度</p>
                          <p className="text-lg font-semibold text-stone-800">{formatConfidence(result.result.confidence)}</p>
                        </div>
                        <div className="bg-stone-50 rounded-lg p-3">
                          <p className="text-xs text-stone-400">影响面积</p>
                          <p className="text-lg font-semibold text-stone-800">{result.result.affected_area.toFixed(1)}</p>
                        </div>
                        <div className="bg-stone-50 rounded-lg p-3">
                          <p className="text-xs text-stone-400">模型</p>
                          <p className="text-sm font-medium text-stone-800 truncate">{result.result.model_name}</p>
                        </div>
                        <div className="bg-stone-50 rounded-lg p-3">
                          <p className="text-xs text-stone-400">版本</p>
                          <p className="text-sm font-medium text-stone-800">{result.result.model_version}</p>
                        </div>
                      </div>
                    </div>

                    {result.result.mask_uri && (
                      <div className="bg-white rounded-xl border border-stone-200/60 p-4">
                        <h3 className="text-sm font-medium text-stone-700 mb-3">掩膜/分类图</h3>
                        <a
                          href={`/v2/artifacts/open?path=${encodeURIComponent(result.result.mask_uri)}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="block bg-stone-50 rounded-lg p-4 text-center hover:bg-stone-100 transition-colors"
                        >
                          <Image size={24} className="mx-auto text-stone-400 mb-2" />
                          <p className="text-xs text-stone-500">点击查看掩膜图</p>
                          <p className="text-[10px] text-stone-400 truncate mt-1">{result.result.mask_uri}</p>
                        </a>
                      </div>
                    )}

                    {result.result.class_distribution && result.result.class_distribution.length > 0 && (
                      <div className="bg-white rounded-xl border border-stone-200/60 p-4">
                        <h3 className="text-sm font-medium text-stone-700 mb-3">类别分布</h3>
                        <div className="space-y-2">
                          {result.result.class_distribution.map((cls, idx) => (
                            <div key={idx} className="flex items-center gap-3">
                              <span className="text-xs text-stone-500 w-20 shrink-0">
                                {cls.label || `类别 ${cls.class_value}`}
                              </span>
                              <div className="flex-1 bg-stone-100 rounded-full h-2 overflow-hidden">
                                <div
                                  className="bg-stone-600 h-full rounded-full transition-all"
                                  style={{ width: `${Math.min(cls.ratio * 100, 100)}%` }}
                                />
                              </div>
                              <span className="text-xs text-stone-500 w-16 text-right">
                                {(cls.ratio * 100).toFixed(1)}%
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {result.result.polygons && result.result.polygons.length > 0 && (
                      <div className="bg-white rounded-xl border border-stone-200/60 p-4">
                        <h3 className="text-sm font-medium text-stone-700 mb-3 flex items-center gap-2">
                          <MapPin size={14} />
                          检测区域
                        </h3>
                        <p className="text-xs text-stone-500">共检测到 {result.result.polygons.length} 个区域</p>
                      </div>
                    )}
                  </>
                )}
              </>
            ) : (
              <div className="bg-white rounded-xl border border-stone-200/60 p-8 text-center">
                <Image size={32} className="mx-auto text-stone-300 mb-3" />
                <p className="text-sm text-stone-400">上传影像并设置参数后，点击"开始分析"</p>
                <p className="text-xs text-stone-300 mt-1">分析结果将在此处显示</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default ImageAnalysisPage
