import { redirect } from "next/navigation";

/**
 * 首页：直接重定向到 dashboard
 * （如果未登录，dashboard 页面会再跳转到 login）
 */
export default function Home() {
  redirect("/dashboard");
}
