import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createLaiAnalysis, fetchLiveFarms, getLaiAnalysis, searchLiveImagery, streamLaiAnalysis, type LaiPixelProgress, type LiveFarm, type LiveImageryCandidate } from '../services/spatialClient'
import LiveFarmMap, { type AoiGeometry } from '../components/LiveFarmMap'
import { formatAoiArea } from '../utils/aoiGeometry'
import {
  Bot, Check, ChevronRight, CloudSun, Crosshair, FileText, Layers, MapPinned,
  Play, RotateCcw, Search, Sparkles, WandSparkles, X,
} from 'lucide-react'

type AnalysisStage = 'idle' | 'candidates' | 'ready' | 'running' | 'done'

const DEMO_FARMS: LiveFarm[] = [
  {
    farm_id: 'farm-heihe', name: '黑河绿洲示范农场', location_label: '甘肃 · 张掖', area_hectares: 1286,
    geometry: { type: 'Polygon', coordinates: [[[100.354, 38.955], [100.401, 38.955], [100.401, 38.98], [100.354, 38.98], [100.354, 38.955]]] },
  },
  {
    farm_id: 'farm-yongchang', name: '永昌智慧农场', location_label: '甘肃 · 金昌', area_hectares: 742,
    geometry: { type: 'Polygon', coordinates: [[[101.954, 38.205], [101.985, 38.205], [101.985, 38.227], [101.954, 38.227], [101.954, 38.205]]] },
  },
  {
    farm_id: 'farm-wuwei', name: '凉州灌区试验田', location_label: '甘肃 · 武威', area_hectares: 514,
    geometry: { type: 'Polygon', coordinates: [[[102.614, 37.881], [102.64, 37.881], [102.64, 37.9], [102.614, 37.9], [102.614, 37.881]]] },
  },
]

const DEMO_CANDIDATES = [
  { id: 'S2B_50SMF_20250528', date: '2025-05-28', cloud: '3.2%', recommended: true },
  { id: 'S2A_50SMF_20250518', date: '2025-05-18', cloud: '8.6%', recommended: false },
  { id: 'S2B_50SMF_20250602', date: '2025-06-02', cloud: '14.8%', recommended: false },
]

const STAGE_STEPS = [
  ['影像准备', '正在读取 AOI 范围关键波段'],
  ['LAI 反演', '正在进行逐像元反演'],
  ['生成报告', '正在整理分析结果'],
]

const farmAccent = ['emerald', 'cyan', 'amber'] as const

export default function MapWorkspaceDemoPage({ live = false }: { live?: boolean }) {
  const [selectedFarm, setSelectedFarm] = useState(DEMO_FARMS[0].farm_id)
  const [selectedImage, setSelectedImage] = useState(DEMO_CANDIDATES[0].id)
  const [stage, setStage] = useState<AnalysisStage>('idle')
  const [progress, setProgress] = useState(0)
  const [liveFarms, setLiveFarms] = useState<LiveFarm[]>([])
  const [liveAoi, setLiveAoi] = useState<AoiGeometry | null>(null)
  const [liveAoiArea, setLiveAoiArea] = useState<number | null>(null)
  const [aoiResetVersion, setAoiResetVersion] = useState(0)
  const [liveStatus, setLiveStatus] = useState(live ? '正在连接地图服务…' : '本地演示数据')
  const [liveCandidates, setLiveCandidates] = useState<LiveImageryCandidate[] | null>(null)
  const [analysisError, setAnalysisError] = useState('')
  const [reportUrl, setReportUrl] = useState('')
  const [analysisId, setAnalysisId] = useState('')
  const [analysisDetail, setAnalysisDetail] = useState('')
  const [analysisStartedAt, setAnalysisStartedAt] = useState<number | null>(null)
  const [analysisUpdatedAt, setAnalysisUpdatedAt] = useState<number | null>(null)
  const [analysisClock, setAnalysisClock] = useState(() => Date.now())
  const [analysisConnectionIssue, setAnalysisConnectionIssue] = useState(false)
  const [pixelProgress, setPixelProgress] = useState<LaiPixelProgress | null>(null)
  const stopAnalysisStream = useRef<(() => void) | null>(null)

  useEffect(() => {
    if (!live) return undefined
    let disposed = false
    setLiveStatus('正在加载农场边界…')
    fetchLiveFarms().then((items) => {
      if (disposed) return
      setLiveFarms(items)
      setSelectedFarm((current) => items.some((item) => item.farm_id === current) ? current : (items[0]?.farm_id ?? current))
      setLiveStatus(`已加载 ${items.length} 个农场边界`)
    }).catch((error) => {
      if (!disposed) setLiveStatus(error instanceof Error ? error.message : '农场边界加载失败')
    })
    return () => { disposed = true }
  }, [live])

  useEffect(() => () => {
    stopAnalysisStream.current?.()
    stopAnalysisStream.current = null
  }, [])

  const displayedFarms = live && liveFarms.length ? liveFarms : DEMO_FARMS
  const farm = displayedFarms.find((item) => item.farm_id === selectedFarm) ?? displayedFarms[0]
  const aoiReady = liveAoi != null && liveAoiArea != null && liveAoiArea > 0
  const aoiAreaLabel = formatAoiArea(liveAoiArea)
  const displayedCandidates = useMemo(() => {
    if (!live) return DEMO_CANDIDATES
    return (liveCandidates ?? []).map((item) => ({
      id: item.item_id,
      date: item.acquired_at.slice(0, 10),
      cloud: item.cloud_cover == null ? '未知' : `${item.cloud_cover.toFixed(1)}%`,
      recommended: item.is_recommended,
    }))
  }, [live, liveCandidates])
  const displayedImage = displayedCandidates.find((item) => item.id === selectedImage) ?? displayedCandidates[0]
  const currentStep = useMemo(() => progress < 35 ? 0 : progress < 90 ? 1 : 2, [progress])
  const elapsedSeconds = analysisStartedAt == null ? 0 : Math.max(0, Math.floor((analysisClock - analysisStartedAt) / 1000))
  const lastUpdateSeconds = analysisUpdatedAt == null ? null : Math.max(0, Math.floor((analysisClock - analysisUpdatedAt) / 1000))
  const analysisDelayed = live && stage === 'running' && lastUpdateSeconds != null && lastUpdateSeconds >= 15

  useEffect(() => {
    if (stage !== 'running') return undefined
    setAnalysisClock(Date.now())
    const timer = window.setInterval(() => setAnalysisClock(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [stage])

  useEffect(() => {
    if (live || stage !== 'running') return undefined
    const timer = window.setInterval(() => {
      setProgress((value) => {
        if (value >= 100) {
          window.clearInterval(timer)
          setStage('done')
          return 100
        }
        return Math.min(100, value + 4)
      })
    }, 180)
    return () => window.clearInterval(timer)
  }, [live, stage])

  useEffect(() => {
    if (!live || stage !== 'running' || !analysisId) return undefined
    let disposed = false
    let requestInFlight = false

    const syncStatus = async () => {
      if (requestInFlight) return
      requestInFlight = true
      try {
        const analysis = await getLaiAnalysis(analysisId)
        if (disposed) return
        if (typeof analysis.progress_percent === 'number') {
          setProgress((current) => Math.max(current, analysis.progress_percent))
        }
        if (analysis.detail) {
          setAnalysisDetail(analysis.detail)
          setLiveStatus(analysis.detail)
        }
        const polledPixelProgress = readPixelProgress(analysis.progress_data)
        if (polledPixelProgress) setPixelProgress(polledPixelProgress)
        const serverUpdatedAt = analysis.updated_at ? Date.parse(analysis.updated_at) : Number.NaN
        if (Number.isFinite(serverUpdatedAt)) {
          setAnalysisUpdatedAt((current) => current == null || serverUpdatedAt > current ? serverUpdatedAt : current)
        }

        if (analysis.status === 'completed') {
          setProgress(100)
          setReportUrl(typeof analysis.result.report_uri === 'string' ? analysis.result.report_uri : '')
          setAnalysisDetail(analysis.detail || 'LAI 反演和报告已完成')
          setStage('done')
          setAnalysisConnectionIssue(false)
          stopAnalysisStream.current?.()
          stopAnalysisStream.current = null
        } else if (analysis.status === 'failed' || analysis.status === 'cancelled') {
          const message = typeof analysis.result.error === 'string'
            ? analysis.result.error
            : analysis.detail || 'LAI 分析未能完成，请重试。'
          setAnalysisError(message)
          setAnalysisDetail(message)
          setStage('ready')
          setAnalysisConnectionIssue(false)
          stopAnalysisStream.current?.()
          stopAnalysisStream.current = null
        }
      } catch {
        if (!disposed) setAnalysisConnectionIssue(true)
      } finally {
        requestInFlight = false
      }
    }

    void syncStatus()
    const timer = window.setInterval(() => void syncStatus(), 3000)
    return () => {
      disposed = true
      window.clearInterval(timer)
    }
  }, [analysisId, live, stage])

  const resetAnalysisTracking = () => {
    stopAnalysisStream.current?.()
    stopAnalysisStream.current = null
    setAnalysisId('')
    setAnalysisDetail('')
    setAnalysisStartedAt(null)
    setAnalysisUpdatedAt(null)
    setAnalysisConnectionIssue(false)
    setPixelProgress(null)
  }

  const clearAoi = () => {
    resetAnalysisTracking()
    setLiveAoi(null)
    setLiveAoiArea(null)
    setLiveCandidates(null)
    setSelectedImage(live ? '' : DEMO_CANDIDATES[0].id)
    setAnalysisError('')
    setReportUrl('')
    setStage('idle')
    setProgress(0)
    setAoiResetVersion((value) => value + 1)
  }

  const selectFarm = (farmId: string) => {
    if (farmId === selectedFarm) return
    setSelectedFarm(farmId)
    clearAoi()
  }

  const handleAoiChange = (geometry: AoiGeometry | null, areaHectares: number | null) => {
    resetAnalysisTracking()
    setLiveAoi(geometry)
    setLiveAoiArea(areaHectares)
    setLiveCandidates(null)
    setSelectedImage(live ? '' : DEMO_CANDIDATES[0].id)
    setAnalysisError('')
    setReportUrl('')
    setStage('idle')
    setProgress(0)
    if (live) setLiveStatus(geometry && areaHectares ? `AOI 已更新 · ${formatAoiArea(areaHectares)}` : 'AOI 已清除')
  }

  const startAnalysis = async () => {
    setAnalysisError('')
    if (!aoiReady || !liveAoi || liveAoiArea == null) {
      setAnalysisError('请先绘制有效的 AOI。')
      return
    }
    if (!live) {
      const now = Date.now()
      setStage('running')
      setProgress(4)
      setAnalysisDetail('正在读取 AOI 范围关键波段')
      setAnalysisStartedAt(now)
      setAnalysisUpdatedAt(now)
      return
    }

    const selectedCandidate = liveCandidates?.find((item) => item.item_id === selectedImage)
    if (!selectedCandidate) {
      setAnalysisError('请先选择一景 Sentinel 影像。')
      return
    }

    try {
      const startedAt = Date.now()
      stopAnalysisStream.current?.()
      stopAnalysisStream.current = null
      setAnalysisId('')
      setStage('running')
      setProgress(1)
      setAnalysisStartedAt(startedAt)
      setAnalysisUpdatedAt(startedAt)
      setAnalysisClock(startedAt)
      setAnalysisConnectionIssue(false)
      setPixelProgress(null)
      setAnalysisDetail('正在创建 LAI 分析任务')
      setLiveStatus('正在创建 LAI 分析任务…')
      const analysis = await createLaiAnalysis({
        aoi: { geometry: liveAoi, source: 'drawn', area_hectares: Number(liveAoiArea.toFixed(2)) },
        imagery_item_id: selectedCandidate.item_id,
        imagery_snapshot: selectedCandidate,
        farm_id: selectedFarm,
        parameters: { target_resolution_m: 20 },
      })
      setAnalysisId(analysis.analysis_id)
      setAnalysisDetail(analysis.detail || '任务已创建，正在连接实时进度')
      const createdUpdatedAt = analysis.updated_at ? Date.parse(analysis.updated_at) : Number.NaN
      if (Number.isFinite(createdUpdatedAt)) setAnalysisUpdatedAt(createdUpdatedAt)
      stopAnalysisStream.current = streamLaiAnalysis(analysis.analysis_id, (event) => {
        const eventTimestamp = event.timestamp ? Date.parse(event.timestamp) : Number.NaN
        if (event.progress_percent != null) {
          setProgress((current) => Math.max(current, event.progress_percent ?? current))
        }
        setAnalysisDetail(event.detail)
        setAnalysisUpdatedAt(Number.isFinite(eventTimestamp) ? eventTimestamp : Date.now())
        setAnalysisConnectionIssue(false)
        setLiveStatus(event.detail)
        const streamedPixelProgress = readPixelProgress(event.data)
        if (streamedPixelProgress) setPixelProgress(streamedPixelProgress)
        if (event.kind === 'result') {
          setProgress(100)
          setReportUrl(typeof event.data.report_uri === 'string' ? event.data.report_uri : '')
          setStage('done')
          stopAnalysisStream.current?.()
          stopAnalysisStream.current = null
        }
        if (event.kind === 'error') {
          setAnalysisError(event.detail)
          setStage('ready')
          stopAnalysisStream.current?.()
          stopAnalysisStream.current = null
        }
      }, () => {
        setAnalysisConnectionIssue(true)
        setLiveStatus('实时进度连接正在恢复，任务仍在后台运行')
      }, () => {
        setAnalysisConnectionIssue(false)
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : '创建 LAI 分析任务失败。'
      setAnalysisError(message)
      setAnalysisDetail(message)
      setAnalysisUpdatedAt(Date.now())
      setAnalysisId('')
      setAnalysisConnectionIssue(false)
      setStage('ready')
    }
  }

  const findImagery = async () => {
    if (!aoiReady || !liveAoi || liveAoiArea == null) {
      setAnalysisError('请先绘制有效的 AOI。')
      return
    }
    if (!live) {
      setStage('candidates')
      return
    }
    setAnalysisError('')
    setLiveStatus('正在搜索 Sentinel-2 L2A 影像…')
    try {
      const items = await searchLiveImagery({
        aoi: { geometry: liveAoi, source: 'drawn', area_hectares: Number(liveAoiArea.toFixed(2)) },
        start_date: '2025-05-01',
        end_date: '2025-06-10',
        max_cloud_cover: 20,
      })
      setLiveCandidates(items)
      setSelectedImage(items[0]?.item_id ?? '')
      setLiveStatus(items.length ? `找到 ${items.length} 景候选影像` : '未找到满足条件的候选影像')
      setStage('candidates')
    } catch (error) {
      setAnalysisError(error instanceof Error ? error.message : '影像搜索失败。')
    }
  }

  return (
    <main className="h-screen min-h-[680px] overflow-hidden bg-[#071611] text-slate-100 selection:bg-emerald-400/30">
      <header className="absolute inset-x-0 top-0 z-40 flex h-16 items-center justify-between border-b border-white/10 bg-[#0a1d17]/95 px-5 backdrop-blur-xl">
        <div className="flex min-w-0 items-center gap-3">
          <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-emerald-300 text-[#06251b] shadow-lg shadow-emerald-500/20"><Sparkles size={17} /></div>
          <div className="min-w-0"><p className="text-sm font-semibold tracking-[0.12em] text-white">KTP</p><p className="text-[10px] text-emerald-200/70">AGRICULTURE INTELLIGENCE</p></div>
          <span className="hidden h-5 w-px bg-white/15 sm:block" />
          <span className="hidden text-xs text-slate-300 sm:block">地图分析工作台</span>
        </div>
        <div className="flex min-w-0 items-center gap-2 text-[10px]">
          <span title={liveStatus} className={`h-2 w-2 rounded-full ${live && liveStatus.includes('失败') ? 'bg-rose-400' : 'bg-emerald-300'}`} />
          <span className="hidden max-w-44 truncate text-slate-300 sm:inline sm:max-w-80">{liveStatus}</span>
        </div>
      </header>

      <section className="grid h-full grid-cols-[248px_minmax(0,1fr)_376px] pt-16 max-[1100px]:grid-cols-[220px_minmax(0,1fr)_340px] max-[880px]:grid-cols-[minmax(0,1fr)_340px] max-[680px]:block">
        <aside className="z-20 flex min-h-0 flex-col border-r border-white/10 bg-[#0a1b16]/95 p-4 max-[880px]:hidden">
          <div className="mb-4 flex items-center justify-between"><div><p className="text-xs font-medium text-white">农场边界</p><p className="mt-1 text-[11px] text-slate-500">{displayedFarms.length} 个可用范围</p></div><MapPinned size={15} className="text-emerald-300" /></div>
          <div className="space-y-2">
            {displayedFarms.map((item, index) => {
              const accent = farmAccent[index % farmAccent.length]
              const selected = item.farm_id === selectedFarm
              return <button key={item.farm_id} onClick={() => selectFarm(item.farm_id)} className={`w-full rounded-lg border p-3 text-left transition ${selected ? 'border-emerald-300/45 bg-emerald-400/[0.12] shadow-lg shadow-emerald-950/20' : 'border-white/[0.07] bg-white/[0.025] hover:border-white/15 hover:bg-white/[0.06]'}`}>
                <div className="flex items-start justify-between gap-2"><span className="text-xs font-medium text-slate-100">{item.name}</span><span className={`mt-0.5 h-2 w-2 rounded-full ${accent === 'emerald' ? 'bg-emerald-400' : accent === 'cyan' ? 'bg-cyan-400' : 'bg-amber-400'}`} /></div>
                <div className="mt-1.5 flex items-center justify-between gap-2 text-[10px] text-slate-500"><span className="truncate">{item.location_label}</span><span className="shrink-0">{formatAoiArea(item.area_hectares)}</span></div>
              </button>
            })}
          </div>
          <div className="mt-6 border-t border-white/10 pt-4">
            <div className="mb-2 flex items-center gap-2 text-xs font-medium text-slate-300"><Layers size={14} className="text-slate-500" />当前图层</div>
            <div className="space-y-2 text-[11px] text-slate-500"><p className="flex items-center gap-2"><i className="h-2 w-2 rounded-sm border border-emerald-200 bg-emerald-300/30" />农场边界</p><p className="flex items-center gap-2"><i className="h-2 w-2 rounded-sm border border-cyan-200 bg-cyan-300/30" />分析区域</p></div>
          </div>
          <div className="mt-auto border-t border-white/10 pt-4"><p className="text-[10px] uppercase tracking-wide text-slate-500">分析区域</p><p className={`mt-1 text-sm font-medium ${aoiReady ? 'text-cyan-100' : 'text-slate-400'}`}>{aoiReady ? aoiAreaLabel : '尚未选择 AOI'}</p><p className="mt-1 text-[10px] text-slate-500">{aoiReady ? 'GeoJSON 已同步到分析任务' : '等待地图绘制结果'}</p></div>
        </aside>

        <section className="relative min-h-0 overflow-hidden bg-[#18392e] max-[680px]:h-[55vh]" aria-label="遥感分析地图">
          <LiveFarmMap
            farms={displayedFarms}
            selectedFarmId={selectedFarm}
            onFarmSelect={selectFarm}
            onAoiChange={handleAoiChange}
            onAoiError={setAnalysisError}
            clearVersion={aoiResetVersion}
            aoiAreaHectares={liveAoiArea}
          />
        </section>

        <aside className="z-20 flex min-h-0 min-w-0 flex-col border-l border-white/10 bg-[#0b1d18]/95 backdrop-blur-xl max-[680px]:h-[calc(45vh-4rem)] max-[680px]:border-l-0 max-[680px]:border-t">
          <div className="border-b border-white/10 px-5 py-4"><div className="flex items-center gap-2"><span className="grid h-7 w-7 place-items-center rounded-lg bg-emerald-400/15 text-emerald-200"><Bot size={16} /></span><div><h1 className="text-sm font-semibold text-white">遥感分析</h1><p className="text-[10px] text-emerald-200/65">{farm.name} · {farm.location_label}</p></div></div></div>
          <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
            <AgentMessage icon={<MapPinned size={14} />} tone="emerald" title="当前农场" time="已定位"><b>{farm.name}</b><br />边界面积 {formatAoiArea(farm.area_hectares)}</AgentMessage>
            {!aoiReady && <AgentMessage icon={<Crosshair size={14} />} tone="cyan" title="等待分析区域" time="AOI"><span>请在地图左上角绘制矩形或多边形区域。</span></AgentMessage>}
            {aoiReady && <AgentMessage icon={<Crosshair size={14} />} tone="cyan" title="分析区域已就绪" time="AOI"><b>{aoiAreaLabel}</b><br />边界编辑会自动同步面积与 GeoJSON。</AgentMessage>}
            {aoiReady && stage === 'idle' && <ActionCard title="搜索可用影像" subtitle="Sentinel-2 L2A · 2025-05 至 2025-06 · 云量不高于 20%" action="搜索 Sentinel 影像" onClick={findImagery} icon={<Search size={15} />} />}
            {stage === 'candidates' && <CandidateList candidates={displayedCandidates} selectedImage={selectedImage} onSelect={(candidateId) => { setSelectedImage(candidateId); setStage('ready') }} />}
            {stage === 'ready' && displayedImage && <><AgentMessage icon={<WandSparkles size={14} />} tone="amber" title="推荐影像已选定" time="影像"><b>{displayedImage.date}</b> · 云量 {displayedImage.cloud}</AgentMessage><ActionCard title="启动 LAI 反演" subtitle={`${aoiAreaLabel} · ${displayedImage.id} · 20 m 分辨率`} action="开始反演" onClick={startAnalysis} icon={<Play size={15} />} strong /></>}
            {analysisError && <AgentMessage icon={<X size={14} />} tone="rose" title="操作提示" time="刚刚">{analysisError}</AgentMessage>}
            {stage === 'running' && <ProgressCard
              progress={progress}
              currentStep={currentStep}
              detail={analysisDetail}
              elapsedSeconds={elapsedSeconds}
              lastUpdateSeconds={lastUpdateSeconds}
              delayed={analysisDelayed}
              connectionIssue={analysisConnectionIssue}
              pixelProgress={pixelProgress}
            />}
            {stage === 'done' && <ResultCard reportUrl={reportUrl} onReset={() => { resetAnalysisTracking(); setStage('idle'); setProgress(0); setReportUrl(''); setAnalysisError('') }} />}
          </div>
        </aside>
      </section>
    </main>
  )
}

function CandidateList({ candidates, selectedImage, onSelect }: { candidates: Array<{ id: string; date: string; cloud: string; recommended: boolean }>; selectedImage: string; onSelect: (candidateId: string) => void }) {
  if (!candidates.length) return <AgentMessage icon={<CloudSun size={14} />} tone="amber" title="未找到候选影像" time="影像">请调整日期范围或云量条件后重试。</AgentMessage>
  return <article className="rounded-lg border border-white/10 bg-white/[0.035] p-3"><div className="mb-3 flex items-center gap-2"><CloudSun size={15} className="text-amber-300" /><div><p className="text-xs font-medium text-white">{candidates.length} 景候选影像</p><p className="mt-0.5 text-[10px] text-slate-500">选择一景后启动反演</p></div></div><div className="space-y-2">{candidates.map((item) => <button key={item.id} onClick={() => onSelect(item.id)} className={`flex w-full items-center gap-2 rounded-lg border p-2 text-left transition ${item.id === selectedImage ? 'border-emerald-300/50 bg-emerald-400/[0.1]' : 'border-white/[0.08] bg-black/10 hover:bg-white/[0.06]'}`}><span className={`h-9 w-1 shrink-0 rounded-full ${item.recommended ? 'bg-emerald-300' : 'bg-cyan-300/70'}`} /><span className="min-w-0 flex-1"><span className="flex items-center gap-1 text-[10px] font-medium text-slate-200">{item.date}{item.recommended && <em className="rounded bg-emerald-300/15 px-1 py-0.5 text-[8px] not-italic text-emerald-200">推荐</em>}</span><span className="mt-1 block text-[9px] text-slate-500">云量 {item.cloud}</span></span>{item.id === selectedImage && <Check size={14} className="shrink-0 text-emerald-300" />}</button>)}</div></article>
}

function AgentMessage({ icon, tone, title, time, children }: { icon: ReactNode; tone: 'emerald' | 'cyan' | 'amber' | 'rose'; title: string; time: string; children: ReactNode }) {
  const colors = { emerald: 'border-emerald-300/15 bg-emerald-300/[0.055] text-emerald-200', cyan: 'border-cyan-300/15 bg-cyan-300/[0.055] text-cyan-200', amber: 'border-amber-300/15 bg-amber-300/[0.055] text-amber-200', rose: 'border-rose-300/15 bg-rose-300/[0.055] text-rose-200' }
  return <article className={`rounded-lg border p-3 ${colors[tone]}`}><div className="mb-2 flex items-center justify-between"><div className="flex items-center gap-1.5 text-[10px] font-medium">{icon}<span>{title}</span></div><span className="text-[9px] text-slate-500">{time}</span></div><div className="text-[11px] leading-5 text-slate-300">{children}</div></article>
}

function ActionCard({ title, subtitle, action, onClick, icon, strong = false }: { title: string; subtitle: string; action: string; onClick: () => void; icon: ReactNode; strong?: boolean }) {
  return <article className="rounded-lg border border-white/10 bg-white/[0.035] p-3"><p className="text-xs font-medium text-white">{title}</p><p className="mt-1 text-[10px] leading-4 text-slate-500">{subtitle}</p><button onClick={onClick} className={`mt-3 flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-[11px] font-medium transition ${strong ? 'bg-emerald-400 text-[#06261b] hover:bg-emerald-300' : 'border border-emerald-300/25 bg-emerald-400/[0.08] text-emerald-100 hover:bg-emerald-400/[0.16]'}`}>{icon}{action}<ChevronRight size={13} /></button></article>
}

function formatElapsed(seconds: number): string {
  const minutes = Math.floor(seconds / 60)
  const remainder = seconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`
}

function formatLastUpdate(seconds: number | null): string {
  if (seconds == null) return '等待中'
  if (seconds < 2) return '刚刚'
  if (seconds < 60) return `${seconds} 秒前`
  return `${Math.floor(seconds / 60)} 分钟前`
}

function readPixelProgress(value: unknown): LaiPixelProgress | null {
  if (!value || typeof value !== 'object') return null
  const candidate = value as Partial<LaiPixelProgress>
  const processed = candidate.processed_pixels
  const current = candidate.current_pixel
  const total = candidate.total_pixels
  if (typeof processed !== 'number' || typeof current !== 'number' || typeof total !== 'number') return null
  return { processed_pixels: processed, current_pixel: current, total_pixels: total }
}

function ProgressCard({
  progress,
  currentStep,
  detail,
  elapsedSeconds,
  lastUpdateSeconds,
  delayed,
  connectionIssue,
  pixelProgress,
}: {
  progress: number
  currentStep: number
  detail: string
  elapsedSeconds: number
  lastUpdateSeconds: number | null
  delayed: boolean
  connectionIssue: boolean
  pixelProgress: LaiPixelProgress | null
}) {
  const currentDetail = detail || STAGE_STEPS[currentStep]?.[1] || '正在处理分析任务'
  const safeProgress = Math.max(0, Math.min(100, progress))
  return <article aria-live="polite" className={`rounded-lg border p-3 ${delayed ? 'border-amber-300/25 bg-amber-300/[0.05]' : 'border-cyan-300/20 bg-cyan-300/[0.055]'}`}>
    <div className="flex items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-2 text-xs font-medium text-cyan-100"><Bot size={15} className="shrink-0" /><span className="truncate">正在执行 LAI 分析</span></div>
      <span className="min-w-10 shrink-0 text-right text-[11px] tabular-nums text-cyan-200">{safeProgress}%</span>
    </div>
    <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-950/80"><div className="h-full rounded-full bg-cyan-300 transition-all duration-300" style={{ width: `${safeProgress}%` }} /></div>
    <div className="mt-3 border-y border-white/[0.08] py-3">
      <p className="break-words text-[11px] leading-5 text-slate-200">{currentDetail}</p>
      {pixelProgress && pixelProgress.total_pixels > 0 && <div className="mt-3 grid grid-cols-[minmax(0,1fr)_auto] items-end gap-4 border-t border-white/[0.08] pt-3">
        <div className="min-w-0"><p className="text-[9px] text-slate-500">有效像元进度</p><p className="mt-1 truncate text-[12px] font-medium tabular-nums text-cyan-100">{pixelProgress.processed_pixels.toLocaleString()} / {pixelProgress.total_pixels.toLocaleString()}</p></div>
        <div className="text-right"><p className="text-[9px] text-slate-500">当前像元</p><p className="mt-1 text-[12px] font-medium tabular-nums text-white">#{pixelProgress.current_pixel.toLocaleString()}</p></div>
      </div>}
      {delayed && <p className="mt-2 flex items-start gap-2 text-[10px] leading-4 text-amber-200"><i className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-300 animate-pulse" />{currentStep === 0 ? '远程影像仍在读取，单个波段可能需要较长时间，任务仍在后台运行。' : '计算仍在进行，任务仍在后台运行。'}</p>}
      {connectionIssue && <p className="mt-2 flex items-start gap-2 text-[10px] leading-4 text-cyan-200/75"><RotateCcw size={11} className="mt-0.5 shrink-0 animate-spin" />实时连接正在恢复，状态查询仍在同步任务。</p>}
    </div>
    <dl className="grid grid-cols-3 border-b border-white/[0.08] py-2.5 text-[9px]">
      <div><dt className="text-slate-500">已用时</dt><dd className="mt-1 tabular-nums text-slate-300">{formatElapsed(elapsedSeconds)}</dd></div>
      <div><dt className="text-slate-500">最近更新</dt><dd className="mt-1 text-slate-300">{formatLastUpdate(lastUpdateSeconds)}</dd></div>
      <div><dt className="text-slate-500">状态来源</dt><dd className={`mt-1 ${connectionIssue ? 'text-amber-200' : 'text-emerald-200'}`}>{connectionIssue ? '轮询同步' : '实时同步'}</dd></div>
    </dl>
    <div className="mt-3 space-y-3">{STAGE_STEPS.map(([name, stepDetail], index) => <div key={name} className="flex gap-2"><span className={`mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full text-[9px] ${index < currentStep ? 'bg-emerald-400 text-[#06261b]' : index === currentStep ? 'border border-cyan-300 bg-cyan-300/20 text-cyan-100 animate-pulse' : 'border border-white/15 text-slate-500'}`}>{index < currentStep ? <Check size={10} /> : index + 1}</span><div className="min-w-0"><p className={`text-[11px] ${index <= currentStep ? 'text-slate-100' : 'text-slate-500'}`}>{name}</p><p className="mt-0.5 break-words text-[9px] leading-4 text-slate-500">{index === currentStep ? stepDetail : index < currentStep ? '已完成' : '等待中'}</p></div></div>)}</div>
  </article>
}

function ResultCard({ onReset, reportUrl }: { onReset: () => void; reportUrl: string }) {
  return <article className="overflow-hidden rounded-lg border border-emerald-300/25 bg-[#0c2b20]"><div className="border-b border-emerald-300/10 bg-emerald-400/[0.08] p-3"><div className="flex items-center gap-2 text-xs font-semibold text-emerald-100"><span className="grid h-5 w-5 place-items-center rounded-full bg-emerald-400 text-[#052218]"><Check size={12} /></span>LAI 分析已完成</div><p className="mt-1 text-[10px] text-emerald-100/60">结果和产物已写入本次分析任务</p></div><div className="space-y-2 p-3">{reportUrl ? <a href={reportUrl} target="_blank" rel="noreferrer" className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-400 py-2 text-[11px] font-medium text-[#06261b] hover:bg-emerald-300"><FileText size={14} />查看完整报告</a> : <p className="rounded-lg border border-white/10 px-3 py-2 text-center text-[10px] text-slate-400">报告产物将在任务完成后提供</p>}<button onClick={onReset} className="flex w-full items-center justify-center gap-1 py-1 text-[10px] text-slate-500 hover:text-slate-200"><RotateCcw size={11} />基于当前 AOI 再次分析</button></div></article>
}
