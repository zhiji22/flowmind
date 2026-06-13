"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { chatApi, workflowApi } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { withToast } from "@/lib/toast";
import type { ChatMessage as ChatMessageType } from "@/types";
import ChatMessage from "@/components/chat/ChatMessage";
import ChatInput from "@/components/chat/ChatInput";
import WorkflowPreview from "@/components/chat/WorkflowPreview";

export default function ChatPage() {
  const router = useRouter();

  // 消息列表
  const [messages, setMessages] = useState<ChatMessageType[]>([]);
  // 最近生成的工作流（用于预览）
  const [previewWorkflow, setPreviewWorkflow] = useState<{
    id: string;
    name: string;
    description: string | null;
    dag_json: Record<string, unknown> | null;
    status: string;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);

  // 消息列表底部引用，用于自动滚动
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 页面加载时检查登录状态
  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
    }
  }, [router]);

  // 消息更新时自动滚到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  /** 发送消息给 Agent */
  async function handleSend(message: string) {
    // 添加用户消息到列表
    setMessages((prev) => [...prev, { role: "user", content: message }]);
    setLoading(true);

    try {
      // 调用后端 Agent 聊天 API
      const data = await chatApi.send(message);

      // 添加 AI 回复到列表
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.final_answer,
          thoughts: data.thoughts,
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `出错了: ${err instanceof Error ? err.message : "请求失败"}`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  /** 从对话内容创建工作流 */
  async function handleCreateWorkflow() {
    // 取用户最后一条消息作为工作流描述
    const lastUserMessage = [...messages]
      .reverse()
      .find((m) => m.role === "user");

    if (!lastUserMessage) return;

    setCreating(true);
    try {
      const workflow = await withToast(
        workflowApi.create(lastUserMessage.content),
        {
          loading: "正在创建工作流...",
          success: "工作流创建成功",
        }
      );
      setPreviewWorkflow(workflow);
    } catch {
      // withToast 已显示错误 toast
    } finally {
      setCreating(false);
    }
  }

  /** 确认保存工作流，跳转到 dashboard */
  function handleConfirmWorkflow() {
    setPreviewWorkflow(null);
    router.push("/dashboard");
  }

  return (
    <div className="flex h-screen flex-col bg-gray-50">
      {/* 顶部导航 */}
      <nav className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-3 shadow-sm">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push("/dashboard")}
            className="text-sm text-gray-500 hover:text-gray-700"
          >
            ← 返回
          </button>
          <h1 className="text-lg font-bold text-gray-900">AI 对话</h1>
        </div>
        <button
          onClick={handleCreateWorkflow}
          disabled={creating || messages.length === 0}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
        >
          {creating ? "生成中..." : "保存为工作流"}
        </button>
      </nav>

      {/* 消息列表区域 */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto max-w-3xl space-y-4">
          {/* 欢迎提示 */}
          {messages.length === 0 && (
            <div className="py-20 text-center">
              <h2 className="mb-3 text-2xl font-bold text-gray-900">
                用自然语言描述你的需求
              </h2>
              <p className="mb-6 text-gray-500">
                例如：每天早上9点搜索竞品价格，如果降价就发邮件通知我
              </p>
              <div className="flex flex-wrap justify-center gap-2">
                {[
                  "每天查竞品价格并发邮件通知",
                  "每周一生成周报并发送给团队",
                  "监控网站变化，有变化时通知我",
                ].map((example) => (
                  <button
                    key={example}
                    onClick={() => handleSend(example)}
                    className="rounded-full border border-gray-200 bg-white px-4 py-2 text-sm text-gray-600 transition-colors hover:bg-gray-50"
                  >
                    {example}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* 渲染每条消息 */}
          {messages.map((msg, idx) => (
            <ChatMessage key={idx} message={msg} />
          ))}

          {/* 加载中提示 */}
          {loading && (
            <div className="flex items-center gap-2 text-sm text-gray-400">
              <div className="h-2 w-2 animate-pulse rounded-full bg-blue-400" />
              AI 正在思考...
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* 工作流预览弹窗 */}
      {previewWorkflow && (
        <WorkflowPreview
          workflow={previewWorkflow}
          onConfirm={handleConfirmWorkflow}
          onCancel={() => setPreviewWorkflow(null)}
        />
      )}

      {/* 输入框 */}
      <ChatInput onSend={handleSend} disabled={loading} />
    </div>
  );
}
