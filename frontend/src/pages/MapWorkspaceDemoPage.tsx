import { useCallback, useEffect, useMemo, useReducer, useRef, useState, type CSSProperties } from 'react'
import { createLaiAnalysis, fetchLiveFarms, getAnalysisWorkflow, getCropAnalysis, getLaiAnalysis, readLaiAnalysisProducts, retryAnalysisWorkflowStep, searchLiveImagery, streamLaiAnalysis, updateAnalysisWorkflowYieldInputs, type AnalysisWorkflow, type CropAnalysis, type LaiMapOverlay, type LaiPixelProgress, type LiveFarm, type LiveImageryCandidate, type WorkflowTaskId, type YieldAgronomicInputs } from '../services/spatialClient'
import LiveFarmMap, { type AoiGeometry } from '../components/LiveFarmMap'
import { formatAoiArea } from '../utils/aoiGeometry'
import { createUuid } from '../utils/uuid'
import WorkspaceAssistantPanel from '../features/workspace-assistant/WorkspaceAssistantPanel'
import WorkspaceAnalysisPanel from '../features/workspace-assistant/WorkspaceAnalysisPanel'
import type { AnalysisViewRequest, WorkspacePanelProps } from '../features/workspace-assistant/workspacePanelTypes'
import { useWorkspaceLayout } from '../features/workspace-assistant/useWorkspaceLayout'
import { ATTENTION_COLORS, useWorkspaceAttention } from '../features/workspace-assistant/useWorkspaceAttention'
import { useWorkspaceConversation } from '../features/workspace-assistant/useWorkspaceConversation'
import { getWorkspaceWorkflows, type WorkspaceContext } from '../services/canonical/workspaceClient'
import { getLastLoginUser } from '../services/api'
import { buildWorkspaceUiState, sameTaskSelection } from '../features/workspace-assistant/workspaceUiContext'
import {
  createWorkspaceTimelineEventId,
  type WorkspaceTimelineItem,
  workspaceTimelineReducer,
} from '../features/workspace-assistant/workspaceTimeline'
import {
  ChevronDown, Layers, MapPinned, Sparkles, WandSparkles, X,
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
const ACTIVE_CROP_KEY = 'ktp_active_crop_analysis_id'
const ACTIVE_WORKFLOW_KEY = 'ktp_active_analysis_workflow_id'

function formatLocalIsoDate(value: Date): string {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

// 工作台必须默认使用实时接口。这样即使某个旧路由遗漏了 `live` 参数，
// 也不会回退为包含 2025 年固定日期的演示候选影像。
export default function MapWorkspaceDemoPage({ live = true }: { live?: boolean }) {
  const layout = useWorkspaceLayout()
  const [analysisView, setAnalysisView] = useState<AnalysisViewRequest | null>(null)
  const restoredWorkflowId = useRef(window.localStorage.getItem(ACTIVE_WORKFLOW_KEY))
  const [visibleAnalysisTaskId, setVisibleAnalysisTaskId] = useState<string | null>(null)
  const openAnalysis = (workflowId: string | null) => {
    setAnalysisView((previous) => ({ workflowId, requestId: (previous?.requestId ?? 0) + 1 }))
    if (!layout.docked) layout.openDrawer()
  }
  const [selectedFarm, setSelectedFarm] = useState(DEMO_FARMS[0].farm_id)
  const [selectedImage, setSelectedImage] = useState('')
  const [stage, setStage] = useState<AnalysisStage>('idle')
  const [progress, setProgress] = useState(0)
  const [liveFarms, setLiveFarms] = useState<LiveFarm[]>([])
  const [liveAoi, setLiveAoi] = useState<AoiGeometry | null>(null)
  const [restoredAoi, setRestoredAoi] = useState<AoiGeometry | null>(null)
  const [liveAoiArea, setLiveAoiArea] = useState<number | null>(null)
  const [aoiResetVersion, setAoiResetVersion] = useState(0)
  const [liveStatus, setLiveStatus] = useState(live ? '正在连接地图服务…' : '本地演示数据')
  const [liveCandidates, setLiveCandidates] = useState<LiveImageryCandidate[] | null>(null)
  const [analysisError, setAnalysisError] = useState('')
  const [imageryIsSearching, setImageryIsSearching] = useState(false)
  const imageryRequest = useRef(0)
  const launchLocked = useRef(false)
  const [cropAnalysis, setCropAnalysis] = useState<CropAnalysis | null>(null)
  const [workflow, setWorkflow] = useState<AnalysisWorkflow | null>(null)
  const cropOnlyRun = useRef(false)
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
  const [draftTaskIds, setDraftTaskIds] = useState<WorkflowTaskId[]>([])
  const updateDraftTaskIds = useCallback((tasks: WorkflowTaskId[]) => {
    setDraftTaskIds((current) => sameTaskSelection(current, tasks) ? current : tasks)
  }, [])
  const [workspaceId] = useState(() => {
    const key = `ktp_workspace_id:${getLastLoginUser()}:${live ? 'live' : 'demo'}`
    const existing = window.localStorage.getItem(key)
    if (existing) return existing
    const created = createUuid()
    window.localStorage.setItem(key, created)
    return created
  })
  const workspaceRevision = useRef(Date.now())
  const stopAnalysisStream = useRef<(() => void) | null>(null)
  const analysisProgressEventId = useRef<string | null>(null)

  const applyWorkflow = useCallback((updated: AnalysisWorkflow) => {
    setWorkflow(updated)
    appendTimelineItem({ eventId: `workflow-${updated.workflow_id}`, kind: 'workflow', workflow: updated, timestamp: updated.created_at })
    const laiStep = updated.steps.find((step) => step.step_id === 'lai')
    if (laiStep?.status === 'completed') {
      const products = readLaiAnalysisProducts(laiStep.result)
      setReportUrl(products.reportUrl)
      setRasterUrl(products.rasterUrl)
      setLaiOverlay(products.overlay)
      setOverlayOpacity(products.overlay?.opacity ?? 0.72)
      setOverlayVisible(true)
    }
    setStage(['completed', 'blocked', 'failed', 'cancelled'].includes(updated.status) ? 'done' : 'running')
    setLiveStatus(updated.detail)
  }, [appendTimelineItem])

  useEffect(() => {
    if (!live) return undefined
    const stored = window.localStorage.getItem(ACTIVE_WORKFLOW_KEY)
    if (!stored) return undefined
    let disposed = false
    getAnalysisWorkflow(stored).then((result) => {
      if (disposed) return
      const geometry = result.aoi.geometry as AoiGeometry
      setLiveAoi(geometry)
      setRestoredAoi(geometry)
      setLiveAoiArea(result.aoi.area_hectares)
      setSelectedImage(result.imagery_item_id)
      setLiveCandidates([result.imagery_snapshot])
      updateDraftTaskIds(result.requested_task_ids)
      if (result.farm_id) setSelectedFarm(result.farm_id)
      appendTimelineItem({ eventId: 'imagery-candidates', kind: 'imagery_candidates', candidates: [{ id: result.imagery_item_id, date: result.imagery_snapshot.acquired_at.slice(0, 10), cloud: result.imagery_snapshot.cloud_cover == null ? '未知' : `${result.imagery_snapshot.cloud_cover.toFixed(1)}%`, recommended: true }], timestamp: result.created_at })
      appendTimelineItem({ eventId: 'imagery-selection', kind: 'imagery_selected', candidateId: result.imagery_item_id, timestamp: result.created_at })
      applyWorkflow(result)
    }).catch(() => window.localStorage.removeItem(ACTIVE_WORKFLOW_KEY))
    return () => { disposed = true }
  }, [live, applyWorkflow, appendTimelineItem, updateDraftTaskIds])

  useEffect(() => {
    if (!workflow || !['planned', 'running'].includes(workflow.status)) return undefined
    let disposed = false
    let pending = false
    const poll = async () => {
      if (pending) return
      pending = true
      try {
        const updated = await getAnalysisWorkflow(workflow.workflow_id)
        if (!disposed) applyWorkflow(updated)
      } catch (error) {
        if (!disposed) setAnalysisError(error instanceof Error ? error.message : '工作流状态查询失败')
      } finally {
        pending = false
      }
    }
    const timer = window.setInterval(() => void poll(), 2500)
    return () => { disposed = true; window.clearInterval(timer) }
  }, [workflow, applyWorkflow])

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
    const stored = window.localStorage.getItem(ACTIVE_CROP_KEY)
    if (stored) getCropAnalysis(stored).then(setCropAnalysis).catch(() => window.localStorage.removeItem(ACTIVE_CROP_KEY))
    return undefined
  }, [live])

  useEffect(() => {
    if (!cropAnalysis || cropAnalysis.status === 'completed' || cropAnalysis.status === 'failed') return undefined
    let cancelled = false
    const timer = window.setInterval(() => {
      getCropAnalysis(cropAnalysis.analysis_id).then((updated) => {
        if (cancelled) return
        setCropAnalysis(updated)
        if (updated.status === 'completed' && cropOnlyRun.current) setStage('done')
        if (updated.status === 'failed' && cropOnlyRun.current) setStage('ready')
      }).catch((error) => {
        if (!cancelled) setAnalysisError(error instanceof Error ? error.message : '作物识别状态查询失败')
      })
    }, 2000)
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [cropAnalysis])

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
    setCropAnalysis(null)
    window.localStorage.removeItem(ACTIVE_CROP_KEY)
    setWorkflow(null)
    window.localStorage.removeItem(ACTIVE_WORKFLOW_KEY)
  }

  const clearAnalysisProducts = () => {
    setReportUrl('')
    setRasterUrl('')
    setLaiOverlay(null)
    setOverlayVisible(true)
    setOverlayOpacity(0.72)
  }

  const clearAoi = () => {
    if (launchLocked.current) return
    imageryRequest.current += 1
    setImageryIsSearching(false)
    resetAnalysisTracking()
    updateDraftTaskIds([])
    dispatchTimeline({ type: 'removeKinds', kinds: ['aoi_ready', 'imagery_candidates', 'imagery_selected', 'analysis_progress', 'analysis_result', 'error'] })
    setLiveAoi(null)
    setRestoredAoi(null)
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
    if (launchLocked.current || farmId === selectedFarm) return
    setSelectedFarm(farmId)
    clearAoi()
  }

  const handleAoiChange = (geometry: AoiGeometry | null, areaHectares: number | null) => {
    if (launchLocked.current) return
    imageryRequest.current += 1
    setImageryIsSearching(false)
    resetAnalysisTracking()
    updateDraftTaskIds([])
    setRestoredAoi(null)
    dispatchTimeline({ type: 'removeKinds', kinds: ['aoi_ready', 'imagery_candidates', 'imagery_selected', 'analysis_progress', 'analysis_result', 'error'] })
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

  const startDemoTasks = (taskIds: WorkflowTaskId[]) => {
    if (live || stage === 'running') return
    if (taskIds.every((id) => id === 'lai' || id === 'growth')) void startAnalysis()
    else setAnalysisError('演示模式仅提供 LAI 和长势分析。')
  }

  const retryWorkflowStep = async (stepId: 'imagery' | 'crop' | 'lai' | 'potential' | 'yield_simple' | 'yield') => {
    if (!workflow) return
    setAnalysisError('')
    try {
      applyWorkflow(await retryAnalysisWorkflowStep(workflow.workflow_id, stepId))
    } catch (error) {
      setAnalysisError(error instanceof Error ? error.message : '重试任务失败')
    }
  }

  const updateYieldInputs = async (inputs: YieldAgronomicInputs) => {
    if (!workflow) throw new Error('当前没有可更新的工作流')
    const updated = await updateAnalysisWorkflowYieldInputs(workflow.workflow_id, inputs)
    applyWorkflow(updated)
  }

  const findImagery = async () => {
    if (launchLocked.current || imageryIsSearching || stage === 'running') return
    const requestId = ++imageryRequest.current
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
    setImageryIsSearching(true)
    setLiveCandidates(null)
    setSelectedImage('')
    setStage('idle')
    setLiveStatus('正在搜索 Sentinel-2 L2A 影像…')
    try {
      const items = await searchLiveImagery({
        aoi: { geometry: liveAoi, source: 'drawn', area_hectares: Number(liveAoiArea.toFixed(2)) },
        end_date: imagerySearchEndDate,
        max_cloud_cover: 20,
      })
      if (requestId !== imageryRequest.current) return
      setLiveCandidates(items)
      setSelectedImage('')
      setLiveStatus(items.length ? `找到 ${items.length} 景候选影像` : '未找到满足条件的候选影像')
      if (!items.length) setAnalysisError('未找到满足当前日期和云量条件的影像，可稍后重新搜索。')
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
      if (requestId !== imageryRequest.current) return
      const detail = error instanceof Error ? error.message : '影像搜索失败。'
      setAnalysisError(detail)
      dispatchTimeline({ type: 'upsert', item: { eventId: createWorkspaceTimelineEventId('error'), kind: 'error', detail, timestamp: new Date().toISOString() } })
    } finally {
      if (requestId === imageryRequest.current) setImageryIsSearching(false)
    }
  }

  const selectImageryCandidate = (candidateId: string) => {
    if (launchLocked.current || imageryIsSearching || stage === 'running') return
    const candidate = displayedCandidates.find((item) => item.id === candidateId)
    if (!candidate) return
    if (stage === 'done') {
      resetAnalysisTracking()
      clearAnalysisProducts()
      setAnalysisError('')
    }
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

  const workspaceContext = useMemo<WorkspaceContext>(() => {
    workspaceRevision.current = Math.max(Date.now(), workspaceRevision.current + 1)
    const candidate = liveCandidates?.find((item) => item.item_id === selectedImage)
    return {
      workspace_id: workspaceId, revision: workspaceRevision.current,
      execution_mode: live ? 'live' : 'demo', farm_id: selectedFarm,
      aoi: liveAoi && liveAoiArea != null ? { geometry: liveAoi, source: 'drawn', area_hectares: liveAoiArea } : null,
      imagery_item_id: selectedImage || null, imagery_snapshot: candidate ?? null,
      active_workflow_id: workflow?.workflow_id ?? null, draft_task_ids: draftTaskIds,
    }
  }, [workspaceId, live, selectedFarm, liveAoi, liveAoiArea, selectedImage, liveCandidates, workflow?.workflow_id, draftTaskIds])

  const workspaceContextRef = useRef(workspaceContext)
  workspaceContextRef.current = workspaceContext
  const onWorkflowLinked = useCallback(async (workflowId: string, activate = true) => {
    const captured = workspaceContextRef.current
    if (activate) window.localStorage.setItem(ACTIVE_WORKFLOW_KEY, workflowId)
    const created = await getAnalysisWorkflow(workflowId)
    appendTimelineItem({ eventId: `workflow-${workflowId}`, kind: 'workflow', workflow: created, timestamp: created.created_at })
    const current = workspaceContextRef.current
    if (!activate || current.workspace_id !== captured.workspace_id || current.imagery_item_id !== created.imagery_item_id || current.farm_id !== created.farm_id || JSON.stringify(current.aoi?.geometry) !== JSON.stringify(created.aoi.geometry)) return
    clearAnalysisProducts()
    updateDraftTaskIds(created.requested_task_ids)
    applyWorkflow(created)
  }, [applyWorkflow, appendTimelineItem, updateDraftTaskIds])
  const workspaceUi = buildWorkspaceUiState(workspaceContext, stage, { name: farm.name, locationLabel: farm.location_label, areaLabel: formatAoiArea(farm.area_hectares) }, displayedCandidates, timeline)
  if (visibleAnalysisTaskId) {
    const viewed = visibleAnalysisTaskId === workflow?.workflow_id ? workflow : timeline.find((item) => item.kind === 'workflow' && item.workflow.workflow_id === visibleAnalysisTaskId)
    const viewedWorkflow = viewed && 'workflow' in viewed ? viewed.workflow : viewed && 'workflow_id' in viewed ? viewed : null
    workspaceUi.cards = [...workspaceUi.cards.slice(0, 11), { card_id: 'analysis-panel-view', kind: 'workflow', title: '左侧正在查看的任务', state: visibleAnalysisTaskId === workflow?.workflow_id ? 'current' : 'historical', workflow_id: visibleAnalysisTaskId, summary: viewedWorkflow?.detail, task_ids: viewedWorkflow?.requested_task_ids, fields: { 展示位置: '左侧分析面板', 仅查看记录: visibleAnalysisTaskId === workflow?.workflow_id ? '否' : '是' } }]
  }
  const workspaceConversation = useWorkspaceConversation(appendTimelineItem, {
    context: workspaceContext, ui: workspaceUi, onWorkflowLinked,
    onDraftTasks: (tasks) => {
      if (stage === 'done') {
        resetAnalysisTracking()
        clearAnalysisProducts()
        setStage(selectedImage ? 'ready' : 'idle')
      }
      updateDraftTaskIds(tasks)
    },
    onDemoStart: startDemoTasks,
  })

  launchLocked.current = workspaceConversation.isLaunching

  useEffect(() => {
    let disposed = false
    void getWorkspaceWorkflows(workspaceId).then((items) => {
      if (!disposed) items.forEach((item) => appendTimelineItem({ eventId: `workflow-${item.workflow_id}`, kind: 'workflow', workflow: item, timestamp: item.created_at }))
    }).catch(() => { /* Current task restoration reports its own errors. */ })
    return () => { disposed = true }
  }, [workspaceId, appendTimelineItem])

  const { attention, acknowledge: acknowledgeAttention } = useWorkspaceAttention({ workflow, viewRequest: analysisView, restoredWorkflowId: restoredWorkflowId.current,
    aoiReady, selectedImage, draftSignature: draftTaskIds.join(','), candidateSignature: displayedCandidates.map((item) => item.id).join(','), imageryIsSearching, isLaunching: workspaceConversation.isLaunching, analysisError: analysisError || workspaceConversation.error })

  const historicalRunningIds = timeline.filter((item) => item.kind === 'workflow' && item.workflow.workflow_id !== workflow?.workflow_id && ['planned', 'running'].includes(item.workflow.status)).map((item) => item.kind === 'workflow' ? item.workflow.workflow_id : '').join(',')
  useEffect(() => {
    if (!historicalRunningIds) return
    let disposed = false
    const timer = window.setInterval(() => {
      void Promise.all(historicalRunningIds.split(',').map((id) => getAnalysisWorkflow(id).then((item) => {
        if (!disposed) appendTimelineItem({ eventId: `workflow-${id}`, kind: 'workflow', workflow: item, timestamp: item.created_at })
      }).catch(() => { /* Keep last known historical status. */ })))
    }, 3000)
    return () => { disposed = true; window.clearInterval(timer) }
  }, [historicalRunningIds, appendTimelineItem])

  const panelProps: WorkspacePanelProps = {
    farm: { name: farm.name, locationLabel: farm.location_label, areaLabel: formatAoiArea(farm.area_hectares) },
    aoiReady, aoiAreaLabel, imagerySearchEndDate, stage, timeline, selectedImage, selectedCandidate: displayedImage,
    analysisError, progress, detail: analysisDetail, elapsedSeconds, lastUpdateSeconds, delayed: analysisDelayed,
    connectionIssue: analysisConnectionIssue, pixelProgress, reportUrl, rasterUrl, cropAnalysis, workflow,
    onFindImagery: findImagery, onSelectCandidate: selectImageryCandidate, onStartAnalysis: () => void workspaceConversation.executeTasks(),
    onStartYieldDemo: (crop) => void workspaceConversation.executeTasks(crop),
    onRetryWorkflowStep: retryWorkflowStep, onUpdateYieldInputs: updateYieldInputs,
    onReset: () => { resetAnalysisTracking(); dispatchTimeline({ type: 'removeKinds', kinds: ['analysis_progress', 'analysis_result'] }); setStage(selectedImage ? 'ready' : 'idle'); setProgress(0); setAnalysisError('') },
    assistantIsSending: workspaceConversation.isSending, assistantIsLaunching: workspaceConversation.isLaunching,
    imageryIsSearching, assistantError: workspaceConversation.error, onSendAssistantMessage: workspaceConversation.sendMessage,
    onCancelAssistantMessage: workspaceConversation.cancelMessage, onRecoverTask: workspaceConversation.recoverWorkflow,
    executionMode: live ? 'live' : 'demo', workspaceContext, draftTaskIds, onDraftTaskIds: updateDraftTaskIds,
  }

  return (
    <main className="h-dvh min-h-0 overflow-hidden bg-[#071611] text-slate-100 selection:bg-emerald-400/30">
      <span role="status" aria-live="polite" className="sr-only">{attention?.unread ? attention.message : ''}</span>
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

      <section style={{ gridTemplateColumns: layout.docked ? `${layout.width}px minmax(0,1fr) ${layout.chatWidth}px` : `minmax(0,1fr) ${layout.chatWidth}px` }} className={`grid h-full pt-16 max-[680px]:block ${layout.resizing ? "select-none" : ""}`}>
        {!layout.docked && layout.drawerOpen && <button type="button" aria-label="关闭分析面板遮罩" onClick={layout.closeDrawer} className="fixed inset-0 top-16 z-[1000] bg-black/40" />}
        <aside aria-label="分析工作台" style={{ width: layout.width }} className={`${layout.docked ? 'relative z-20 flex' : layout.drawerOpen ? 'fixed bottom-0 left-0 top-16 z-[1100] flex shadow-2xl' : 'hidden'} min-h-0 flex-col border-r border-white/10 bg-[#0a1b16]`}>
          {!layout.docked && <div className="flex shrink-0 items-center justify-between border-b border-white/10 px-4 py-2"><span className="text-xs text-emerald-100">分析工作台</span><button type="button" aria-label="关闭分析面板" onClick={layout.closeDrawer} className="rounded p-1 text-slate-400 hover:text-white"><X size={16} /></button></div>}
          <details open className="group shrink-0 border-b border-white/10">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 text-xs text-slate-200"><span className="min-w-0"><span className="block font-medium">农场与图层</span><span className="mt-1 block truncate text-[10px] text-slate-500">{farm.name}</span></span><ChevronDown size={14} className="shrink-0 text-slate-500 group-open:rotate-180" /></summary>
            <div className="max-h-[30vh] overflow-y-auto px-3 pb-3">
          <div className="mb-4 flex items-center justify-between"><div><p className="text-xs font-medium text-white">农场边界</p><p className="mt-1 text-[11px] text-slate-500">{displayedFarms.length} 个可用范围</p></div><MapPinned size={15} className="text-emerald-300" /></div>
          <div className="space-y-2">
            {displayedFarms.map((item, index) => {
              const accent = farmAccent[index % farmAccent.length]
              const selected = item.farm_id === selectedFarm
              return <button key={item.farm_id} disabled={workspaceConversation.isLaunching} onClick={() => selectFarm(item.farm_id)} className={`w-full rounded-lg border p-3 text-left transition ${selected ? 'border-emerald-300/45 bg-emerald-400/[0.12] shadow-lg shadow-emerald-950/20' : 'border-white/[0.07] bg-white/[0.025] hover:border-white/15 hover:bg-white/[0.06]'}`}>
                <div className="flex items-start justify-between gap-2"><span className="text-xs font-medium text-slate-100">{item.name}</span><span className={`mt-0.5 h-2 w-2 rounded-full ${accent === 'emerald' ? 'bg-emerald-400' : accent === 'cyan' ? 'bg-cyan-400' : 'bg-amber-400'}`} /></div>
                <div className="mt-1.5 flex items-center justify-between gap-2 text-[10px] text-slate-500"><span className="truncate">{item.location_label}</span><span className="shrink-0">{formatAoiArea(item.area_hectares)}</span></div>
              </button>
            })}
          </div>
          <div className="mt-6 border-t border-white/10 pt-4">
            <div className="mb-2 flex items-center gap-2 text-xs font-medium text-slate-300"><Layers size={14} className="text-slate-500" />当前图层</div>
            <div className="space-y-2 text-[11px] text-slate-500"><p className="flex items-center gap-2"><i className="h-2 w-2 rounded-sm border border-emerald-200 bg-emerald-300/30" />农场边界</p><p className="flex items-center gap-2"><i className="h-2 w-2 rounded-sm border border-cyan-200 bg-cyan-300/30" />分析区域</p></div>
          </div>
            </div>
          </details>
          <WorkspaceAnalysisPanel {...panelProps} viewRequest={analysisView} onViewChange={setVisibleAnalysisTaskId} attention={attention} onAttentionRead={acknowledgeAttention} />
          {layout.docked && <div role="separator" tabIndex={0} aria-orientation="vertical" aria-label="调整分析面板宽度" aria-valuemin={280} aria-valuemax={layout.maximum} aria-valuenow={Math.round(layout.width)} {...layout.resizeHandlers} className="absolute -right-1 top-0 z-30 h-full w-2 cursor-col-resize touch-none bg-transparent transition hover:bg-emerald-400/30 focus:bg-emerald-400/30 focus:outline-none" />}
        </aside>

        <section className="relative isolate min-h-0 overflow-hidden bg-[#18392e] max-[680px]:h-[40dvh]" aria-label="遥感分析地图">
          {!layout.docked && <button type="button" id="workspace-open-analysis" aria-controls="workspace-analysis-panel" title={attention?.unread ? attention.message : undefined} onClick={() => openAnalysis(attention?.unread ? attention.workflowId : null)} style={{ '--analysis-attention-color': ATTENTION_COLORS[attention?.tone ?? 'info'] } as CSSProperties}
            className={`absolute left-16 top-16 z-[600] flex items-center gap-2 rounded-lg border border-emerald-300/25 bg-[#0b211b]/95 px-3 py-2 text-[11px] text-emerald-100 shadow-lg ${attention?.active ? 'workspace-attention-entry' : ''}`}><WandSparkles size={13} />{attention?.unread ? '查看分析提醒' : '打开分析面板'}{attention?.unread && <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: `rgb(${ATTENTION_COLORS[attention.tone]})` }} />}</button>}
          <div className={`h-full ${workspaceConversation.isLaunching ? 'pointer-events-none' : ''}`} aria-busy={workspaceConversation.isLaunching}>
          <LiveFarmMap
            farms={displayedFarms}
            selectedFarmId={selectedFarm}
            onFarmSelect={selectFarm}
            onAoiChange={handleAoiChange}
            onAoiError={setAnalysisError}
            clearVersion={aoiResetVersion}
            aoiAreaHectares={liveAoiArea}
            restoredAoi={restoredAoi}
            laiOverlay={laiOverlay}
            overlayVisible={overlayVisible}
            overlayOpacity={overlayOpacity}
            onOverlayVisibleChange={setOverlayVisible}
            onOverlayOpacityChange={setOverlayOpacity}
          />
          </div>
        </section>

        <WorkspaceAssistantPanel {...panelProps} onOpenAnalysis={openAnalysis} attention={attention} />
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
