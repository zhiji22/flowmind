/**
 * 工作流 DAG 与 React Flow 节点/边的转换工具
 *
 * 后端 dag_json 格式：
 * { name, description, steps: [{ id, step_type, tool_name, config, next, next_yes, next_no }] }
 *
 * React Flow 格式：
 * nodes: [{ id, type, position, data }]
 * edges: [{ id, source, target, label }]
 */

import type { Node, Edge } from "@xyflow/react";

// DAG 中单个步骤的结构
interface DagStep {
  id: string;
  step_type: string;       // trigger / tool / condition / approval
  tool_name?: string;
  config?: Record<string, unknown>;
  next?: string[];
  next_yes?: string[];
  next_no?: string[];
  position?: { x: number; y: number };
}

// dag_json 的顶层结构
interface DagJson {
  name: string;
  description: string;
  steps: DagStep[];
}

/** 自动布局的垂直间距 */
const LEVEL_HEIGHT = 120;
/** 同层节点的水平间距 */
const NODE_WIDTH = 200;

/**
 * 简单的自动布局算法：按 DAG 层级分配 x, y 坐标
 * 使用 BFS 确定每个节点的层级，同层节点水平排列
 */
function autoLayout(steps: DagStep[]): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>();

  // 构建邻接表：记录每个节点的前驱
  const predecessors = new Map<string, Set<string>>();
  const successors = new Map<string, Set<string>>();

  for (const step of steps) {
    if (!predecessors.has(step.id)) predecessors.set(step.id, new Set());
    if (!successors.has(step.id)) successors.set(step.id, new Set());
  }

  // 根据 next / next_yes / next_no 建立边
  for (const step of steps) {
    const allNext = [
      ...(step.next || []),
      ...(step.next_yes || []),
      ...(step.next_no || []),
    ];
    for (const targetId of allNext) {
      successors.get(step.id)?.add(targetId);
      if (!predecessors.has(targetId)) predecessors.set(targetId, new Set());
      predecessors.get(targetId)?.add(step.id);
    }
  }

  // BFS 分层：找入度为 0 的节点作为起始层
  const levels = new Map<string, number>();
  const queue: string[] = [];

  for (const [id, preds] of predecessors) {
    if (preds.size === 0) {
      queue.push(id);
      levels.set(id, 0);
    }
  }

  let head = 0;
  while (head < queue.length) {
    const current = queue[head++];
    const currentLevel = levels.get(current) || 0;

    for (const next of successors.get(current) || []) {
      const newLevel = currentLevel + 1;
      const existingLevel = levels.get(next);
      // 取最大层级（确保依赖都在前面）
      if (existingLevel === undefined || newLevel > existingLevel) {
        levels.set(next, newLevel);
      }
      // 只有当所有前驱都已处理时才入队
      const allPredsDone = [...(predecessors.get(next) || [])].every(
        (p) => levels.has(p) && (levels.get(p) || 0) < newLevel
      );
      if (allPredsDone && !queue.includes(next)) {
        queue.push(next);
      }
    }
  }

  // 处理未分配层级的节点（孤立节点）
  for (const step of steps) {
    if (!levels.has(step.id)) {
      levels.set(step.id, 0);
    }
  }

  // 按层级分组
  const levelGroups = new Map<number, string[]>();
  for (const [id, level] of levels) {
    if (!levelGroups.has(level)) levelGroups.set(level, []);
    levelGroups.get(level)!.push(id);
  }

  // 分配坐标
  for (const [level, ids] of levelGroups) {
    const startX = -(ids.length - 1) * NODE_WIDTH / 2;
    ids.forEach((id, idx) => {
      positions.set(id, {
        x: startX + idx * NODE_WIDTH,
        y: level * LEVEL_HEIGHT,
      });
    });
  }

  return positions;
}

/**
 * 将后端的 dag_json 转换为 React Flow 的 nodes 和 edges
 */
export function dagToFlow(
  dagJson: Record<string, unknown> | null | undefined,
  stepStatuses?: Map<string, string>
): { nodes: Node[]; edges: Edge[] } {
  if (!dagJson || !Array.isArray(dagJson.steps)) {
    return { nodes: [], edges: [] };
  }

  const steps = dagJson.steps as DagStep[];
  const positions = autoLayout(steps);
  const nodeTypeMap: Record<string, string> = {
    trigger: "trigger",
    tool: "tool",
    condition: "condition",
    approval: "approval",
  };

  // 创建节点
  const nodes: Node[] = steps.map((step) => {
    // 如果步骤有自定义 position，优先使用
    const pos = step.position || positions.get(step.id) || { x: 0, y: 0 };

    // 执行状态颜色（用于 run 页面）
    const status = stepStatuses?.get(step.id);

    return {
      id: step.id,
      type: nodeTypeMap[step.step_type] || "tool",
      position: { x: pos.x, y: pos.y },
      data: {
        label: step.tool_name || step.step_type,
        stepType: step.step_type,
        config: step.config,
        status,  // pending / running / success / failed
      },
    };
  });

  // 创建边
  const edges: Edge[] = [];

  for (const step of steps) {
    // 普通连接（next）
    for (const targetId of step.next || []) {
      edges.push({
        id: `${step.id}-${targetId}`,
        source: step.id,
        target: targetId,
        animated: true,
        style: { stroke: "#6366f1" },
      });
    }

    // 条件为真的连接
    for (const targetId of step.next_yes || []) {
      edges.push({
        id: `${step.id}-yes-${targetId}`,
        source: step.id,
        target: targetId,
        label: "是",
        style: { stroke: "#22c55e" },
        labelStyle: { fill: "#22c55e", fontWeight: 600 },
      });
    }

    // 条件为假的连接
    for (const targetId of step.next_no || []) {
      edges.push({
        id: `${step.id}-no-${targetId}`,
        source: step.id,
        target: targetId,
        label: "否",
        style: { stroke: "#ef4444" },
        labelStyle: { fill: "#ef4444", fontWeight: 600 },
      });
    }
  }

  return { nodes, edges };
}

/**
 * 将 React Flow 的节点位置转换回后端格式（保存编辑后的位置）
 */
export function flowToPositions(
  nodes: Node[]
): Record<string, { x: number; y: number }> {
  const result: Record<string, { x: number; y: number }> = {};
  for (const node of nodes) {
    result[node.id] = { x: node.position.x, y: node.position.y };
  }
  return result;
}

/**
 * 状态 → 颜色映射（执行监控页面用）
 */
export const statusColors: Record<string, string> = {
  pending: "#9ca3af",    // 灰色
  running: "#3b82f6",    // 蓝色
  success: "#22c55e",    // 绿色
  failed: "#ef4444",     // 红色
};
