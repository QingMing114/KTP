import type { AnalysisWorkflow, CropAnalysis, LaiPixelProgress, WorkflowTaskId, YieldAgronomicInputs } from '../../services/spatialClient'
import type { WorkspaceCandidateCardItem, WorkspaceTimelineItem } from './workspaceTimeline'
import type { WorkspaceContext } from '../../services/canonical/workspaceClient'

export type AnalysisStage = 'idle' | 'candidates' | 'ready' | 'running' | 'done'

export interface WorkspacePanelProps {
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
  cropAnalysis: CropAnalysis | null
  workflow: AnalysisWorkflow | null
  onFindImagery: () => void
  onSelectCandidate: (candidateId: string) => void
  onStartAnalysis: (taskIds: (WorkflowTaskId | 'forecast')[]) => void
  onStartYieldDemo?: (crop: 'wheat' | 'maize') => void
  onRetryWorkflowStep: (stepId: 'imagery' | 'crop' | 'lai' | 'potential' | 'yield_simple' | 'yield') => void
  onUpdateYieldInputs: (inputs: YieldAgronomicInputs) => Promise<void>
  onReset: () => void
  assistantIsSending: boolean
  assistantIsLaunching: boolean
  imageryIsSearching: boolean
  assistantError: string
  onSendAssistantMessage: (message: string) => Promise<void>
  onCancelAssistantMessage: () => Promise<void>
  onRecoverTask: () => Promise<void>
  executionMode: 'live' | 'demo'
  workspaceContext: WorkspaceContext
  draftTaskIds: WorkflowTaskId[]
  onDraftTaskIds: (tasks: WorkflowTaskId[]) => void
}

export interface AnalysisViewRequest { workflowId: string | null; requestId: number }
