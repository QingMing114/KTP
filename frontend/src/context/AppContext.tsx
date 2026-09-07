import React, { createContext, useContext, useState, useEffect, useCallback, useMemo, useRef, ReactNode } from 'react'
import { AppState, AppContextType, Run, RunPart, SessionMessage, Session, Attachment, User, AuthState, SubmissionStatus, SubmissionStage, PendingArtifactRef } from '../types'
import * as api from '../services/api'
import { buildUrl } from '../services/api'
import { listConversations, createConversation, deleteConversation, createSubmission, cancelSubmission, getRun, subscribeSubmissionEvents, fetchManifest } from '../services/canonical'
import type { CanonicalRun } from '../services/canonical'
import type { SubmissionSseEvent } from '../services/canonical/request'
import { logger } from '../utils/logger'

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
      // Invalid persisted credentials are handled below.
    }
    api.clearJwtToken()
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
  pendingSubmission: null,
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
  manifest: null,
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

  const buildSessionTitle = useCallback((message: string) => {
    return message.length > 48 ? `${message.slice(0, 48)}...` : message
  }, [])

  const updatePendingSubmission = useCallback((event: SubmissionSseEvent) => {
    setState(prev => {
      if (!prev.pendingSubmission) return prev
      const sub = prev.pendingSubmission

      switch (event.event) {
        case 'submission.accepted':
          return { ...prev, pendingSubmission: { ...sub, status: 'queued' as const, stage: 'accepted' as const } }

        case 'run.started':
          return {
            ...prev,
            pendingSubmission: {
              ...sub,
              status: 'running' as const,
              stage: 'processing' as const,
              run_id: (event.run_id ?? sub.run_id) as string,
            },
          }

        case 'run.progress':
          return {
            ...prev,
            pendingSubmission: {
              ...sub,
              stage: ((event.stage ?? sub.stage) as SubmissionStage),
            },
          }

        case 'artifact.available': {
          if (!event.data?.artifact) return prev
          return {
            ...prev,
            pendingSubmission: {
              ...sub,
              artifacts: [...sub.artifacts, event.data.artifact as unknown as PendingArtifactRef],
            },
          }
        }

        case 'run.completed':
          return {
            ...prev,
            pendingSubmission: { ...sub, status: 'completed' as const, stage: 'completed' as const },
          }

        case 'run.failed':
          return {
            ...prev,
            pendingSubmission: {
              ...sub,
              status: 'failed' as const,
              stage: 'failed' as const,
              error: event.data?.error as { code: string; message: string } | undefined,
            },
          }

        case 'submission.cancelled':
          return {
            ...prev,
            pendingSubmission: { ...sub, status: 'cancelled' as const, stage: 'cancelled' as const },
          }

        case 'submission.updated':
          return {
            ...prev,
            pendingSubmission: {
              ...sub,
              status: ((event.data?.status ?? sub.status) as SubmissionStatus),
              stage: ((event.data?.stage ?? sub.stage) as SubmissionStage),
              run_id: (event.data?.run_id ?? sub.run_id) as string,
            },
          }

        default:
          return prev
      }
    })
  }, [])

  const checkBackendHealth = useCallback(async () => {
    try {
      await fetch(buildUrl('/health'))
      setState(prev => ({ ...prev, backendOnline: true }))
    } catch {
      setState(prev => ({ ...prev, backendOnline: false }))
    }
  }, [])

  const loadManifest = useCallback(async () => {
    try {
      const manifest = await fetchManifest()
      setState(prev => ({ ...prev, manifest, backendOnline: true }))
      // Optionally load V2 tools/agents/packs if compat_adapters includes /v2
      if (manifest.compat_adapters?.includes('/v2')) {
        api.loadMetadata().then(({ tools, agents, packs }) => {
          setState(prev => ({ ...prev, tools, agents, packs }))
        }).catch(() => {})
      }
    } catch {
      setState(prev => ({ ...prev, backendOnline: false }))
    }
  }, [])

  const refreshSessions = useCallback(async (options: { preferredSessionId?: string; preferredRunId?: string } = {}) => {
    if (!api.getJwtToken() && !api.getApiKey()) {
      setState(prev => ({
        ...prev,
        sessions: [],
        selectedSessionId: null,
        selectedSession: null,
        sessionMessages: [],
        sessionRuns: [],
        selectedRunId: null,
        selectedRun: null,
        errorMessage: null,
        loading: { ...prev.loading, sessions: false },
      }))
      return
    }
    setState(prev => ({ ...prev, loading: { ...prev.loading, sessions: true } }))
    try {
      const conversations = await listConversations()
      const sessions: Session[] = conversations.map(c => ({
        session_id: c.conversation_id,
        title: c.title,
        created_at: c.created_at,
        updated_at: c.updated_at,
      }))
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
          errorMessage: null,
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
        errorMessage: null,
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

  const silentRefreshAfterSend = useCallback(async (_conversationId: string) => {
    try {
      const conversations = await listConversations()
      const sessions: Session[] = conversations.map(c => ({
        session_id: c.conversation_id,
        title: c.title,
      }))
      setState(prev => ({ ...prev, sessions }))
    } catch { /* silent */ }
  }, [])

  const refreshAll = useCallback((options: { preferredSessionId?: string; preferredRunId?: string } = {}) => {
    setState(prev => ({ ...prev, loading: { ...prev.loading, boot: true }, errorMessage: null }))
    checkBackendHealth()
    const bootTimeout = setTimeout(() => {
      setState(prev => ({ ...prev, loading: { ...prev.loading, boot: false } }))
    }, 8000)
    Promise.all([loadManifest(), refreshSessions(options)])
      .catch(() => {})
      .finally(() => {
        clearTimeout(bootTimeout)
        setState(prev => ({ ...prev, loading: { ...prev.loading, boot: false } }))
      })
  }, [checkBackendHealth, loadManifest, refreshSessions])

  const createSession = useCallback(async (title: string) => {
    const conv = await createConversation(title)
    return { session_id: conv.conversation_id, title: conv.title }
  }, [])

  const deleteSession = useCallback(async (sessionId: string) => {
    try {
      await deleteConversation(sessionId)
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

  const commitPendingSubmissionToMessages = useCallback((run: CanonicalRun | null) => {
    setState(prev => {
      if (!prev.pendingSubmission) return prev
      const { message } = prev.pendingSubmission
      const now = new Date().toISOString()

      const userMsg: SessionMessage = {
        role: 'user',
        content: message,
        timestamp: now,
      }

      const textContent = run?.assistant?.summary ?? ''
      const parts: RunPart[] = (run?.assistant?.parts ?? []).map(p => {
        if (p.type === 'artifact_ref' && p.artifact_id) {
          const art = run?.artifacts?.find(a => a.artifact_id === p.artifact_id)
          return {
            type: 'artifact' as const,
            artifact: art ? {
              artifact_type: art.kind,
              pack_name: '',
              title: art.title,
              content: '',
              uri: art.view_url,
            } : undefined,
          }
        }
        return { type: p.type as RunPart['type'], text: p.text }
      })

      const assistantMsg: SessionMessage = {
        role: 'assistant',
        content: textContent,
        parts: parts.length > 0 ? parts : undefined,
        run_id: prev.pendingSubmission.run_id ?? run?.run_id ?? undefined,
        timestamp: now,
      }

      return {
        ...prev,
        sessionMessages: [...prev.sessionMessages, userMsg, assistantMsg],
        pendingSubmission: null,
      }
    })
  }, [])

  const sendMessage = useCallback(async () => {
    const current = stateRef.current
    const message = current.composer.message.trim()
    let conversationId = current.selectedSessionId
    const attachments = [...current.composer.attachments]

    if (!message || current.loading.sendMessage || current.pendingSubmission) return

    setState(prev => ({ ...prev, loading: { ...prev.loading, sendMessage: true } }))

    try {
      // 1. Ensure conversation exists
      let isNew = false
      if (!conversationId) {
        const conv = await createConversation(buildSessionTitle(message))
        conversationId = conv.conversation_id
        isNew = true
      }

      // 2. Initialize pendingSubmission for immediate UI response
      setState(prev => ({
        ...prev,
        selectedSessionId: conversationId!,
        sessions: isNew
          ? [...prev.sessions, { session_id: conversationId!, title: buildSessionTitle(message) }]
          : prev.sessions,
        composer: { message: '', attachments: [] },
        pendingSubmission: {
          submission_id: null,
          conversation_id: conversationId!,
          message,
          attachments,
          status: 'queued' as SubmissionStatus,
          stage: 'accepted' as SubmissionStage,
          run_id: null,
          parts: [],
          artifacts: [],
        },
      }))

      // 3. Create Submission (backend accepts the task)
      const datasetRefs = attachments
        .filter(a => a.dataset_id)
        .map(a => ({ type: 'dataset' as const, id: a.dataset_id! }))

      const sub = await createSubmission(conversationId!, {
        message,
        dataset_refs: datasetRefs,
        mode: { delivery: 'async' },
        context: { inherit: 'latest' },
      })

      // Write submission_id to state
      setState(prev => prev.pendingSubmission
        ? { ...prev, pendingSubmission: { ...prev.pendingSubmission, submission_id: sub.submission_id } }
        : prev
      )

      // 4. SSE subscription
      const abortController = new AbortController()
      abortControllerRef.current = abortController

      await new Promise<void>((resolve, reject) => {
        subscribeSubmissionEvents(
          sub.submission_id,
          (event: SubmissionSseEvent) => {
            updatePendingSubmission(event)
            if (event.event === 'run.completed' || event.event === 'run.failed'
                || event.event === 'submission.cancelled') {
              resolve()
            }
          },
          (error: Error) => {
            if (error.name === 'AbortError') resolve()
            else reject(error)
          },
          abortController.signal,
        )
      })

      abortControllerRef.current = null

      // 5. Fetch final Run result
      const finalSub = stateRef.current.pendingSubmission
      let run: CanonicalRun | null = null
      if (finalSub?.run_id && finalSub.status === 'completed') {
        try { run = await getRun(finalSub.run_id) } catch { /* silent */ }
      }

      // 6. Commit message to history
      commitPendingSubmissionToMessages(run)

      // 7. Refresh session list
      silentRefreshAfterSend(conversationId!)

    } catch (error) {
      logger.error('sendMessage error:', error)
      setState(prev => ({
        ...prev,
        errorMessage: error instanceof Error ? error.message : String(error),
        pendingSubmission: null,
        composer: { ...prev.composer, message: '', attachments: [] },
      }))
    } finally {
      setState(prev => ({ ...prev, loading: { ...prev.loading, sendMessage: false } }))
    }
  }, [createConversation, buildSessionTitle, updatePendingSubmission,
      commitPendingSubmissionToMessages, silentRefreshAfterSend])

  const selectSession = useCallback(async (sessionId: string) => {
    if (sessionId === stateRef.current.selectedSessionId) return
    setState(prev => ({ ...prev, pendingSubmission: null, errorMessage: null }))
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
      logger.error("Error replaying run:", error)
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

  const stopGeneration = useCallback(async () => {
    // Abort SSE connection
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    // Cancel backend submission
    const sub = stateRef.current.pendingSubmission
    if (sub?.submission_id) {
      try { await cancelSubmission(sub.submission_id) } catch { /* ignore */ }
    }
    // Commit any partial content received so far
    commitPendingSubmissionToMessages(null)
  }, [commitPendingSubmissionToMessages])

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
      errorMessage: null,
    }))
    refreshAll()
  }, [refreshAll])

  const register = useCallback(async (userId: string, password: string) => {
    const result = await api.authRegister(userId, password)
    api.setJwtToken(result.access_token)
    const user: User = { user_id: result.user_id, role: result.role || 'user' }
    setState(prev => ({
      ...prev,
      auth: { isAuthenticated: true, user, token: result.access_token },
      errorMessage: null,
    }))
    refreshAll()
  }, [refreshAll])

  const logout = useCallback(() => {
    api.authLogout()
    api.clearJwtToken()
    api.clearApiKey()
    setState(prev => ({
      ...prev,
      auth: { isAuthenticated: false, user: null, token: null },
      sessions: [],
      selectedSessionId: null,
      selectedSession: null,
      sessionMessages: [],
      sessionRuns: [],
      selectedRunId: null,
      selectedRun: null,
      errorMessage: null,
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
        sessions: [],
        selectedSessionId: null,
        selectedSession: null,
        sessionMessages: [],
        sessionRuns: [],
        selectedRunId: null,
        selectedRun: null,
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
