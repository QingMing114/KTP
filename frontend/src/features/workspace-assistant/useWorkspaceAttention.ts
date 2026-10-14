import { useCallback, useEffect, useRef, useState } from 'react'
import type { AnalysisWorkflow } from '../../services/spatialClient'
import type { AnalysisViewRequest } from './workspacePanelTypes'

export interface AnalysisAttention {
  id: number
  tone: 'info' | 'success' | 'warning' | 'error'
  message: string
  workflowId: string | null
  active: boolean
  unread: boolean
}
export const ATTENTION_COLORS = { info: '34, 211, 238', success: '52, 211, 153', warning: '251, 191, 36', error: '251, 113, 133' }

interface AttentionInputs {
  workflow: AnalysisWorkflow | null
  viewRequest: AnalysisViewRequest | null
  restoredWorkflowId: string | null
  aoiReady: boolean
  selectedImage: string
  draftSignature: string
  candidateSignature: string
  imageryIsSearching: boolean
  isLaunching: boolean
  analysisError: string
}

function workflowCue(workflow: AnalysisWorkflow): Pick<AnalysisAttention, 'tone' | 'message' | 'workflowId'> {
  const base = { workflowId: workflow.workflow_id }
  if (workflow.status === 'completed') return { ...base, tone: 'success', message: '任务已完成，结果在这里' }
  if (workflow.status === 'failed') return { ...base, tone: 'error', message: '任务执行失败，请查看原因' }
  if (workflow.status === 'cancelled') return { ...base, tone: 'warning', message: '任务已取消，可查看任务记录' }
  if (workflow.status === 'blocked') {
    if (workflow.steps.some((step) => step.status === 'blocked' && step.result.reason_code === 'professional_confirmation_required')) return { ...base, tone: 'warning', message: '参数已推荐，请在助手中编辑确认后继续' }
    const crop = workflow.steps.some((step) => step.status === 'blocked' && step.result.reason_code === 'crop_confirmation_required')
    const season = workflow.steps.some((step) => step.status === 'blocked' && step.result.reason_code === 'season_in_progress')
    return { ...base, tone: 'warning', message: crop ? '需要确认作物，请在这里继续' : season ? '尚未观测到季末，请查看估产说明' : '任务暂未就绪，请查看所需输入或说明' }
  }
  return { ...base, tone: 'info', message: '任务已提交，执行进度在这里' }
}

/** Meaningful changes get one finite cue; ordinary polling and percentages stay quiet. */
export function useWorkspaceAttention(inputs: AttentionInputs) {
  const { workflow, viewRequest, restoredWorkflowId, aoiReady, selectedImage, draftSignature, candidateSignature, imageryIsSearching, isLaunching, analysisError } = inputs
  const fingerprint = workflow ? JSON.stringify([workflow.workflow_id, workflow.status,
    ['blocked', 'failed'].includes(workflow.status) ? workflow.steps.filter((step) => ['blocked', 'failed'].includes(step.status)).map((step) => [step.step_id, step.result.reason_code ?? '', step.result.input_assessment ?? null]) : []]) : ''
  const previous = useRef({ fingerprint, workflowId: workflow?.workflow_id ?? null, requestId: viewRequest?.requestId, aoiReady, selectedImage, draftSignature, candidateSignature, imageryIsSearching, isLaunching, analysisError })
  const [attention, setAttention] = useState<AnalysisAttention | null>(null)
  const sequence = useRef(0)
  const notify = useCallback((cue: Pick<AnalysisAttention, 'tone' | 'message' | 'workflowId'>) => {
    sequence.current += 1
    setAttention({ ...cue, id: sequence.current, active: true, unread: true })
  }, [])
  useEffect(() => {
    const prior = previous.current
    previous.current = { fingerprint, workflowId: workflow?.workflow_id ?? null, requestId: viewRequest?.requestId, aoiReady, selectedImage, draftSignature, candidateSignature, imageryIsSearching, isLaunching, analysisError }
    if (viewRequest && viewRequest.requestId !== prior.requestId) {
      const urgent = workflow && viewRequest.workflowId === workflow.workflow_id && ['blocked', 'failed'].includes(workflow.status) ? workflowCue(workflow).tone : 'info'
      notify({ workflowId: viewRequest.workflowId, tone: urgent, message: viewRequest.workflowId ? '已定位任务，进度与结果在这里' : '分析配置在这里' })
      return
    }
    if (workflow && fingerprint !== prior.fingerprint) {
      if (workflow.workflow_id === restoredWorkflowId && workflow.workflow_id !== prior.workflowId) return
      notify(workflowCue(workflow))
      return
    }
    if (!workflow && prior.workflowId) setAttention(null)
    if (analysisError && analysisError !== prior.analysisError) {
      notify({ workflowId: workflow?.workflow_id ?? null, tone: 'error', message: '分析遇到问题，请查看提示或恢复入口' })
      return
    }
    if (isLaunching && !prior.isLaunching) {
      notify({ workflowId: null, tone: 'info', message: '任务正在提交，请查看当前状态' })
      return
    }
    if (isLaunching) return
    // A user already operating these controls does not need a configuration cue.
    if (document.getElementById('workspace-analysis-panel')?.contains(document.activeElement)) return
    if (!workflow && aoiReady) {
      const cue = !prior.aoiReady ? '选区已同步，请在这里选择影像'
        : candidateSignature && !imageryIsSearching && (prior.imageryIsSearching || candidateSignature !== prior.candidateSignature) ? '影像已就绪，请在这里选择影像'
        : selectedImage && selectedImage !== prior.selectedImage ? '影像已选定，请在这里配置任务'
        : selectedImage && draftSignature && draftSignature !== prior.draftSignature ? '任务配置已更新，可以开始执行' : null
      if (cue) notify({ workflowId: null, tone: 'info', message: cue })
    }
  }, [workflow, fingerprint, viewRequest, restoredWorkflowId, aoiReady, selectedImage, draftSignature, candidateSignature, imageryIsSearching, isLaunching, analysisError, notify])
  const attentionId = attention?.id
  useEffect(() => {
    if (attentionId == null) return
    const timer = window.setTimeout(() => setAttention((current) => current?.id === attentionId ? { ...current, active: false } : current), 6000)
    return () => window.clearTimeout(timer)
  }, [attentionId])
  const acknowledge = useCallback(() => setAttention((current) => current?.unread || current?.active ? { ...current, unread: false, active: false } : current), [])
  return { attention, acknowledge }
}
