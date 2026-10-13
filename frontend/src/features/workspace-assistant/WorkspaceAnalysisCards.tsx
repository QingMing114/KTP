import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Bot, Check, ChevronRight, CloudSun, FileText, Layers, Play, RotateCcw, Search, WandSparkles } from 'lucide-react'
import { loadHtmlReportObjectUrl, type AnalysisWorkflow, type CropAnalysis, type LaiPixelProgress, type YieldAgronomicInputs, type WorkflowTaskId } from '../../services/spatialClient'
import type { WorkspaceCandidateCardItem } from './workspaceTimeline'
import AnalysisDetails from './AnalysisDetails'
import { WORKSPACE_TASKS } from './workspaceTasks'
import { simpleYieldBlockedLabel } from './workspaceFlow'

const STAGE_STEPS = [
  ['影像准备', '正在读取 AOI 范围关键波段'],
  ['LAI 反演', '正在进行逐像元反演'],
  ['生成报告', '正在整理分析结果'],
]

export function CandidateList({ candidates, selectedImage, onSelect, disabled = false }: { candidates: WorkspaceCandidateCardItem[]; selectedImage: string; onSelect: (candidateId: string) => void; disabled?: boolean }) {
  if (!candidates.length) return <AgentMessage icon={<CloudSun size={14} />} tone="amber" title="未找到候选影像" time="影像">请调整日期范围或云量条件后重试。</AgentMessage>
  return <article className="rounded-lg border border-white/10 bg-white/[0.035] p-3"><div className="mb-3 flex items-center gap-2"><CloudSun size={15} className="text-amber-300" /><div><p className="text-xs font-medium text-white">{candidates.length} 景候选影像</p><p className="mt-0.5 text-[10px] text-slate-500">选择一景后组合专业任务</p></div></div><div className="space-y-2">{candidates.map((item) => { const selected = item.id === selectedImage; const highlighted = selected || (!selectedImage && item.recommended); return <button key={item.id} type="button" aria-pressed={selected} disabled={disabled} onClick={() => onSelect(item.id)} className={`flex w-full items-center gap-2 rounded-lg border p-2 text-left transition ${highlighted ? 'border-emerald-300/50 bg-emerald-400/[0.1]' : 'border-white/[0.08] bg-black/10 hover:bg-white/[0.06]'}`}><span className={`h-9 w-1 shrink-0 rounded-full ${item.recommended ? 'bg-emerald-300' : 'bg-cyan-300/70'}`} /><span className="min-w-0 flex-1"><span className="flex items-center gap-1 text-[10px] font-medium text-slate-200">{item.date}{item.recommended && <em className="rounded bg-emerald-300/15 px-1 py-0.5 text-[8px] not-italic text-emerald-200">推荐</em>}</span><span className="mt-1 block text-[9px] text-slate-500">云量 {item.cloud}</span></span>{selected && <Check size={14} className="shrink-0 text-emerald-300" />}</button> })}</div></article>
}

const PROFESSIONAL_TASKS = WORKSPACE_TASKS.map((task) => ({ ...task, icon: task.id === 'crop' ? <Search size={15} /> : task.id === 'growth' ? <WandSparkles size={15} /> : task.id === 'yield' || task.id === 'yield_simple' || task.id === 'forecast' ? <CloudSun size={15} /> : <Layers size={15} /> }))

type ProfessionalTaskId = (typeof PROFESSIONAL_TASKS)[number]['id']

export function ProfessionalTaskCard({ onStartTasks, initialTaskIds = [], onDraftTasks, executionMode, onStartYieldDemo, disabled = false }: { onStartTasks: (taskIds: ProfessionalTaskId[]) => void; initialTaskIds?: WorkflowTaskId[]; onDraftTasks: (tasks: WorkflowTaskId[]) => void; executionMode: 'live' | 'demo'; onStartYieldDemo?: (crop: 'wheat' | 'maize') => void; disabled?: boolean }) {
  const [editing, setEditing] = useState(!initialTaskIds.length)
  const [demoCrop, setDemoCrop] = useState<'wheat' | 'maize'>('wheat')
  const hasYield = initialTaskIds.some((id) => id === 'yield' || id === 'yield_simple')
  const onlyYield = initialTaskIds.every((id) => id === 'yield' || id === 'yield_simple')
  const selectedTasks = PROFESSIONAL_TASKS.filter((task) => initialTaskIds.includes(task.id as WorkflowTaskId))
  function toggleTask(taskId: ProfessionalTaskId) {
    if (disabled || taskId === 'forecast') return
    onDraftTasks(initialTaskIds.includes(taskId) ? initialTaskIds.filter((id) => id !== taskId) : [...initialTaskIds, taskId])
  }
  return <div aria-label="专业任务推荐" className="space-y-3">
    <div className="flex items-center justify-between text-[11px]"><span className="font-medium text-slate-200">{selectedTasks.length ? `已选 ${selectedTasks.length} 项任务` : '选择专业任务'}</span><button type="button" onClick={() => setEditing(!editing)} disabled={disabled} className="text-emerald-200 disabled:opacity-40">{editing ? '收起选项' : '调整任务'}</button></div>
    {editing && <div className="grid grid-cols-2 gap-2">{PROFESSIONAL_TASKS.map((task) => {
      const available = task.available && (executionMode === 'live' || task.id === 'lai' || task.id === 'growth')
      const selected = initialTaskIds.includes(task.id as WorkflowTaskId)
      return <button key={task.id} type="button" title={task.description} aria-pressed={selected} disabled={disabled || !available} onClick={() => toggleTask(task.id)} className={`rounded-lg border p-2 text-left transition disabled:opacity-45 ${selected ? 'border-emerald-300/60 bg-emerald-400/10' : 'border-white/10 bg-black/10 hover:border-white/25'}`}><span className="flex items-center justify-between text-emerald-300">{task.icon}<span className={`grid h-3.5 w-3.5 place-items-center rounded border ${selected ? 'border-emerald-300 bg-emerald-300 text-[#06261b]' : 'border-white/30'}`}>{selected && <Check size={10} />}</span></span><span className="mt-1.5 block text-[10px] font-medium text-white">{task.title}</span><span className="mt-1 block text-[9px] text-slate-500">{available ? task.status : task.available ? '实时模式可用' : task.status}</span></button>
    })}</div>}
    {initialTaskIds.includes('growth') && !initialTaskIds.includes('lai') && <p className="text-[10px] text-slate-400">长势评估会自动包含 LAI 反演。</p>}
    {(initialTaskIds.includes('potential') || initialTaskIds.includes('yield')) && <p className="text-[10px] leading-4 text-slate-400">将自动包含作物识别和 LAI 反演。{initialTaskIds.includes('yield') ? '估产缺少地块资料时会暂停，等待补充。' : ''}</p>}
    {initialTaskIds.includes('potential') && <p className="text-[10px] leading-4 text-amber-200/80">冠层指数为未校准的 0–100 分，不代表产量，不能替代 APSIM 估产。</p>}
    {initialTaskIds.includes('yield_simple') && <p className="text-[10px] leading-4 text-amber-200/80">小麦/玉米自动获取时序和辐射，无需填写播收日期。输出粮食干重的试验估计，尚未本地校准。</p>}
    <button type="button" disabled={disabled || !selectedTasks.length} onClick={() => onStartTasks(initialTaskIds)} className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-400 px-3 py-2.5 text-[11px] font-medium text-[#06261b] transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-40"><Play size={14} />{disabled ? '等待当前处理完成' : selectedTasks.length ? `开始执行 ${selectedTasks.length} 项任务` : '请选择需要执行的任务'}</button>
    {!!selectedTasks.length && <p className="text-center text-[9px] text-slate-500">也可以直接说“开始执行”</p>}
    {hasYield && executionMode === 'live' && onStartYieldDemo && <div className="space-y-2 rounded-lg border border-amber-300/20 bg-amber-300/5 p-3 text-[10px]">
      <p className="font-medium text-amber-100">估产模拟演示</p>
      <p className="leading-4 text-slate-400">使用预设生长曲线与产量示例，演示进度、结果和 APSIM 模板报告。无需补充农学资料，数值不代表实际产量。</p>
      <label className="block text-slate-300">演示作物<select value={demoCrop} disabled={disabled} onChange={(event) => setDemoCrop(event.target.value as 'wheat' | 'maize')} className="mt-1 w-full rounded border border-white/15 bg-[#0b1d18] p-2 text-white"><option value="wheat">小麦</option><option value="maize">玉米</option></select></label>
      {!onlyYield && <p className="text-amber-200">演示时请仅选择估产任务，依赖步骤会自动模拟。</p>}
      <button type="button" disabled={disabled || !onlyYield} onClick={() => onStartYieldDemo(demoCrop)} className="flex w-full items-center justify-center gap-2 rounded-lg border border-amber-300/40 px-3 py-2 font-medium text-amber-100 disabled:opacity-40"><Play size={12} />演示估产与报告</button>
    </div>}
  </div>
}

export function AgentMessage({ icon, tone, title, time, children }: { icon: ReactNode; tone: 'emerald' | 'cyan' | 'amber' | 'rose'; title: string; time: string; children: ReactNode }) {
  const colors = { emerald: 'border-emerald-300/15 bg-emerald-300/[0.055] text-emerald-200', cyan: 'border-cyan-300/15 bg-cyan-300/[0.055] text-cyan-200', amber: 'border-amber-300/15 bg-amber-300/[0.055] text-amber-200', rose: 'border-rose-300/15 bg-rose-300/[0.055] text-rose-200' }
  return <article className={`rounded-lg border p-3 ${colors[tone]}`}><div className="mb-2 flex items-center justify-between"><div className="flex items-center gap-1.5 text-[10px] font-medium">{icon}<span>{title}</span></div><span className="text-[9px] text-slate-500">{time}</span></div><div className="text-[11px] leading-5 text-slate-300">{children}</div></article>
}

export function ActionCard({ title, subtitle, action, onClick, icon, strong = false, disabled = false }: { title: string; subtitle: string; action: string; onClick: () => void; icon: ReactNode; strong?: boolean; disabled?: boolean }) {
  return <article className="rounded-lg border border-white/10 bg-white/[0.035] p-3"><p className="text-xs font-medium text-white">{title}</p><p className="mt-1 text-[10px] leading-4 text-slate-500">{subtitle}</p><button type="button" disabled={disabled} onClick={onClick} className={`mt-3 flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2 text-[11px] font-medium transition ${strong ? 'bg-emerald-400 text-[#06261b] hover:bg-emerald-300' : 'border border-emerald-300/25 bg-emerald-400/[0.08] text-emerald-100 hover:bg-emerald-400/[0.16]'}`}>{icon}{action}<ChevronRight size={13} /></button></article>
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

export function ProgressCard({ progress, currentStep, detail, elapsedSeconds, lastUpdateSeconds, delayed, connectionIssue, pixelProgress, executionMode }: { progress: number; currentStep: number; detail: string; elapsedSeconds: number; lastUpdateSeconds: number | null; delayed: boolean; connectionIssue: boolean; pixelProgress: LaiPixelProgress | null; executionMode: 'live' | 'demo' }) {
  const currentDetail = detail || STAGE_STEPS[currentStep]?.[1] || '正在处理分析任务'
  const safeProgress = Math.max(0, Math.min(100, progress))
  return <article aria-live="polite" className={`rounded-lg border p-3 ${delayed ? 'border-amber-300/25 bg-amber-300/[0.05]' : 'border-cyan-300/20 bg-cyan-300/[0.055]'}`}>
    <div className="flex items-center justify-between gap-3"><div className="flex min-w-0 items-center gap-2 text-xs font-medium text-cyan-100"><Bot size={15} className="shrink-0" /><span className="truncate">正在执行 LAI 分析</span></div><span className="min-w-10 shrink-0 text-right text-[11px] tabular-nums text-cyan-200">{safeProgress}%</span></div>
    {executionMode === 'demo' && <AnalysisDetails demo parts={[{ type: 'parameter_set', data: { state: 'effective', parameters: [{ name: '影像准备分辨率', value: 20, unit: 'm', source: 'algorithm_fixed', editable: false }, { name: '反演方法', value: 'PROSAIL / LAI（演示）', source: 'algorithm_fixed', editable: false }] } }]} />}
    <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-950/80"><div className="h-full rounded-full bg-cyan-300 transition-all duration-300" style={{ width: `${safeProgress}%` }} /></div>
    <div className="mt-3 border-y border-white/[0.08] py-3"><p className="break-words text-[11px] leading-5 text-slate-200">{currentDetail}</p>{pixelProgress && pixelProgress.total_pixels > 0 && <div className="mt-3 grid grid-cols-[minmax(0,1fr)_auto] items-end gap-4 border-t border-white/[0.08] pt-3"><div className="min-w-0"><p className="text-[9px] text-slate-500">有效像元进度</p><p className="mt-1 truncate text-[12px] font-medium tabular-nums text-cyan-100">{pixelProgress.processed_pixels.toLocaleString()} / {pixelProgress.total_pixels.toLocaleString()}</p></div><div className="text-right"><p className="text-[9px] text-slate-500">当前像元</p><p className="mt-1 text-[12px] font-medium tabular-nums text-white">#{pixelProgress.current_pixel.toLocaleString()}</p></div></div>}{delayed && <p className="mt-2 flex items-start gap-2 text-[10px] leading-4 text-amber-200"><i className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-300 animate-pulse" />{currentStep === 0 ? '远程影像仍在读取，单个波段可能需要较长时间，任务仍在后台运行。' : '计算仍在进行，任务仍在后台运行。'}</p>}{connectionIssue && <p className="mt-2 flex items-start gap-2 text-[10px] leading-4 text-cyan-200/75"><RotateCcw size={11} className="mt-0.5 shrink-0 animate-spin" />实时连接正在恢复，状态查询仍在同步任务。</p>}</div>
    <dl className="grid grid-cols-3 border-b border-white/[0.08] py-2.5 text-[9px]"><div><dt className="text-slate-500">已用时</dt><dd className="mt-1 tabular-nums text-slate-300">{formatElapsed(elapsedSeconds)}</dd></div><div><dt className="text-slate-500">最近更新</dt><dd className="mt-1 text-slate-300">{formatLastUpdate(lastUpdateSeconds)}</dd></div><div><dt className="text-slate-500">状态来源</dt><dd className={`mt-1 ${connectionIssue ? 'text-amber-200' : 'text-emerald-200'}`}>{connectionIssue ? '轮询同步' : '实时同步'}</dd></div></dl>
    <div className="mt-3 space-y-3">{(executionMode === "demo" ? STAGE_STEPS : []).map(([name, stepDetail], index) => <div key={name} className="flex gap-2"><span className={`mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full text-[9px] ${index < currentStep ? 'bg-emerald-400 text-[#06261b]' : index === currentStep ? 'border border-cyan-300 bg-cyan-300/20 text-cyan-100 animate-pulse' : 'border border-white/15 text-slate-500'}`}>{index < currentStep ? <Check size={10} /> : index + 1}</span><div className="min-w-0"><p className={`text-[11px] ${index <= currentStep ? 'text-slate-100' : 'text-slate-500'}`}>{name}</p><p className="mt-0.5 break-words text-[9px] leading-4 text-slate-500">{index === currentStep ? stepDetail : index < currentStep ? '已完成' : '等待中'}</p></div></div>)}</div>
  </article>
}

export function ResultCard({ onReset, reportUrl, rasterUrl }: { onReset: () => void; reportUrl: string; rasterUrl: string }) {
  return <article className="overflow-hidden rounded-lg border border-emerald-300/25 bg-[#0c2b20]"><div className="border-b border-emerald-300/10 bg-emerald-400/[0.08] p-3"><div className="flex items-center gap-2 text-xs font-semibold text-emerald-100"><span className="grid h-5 w-5 place-items-center rounded-full bg-emerald-400 text-[#052218]"><Check size={12} /></span>LAI 分析已完成</div><p className="mt-1 text-[10px] text-emerald-100/60">结果图层已叠加到地图，并写入分析产物</p></div><div className="space-y-2 p-3">{reportUrl ? <a href={reportUrl} target="_blank" rel="noreferrer" className="flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-400 py-2 text-[11px] font-medium text-[#06261b] hover:bg-emerald-300"><FileText size={14} />查看完整报告</a> : <p className="rounded-lg border border-white/10 px-3 py-2 text-center text-[10px] text-slate-400">报告产物将在任务完成后提供</p>}{rasterUrl && <a href={rasterUrl} className="flex w-full items-center justify-center gap-2 rounded-lg border border-emerald-300/20 py-2 text-[11px] text-emerald-100 hover:bg-emerald-400/10"><Layers size={14} />下载 LAI GeoTIFF</a>}<button onClick={onReset} className="flex w-full items-center justify-center gap-1 py-1 text-[10px] text-slate-500 hover:text-slate-200"><RotateCcw size={11} />基于当前 AOI 再次分析</button></div></article>
}

export function CropAnalysisCard({ analysis, onReset }: { analysis: CropAnalysis; onReset: () => void }) {
  const result = analysis.result
  const ranked = [...(result.class_scores ?? [])].sort((a, b) => b.score - a.score)
  return <article aria-live="polite" className="rounded-lg border border-emerald-300/25 bg-[#102820] p-3">
    <div className="flex items-center justify-between gap-2"><h2 className="flex items-center gap-2 text-xs font-semibold text-emerald-100"><Search size={14} />农作物识别{analysis.status === 'completed' ? '结果' : '任务'}</h2><span className="text-[10px] text-emerald-200">{analysis.progress_percent}%</span></div>
    {analysis.status !== 'completed' && <><div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-950/80"><div className="h-full bg-emerald-300 transition-all" style={{ width: `${analysis.progress_percent}%` }} /></div><p className={`mt-2 text-[10px] ${analysis.status === 'failed' ? 'text-rose-200' : 'text-slate-300'}`}>{analysis.detail}</p></>}
    {analysis.status === 'completed' && result.predicted_class && <><p className="mt-3 text-sm font-semibold text-white">{result.predicted_class.name_zh} <span className="text-[10px] font-normal text-slate-400">{result.predicted_class.name}</span></p><p className="mt-1 text-[10px] text-slate-400">模型输出分数 {(result.predicted_class.score * 100).toFixed(1)}%</p><div className="mt-3 space-y-1.5">{ranked.map((entry) => <div key={entry.class_id} className="grid grid-cols-[4.5rem_1fr_2.5rem] items-center gap-2 text-[10px]"><span className="text-slate-300">{entry.name_zh}</span><div className="h-1.5 overflow-hidden rounded-full bg-slate-900"><div className="h-full bg-emerald-400" style={{ width: `${entry.score * 100}%` }} /></div><span className="text-right tabular-nums text-slate-300">{(entry.score * 100).toFixed(1)}%</span></div>)}</div>{result.input && <p className="mt-3 text-[9px] text-slate-500">Sentinel-2 · {result.input.resolution_m} m · 有效像元 {result.input.valid_pixels}</p>}{result.warnings?.map((warning) => <p key={warning} className="mt-2 text-[9px] leading-4 text-amber-200/80">{warning}</p>)}</>}
    {analysis.status === 'completed' && <ReportLink uri={result.report_uri} label="查看作物识别报告" />}
    {(analysis.status === 'completed' || analysis.status === 'failed') && <button type="button" onClick={onReset} className="mt-3 flex items-center gap-1 text-[10px] text-emerald-200 hover:text-emerald-100"><RotateCcw size={11} />再次分析</button>}
  </article>
}

function ReportLink({ uri, label }: { uri?: string | null; label: string }) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    if (!uri) return undefined
    let disposed = false
    let loadedUrl = ''
    loadHtmlReportObjectUrl(uri).then((nextUrl) => {
      if (disposed) URL.revokeObjectURL(nextUrl)
      else { loadedUrl = nextUrl; setUrl(nextUrl); setError('') }
    }).catch((cause) => { if (!disposed) setError(cause instanceof Error ? cause.message : '报告加载失败') })
    return () => { disposed = true; if (loadedUrl) URL.revokeObjectURL(loadedUrl); setUrl(''); setError('') }
  }, [uri])
  if (!uri) return null
  return <span className="mt-2 block text-[10px]">{url
    ? <a href={url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-emerald-200 hover:text-white"><FileText size={11} />{label}</a>
    : <span className={error ? 'text-rose-200' : 'text-slate-500'}>{error || '正在加载报告…'}</span>}</span>
}

export function WorkflowCard({ workflow, onRetry, onUpdateYieldInputs, onReset, readOnly = false }: { workflow: AnalysisWorkflow; onRetry: (stepId: 'imagery' | 'crop' | 'lai' | 'potential' | 'yield_simple' | 'yield') => void; onUpdateYieldInputs: (inputs: YieldAgronomicInputs) => Promise<void>; onReset: () => void; readOnly?: boolean }) {
  const labels: Record<string, string> = { imagery: '影像准备', crop: '农作物识别', lai: 'PROSAIL / LAI 反演', growth: '作物长势评估', potential: '遥感冠层指数', yield_simple: '自动简化估产（试验）', yield: 'APSIM 产量估计' }
  const statusLabels: Record<string, string> = { planned: '等待', waiting: '等待', running: '执行中', completed: '完成', blocked: '待补充输入', failed: '失败', skipped: '跳过' }
  const crop = workflow.steps.find((step) => step.step_id === 'crop')
  const lai = workflow.steps.find((step) => step.step_id === 'lai')
  const prediction = crop?.result.predicted_class && typeof crop.result.predicted_class === 'object' ? crop.result.predicted_class as { name_zh?: string; name?: string; score?: number } : null
  const scores = Array.isArray(crop?.result.class_scores) ? crop.result.class_scores as Array<{ class_id: number; name_zh: string; score: number }> : []
  const laiMean = typeof lai?.result.lai_mean === 'number' ? lai.result.lai_mean : null
  const quality = lai?.result.quality && typeof lai.result.quality === 'object' ? lai.result.quality as { valid_pixel_count?: number; valid_pixel_fraction?: number } : null
  const observationAt = typeof lai?.result.observation_at === 'string' ? lai.result.observation_at.slice(0, 10) : ''
  const reportUri = typeof lai?.result.report_uri === 'string' ? lai.result.report_uri : ''
  const growth = workflow.steps.find((step) => step.step_id === 'growth')
  const potential = workflow.steps.find((step) => step.step_id === 'potential')
  const potentialReportUri = typeof potential?.result.report_uri === 'string' ? potential.result.report_uri : ''
  const simpleYield = workflow.steps.find((step) => step.step_id === 'yield_simple')
  const simpleSeason = simpleYield?.result.season as { start?: string; end?: string; observations?: number } | undefined
  const simpleRange = simpleYield?.result.parameter_scenario_range_t_ha as number[] | undefined
  const yieldStep = workflow.steps.find((step) => step.step_id === 'yield')
  const yieldReportUri = typeof yieldStep?.result.report_uri === 'string' ? yieldStep.result.report_uri : ''
  const yieldAssessment = yieldStep?.result.input_assessment && typeof yieldStep.result.input_assessment === 'object'
    ? yieldStep.result.input_assessment as { status?: string; resolved_crop?: string | null; crop_source?: string; lai_use?: string; imagery_acquired_at?: string; lai_observation?: { observed_at?: string; lai_mean?: number }; field_dataset?: { dataset_id?: string; verified_by?: string; weather_period?: string[] }; sources?: Record<string, string>; issues?: Array<{ code: string; field: string; message: string }> }
    : null
  const warnings = Array.isArray(crop?.result.warnings) ? crop.result.warnings.filter((warning): warning is string => typeof warning === 'string') : []
  const busy = workflow.status === 'running' || workflow.status === 'planned'
  const demo = workflow.data_mode === 'demo'

  return <article aria-live="polite" data-data-mode={workflow.data_mode ?? 'live'} className="rounded-lg border border-emerald-300/25 bg-[#102820] p-3">
    <div className="flex items-center justify-between gap-2"><h2 className="flex items-center gap-2 text-xs font-semibold text-emerald-100"><WandSparkles size={14} />任务进度与结果</h2><span className={`text-[10px] ${workflow.status === 'failed' ? 'text-rose-200' : workflow.status === 'blocked' ? 'text-amber-200' : 'text-emerald-200'}`}>{workflow.status === 'blocked' && simpleYield?.status === 'blocked' ? simpleYieldBlockedLabel(simpleYield.result.reason_code) : statusLabels[workflow.status] ?? workflow.status}</span></div>
    <p className="mt-2 text-[10px] leading-4 text-slate-400">{workflow.detail}</p>
    {demo && <p role="note" className="mt-2 rounded-md border border-amber-300/25 bg-amber-300/5 p-2 text-[10px] leading-5 text-amber-100">模拟数据 · 仅用于功能演示。未运行 APSIM，未读取地块影像、气象或土壤；数值不代表实际产量。</p>}
    <AnalysisDetails demo={demo} parts={[{ type: 'parameter_set', data: { state: 'effective', parameters: demo ? [
      { name: '数据来源', value: '构造的模拟数据', source: 'demo', editable: false },
      { name: '演示作物', value: workflow.demo_crop === 'maize' ? '玉米' : '小麦', source: 'demo', editable: false },
      { name: '报告模板', value: 'APSIM 生长曲线报告', source: 'demo', editable: false },
    ] : [
      { name: '选区面积', value: workflow.aoi.area_hectares, unit: 'ha', source: 'user', editable: false },
      { name: '影像准备分辨率', value: workflow.parameters?.target_resolution_m ?? 20, unit: 'm', source: 'algorithm_fixed', editable: false },
      { name: '共享反射率波段', value: (workflow.parameters?.reflectance_bands ?? ['B02', 'B03', 'B04', 'B07', 'B08']).join(' / '), source: 'algorithm_fixed', editable: false },
    ] } }]} />
    <p className="mt-1 break-all text-[9px] text-slate-500">影像 {workflow.imagery_snapshot?.acquired_at?.slice(0, 10) ?? '—'} · {workflow.imagery_item_id} · 任务 {workflow.requested_task_ids.map((id) => labels[id]).join('、')}</p>
    {!busy && <ReportLink uri={workflow.report_uri} label="查看工作流总报告" />}
    <div className="mt-3 space-y-2 border-t border-white/10 pt-3">{workflow.steps.map((step) => <div key={step.step_id} className="rounded-md border border-white/[0.07] bg-black/10 p-2"><div className="flex items-center justify-between gap-2 text-[10px]"><span className="font-medium text-slate-100">{labels[step.step_id]}</span><span className={step.status === 'failed' ? 'text-rose-200' : step.status === 'blocked' ? 'text-amber-200' : step.status === 'completed' ? 'text-emerald-200' : 'text-cyan-200'}>{step.status === 'blocked' && step.step_id === 'yield_simple' ? simpleYieldBlockedLabel(step.result.reason_code) : statusLabels[step.status]}{step.status === 'running' ? ` ${step.progress_percent}%` : ''}</span></div>{step.depends_on.length > 0 && <p className="mt-1 text-[9px] text-slate-500">依赖：{step.depends_on.map((id) => labels[id]).join('、')}</p>}{step.status === 'running' && <div className="mt-2 h-1 overflow-hidden rounded-full bg-slate-950"><div className="h-full bg-cyan-300 transition-all" style={{ width: `${step.progress_percent}%` }} /></div>}{step.detail && <p className="mt-1 break-words text-[9px] leading-4 text-slate-400">{step.detail}</p>}{!readOnly && !busy && !(step.step_id === 'yield_simple' && step.result.reason_code === 'crop_confirmation_required') && (step.status === 'failed' || (step.status === 'blocked' && step.step_id !== 'growth' && step.step_id !== 'yield')) && (step.step_id === 'imagery' || step.step_id === 'crop' || step.step_id === 'lai' || step.step_id === 'yield_simple' || step.step_id === 'yield') && <button type="button" onClick={() => onRetry(step.step_id as 'imagery' | 'crop' | 'lai' | 'yield_simple' | 'yield')} className="mt-2 flex items-center gap-1 text-[9px] text-emerald-200 hover:text-white"><RotateCcw size={10} />重试此步骤</button>}</div>)}</div>
    {prediction && crop?.status === 'completed' && <div className="mt-3 border-t border-white/10 pt-3"><p className="text-[10px] text-slate-400">作物识别结果</p><p className="mt-1 text-sm font-semibold text-white">{prediction.name_zh} <span className="text-[10px] font-normal text-slate-400">{prediction.name} · 模型分数 {typeof prediction.score === 'number' ? (prediction.score * 100).toFixed(1) : '—'}%</span></p><div className="mt-2 space-y-1">{[...scores].sort((a, b) => b.score - a.score).map((score) => <div key={score.class_id} className="grid grid-cols-[3.5rem_1fr_2.3rem] items-center gap-2 text-[9px] text-slate-300"><span>{score.name_zh}</span><div className="h-1 overflow-hidden rounded-full bg-slate-900"><div className="h-full bg-emerald-400" style={{ width: `${score.score * 100}%` }} /></div><span className="text-right">{(score.score * 100).toFixed(1)}%</span></div>)}</div>{warnings.map((warning) => <p key={warning} className="mt-2 text-[9px] leading-4 text-amber-200/80">{warning}</p>)}<ReportLink uri={typeof crop.result.report_uri === 'string' ? crop.result.report_uri : ''} label="查看作物识别报告" /></div>}
    {lai?.status === 'completed' && <div className="mt-3 border-t border-white/10 pt-3"><p className="text-[10px] text-slate-400">LAI 观测结果 {observationAt && `· ${observationAt}`}</p><p className="mt-1 text-sm font-semibold text-white">{laiMean == null ? '—' : laiMean.toFixed(2)} <span className="text-[10px] font-normal text-slate-400">m²/m² · 选区均值</span></p>{quality && <p className="mt-1 text-[9px] text-slate-400">有效像元 {quality.valid_pixel_count ?? '—'} · 有效比例 {typeof quality.valid_pixel_fraction === 'number' ? `${(quality.valid_pixel_fraction * 100).toFixed(1)}%` : '—'}</p>}<ReportLink uri={reportUri} label="查看 LAI 报告" /></div>}
      {growth?.status === 'completed' && <p className="mt-3 border-t border-white/10 pt-3 text-[9px] leading-4 text-slate-300">当前影像摘要：LAI {typeof growth.result.lai_mean === 'number' ? growth.result.lai_mean.toFixed(2) : '—'}，有效像元比例 {typeof growth.result.vegetation_ratio === 'number' ? `${growth.result.vegetation_ratio.toFixed(1)}%` : '—'}。尚未按生育期判定等级。<ReportLink uri={typeof growth.result.report_uri === 'string' ? growth.result.report_uri : ''} label="查看长势观测报告" /></p>}
      {potential?.status === 'completed' && typeof potential.result.canopy_index === 'number' && <div className="mt-3 border-t border-white/10 pt-3 text-[10px] text-slate-200"><p className="font-medium text-emerald-100">遥感冠层指数 {potential.result.canopy_index.toFixed(1)} / 100</p><p className="mt-1 text-slate-400">NDVI 中位数 {typeof potential.result.ndvi_median === 'number' ? potential.result.ndvi_median.toFixed(3) : '—'} · LAI {typeof potential.result.lai_mean === 'number' ? potential.result.lai_mean.toFixed(2) : '—'} · 观测日 {String(potential.result.observed_at ?? '').slice(0, 10)}</p>{typeof potential.result.signal_warning === 'string' && <p className="mt-2 text-[9px] leading-4 text-amber-200">{potential.result.signal_warning}</p>}<p className="mt-2 text-[9px] leading-4 text-amber-200">{String(potential.result.uncertainty_note ?? '')}</p><ReportLink uri={potentialReportUri} label="查看试验报告" /></div>}
      {potential && !readOnly && !busy && (potential.status === 'failed' || potential.status === 'blocked') && crop?.status === 'completed' && lai?.status === 'completed' && <button type="button" onClick={() => onRetry('potential')} className="mt-2 flex items-center gap-1 text-[9px] text-emerald-200"><RotateCcw size={10} />重试冠层指数</button>}
      {simpleYield?.status === 'completed' && typeof simpleYield.result.estimated_yield_t_ha === 'number' && <div className="mt-3 border-t border-white/10 pt-3 text-[10px] text-slate-200">
        <p className="font-medium text-emerald-100">{demo ? '模拟单产（粮食干重）' : '粮食干重试验估计'} {simpleYield.result.estimated_yield_t_ha.toFixed(2)} t/ha</p>
        {simpleRange?.length === 2 && <p className="mt-1 text-slate-400">{demo ? '示例情景范围' : '参数情景范围'} {simpleRange[0].toFixed(2)}–{simpleRange[1].toFixed(2)} t/ha</p>}
        <p className="mt-1 leading-4 text-slate-400">{String(simpleYield.result.crop_label ?? '')} · {demo ? '预设生长期' : '遥感生长期'} {simpleSeason?.start} 至 {simpleSeason?.end} · {simpleSeason?.observations} {demo ? '条模拟记录' : '次清晰观测'}</p>
        {demo ? <p className="mt-2 leading-4 text-amber-200/80">{typeof simpleYield.result.estimated_total_t === 'number' && `示例总产量 ${simpleYield.result.estimated_total_t.toFixed(2)} t（当前面积 × 模拟单产）。`}日期和曲线均为演示预设。</p> : <p className="mt-2 leading-4 text-amber-200/80">自动识别的日期不是实际播种/收获记录。未用本地实收数据校准，参数范围不是置信区间。</p>}
        <ReportLink uri={typeof simpleYield.result.report_uri === 'string' ? simpleYield.result.report_uri : ''} label={demo ? '查看估产演示报告（APSIM 模板）' : '查看简化估产方法与数据报告'} />
      </div>}
      {simpleYield?.status === 'blocked' && simpleYield.result.reason_code === 'crop_confirmation_required' && !readOnly && !busy && <SimpleYieldCropForm inputs={workflow.yield_inputs} onSave={onUpdateYieldInputs} />}
      {yieldAssessment && <div className="mt-3 border-t border-white/10 pt-3"><p className="text-[10px] font-medium text-amber-100">{yieldAssessment.status === 'ready' ? '产量估计输入已核验' : `产量估计启动条件 · 尚有 ${yieldAssessment.issues?.length ?? 0} 项缺口`}</p><p className="mt-1 text-[9px] text-slate-400">映射作物：{yieldAssessment.resolved_crop ?? '尚未支持或确认'} · 来源：{yieldAssessment.crop_source === 'user_confirmed' ? '用户确认' : '模型识别'} · 遥感 LAI 观测日：{yieldAssessment.lai_observation?.observed_at?.slice(0, 10) ?? '—'}。按同日 APSIM 模拟 LAI 筛选情景。</p>{yieldAssessment.field_dataset && <p className="mt-1 text-[9px] text-slate-400">数据集 {yieldAssessment.field_dataset.dataset_id} · 核验人 {yieldAssessment.field_dataset.verified_by} · 气象覆盖 {yieldAssessment.field_dataset.weather_period?.join(' 至 ')}</p>}{yieldAssessment.sources && <p className="mt-1 text-[9px] text-slate-500">来源：气象 {yieldAssessment.sources.daily_weather === 'verified_dataset' ? '已核验' : '待核验'} · 土壤 {yieldAssessment.sources.soil_profile === 'verified_dataset' ? '已核验' : '待核验'} · 管理 {yieldAssessment.sources.management === 'verified_dataset' ? '已核验' : '待核验'} · APSIM {yieldAssessment.sources.apsim_runtime === 'verified' ? '已验证' : '待验证'}</p>}<ul className="mt-2 space-y-1 text-[9px] leading-4 text-amber-100/80">{yieldAssessment.issues?.map((issue) => <li key={issue.code}>• {issue.message}</li>)}</ul></div>}
      {yieldStep && !readOnly && !busy && yieldStep.status !== 'completed' && <YieldInputsForm inputs={workflow.yield_inputs} observationAt={observationAt} busy={yieldStep.status === 'running'} onSave={onUpdateYieldInputs} />}
      {yieldStep?.status === 'completed' && typeof yieldStep.result.constrained_yield_t_ha === 'number' && <div className="mt-3 border-t border-white/10 pt-3 text-[10px] text-slate-200"><p>{demo ? '模拟单产（粮食干重）' : 'APSIM + LAI 情景估产'}：{yieldStep.result.constrained_yield_t_ha.toFixed(2)} t/ha</p><p className="mt-1 text-slate-400">{demo ? '示例基线' : '基线'} {typeof yieldStep.result.baseline_yield_t_ha === 'number' ? yieldStep.result.baseline_yield_t_ha.toFixed(2) : '—'} t/ha · {demo ? '示例入选' : '入选'} {String(yieldStep.result.accepted_count ?? '—')}/{String(yieldStep.result.scenario_count ?? '—')} 个情景</p>{demo && typeof yieldStep.result.estimated_total_t === 'number' && <p className="mt-1 text-slate-400">示例总产量 {yieldStep.result.estimated_total_t.toFixed(2)} t（当前面积 × 模拟单产）</p>}<ReportLink uri={yieldReportUri} label={demo ? '查看估产演示报告（APSIM 模板）' : '查看产量报告'} /><p className="mt-2 text-[9px] text-amber-200/80">{String(yieldStep.result.uncertainty_note ?? '')}</p></div>}
      {!readOnly && !busy && <button type="button" onClick={onReset} className="mt-3 flex items-center gap-1 text-[10px] text-slate-400 hover:text-white"><RotateCcw size={11} />基于当前 AOI 再次分析</button>}
  </article>
}

function YieldInputsForm({ inputs, observationAt, busy, onSave }: { inputs: YieldAgronomicInputs; observationAt: string; busy: boolean; onSave: (inputs: YieldAgronomicInputs) => Promise<void> }) {
  const [cropId, setCropId] = useState(inputs.confirmed_crop_class_id == null ? '' : String(inputs.confirmed_crop_class_id))
  const [cultivar, setCultivar] = useState(inputs.cultivar ?? '')
  const [sowingDate, setSowingDate] = useState(inputs.sowing_date ?? '')
  const [datasetId, setDatasetId] = useState(inputs.field_dataset_id ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const cropClasses = ['玉米', '棉花（估产暂不支持）', '大豆', '春小麦', '冬小麦', '大麦（估产暂不支持）']

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      await onSave({
        confirmed_crop_class_id: cropId === '' ? null : Number(cropId),
        cultivar: cultivar.trim() || null,
        sowing_date: sowingDate || null,
        field_dataset_id: datasetId.trim() || null,
      })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '农学输入保存失败')
    } finally {
      setSaving(false)
    }
  }

  return <form onSubmit={(event) => void save(event)} className="mt-3 space-y-2 border-t border-white/10 pt-3 text-[10px] text-slate-300">
    <p className="font-medium text-white">核对产量估计输入</p>
    <p className="text-[9px] leading-4 text-slate-400">确认作物、品种和实际播期。数据集 ID 由地块资料管理员核验后提供；填写未经核验的 ID 不会产生估产。</p>
    <label className="block">确认作物<select value={cropId} onChange={(event) => setCropId(event.target.value)} className="mt-1 w-full rounded border border-white/15 bg-[#0b1d18] p-2 text-white"><option value="">沿用模型识别</option>{cropClasses.map((name, id) => <option key={id} value={id}>{name}</option>)}</select></label>
    <label className="block">品种<input value={cultivar} onChange={(event) => setCultivar(event.target.value)} maxLength={120} placeholder="填写实际种植品种" className="mt-1 w-full rounded border border-white/15 bg-[#0b1d18] p-2 text-white" /></label>
    <label className="block">实际播种日期<input type="date" value={sowingDate} max={observationAt || undefined} onChange={(event) => setSowingDate(event.target.value)} className="mt-1 w-full rounded border border-white/15 bg-[#0b1d18] p-2 text-white" /></label>
    <label className="block">已核验地块数据集 ID<input value={datasetId} onChange={(event) => setDatasetId(event.target.value)} maxLength={80} pattern="[a-zA-Z0-9][a-zA-Z0-9_-]*" placeholder="由地块资料管理员提供" className="mt-1 w-full rounded border border-white/15 bg-[#0b1d18] p-2 text-white" /></label>
    {error && <p role="alert" className="text-rose-200">{error}</p>}
    <button type="submit" disabled={busy || saving} className="rounded bg-emerald-400 px-3 py-2 font-medium text-[#06261b] disabled:cursor-not-allowed disabled:opacity-50">{saving ? '正在核验…' : '保存并核验输入'}</button>
  </form>
}

function SimpleYieldCropForm({ inputs, onSave }: { inputs: YieldAgronomicInputs; onSave: (inputs: YieldAgronomicInputs) => Promise<void> }) {
  const [crop, setCrop] = useState(inputs.confirmed_crop_class_id == null ? '' : String(inputs.confirmed_crop_class_id))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!crop || busy) return
    setBusy(true); setError('')
    try { await onSave({ ...inputs, confirmed_crop_class_id: Number(crop) }) }
    catch (cause) { setError(cause instanceof Error ? cause.message : '作物确认失败') }
    finally { setBusy(false) }
  }
  return <form onSubmit={(event) => void submit(event)} className="mt-3 space-y-2 border-t border-white/10 pt-3 text-[10px]">
    <label className="block text-slate-300">确认本季作物<select aria-label="简化估产作物" value={crop} onChange={(event) => setCrop(event.target.value)} className="mt-1 w-full rounded border border-white/15 bg-[#0b1d18] p-2 text-white"><option value="">请选择地块作物</option><option value="0">玉米</option><option value="3">春小麦</option><option value="4">冬小麦</option></select></label>
    <p className="leading-4 text-slate-500">后续影像、辐射和季节识别自动完成，无需填写播种/收获日期。</p>
    {error && <p role="alert" className="text-rose-200">{error}</p>}
    <button type="submit" disabled={busy || !crop} className="rounded bg-emerald-400 px-3 py-2 text-[#06261b] disabled:opacity-40">{busy ? '正在确认…' : '确认并继续估产'}</button>
  </form>
}
