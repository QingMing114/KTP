import React, { createContext, useContext, useState, useEffect, useCallback, useMemo, useRef, ReactNode } from 'react'
import { AppState, AppContextType, Run, RunPart, SessionMessage, ThinkingStep, Session, Attachment, TokenUsage, User, AuthState } from '../types'
import { SseEvent } from '../types/api'
import * as api from '../services/api'
import { buildUrl } from '../services/api'

function loadInitialAuth(): AuthState {
  const token = api.getJwtToken()
  if (token) {
    try {
      const parts = token.split('.')
      if (parts.length === 3) {
        const b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
        const pad = b64.length % 4
        const padded = pad ? b64 + '='.repeat(4 - pad) : b64
        const payload = JSON.parse(decodeURIComponent(escape(atob(padded))))
        if (payload.exp && payload.exp * 1000 > Date.now()) {
          return {
            isAuthenticated: true,
            user: { user_id: payload.user_id || payload.sub || 'unknown', role: payload.role || 'user' },
            token,
          }
        }
      }
    } catch {
      api.clearJwtToken()
    }
  }
  return { isAuthenticated: false, user: null, token: null }
}

const initialState: AppState = {
  apiBaseUrl: api.getApiBaseUrl(),
  auth: loadInitialAuth(),
  sessions: [],
  selectedSessionId: null,
  selectedSession: null,
  sessionMessages: [],
  sessionRuns: [],
  selectedRunId: null,
  selectedRun: null,
  pendingRun: null,
  replayResponse: null,
  tools: [],
  agents: [],
  packs: [],
  errorMessage: null,
  loading: {
    boot: false,
    sessions: false,
    sendMessage: false,
    replay: false,
  },
  composer: {
    message: "",
    attachments: [],
  },
  backendOnline: false,
  conversationMode: "chat",
  useMock: false,
}
const AppContext = createContext<AppContextType | undefined>(undefined)

export const useAppContext = () => {
  const context = useContext(AppContext)
  if (!context) {
    throw new Error('useAppContext must be used within an AppProvider')
  }
  return context
}

interface AppProviderProps {
  children: ReactNode
}

export const AppProvider: React.FC<AppProviderProps> = ({ children }) => {
  const [state, setState] = useState<AppState>(initialState)
  const healthIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const stateRef = useRef(state)
  stateRef.current = state

  const AGENT_DISPLAY_NAMES: Record<string, string> = useMemo(() => ({
    ktp_frontdesk: "前台调度",
    ktp_analysis_specialist: "分析专家",
    ktp_knowledge_specialist: "知识专家",
    ktp_training_specialist: "训练专家",
    ktp_workspace_specialist: "工作区专家",
  }), [])

  const buildSessionTitle = useCallback((message: string) => {
    return message.length > 48 ? `${message.slice(0, 48)}...` : message
  }, [])

  const getAgentDisplayName = useCallback((agentId: string): string => {
    return AGENT_DISPLAY_NAMES[agentId] || agentId
  }, [AGENT_DISPLAY_NAMES])

  const updatePendingRun = useCallback((event: SseEvent) => {
    setState(prev => {
      if (!prev.pendingRun) return { ...prev }

      let newParts: RunPart[] = [...prev.pendingRun.parts]
      let newStatus = prev.pendingRun.status
      let newRunId = prev.pendingRun.runId
      let newThinkingSteps: ThinkingStep[] = [...prev.pendingRun.thinkingSteps]
      let newTokenUsage: TokenUsage | undefined = prev.pendingRun.tokenUsage

      if (event.run_id) newRunId = event.run_id

      if (event.event === "run.started") {
        newStatus = "streaming"
      }

      if (event.event === "token.usage" && event.detail) {
        try {
          newTokenUsage = JSON.parse(event.detail)
        } catch { /* ignore */ }
      }

      if (event.event === "assistant.delta" && event.assistant_part) {
        const part = event.assistant_part
        const lastPart = newParts[newParts.length - 1]
        if (lastPart && lastPart.type === "text" && part.type === "text") {
          newParts = [...newParts.slice(0, -1), { ...lastPart, text: (lastPart.text || "") + (part.text || "") }]
        } else {
          newParts = [...newParts, { type: "text", text: part.text || "" } as RunPart]
        }
      }

      if (event.event === "assistant.delta" && event.output_message) {
        const lastPart = newParts[newParts.length - 1]
        if (lastPart && lastPart.type === "text") {
          newParts = [...newParts.slice(0, -1), { ...lastPart, text: (lastPart.text || "") + event.output_message }]
        } else {
          newParts = [...newParts, { type: "text", text: event.output_message }]
        }
      }

      if (event.event === "planner.thinking" || event.event === "planner.decision") {
        const thinkingText = event.detail || ""
        const pd = event.planner_decision
        const lastStep = newThinkingSteps[newThinkingSteps.length - 1]
        if (lastStep && lastStep.type === "reasoning" && lastStep.label === "思考中") {
          newThinkingSteps = [
            ...newThinkingSteps.slice(0, -1),
            { ...lastStep, detail: thinkingText }
          ]
        } else if (pd) {
          const actionLabel = pd.action === "reply" ? "直接回复" : pd.action === "delegate_agent" ? "委派专家" : pd.action === "call_tool" ? "调用工具" : pd.action === "clarify" ? "请求澄清" : pd.action
          newThinkingSteps = [...newThinkingSteps, {
            type: "reasoning",
            label: `决策：${actionLabel}`,
            detail: thinkingText || pd.reasoning,
          }]
        } else if (thinkingText) {
          newThinkingSteps = [...newThinkingSteps, { type: "reasoning", label: "思考中", detail: thinkingText }]
        }
      }

      if (event.event === "planner.delta" && event.planner_decision) {
        const pd = event.planner_decision
        if (!pd || !pd.reasoning) return {
          ...prev,
          pendingRun: {
            ...prev.pendingRun!,
            parts: newParts,
            status: newStatus,
            runId: newRunId,
            thinkingSteps: newThinkingSteps,
            tokenUsage: newTokenUsage,
          }
        }
        const actionLabel = pd.action === "reply" ? "直接回复" : pd.action === "delegate_agent" ? "委派专家" : pd.action === "call_tools" ? "调用工具" : pd.action === "clarify" ? "请求澄清" : pd.action || pd.action
        newThinkingSteps = [...newThinkingSteps, {
          type: "reasoning",
          label: `规划决策：${actionLabel}`,
          detail: pd.reasoning,
        }]
      }

      if (event.event === "thinking") {
        newThinkingSteps = [...newThinkingSteps, { type: "reasoning", label: "LLM思考中", detail: event.detail }]
      }

      if (event.event === "agent.delegated" && event.delegation) {
        const target = event.delegation.target_agent
        const summary = event.delegation.summary
        newThinkingSteps = [...newThinkingSteps, {
          type: "delegating",
          label: `委派给 ${getAgentDisplayName(target)}`,
          detail: summary,
        }]
      }

      if (event.event === "agent.returned" && event.delegation) {
        const target = event.delegation.target_agent
        newThinkingSteps = [...newThinkingSteps, {
          type: "delegated_back",
          label: `${getAgentDisplayName(target)} 已返回`,
          detail: event.delegation.summary,
        }]
      }

      if (event.event === "tool.started" && event.tool_invocation) {
        const toolName = event.tool_invocation.display_name || event.tool_invocation.tool_name || "工具"
        const toolInput = event.tool_invocation.input_summary || event.tool_invocation.raw_input
          || (event.tool_invocation.tool_input ? JSON.stringify(event.tool_invocation.tool_input, null, 2) : undefined)
        newThinkingSteps = [...newThinkingSteps, {
          type: "tool_calling",
          label: `调用 ${toolName}`,
          toolInput,
          toolStatus: "running",
        }]
        newParts = [...newParts, { type: "tool_call", tool_invocation: event.tool_invocation }]
      }
      if ((event.event === "tool.completed" || event.event === "tool.blocked") && event.tool_invocation) {
        const toolOutput = event.tool_invocation.output_summary || event.tool_invocation.result_preview
        let lastToolStepIdx = -1
        for (let i = newThinkingSteps.length - 1; i >= 0; i--) {
          if (newThinkingSteps[i].type === "tool_calling") {
            lastToolStepIdx = i
            break
          }
        }
        if (lastToolStepIdx >= 0) {
          const step = newThinkingSteps[lastToolStepIdx]
          newThinkingSteps = [
            ...newThinkingSteps.slice(0, lastToolStepIdx),
            { ...step, toolOutput, toolStatus: event.tool_invocation.status || "completed" },
            ...newThinkingSteps.slice(lastToolStepIdx + 1),
          ]
        }
        newParts = [...newParts, {
          type: "tool_result",
          tool_invocation: event.tool_invocation,
          text: event.tool_invocation.result_preview || event.tool_invocation.output_summary,
          status: event.tool_invocation.status,
        }]
      }
      if (event.event === "artifact.available" && event.artifact) {
        let artifactStepIdx = -1
        for (let i = newThinkingSteps.length - 1; i >= 0; i--) {
          if (newThinkingSteps[i].type === "tool_calling") {
            artifactStepIdx = i
            break
          }
        }
        if (artifactStepIdx >= 0) {
          const step = newThinkingSteps[artifactStepIdx]
          newThinkingSteps = [
            ...newThinkingSteps.slice(0, artifactStepIdx),
            { ...step, artifact: event.artifact },
            ...newThinkingSteps.slice(artifactStepIdx + 1),
          ]
        }
        newParts = [...newParts, { type: "artifact", artifact: event.artifact }]
      }

      if (event.event === "run.error" || event.event === "run.failed") {
        if (event.output_message) {
          newParts = [...newParts, { type: "error", text: event.output_message, status: "failed" }]
        }
        if (event.detail && !event.output_message) {
          newParts = [...newParts, { type: "error", text: event.detail, status: "failed" }]
        }
        if (event.run_status === "failed") {
          newStatus = "completed"
          newThinkingSteps = newThinkingSteps.map(s =>
            s.type === "tool_calling" && s.toolStatus === "running"
              ? { ...s, toolStatus: "completed" }
              : s
          )
        } else {
          newStatus = "streaming"
        }
      }
      if (event.event === "run.failed" && event.output_message) {
        newParts = [...newParts, { type: "error", text: event.output_message, status: "failed" }]
        newStatus = "failed"
        newThinkingSteps = newThinkingSteps.map(s =>
          s.type === "tool_calling" && s.toolStatus === "running"
            ? { ...s, toolStatus: "error" }
            : s
        )
      }
      if (event.event === "run.completed") {
        newStatus = "completed"
        newThinkingSteps = newThinkingSteps.map(s =>
          s.type === "tool_calling" && s.toolStatus === "running"
            ? { ...s, toolStatus: "completed" }
            : s
        )
      }

      return {
        ...prev,
        pendingRun: {
          ...prev.pendingRun,
          parts: newParts,
          status: newStatus,
          runId: newRunId,
          thinkingSteps: newThinkingSteps,
          tokenUsage: newTokenUsage,
        }
      }
    })
  }, [getAgentDisplayName])

  const checkBackendHealth = useCallback(async () => {
    try {
      await fetch(buildUrl('/health'))
      setState(prev => ({ ...prev, backendOnline: true }))
    } catch {
      setState(prev => ({ ...prev, backendOnline: false }))
    }
  }, [])

  const loadMetadata = useCallback(async () => {
    try {
      const { tools, agents, packs } = await api.loadMetadata()
      setState(prev => ({ ...prev, tools, agents, packs }))
    } catch (err) {
      setState(prev => ({ ...prev, tools: [], agents: [], packs: [], errorMessage: "元数据加载失败，部分功能可能不可用" }))
    }
  }, [])

  const refreshSessions = useCallback(async (options: { preferredSessionId?: string; preferredRunId?: string } = {}) => {
    setState(prev => ({ ...prev, loading: { ...prev.loading, sessions: true } }))
    try {
      const sessions = await api.getSessions()
      const preferredSessionId = options.preferredSessionId ?? sessions.at(-1)?.session_id ?? null

      if (preferredSessionId === null || !sessions.some((s: Session) => s.session_id === preferredSessionId)) {
        setState(prev => ({
          ...prev,
          sessions,
          selectedSessionId: null,
          selectedSession: null,
          sessionMessages: [],
          sessionRuns: [],
          selectedRunId: null,
          selectedRun: null,
          replayResponse: null,
          loading: { ...prev.loading, sessions: false }
        }))
        return
      }

      const selectedSession = await api.getSession(preferredSessionId) as Session
      const sessionMessages: SessionMessage[] = selectedSession.messages || []

      setState(prev => ({
        ...prev,
        sessions,
        selectedSessionId: preferredSessionId,
        selectedSession,
        sessionMessages,
        sessionRuns: [],
        selectedRunId: null,
        selectedRun: null,
        replayResponse: null,
        loading: { ...prev.loading, sessions: false }
      }))

      try {
        const runSummaries = await api.getSessionRuns(preferredSessionId)
        const finalPreferredRunId = options.preferredRunId ?? runSummaries.at(-1)?.run_id ?? null
        let selectedRun: Run | null = null
        const runDetails: Run[] = []
        for (const summary of runSummaries.slice(-5)) {
          try {
            const detail = await api.getRunDetail(summary.run_id)
            runDetails.push(detail)
            if (detail.run_id === finalPreferredRunId) selectedRun = detail
          } catch { /* skip failed run details */ }
        }
        setState(prev => ({
          ...prev,
          sessionRuns: runDetails,
          selectedRunId: finalPreferredRunId,
          selectedRun,
        }))
      } catch {
        // silent - run details are enhancement only
      }
    } catch (err) {
      setState(prev => ({
        ...prev,
        sessions: [],
        loading: { ...prev.loading, sessions: false },
        errorMessage: "会话列表加载失败",
      }))
    }
  }, [])

  const silentRefreshAfterSend = useCallback(async (sessionId: string, runId?: string) => {
    try {
      const sessions = await api.getSessions()
      const selectedSession = await api.getSession(sessionId) as Session
      setState(prev => ({
        ...prev,
        sessions,
        selectedSession,
        sessionMessages: selectedSession.messages || prev.sessionMessages,
      }))
      if (runId) {
        try {
          const runDetail = await api.getRunDetail(runId)
          setState(prev => ({
            ...prev,
            sessionRuns: [...prev.sessionRuns.filter(r => r.run_id !== runId), runDetail],
          }))
        } catch { /* silent */ }
      }
    } catch { /* silent */ }
  }, [])

  const refreshAll = useCallback((options: { preferredSessionId?: string; preferredRunId?: string } = {}) => {
    setState(prev => ({ ...prev, loading: { ...prev.loading, boot: true }, errorMessage: null }))
    checkBackendHealth()
    const bootTimeout = setTimeout(() => {
      setState(prev => ({ ...prev, loading: { ...prev.loading, boot: false } }))
    }, 8000)
    Promise.all([loadMetadata(), refreshSessions(options)])
      .catch(() => {})
      .finally(() => {
        clearTimeout(bootTimeout)
        setState(prev => ({ ...prev, loading: { ...prev.loading, boot: false } }))
      })
  }, [checkBackendHealth, loadMetadata, refreshSessions])

  const createSession = useCallback(async (title: string) => {
    return api.createSession(title)
  }, [])

  const deleteSession = useCallback(async (sessionId: string) => {
    try {
      await api.deleteSession(sessionId)
      let needsRefresh = false
      setState(prev => {
        const sessions = prev.sessions.filter(s => s.session_id !== sessionId)
        const isSelected = prev.selectedSessionId === sessionId
        if (isSelected) needsRefresh = true
        return {
          ...prev,
          sessions,
          selectedSessionId: isSelected ? null : prev.selectedSessionId,
          selectedSession: isSelected ? null : prev.selectedSession,
          sessionMessages: isSelected ? [] : prev.sessionMessages,
          sessionRuns: isSelected ? [] : prev.sessionRuns,
        }
      })
      if (needsRefresh) {
        refreshSessions({})
      }
    } catch (error) {
      setState(prev => ({ ...prev, errorMessage: error instanceof Error ? error.message : String(error) }))
    }
  }, [refreshSessions])

  const commitPendingRunToMessages = useCallback(() => {
    setState(prev => {
      if (!prev.pendingRun) return prev

      const now = new Date().toISOString()
      const userMsg: SessionMessage = { role: "user", content: prev.pendingRun.message, timestamp: now }
      const assistantText = prev.pendingRun.parts
        .filter((p: RunPart) => p.type === "text" || p.type === "error")
        .map((p: RunPart) => p.text)
        .join("")
      const nonTextParts = prev.pendingRun.parts.filter((p: RunPart) => p.type !== "text" && p.type !== "error")
      const thinkingSteps = prev.pendingRun.thinkingSteps.length > 0
        ? prev.pendingRun.thinkingSteps
        : undefined
      const assistantMsg: SessionMessage = {
        role: "assistant",
        content: assistantText,
        parts: nonTextParts.length > 0 ? prev.pendingRun.parts : undefined,
        thinkingSteps,
        timestamp: now,
      }

      const newMessages = [...prev.sessionMessages, userMsg, assistantMsg]

      return {
        ...prev,
        sessionMessages: newMessages,
        pendingRun: null,
      }
    })
  }, [])

  const sendMessage = useCallback(async () => {
    const current = stateRef.current
    const message = current.composer.message.trim()
    let sessionId = current.selectedSessionId
    const conversationMode = current.conversationMode
    const useMock = current.useMock
    const attachments = [...current.composer.attachments]
    const authUserId = current.auth.isAuthenticated ? (current.auth.user?.user_id || "web-user") : "web-user"

    if (!message || current.loading.sendMessage || current.pendingRun) return

    setState(prev => ({ ...prev, loading: { ...prev.loading, sendMessage: true } }))
    try {
      let isNewSession = false
      if (sessionId === null) {
        const session = await createSession(buildSessionTitle(message))
        sessionId = session.session_id
        isNewSession = true
      }
      const primaryPath = attachments[0]?.path ?? null

      setState(prev => {
        const existingSessions = prev.sessions
        const updatedSessions = isNewSession && !existingSessions.some(s => s.session_id === sessionId)
          ? [...existingSessions, { session_id: sessionId!, title: buildSessionTitle(message) }]
          : existingSessions
        return {
          ...prev,
          sessions: updatedSessions,
          selectedSessionId: sessionId!,
          composer: { ...prev.composer, message: "", attachments: [] },
          pendingRun: {
            sessionId: sessionId!,
            message,
            attachments,
            parts: [],
            status: "streaming",
            runId: null,
            thinkingSteps: [],
            tokenUsage: undefined,
          },
        }
      })

      const abortController = new AbortController()
      abortControllerRef.current = abortController

      let finalRunId: string | null = null
      let streamError: Error | null = null

      await api.requestEventStream(
        `/v2/sessions/${sessionId}/messages/stream`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message,
            user_id: authUserId,
            context: {
              entrypoint: "v2_ui",
              conversation_mode: conversationMode,
              use_mock: useMock,
              attachments: attachments.map(a => ({ kind: "local_path" as const, path: a.path, name: a.name })),
              image_path: primaryPath,
            },
          }),
          signal: abortController.signal,
        },
        (event: SseEvent) => {
          if (event.run_id && !finalRunId) finalRunId = event.run_id
          updatePendingRun(event)
        },
        (error: Error) => {
          streamError = error
        },
        abortController.signal,
      )

      if (streamError != null) {
        if (String(streamError).includes("aborted")) {
          // User cancelled
        } else {
          throw streamError
        }
      }
      abortControllerRef.current = null

      commitPendingRunToMessages()

      silentRefreshAfterSend(sessionId!, finalRunId ?? undefined)
    } catch (error) {
      console.error("Error sending message:", error)
      setState(prev => ({
        ...prev,
        errorMessage: error instanceof Error ? error.message : String(error),
        pendingRun: null,
        composer: { ...prev.composer, message: "", attachments: [] },
      }))
    } finally {
      setState(prev => ({ ...prev, loading: { ...prev.loading, sendMessage: false } }))
    }
  }, [createSession, buildSessionTitle, updatePendingRun, commitPendingRunToMessages, silentRefreshAfterSend])

  const selectSession = useCallback(async (sessionId: string) => {
    if (sessionId === stateRef.current.selectedSessionId) return
    setState(prev => ({ ...prev, pendingRun: null, errorMessage: null }))
    await refreshSessions({ preferredSessionId: sessionId })
  }, [refreshSessions])

  const replaySelectedRun = useCallback(async () => {
    const run = stateRef.current.selectedRun
    if (!run) return
    setState(prev => ({ ...prev, loading: { ...prev.loading, replay: true } }))
    try {
      const replayResponse = await api.replayRun(run.run_id)
      setState(prev => ({ ...prev, replayResponse }))
    } catch (error) {
      console.error("Error replaying run:", error)
      setState(prev => ({ ...prev, errorMessage: error instanceof Error ? error.message : String(error) }))
    } finally {
      setState(prev => ({ ...prev, loading: { ...prev.loading, replay: false } }))
    }
  }, [])

  const handleApiConfigSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault()
    const target = e.target as HTMLFormElement
    const apiBase = target.elements.namedItem('apiBase') as HTMLInputElement
    const apiBaseValue = apiBase.value
    api.setApiBaseUrl(apiBaseValue)
    setState(prev => ({ ...prev, apiBaseUrl: apiBaseValue }))
    refreshAll({ preferredSessionId: stateRef.current.selectedSessionId ?? undefined, preferredRunId: stateRef.current.selectedRunId ?? undefined })
  }, [refreshAll])

  const handleMessageChange = useCallback((e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setState(prev => ({
      ...prev,
      composer: { ...prev.composer, message: e.target.value }
    }))
  }, [])

  const handlePromptClick = useCallback((prompt: string) => {
    setState(prev => ({
      ...prev,
      composer: { ...prev.composer, message: prompt }
    }))
  }, [])

  const handleAttachmentRemove = useCallback((index: number) => {
    setState(prev => ({
      ...prev,
      composer: {
        ...prev.composer,
        attachments: prev.composer.attachments.filter((_, i) => i !== index)
      }
    }))
  }, [])

  const addAttachment = useCallback((attachment: Attachment) => {
    setState(prev => ({
      ...prev,
      composer: {
        ...prev.composer,
        attachments: [...prev.composer.attachments, attachment]
      }
    }))
  }, [])

  const clearError = useCallback(() => {
    setState(prev => ({ ...prev, errorMessage: null }))
  }, [])

  const setConversationMode = useCallback((mode: "chat" | "task") => {
    setState(prev => ({ ...prev, conversationMode: mode }))
  }, [])

  const setUseMock = useCallback((value: boolean) => {
    setState(prev => ({ ...prev, useMock: value }))
  }, [])

  const stopGeneration = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    commitPendingRunToMessages()
  }, [commitPendingRunToMessages])

  const retryLastMessage = useCallback(() => {
    const lastUserMsg = [...stateRef.current.sessionMessages].reverse().find(m => m.role === "user")
    if (!lastUserMsg) return
    setState(prev => ({
      ...prev,
      composer: { ...prev.composer, message: lastUserMsg.content },
    }))
  }, [])

  const login = useCallback(async (userId: string, password: string) => {
    const result = await api.authLogin(userId, password)
    api.setJwtToken(result.access_token)
    const user: User = { user_id: result.user_id, role: result.role || 'user' }
    setState(prev => ({
      ...prev,
      auth: { isAuthenticated: true, user, token: result.access_token },
    }))
  }, [])

  const register = useCallback(async (userId: string, password: string) => {
    const result = await api.authRegister(userId, password)
    api.setJwtToken(result.access_token)
    const user: User = { user_id: result.user_id, role: result.role || 'user' }
    setState(prev => ({
      ...prev,
      auth: { isAuthenticated: true, user, token: result.access_token },
    }))
  }, [])

  const logout = useCallback(() => {
    api.authLogout()
    api.clearJwtToken()
    setState(prev => ({
      ...prev,
      auth: { isAuthenticated: false, user: null, token: null },
      sessions: [],
      selectedSessionId: null,
      selectedSession: null,
      sessionMessages: [],
    }))
  }, [])

  useEffect(() => {
    refreshAll()
    healthIntervalRef.current = setInterval(checkBackendHealth, 30000)
    return () => {
      if (healthIntervalRef.current) clearInterval(healthIntervalRef.current)
    }
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    api.onAuthExpired(() => {
      setState(prev => ({
        ...prev,
        auth: { isAuthenticated: false, user: null, token: null },
        errorMessage: "登录已过期，请重新登录",
      }))
    })
    return () => api.onAuthExpired(null)
  }, [])

  const value: AppContextType = useMemo(() => ({
    state,
    refreshAll,
    selectSession,
    createSession,
    deleteSession,
    sendMessage,
    retryLastMessage,
    stopGeneration,
    handleMessageChange,
    handlePromptClick,
    handleAttachmentRemove,
    addAttachment,
    replaySelectedRun,
    handleApiConfigSubmit,
    clearError,
    setConversationMode,
    setUseMock,
    login,
    register,
    logout,
    refreshSessions,
  }), [state, refreshAll, selectSession, createSession, deleteSession, sendMessage, retryLastMessage, stopGeneration, handleMessageChange, handlePromptClick, handleAttachmentRemove, addAttachment, replaySelectedRun, handleApiConfigSubmit, clearError, setConversationMode, setUseMock, login, register, logout, refreshSessions])

  return (
    <AppContext.Provider value={value}>
      {children}
    </AppContext.Provider>
  )
}

export default AppContext
