"""HTTP 请求工具：调用外部 REST API（带 SSRF 防护）。

安全策略：
  1. 只允许 http/https 协议
  2. 解析域名 IP，拒绝内网 / 环回 / 链路本地地址（防 SSRF）
  3. 请求超时 + 响应体大小上限（防拉取超大响应）
  4. 手动跟随重定向，每跳都重新做 SSRF 校验（防 302 绕过）
"""

import asyncio
import ipaddress
import logging
import socket
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.tools.base import BaseTool, registry

logger = logging.getLogger(__name__)

# 允许的 HTTP 方法
_ALLOWED_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH"}
# 请求超时（秒）
_TIMEOUT = 15.0
# 响应体最大字符数（截断，防止超长响应）
_MAX_RESPONSE_CHARS = 100_000
# 最多跟随的重定向次数
_MAX_REDIRECTS = 5
# DNS 解析超时（秒），防止恶意慢 DNS 占住 worker 线程
_DNS_TIMEOUT = 5.0
# 云厂商元数据服务主机名黑名单（IP 由 _is_unsafe_ip 的 link_local 命中，这里补域名形式）
_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "metadata",
        "metadata.google.internal",
        "metadata.goog",
    }
)


def _is_unsafe_ip(ip: str) -> bool:
    """判断 IP 是否为内网 / 环回 / 链路本地等不可达地址。"""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True

    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified  # 0.0.0.0 / :: —— 部分栈会路由到本机
    )


async def _assert_safe_url(url: str) -> None:
    """SSRF 防护：解析 URL 并拒绝指向内网的请求。

    注意：本函数与 httpx 实际建连是两次独立的 DNS 解析，存在 DNS rebinding
    的 TOCTOU 风险（攻击者控制权威 DNS，让第一次返回公网 IP 通过校验、
    第二次返回 169.254.169.254 等内网地址）。彻底防御需在 Transport 层绑定
    解析结果，调用方应将本服务部署在隔离网络中作为兜底。
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"不允许的协议: {parsed.scheme} （仅支持 http/https）")

    if not parsed.hostname:
        raise ValueError("URL 缺少主机名")

    hostname = parsed.hostname

    # 主机名本身就是 IP 字面量
    try:
        ipaddress.ip_address(hostname)
        is_ip_literal = True
    except ValueError:
        is_ip_literal = False

    if is_ip_literal:
        if _is_unsafe_ip(hostname):
            raise ValueError(f"禁止访问内网地址: {hostname}")
        return

    # 域名：先拒绝明显的本地名 / 云元数据主机名
    if hostname.lower() in _BLOCKED_HOSTNAMES:
        raise ValueError(f"禁止访问的主机名: {hostname}")

    # 域名解析为 IP，逐个检查，防止 DNS 解析到内网（解析加超时，防慢 DNS 占线程）
    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: socket.getaddrinfo(hostname, None)),
            timeout=_DNS_TIMEOUT,
        )
    except TimeoutError as e:
        raise ValueError(f"解析域名 {hostname} 超时") from e
    except socket.gaierror as e:
        raise ValueError(f"无法解析域名 {hostname}: {e}") from e

    for info in infos:
        ip = info[4][0]
        if _is_unsafe_ip(ip):
            raise ValueError(f"域名 {hostname} 解析到内网地址 {ip}，已拦截")


class HttpRequestTool(BaseTool):
    name = "http_request"
    description = (
        "向外部 REST API 发起 HTTP 请求（GET/POST/PUT/DELETE/PATCH）。"
        "用于调用第三方接口、获取数据或触发 Webhook。"
        "出于安全考虑，禁止访问内网地址。"
    )

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "description": "HTTP 方法",
                    "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                },
                "url": {
                    "type": "string",
                    "description": "请求地址，必须是 http/https",
                },
                "headers": {
                    "type": "object",
                    "description": "请求头键值对（可选）",
                },
                "body": {
                    "type": "object",
                    "description": "JSON 请求体（POST/PUT/PATCH 时使用，可选）",
                },
            },
            "required": ["method", "url"],
        }

    async def execute(self, **kwargs) -> str:
        method = str(kwargs.get("method", "GET")).upper()
        url = str(kwargs.get("url", ""))
        headers = kwargs.get("headers")
        body = kwargs.get("body")

        if method not in _ALLOWED_METHODS:
            return f"不支持的方法: {method}"
        if not url:
            return "缺少 url 参数"

        try:
            # 关闭自动重定向，手动循环以便每跳都做 SSRF 校验
            async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
                current_url = url
                current_method = method
                current_body = body
                response: httpx.Response | None = None

                for hop in range(_MAX_REDIRECTS + 1):
                    try:
                        await _assert_safe_url(current_url)
                    except ValueError as e:
                        logger.warning("HTTP 请求被 SSRF 防护拦截 (hop=%d): %s", hop, e)
                        return f"请求被拒绝: {e}"

                    response = await client.request(
                        current_method,
                        current_url,
                        headers=headers if isinstance(headers, dict) else None,
                        json=current_body if (current_body and current_method != "GET") else None,
                    )

                    # 非 3xx 或没有 Location，结束
                    if not (300 <= response.status_code < 400):
                        break
                    location = response.headers.get("location")
                    if not location:
                        break

                    # 计算下一跳绝对 URL
                    next_url = urljoin(current_url, location)

                    # 按 RFC 7231：301/302/303 在跟随时常被改写为 GET 且去掉 body
                    if response.status_code in (301, 302, 303) and current_method != "GET":
                        current_method = "GET"
                        current_body = None

                    current_url = next_url
                else:
                    # for...else：循环正常结束意味着重定向次数超限
                    return f"重定向次数过多（>{_MAX_REDIRECTS}），已中止"

                assert response is not None
                content = response.text[:_MAX_RESPONSE_CHARS]
                return f"[HTTP {response.status_code}] {content}"
        except httpx.TimeoutException:
            return f"请求超时（>{_TIMEOUT}s）"
        except httpx.HTTPError as e:
            return f"请求失败: {e}"


registry.register(HttpRequestTool())
