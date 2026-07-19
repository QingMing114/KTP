import type { CanonicalManifest } from '../services/canonical/manifestClient'

export interface Session {
  session_id: string;
  title: string;
  created_at?: string;
  updated_at?: string;
  latest_run_id?: string;
  messages?: SessionMessage[];
}

export interface Tool {
  tool_name: string;
  name?: string;
  display_name?: string;
  description?: string;
  category?: string;
  visibility?: string;
  safety_level?: string;
  capabilities?: string[];
  produces_artifacts?: string[] | boolean;
}

export interface ToolDetail extends Tool {
  owned_by_agent?: string;
  input_schema?: Record<string, unknown>;
  output_schema?: Record<string, unknown>;
}

export interface Agent {
  agent_id: string;
  name?: string;
  display_name?: string;
  description?: string;
}

export interface DomainPack {
  pack_id: string;
  name?: string;
  display_name?: string;
  description?: string;
  tools?: string[];
  agents?: string[];
}

export interface Dataset {
  dataset_id: string;
  name: string;
  description?: string;
  data_type?: string;
  region?: string;
  source_path?: string;
  metadata?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
}

export interface RunSummary {
  run_id: string;
  session_id?: string;
  input_message: string;
  status: string;
  created_at?: string;
  model_name?: string;
}

export interface SystemManifest {
  version?: string;
  tools_count?: number;
  agents_count?: number;
  packs_count?: number;
  uptime_seconds?: number;
  config?: Record<string, unknown>;
}

export interface ToolInvocation {
  tool_name: string;
  display_name?: string;
  status: "pending" | "running" | "completed" | "failed" | "success" | "error" | "blocked" | "approval_required";
  result_preview?: string;
  output_summary?: string;
  tool_input?: Record<string, unknown>;
  input_summary?: string;
  raw_input?: string;
  is_user_visible?: boolean;
  category?: string;
}

export interface Artifact {
  title: string;
  content?: string;
  uri?: string;
  artifact_type?: string;
  pack_name?: string;
}

export interface PlannerDecision {
  action: string;
  reasoning?: string;
  target_agent?: string;
  tool_name?: string;
}

export interface TraceEntry {
  event: string;
  detail?: string;
  timestamp?: string;
}

export interface DelegationInfo {
  target_agent: string;
  summary?: string;
}

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number;
  model_name?: string;
}

export interface Run {
  run_id: string;
  session_id?: string;
  input_message: string;
  output_message?: string;
  status: "completed" | "failed" | "running" | "streaming" | "pending";
  created_at?: string;
  session_message_index?: number;
  assistant_message?: {
    parts?: RunPart[];
  };
  input_context?: {
    attachments?: Attachment[];
  };
  tool_invocations?: ToolInvocation[];
  agent_steps?: AgentStep[];
  planner_decision?: PlannerDecision;
  trace?: TraceEntry[];
  delegation?: DelegationInfo;
  artifacts?: Artifact[];
  token_usage?: TokenUsage;
  model_name?: string;
}

export interface AgentStep {
  action: string;
  reasoning?: string;
  response_message?: string;
  tool_calls?: AgentToolCall[];
}

export interface AgentToolCall {
  call_id?: string;
  tool_name: string;
  display_name?: string;
}

export interface RunPart {
  type: 'text' | 'tool_call' | 'tool_result' | 'artifact' | 'error' | 'thinking';
  text?: string;
  tool_invocation?: ToolInvocation;
  artifact?: Artifact;
  status?: string;
}

export interface Attachment {
  kind: "local_path";
  name?: string;
  path: string;
  dataset_id?: string;
  size?: number;
}

export type SubmissionStatus = "queued" | "running" | "cancelling" | "cancelled" | "completed" | "failed"
export type SubmissionStage  = "accepted" | "processing" | "finalizing" | "completed" | "failed"

export interface PendingArtifactRef {
  artifact_id: string
  kind: string
  title: string
  view_url: string
  download_url?: string
}

export interface PendingSubmission {
  submission_id: string | null
  conversation_id: string
  message: string
  attachments: Attachment[]
  status: SubmissionStatus
  stage: SubmissionStage
  run_id: string | null
  parts: RunPart[]
  artifacts: PendingArtifactRef[]
  error?: { code: string; message: string }
}

export interface LoadingState {
  boot: boolean;
  sessions: boolean;
  sendMessage: boolean;
  replay: boolean;
}

export interface ComposerState {
  message: string;
  attachments: Attachment[];
}

export interface SessionMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  parts?: RunPart[];
  run_id?: string;   // canonical run id, populated by Phase 2 for debug drawer access
  timestamp?: string;
}

export interface User {
  user_id: string;
  role: string;
}

export interface AuthState {
  isAuthenticated: boolean;
  user: User | null;
  token: string | null;
}

export interface ReplayResponse {
  run_id: string;
  status: string;
  output_message?: string;
  replay_diff?: Record<string, unknown>;
}

export interface PluginToolEndpoint {
  adapter: 'http_api';
  url: string;
  method: 'GET' | 'POST';
  headers?: Record<string, string>;
  timeout?: number;
}

export interface PluginToolSpec {
  name: string;
  display_name: string;
  description: string;
  category: string;
  pack_name: string;
  usage_hint?: string;
  input_schema: Record<string, string>;
  safety_level: 'safe' | 'caution' | 'dangerous';
  endpoint: PluginToolEndpoint;
  enabled: boolean;
}

export interface PluginToolTestResult {
  success?: boolean
  status: string
  summary: string
  message?: string
  data?: unknown
  payload?: unknown
  artifacts?: Array<{
    pack_name: string
    artifact_type: string
    title: string
    content?: string
    uri?: string
  }>
}

export interface KnowledgeDocument {
  document_id: string
  title: string
  source: string
  metadata?: Record<string, unknown>
  chunk_count?: number
  chunk_ids?: string[]
}

export interface KnowledgeQueryResult {
  chunk_id: string
  document_id: string
  text: string
  source: string
  score: number
  metadata?: Record<string, unknown>
}

export interface AppState {
  apiBaseUrl: string;
  auth: AuthState;
  sessions: Session[];
  selectedSessionId: string | null;
  selectedSession: Session | null;
  sessionMessages: SessionMessage[];
  sessionRuns: Run[];
  selectedRunId: string | null;
  selectedRun: Run | null;
  pendingSubmission: PendingSubmission | null;
  replayResponse: ReplayResponse | null;
  tools: Tool[];
  agents: Agent[];
  packs: DomainPack[];
  errorMessage: string | null;
  loading: LoadingState;
  composer: ComposerState;
  backendOnline: boolean;
  conversationMode: "chat" | "task";
  useMock: boolean;
  manifest: CanonicalManifest | null;
}

export interface AppContextType {
  state: AppState;
  refreshAll: (options?: { preferredSessionId?: string; preferredRunId?: string }) => void;
  selectSession: (sessionId: string) => Promise<void>;
  createSession: (title: string) => Promise<{ session_id: string; title: string }>;
  deleteSession: (sessionId: string) => Promise<void>;
  sendMessage: () => Promise<void>;
  retryLastMessage: () => void;
  stopGeneration: () => void;
  handleMessageChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => void;
  handlePromptClick: (prompt: string) => void;
  handleAttachmentRemove: (index: number) => void;
  addAttachment: (attachment: Attachment) => void;
  replaySelectedRun: () => Promise<void>;
  handleApiConfigSubmit: (e: React.FormEvent) => void;
  clearError: () => void;
  setConversationMode: (mode: "chat" | "task") => void;
  setUseMock: (value: boolean) => void;
  login: (userId: string, password: string) => Promise<void>;
  register: (userId: string, password: string) => Promise<void>;
  logout: () => void;
  refreshSessions: (options?: { preferredSessionId?: string; preferredRunId?: string }) => Promise<void>;
}
