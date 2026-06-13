"use client";

import { useEffect, useCallback } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type NodeChange,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import TriggerNode from "./TriggerNode";
import ToolNode from "./ToolNode";
import ConditionNode from "./ConditionNode";
import ApprovalNode from "./ApprovalNode";

const nodeTypes = {
  trigger: TriggerNode,
  tool: ToolNode,
  condition: ConditionNode,
  approval: ApprovalNode,
};

interface WorkflowEditorProps {
  initialNodes: Node[];
  initialEdges: Edge[];
  onNodesChange?: (nodes: Node[]) => void;
}

export default function WorkflowEditor({
  initialNodes,
  initialEdges,
  onNodesChange,
}: WorkflowEditorProps) {
  const [nodes, setNodes, onNodesChangeInternal] = useNodesState(initialNodes);
  const [edges] = useEdgesState(initialEdges);

  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      onNodesChangeInternal(changes);
    },
    [onNodesChangeInternal]
  );

  // 同步最新节点到父组件（在渲染后执行，保证读到最新 state）
  useEffect(() => {
    onNodesChange?.(nodes);
  }, [nodes, onNodesChange]);

  return (
    <div className="h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={handleNodesChange}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        minZoom={0.3}
        maxZoom={2}
      >
        <Background color="#e5e7eb" gap={20} />
        <Controls />
        <MiniMap
          nodeStrokeWidth={3}
          nodeColor={(node) => {
            const typeColors: Record<string, string> = {
              trigger: "#f59e0b",
              tool: "#6366f1",
              condition: "#8b5cf6",
              approval: "#f59e0b",
            };
            return typeColors[node.type || ""] || "#6366f1";
          }}
        />
      </ReactFlow>
    </div>
  );
}
