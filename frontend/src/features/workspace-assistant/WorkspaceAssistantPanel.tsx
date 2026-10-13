import { useEffect, useLayoutEffect, useRef, type CSSProperties } from 'react'
import { Bot, ChevronRight, Layers, MapPinned, WandSparkles } from 'lucide-react'
import type { AnalysisWorkflow, WorkflowTaskId } from '../../services/spatialClient'
import { latestWorkspaceTimelineItem } from './workspaceTimeline'
import WorkspaceComposer from './WorkspaceComposer'
import AnalysisDetails from './AnalysisDetails'
import { AgentMessage } from './WorkspaceAnalysisCards'
import type { WorkspacePanelProps } from './workspacePanelTypes'
import { conversationWorkflowLinks, workflowStatusLabel, workflowTitle, workspacePhase } from './workspaceFlow'
import { ATTENTION_COLORS, type AnalysisAttention } from './useWorkspaceAttention'

function scrollConversationToLatest(node: HTMLDivElement) {
  const latest = node.querySelector<HTMLElement>('[data-latest-message="true"]')
  if (latest?.querySelector('[data-workflow-id]') && latest.offsetHeight > node.clientHeight) {
    // Keep the launch reply visible when its compact receipt exceeds a small viewport.
    node.scrollTop += latest.getBoundingClientRect().top - node.getBoundingClientRect().top - 8
  } else {
    node.scrollTop = node.scrollHeight
  }
}

export default function WorkspaceAssistantPanel({ farm, timeline, workflow, stage, workspaceContext, assistantIsSending, assistantIsLaunching, imageryIsSearching, assistantError, onSendAssistantMessage, onCancelAssistantMessage, onRecoverTask, onOpenAnalysis = () => {}, attention }: WorkspacePanelProps & { onOpenAnalysis?: (workflowId: string | null) => void; attention?: AnalysisAttention | null }) {
  const phase = workspacePhase(workspaceContext, latestWorkspaceTimelineItem(timeline, 'imagery_candidates')?.candidates.length ?? 0, workflow, stage, assistantIsLaunching)
  const taskLinks = conversationWorkflowLinks(timeline, workflow)
  const conversationItems = timeline.filter((item) => item.kind === 'agent_user_message' || item.kind === 'agent_message')
  const latestMessage = conversationItems.at(-1)
  const latestMessageId = latestMessage?.eventId
  const latestMessageText = latestMessage && (latestMessage.kind === 'agent_user_message' || latestMessage.kind === 'agent_message') ? latestMessage.message : ''
  const latestMessageStatus = latestMessage?.kind === 'agent_message' ? latestMessage.status : 'user'
  const scrollContainer = useRef<HTMLDivElement>(null)
  const conversationContent = useRef<HTMLDivElement>(null)
  const scrollViewport = useRef({ width: 0, height: 0 })
  const followLatest = useRef(true)
  const touchStartY = useRef(0)
  const previousUserCount = useRef(0)
  const userCount = conversationItems.filter((item) => item.kind === 'agent_user_message').length
  useLayoutEffect(() => {
    const node = scrollContainer.current
    if (node && (followLatest.current || userCount > previousUserCount.current)) {
      scrollConversationToLatest(node)
      followLatest.current = true
    }
    previousUserCount.current = userCount
  }, [latestMessageId, latestMessageText, latestMessageStatus, userCount])
  useEffect(() => {
    const node = scrollContainer.current
    if (!node) return
    const resize = () => {
      if (followLatest.current) scrollConversationToLatest(node)
      scrollViewport.current = { width: node.clientWidth, height: node.clientHeight }
    }
    resize()
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(resize)
    observer?.observe(node)
    if (conversationContent.current) observer?.observe(conversationContent.current)
    window.addEventListener('resize', resize)
    return () => { observer?.disconnect(); window.removeEventListener('resize', resize) }
  }, [])
  const renderTask = (id: string, requested: WorkflowTaskId[] = [], syncFailed = false) => <TaskReceipt key={id} workflowId={id} workflow={taskLinks.workflows.get(id)} taskIds={requested} historical={taskLinks.workflows.has(id) && id !== workflow?.workflow_id} onOpen={() => onOpenAnalysis(id)} onRecover={onRecoverTask} syncFailed={!taskLinks.workflows.has(id) && syncFailed} />
  const hasPendingReceipt = latestMessage?.kind === 'agent_message' && latestMessage.runId && taskLinks.byRun.get(latestMessage.runId)?.some((id) => !taskLinks.workflows.has(id))
  const hints = { draw: '在地图框选区域，或告诉助手想做什么', search: '到左侧分析面板搜索并选择影像', choose: '到左侧分析面板选择影像', configure: '可在左侧选择任务，也可以直接告诉助手', ready: '配置已就绪，可以开始执行', launching: '正在提交任务，请稍候', running: '任务正在后台执行，可继续询问进度', result: '查看结果，或发起下一次分析' }
  return <aside aria-label="遥感分析助手" className="z-20 flex min-h-0 min-w-0 flex-col border-l border-white/10 bg-[#0b1d18]/95 backdrop-blur-xl max-[680px]:h-[calc(60dvh-4rem)] max-[680px]:border-l-0 max-[680px]:border-t">
    <div className="shrink-0 border-b border-white/10 px-4 py-3"><div className="flex items-center gap-2"><span className="grid h-7 w-7 place-items-center rounded-lg bg-emerald-400/15 text-emerald-200"><Bot size={16} /></span><div className="min-w-0 flex-1"><h1 className="text-sm font-semibold text-white">遥感分析助手</h1><p className="truncate text-[10px] text-emerald-200/65">{farm.name} · {farm.locationLabel}</p></div>
      {attention?.unread && <button key={attention.id} type="button" aria-label="查看分析提醒" title={attention.message} aria-controls="workspace-analysis-panel" onClick={() => onOpenAnalysis(attention.workflowId)} style={{ '--analysis-attention-color': ATTENTION_COLORS[attention.tone], color: `rgb(${ATTENTION_COLORS[attention.tone]})` } as CSSProperties} className={`grid h-7 w-7 shrink-0 place-items-center rounded-lg border border-current/30 ${attention.active ? 'workspace-attention-entry' : ''}`}><WandSparkles size={14} /></button>}
      <button type="button" aria-controls="workspace-analysis-panel" onClick={() => onOpenAnalysis(null)} className="flex shrink-0 items-center gap-1 rounded-lg border border-emerald-300/20 px-2 py-1.5 text-[10px] text-emerald-100"><WandSparkles size={12} />配置分析</button></div></div>
    {phase === 'launching' && assistantError && !hasPendingReceipt && <button type="button" onClick={() => void onRecoverTask()} className="shrink-0 border-b border-amber-300/15 bg-amber-300/5 px-4 py-2 text-left text-[10px] text-amber-200">恢复任务状态</button>}
        <div role="log" aria-label="助手对话" tabIndex={0} ref={scrollContainer}
      onWheel={(event) => { if (event.deltaY < 0) followLatest.current = false }}
      onTouchStart={(event) => { touchStartY.current = event.touches[0]?.clientY ?? 0 }}
      onTouchMove={(event) => { if ((event.touches[0]?.clientY ?? 0) > touchStartY.current) followLatest.current = false }}
      onPointerDown={(event) => { if (event.target === event.currentTarget && event.clientX > event.currentTarget.getBoundingClientRect().right - 20) followLatest.current = false }}
      onKeyDown={(event) => { if (['Home', 'PageUp', 'ArrowUp'].includes(event.key)) followLatest.current = false }}
      style={{ overflowAnchor: 'none' }} onScroll={() => { const node = scrollContainer.current; if (node && node.clientWidth === scrollViewport.current.width && node.clientHeight === scrollViewport.current.height && node.scrollHeight - node.scrollTop - node.clientHeight < 80) followLatest.current = true }} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
      <div ref={conversationContent} className="space-y-3">
      {taskLinks.unattached.map((flow) => <div key={flow.workflow_id}>{renderTask(flow.workflow_id)}</div>)}
      {!conversationItems.length && !taskLinks.unattached.length && <p className="px-1 text-[11px] leading-5 text-slate-400">先在地图框选区域。左侧分析面板用于配置和查看结果，也可以直接告诉我需要执行的任务。</p>}
      {conversationItems.map((item) => {
        if (item.kind === 'agent_user_message') return <AgentMessage key={item.eventId} icon={<MapPinned size={14} />} tone="cyan" title="你" time="">{item.message}</AgentMessage>
        if (item.kind !== 'agent_message') return null
        const parts = timeline.filter((entry) => entry.kind === 'agent_part' && !!item.runId && entry.runId === item.runId).flatMap((entry) => entry.kind === 'agent_part' && ['analysis_plan', 'parameter_set'].includes(entry.part.type) ? [entry.part] : [])
        const linkedIds = item.runId ? taskLinks.byRun.get(item.runId) ?? [] : []
        const requested = parts.find((part) => part.type === 'analysis_plan')?.data?.requested_task_ids ?? []
        const message = linkedIds.length ? item.message.replace('当前分析卡片将持续显示进度和结果。', '左侧分析面板可查看进度和结果。').replace('下方任务卡片可查看进度和结果。', '左侧分析面板可查看进度和结果。') : item.message
        return <div key={item.eventId} data-assistant-run={item.runId} data-latest-message={item.eventId === latestMessageId}><AgentMessage icon={<Bot size={14} />} tone={item.status === 'failed' ? 'rose' : 'emerald'} title="遥感分析助手" time={item.status === 'streaming' ? '处理中' : item.status === 'failed' ? '未完成' : ''}><p>{message}</p>{linkedIds.map((id) => renderTask(id, requested, item.eventId === latestMessageId && assistantIsLaunching && !!assistantError))}</AgentMessage>{!linkedIds.length && item.status === 'completed' && !!parts.length && <details className="mt-1 px-2 text-[10px] text-slate-500"><summary className="cursor-pointer">查看本轮分析说明</summary><div className="mt-2"><AnalysisDetails parts={parts} demo={parts[0]?.data?.execution_mode === 'demo'} expanded={false} /></div></details>}</div>
      })}


    </div>
    </div>

    <WorkspaceComposer isSending={assistantIsSending} blocked={imageryIsSearching} isLaunching={assistantIsLaunching} hint={imageryIsSearching ? '搜索完成后可继续对话' : hints[phase]} error={assistantError} onSend={onSendAssistantMessage} onCancel={onCancelAssistantMessage} />
  </aside>
}

function TaskReceipt({ workflowId, workflow, taskIds, historical, onOpen, onRecover, syncFailed }: { workflowId: string; workflow?: AnalysisWorkflow; taskIds: WorkflowTaskId[]; historical: boolean; onOpen: () => void; onRecover: () => Promise<void>; syncFailed: boolean }) {
  const title = workflowTitle(workflow?.requested_task_ids ?? taskIds)
  const status = workflow ? workflowStatusLabel(workflow) : syncFailed ? '状态同步中断' : '正在同步状态'
  const active = workflow?.steps.find((step) => step.status === 'running')
  const tone = workflow?.status === 'failed' ? 'text-rose-200' : workflow?.status === 'blocked' || syncFailed ? 'text-amber-200' : 'text-emerald-200'
  return <section id={`workspace-task-${workflowId}`} aria-label={`任务卡片：${title}`} data-workflow-id={workflowId} className="mt-3 border-t border-emerald-300/15 pt-3">
    <div className="flex items-start justify-between gap-3"><p className="flex min-w-0 items-start gap-1.5 font-medium text-emerald-100"><Layers size={13} className="mt-1 shrink-0" /><span>{title}</span></p><span role="status" className={`shrink-0 rounded bg-white/5 px-1.5 text-[10px] ${tone}`}>{status}</span></div>
    {workflow && <p className="mt-1 text-[9px] leading-4 text-slate-500">{historical && '历史任务 · '}{workflow.aoi.area_hectares.toFixed(2)} ha · 影像 {workflow.imagery_snapshot.acquired_at.slice(0, 10)}</p>}
    {workflow?.data_mode === 'demo' && <p className="mt-1 text-[10px] text-amber-200">模拟数据 · {workflow.demo_crop === 'maize' ? '玉米' : '小麦'}演示 · 非实际产量</p>}
    {active && <p className="mt-1 text-[10px] leading-4 text-slate-400">{active.detail} · {active.progress_percent}%</p>}
    {workflow?.status === 'blocked' && <p className="mt-1 line-clamp-2 text-[10px] leading-4 text-amber-200/80">{workflow.detail}</p>}
    {workflow ? <button type="button" aria-controls="workspace-analysis-panel" aria-label={`查看${title}的进度与结果`} onClick={onOpen} className="mt-2 flex w-full items-center justify-between rounded-md bg-emerald-400/10 px-2.5 py-2 text-[10px] font-medium text-emerald-100 hover:bg-emerald-400/20">{workflow.steps.some((step) => step.result.reason_code === 'crop_confirmation_required' && step.status === 'blocked') ? '确认作物并继续估产' : '查看进度与结果'}<ChevronRight size={12} /></button> : syncFailed ? <button type="button" onClick={() => void onRecover()} className="mt-2 text-[10px] text-amber-200">恢复任务状态</button> : <p className="mt-1 text-[10px] text-slate-500">任务已提交，正在获取执行状态…</p>}
  </section>
}
