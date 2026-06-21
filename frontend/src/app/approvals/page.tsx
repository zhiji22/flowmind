"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { approvalApi, AuthenticationError } from "@/lib/api";
import type { ApprovalRequest } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { showError, showSuccess } from "@/lib/toast";

export default function ApprovalsPage() {
  const router = useRouter();
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState<string | null>(null);

  /** 加载待审批列表 */
  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }

    let cancelled = false;

    async function loadApprovals() {
      try {
        const data = await approvalApi.list();
        if (cancelled) return;
        setApprovals(data);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof AuthenticationError) {
          router.replace("/login");
          return;
        }
        showError("加载审批列表失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadApprovals();
    return () => {
      cancelled = true;
    };
  }, [router]);

  /** 通过审批 */
  async function handleApprove(id: string) {
    setActing(id);
    try {
      await approvalApi.approve(id);
      showSuccess("已通过审批，工作流继续执行");
      // 从列表移除
      setApprovals((prev) => prev.filter((a) => a.id !== id));
    } catch (err) {
      if (err instanceof AuthenticationError) {
        router.replace("/login");
        return;
      }
      showError("操作失败");
    } finally {
      setActing(null);
    }
  }

  /** 拒绝审批 */
  async function handleReject(id: string) {
    const note = window.prompt("拒绝原因（可选）");
    // 用户点"取消"返回 null：直接放弃操作，不发请求
    if (note === null) return;
    setActing(id);
    try {
      await approvalApi.reject(id, note || undefined);
      showSuccess("已拒绝审批，工作流已中止");
      setApprovals((prev) => prev.filter((a) => a.id !== id));
    } catch (err) {
      if (err instanceof AuthenticationError) {
        router.replace("/login");
        return;
      }
      showError("操作失败");
    } finally {
      setActing(null);
    }
  }

  // 步骤类型中文标签
  const stepTypeLabels: Record<string, string> = {
    trigger: "触发器",
    tool: "工具",
    condition: "条件",
    approval: "审批",
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* 顶部导航 */}
      <nav className="border-b border-gray-200 bg-white shadow-sm">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push("/dashboard")}
              className="text-sm text-gray-500 hover:text-gray-700"
            >
              ← 返回
            </button>
            <h1 className="text-xl font-bold text-gray-900">待审批</h1>
            {approvals.length > 0 && (
              <span className="rounded-full bg-orange-100 px-2.5 py-0.5 text-xs font-medium text-orange-700">
                {approvals.length}
              </span>
            )}
          </div>
        </div>
      </nav>

      {/* 主内容 */}
      <main className="mx-auto max-w-4xl px-6 py-8">
        {loading && (
          <div className="py-20 text-center text-gray-400">加载中...</div>
        )}

        {!loading && approvals.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 text-gray-400">
            <span className="mb-2 text-4xl">✅</span>
            <p>暂无待审批项</p>
          </div>
        )}

        {/* 审批卡片 */}
        <div className="space-y-4">
          {approvals.map((approval) => (
            <div
              key={approval.id}
              className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm"
            >
              {/* 工作流名 + 步骤类型 */}
              <div className="mb-3 flex items-start justify-between">
                <div>
                  <h3 className="text-lg font-semibold text-gray-900">
                    {approval.workflow_name || "未命名工作流"}
                  </h3>
                  <p className="text-xs text-gray-400">
                    请求时间：{" "}
                    {new Date(approval.requested_at).toLocaleString("zh-CN")}
                  </p>
                </div>
                <span className="rounded-full bg-yellow-100 px-2.5 py-0.5 text-xs font-medium text-yellow-700">
                  {stepTypeLabels[approval.step_type || ""] || approval.step_type || "审批"}
                </span>
              </div>

              {/* 步骤配置摘要 */}
              {approval.step_config && (
                <div className="mb-4 rounded-lg bg-gray-50 p-3">
                  <p className="mb-1 text-xs font-medium text-gray-500">审批步骤配置</p>
                  <pre className="overflow-x-auto text-xs text-gray-600">
                    {JSON.stringify(approval.step_config, null, 2).slice(0, 400)}
                  </pre>
                </div>
              )}

              {/* 操作按钮 */}
              <div className="flex gap-2">
                <button
                  onClick={() => handleApprove(approval.id)}
                  disabled={acting === approval.id}
                  className="flex-1 rounded-lg bg-green-600 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
                >
                  {acting === approval.id ? "处理中..." : "通过"}
                </button>
                <button
                  onClick={() => handleReject(approval.id)}
                  disabled={acting === approval.id}
                  className="flex-1 rounded-lg bg-red-50 py-2 text-sm font-medium text-red-600 hover:bg-red-100 disabled:opacity-50"
                >
                  拒绝
                </button>
              </div>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
