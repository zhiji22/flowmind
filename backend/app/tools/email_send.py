import logging
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import aiosmtplib

from app.config import settings
from app.tools.base import BaseTool, registry

logger = logging.getLogger(__name__)

# Basic RFC-compliant email regex
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


class EmailSendTool(BaseTool):
    name = "send_email"
    description = "发送电子邮件。当需要通知用户、发送报告或报警时使用。"

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "收件人邮箱地址",
                },
                "subject": {
                    "type": "string",
                    "description": "邮件主题",
                },
                "body": {
                    "type": "string",
                    "description": "邮件正文内容",
                },
            },
            "required": ["to", "subject", "body"],
        }

    async def execute(self, **kwargs) -> str:
        to_addr: str = kwargs.get("to", "")
        subject: str = kwargs.get("subject", "(无主题)")
        body: str = kwargs.get("body", "")

        if not to_addr:
            return "发送失败：缺少收件人邮箱地址"

        if not _EMAIL_RE.match(to_addr):
            return "发送失败：收件人邮箱地址格式无效"

        msg = MIMEMultipart()
        msg["From"] = settings.SMTP_FROM
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        try:
            await aiosmtplib.send(
                msg,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USER,
                password=settings.SMTP_PASSWORD,
                use_tls=settings.SMTP_USE_TLS and settings.SMTP_PORT == 465,
                start_tls=settings.SMTP_USE_TLS and settings.SMTP_PORT == 587,
            )
            logger.info("邮件已发送至 %s，主题: %s", to_addr, subject)
            return f"邮件已成功发送至 {to_addr}"
        except Exception as e:
            logger.error("邮件发送失败: %s", e)
            raise RuntimeError("邮件发送失败，请检查邮件服务配置") from e


registry.register(EmailSendTool())
