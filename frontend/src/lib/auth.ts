// Token 在 localStorage 中的 key
const TOKEN_KEY = "flowmind_token";

/**
 * 保存 JWT token 到 localStorage
 */
export function saveToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

/**
 * 获取当前保存的 JWT token
 */
export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

/**
 * 清除 token（退出登录）
 */
export function removeToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

/**
 * 检查用户是否已登录（简单判断 token 是否存在）
 */
export function isAuthenticated(): boolean {
  return !!getToken();
}
