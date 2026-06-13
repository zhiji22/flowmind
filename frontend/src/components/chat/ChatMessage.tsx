"use client";

import { useState } from "react";
import type { ChatMessage as ChatMessageType } from "@/types";

interface ChatMessageProps {
  message: ChatMessageType;
}

export default function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === "user";
  const [showThoughts, setShowThoughts] = useState(false);

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 ${
          isUser
            ? "bg-blue-600 text-white"
            : "bg-white text-gray-900 shadow-sm border border-gray-100"
        }`}
      >
        {/* 消息内容 */}
        <p className="whitespace-pre-wrap text-sm leading-relaxed">
          {message.content}
        </p>

        {/* Agent 的思考过程（可展开/折叠） */}
        {!isUser && message.thoughts && message.thoughts.length > 0 && (
          <div className="mt-3 border-t border-gray-100 pt-2">
            <button
              onClick={() => setShowThoughts(!showThoughts)}
              className="text-xs text-gray-400 hover:text-gray-600"
            >
              {showThoughts ? "隐藏思考过程 ▲" : "查看思考过程 ▼"}
            </button>

            {showThoughts && (
              <div className="mt-2 space-y-2">
                {message.thoughts.map((t) => (
                  <div key={t.step} className="rounded-lg bg-gray-50 p-2 text-xs text-gray-600">
                    <p><span className="font-semibold text-blue-600">思考:</span> {t.thought}</p>
                    <p><span className="font-semibold text-green-600">行动:</span> {t.action}</p>
                    <p><span className="font-semibold text-purple-600">观察:</span> {t.observation}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
