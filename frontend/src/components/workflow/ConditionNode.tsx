"use client";

import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { statusColors } from "@/lib/workflow-utils";

export type ConditionNode = Node<{ label: string; stepType: string; config?: Record<string, unknown>; status?: string }, "condition">;

export default function ConditionNode({ data }: NodeProps<ConditionNode>) {
  const borderColor = data.status ? statusColors[data.status] || "#8b5cf6" : "#8b5cf6";

  const field = data.config?.field as string | undefined;
  const operator = data.config?.operator as string | undefined;
  const value = data.config?.value as string | undefined;

  return (
    <div
      className="rounded-xl border-2 bg-purple-50 px-4 py-3 shadow-md min-w-[180px]"
      style={{ borderColor }}
    >
      <Handle type="target" position={Position.Top} className="!bg-purple-500 !w-3 !h-3" />

      <Handle
        type="source"
        position={Position.Bottom}
        id="yes"
        className="!bg-green-500 !w-3 !h-3"
        style={{ left: "30%" }}
      />

      <Handle
        type="source"
        position={Position.Bottom}
        id="no"
        className="!bg-red-500 !w-3 !h-3"
        style={{ left: "70%" }}
      />

      <div className="flex items-center gap-2 mb-1">
        <span className="text-lg">🔀</span>
        <span className="font-bold text-purple-800 text-sm">条件判断</span>
      </div>

      {field && (
        <p className="text-xs text-purple-600 bg-purple-100 rounded px-2 py-0.5 font-mono truncate">
          {field} {operator} {value}
        </p>
      )}

      {data.status && (
        <span
          className="mt-1 inline-block rounded-full px-2 py-0.5 text-xs font-medium text-white"
          style={{ backgroundColor: statusColors[data.status] }}
        >
          {data.status}
        </span>
      )}
    </div>
  );
}
