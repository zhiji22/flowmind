import { getToken, removeToken } from "./auth";

const API_BASE = "";

export class AuthenticationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AuthenticationError";
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    removeToken();
    throw new AuthenticationError("登录已过期，请重新登录");
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "请求失败" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json() as Promise<T>;
}

// ===== 认证 API =====

export const authApi = {
  register: (email: string, password: string) =>
    request<{ access_token: string }>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  login: (email: string, password: string) =>
    request<{ access_token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  me: () =>
    request<{ id: string; email: string; created_at: string }>("/api/auth/me"),
};

// ===== 聊天 API =====

const CHAT_TIMEOUT_MS = 5 * 60 * 1000;

export const chatApi = {
  send: (message: string) => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS);

    return request<{
      thoughts: Array<{
        step: number;
        thought: string;
        action: string;
        observation: string;
      }>;
      final_answer: string;
      iterations: number;
    }>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message }),
      signal: controller.signal,
    }).finally(() => clearTimeout(timeoutId));
  },
};

// ===== 工作流 API =====

export interface WorkflowItem {
  id: string;
  name: string;
  description: string | null;
  status: string;
  created_at: string;
}

export interface WorkflowDetail {
  id: string;
  name: string;
  description: string | null;
  dag_json: Record<string, unknown> | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface StepExecution {
  id: string;
  step_id: string;
  status: string;
  input_data: Record<string, unknown> | null;
  output_data: Record<string, unknown> | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface ExecutionDetail {
  id: string;
  workflow_id: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  result: Record<string, unknown> | null;
  step_executions: StepExecution[];
}

export const workflowApi = {
  list: () =>
    request<WorkflowItem[]>("/api/workflows"),

  create: (message: string) =>
    request<WorkflowDetail>("/api/workflows", {
      method: "POST",
      body: JSON.stringify({ message }),
    }),

  get: (id: string) =>
    request<WorkflowDetail>(`/api/workflows/${id}`),

  update: (id: string, data: { name?: string; description?: string; dag_json?: Record<string, unknown> }) =>
    request<WorkflowDetail>(`/api/workflows/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    request<{ message: string }>(`/api/workflows/${id}`, { method: "DELETE" }),
};

// ===== 执行 API =====

export const executionApi = {
  trigger: (workflowId: string) =>
    request<ExecutionDetail>(`/api/executions/${workflowId}`, { method: "POST" }),

  get: (executionId: string) =>
    request<ExecutionDetail>(`/api/executions/${executionId}`),

  retry: (executionId: string) =>
    request<{ id: string; workflow_id: string; status: string }>(`/api/executions/${executionId}/retry`, { method: "POST" }),
};
