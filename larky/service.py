"""统一消息服务 — 独立进程运行，通过 Redis Pub/Sub 与其他程序通信

支持所有平台（飞书/微信/QQ），通过 BOT_PLATFORM 环境变量选择。

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
                   │UnifiedService │ ← 唯一平台连接（飞书/微信/QQ）
                   └───────────────┘

使用方法：
    # 终端1：启动统一消息服务
    BOT_PLATFORM=feishu uv run python -m larky
    BOT_PLATFORM=wechat uv run python -m larky
    BOT_PLATFORM=qq     uv run python -m larky

    # 终端2+：量化程序使用 UnifiedClient 发送/接收消息

消息优先级：
    - normal（默认）: 普通优先级，离线时消息丢弃
    - high: 高优先级，离线时消息保存到队列并通过邮件备份发送，
            服务恢复后自动重发

故障处理：
    - 掉线自动重连（指数退避）
    - Token 过期时通过邮件通知（微信）/ 自动重试（飞书/QQ）
    - 高优先级消息队列持久化，恢复后重发
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from ._email import EmailNotifier as BackupNotifier  # re-export under existing name

try:
    import redis.asyncio as redis
except ImportError:
    raise ImportError("请安装 redis: uv add redis")

from dotenv import load_dotenv

from .unified import UnifiedBot, UnifiedMessage

load_dotenv()

logger = logging.getLogger(__name__)

# Redis 频道名（可配置前缀）
DEFAULT_PREFIX = "bot"


def _channel(prefix: str, name: str) -> str:
    return f"{prefix}:{name}"


# ------------------------------------------------------------------
# 入站消息序列化
# ------------------------------------------------------------------


def _build_incoming_payload(msg: UnifiedMessage) -> dict[str, Any]:
    """将 UnifiedMessage 转换为 Redis 发布载荷。

    生成平台无关的基础字段。平台特有数据可通过 msg.raw_data 获取。
    """
    return {
        "text": msg.get_text(),
        "sender_id": msg.sender_id,
        "sender_name": msg.sender_name,
        "message_id": msg.message_id,
        "chat_id": msg.chat_id,
        "platform": msg.platform,
        "msg_type": msg.msg_type,
        "timestamp": msg.create_time,
    }


# ------------------------------------------------------------------
# 服务状态
# ------------------------------------------------------------------


@dataclass
class ServiceStatus:
    """服务状态"""

    connected: bool = False
    need_login: bool = False
    last_error: str = ""
    reconnect_count: int = 0
    message_sent: int = 0
    message_failed: int = 0


# ------------------------------------------------------------------
# BackupNotifier 从 ._email 导入 (EmailNotifier) — 见文件顶部 import


# ------------------------------------------------------------------
# 统一消息服务
# ------------------------------------------------------------------


class UnifiedService:
    """统一消息服务 — 独立进程运行，管理各平台的消息收发。

    包装 UnifiedBot，通过 Redis Pub/Sub 与多个量化程序共享
    同一条平台连接。

    用法::

        service = UnifiedService()  # BOT_PLATFORM 从 .env 读取
        await service.run()
    """

    def __init__(
        self,
        platform: str | None = None,
        redis_url: str = "",
        redis_host: str = "",
        redis_port: int = 0,
        redis_db: int = 0,
        channel_prefix: str = "",
        max_reconnect: int = 10,
        reconnect_delay: float = 5.0,
    ):
        # 平台
        self._platform = platform

        # Redis
        redis_url = redis_url or os.getenv("REDIS_URL", "")
        redis_host = redis_host or os.getenv("REDIS_HOST", "localhost")
        redis_port = redis_port or int(os.getenv("REDIS_PORT", "6379"))
        if redis_url and redis_url != "redis://localhost:6379":
            self.redis = redis.from_url(redis_url)
        else:
            self.redis = redis.Redis(host=redis_host, port=redis_port, db=redis_db)

        # 频道前缀
        self._prefix = channel_prefix or os.getenv("BOT_SERVICE_PREFIX", DEFAULT_PREFIX)

        # Bot（延迟创建，因为平台配置可能依赖环境变量）
        self.bot: UnifiedBot | None = None

        # 状态
        self._running = False
        self._stop_requested = False
        self._status = ServiceStatus()
        self._max_reconnect = max_reconnect
        self._reconnect_delay = reconnect_delay
        self._backup_notifier = BackupNotifier()
        self._on_ready_callback: Callable[[], Any] | None = None

    # ------------------------------------------------------------------
    # 频道名快捷方法
    # ------------------------------------------------------------------

    @property
    def _CH_INCOMING(self) -> str:
        return _channel(self._prefix, "incoming")

    @property
    def _CH_OUTGOING(self) -> str:
        return _channel(self._prefix, "outgoing")

    @property
    def _CH_STATUS(self) -> str:
        return _channel(self._prefix, "status")

    @property
    def _Q_PENDING(self) -> str:
        return _channel(self._prefix, "pending_messages")

    @property
    def _Q_FAILED(self) -> str:
        return _channel(self._prefix, "failed_messages")

    # ------------------------------------------------------------------
    # 运行
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """启动服务（带自动重连）。"""
        logger.info("🚀 统一消息服务启动中 [platform=%s]...",
                     self._platform or os.getenv("BOT_PLATFORM", "feishu"))

        self.bot = UnifiedBot(platform=self._platform)
        self._setup_handlers()

        reconnect_count = 0
        while reconnect_count < self._max_reconnect and not self._stop_requested:
            try:
                await self._run_once()
                reconnect_count = 0  # 正常退出
            except Exception as e:
                self._status.connected = False
                self._status.last_error = str(e)

                if self._is_auth_error(e):
                    self._status.need_login = True
                    await self._handle_auth_expired()
                    break
                else:
                    reconnect_count += 1
                    self._status.reconnect_count = reconnect_count
                    delay = min(self._reconnect_delay * (2 ** (reconnect_count - 1)), 300)
                    logger.warning(
                        "⚠️ 连接断开 (%d/%d)，%ds 后重连: %s",
                        reconnect_count, self._max_reconnect, delay, e,
                    )
                    await asyncio.sleep(delay)

        if reconnect_count >= self._max_reconnect:
            logger.error("❌ 重连次数超过上限 (%d)，服务停止", self._max_reconnect)
            await self._backup_notifier.send(
                "⚠️ 消息服务已停止",
                f"服务重连失败，已停止运行。\n\n"
                f"平台: {self.bot.platform}\n"
                f"最后错误: {self._status.last_error}\n\n"
                f"请检查服务并重启。",
            )

        await self.bot.close()
        await self.redis.close()
        logger.info("🛑 统一消息服务已停止")

    async def _run_once(self) -> None:
        """运行一次（直到断开）。"""
        sender_task = asyncio.create_task(self._sender_loop())
        health_task = asyncio.create_task(self._health_check_loop())
        pending_task = asyncio.create_task(self._process_pending_messages())

        tasks = [sender_task, health_task, pending_task]

        if self.bot.platform == "wechat":
            keepalive_task = asyncio.create_task(self._context_keepalive_loop())
            tasks.append(keepalive_task)

        async def on_ready(bot: UnifiedBot):
            self._status.connected = True
            self._status.need_login = False
            self._running = True
            logger.info("✅ 消息服务已就绪 [platform=%s]", bot.platform)

            await self._publish_status("online")

            # 启动通知
            try:
                await bot.send_text("🤖 消息服务已启动")
            except Exception as e:
                logger.warning("启动通知发送失败 (non-fatal): %s", e)

            if self._on_ready_callback:
                result = self._on_ready_callback()
                if asyncio.iscoroutine(result):
                    await result

        try:
            await self.bot.run(on_ready=on_ready)
        finally:
            self._running = False
            self._status.connected = False
            for task in tasks:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            await self._publish_status("offline")

    # ------------------------------------------------------------------
    # 消息处理注册
    # ------------------------------------------------------------------

    def _setup_handlers(self) -> None:
        """注册服务内置消息处理器。"""

        @self.bot.on_message
        async def on_message(msg: UnifiedMessage):
            await self._handle_incoming_message(msg)

        @self.bot.on_command("help")
        async def cmd_help(msg: UnifiedMessage, args: list):
            platform_names = {
                "feishu": "飞书", "wechat": "微信", "qq": "QQ",
            }
            pname = platform_names.get(self.bot.platform, self.bot.platform)
            await msg.reply(
                f"🤖 消息服务命令 [{pname}]：\n\n"
                "/help     - 显示帮助\n"
                "/status   - 显示服务状态\n"
                "/ping     - 测试连接\n\n"
                "💡 此服务为多程序共享，发送消息请使用各量化程序的命令"
            )

        @self.bot.on_command("status")
        async def cmd_status(msg: UnifiedMessage, args: list):
            status_text = (
                f"📊 服务状态：\n\n"
                f"平台: {self.bot.platform}\n"
                f"连接: {'✅ 在线' if self._status.connected else '❌ 离线'}\n"
                f"消息发送: {self._status.message_sent}\n"
                f"发送失败: {self._status.message_failed}\n"
                f"重连次数: {self._status.reconnect_count}"
            )
            if self._status.last_error:
                status_text += f"\n最后错误: {self._status.last_error}"
            await msg.reply(status_text)

        @self.bot.on_command("ping")
        async def cmd_ping(msg: UnifiedMessage, args: list):
            await msg.reply("🏓 Pong!")

    # ------------------------------------------------------------------
    # 入站消息处理
    # ------------------------------------------------------------------

    async def _handle_incoming_message(self, msg: UnifiedMessage) -> None:
        """处理收到的平台消息，发布到 Redis。"""
        # 内置命令不发布到 Redis
        if msg.is_command("/"):
            cmd = msg.get_command("/")
            if cmd and cmd[0] in ("help", "status", "ping"):
                return

        data = _build_incoming_payload(msg)

        try:
            await self.redis.publish(
                self._CH_INCOMING, json.dumps(data, ensure_ascii=False)
            )
            logger.debug("📤 发布消息到 %s: %s", self._CH_INCOMING, data["text"][:50])
        except Exception as e:
            logger.error("发布消息失败: %s", e)

    # ------------------------------------------------------------------
    # 发送消息处理
    # ------------------------------------------------------------------

    async def _sender_loop(self) -> None:
        """监听 Redis 发送请求，转发到平台。"""
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(self._CH_OUTGOING)
        logger.info("📥 订阅 %s", self._CH_OUTGOING)

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    if not self._running:
                        continue
                    await self._handle_outgoing_message(message["data"])
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(self._CH_OUTGOING)
            await pubsub.aclose()

    async def _handle_outgoing_message(self, data: bytes) -> None:
        """处理发送请求。

        优先级逻辑（所有平台通用）:
        - normal: 离线时消息丢弃
        - high: 离线时消息入队 + 邮件备份，恢复后重发

        平台特定错误处理:
        - 微信 prepare failed → 移入 failed 队列（需用户发消息激活）
        - 其他错误 → 移入 pending 队列重试
        """
        try:
            payload = json.loads(data)
        except json.JSONDecodeError as e:
            logger.error("JSON 解析失败: %s", e)
            return

        text = payload.get("text", "")
        source = payload.get("source", "unknown")
        priority = payload.get("priority", "normal")
        timestamp = payload.get("timestamp", datetime.now().isoformat())
        target_id = payload.get("target_id")

        if not text:
            logger.warning("收到空消息，忽略")
            return

        # ── 离线处理 ──
        if not self._status.connected:
            if priority == "high":
                await self.redis.rpush(self._Q_PENDING, data)
                logger.warning("📦 离线，高优先级消息已入队: %s", text[:30])
                await self._backup_notifier.send_message_backup(
                    text=text, source=source, timestamp=timestamp
                )
            else:
                logger.warning("⚠️ 离线，普通消息丢弃: %s", text[:30])
            return

        # ── 在线发送 ──
        try:
            await self.bot.send_text(text, target_id=target_id)
            self._status.message_sent += 1
            logger.info("📨 发送消息 (来源: %s, 优先级: %s): %s",
                         source, priority, text[:50])
        except Exception as e:
            err_msg = str(e).lower()

            if "prepare failed" in err_msg and self.bot.platform == "wechat":
                # 微信 context_token 过期 — 需用户交互刷新，快速重试无意义
                logger.warning("🔴 context_token 过期，消息移入失败队列: %s", text[:30])
                await self.redis.rpush(self._Q_FAILED, data)
                await self._backup_notifier.send_message_backup(
                    text=text, source=source, timestamp=timestamp
                )
            else:
                self._status.message_failed += 1
                logger.error("发送消息失败: %s", e)
                # 所有平台：入 pending 队列重试
                await self.redis.rpush(self._Q_PENDING, data)
                logger.info("📦 消息已加入待发队列")

    # ------------------------------------------------------------------
    # 健康检查
    # ------------------------------------------------------------------

    async def _health_check_loop(self) -> None:
        """定期发布服务状态。"""
        while self._running:
            await asyncio.sleep(60)
            await self._publish_status(
                "online" if self._status.connected else "offline"
            )

    async def _context_keepalive_loop(self) -> None:
        """微信专属：定期检查 context_token 有效性。

        飞书和 QQ 的 token 自动刷新，无需此逻辑。
        """
        if self.bot.platform != "wechat":
            return

        interval = int(os.getenv("WECHAT_KEEPALIVE_INTERVAL_SEC", "1800"))
        await asyncio.sleep(60)  # 启动后等 1 分钟

        while self._running:
            try:
                wechat_bot = self.bot._bot
                if (
                    self._status.connected
                    and hasattr(wechat_bot, "get_user_id")
                    and wechat_bot.get_user_id()
                ):
                    healthy = await wechat_bot.check_context_health()
                    ctx_token = wechat_bot._get_context_token(wechat_bot.get_user_id())
                    if not healthy and ctx_token is not None:
                        # Token exists but is expired — notify the user.
                        logger.warning("🔴 context_token 已过期，发送邮件通知")
                        await self._backup_notifier.send(
                            "⚠️ 微信会话已过期，需要手动激活",
                            f"""微信机器人的 context_token 已过期，暂时无法主动推送消息。

时间: {datetime.now():%Y-%m-%d %H:%M:%S}
服务器: {os.getenv('SERVER_NAME', 'unknown')}

请在微信中给机器人发送任意一条消息以恢复推送能力。
消息发送失败的记录会自动排队，恢复后重新发送。""",
                        )
                    else:
                        logger.debug(
                            "Context token keepalive: %s",
                            "healthy" if healthy else "no token yet",
                        )
            except Exception as e:
                logger.warning("Keepalive check failed: %s", e)

            await asyncio.sleep(interval)

    # ------------------------------------------------------------------
    # 待发/失败队列处理
    # ------------------------------------------------------------------

    async def _process_pending_messages(self) -> None:
        """处理待发送消息队列。

        两种处理时机：
        1. 定时（30s）：处理 pending 队列（离线重连后积压的消息）
        2. 收到新消息（仅微信）：处理 failed 队列
           （context_token 刷新后才能发送成功）
        """
        await asyncio.sleep(5)

        while self._running:
            try:
                if not self._status.connected:
                    await asyncio.sleep(30)
                    continue

                await self._drain_queue(self._Q_PENDING, "待发")

            except Exception as e:
                logger.error("处理待发消息失败: %s", e)

            # 等待 30 秒或新消息到达（仅微信有 context_token_updated 事件）
            if self.bot.platform == "wechat":
                wechat_bot = self.bot._bot
                if hasattr(wechat_bot, "context_token_updated"):
                    try:
                        await asyncio.wait_for(
                            wechat_bot.context_token_updated.wait(), timeout=30,
                        )
                        wechat_bot.context_token_updated.clear()
                        logger.debug("收到新消息，处理所有待发/失败队列")
                        if self._status.connected:
                            await self._drain_queue(self._Q_PENDING, "待发")
                            await self._drain_queue(self._Q_FAILED, "失败待重试")
                    except asyncio.TimeoutError:
                        pass
                else:
                    await asyncio.sleep(30)
            else:
                await asyncio.sleep(30)

    async def _drain_queue(self, queue_key: str, label: str) -> None:
        """处理指定队列中的所有消息。

        失败不阻塞队列 — 单条失败跳过，继续处理下一条。
        连续失败超过阈值则停止。
        只处理调用时队列中已有的消息，避免因重入队导致的无限循环。
        """
        consecutive_failures = 0
        max_consecutive_failures = 3

        initial_count = await self.redis.llen(queue_key)
        if initial_count == 0:
            return

        logger.info("📦 开始处理 %d 条%s消息...", initial_count, label)
        processed = 0

        while processed < initial_count:
            data = await self.redis.lpop(queue_key)
            if not data:
                break
            processed += 1

            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                logger.error("❌ %s队列中消息 JSON 损坏，已丢弃", label)
                continue

            text = payload.get("text", "")
            source = payload.get("source", "unknown")
            priority = payload.get("priority", "normal")
            target_id = payload.get("target_id")

            try:
                await self.bot.send_text(text, target_id=target_id)
                self._status.message_sent += 1
                logger.info(
                    "📨 重发%s消息 (来源: %s, 优先级: %s): %s",
                    label, source, priority, text[:50],
                )
                consecutive_failures = 0
                await asyncio.sleep(1)
            except Exception as e:
                err_msg = str(e).lower()
                if "prepare failed" in err_msg and self.bot.platform == "wechat":
                    logger.warning("🔴 token 仍过期，%s消息移入失败队列: %s",
                                   label, text[:50])
                    await self.redis.rpush(self._Q_FAILED, data)
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    logger.error("%s消息发送失败 (%d): %s", label, consecutive_failures, e)
                    await self.redis.rpush(queue_key, data)
                    if consecutive_failures >= max_consecutive_failures:
                        logger.error(
                            "❌ %s队列连续 %d 次失败，暂停处理",
                            label, max_consecutive_failures,
                        )
                        break

    # ------------------------------------------------------------------
    # 认证错误处理
    # ------------------------------------------------------------------

    @staticmethod
    def _is_auth_error(error: Exception) -> bool:
        """判断是否为认证/登录相关错误。"""
        msg = str(error).lower()
        return any(kw in msg for kw in ("login", "token", "auth", "session expired"))

    async def _handle_auth_expired(self) -> None:
        """处理认证过期。"""
        logger.error("❌ 认证已过期 [platform=%s]", self.bot.platform)

        await self._publish_status("need_login")

        platform_names = {"feishu": "飞书", "wechat": "微信", "qq": "QQ"}
        pname = platform_names.get(self.bot.platform, self.bot.platform)

        if self.bot.platform == "wechat":
            await self._backup_notifier.send(
                f"⚠️ {pname}机器人需要重新登录",
                f"""{pname}机器人登录已过期，请重新扫码登录。

时间: {datetime.now():%Y-%m-%d %H:%M:%S}
服务器: {os.getenv('SERVER_NAME', 'unknown')}

请在服务器上运行以下命令重新登录：
BOT_PLATFORM=wechat uv run python -m larky

如有重要消息未发送，将在重新登录后自动重发。""",
            )
        else:
            await self._backup_notifier.send(
                f"⚠️ {pname}服务认证失败",
                f"""{pname}服务认证失败，请检查配置。

时间: {datetime.now():%Y-%m-%d %H:%M:%S}
服务器: {os.getenv('SERVER_NAME', 'unknown')}
错误: {self._status.last_error}

请检查 .env 中的 APP_ID / APP_SECRET 配置是否正确。""",
            )

        pending_count = await self.redis.llen(self._Q_PENDING)
        if pending_count > 0:
            logger.info("📦 有 %d 条消息等待重发", pending_count)

    # ------------------------------------------------------------------
    # 状态发布
    # ------------------------------------------------------------------

    async def _publish_status(self, status: str) -> None:
        """发布服务状态到 Redis。"""
        data = {
            "status": status,
            "connected": self._status.connected,
            "need_login": self._status.need_login,
            "platform": self.bot.platform if self.bot else "unknown",
            "timestamp": datetime.now().isoformat(),
            "message_sent": self._status.message_sent,
            "message_failed": self._status.message_failed,
        }
        try:
            await self.redis.publish(
                self._CH_STATUS, json.dumps(data, ensure_ascii=False)
            )
        except Exception as e:
            logger.debug("发布状态失败: %s", e)

    # ------------------------------------------------------------------
    # 回调
    # ------------------------------------------------------------------

    def on_ready(self, callback: Callable[[], Any]) -> None:
        """设置就绪回调。"""
        self._on_ready_callback = callback

    def stop(self) -> None:
        """请求停止服务（优雅退出）。"""
        self._stop_requested = True
        self._running = False
        if self.bot:
            self.bot.stop()


# ------------------------------------------------------------------
# 统一客户端
# ------------------------------------------------------------------


class UnifiedClient:
    """统一消息客户端 — 量化程序使用此类发送/接收消息。

    支持所有平台（由 UnifiedService 的 BOT_PLATFORM 决定）。

    用法::

        client = UnifiedClient(source="btc-monitor")

        @client.message_handler
        async def on_message(data: dict):
            text = data.get("text", "")
            if "price" in text:
                await client.notify(f"Price: ${get_price()}")

        @client.status_handler
        async def on_status(data: dict):
            if data.get("need_login"):
                logger.warning("Service needs re-auth")

        await client.run()
    """

    def __init__(
        self,
        source: str = "default",
        redis_url: str = "",
        redis_host: str = "",
        redis_port: int = 0,
        redis_db: int = 0,
        channel_prefix: str = "",
    ):
        self.source = source

        redis_url = redis_url or os.getenv("REDIS_URL", "")
        redis_host = redis_host or os.getenv("REDIS_HOST", "localhost")
        redis_port = redis_port or int(os.getenv("REDIS_PORT", "6379"))

        if redis_url and redis_url != "redis://localhost:6379":
            self.redis = redis.from_url(redis_url)
        else:
            self.redis = redis.Redis(host=redis_host, port=redis_port, db=redis_db)

        self._prefix = channel_prefix or os.getenv("BOT_SERVICE_PREFIX", DEFAULT_PREFIX)
        self._handlers: list[Callable[[dict[str, Any]], Any]] = []
        self._status_handlers: list[Callable[[dict[str, Any]], Any]] = []
        self._running = False

    # ------------------------------------------------------------------
    # 频道名
    # ------------------------------------------------------------------

    @property
    def _CH_INCOMING(self) -> str:
        return _channel(self._prefix, "incoming")

    @property
    def _CH_OUTGOING(self) -> str:
        return _channel(self._prefix, "outgoing")

    @property
    def _CH_STATUS(self) -> str:
        return _channel(self._prefix, "status")

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    async def notify(self, text: str, priority: str = "normal",
                     target_id: str | None = None) -> None:
        """发送通知。

        Args:
            text: 消息内容。
            priority: "normal"（默认，离线丢弃）或 "high"（离线入队+邮件备份）。
            target_id: 目标用户标识（可选，各平台含义不同）。
        """
        payload = {
            "text": text,
            "source": self.source,
            "priority": priority,
            "target_id": target_id,
            "timestamp": datetime.now().isoformat(),
        }
        await self.redis.publish(
            self._CH_OUTGOING, json.dumps(payload, ensure_ascii=False)
        )
        logger.debug("📤 发送通知 (优先级: %s): %s", priority, text[:50])

    def message_handler(
        self, func: Callable[[dict[str, Any]], Any]
    ) -> Callable[[dict[str, Any]], Any]:
        """装饰器：注册消息处理器。"""
        self._handlers.append(func)
        return func

    def status_handler(
        self, func: Callable[[dict[str, Any]], Any]
    ) -> Callable[[dict[str, Any]], Any]:
        """装饰器：注册状态处理器。"""
        self._status_handlers.append(func)
        return func

    async def run(self) -> None:
        """启动客户端，监听消息和状态。"""
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(self._CH_INCOMING, self._CH_STATUS)
        logger.info("📥 %s 订阅 %s 和 %s",
                     self.source, self._CH_INCOMING, self._CH_STATUS)
        self._running = True

        try:
            async for message in pubsub.listen():
                if not self._running:
                    break
                if message["type"] == "message":
                    channel = message["channel"]
                    if isinstance(channel, bytes):
                        channel = channel.decode()

                    if channel == self._CH_INCOMING:
                        await self._dispatch(message["data"], self._handlers)
                    elif channel == self._CH_STATUS:
                        await self._dispatch(message["data"], self._status_handlers)
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            await pubsub.unsubscribe(self._CH_INCOMING, self._CH_STATUS)
            await pubsub.close()
            await self.redis.close()

    async def _dispatch(
        self, data: bytes, handlers: list[Callable[[dict[str, Any]], Any]]
    ) -> None:
        """分发消息给所有处理器。"""
        try:
            payload = json.loads(data)
        except json.JSONDecodeError as e:
            logger.error("JSON 解析失败: %s", e)
            return

        for handler in handlers:
            try:
                result = handler(payload)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error("消息处理器执行失败: %s", e)

    def stop(self) -> None:
        """停止客户端。"""
        self._running = False


# ------------------------------------------------------------------
