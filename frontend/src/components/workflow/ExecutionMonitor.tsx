"use client";

import { useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import TriggerNode from "./TriggerNode";
import ToolNode from "./ToolNode";
import ConditionNode from "./ConditionNode";
import ApprovalNode from "./ApprovalNode";
import type { StepExecution } from "@/types";

const nodeTypes = {
  trigger: TriggerNode,
  tool: ToolNode,
  condition: ConditionNode,
  approval: ApprovalNode,
};

interface ExecutionMonitorProps {
  nodes: Node[];
  edges: Edge[];
  stepExecutions: StepExecution[];
}

export default function ExecutionMonitor({
  nodes,
  edges,
  stepExecutions,
}: ExecutionMonitorProps) {
  const statusMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const se of stepExecutions) {
      // 优先用 client_id（与 dag_json 节点 id 对齐），回退 step_id
      map.set(se.client_id ?? se.step_id, se.status);
    }
    return map;
  }, [stepExecutions]);

  const enrichedNodes = useMemo(
    () =>
      nodes.map((node) => ({
        ...node,
        data: {
          ...node.data,
          status: statusMap.get(node.id) || "pending",
        },
      })),
    [nodes, statusMap]
  );

  const totalSteps = stepExecutions.length;
  const successCount = stepExecutions.filter((s) => s.status === "success").length;
  const failedCount = stepExecutions.filter((s) => s.status === "failed").length;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-4 border-b border-gray-200 bg-white px-4 py-2">
        <span className="text-sm text-gray-500">
          步骤: {totalSteps}
        </span>
        <span className="text-sm text-green-600">
          成功: {successCount}
        </span>
        <span className="text-sm text-red-600">
          失败: {failedCount}
        </span>
      </div>

      <div className="flex-1">
        <ReactFlow
          nodes={enrichedNodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.3 }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
        >
          <Background color="#e5e7eb" gap={20} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>

      {stepExecutions.length > 0 && (
        <div className="max-h-48 overflow-y-auto border-t border-gray-200 bg-white p-3">
          <h4 className="mb-2 text-sm font-semibold text-gray-700">执行日志</h4>
          {stepExecutions.map((se) => (
            <div
              key={se.step_id}
              className="mb-2 rounded-lg bg-gray-50 px-3 py-2 text-xs"
            >
              <div className="flex items-center gap-2">
                <span className="font-medium text-gray-700">
                  Step {se.step_id.slice(0, 8)}
                </span>
                <span
                  className={`rounded-full px-2 py-0.5 font-medium text-white ${
                    se.status === "success"
                      ? "bg-green-500"
                      : se.status === "failed"
                        ? "bg-red-500"
                        : se.status === "running"
                          ? "bg-blue-500"
                          : "bg-gray-400"
                  }`}
                >
                  {se.status}
                </span>
              </div>
              {se.error_message && (
                <p className="mt-1 text-red-500">{se.error_message}</p>
              )}
              {se.output_data && (
                <p className="mt-1 text-gray-400 truncate">
                  {JSON.stringify(se.output_data).slice(0, 120)}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
