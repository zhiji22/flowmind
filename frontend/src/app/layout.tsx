import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Toaster } from "sonner";
import LoadingOverlay from "@/components/LoadingOverlay";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "FlowMind - AI智能工作流平台",
  description: "通过自然语言创建和执行自动化工作流",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-gray-50 text-gray-900">
        {children}
        <LoadingOverlay />
        <Toaster
          position="top-center"
          toastOptions={{
            unstyled: true,
            classNames: {
              toast:
                "flex items-center gap-3 rounded-lg border border-gray-200 bg-white px-5 py-3 shadow-lg max-w-sm w-full z-[9999]",
              title: "text-sm font-medium text-gray-900",
              description: "text-sm text-gray-500",
              success: "border-l-4 border-l-green-500",
              error: "border-l-4 border-l-red-500",
              loading: "border-l-4 border-l-blue-500",
              // 修复 sonner loader 图标与文本的水平对齐问题
              loader: "shrink-0",
            },
          }}
        />
      </body>
    </html>
  );
}
