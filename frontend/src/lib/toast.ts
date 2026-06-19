import { toast } from "sonner";

/** Toast 提示选项，传递给 withToast */
export interface ToastMessages {
  loading: string;
  success: string;
}

/** 最短 loading 可见时间（ms），避免请求太快导致 loading 闪烁 */
const MIN_LOADING_MS = 600;

function emitLoadingStart(): void {
  window.dispatchEvent(new CustomEvent("flowmind:loading-start"));
}

function emitLoadingEnd(): void {
  window.dispatchEvent(new CustomEvent("flowmind:loading-end"));
}

/**
 * 用 toast 反馈包装异步操作。
 * 自动显示 loading → 成功/错误 toast，同时显示全屏遮罩层阻止交互。
 * 错误会被重新抛出，调用方仍可 catch 处理（如跳转路由）。
 */
export async function withToast<T>(
  promise: Promise<T>,
  messages: ToastMessages
): Promise<T> {
  const start = Date.now();
  const toastId = toast.loading(messages.loading);
  emitLoadingStart();

  try {
    const result = await promise;
    const elapsed = Date.now() - start;
    if (elapsed < MIN_LOADING_MS) {
      await new Promise((resolve) => setTimeout(resolve, MIN_LOADING_MS - elapsed));
    }
    toast.success(messages.success, { id: toastId, duration: 3000 });
    emitLoadingEnd();
    return result;
  } catch (error: unknown) {
    const elapsed = Date.now() - start;
    if (elapsed < MIN_LOADING_MS) {
      await new Promise((resolve) => setTimeout(resolve, MIN_LOADING_MS - elapsed));
    }
    const errorMessage =
      error instanceof Error ? error.message : "操作失败";
    toast.error(errorMessage, { id: toastId, duration: 5000 });
    emitLoadingEnd();
    throw error;
  }
}

/** 仅显示错误 toast（用于不需要 loading 的场景，如页面初始化加载失败） */
export function showError(message: string): void {
  toast.error(message, { duration: 5000 });
}

/** 仅显示成功 toast（用于不需要 loading 的场景，如审批通过/拒绝） */
export function showSuccess(message: string): void {
  toast.success(message, { duration: 3000 });
}
