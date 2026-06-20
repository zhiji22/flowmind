"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { authApi, workflowApi, executionApi, AuthenticationError, scheduleApi } from "@/lib/api";
import { getToken, removeToken } from "@/lib/auth";
import { withToast, showError } from "@/lib/toast";
import type { WorkflowListItem } from "@/types";

export default function DashboardPage() {
  const router = useRouter();
  const [workflows, setWorkflows] = useState<WorkflowListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [operatingId, setOperatingId] = useState<string | null>(null);

  // 页面加载时：检查登录状态 + 获取数据
  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }

    let cancelled = false;

    async function load() {
      try {
        const data = await workflowApi.list();
        if (!cancelled) setWorkflows(data);
      } catch (err) {
        if (!cancelled) {
          if (err instanceof AuthenticationError) {
            router.replace("/login");
          } else {
            removeToken();
            router.replace("/login");
          }
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();

    return () => { cancelled = true; };
  }, [router]);

  /** 删除工作流 */
  async function handleDelete(id: string) {
    if (operatingId) return;
    if (!confirm("确定要删除这个工作流吗？")) return;
    setOperatingId(id);
    try {
      await withToast(workflowApi.delete(id), {
        loading: "正在删除...",
        success: "删除成功",
      });
      setWorkflows((prev) => prev.filter((w) => w.id !== id));
    } catch {
      // withToast 已显示错误 toast
    } finally {
      setOperatingId(null);
    }
  }

  /** 执行工作流 */
  async function handleRun(id: string) {
    if (operatingId) return;
    setOperatingId(id);
    try {
      const execution = await withToast(executionApi.trigger(id), {
        loading: "正在启动执行...",
        success: "执行已启动",
      });
      router.push(`/workflows/${id}/run?executionId=${execution.id}`);
    } catch {
      // withToast 已显示错误 toast
    } finally {
      setOperatingId(null);
    }
  }

  /** 暂停/恢复定时调度 */
  async function handleToggleSchedule(id: string) {
    setOperatingId(id);
    try {
      const result = await scheduleApi.toggle(id);
      // 局部更新对应卡片
      setWorkflows((prev) =>
        prev.map((w) =>
          w.id === id
            ? {
                ...w,
                schedule_enabled: result.enabled,
                next_run: result.next_run,
                status: result.workflow_status,
              }
            : w
        )
      );
    } catch (err) {
      if (err instanceof AuthenticationError) {
        router.replace("/login");
        return;
      }
      showError(err instanceof Error ? err.message : "操作失败");
    } finally {
      setOperatingId(null);
    }
  }

  /** 退出登录：先通知后端将 token 加入黑名单，再清除本地状态 */
  async function handleLogout() {
    try {
      await authApi.logout();
    } finally {
      removeToken();
      router.push("/login");
    }
  }

  // 状态标签颜色
  const statusColors: Record<string, string> = {
    draft: "bg-gray-100 text-gray-700",
    active: "bg-green-100 text-green-700",
    paused: "bg-yellow-100 text-yellow-700",
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* 顶部导航 */}
      <nav className="border-b border-gray-200 bg-white shadow-sm">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <h1
            className="cursor-pointer text-xl font-bold text-gray-900"
            onClick={() => router.push("/dashboard")}
          >
            FlowMind
          </h1>
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push("/approvals")}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
            >
              审批
            </button>
            <button
              onClick={() => router.push("/chat")}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
            >
              + 新建工作流
            </button>
            <button
              onClick={handleLogout}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
            >
              退出
            </button>
          </div>
        </div>
      </nav>

      {/* 主内容 */}
      <main className="mx-auto max-w-7xl px-6 py-8">
        <h2 className="mb-6 text-2xl font-bold text-gray-900">我的工作流</h2>

        {loading && (
          <div className="py-20 text-center text-gray-400">加载中...</div>
        )}

        {!loading && workflows.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20">
            <p className="mb-4 text-gray-400">还没有工作流</p>
            <button
              onClick={() => router.push("/chat")}
              className="rounded-lg bg-blue-600 px-6 py-2.5 font-medium text-white hover:bg-blue-700"
            >
              用自然语言创建第一个工作流
            </button>
          </div>
        )}

        {/* 工作流卡片 */}
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {workflows.map((workflow) => (
            <div
              key={workflow.id}
              className="cursor-pointer rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition-shadow hover:shadow-md"
              onClick={() => router.push(`/workflows/${workflow.id}/edit`)}
            >
              <div className="mb-3 flex items-start justify-between">
                <h3 className="text-lg font-semibold text-gray-900">
                  {workflow.name}
                </h3>
                <span
                  className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColors[workflow.status] || "bg-gray-100 text-gray-700"}`}
                >
                  {workflow.status}
                </span>
              </div>

              <p className="mb-4 line-clamp-2 text-sm text-gray-500">
                {workflow.description || "暂无描述"}
              </p>

              <p className="mb-3 text-xs text-gray-400">
                创建于 {new Date(workflow.created_at).toLocaleString("zh-CN")}
              </p>

              {/* 定时调度状态 */}
              {workflow.cron_expr && (
                <div className="mb-3 flex items-center justify-between rounded-lg bg-gray-50 px-3 py-1.5">
                  <span className="truncate font-mono text-xs text-gray-500">
                    ⏰ {workflow.cron_expr}
                    {workflow.next_run && (
                      <span className="ml-1 text-gray-400">
                        · 下次 {new Date(workflow.next_run).toLocaleString("zh-CN")}
                      </span>
                    )}
                  </span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleToggleSchedule(workflow.id);
                    }}
                    disabled={operatingId === workflow.id}
                    className={`rounded px-2 py-0.5 text-xs font-medium disabled:opacity-50 ${
                      workflow.schedule_enabled === true
                        ? "bg-green-100 text-green-700"
                        : "bg-gray-200 text-gray-500"
                    }`}
                  >
                    {workflow.schedule_enabled === true ? "运行中" : "已暂停"}
                  </button>
                </div>
              )}

              {/* 操作按钮 */}
              <div
                className="flex gap-2"
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  onClick={() => router.push(`/workflows/${workflow.id}/edit`)}
                  disabled={operatingId === workflow.id}
                  className="flex-1 rounded-lg bg-blue-50 py-1.5 text-sm font-medium text-blue-600 hover:bg-blue-100 disabled:opacity-50"
                >
                  编辑
                </button>
                <button
                  onClick={() => handleRun(workflow.id)}
                  disabled={operatingId === workflow.id}
                  className="flex-1 rounded-lg bg-green-50 py-1.5 text-sm font-medium text-green-600 hover:bg-green-100 disabled:opacity-50"
                >
                  {operatingId === workflow.id ? "执行中..." : "执行"}
                </button>
                <button
                  onClick={() => handleDelete(workflow.id)}
                  disabled={operatingId === workflow.id}
                  className="flex-1 rounded-lg bg-red-50 py-1.5 text-sm font-medium text-red-600 hover:bg-red-100 disabled:opacity-50"
                >
                  {operatingId === workflow.id ? "删除中..." : "删除"}
                </button>
              </div>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
