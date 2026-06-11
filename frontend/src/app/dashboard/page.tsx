"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { workflowApi, executionApi } from "@/lib/api";
import { getToken, removeToken } from "@/lib/auth";
import type { WorkflowListItem } from "@/types";

export default function DashboardPage() {
  const router = useRouter();
  const [workflows, setWorkflows] = useState<WorkflowListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // 页面加载时：检查登录状态 + 获取数据
  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }

    let ignore = false;

    (async () => {
      try {
        const data = await workflowApi.list();
        if (!ignore) setWorkflows(data);
      } catch (err) {
        if (!ignore) setError(err instanceof Error ? err.message : "加载失败");
      } finally {
        if (!ignore) setLoading(false);
      }
    })();

    return () => {
      ignore = true;
    };
  }, [router]);

  /** 删除工作流 */
  async function handleDelete(id: string) {
    if (!confirm("确定要删除这个工作流吗？")) return;

    try {
      await workflowApi.delete(id);
      // 从列表中移除，而不是重新请求
      setWorkflows((prev) => prev.filter((w) => w.id !== id));
    } catch (err) {
      alert(err instanceof Error ? err.message : "删除失败");
    }
  }

  /** 执行工作流 */
  async function handleRun(id: string) {
    try {
      const execution = await executionApi.trigger(id);
      alert(`工作流已触发执行，状态: ${execution.status}`);
    } catch (err) {
      alert(err instanceof Error ? err.message : "执行失败");
    }
  }

  /** 退出登录 */
  function handleLogout() {
    removeToken();
    router.push("/login");
  }

  // 状态标签颜色映射
  const statusColors: Record<string, string> = {
    draft: "bg-gray-100 text-gray-700",
    active: "bg-green-100 text-green-700",
    paused: "bg-yellow-100 text-yellow-700",
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* 顶部导航栏 */}
      <nav className="border-b border-gray-200 bg-white shadow-sm">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <h1
            className="cursor-pointer text-xl font-bold text-gray-900"
            onClick={() => router.push("/dashboard")}
          >
            FlowMind
          </h1>
          <div className="flex items-center gap-4">
            {/* 新建工作流按钮 */}
            <button
              onClick={() => router.push("/chat")}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
            >
              + 新建工作流
            </button>
            {/* 退出按钮 */}
            <button
              onClick={handleLogout}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50"
            >
              退出
            </button>
          </div>
        </div>
      </nav>

      {/* 主内容区 */}
      <main className="mx-auto max-w-7xl px-6 py-8">
        <h2 className="mb-6 text-2xl font-bold text-gray-900">我的工作流</h2>

        {/* 加载中 */}
        {loading && (
          <div className="py-20 text-center text-gray-400">加载中...</div>
        )}

        {/* 错误提示 */}
        {error && (
          <div className="rounded-lg bg-red-50 p-4 text-red-600">{error}</div>
        )}

        {/* 空状态 */}
        {!loading && workflows.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20">
            <p className="mb-4 text-gray-400">还没有工作流</p>
            <button
              onClick={() => router.push("/chat")}
              className="rounded-lg bg-blue-600 px-6 py-2.5 font-medium text-white transition-colors hover:bg-blue-700"
            >
              用自然语言创建第一个工作流
            </button>
          </div>
        )}

        {/* 工作流卡片列表 */}
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {workflows.map((workflow) => (
            <div
              key={workflow.id}
              className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm transition-shadow hover:shadow-md"
            >
              {/* 工作流名称 + 状态标签 */}
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

              {/* 描述 */}
              <p className="mb-4 line-clamp-2 text-sm text-gray-500">
                {workflow.description || "暂无描述"}
              </p>

              {/* 创建时间 */}
              <p className="mb-4 text-xs text-gray-400">
                创建于 {new Date(workflow.created_at).toLocaleString("zh-CN")}
              </p>

              {/* 操作按钮 */}
              <div className="flex gap-2">
                <button
                  onClick={() => handleRun(workflow.id)}
                  className="flex-1 rounded-lg bg-green-50 py-1.5 text-sm font-medium text-green-600 transition-colors hover:bg-green-100"
                >
                  执行
                </button>
                <button
                  onClick={() => handleDelete(workflow.id)}
                  className="flex-1 rounded-lg bg-red-50 py-1.5 text-sm font-medium text-red-600 transition-colors hover:bg-red-100"
                >
                  删除
                </button>
              </div>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
