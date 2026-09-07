import type { ReactNode } from 'react'
import { Bot, Check, ChevronRight, CloudSun, Crosshair, FileText, Layers, MapPinned, Play, RotateCcw, Search, WandSparkles, X } from 'lucide-react'
import type { LaiPixelProgress } from '../../services/spatialClient'
import { latestWorkspaceTimelineItem, type WorkspaceCandidateCardItem, type WorkspaceTimelineItem } from './workspaceTimeline'
import WorkspaceComposer from './WorkspaceComposer'

type AnalysisStage = 'idle' | 'candidates' | 'ready' | 'running' | 'done'

interface WorkspaceAssistantPanelProps {
  farm: { name: string; locationLabel: string; areaLabel: string }
  aoiReady: boolean
  aoiAreaLabel: string
  imagerySearchEndDate: string
  stage: AnalysisStage
  timeline: WorkspaceTimelineItem[]
  selectedImage: string
  selectedCandidate?: WorkspaceCandidateCardItem
  analysisError: string
  progress: number
  detail: string
  elapsedSeconds: number
  lastUpdateSeconds: number | null
  delayed: boolean
  connectionIssue: boolean
  pixelProgress: LaiPixelProgress | null
  reportUrl: string
  rasterUrl: string
  onFindImagery: () => void
  onSelectCandidate: (candidateId: string) => void
  onStartAnalysis: () => void
  onReset: () => void
  assistantIsSending: boolean
  assistantError: string
  onSendAssistantMessage: (message: string) => Promise<void>
  onCancelAssistantMessage: () => Promise<void>
}

const STAGE_STEPS = [
  ['影像准备', '正在读取 AOI 范围关键波段'],
  ['LAI 反演', '正在进行逐像元反演'],
  ['生成报告', '正在整理分析结果'],
]

/**
 * The Workspace page owns map and analysis state.  This panel only renders
 * that state as the established assistant card stack, so later Agent message
 * cards can join the same timeline without changing the map workflow.
 */
export default function WorkspaceAssistantPanel({
  farm,
  aoiReady,
  aoiAreaLabel,
  imagerySearchEndDate,
  stage,
  timeline,
  selectedImage,
  selectedCandidate,
  analysisError,
  progress,
  detail,
  elapsedSeconds,
  lastUpdateSeconds,
  delayed,
  connectionIssue,
  pixelProgress,
  reportUrl,
  rasterUrl,
  onFindImagery,
  onSelectCandidate,
  onStartAnalysis,
  onReset,
  assistantIsSending,
  assistantError,
  onSendAssistantMessage,
  onCancelAssistantMessage,
}: WorkspaceAssistantPanelProps) {
  const candidatesTimelineItem = latestWorkspaceTimelineItem(timeline, 'imagery_candidates')
  const selectionTimelineItem = latestWorkspaceTimelineItem(timeline, 'imagery_selected')
  const progressTimelineItem = latestWorkspaceTimelineItem(timeline, 'analysis_progress')
  const resultTimelineItem = latestWorkspaceTimelineItem(timeline, 'analysis_result')
  const errorTimelineItem = latestWorkspaceTimelineItem(timeline, 'error')
  const agentTimelineItems = timeline.filter((item) => item.kind === 'agent_user_message' || item.kind === 'agent_message')
  const currentStep = progress < 35 ? 0 : progress < 90 ? 1 : 2

  return <aside className="z-20 flex min-h-0 min-w-0 flex-col border-l border-white/10 bg-[#0b1d18]/95 backdrop-blur-xl max-[680px]:h-[calc(45vh-4rem)] max-[680px]:border-l-0 max-[680px]:border-t">
    <div className="border-b border-white/10 px-5 py-4"><div className="flex items-center gap-2"><span className="grid h-7 w-7 place-items-center rounded-lg bg-emerald-400/15 text-emerald-200"><Bot size={16} /></span><div><h1 className="text-sm font-semibold text-white">遥感分析</h1><p className="text-[10px] text-emerald-200/65">{farm.name} · {farm.locationLabel}</p></div></div></div>
    <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
      <AgentMessage icon={<MapPinned size={14} />} tone="emerald" title="当前农场" time="已定位"><b>{farm.name}</b><br />边界面积 {farm.areaLabel}</AgentMessage>
      {!aoiReady && <AgentMessage icon={<Crosshair size={14} />} tone="cyan" title="等待分析区域" time="AOI"><span>请在地图左上角绘制矩形或多边形区域。</span></AgentMessage>}
      {aoiReady && <AgentMessage icon={<Crosshair size={14} />} tone="cyan" title="分析区域已就绪" time="AOI"><b>{aoiAreaLabel}</b><br />边界编辑会自动同步面积与 GeoJSON。</AgentMessage>}
      {aoiReady && !candidatesTimelineItem && stage === 'idle' && <ActionCard title="搜索可用影像" subtitle={`Sentinel-2 L2A · 截止 ${imagerySearchEndDate} · Top 5 · 云量不高于 20%`} action="搜索 Sentinel 影像" onClick={onFindImagery} icon={<Search size={15} />} />}
      {candidatesTimelineItem && <CandidateList candidates={candidatesTimelineItem.candidates} selectedImage={selectedImage} onSelect={onSelectCandidate} />}
      {selectionTimelineItem && selectedCandidate && <><AgentMessage icon={<WandSparkles size={14} />} tone="amber" title="推荐影像已选定" time="影像"><b>{selectedCandidate.date}</b> · 云量 {selectedCandidate.cloud}</AgentMessage>{stage === 'ready' && <ActionCard title="启动 LAI 反演" subtitle={`${aoiAreaLabel} · ${selectedCandidate.id} · 20 m 分辨率`} action="开始反演" onClick={onStartAnalysis} icon={<Play size={15} />} strong />}</>}
      {(errorTimelineItem?.detail || analysisError) && <AgentMessage icon={<X size={14} />} tone="rose" title="操作提示" time="刚刚">{errorTimelineItem?.detail || analysisError}</AgentMessage>}
      {progressTimelineItem && <ProgressCard progress={progress} currentStep={currentStep} detail={detail} elapsedSeconds={elapsedSeconds} lastUpdateSeconds={lastUpdateSeconds} delayed={delayed} connectionIssue={connectionIssue} pixelProgress={pixelProgress} />}
      {resultTimelineItem && <ResultCard reportUrl={reportUrl} rasterUrl={rasterUrl} onReset={onReset} />}
      {agentTimelineItems.map((item) => item.kind === 'agent_user_message'
        ? <AgentMessage key={item.eventId} icon={<MapPinned size={14} />} tone="cyan" title="你的问题" time="刚刚">{item.message}</AgentMessage>
        : <AgentMessage key={item.eventId} icon={<Bot size={14} />} tone={item.status === 'failed' ? 'rose' : 'emerald'} title="遥感分析助手" time={item.status === 'streaming' ? '正在回答' : item.status === 'failed' ? '未完成' : '刚刚'}>{item.message}</AgentMessage>)}
    </div>
    <WorkspaceComposer isSending={assistantIsSending} error={assistantError} onSend={onSendAssistantMessage} onCancel={onCancelAssistantMessage} />
  </aside>
}

function CandidateList({ candidates, selectedImage, onSelect }: { candidates: WorkspaceCandidateCardItem[]; selectedImage: string; onSelect: (candidateId: string) => void }) {
  if (!candidates.length) return <AgentMessage icon={<CloudSun size={14} />} tone="amber" title="未找到候选影像" time="影像">请调整日期范围或云量条件后重试。</AgentMessage>
  return <article className="rounded-lg border border-white/10 bg-white/[0.035] p-3"><div className="mb-3 flex items-center gap-2"><CloudSun size={15} className="text-amber-300" /><div><p className="text-xs font-medium text-white">{candidates.length} 景候选影像</p><p className="mt-0.5 text-[10px] text-slate-500">选择一景后启动反演</p></div></div><div className="space-y-2">{candidates.map((item) => { const selected = item.id === selectedImage; const highlighted = selected || (!selectedImage && item.recommended); return <button key={item.id} type="button" aria-pressed={selected} onClick={() => onSelect(item.id)} className={`flex w-full items-center gap-2 rounded-lg border p-2 text-left transition ${highlighted ? 'border-emerald-300/50 bg-emerald-400/[0.1]' : 'border-white/[0.08] bg-black/10 hover:bg-white/[0.06]'}`}><span className={`h-9 w-1 shrink-0 rounded-full ${item.recommended ? 'bg-emerald-300' : 'bg-cyan-300/70'}`} /><span className="min-w-0 flex-1"><span className="flex items-center gap-1 text-[10px] font-medium text-slate-200">{item.date}{item.recommended && <em className="rounded bg-emerald-300/15 px-1 py-0.5 text-[8px] not-italic text-emerald-200">推荐</em>}</span><span className="mt-1 block text-[9px] text-slate-500">云量 {item.cloud}</span></span>{selected && <Check size={14} className="shrink-0 text-emerald-300" />}</button> })}</div></article>
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

function ProgressCard({ progress, currentStep, detail, elapsedSeconds, lastUpdateSeconds, delayed, connectionIssue, pixelProgress }: { progress: number; currentStep: number; detail: string; elapsedSeconds: number; lastUpdateSeconds: number | null; delayed: boolean; connectionIssue: boolean; pixelProgress: LaiPixelProgress | null }) {
  const currentDetail = detail || STAGE_STEPS[currentStep]?.[1] || '正在处理分析任务'
  const safeProgress = Math.max(0, Math.min(100, progress))
  return <article aria-live="polite" className={`rounded-lg border p-3 ${delayed ? 'border-amber-300/25 bg-amber-300/[0.05]' : 'border-cyan-300/20 bg-cyan-300/[0.055]'}`}>
    <div className="flex items-center justify-between gap-3"><div className="flex min-w-0 items-center gap-2 text-xs font-medium text-cyan-100"><Bot size={15} className="shrink-0" /><span className="truncate">正在执行 LAI 分析</span></div><span className="min-w-10 shrink-0 text-right text-[11px] tabular-nums text-cyan-200">{safeProgress}%</span></div>
    <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-950/80"><div className="h-full rounded-full bg-cyan-300 transition-all duration-300" style={{ width: `${safeProgress}%` }} /></div>
    <div className="mt-3 border-y border-white/[0.08] py-3"><p className="break-words text-[11px] leading-5 text-slate-200">{currentDetail}</p>{pixelProgress && pixelProgress.total_pixels > 0 && <div className="mt-3 grid grid-cols-[minmax(0,1fr)_auto] items-end gap-4 border-t border-white/[0.08] pt-3"><div className="min-w-0"><p className="text-[9px] text-slate-500">有效像元进度</p><p className="mt-1 truncate text-[12px] font-medium tabular-nums text-cyan-100">{pixelProgress.processed_pixels.toLocaleString()} / {pixelProgress.total_pixels.toLocaleString()}</p></div><div className="text-right"><p className="text-[9px] text-slate-500">当前像元</p><p className="mt-1 text-[12px] font-medium tabular-nums text-white">#{pixelProgress.current_pixel.toLocaleString()}</p></div></div>}{delayed && <p className="mt-2 flex items-start gap-2 text-[10px] leading-4 text-amber-200"><i className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-300 animate-pulse" />{currentStep === 0 ? '远程影像仍在读取，单个波段可能需要较长时间，任务仍在后台运行。' : '计算仍在进行，任务仍在后台运行。'}</p>}{connectionIssue && <p className="mt-2 flex items-start gap-2 text-[10px] leading-4 text-cyan-200/75"><RotateCcw size={11} className="mt-0.5 shrink-0 animate-spin" />实时连接正在恢复，状态查询仍在同步任务。</p>}</div>
    <dl className="grid grid-cols-3 border-b border-white/[0.08] py-2.5 text-[9px]"><div><dt className="text-slate-500">已用时</dt><dd className="mt-1 tabular-nums text-slate-300">{formatElapsed(elapsedSeconds)}</dd></div><div><dt className="text-slate-500">最近更新</dt><dd className="mt-1 text-slate-300">{formatLastUpdate(lastUpdateSeconds)}</dd></div><div><dt className="text-slate-500">状态来源</dt><dd className={`mt-1 ${connectionIssue ? 'text-amber-200' : 'text-emerald-200'}`}>{connectionIssue ? '轮询同步' : '实时同步'}</dd></div></dl>
    <div className="mt-3 space-y-3">{STAGE_STEPS.map(([name, stepDetail], index) => <div key={name} className="flex gap-2"><span className={`mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full text-[9px] ${index < currentStep ? 'bg-emerald-400 text-[#06261b]' : index === currentStep ? 'border border-cyan-300 bg-cyan-300/20 text-cyan-100 animate-pulse' : 'border border-white/15 text-slate-500'}`}>{index < currentStep ? <Check size={10} /> : index + 1}</span><div className="min-w-0"><p className={`text-[11px] ${index <= currentStep ? 'text-slate-100' : 'text-slate-500'}`}>{name}</p><p className="mt-0.5 break-words text-[9px] leading-4 text-slate-500">{index === currentStep ? stepDetail : index < currentStep ? '已完成' : '等待中'}</p></div></div>)}</div>
  </article>
}

function ResultCard({ onReset, reportUrl, rasterUrl }: { onReset: () => void; reportUrl: string; rasterUrl: string }) {
  return <article className="overflow-hidden rounded-lg border border-emerald-300/25 bg-[#0c2b20]"><div className="border-b border-emerald-300/10 bg-emerald-400/[0.08] p-3"><div className="flex items-center gap-2 text-xs font-semibold text-emerald-100"><span className="grid h-5 w-5 place-items-center rounded-full bg-emerald-400 text-[#052218]"><Check size={12} /></span>LAI 分析已完成</div><p className="mt-1 text-[10px] text-emerald-100/60">结果图层已叠加到地图，并写入分析产物</p></div><div className="space-y-2 p-3">{reportUrl ? <a href={reportUrl} target="_blank" rel="noreferrer" className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-400 py-2 text-[11px] font-medium text-[#06261b] hover:bg-emerald-300"><FileText size={14} />查看完整报告</a> : <p className="rounded-lg border border-white/10 px-3 py-2 text-center text-[10px] text-slate-400">报告产物将在任务完成后提供</p>}{rasterUrl && <a href={rasterUrl} className="flex w-full items-center justify-center gap-2 rounded-lg border border-emerald-300/20 py-2 text-[11px] text-emerald-100 hover:bg-emerald-400/10"><Layers size={14} />下载 LAI GeoTIFF</a>}<button onClick={onReset} className="flex w-full items-center justify-center gap-1 py-1 text-[10px] text-slate-500 hover:text-slate-200"><RotateCcw size={11} />基于当前 AOI 再次分析</button></div></article>
}
