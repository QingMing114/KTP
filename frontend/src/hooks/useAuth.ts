import { useAppContext } from '../context/AppContext'
import type { User, AuthState, Session, SessionMessage, Run, Attachment, PendingSubmission } from '../types'

/** Auth-specific hook — extracts auth slice from AppContext */
export function useAuth(): {
  auth: AuthState
  user: User | null
  isAuthenticated: boolean
  login: (userId: string, password: string) => Promise<void>
  register: (userId: string, password: string) => Promise<void>
  logout: () => void
} {
  const ctx = useAppContext()
  return {
    auth: ctx.state.auth,
    user: ctx.state.auth.user,
    isAuthenticated: ctx.state.auth.isAuthenticated,
    login: ctx.login,
    register: ctx.register,
    logout: ctx.logout,
  }
}

/** Session-specific hook — extracts session slice from AppContext */
export function useSession(): {
  sessions: Session[]
  selectedSessionId: string | null
  selectedSession: Session | null
  sessionMessages: SessionMessage[]
  sessionRuns: Run[]
  selectSession: (sessionId: string) => Promise<void>
  createSession: (title: string) => Promise<{ session_id: string; title: string }>
  deleteSession: (sessionId: string) => Promise<void>
  refreshSessions: (options?: { preferredSessionId?: string; preferredRunId?: string }) => Promise<void>
} {
  const ctx = useAppContext()
  return {
    sessions: ctx.state.sessions,
    selectedSessionId: ctx.state.selectedSessionId,
    selectedSession: ctx.state.selectedSession,
    sessionMessages: ctx.state.sessionMessages,
    sessionRuns: ctx.state.sessionRuns,
    selectSession: ctx.selectSession,
    createSession: ctx.createSession,
    deleteSession: ctx.deleteSession,
    refreshSessions: ctx.refreshSessions,
  }
}

/** Chat-specific hook — extracts chat/messaging slice from AppContext */
export function useChat(): {
  pendingSubmission: PendingSubmission | null
  composer: { message: string; attachments: Attachment[] }
  conversationMode: "chat" | "task"
  useMock: boolean
  loading: { boot: boolean; sessions: boolean; sendMessage: boolean; replay: boolean }
  sendMessage: () => Promise<void>
  stopGeneration: () => void
  retryLastMessage: () => void
  handleMessageChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => void
  handlePromptClick: (prompt: string) => void
  addAttachment: (attachment: Attachment) => void
  handleAttachmentRemove: (index: number) => void
  setConversationMode: (mode: "chat" | "task") => void
  setUseMock: (value: boolean) => void
  replaySelectedRun: () => Promise<void>
} {
  const ctx = useAppContext()
  return {
    pendingSubmission: ctx.state.pendingSubmission,
    composer: ctx.state.composer,
    conversationMode: ctx.state.conversationMode,
    useMock: ctx.state.useMock,
    loading: ctx.state.loading,
    sendMessage: ctx.sendMessage,
    stopGeneration: ctx.stopGeneration,
    retryLastMessage: ctx.retryLastMessage,
    handleMessageChange: ctx.handleMessageChange,
    handlePromptClick: ctx.handlePromptClick,
    addAttachment: ctx.addAttachment,
    handleAttachmentRemove: ctx.handleAttachmentRemove,
    setConversationMode: ctx.setConversationMode,
    setUseMock: ctx.setUseMock,
    replaySelectedRun: ctx.replaySelectedRun,
  }
}
