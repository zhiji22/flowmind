"use client";

import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

export type TriggerNode = Node<{ label: string; stepType: string; config?: Record<string, unknown>; status?: string }, "trigger">;

export default function TriggerNode({ data }: NodeProps<TriggerNode>) {
  const schedule = data.config?.schedule as string | undefined;

  return (
    <div className="rounded-xl border-2 border-amber-400 bg-amber-50 px-4 py-3 shadow-md min-w-[160px]">
      <Handle type="source" position={Position.Bottom} className="!bg-amber-500 !w-3 !h-3" />

      <div className="flex items-center gap-2 mb-1">
        <span className="text-lg">⏰</span>
        <span className="font-bold text-amber-800 text-sm">触发器</span>
      </div>

      {schedule && (
        <p className="text-xs text-amber-600 bg-amber-100 rounded px-2 py-0.5 font-mono">
          {schedule}
        </p>
      )}
    </div>
  );
}
