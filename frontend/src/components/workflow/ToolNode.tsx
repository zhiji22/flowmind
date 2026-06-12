"use client";

import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { statusColors } from "@/lib/workflow-utils";

export type ToolNode = Node<{ label: string; stepType: string; config?: Record<string, unknown>; status?: string }, "tool">;

export default function ToolNode({ data }: NodeProps<ToolNode>) {
  const borderColor = data.status ? statusColors[data.status] || "#6366f1" : "#6366f1";

  return (
    <div
      className="rounded-xl border-2 bg-white px-4 py-3 shadow-md min-w-[180px]"
      style={{ borderColor }}
    >
      <Handle type="target" position={Position.Top} className="!bg-indigo-500 !w-3 !h-3" />
      <Handle type="source" position={Position.Bottom} className="!bg-indigo-500 !w-3 !h-3" />

      <div className="flex items-center gap-2 mb-1">
        <span className="text-lg">🔧</span>
        <span className="font-bold text-indigo-800 text-sm">{data.label}</span>
      </div>

      {data.config && Object.keys(data.config).length > 0 && (
        <p className="text-xs text-gray-500 truncate max-w-[160px]">
          {JSON.stringify(data.config).slice(0, 80)}
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
