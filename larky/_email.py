"""共享邮件通知器 — 所有平台通用。

从 wechat_bot.py, wechat_service.py, service.py 的重复 SMTP 代码中提取。
"""

import asyncio
import logging
import os
import smtplib
from datetime import datetime
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


class EmailNotifier:
    """邮件通知器 — 通过 SMTP 发送邮件通知。

    通过 BACKUP_EMAIL_* 环境变量配置。若未配置 BACKUP_EMAIL_TO 则静默禁用。
    """

    def __init__(self):
        self.enabled = bool(os.getenv("BACKUP_EMAIL_TO"))
        self.email_from = os.getenv("BACKUP_EMAIL_FROM", "")
        self.email_to = os.getenv("BACKUP_EMAIL_TO", "")
        self.email_smtp = os.getenv("BACKUP_EMAIL_SMTP", "smtp.gmail.com")
        self.email_port = int(os.getenv("BACKUP_EMAIL_PORT", "587"))
        self.email_user = os.getenv("BACKUP_EMAIL_USER", "")
        self.email_password = os.getenv("BACKUP_EMAIL_PASSWORD", "")

    async def send(self, subject: str, message: str) -> bool:
        """发送通用通知邮件。

        Returns:
            True 若发送成功或邮件未启用，否则 False。
        """
        if not self.enabled:
            return False
        try:
            await self._send_email(subject, message)
            logger.info("📧 邮件已发送: %s", subject)
            return True
        except Exception as e:
            logger.error("发送邮件失败: %s", e)
            return False

    async def send_message_backup(
        self, text: str, source: str, timestamp: str | None = None
    ) -> bool:
        """发送高优先级消息的邮件备份。

        Args:
            text: 消息内容。
            source: 来源程序标识。
            timestamp: 消息时间戳（可选）。

        Returns:
            True 若发送成功或邮件未启用，否则 False。
        """
        if not self.enabled:
            return False

        subject = f"🚨 [高优先级消息备份] {source}"
        body = f"""消息服务离线，高优先级消息已通过邮件备份发送。

来源程序: {source}
时间: {timestamp or datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

消息内容:
{text}

---
此消息将在服务恢复后自动重发。"""

        try:
            await self._send_email(subject, body)
            logger.info("📧 消息备份邮件已发送: %s", text[:30])
            return True
        except Exception as e:
            logger.error("发送消息备份邮件失败: %s", e)
            return False

    async def _send_email(self, subject: str, body: str) -> None:
        """通过 SMTP 发送邮件。

        根据端口自动选择:
        - 465: SMTP_SSL（直接 SSL）
        - 587 及其他: SMTP + STARTTLS
        """
        loop = asyncio.get_running_loop()

        def _send():
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = self.email_from
            msg["To"] = self.email_to

            if self.email_port == 465:
                with smtplib.SMTP_SSL(self.email_smtp, self.email_port) as server:
                    server.login(self.email_user, self.email_password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(self.email_smtp, self.email_port) as server:
                    server.starttls()
                    server.login(self.email_user, self.email_password)
                    server.send_message(msg)

        await loop.run_in_executor(None, _send)
