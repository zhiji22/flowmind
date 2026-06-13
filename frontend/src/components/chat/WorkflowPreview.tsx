"use client";

interface WorkflowPreviewProps {
  workflow: {
    id: string;
    name: string;
    description: string | null;
    dag_json: Record<string, unknown> | null;
    status: string;
  };
  onConfirm: () => void;
  onCancel: () => void;
}

export default function WorkflowPreview({
  workflow,
  onConfirm,
  onCancel,
}: WorkflowPreviewProps) {
  // 从 dag_json 中提取步骤列表
  const steps = (workflow.dag_json?.steps ?? []) as Array<{
    id: string;
    step_type: string;
    tool_name?: string;
    config?: Record<string, unknown>;
  }>;

  // 步骤类型对应的中文名和图标
  const typeLabels: Record<string, string> = {
    trigger: "触发器",
    tool: "工具",
    condition: "条件",
    approval: "审批",
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl">
        {/* 标题 */}
        <h2 className="mb-1 text-xl font-bold text-gray-900">
          {workflow.name}
        </h2>
        <p className="mb-4 text-sm text-gray-500">
          {workflow.description || "工作流已生成，确认后将保存"}
        </p>

        {/* 步骤列表 */}
        <div className="mb-6 max-h-64 space-y-2 overflow-y-auto">
          {steps.map((step, idx) => (
            <div
              key={step.id}
              className="flex items-center gap-3 rounded-lg bg-gray-50 px-4 py-2.5"
            >
              {/* 步骤序号 */}
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-blue-100 text-xs font-bold text-blue-600">
                {idx + 1}
              </span>

              {/* 步骤类型标签 */}
              <span className="rounded bg-gray-200 px-2 py-0.5 text-xs font-medium text-gray-600">
                {typeLabels[step.step_type] || step.step_type}
              </span>

              {/* 工具名称 */}
              {step.tool_name && (
                <span className="text-sm font-medium text-gray-900">
                  {step.tool_name}
                </span>
              )}

              {/* 配置信息摘要 */}
              {step.config && Object.keys(step.config).length > 0 && (
                <span className="truncate text-xs text-gray-400">
                  {JSON.stringify(step.config).slice(0, 60)}
                </span>
              )}
            </div>
          ))}
        </div>

        {/* 操作按钮 */}
        <div className="flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 rounded-lg border border-gray-300 py-2.5 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50"
          >
            取消
          </button>
          <button
            onClick={onConfirm}
            className="flex-1 rounded-lg bg-blue-600 py-2.5 text-sm font-medium text-white transition-colors hover:bg-blue-700"
          >
            确认保存
          </button>
        </div>
      </div>
    </div>
  );
}
