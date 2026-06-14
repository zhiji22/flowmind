import { getToken } from "./auth";

/**
 * 执行进度 WebSocket 事件。
 * event: step_started / step_success / step_failed /
 *        execution_started / execution_completed / execution_failed / execution_waiting
 */
export interface ExecutionEvent {
  event: string;
  step_id?: string;
  status?: string;
  error?: string;
  [key: string]: unknown;
}

interface ExecutionSocketOptions {
  executionId: string;
  onEvent: (event: ExecutionEvent) => void;
  onClose?: () => void;
}

/**
 * 执行进度 WebSocket 客户端。
 * - 自动重连（最多 5 次，指数退避）
 * - 连接断开时通知调用方
 */
export class ExecutionSocket {
  private ws: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private shouldReconnect = true;
  private attempts = 0;
  private readonly maxAttempts = 5;

  constructor(private readonly options: ExecutionSocketOptions) {}

  /** 建立 WebSocket 连接 */
  connect(): void {
    const token = getToken();
    // WebSocket 不能走 Next.js rewrite 代理，直连后端
    const wsBase = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8001";
    const url = `${wsBase}/api/executions/ws/${this.options.executionId}?token=${encodeURIComponent(token || "")}`;

    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.attempts = 0;
    };

    this.ws.onmessage = (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as ExecutionEvent;
        this.options.onEvent(data);
      } catch {
        // 忽略无法解析的消息
      }
    };

    this.ws.onclose = () => {
      this.options.onClose?.();
      this.tryReconnect();
    };

    this.ws.onerror = () => {
      // 出错后主动关闭，触发 onclose 的重连逻辑
      this.ws?.close();
    };
  }

  /** 指数退避重连 */
  private tryReconnect(): void {
    if (!this.shouldReconnect || this.attempts >= this.maxAttempts) return;
    this.attempts++;
    const delay = Math.min(1000 * this.attempts, 5000);
    this.reconnectTimer = setTimeout(() => this.connect(), delay);
  }

  /** 主动关闭连接，不再重连 */
  close(): void {
    this.shouldReconnect = false;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
    this.ws = null;
  }
}
