import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from 'react'
import { Check, ChevronRight, RotateCcw, Search, WandSparkles } from 'lucide-react'
import type { WorkspacePanelProps, AnalysisViewRequest } from './workspacePanelTypes'
import { latestWorkspaceTimelineItem } from './workspaceTimeline'
import { conversationWorkflowLinks, currentAnalysisDetails, workspacePhase, workflowStatusLabel, workflowTitle } from './workspaceFlow'
import { CandidateList, ProfessionalTaskCard, ActionCard, ProgressCard, ResultCard, CropAnalysisCard, WorkflowCard } from './WorkspaceAnalysisCards'
import AnalysisDetails from './AnalysisDetails'
import { WORKSPACE_TASKS } from './workspaceTasks'
import type { WorkflowTaskId } from '../../services/spatialClient'
import { ATTENTION_COLORS, type AnalysisAttention } from './useWorkspaceAttention'

const hints = { draw: '下一步：在地图框选分析区域', search: '下一步：搜索并选择一景影像', choose: '下一步：选择一景影像', configure: '下一步：选择任务，也可以直接告诉助手', ready: '配置已就绪，可以开始执行', launching: '正在核验配置并建立任务…', running: '任务正在后台执行', result: '查看结果，或发起下一次分析' }

export default function WorkspaceAnalysisPanel(props: WorkspacePanelProps & { viewRequest?: AnalysisViewRequest | null; onViewChange?: (workflowId: string | null) => void; attention?: AnalysisAttention | null; onAttentionRead?: () => void }) {
  const { aoiReady, aoiAreaLabel, imagerySearchEndDate, stage, timeline, selectedImage, selectedCandidate, workflow,
    analysisError, progress, detail, elapsedSeconds, lastUpdateSeconds, delayed, connectionIssue, pixelProgress,
    reportUrl, rasterUrl, cropAnalysis, executionMode, workspaceContext, draftTaskIds, assistantIsSending,
    assistantIsLaunching, imageryIsSearching, assistantError, onFindImagery, onSelectCandidate, onStartAnalysis,
    onDraftTaskIds, onRetryWorkflowStep, onUpdateYieldInputs, onReset, onRecoverTask, viewRequest, onViewChange, attention, onAttentionRead } = props
  const [tab, setTab] = useState<'configure' | 'task'>(workflow ? 'task' : 'configure')
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const content = useRef<HTMLDivElement>(null)
  const panel = useRef<HTMLElement>(null)
  const taskLinks = conversationWorkflowLinks(timeline, workflow)
  const tasks = taskLinks.workflows
  const latestReply = [...timeline].reverse().find((item) => item.kind === 'agent_message')
  const hasPendingReceipt = latestReply?.kind === 'agent_message' && latestReply.runId && taskLinks.byRun.get(latestReply.runId)?.some((id) => !tasks.has(id))
  const selectedTask = selectedTaskId ? tasks.get(selectedTaskId) : workflow
  const workflowId = workflow?.workflow_id
  const phase = workspacePhase(workspaceContext, latestWorkspaceTimelineItem(timeline, 'imagery_candidates')?.candidates.length ?? 0, workflow, stage, assistantIsLaunching)
  const candidates = latestWorkspaceTimelineItem(timeline, 'imagery_candidates')?.candidates ?? []
  const currentDetails = currentAnalysisDetails(workspaceContext, timeline, aoiAreaLabel, selectedCandidate?.date ?? '')
  const currentStep = progress < 35 ? 0 : progress < 90 ? 1 : 2
  const step = phase === 'draw' ? 0 : ['search', 'choose'].includes(phase) ? 1 : ['configure', 'ready'].includes(phase) ? 2 : 3
  useEffect(() => {
    setSelectedTaskId(null)
    setTab(workflowId ? 'task' : 'configure')
  }, [workflowId])
  useEffect(() => {
    if (!viewRequest) return
    setSelectedTaskId(viewRequest.workflowId)
    setTab(viewRequest.workflowId ? 'task' : 'configure')
    panel.current?.focus({ preventScroll: true })
  }, [viewRequest])
  useLayoutEffect(() => { if (content.current) content.current.scrollTop = 0 }, [tab, selectedTaskId, workflow?.workflow_id, viewRequest?.requestId])
  useEffect(() => { onViewChange?.(tab === 'task' ? selectedTask?.workflow_id ?? null : null) }, [tab, selectedTask?.workflow_id, onViewChange])
  const historical = !!selectedTask && selectedTask.workflow_id !== workflow?.workflow_id
  const attentionColor = attention ? ATTENTION_COLORS[attention.tone] : ATTENTION_COLORS.info
  return <section ref={panel} id="workspace-analysis-panel" tabIndex={-1} aria-label="当前分析面板" data-attention-id={attention?.id} data-attention-active={attention?.active ?? false}
    onClickCapture={(event) => { if (!(event.target as HTMLElement).closest('[data-attention-action]')) onAttentionRead?.() }}
    style={{ '--analysis-attention-color': attentionColor, boxShadow: attention?.unread ? `inset 0 0 0 1px rgba(${attentionColor}, .45)` : undefined } as CSSProperties}
    className="relative isolate flex min-h-0 flex-1 flex-col outline-none">
    {attention?.active && <span key={attention.id} aria-hidden="true" data-attention-tone={attention.tone} className="workspace-attention-glow" />}
    <div className="shrink-0 border-b border-white/10 px-4 py-3">
      <h2 className="flex items-center gap-2 text-xs font-semibold text-emerald-100"><WandSparkles size={14} />当前分析<span className="ml-auto text-[9px] font-normal text-slate-400">{tab === 'task' && selectedTask ? workflowStatusLabel(selectedTask) : aoiReady ? aoiAreaLabel : '等待框选'}</span></h2>
      {attention && (attention.active || attention.unread) && <div className="mt-2 flex items-center gap-2 rounded-md border px-2 py-1.5 text-[10px]" style={{ color: `rgb(${attentionColor})`, borderColor: `rgba(${attentionColor}, .3)`, backgroundColor: `rgba(${attentionColor}, .06)` }}>
        <button type="button" data-attention-action className="flex min-w-0 flex-1 items-center gap-1 text-left leading-4" onClick={() => { setSelectedTaskId(attention.workflowId); setTab(attention.workflowId ? 'task' : 'configure'); onAttentionRead?.() }}>{attention.message}<ChevronRight size={12} className="shrink-0" /></button>
        <button type="button" data-attention-action aria-label="我已看到分析提醒" onClick={onAttentionRead} className="shrink-0 text-[9px] opacity-75 hover:opacity-100">知道了</button>
      </div>}
      <div role="tablist" aria-label="分析面板视图" className="mt-3 flex gap-1 rounded-lg bg-black/15 p-1 text-[10px]">
        <button type="button" role="tab" id="analysis-config-tab" aria-selected={tab === 'configure'} aria-controls="analysis-config-content" onClick={() => setTab('configure')} className={`flex-1 rounded-md px-2 py-1.5 ${tab === 'configure' ? 'bg-emerald-400/15 text-emerald-100' : 'text-slate-400'}`}>分析配置</button>
        <button type="button" role="tab" id="analysis-task-tab" aria-selected={tab === 'task'} aria-controls="analysis-task-content" onClick={() => setTab('task')} className={`flex-1 rounded-md px-2 py-1.5 ${tab === 'task' ? 'bg-emerald-400/15 text-emerald-100' : 'text-slate-400'}`}>任务详情</button>
      </div>
    </div>
    <div ref={content} className="min-h-0 flex-1 overflow-y-auto p-3">
      {tab === 'configure' ? <div id="analysis-config-content" role="tabpanel" aria-labelledby="analysis-config-tab">
        {workflow ? <div className="mb-3 rounded-lg border border-emerald-300/20 bg-emerald-300/5 p-3 text-[10px] leading-5 text-slate-300"><p>当前配置已提交：{workflowTitle(workflow.requested_task_ids)}</p><button type="button" onClick={() => { setSelectedTaskId(null); setTab('task') }} className="mt-1 text-emerald-200">查看当前任务<ChevronRight size={11} className="ml-1 inline" /></button>{!['running', 'planned'].includes(workflow.status) && <button type="button" onClick={onReset} className="mt-2 block text-emerald-200">开始新一轮分析</button>}</div> : <section aria-label="分析配置" className="rounded-xl border border-emerald-300/25 bg-[#102820] p-3">
        {executionMode === 'demo' && <span className="text-[9px] text-amber-200">演示模式</span>}
        <ol aria-label="分析步骤" className="my-3 flex items-center gap-1 text-[9px]">{['区域', '影像', '任务', '执行'].map((label, index) => <li key={label} className={`flex flex-1 items-center gap-1 ${index <= step ? 'text-emerald-200' : 'text-slate-500'}`}><span className={`grid h-4 w-4 place-items-center rounded-full ${index < step ? 'bg-emerald-300/20' : 'border border-current'}`}>{index < step ? <Check size={9} /> : index + 1}</span>{label}{index < 3 && <ChevronRight size={10} className="ml-auto text-slate-600" />}</li>)}</ol>
        <p role="status" className="text-[11px] leading-5 text-emerald-100">{imageryIsSearching ? '正在搜索可用影像…' : hints[phase]}</p>
        {aoiReady && <div className="mt-2 rounded-lg bg-black/15 px-3 py-2 text-[10px] text-slate-400"><p>分析区域 <span className="float-right text-slate-200">{aoiAreaLabel}</span></p>{selectedCandidate && <p className="mt-1">已选影像 <span className="float-right text-slate-200">{selectedCandidate.date} · 云量 {selectedCandidate.cloud}</span></p>}{!!draftTaskIds.length && phase !== 'running' && phase !== 'result' && <p className="mt-1 leading-4">已选任务：<span className="text-emerald-200">{WORKSPACE_TASKS.filter((task) => draftTaskIds.includes(task.id as WorkflowTaskId)).map((task) => task.title).join('、')}</span></p>}</div>}
        {phase === 'draw' && <p className="mt-3 text-[10px] leading-5 text-slate-400">使用地图左上角的矩形或多边形工具。也可以先告诉我需要执行的任务。</p>}
        {(phase === 'search' || phase === 'choose') && <div className="mt-3 space-y-3">
          {!!candidates.length && <CandidateList candidates={candidates} selectedImage={selectedImage} onSelect={onSelectCandidate} disabled={assistantIsLaunching || imageryIsSearching} />}
          <ActionCard title={candidates.length ? '重新搜索影像' : '搜索可用影像'} subtitle={`Sentinel-2 · 截止 ${imagerySearchEndDate} · 云量 ≤ 20%`} action={imageryIsSearching ? '正在搜索…' : candidates.length ? '重新搜索' : '搜索影像'} onClick={onFindImagery} disabled={imageryIsSearching || assistantIsLaunching} icon={<Search size={14} />} />
          {!!draftTaskIds.length && <p className="text-[10px] leading-4 text-slate-400">任务选择已保留，选片后确认启动即可。</p>}
        </div>}
        {(phase === 'configure' || phase === 'ready') && selectedCandidate && <div className="mt-3 space-y-3">
          <details className="text-[10px] text-slate-400"><summary className="cursor-pointer">更换影像</summary><div className="mt-2"><CandidateList candidates={candidates} selectedImage={selectedImage} onSelect={onSelectCandidate} disabled={assistantIsSending || imageryIsSearching} /></div></details>
          <ProfessionalTaskCard key={selectedCandidate.id} initialTaskIds={draftTaskIds} onDraftTasks={onDraftTaskIds} executionMode={executionMode} onStartTasks={onStartAnalysis} onStartYieldDemo={props.onStartYieldDemo} disabled={assistantIsSending || imageryIsSearching} />
          <AnalysisDetails parts={currentDetails} demo={executionMode === 'demo'} expanded={false} />
        </div>}
        {phase === 'launching' && !hasPendingReceipt && <div className="mt-3 rounded-lg border border-cyan-300/20 p-3 text-[11px] text-cyan-200">{assistantError ? <><p className="leading-5">{assistantError}</p><button type="button" onClick={() => void onRecoverTask()} className="mt-2 rounded bg-emerald-400/15 px-3 py-2 text-emerald-200">恢复任务状态</button></> : <p className="flex items-center gap-2"><RotateCcw size={14} className="animate-spin" />正在核验配置并建立任务…</p>}</div>}
        {analysisError && <p role="alert" className="mt-3 rounded-lg border border-rose-300/20 p-3 text-[10px] leading-5 text-rose-200">{analysisError}</p>}
        {assistantError && !analysisError && !assistantIsLaunching && <p role="alert" className="mt-3 rounded-lg border border-rose-300/20 p-3 text-[10px] leading-5 text-rose-200">{assistantError}</p>}
        {cropAnalysis && <div className="mt-3"><CropAnalysisCard analysis={cropAnalysis} onReset={onReset} /></div>}
      </section>}
      </div> : <div id="analysis-task-content" role="tabpanel" aria-labelledby="analysis-task-tab">
        {selectedTask ? <>
          <div className="mb-3 text-[10px] leading-5 text-slate-400"><p className="font-medium text-emerald-100">{workflowTitle(selectedTask.requested_task_ids)}</p><p>{historical ? '历史任务 · ' : ''}{selectedTask.aoi.area_hectares.toFixed(2)} ha · 影像 {selectedTask.imagery_snapshot.acquired_at.slice(0, 10)}</p>{historical && <><p className="text-amber-200/75">仅查看记录，当前选区和任务配置保持不变。</p>{workflow && <button type="button" onClick={() => setSelectedTaskId(null)} className="mt-1 text-emerald-200">返回当前任务</button>}</>}</div>
          <WorkflowCard key={selectedTask.workflow_id} workflow={selectedTask} readOnly={historical} onRetry={onRetryWorkflowStep} onUpdateYieldInputs={onUpdateYieldInputs} onReset={onReset} />
        </> : selectedTaskId ? <p className="text-[11px] text-slate-400">任务详情暂未加载，请稍后重试。</p> : stage === 'running' ? <ProgressCard progress={progress} currentStep={currentStep} detail={detail} elapsedSeconds={elapsedSeconds} lastUpdateSeconds={lastUpdateSeconds} delayed={delayed} connectionIssue={connectionIssue} pixelProgress={pixelProgress} executionMode={executionMode} /> : stage === 'done' ? <ResultCard reportUrl={reportUrl} rasterUrl={rasterUrl} onReset={onReset} /> : <p className="text-[11px] leading-6 text-slate-400">任务启动后，执行步骤、实际参数和结果会显示在这里。</p>}
      </div>}
    </div>
  </section>
}
