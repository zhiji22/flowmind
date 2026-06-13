"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import { ReactFlowProvider } from "@xyflow/react";
import { workflowApi, executionApi, AuthenticationError } from "@/lib/api";
import type { WorkflowDetail } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { withToast, showError } from "@/lib/toast";
import { dagToFlow, flowToPositions } from "@/lib/workflow-utils";
import WorkflowEditor from "@/components/workflow/WorkflowEditor";
import type { Node, Edge } from "@xyflow/react";

export default function EditWorkflowPage() {
  const router = useRouter();
  const params = useParams();
  const workflowId = params.id as string;

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [dagJson, setDagJson] = useState<WorkflowDetail["dag_json"]>(null);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }

    let cancelled = false;

    async function loadWorkflow() {
      try {
        const data = await workflowApi.get(workflowId);
        if (cancelled) return;
        setName(data.name);
        setDescription(data.description || "");
        setDagJson(data.dag_json);

        const flow = dagToFlow(data.dag_json);
        setNodes(flow.nodes);
        setEdges(flow.edges);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof AuthenticationError) {
          router.replace("/login");
          return;
        }
        showError("加载工作流失败");
        router.push("/dashboard");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadWorkflow();
    return () => { cancelled = true; };
  }, [workflowId, router]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      const positions = flowToPositions(nodes);
      const updatedDag = dagJson
        ? {
            ...dagJson,
            steps: ((dagJson as Record<string, unknown>).steps as Array<Record<string, unknown>>).map(
              (step) => ({
                ...step,
                position: positions[step.id as string] || step.position,
              })
            ),
          }
        : null;

      await withToast(
        workflowApi.update(workflowId, {
          name,
          description,
          dag_json: updatedDag as Record<string, unknown>,
        }),
        {
          loading: "正在保存...",
          success: "保存成功",
        }
      );
    } catch (err) {
      if (err instanceof AuthenticationError) {
        router.replace("/login");
        return;
      }
      // withToast 已显示错误 toast
    } finally {
      setSaving(false);
    }
  }, [workflowId, name, description, dagJson, nodes, router]);

  async function handleRun() {
    setRunning(true);
    try {
      const execution = await withToast(executionApi.trigger(workflowId), {
        loading: "正在启动执行...",
        success: "执行已启动",
      });
      router.push(`/workflows/${workflowId}/run?executionId=${execution.id}`);
    } catch (err) {
      if (err instanceof AuthenticationError) {
        router.replace("/login");
        return;
      }
      // withToast 已显示错误 toast
    } finally {
      setRunning(false);
    }
  }

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center text-gray-400">
        加载中...
      </div>
    );
  }

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
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="text-lg font-bold text-gray-900 border-b border-transparent hover:border-gray-300 focus:border-blue-500 focus:outline-none"
          />
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleRun}
            disabled={running}
            className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
          >
            {running ? "执行中..." : "执行"}
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? "保存中..." : "保存"}
          </button>
        </div>
      </nav>

      <div className="border-b border-gray-100 bg-white px-6 py-2">
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="添加工作流描述..."
          className="w-full text-sm text-gray-500 focus:outline-none"
        />
      </div>

      <div className="flex-1 bg-gray-50">
        <ReactFlowProvider>
          <WorkflowEditor
            initialNodes={nodes}
            initialEdges={edges}
            onNodesChange={(updatedNodes) => setNodes(updatedNodes)}
          />
        </ReactFlowProvider>
      </div>
    </div>
  );
}
