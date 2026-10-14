import { useEffect, useLayoutEffect, useRef, type CSSProperties } from 'react'
import { Bot, ChevronRight, History, Layers, ListX, MapPinned, WandSparkles } from 'lucide-react'
import type { AnalysisWorkflow, WorkflowTaskId } from '../../services/spatialClient'
import { latestWorkspaceTimelineItem } from './workspaceTimeline'
import WorkspaceComposer from './WorkspaceComposer'
import ProfessionalReviewList from './ProfessionalReviewList'
import WorkspaceRunRecord from './WorkspaceRunRecord'
import { AgentMessage } from './WorkspaceAnalysisCards'
import type { WorkspacePanelProps } from './workspacePanelTypes'
import { conversationWorkflowLinks, workflowStatusLabel, workflowTitle, workspacePhase } from './workspaceFlow'
import { ATTENTION_COLORS, type AnalysisAttention } from './useWorkspaceAttention'
import { useWorkspaceHistoryVisibility } from './useWorkspaceHistoryVisibility'

function scrollConversationToLatest(node: HTMLDivElement) {
  const latest = node.querySelector<HTMLElement>('[data-latest-message="true"]')
  const record = latest?.querySelector<HTMLElement>('[data-run-record-expanded="true"]')
  if (record && !latest?.querySelector('[data-active-review="true"]')) {
    node.scrollTop += record.getBoundingClientRect().top - node.getBoundingClientRect().top - 8
  } else if (!latest?.querySelector('[data-active-review="true"]') && latest?.querySelector('[data-workflow-id]') && latest.offsetHeight > node.clientHeight) {
    // Keep the launch reply visible when its compact receipt exceeds a small viewport.
    node.scrollTop += latest.getBoundingClientRect().top - node.getBoundingClientRect().top - 8
  } else {
    node.scrollTop = node.scrollHeight
  }
}

export default function WorkspaceAssistantPanel({ farm, timeline, workflow, stage, workspaceContext, assistantIsSending, assistantIsLaunching, imageryIsSearching, assistantError, onSendAssistantMessage, onCancelAssistantMessage, onRecoverTask, onAutoExecute, onProfessionalMode, professionalReviews = [], professionalReviewBusy = false, onProfessionalDecision, onOpenAnalysis = () => {}, attention }: WorkspacePanelProps & { onOpenAnalysis?: (workflowId: string | null) => void; attention?: AnalysisAttention | null }) {
  const phase = workspacePhase(workspaceContext, latestWorkspaceTimelineItem(timeline, 'imagery_candidates')?.candidates.length ?? 0, workflow, stage, assistantIsLaunching)
  const taskLinks = conversationWorkflowLinks(timeline, workflow)
  const automaticIds = new Set(timeline.flatMap((item) => item.kind === 'agent_part' && item.part.type === 'workflow_reference' && item.part.data?.auto_execute && item.part.data.workflow_id ? [item.part.data.workflow_id] : []))
  const history = useWorkspaceHistoryVisibility(timeline, workspaceContext, professionalReviews, taskLinks.workflows, taskLinks.unattached)
  const conversationItems = history.messages.filter((item) => !history.isHiddenMessage(item))
  const visibleUnattached = taskLinks.unattached.filter((flow) => !history.isHiddenWorkflow(flow))
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
  const renderTask = (id: string, requested: WorkflowTaskId[] = [], syncFailed = false) => <div key={id}><TaskReceipt workflowId={id} workflow={taskLinks.workflows.get(id)} taskIds={requested} historical={taskLinks.workflows.has(id) && id !== workflow?.workflow_id} onOpen={() => onOpenAnalysis(id)} onRecover={onRecoverTask} syncFailed={!taskLinks.workflows.has(id) && syncFailed} />{automaticIds.has(id) && <AutomaticOutcome workflow={taskLinks.workflows.get(id)} onOpen={() => onOpenAnalysis(id)} />}</div>
  const hasPendingReceipt = latestMessage?.kind === 'agent_message' && latestMessage.runId && taskLinks.byRun.get(latestMessage.runId)?.some((id) => !taskLinks.workflows.has(id))
  const hints = { draw: '在地图框选区域，或告诉助手想做什么', search: '到左侧分析面板搜索并选择影像', choose: '到左侧分析面板选择影像', configure: '可在左侧选择任务，也可以直接告诉助手', ready: '配置已就绪，可以开始执行', launching: '正在提交任务，请稍候', running: '任务正在后台执行，可继续询问进度', result: '查看结果，或发起下一次分析' }
  return <aside aria-label="遥感分析助手" className="z-20 flex min-h-0 min-w-0 flex-col border-l border-white/10 bg-[#0b1d18]/95 backdrop-blur-xl max-[680px]:h-[calc(60dvh-4rem)] max-[680px]:border-l-0 max-[680px]:border-t">
    <div className="shrink-0 border-b border-white/10 px-4 py-3"><div className="flex items-center gap-2"><span className="grid h-7 w-7 place-items-center rounded-lg bg-emerald-400/15 text-emerald-200"><Bot size={16} /></span><div className="min-w-0 flex-1"><h1 className="text-sm font-semibold text-white">遥感分析助手</h1><p className="truncate text-[10px] text-emerald-200/65">{farm.name} · {farm.locationLabel}</p></div>
      {attention?.unread && <button key={attention.id} type="button" aria-label="查看分析提醒" title={attention.message} aria-controls="workspace-analysis-panel" onClick={() => onOpenAnalysis(attention.workflowId)} style={{ '--analysis-attention-color': ATTENTION_COLORS[attention.tone], color: `rgb(${ATTENTION_COLORS[attention.tone]})` } as CSSProperties} className={`grid h-7 w-7 shrink-0 place-items-center rounded-lg border border-current/30 ${attention.active ? 'workspace-attention-entry' : ''}`}><WandSparkles size={14} /></button>}
      <button type="button" aria-controls="workspace-analysis-panel" onClick={() => onOpenAnalysis(null)} className="flex shrink-0 items-center gap-1 rounded-lg border border-emerald-300/20 px-2 py-1.5 text-[10px] text-emerald-100"><WandSparkles size={12} />配置分析</button></div><div className="mt-2 flex items-center justify-end gap-3 text-[10px] text-slate-400">{history.hasHidden && <button type="button" onClick={history.restore} title="恢复此浏览器隐藏的历史消息" className="flex items-center gap-1 hover:text-emerald-100"><History size={12} />恢复历史</button>}<button type="button" onClick={history.clear} disabled={!history.canClear || assistantIsSending || assistantIsLaunching || professionalReviewBusy} title="只隐藏已结束的历史消息，保留聊天记录和任务结果；运行中和待确认的轮次保留" className="flex items-center gap-1 hover:text-emerald-100 disabled:opacity-35"><ListX size={12} />清空列表</button></div>{history.error && <p role="alert" className="mt-2 text-[10px] text-rose-300">{history.error}</p>}</div>
    {phase === 'launching' && assistantError && !hasPendingReceipt && <button type="button" onClick={() => void onRecoverTask()} className="shrink-0 border-b border-amber-300/15 bg-amber-300/5 px-4 py-2 text-left text-[10px] text-amber-200">恢复任务状态</button>}
        <div role="log" aria-label="助手对话" tabIndex={0} ref={scrollContainer}
      onClickCapture={(event) => { const target = event.target as HTMLElement; if (target.closest('[data-run-record]') && target.closest('summary, button[aria-expanded]')) followLatest.current = false }}
      onWheel={(event) => { if (event.deltaY < 0) followLatest.current = false }}
      onTouchStart={(event) => { touchStartY.current = event.touches[0]?.clientY ?? 0 }}
      onTouchMove={(event) => { if ((event.touches[0]?.clientY ?? 0) > touchStartY.current) followLatest.current = false }}
      onPointerDown={(event) => { if (event.target === event.currentTarget && event.clientX > event.currentTarget.getBoundingClientRect().right - 20) followLatest.current = false }}
      onKeyDown={(event) => { if (['Home', 'PageUp', 'ArrowUp'].includes(event.key)) followLatest.current = false }}
      style={{ overflowAnchor: 'none' }} onScroll={() => { const node = scrollContainer.current; if (node && node.clientWidth === scrollViewport.current.width && node.clientHeight === scrollViewport.current.height && node.scrollHeight - node.scrollTop - node.clientHeight < 80) followLatest.current = true }} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
      <div ref={conversationContent} className="space-y-3">
      {taskLinks.unattached.map((flow) => <div key={flow.workflow_id} hidden={history.isHiddenWorkflow(flow)}>{renderTask(flow.workflow_id)}</div>)}
      {!conversationItems.length && !visibleUnattached.length && <p className="px-1 text-[11px] leading-5 text-slate-400">{history.hasHidden ? '列表已清空，聊天记录和任务结果仍保留。' : '先在地图框选区域。左侧分析面板用于配置和查看结果，也可以直接告诉我需要执行的任务。'}</p>}
      {history.messages.map((item) => {
        if (item.kind === 'agent_user_message') return <div key={item.eventId} hidden={history.isHiddenMessage(item)}><AgentMessage icon={<MapPinned size={14} />} tone="cyan" title="你" time="">{item.message}</AgentMessage></div>
        if (item.kind !== 'agent_message') return null
        const parts = timeline.filter((entry) => entry.kind === 'agent_part' && !!item.runId && entry.runId === item.runId).flatMap((entry) => entry.kind === 'agent_part' && ['analysis_plan', 'parameter_set'].includes(entry.part.type) ? [entry.part] : [])
        const linkedIds = item.runId ? taskLinks.byRun.get(item.runId) ?? [] : []
        const recordWorkflows = linkedIds.flatMap((id) => taskLinks.workflows.has(id) ? [taskLinks.workflows.get(id)!] : [])
        const hasProfessionalReviews = professionalReviews.some((review) => review.source_run_id === item.runId && review.workspace_id === workspaceContext.workspace_id)
        const finished = !!recordWorkflows.length && recordWorkflows.length === linkedIds.length && recordWorkflows.every((flow) => (hasProfessionalReviews ? ["completed", "failed", "cancelled"] : ["completed", "failed", "cancelled", "blocked"]).includes(flow.status))
        const expandRecord = item.eventId === latestMessageId && item.status !== "streaming" && finished
        const recordRound = history.messages.filter((entry) => entry.kind === "agent_user_message").at(-1)?.eventId ?? latestMessageId ?? "restored"
        const requested = parts.find((part) => part.type === 'analysis_plan')?.data?.requested_task_ids ?? []
        const message = linkedIds.length ? item.message.replace('当前分析卡片将持续显示进度和结果。', '左侧分析面板可查看进度和结果。').replace('下方任务卡片可查看进度和结果。', '左侧分析面板可查看进度和结果。') : item.message
        return <div key={item.eventId} hidden={history.isHiddenMessage(item)} data-assistant-run={item.runId} data-latest-message={item.eventId === latestMessageId}><AgentMessage icon={<Bot size={14} />} tone={item.status === 'failed' ? 'rose' : 'emerald'} title="遥感分析助手" time={item.status === 'streaming' ? '处理中' : item.status === 'failed' ? '未完成' : ''}><p>{message}</p>{linkedIds.map((id) => renderTask(id, requested, item.eventId === latestMessageId && assistantIsLaunching && !!assistantError))}</AgentMessage>{hasProfessionalReviews && onProfessionalDecision && item.runId ? <ProfessionalReviewList runId={item.runId} reviews={professionalReviews} context={workspaceContext} timeline={timeline} busy={professionalReviewBusy || assistantIsSending} onDecision={onProfessionalDecision} workflows={taskLinks.workflows} onOpenWorkflow={onOpenAnalysis} automaticallyExpanded={expandRecord} /> : <WorkspaceRunRecord runId={item.runId ?? item.eventId} round={recordRound} automaticallyExpanded={expandRecord} parts={parts} workflows={recordWorkflows} assistantSummary={item.message} automatic={linkedIds.some((id) => automaticIds.has(id))} />}</div>
      })}



    </div>
    </div>

    <WorkspaceComposer isSending={assistantIsSending} blocked={imageryIsSearching || professionalReviewBusy} isLaunching={assistantIsLaunching} autoExecute={workspaceContext.auto_execute} professionalMode={workspaceContext.professional_mode} onProfessionalMode={onProfessionalMode} onAutoExecute={onAutoExecute} hint={imageryIsSearching ? '搜索完成后可继续对话' : workspaceContext.professional_mode ? '推荐配置将显示为可编辑确认卡片' : workspaceContext.auto_execute && !['running', 'launching', 'result'].includes(phase) ? '告诉我分析需求，我会自动选片并执行' : hints[phase]} error={assistantError} onSend={onSendAssistantMessage} onCancel={onCancelAssistantMessage} />
  </aside>
}

function AutomaticOutcome({ workflow, onOpen }: { workflow?: AnalysisWorkflow; onOpen: () => void }) {
  if (!workflow || !['completed', 'failed', 'blocked', 'cancelled'].includes(workflow.status)) return null
  const success = workflow.status === 'completed'
  const label = success ? '自动执行已完成' : workflow.status === 'blocked' ? '自动执行需要补充信息' : workflow.status === 'cancelled' ? '自动执行已取消' : '自动执行未完成'
  return <div role="status" aria-label="自动执行结果" className={`mt-2 rounded-lg border p-2 text-[11px] leading-5 ${success ? 'border-emerald-300/25 bg-emerald-400/10 text-emerald-100' : 'border-amber-300/25 bg-amber-400/10 text-amber-100'}`}>
    <p>{label}：{workflowTitle(workflow.requested_task_ids)}。</p>
    {!success && <p>{workflow.detail}</p>}
    <button type="button" onClick={onOpen} className="mt-1 underline underline-offset-2">{success ? '查看分析结果与报告' : '查看任务详情'}</button>
  </div>
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
