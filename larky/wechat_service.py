"""微信消息服务 - 独立进程运行，通过 Redis Pub/Sub 与其他程序通信

架构：
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ 量化程序 A  │     │ 量化程序 B  │     │ 量化程序 C  │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       └───────────────────┼───────────────────┘
                           ▼
                   ┌───────────────┐
                   │ Redis Pub/Sub │
                   └───────┬───────┘
                           │
                           ▼
                   ┌───────────────┐
                   │ WeChatService │ ← 唯一微信连接
                   └───────────────┘

使用方法：
    # 终端1：启动微信消息服务
    uv run python -m larky.wechat_service

    # 终端2：量化程序使用 WeChatClient 发送/接收消息

消息优先级：
    - normal（默认）: 普通优先级，离线时消息丢弃
    - high: 高优先级，离线时消息保存到队列并通过邮件备份发送，
            微信恢复后自动重发积压的历史消息

故障处理：
    - 掉线自动重连
    - Token 过期时通过备份渠道通知用户重新扫码
    - 高优先级消息队列持久化，恢复后重发
"""

import asyncio
import json
import logging
import os
import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.mime.text import MIMEText
from typing import Any, Callable

try:
    import redis.asyncio as redis
except ImportError:
    raise ImportError("请安装 redis: uv add redis")

from dotenv import load_dotenv

from . import WeChatBot, WeChatMessage, WeChatError

load_dotenv()

logger = logging.getLogger(__name__)

CHANNEL_INCOMING = "wechat:incoming"
CHANNEL_OUTGOING = "wechat:outgoing"
CHANNEL_STATUS = "wechat:status"
QUEUE_PENDING = "wechat:pending_messages"
QUEUE_FAILED = "wechat:failed_messages"


def _build_incoming_payload(msg: "WeChatMessage") -> dict[str, Any]:
    """Build a complete serializable payload from an incoming WeChatMessage.

    Includes text, media metadata, and CDN credentials so downstream
    consumers (WeChatClient subscribers) can work with rich messages.
    Backward-compatible: existing consumers that only read ``text`` work unchanged.
    """

    def _item_dict(item: "MessageItem") -> dict[str, Any]:
        """Serialize a single MessageItem to a dict."""
        d: dict[str, Any] = {
            "type": item.type.value,
            "type_name": item.type.name,
            "msg_id": item.msg_id,
            "create_time_ms": item.create_time_ms,
        }
        if item.text_item:
            d["text"] = item.text_item.text
        if item.image_item:
            img = item.image_item
            d["image"] = {"url": img.url, "aeskey": img.aeskey}
            if img.media:
                d["image"]["media"] = {
                    "encrypt_query_param": img.media.encrypt_query_param,
                    "aes_key": img.media.aes_key,
                    "encrypt_type": img.media.encrypt_type,
                }
            if img.thumb_media:
                d["image"]["thumb_media"] = {
                    "encrypt_query_param": img.thumb_media.encrypt_query_param,
                    "aes_key": img.thumb_media.aes_key,
                    "encrypt_type": img.thumb_media.encrypt_type,
                }
        if item.voice_item:
            v = item.voice_item
            d["voice"] = {
                "text": v.text,
                "encode_type": v.encode_type,
                "sample_rate": v.sample_rate,
                "playtime": v.playtime,
            }
            if v.media:
                d["voice"]["media"] = {
                    "encrypt_query_param": v.media.encrypt_query_param,
                    "aes_key": v.media.aes_key,
                    "encrypt_type": v.media.encrypt_type,
                }
        if item.file_item:
            f = item.file_item
            d["file"] = {"file_name": f.file_name, "md5": f.md5, "len": f.len}
            if f.media:
                d["file"]["media"] = {
                    "encrypt_query_param": f.media.encrypt_query_param,
                    "aes_key": f.media.aes_key,
                    "encrypt_type": f.media.encrypt_type,
                }
        if item.video_item:
            vid = item.video_item
            d["video"] = {
                "video_size": vid.video_size,
                "play_length": vid.play_length,
                "video_md5": vid.video_md5,
            }
            if vid.media:
                d["video"]["media"] = {
                    "encrypt_query_param": vid.media.encrypt_query_param,
                    "aes_key": vid.media.aes_key,
                    "encrypt_type": vid.media.encrypt_type,
                }
            if vid.thumb_media:
                d["video"]["thumb_media"] = {
                    "encrypt_query_param": vid.thumb_media.encrypt_query_param,
                    "aes_key": vid.thumb_media.aes_key,
                    "encrypt_type": vid.thumb_media.encrypt_type,
                }
        return d

    media_type = msg.get_media_type()
    return {
        # ── backward-compatible fields ──
        "from_user_id": msg.from_user_id,
        "text": msg.get_text(),
        "message_id": msg.message_id,
        "timestamp": msg.create_time_ms,
        # ── new fields ──
        "session_id": msg.session_id,
        "message_type": msg.message_type.name,
        "message_state": msg.message_state.name,
        "context_token": msg.context_token or None,
        "has_media": msg.has_media(),
        "media_type": media_type.name if media_type else None,
        "items": [_item_dict(item) for item in msg.item_list],
    }


@dataclass
class ServiceStatus:
    """服务状态"""

    connected: bool = False
    need_login: bool = False
    last_error: str = ""
    reconnect_count: int = 0
    message_sent: int = 0
    message_failed: int = 0


class BackupNotifier:
    """备份通知器 - 当微信失联时通过邮件通知用户"""

    def __init__(self):
        self.email_enabled = bool(os.getenv("BACKUP_EMAIL_TO"))
        self.email_from = os.getenv("BACKUP_EMAIL_FROM", "")
        self.email_to = os.getenv("BACKUP_EMAIL_TO", "")
        self.email_smtp = os.getenv("BACKUP_EMAIL_SMTP", "smtp.gmail.com")
        self.email_port = int(os.getenv("BACKUP_EMAIL_PORT", "587"))
        self.email_user = os.getenv("BACKUP_EMAIL_USER", "")
        self.email_password = os.getenv("BACKUP_EMAIL_PASSWORD", "")

    async def notify(self, subject: str, message: str) -> bool:
        """发送备份通知"""
        if not self.email_enabled:
            return False

        try:
            await self._send_email(subject, message)
            logger.info(f"📧 备份邮件已发送: {subject}")
            return True
        except Exception as e:
            logger.error(f"发送备份邮件失败: {e}")
            return False

    async def send_message_backup(
        self, text: str, source: str, timestamp: str | None = None
    ) -> bool:
        """发送消息备份邮件（高优先级消息无法发送微信时使用）

        Args:
            text: 消息内容
            source: 消息来源程序
            timestamp: 消息时间戳

        Returns:
            是否发送成功
        """
        if not self.email_enabled:
            return False

        subject = f"🚨 [高优先级消息备份] {source}"
        message = f"""微信服务离线，高优先级消息已通过邮件备份发送。

来源程序: {source}
时间: {timestamp or datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

消息内容:
{text}

---
此消息将在微信服务恢复后自动重发。"""

        try:
            await self._send_email(subject, message)
            logger.info(f"📧 消息备份邮件已发送: {text[:30]}...")
            return True
        except Exception as e:
            logger.error(f"发送消息备份邮件失败: {e}")
            return False

    async def _send_email(self, subject: str, message: str) -> None:
        """发送邮件通知

        根据端口自动选择连接方式：
        - 465 端口：使用 SMTP_SSL（直接 SSL 连接）
        - 587 或其他端口：使用 SMTP + STARTTLS
        """
        loop = asyncio.get_event_loop()

        def send():
            msg = MIMEText(message, "plain", "utf-8")
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

        await loop.run_in_executor(None, send)


class WeChatService:
    """微信消息服务 - 独立进程运行，处理微信消息收发"""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        max_reconnect: int = 10,
        reconnect_delay: float = 5.0,
    ):
        if redis_url != "redis://localhost:6379":
            self.redis = redis.from_url(redis_url)
        else:
            self.redis = redis.Redis(host=redis_host, port=redis_port, db=redis_db)
        self.bot = WeChatBot.from_env()
        self._running = False
        self._status = ServiceStatus()
        self._max_reconnect = max_reconnect
        self._reconnect_delay = reconnect_delay
        self._backup_notifier = BackupNotifier()
        self._on_ready_callback: Callable[[], Any] | None = None

    async def run(self) -> None:
        """启动服务（带自动重连）"""
        logger.info("🚀 微信消息服务启动中...")

        self._setup_handlers()

        reconnect_count = 0
        while reconnect_count < self._max_reconnect:
            try:
                await self._run_once()
                reconnect_count = 0
            except WeChatError as e:
                self._status.connected = False
                self._status.last_error = str(e)

                if "login" in str(e).lower() or "token" in str(e).lower() or "auth" in str(e).lower():
                    self._status.need_login = True
                    await self._handle_login_expired()
                    break
                else:
                    reconnect_count += 1
                    self._status.reconnect_count = reconnect_count
                    logger.warning(f"⚠️ 连接断开 ({reconnect_count}/{self._max_reconnect}): {e}")
                    await asyncio.sleep(self._reconnect_delay * reconnect_count)

            except Exception as e:
                self._status.connected = False
                self._status.last_error = str(e)
                reconnect_count += 1
                self._status.reconnect_count = reconnect_count
                logger.error(f"❌ 服务异常 ({reconnect_count}/{self._max_reconnect}): {e}")
                await asyncio.sleep(self._reconnect_delay * reconnect_count)

        if reconnect_count >= self._max_reconnect:
            logger.error(f"❌ 重连次数超过上限 ({self._max_reconnect})，服务停止")
            await self._backup_notifier.notify(
                "⚠️ 微信消息服务已停止",
                f"服务重连失败，已停止运行。\n\n最后错误: {self._status.last_error}\n\n请检查服务并重启。",
            )

        await self.bot.notify_stop()
        await self.bot.close()
        await self.redis.close()
        logger.info("🛑 微信消息服务已停止")

    def _setup_handlers(self) -> None:
        """设置消息处理器"""

        @self.bot.on_message
        async def on_message(msg: WeChatMessage):
            await self._handle_incoming_message(msg)

        async def _show_typing(msg: WeChatMessage) -> None:
            """Best-effort typing indicator — silently ignored if unavailable."""
            try:
                await self.bot.send_typing(msg.from_user_id, typing=True)
            except Exception:
                pass  # typing indicator is cosmetic; never fail a command for it

        @self.bot.on_command("help")
        async def cmd_help(msg: WeChatMessage, args: list):
            await _show_typing(msg)
            await self.bot.reply_text(
                msg,
                """🤖 微信消息服务命令：

/help     - 显示帮助
/status   - 显示服务状态
/ping     - 测试连接

💡 此服务为多程序共享，发送消息请使用各量化程序的命令""",
            )

        @self.bot.on_command("status")
        async def cmd_status(msg: WeChatMessage, args: list):
            await _show_typing(msg)
            status_text = f"""📊 服务状态：

微信连接: {'✅ 在线' if self._status.connected else '❌ 离线'}
消息发送: {self._status.message_sent}
发送失败: {self._status.message_failed}
重连次数: {self._status.reconnect_count}
用户ID: {self.bot.get_user_id() or '未绑定'}"""
            if self._status.last_error:
                status_text += f"\n最后错误: {self._status.last_error}"
            await self.bot.reply_text(msg, status_text)

        @self.bot.on_command("ping")
        async def cmd_ping(msg: WeChatMessage, args: list):
            await _show_typing(msg)
            await self.bot.reply_text(msg, "🏓 Pong!")

    async def _run_once(self) -> None:
        """运行一次（直到断开）"""
        sender_task = asyncio.create_task(self._sender_loop())
        health_task = asyncio.create_task(self._health_check_loop())
        pending_task = asyncio.create_task(self._process_pending_messages())
        keepalive_task = asyncio.create_task(self._context_keepalive_loop())

        async def on_ready():
            self._status.connected = True
            self._status.need_login = False
            self._running = True
            logger.info("✅ 微信消息服务已就绪")

            await self._publish_status("online")

            if self.bot.get_user_id():
                try:
                    await self.bot.notify("🤖 微信消息服务已启动")
                except WeChatError as e:
                    logger.warning(f"Startup notification failed (non-fatal): {e}")

            if self._on_ready_callback:
                result = self._on_ready_callback()
                if asyncio.iscoroutine(result):
                    await result

        try:
            await self.bot.run(on_ready=on_ready)
        finally:
            self._running = False
            self._status.connected = False
            for task in [sender_task, health_task, pending_task, keepalive_task]:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            await self._publish_status("offline")

    async def _handle_login_expired(self) -> None:
        """处理登录过期"""
        logger.error("❌ 登录已过期，需要重新扫码")

        await self._publish_status("need_login")

        await self._backup_notifier.notify(
            "⚠️ 微信机器人需要重新登录",
            f"""微信机器人登录已过期，请重新扫码登录。

时间: {datetime.now():%Y-%m-%d %H:%M:%S}
服务器: {os.getenv('SERVER_NAME', 'unknown')}

请在服务器上运行以下命令重新登录：
uv run python -m larky.wechat_service

如有重要消息未发送，将在重新登录后自动重发。""",
        )

        pending_count = await self.redis.llen(QUEUE_PENDING)
        if pending_count > 0:
            logger.info(f"📦 有 {pending_count} 条消息等待重发")

    async def _handle_incoming_message(self, msg: WeChatMessage) -> None:
        """处理收到的微信消息，发布到 Redis

        发布完整的消息元数据（文本、媒体信息、CDN 凭证等），
        下游 WeChatClient 订阅者可以获取富媒体消息的全部上下文。
        """
        if msg.is_command():
            cmd = msg.get_command()
            if cmd and cmd[0] in ("help", "status", "ping"):
                return

        data = _build_incoming_payload(msg)

        try:
            await self.redis.publish(CHANNEL_INCOMING, json.dumps(data, ensure_ascii=False))
            logger.debug(f"📤 发布消息到 {CHANNEL_INCOMING}: {data['text'][:50]}...")
        except Exception as e:
            logger.error(f"发布消息失败: {e}")

    async def _sender_loop(self) -> None:
        """监听 Redis 发送请求，转发到微信"""
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(CHANNEL_OUTGOING)
        logger.info(f"📥 订阅 {CHANNEL_OUTGOING}")

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    if not self._running:
                        continue
                    await self._handle_outgoing_message(message["data"])
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(CHANNEL_OUTGOING)
            await pubsub.aclose()

    async def _handle_outgoing_message(self, data: bytes) -> None:
        """处理发送请求

        优先级处理逻辑：
        - normal（默认）: 离线时消息丢弃
        - high: 离线时消息加入队列 + 并行发送邮件备份，微信恢复后重发

        "prepare failed" 错误处理：
        - context_token 过期时 send_text 内部会清除 token 并重试一次
        - 如果内部重试也失败，说明需要用户发消息来刷新 token
        - 此时将消息移入 failed 队列（而非 pending 队列的快速重试循环）
        - failed 队列的消息只在收到新消息（获得新 token）后才处理
        """
        try:
            payload = json.loads(data)
            text = payload.get("text", "")
            source = payload.get("source", "unknown")
            priority = payload.get("priority", "normal")
            timestamp = payload.get("timestamp", datetime.now().isoformat())

            if not text:
                logger.warning("收到空消息，忽略")
                return

            if not self._status.connected:
                if priority == "high":
                    await self.redis.rpush(QUEUE_PENDING, data)
                    logger.warning(f"📦 离线，高优先级消息已加入待发队列: {text[:30]}...")

                    await self._backup_notifier.send_message_backup(
                        text=text, source=source, timestamp=timestamp
                    )
                else:
                    logger.warning(f"⚠️ 离线，普通消息丢弃: {text[:30]}...")
                return

            await self.bot.notify(text)
            self._status.message_sent += 1
            logger.info(f"📨 发送消息 (来源: {source}, 优先级: {priority}): {text[:50]}...")

        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}")
        except WeChatError as e:
            err_msg = str(e)

            if "prepare failed" in err_msg:
                # send_text already retried once without context_token internally.
                # This error means the token is truly expired and needs user interaction
                # to refresh — fast retries won't help. Move to failed queue.
                logger.warning(
                    f"🔴 context_token 已过期，消息移入失败队列等待用户激活: {text[:30]}..."
                )
                await self.redis.rpush(QUEUE_FAILED, data)
                await self._backup_notifier.send_message_backup(
                    text=text, source=source, timestamp=timestamp
                )
            else:
                self._status.message_failed += 1
                logger.error(f"发送消息失败: {e}")
                payload_bytes = data if isinstance(data, bytes) else data.encode()
                await self.redis.rpush(QUEUE_PENDING, payload_bytes)
                logger.info("📦 消息已加入待发队列")

        except Exception as e:
            self._status.message_failed += 1
            logger.error(f"发送消息失败: {e}")

            payload_bytes = data if isinstance(data, bytes) else data.encode()
            await self.redis.rpush(QUEUE_PENDING, payload_bytes)
            logger.info("📦 消息已加入待发队列")

    async def _health_check_loop(self) -> None:
        """健康检查循环"""
        while self._running:
            await asyncio.sleep(60)
            await self._publish_status("online" if self._status.connected else "offline")

    async def _context_keepalive_loop(self) -> None:
        """定期检查 context_token 是否有效，提前发现过期问题。

        默认每 4 小时探测一次。发现 token 过期时立即发邮件通知，
        而不是等到有消息发不出去才发现。
        """
        interval = int(os.getenv("WECHAT_KEEPALIVE_INTERVAL_SEC", "1800"))
        await asyncio.sleep(60)  # 启动后等 1 分钟再开始检查

        while self._running:
            try:
                if self._status.connected and self.bot.get_user_id():
                    healthy = await self.bot.check_context_health()
                    if not healthy and self.bot._get_context_token(self.bot.get_user_id()) is None:
                        logger.warning("🔴 context_token 已过期，发送邮件通知")
                        await self._backup_notifier.notify(
                            "⚠️ 微信会话已过期，需要手动激活",
                            f"""微信机器人的 context_token 已过期，暂时无法主动推送消息。

时间: {datetime.now():%Y-%m-%d %H:%M:%S}
服务器: {os.getenv('SERVER_NAME', 'unknown')}

请在微信中给机器人发送任意一条消息以恢复推送能力。
消息发送失败的记录会自动排队，恢复后重新发送。""",
                        )
                    else:
                        logger.debug(f"Context token keepalive: {'healthy' if healthy else 'no token yet'}")
            except Exception as e:
                logger.warning(f"Keepalive check failed: {e}")

            await asyncio.sleep(interval)

    async def _process_pending_messages(self) -> None:
        """处理待发送消息队列

        两种处理时机：
        1. 定时（每 30 秒）：只处理 pending 队列（离线重连后积压的消息）
        2. 收到新消息（context_token 刷新）：处理 failed 队列（token 过期导致的消息），
           因为只有新 token 到达才可能发送成功

        失败不会阻塞队列——单条失败会被跳过，其他消息继续处理。
        """
        await asyncio.sleep(5)

        while self._running:
            try:
                if not self._status.connected:
                    await asyncio.sleep(30)
                    continue

                # 每轮只处理 pending 队列（常规积压消息）
                await self._drain_queue(QUEUE_PENDING, "待发")

            except Exception as e:
                logger.error(f"处理待发消息失败: {e}")

            # 等待 30 秒或收到新消息（context_token 刷新）
            # 收到新消息时额外处理 failed 队列
            try:
                await asyncio.wait_for(
                    self.bot.context_token_updated.wait(), timeout=30
                )
                self.bot.context_token_updated.clear()
                logger.debug("收到新消息（context_token 刷新），处理所有待发队列")
                if self._status.connected:
                    await self._drain_queue(QUEUE_PENDING, "待发")
                    await self._drain_queue(QUEUE_FAILED, "失败待重试")
            except asyncio.TimeoutError:
                pass

    async def _drain_queue(self, queue_key: str, label: str) -> None:
        """处理指定队列中的所有消息。

        失败不会阻塞队列：发送失败的消息放回队列末尾，继续处理下一条。
        连续失败超过阈值则停止，避免死循环。
        只处理调用时队列中的消息数，避免因重入队导致的无限循环。
        """
        consecutive_failures = 0
        max_consecutive_failures = 3

        initial_count = await self.redis.llen(queue_key)
        if initial_count == 0:
            return

        logger.info(f"📦 开始处理 {initial_count} 条{label}消息...")
        processed = 0

        while processed < initial_count:
            data = await self.redis.lpop(queue_key)
            if not data:
                break
            processed += 1

            try:
                payload = json.loads(data)
                text = payload.get("text", "")
                source = payload.get("source", "unknown")
                priority = payload.get("priority", "normal")

                await self.bot.notify(text)
                self._status.message_sent += 1
                logger.info(
                    f"📨 重发{label}消息 (来源: {source}, 优先级: {priority}): {text[:50]}..."
                )
                consecutive_failures = 0
                await asyncio.sleep(1)
            except WeChatError as e:
                err_msg = str(e)
                if "prepare failed" in err_msg:
                    # Token still expired — move to failed queue, don't block
                    logger.warning(
                        f"🔴 token 仍过期，{label}消息移入失败队列: {text[:50]}..."
                    )
                    await self.redis.rpush(QUEUE_FAILED, data)
                    consecutive_failures = 0  # Not a real failure
                else:
                    consecutive_failures += 1
                    logger.error(f"{label}消息发送失败 ({consecutive_failures}): {e}")
                    await self.redis.rpush(queue_key, data)
                    if consecutive_failures >= max_consecutive_failures:
                        logger.error(
                            f"❌ {label}队列连续 {max_consecutive_failures} 次失败，暂停处理"
                        )
                        break
            except Exception as e:
                consecutive_failures += 1
                logger.error(f"{label}消息发送失败 ({consecutive_failures}): {e}")
                await self.redis.rpush(queue_key, data)
                if consecutive_failures >= max_consecutive_failures:
                    logger.error(
                        f"❌ {label}队列连续 {max_consecutive_failures} 次失败，暂停处理"
                    )
                    break

    async def _publish_status(self, status: str) -> None:
        """发布服务状态"""
        data = {
            "status": status,
            "connected": self._status.connected,
            "need_login": self._status.need_login,
            "timestamp": datetime.now().isoformat(),
            "message_sent": self._status.message_sent,
            "message_failed": self._status.message_failed,
        }
        await self.redis.publish(CHANNEL_STATUS, json.dumps(data))

    def on_ready(self, callback: Callable[[], Any]) -> None:
        """设置就绪回调"""
        self._on_ready_callback = callback


class WeChatClient:
    """微信客户端 - 量化程序使用此类发送/接收消息"""

    def __init__(
        self,
        source: str = "default",
        redis_url: str = "redis://localhost:6379",
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
    ):
        self.source = source
        if redis_url != "redis://localhost:6379":
            self.redis = redis.from_url(redis_url)
        else:
            self.redis = redis.Redis(host=redis_host, port=redis_port, db=redis_db)
        self._handlers: list[Callable[[dict[str, Any]], Any]] = []
        self._status_handlers: list[Callable[[dict[str, Any]], Any]] = []
        self._running = False

    async def notify(self, text: str, priority: str = "normal") -> None:
        """发送微信通知

        Args:
            text: 消息内容
            priority: 优先级 "normal" 或 "high"
                     "normal"（默认）- 离线时消息丢弃
                     "high" - 离线时消息保存到队列并邮件备份，恢复后重发
        """
        payload = {
            "text": text,
            "source": self.source,
            "priority": priority,
            "timestamp": datetime.now().isoformat(),
        }
        await self.redis.publish(CHANNEL_OUTGOING, json.dumps(payload, ensure_ascii=False))
        logger.debug(f"📤 发送通知请求 (优先级: {priority}): {text[:50]}...")

    async def on_message(self, handler: Callable[[dict[str, Any]], Any]) -> None:
        """注册消息处理器"""
        self._handlers.append(handler)

    def message_handler(self, func: Callable[[dict[str, Any]], Any]) -> Callable[[dict[str, Any]], Any]:
        """装饰器方式注册消息处理器"""
        self._handlers.append(func)
        return func

    async def on_status(self, handler: Callable[[dict[str, Any]], Any]) -> None:
        """注册状态处理器"""
        self._status_handlers.append(handler)

    def status_handler(self, func: Callable[[dict[str, Any]], Any]) -> Callable[[dict[str, Any]], Any]:
        """装饰器方式注册状态处理器"""
        self._status_handlers.append(func)
        return func

    async def run(self) -> None:
        """启动客户端，监听微信消息"""
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(CHANNEL_INCOMING, CHANNEL_STATUS)
        logger.info(f"📥 {self.source} 订阅 {CHANNEL_INCOMING} 和 {CHANNEL_STATUS}")
        self._running = True

        try:
            async for message in pubsub.listen():
                if not self._running:
                    break
                if message["type"] == "message":
                    channel = message["channel"]
                    if isinstance(channel, bytes):
                        channel = channel.decode()

                    if channel == CHANNEL_INCOMING:
                        await self._dispatch_message(message["data"], self._handlers)
                    elif channel == CHANNEL_STATUS:
                        await self._dispatch_message(message["data"], self._status_handlers)
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            await pubsub.unsubscribe(CHANNEL_INCOMING, CHANNEL_STATUS)
            await pubsub.close()
            await self.redis.close()

    async def _dispatch_message(self, data: bytes, handlers: list) -> None:
        """分发消息给所有处理器"""
        try:
            payload = json.loads(data)
            for handler in handlers:
                try:
                    result = handler(payload)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error(f"消息处理器执行失败: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}")

    def stop(self) -> None:
        """停止客户端"""
        self._running = False


async def run_service() -> None:
    """运行微信消息服务（入口点）"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    redis_url = os.getenv("REDIS_URL", f"redis://{redis_host}:{redis_port}")

    service = WeChatService(redis_url=redis_url)
    await service.run()


if __name__ == "__main__":
    asyncio.run(run_service())
