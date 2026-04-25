import { TokenUsage, RunPart, ToolInvocation, Artifact, PlannerDecision, DelegationInfo, Tool, Agent, DomainPack } from './index'

export interface ApiError {
  message: string;
  status: number;
  detail?: string;
}

export interface SessionCreateResponse {
  session: {
    session_id: string;
    title: string;
  };
}

export interface MetadataResponse {
  tools: Tool[];
  agents: Agent[];
  packs: DomainPack[];
}

export interface RunReplayResponse {
  run_id: string;
  status: string;
}

export interface SseEvent {
  event?: string;
  run?: {
    run_id: string;
    status?: string;
    assistant_message?: {
      parts?: RunPart[];
    };
    token_usage?: TokenUsage;
    model_name?: string;
  };
  run_id?: string;
  run_status?: string;
  tool_invocation?: ToolInvocation;
  artifact?: Artifact;
  output_message?: string;
  status?: string;
  detail?: string;
  planner_decision?: PlannerDecision;
  delegation?: DelegationInfo;
  token_usage?: TokenUsage;
}
