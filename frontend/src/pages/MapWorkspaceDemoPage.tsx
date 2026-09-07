import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { createLaiAnalysis, fetchLiveFarms, getLaiAnalysis, readLaiAnalysisProducts, searchLiveImagery, streamLaiAnalysis, type LaiMapOverlay, type LaiPixelProgress, type LiveFarm, type LiveImageryCandidate } from '../services/spatialClient'
import LiveFarmMap, { type AoiGeometry } from '../components/LiveFarmMap'
import { formatAoiArea } from '../utils/aoiGeometry'
import WorkspaceAssistantPanel from '../features/workspace-assistant/WorkspaceAssistantPanel'
import { useWorkspaceConversation } from '../features/workspace-assistant/useWorkspaceConversation'
import {
  createWorkspaceTimelineEventId,
  type WorkspaceTimelineItem,
  workspaceTimelineReducer,
} from '../features/workspace-assistant/workspaceTimeline'
import {
  Layers, MapPinned, Sparkles,
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

const farmAccent = ['emerald', 'cyan', 'amber'] as const
const ACTIVE_ANALYSIS_KEY = 'ktp_active_lai_analysis_id'

function formatLocalIsoDate(value: Date): string {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

// 工作台必须默认使用实时接口。这样即使某个旧路由遗漏了 `live` 参数，
// 也不会回退为包含 2025 年固定日期的演示候选影像。
export default function MapWorkspaceDemoPage({ live = true }: { live?: boolean }) {
  const [selectedFarm, setSelectedFarm] = useState(DEMO_FARMS[0].farm_id)
  const [selectedImage, setSelectedImage] = useState('')
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
  const [rasterUrl, setRasterUrl] = useState('')
  const [laiOverlay, setLaiOverlay] = useState<LaiMapOverlay | null>(null)
  const [overlayVisible, setOverlayVisible] = useState(true)
  const [overlayOpacity, setOverlayOpacity] = useState(0.72)
  const [analysisId, setAnalysisId] = useState('')
  const [analysisDetail, setAnalysisDetail] = useState('')
  const [analysisStartedAt, setAnalysisStartedAt] = useState<number | null>(null)
  const [analysisUpdatedAt, setAnalysisUpdatedAt] = useState<number | null>(null)
  const [analysisClock, setAnalysisClock] = useState(() => Date.now())
  const [analysisConnectionIssue, setAnalysisConnectionIssue] = useState(false)
  const [pixelProgress, setPixelProgress] = useState<LaiPixelProgress | null>(null)
  const [timeline, dispatchTimeline] = useReducer(workspaceTimelineReducer, [])
  const appendTimelineItem = useCallback((item: WorkspaceTimelineItem) => {
    dispatchTimeline({ type: 'upsert', item })
  }, [])
  const workspaceConversation = useWorkspaceConversation(appendTimelineItem)
  const stopAnalysisStream = useRef<(() => void) | null>(null)
  const analysisProgressEventId = useRef<string | null>(null)

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

  useEffect(() => {
    if (!live) return undefined
    const storedId = window.localStorage.getItem(ACTIVE_ANALYSIS_KEY)
    if (!storedId) return undefined
    let disposed = false
    setAnalysisId(storedId)
    getLaiAnalysis(storedId).then((analysis) => {
      if (disposed) return
      setProgress(analysis.progress_percent)
      setAnalysisDetail(analysis.detail)
      const updatedAt = analysis.updated_at ? Date.parse(analysis.updated_at) : Date.now()
      setAnalysisStartedAt(Number.isFinite(updatedAt) ? updatedAt : Date.now())
      setAnalysisUpdatedAt(Number.isFinite(updatedAt) ? updatedAt : Date.now())
      const restoredPixelProgress = readPixelProgress(analysis.progress_data)
      if (restoredPixelProgress) setPixelProgress(restoredPixelProgress)
      analysisProgressEventId.current = `analysis-progress-${analysis.analysis_id}`
      dispatchTimeline({
        type: 'upsert',
        item: {
          eventId: analysisProgressEventId.current,
          kind: 'analysis_progress',
          analysisId: analysis.analysis_id,
          progress: analysis.progress_percent,
          detail: analysis.detail || '正在恢复 LAI 分析状态',
          timestamp: analysis.updated_at || new Date().toISOString(),
        },
      })
      if (analysis.status === 'completed') {
        const products = readLaiAnalysisProducts(analysis.result)
        setReportUrl(products.reportUrl)
        setRasterUrl(products.rasterUrl)
        setLaiOverlay(products.overlay)
        setOverlayOpacity(products.overlay?.opacity ?? 0.72)
        setOverlayVisible(true)
        setProgress(100)
        setStage('done')
        dispatchTimeline({ type: 'upsert', item: { eventId: `analysis-result-${analysis.analysis_id}`, kind: 'analysis_result', analysisId: analysis.analysis_id, timestamp: analysis.completed_at || analysis.updated_at || new Date().toISOString() } })
      } else if (analysis.status === 'queued' || analysis.status === 'running') {
        setStage('running')
      } else {
        window.localStorage.removeItem(ACTIVE_ANALYSIS_KEY)
        setAnalysisId('')
      }
    }).catch(() => {
      if (disposed) return
      window.localStorage.removeItem(ACTIVE_ANALYSIS_KEY)
      setAnalysisId('')
    })
    return () => { disposed = true }
  }, [live])

  const displayedFarms = live && liveFarms.length ? liveFarms : DEMO_FARMS
  const farm = displayedFarms.find((item) => item.farm_id === selectedFarm) ?? displayedFarms[0]
  const aoiReady = liveAoi != null && liveAoiArea != null && liveAoiArea > 0
  const aoiAreaLabel = formatAoiArea(liveAoiArea)
  const imagerySearchEndDate = formatLocalIsoDate(new Date())
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
        const progressEventId = analysisProgressEventId.current ?? `analysis-progress-${analysis.analysis_id}`
        analysisProgressEventId.current = progressEventId
        dispatchTimeline({
          type: 'upsert',
          item: {
            eventId: progressEventId,
            kind: 'analysis_progress',
            analysisId: analysis.analysis_id,
            progress: analysis.progress_percent,
            detail: analysis.detail || '正在同步 LAI 分析状态',
            timestamp: analysis.updated_at || new Date().toISOString(),
          },
        })

        if (analysis.status === 'completed') {
          const products = readLaiAnalysisProducts(analysis.result)
          setProgress(100)
          setReportUrl(products.reportUrl)
          setRasterUrl(products.rasterUrl)
          setLaiOverlay(products.overlay)
          setOverlayOpacity(products.overlay?.opacity ?? 0.72)
          setOverlayVisible(true)
          setAnalysisDetail(analysis.detail || 'LAI 反演和报告已完成')
          setStage('done')
          setAnalysisConnectionIssue(false)
          dispatchTimeline({ type: 'upsert', item: { eventId: `analysis-result-${analysis.analysis_id}`, kind: 'analysis_result', analysisId: analysis.analysis_id, timestamp: analysis.completed_at || analysis.updated_at || new Date().toISOString() } })
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
          dispatchTimeline({ type: 'upsert', item: { eventId: `analysis-error-${analysis.analysis_id}`, kind: 'error', detail: message, timestamp: analysis.updated_at || new Date().toISOString() } })
          stopAnalysisStream.current?.()
          stopAnalysisStream.current = null
          window.localStorage.removeItem(ACTIVE_ANALYSIS_KEY)
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
    analysisProgressEventId.current = null
    dispatchTimeline({ type: 'removeKinds', kinds: ['analysis_progress', 'analysis_result', 'error'] })
    setAnalysisId('')
    setAnalysisDetail('')
    setAnalysisStartedAt(null)
    setAnalysisUpdatedAt(null)
    setAnalysisConnectionIssue(false)
    setPixelProgress(null)
    if (live) window.localStorage.removeItem(ACTIVE_ANALYSIS_KEY)
  }

  const clearAnalysisProducts = () => {
    setReportUrl('')
    setRasterUrl('')
    setLaiOverlay(null)
    setOverlayVisible(true)
    setOverlayOpacity(0.72)
  }

  const clearAoi = () => {
    resetAnalysisTracking()
    dispatchTimeline({ type: 'reset' })
    setLiveAoi(null)
    setLiveAoiArea(null)
    setLiveCandidates(null)
    setSelectedImage('')
    setAnalysisError('')
    clearAnalysisProducts()
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
    dispatchTimeline({ type: 'reset' })
    setLiveAoi(geometry)
    setLiveAoiArea(areaHectares)
    setLiveCandidates(null)
    setSelectedImage('')
    setAnalysisError('')
    clearAnalysisProducts()
    setStage('idle')
    setProgress(0)
    if (geometry && areaHectares) {
      dispatchTimeline({
        type: 'upsert',
        item: {
          eventId: createWorkspaceTimelineEventId('aoi'),
          kind: 'aoi_ready',
          areaLabel: formatAoiArea(areaHectares),
          timestamp: new Date().toISOString(),
        },
      })
    }
    if (live) setLiveStatus(geometry && areaHectares ? `AOI 已更新 · ${formatAoiArea(areaHectares)}` : 'AOI 已清除')
  }

  const startAnalysis = async () => {
    setAnalysisError('')
    dispatchTimeline({ type: 'removeKinds', kinds: ['error', 'analysis_progress', 'analysis_result'] })
    if (!aoiReady || !liveAoi || liveAoiArea == null) {
      const detail = '请先绘制有效的 AOI。'
      setAnalysisError(detail)
      dispatchTimeline({ type: 'upsert', item: { eventId: createWorkspaceTimelineEventId('error'), kind: 'error', detail, timestamp: new Date().toISOString() } })
      return
    }
    if (!live) {
      const now = Date.now()
      setStage('running')
      setProgress(4)
      setAnalysisDetail('正在读取 AOI 范围关键波段')
      setAnalysisStartedAt(now)
      setAnalysisUpdatedAt(now)
      analysisProgressEventId.current = 'analysis-progress-demo'
      dispatchTimeline({ type: 'upsert', item: { eventId: analysisProgressEventId.current, kind: 'analysis_progress', progress: 4, detail: '正在读取 AOI 范围关键波段', timestamp: new Date(now).toISOString() } })
      return
    }

    const selectedCandidate = liveCandidates?.find((item) => item.item_id === selectedImage)
    if (!selectedCandidate) {
      const detail = '请先选择一景 Sentinel 影像。'
      setAnalysisError(detail)
      dispatchTimeline({ type: 'upsert', item: { eventId: createWorkspaceTimelineEventId('error'), kind: 'error', detail, timestamp: new Date().toISOString() } })
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
      clearAnalysisProducts()
      setAnalysisDetail('正在创建 LAI 分析任务')
      setLiveStatus('正在创建 LAI 分析任务…')
      analysisProgressEventId.current = createWorkspaceTimelineEventId('analysis-progress')
      dispatchTimeline({
        type: 'upsert',
        item: {
          eventId: analysisProgressEventId.current,
          kind: 'analysis_progress',
          progress: 1,
          detail: '正在创建 LAI 分析任务',
          timestamp: new Date(startedAt).toISOString(),
        },
      })
      const analysis = await createLaiAnalysis({
        aoi: { geometry: liveAoi, source: 'drawn', area_hectares: Number(liveAoiArea.toFixed(2)) },
        imagery_item_id: selectedCandidate.item_id,
        imagery_snapshot: selectedCandidate,
        farm_id: selectedFarm,
        parameters: { target_resolution_m: 20 },
      })
      setAnalysisId(analysis.analysis_id)
      window.localStorage.setItem(ACTIVE_ANALYSIS_KEY, analysis.analysis_id)
      setAnalysisDetail(analysis.detail || '任务已创建，正在连接实时进度')
      const createdUpdatedAt = analysis.updated_at ? Date.parse(analysis.updated_at) : Number.NaN
      if (Number.isFinite(createdUpdatedAt)) setAnalysisUpdatedAt(createdUpdatedAt)
      if (analysisProgressEventId.current) {
        dispatchTimeline({
          type: 'upsert',
          item: {
            eventId: analysisProgressEventId.current,
            kind: 'analysis_progress',
            analysisId: analysis.analysis_id,
            progress: analysis.progress_percent,
            detail: analysis.detail || '任务已创建，正在连接实时进度',
            timestamp: analysis.updated_at || new Date().toISOString(),
          },
        })
      }
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
        const progressEventId = analysisProgressEventId.current ?? createWorkspaceTimelineEventId('analysis-progress')
        analysisProgressEventId.current = progressEventId
        dispatchTimeline({
          type: 'upsert',
          item: {
            eventId: progressEventId,
            kind: 'analysis_progress',
            analysisId: analysis.analysis_id,
            progress: event.progress_percent ?? progress,
            detail: event.detail,
            timestamp: event.timestamp || new Date().toISOString(),
          },
        })
        if (event.kind === 'result') {
          const products = readLaiAnalysisProducts(event.data)
          setProgress(100)
          setReportUrl(products.reportUrl)
          setRasterUrl(products.rasterUrl)
          setLaiOverlay(products.overlay)
          setOverlayOpacity(products.overlay?.opacity ?? 0.72)
          setOverlayVisible(true)
          setStage('done')
          dispatchTimeline({
            type: 'upsert',
            item: {
              eventId: `analysis-result-${analysis.analysis_id}`,
              kind: 'analysis_result',
              analysisId: analysis.analysis_id,
              timestamp: event.timestamp || new Date().toISOString(),
            },
          })
          stopAnalysisStream.current?.()
          stopAnalysisStream.current = null
        }
        if (event.kind === 'error') {
          setAnalysisError(event.detail)
          dispatchTimeline({ type: 'upsert', item: { eventId: `analysis-error-${analysis.analysis_id}`, kind: 'error', detail: event.detail, timestamp: event.timestamp || new Date().toISOString() } })
          setStage('ready')
          window.localStorage.removeItem(ACTIVE_ANALYSIS_KEY)
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
      dispatchTimeline({ type: 'upsert', item: { eventId: createWorkspaceTimelineEventId('error'), kind: 'error', detail: message, timestamp: new Date().toISOString() } })
      setAnalysisDetail(message)
      setAnalysisUpdatedAt(Date.now())
      setAnalysisId('')
      window.localStorage.removeItem(ACTIVE_ANALYSIS_KEY)
      setAnalysisConnectionIssue(false)
      setStage('ready')
    }
  }

  const findImagery = async () => {
    if (!aoiReady || !liveAoi || liveAoiArea == null) {
      const detail = '请先绘制有效的 AOI。'
      setAnalysisError(detail)
      dispatchTimeline({ type: 'upsert', item: { eventId: createWorkspaceTimelineEventId('error'), kind: 'error', detail, timestamp: new Date().toISOString() } })
      return
    }
    dispatchTimeline({ type: 'removeKinds', kinds: ['error', 'imagery_candidates', 'imagery_selected', 'analysis_progress', 'analysis_result'] })
    if (!live) {
      setStage('candidates')
      dispatchTimeline({ type: 'upsert', item: { eventId: 'imagery-candidates', kind: 'imagery_candidates', candidates: DEMO_CANDIDATES, timestamp: new Date().toISOString() } })
      return
    }
    setAnalysisError('')
    setLiveStatus('正在搜索 Sentinel-2 L2A 影像…')
    try {
      const items = await searchLiveImagery({
        aoi: { geometry: liveAoi, source: 'drawn', area_hectares: Number(liveAoiArea.toFixed(2)) },
        end_date: imagerySearchEndDate,
        max_cloud_cover: 20,
      })
      setLiveCandidates(items)
      setSelectedImage('')
      setLiveStatus(items.length ? `找到 ${items.length} 景候选影像` : '未找到满足条件的候选影像')
      setStage('candidates')
      dispatchTimeline({
        type: 'upsert',
        item: {
          eventId: 'imagery-candidates',
          kind: 'imagery_candidates',
          candidates: items.map((item) => ({
            id: item.item_id,
            date: item.acquired_at.slice(0, 10),
            cloud: item.cloud_cover == null ? '未知' : `${item.cloud_cover.toFixed(1)}%`,
            recommended: item.is_recommended,
          })),
          timestamp: new Date().toISOString(),
        },
      })
    } catch (error) {
      const detail = error instanceof Error ? error.message : '影像搜索失败。'
      setAnalysisError(detail)
      dispatchTimeline({ type: 'upsert', item: { eventId: createWorkspaceTimelineEventId('error'), kind: 'error', detail, timestamp: new Date().toISOString() } })
    }
  }

  const selectImageryCandidate = (candidateId: string) => {
    if (stage === 'running' || stage === 'done') return
    const candidate = displayedCandidates.find((item) => item.id === candidateId)
    if (!candidate) return
    setSelectedImage(candidateId)
    setStage('ready')
    dispatchTimeline({
      type: 'upsert',
      item: {
        eventId: 'imagery-selection',
        kind: 'imagery_selected',
        candidateId,
        timestamp: new Date().toISOString(),
      },
    })
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
            laiOverlay={laiOverlay}
            overlayVisible={overlayVisible}
            overlayOpacity={overlayOpacity}
            onOverlayVisibleChange={setOverlayVisible}
            onOverlayOpacityChange={setOverlayOpacity}
          />
        </section>

        <WorkspaceAssistantPanel
          farm={{ name: farm.name, locationLabel: farm.location_label, areaLabel: formatAoiArea(farm.area_hectares) }}
          aoiReady={aoiReady}
          aoiAreaLabel={aoiAreaLabel}
          imagerySearchEndDate={imagerySearchEndDate}
          stage={stage}
          timeline={timeline}
          selectedImage={selectedImage}
          selectedCandidate={displayedImage}
          analysisError={analysisError}
          progress={progress}
          detail={analysisDetail}
          elapsedSeconds={elapsedSeconds}
          lastUpdateSeconds={lastUpdateSeconds}
          delayed={analysisDelayed}
          connectionIssue={analysisConnectionIssue}
          pixelProgress={pixelProgress}
          reportUrl={reportUrl}
          rasterUrl={rasterUrl}
          onFindImagery={findImagery}
          onSelectCandidate={selectImageryCandidate}
          onStartAnalysis={startAnalysis}
          onReset={() => { resetAnalysisTracking(); dispatchTimeline({ type: 'reset' }); clearAnalysisProducts(); setStage('idle'); setProgress(0); setAnalysisError('') }}
          assistantIsSending={workspaceConversation.isSending}
          assistantError={workspaceConversation.error}
          onSendAssistantMessage={workspaceConversation.sendMessage}
          onCancelAssistantMessage={workspaceConversation.cancelMessage}
        />
      </section>
    </main>
  )
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
