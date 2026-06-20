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
    // 区分两类 401：
    // - 请求已携带 token（受保护接口）：token 过期/无效 → 清除并提示重新登录
    // - 请求未携带 token（如登录/注册）：凭证错误 → 透传后端 detail（如"邮箱或密码错误"）
    if (token) {
      removeToken();
      throw new AuthenticationError("登录已过期，请重新登录");
    }
    const error = await response.json().catch(() => ({ detail: "请求失败" }));
    throw new Error(error.detail || "请求失败");
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

  /** 通知后端将当前 token 加入黑名单。失败不抛错（前端仍会清除本地 token） */
  logout: () =>
    request<{ message: string }>("/api/auth/logout", { method: "POST" }).catch(() => null),

  me: () =>
    request<{ id: string; email: string; created_at: string }>("/api/auth/me"),
};

// ===== 聊天 API =====

export interface ChatThought {
  step: number;
  thought: string;
  action: string;
  observation: string;
}

export interface ChatStreamHandlers {
  /** 收到任意 SSE 事件时实时回调（可选，用于流式渲染思考过程） */
  onEvent?: (event: string, data: Record<string, unknown>) => void;
}

const CHAT_TIMEOUT_MS = 5 * 60 * 1000;

/** 解析单个 SSE 事件块（形如 "event: thought\\ndata: {...}"）。 */
function parseSSEChunk(raw: string): { event: string; data: string } | null {
  let event = "message";
  let data = "";
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  return data ? { event, data } : null;
}

// ===== 聊天 API（SSE 流式）=====
//
// 后端 /api/chat 返回 text/event-stream（event: start/thought/observation/final/error），
// 不能用 response.json() 解析——那会报 "Unexpected token 'e', event: ... is not valid JSON"。

export const chatApi = {
  async send(
    message: string,
    handlers?: ChatStreamHandlers
  ): Promise<{ thoughts: ChatThought[]; final_answer: string; iterations: number }> {
    const token = getToken();
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS);

    try {
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ message }),
        signal: controller.signal,
      });

      if (!resp.ok) {
        if (resp.status === 401) {
          if (token) {
            removeToken();
            throw new AuthenticationError("登录已过期，请重新登录");
          }
          const e = await resp.json().catch(() => ({ detail: "请求失败" }));
          throw new Error(e.detail || "请求失败");
        }
        const e = await resp.json().catch(() => ({ detail: "请求失败" }));
        throw new Error(e.detail || `HTTP ${resp.status}`);
      }
      if (!resp.body) throw new Error("响应不支持流式读取");

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      const thoughts: ChatThought[] = [];
      let finalAnswer = "";
      let iterations = 0;
      let errMsg = "";

      const handle = (event: string, data: Record<string, unknown>): void => {
        handlers?.onEvent?.(event, data);
        switch (event) {
          case "thought":
            thoughts.push({
              step: Number(data.step ?? 0),
              thought: String(data.thought ?? ""),
              action: String(data.action ?? ""),
              observation: String(data.observation ?? ""),
            });
            break;
          case "observation": {
            // thought / observation 成对按序到达，填入最近一条 observation 为空的 thought
            const target = [...thoughts].reverse().find((t) => t.observation === "");
            if (target) target.observation = String(data.observation ?? "");
            break;
          }
          case "final":
            finalAnswer = String(data.answer ?? "");
            iterations = Number(data.iterations ?? 0);
            break;
          case "error":
            errMsg = String(data.message ?? "Agent 出错");
            break;
        }
      };

      const dispatch = (raw: string): void => {
        const parsed = parseSSEChunk(raw);
        if (!parsed) return;
        let data: Record<string, unknown>;
        try {
          data = JSON.parse(parsed.data);
        } catch {
          data = { raw: parsed.data };
        }
        handle(parsed.event, data);
      };

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let sep = buffer.indexOf("\n\n");
        while (sep !== -1) {
          dispatch(buffer.slice(0, sep));
          buffer = buffer.slice(sep + 2);
          sep = buffer.indexOf("\n\n");
        }
      }
      if (buffer.trim()) dispatch(buffer); // flush 尾部残余

      if (errMsg) throw new Error(errMsg);
      return { thoughts, final_answer: finalAnswer, iterations };
    } finally {
      clearTimeout(timeoutId);
    }
  },
};

// ===== 工作流 API =====

export interface WorkflowItem {
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

export interface WorkflowDetail {
  id: string;
  name: string;
  description: string | null;
  dag_json: Record<string, unknown> | null;
  status: string;
  created_at: string;
  updated_at: string;
  // 调度信息（后端 WorkflowResponse 同步下发，创建/编辑后即可拿到）
  cron_expr?: string | null;
  schedule_enabled?: boolean | null;
  next_run?: string | null;
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

// ===== 审批 API =====

export interface ApprovalRequest {
  id: string;
  execution_id: string;
  step_id: string;
  status: string;
  requested_at: string;
  resolved_at: string | null;
  resolver_id: string | null;
  // 上下文
  workflow_id: string | null;
  workflow_name: string | null;
  step_type: string | null;
  step_config: Record<string, unknown> | null;
}

export const approvalApi = {
  /** 列出待审批请求 */
  list: () =>
    request<ApprovalRequest[]>("/api/approvals"),

  /** 通过审批（可附备注） */
  approve: (approvalId: string, note?: string) =>
    request<ApprovalRequest>(`/api/approvals/${approvalId}/approve`, {
      method: "POST",
      body: JSON.stringify(note ? { note } : {}),
    }),

  /** 拒绝审批（可附备注） */
  reject: (approvalId: string, note?: string) =>
    request<ApprovalRequest>(`/api/approvals/${approvalId}/reject`, {
      method: "POST",
      body: JSON.stringify(note ? { note } : {}),
    }),
};

// ===== 定时调度 API =====

export interface ScheduleInfo {
  cron_expr: string | null;
  enabled: boolean | null;
  next_run: string | null;
}

export interface ScheduleToggleResult {
  enabled: boolean;
  cron_expr: string | null;
  next_run: string | null;
  workflow_status: string;
}

export const scheduleApi = {
  /** 设置/更新 cron 定时 */
  set: (workflowId: string, cronExpr: string) =>
    request<ScheduleInfo>(`/api/workflows/${workflowId}/schedule`, {
      method: "POST",
      body: JSON.stringify({ cron_expr: cronExpr }),
    }),

  /** 暂停/恢复调度 */
  toggle: (workflowId: string) =>
    request<ScheduleToggleResult>(`/api/workflows/${workflowId}/schedule/toggle`, {
      method: "POST",
    }),
};

