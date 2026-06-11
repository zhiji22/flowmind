import { getToken } from "./auth";

// 后端 API 基础地址（本地开发环境）
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

/**
 * 封装 fetch 请求，自动带上 JWT token 和统一错误处理
 */
async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();

  // 组装请求头
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  // 如果有 token，自动加上 Authorization
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  // 处理 HTTP 错误
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "请求失败" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json() as Promise<T>;
}

// ===== 认证 API =====

export const authApi = {
  /** 注册新用户 */
  register: (email: string, password: string) =>
    request<{ access_token: string }>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  /** 登录 */
  login: (email: string, password: string) =>
    request<{ access_token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  /** 获取当前用户信息 */
  me: () =>
    request<{ id: string; email: string; created_at: string }>("/api/auth/me"),
};

// ===== 聊天 API =====

export const chatApi = {
  /** 发送消息给 Agent */
  send: (message: string) =>
    request<{
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
    }),
};

// ===== 工作流 API =====

export const workflowApi = {
  /** 获取当前用户的所有工作流 */
  list: () =>
    request<Array<{ id: string; name: string; description: string | null; status: string; created_at: string }>>("/api/workflows"),

  /** 从自然语言创建工作流 */
  create: (message: string) =>
    request<{
      id: string;
      name: string;
      description: string | null;
      dag_json: Record<string, unknown> | null;
      status: string;
      created_at: string;
      updated_at: string;
    }>("/api/workflows", {
      method: "POST",
      body: JSON.stringify({ message }),
    }),

  /** 获取工作流详情 */
  get: (id: string) =>
    request<{
      id: string;
      name: string;
      description: string | null;
      dag_json: Record<string, unknown> | null;
      status: string;
      created_at: string;
      updated_at: string;
    }>(`/api/workflows/${id}`),

  /** 更新工作流 */
  update: (id: string, data: { name?: string; description?: string; dag_json?: Record<string, unknown> }) =>
    request<{ id: string; name: string; description: string | null; dag_json: Record<string, unknown> | null; status: string; created_at: string; updated_at: string }>(`/api/workflows/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  /** 删除工作流 */
  delete: (id: string) =>
    request<{ message: string }>(`/api/workflows/${id}`, { method: "DELETE" }),
};

// ===== 执行 API =====

export const executionApi = {
  /** 触发工作流执行 */
  trigger: (workflowId: string) =>
    request<{
      id: string;
      workflow_id: string;
      status: string;
      started_at: string | null;
      finished_at: string | null;
      result: Record<string, unknown> | null;
      step_executions: Array<unknown>;
    }>(`/api/executions/${workflowId}`, { method: "POST" }),

  /** 查询执行状态 */
  get: (executionId: string) =>
    request<{
      id: string;
      workflow_id: string;
      status: string;
      started_at: string | null;
      finished_at: string | null;
      result: Record<string, unknown> | null;
      step_executions: Array<{
        id: string;
        step_id: string;
        status: string;
        input_data: Record<string, unknown> | null;
        output_data: Record<string, unknown> | null;
        error_message: string | null;
        started_at: string | null;
        finished_at: string | null;
      }>;
    }>(`/api/executions/${executionId}`),

  /** 重试失败的执行 */
  retry: (executionId: string) =>
    request<{ id: string; workflow_id: string; status: string }>(`/api/executions/${executionId}/retry`, { method: "POST" }),
};
