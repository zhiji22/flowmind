"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter, useParams, useSearchParams } from "next/navigation";
import { ReactFlowProvider } from "@xyflow/react";
import { workflowApi, executionApi, AuthenticationError } from "@/lib/api";
import type { StepExecution } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { withToast, showError } from "@/lib/toast";
import { dagToFlow } from "@/lib/workflow-utils";
import ExecutionMonitor from "@/components/workflow/ExecutionMonitor";
import type { Node, Edge } from "@xyflow/react";

const POLL_INTERVAL_MS = 3000;

function RunWorkflowContent() {
  const router = useRouter();
  const params = useParams();
  const searchParams = useSearchParams();
  const workflowId = params.id as string;
  const executionId = searchParams.get("executionId");

  const [workflowName, setWorkflowName] = useState("");
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [stepExecutions, setStepExecutions] = useState<StepExecution[]>([]);
  const [executionStatus, setExecutionStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [retrying, setRetrying] = useState(false);

  // 初始加载
  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }

    let cancelled = false;

    async function loadData() {
      try {
        const [workflow, execution] = await Promise.all([
          workflowApi.get(workflowId),
          executionId ? executionApi.get(executionId) : null,
        ]);

        if (cancelled) return;
        setWorkflowName(workflow.name);

        const flow = dagToFlow(workflow.dag_json);
        setNodes(flow.nodes);
        setEdges(flow.edges);

        if (execution) {
          setExecutionStatus(execution.status);
          setStepExecutions(execution.step_executions);
        }
      } catch (err) {
        if (cancelled) return;
        if (err instanceof AuthenticationError) {
          router.replace("/login");
          return;
        }
        showError("加载数据失败");
        router.push("/dashboard");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadData();
    return () => { cancelled = true; };
  }, [workflowId, executionId, router]);

  // 轮询执行状态（仅在 running/pending 时）
  useEffect(() => {
    if (!executionId) return;
    if (executionStatus !== "running" && executionStatus !== "pending") return;

    const timer = setInterval(async () => {
      try {
        const updated = await executionApi.get(executionId);
        setExecutionStatus(updated.status);
        setStepExecutions(updated.step_executions);
      } catch (err) {
        if (err instanceof AuthenticationError) {
          router.replace("/login");
        }
      }
    }, POLL_INTERVAL_MS);

    return () => clearInterval(timer);
  }, [executionId, executionStatus, router]);

  async function handleRetry() {
    if (!executionId) return;
    setRetrying(true);
    try {
      const execution = await withToast(executionApi.retry(executionId), {
        loading: "正在重试...",
        success: "重试成功",
      });
      setExecutionStatus(execution.status);
      const updated = await executionApi.get(executionId);
      setStepExecutions(updated.step_executions);
    } catch (err) {
      if (err instanceof AuthenticationError) {
        router.replace("/login");
        return;
      }
      // withToast 已显示错误 toast
    } finally {
      setRetrying(false);
    }
  }

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center text-gray-400">
        加载中...
      </div>
    );
  }

  const statusBadge: Record<string, string> = {
    pending: "bg-gray-100 text-gray-700",
    running: "bg-blue-100 text-blue-700",
    success: "bg-green-100 text-green-700",
    failed: "bg-red-100 text-red-700",
  };

  return (
    <div className="flex h-screen flex-col">
      <nav className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-3 shadow-sm">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push("/dashboard")}
            className="text-sm text-gray-500 hover:text-gray-700"
          >
            ← 返回
          </button>
          <h1 className="text-lg font-bold text-gray-900">{workflowName}</h1>
          <span
            className={`rounded-full px-3 py-1 text-xs font-medium ${statusBadge[executionStatus] || "bg-gray-100 text-gray-700"}`}
          >
            {executionStatus || "未知"}
          </span>
        </div>
        <div className="flex gap-2">
          {executionStatus === "failed" && (
            <button
              onClick={handleRetry}
              disabled={retrying}
              className="rounded-lg bg-orange-500 px-4 py-2 text-sm font-medium text-white hover:bg-orange-600 disabled:opacity-50"
            >
              {retrying ? "重试中..." : "重试"}
            </button>
          )}
          <button
            onClick={() => router.push(`/workflows/${workflowId}/edit`)}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
          >
            编辑工作流
          </button>
        </div>
      </nav>

      <div className="flex-1 bg-gray-50">
        <ReactFlowProvider>
          <ExecutionMonitor
            nodes={nodes}
            edges={edges}
            stepExecutions={stepExecutions}
          />
        </ReactFlowProvider>
      </div>
    </div>
  );
}

export default function RunWorkflowPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-screen items-center justify-center text-gray-400">
          加载中...
        </div>
      }
    >
      <RunWorkflowContent />
    </Suspense>
  );
}
