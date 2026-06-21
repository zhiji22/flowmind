// ===== 用户相关类型 =====

export interface User {
  id: string;
  email: string;
  created_at: string;
}

// ===== 认证相关类型 =====

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

// ===== Agent 聊天相关类型 =====

export interface ThoughtStep {
  step: number;
  thought: string;
  action: string;
  observation: string;
}

export interface ChatResponse {
  thoughts: ThoughtStep[];
  final_answer: string;
  iterations: number;
}

// ===== 工作流相关类型 =====

export interface WorkflowStep {
  id: string;
  step_type: string;       // trigger / tool / condition / approval
  tool_name?: string;
  config?: Record<string, unknown>;
  next: string[];
  next_yes: string[];
  next_no: string[];
  position?: { x: number; y: number };
}

export interface Workflow {
  id: string;
  name: string;
  description: string | null;
  dag_json: {
    name: string;
    description: string;
    steps: WorkflowStep[];
  } | null;
  status: string;          // draft / active / paused
  created_at: string;
  updated_at: string;
}

// 工作流列表项（不含 dag_json）
export interface WorkflowListItem {
  id: string;
  name: string;
  description: string | null;
  status: string;
  created_at: string;
  // 调度信息
  cron_expr: string | null;
  schedule_enabled: boolean | null;
  next_run: string | null;
}

// ===== 执行相关类型 =====

export interface StepExecution {
  id: string;
  step_id: string;
  client_id: string | null;
  status: string;
  input_data: Record<string, unknown> | null;
  output_data: Record<string, unknown> | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface Execution {
  id: string;
  workflow_id: string;
  status: string;          // pending / running / success / failed
  started_at: string | null;
  finished_at: string | null;
  result: Record<string, unknown> | null;
  step_executions: StepExecution[];
}

// ===== 聊天消息（前端用） =====

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  thoughts?: ThoughtStep[];
  workflow?: Workflow | null;
}
