"use client";

import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { statusColors } from "@/lib/workflow-utils";

export type ApprovalNode = Node<{ label: string; stepType: string; config?: Record<string, unknown>; status?: string }, "approval">;

export default function ApprovalNode({ data }: NodeProps<ApprovalNode>) {
  const borderColor = data.status ? statusColors[data.status] || "#f59e0b" : "#f59e0b";
  const approver = (data.config?.approver as string) || "待指定";

  return (
    <div
      className="rounded-xl border-2 bg-yellow-50 px-4 py-3 shadow-md min-w-[160px]"
      style={{ borderColor }}
    >
      <Handle type="target" position={Position.Top} className="!bg-yellow-500 !w-3 !h-3" />
      <Handle type="source" position={Position.Bottom} className="!bg-yellow-500 !w-3 !h-3" />

      <div className="flex items-center gap-2 mb-1">
        <span className="text-lg">👤</span>
        <span className="font-bold text-yellow-800 text-sm">人工审批</span>
      </div>

      <p className="text-xs text-yellow-600 bg-yellow-100 rounded px-2 py-0.5 truncate">
        审批人: {approver}
      </p>

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
