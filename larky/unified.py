"""统一机器人 API

通过 BOT_PLATFORM 环境变量控制底层使用飞书、微信还是 QQ，
用户代码无需关心底层差异。

用法:
    from larky import UnifiedBot, UnifiedMessage

    bot = UnifiedBot()  # 从 BOT_PLATFORM 环境变量读取平台

    @bot.on_message
    async def handle(msg: UnifiedMessage):
        await msg.reply(f"收到: {msg.get_text()}")

    @bot.on_command("help")
    async def cmd_help(msg: UnifiedMessage, args: list):
        await msg.reply("帮助信息...")

    await bot.run()
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

logger = logging.getLogger(__name__)

PlatformType = Literal["feishu", "wechat", "qq"]
VALID_PLATFORMS = ("feishu", "wechat", "qq")


@dataclass
class UnifiedMessage:
    """跨平台统一消息类型。

    封装飞书、微信、QQ 三种平台的消息，提供一致的字段访问。
    """

    message_id: str
    chat_id: str
    sender_id: str
    content: str
    platform: str
    sender_name: str = ""
    msg_type: str = "text"
    create_time: int | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)

    # 内部引用（用户不应直接访问）
    _platform_message: Any = field(default=None, repr=False)
    _bot: "UnifiedBot | None" = field(default=None, repr=False)

    def get_text(self) -> str:
        """获取消息纯文本内容。"""
        return self.content

    def is_command(self, prefix: str = "/") -> bool:
        """判断是否为指令消息。"""
        return self.content.strip().startswith(prefix)

    def get_command(self, prefix: str = "/") -> tuple[str, list[str]] | None:
        """解析指令消息，返回 (指令名, 参数列表)。"""
        if not self.is_command(prefix):
            return None
        parts = self.content.strip()[len(prefix):].split()
        if not parts:
            return None
        return parts[0], parts[1:]

    async def reply(self, text: str) -> Any:
        """快捷回复当前消息。"""
        if self._bot is None:
            raise RuntimeError("Message not associated with a bot")
        return await self._bot.reply_text(self, text)


class UnifiedBot:
    """统一机器人，根据平台配置自动委托给底层实现。

    通过 BOT_PLATFORM 环境变量选择平台:
        - "feishu": 飞书 (LarkBot + WebhookServer)
        - "wechat": 微信 (WeChatBot, 长轮询)
        - "qq":     QQ (QQBot, WebSocket)

    用法::

        bot = UnifiedBot()  # 或 UnifiedBot(platform="feishu")

        @bot.on_message
        async def on_message(msg: UnifiedMessage):
            await msg.reply(f"收到: {msg.get_text()}")

        @bot.on_command("help")
        async def cmd_help(msg: UnifiedMessage, args: list):
            await msg.reply("帮助信息")

        await bot.run()
    """

    def __init__(self, platform: str | None = None):
        raw = (platform or os.getenv("BOT_PLATFORM", "feishu")).strip().lower()
        if raw not in VALID_PLATFORMS:
            raise ValueError(
                f"Unknown platform: {raw!r}. Valid options: {', '.join(VALID_PLATFORMS)}"
            )
        self._platform: str = raw
        self._bot: Any = None  # 底层平台 bot 实例
        self._message_handlers: list[Callable[[UnifiedMessage], Any]] = []
        self._command_handlers: dict[str, Callable[[UnifiedMessage, list[str]], Any]] = {}
        self._command_prefix: str = "/"
        self._running: bool = False

        self._init_platform_bot()

    # ------------------------------------------------------------------
    # 平台初始化
    # ------------------------------------------------------------------

    def _init_platform_bot(self) -> None:
        """根据平台创建底层 bot 实例并注册统一分发回调。"""
        if self._platform == "feishu":
            from .config import LarkConfig
            from .bot import LarkBot

            self._bot = LarkBot(config=LarkConfig.from_env())
        elif self._platform == "wechat":
            from .wechat_config import WeChatConfig
            from .wechat_bot import WeChatBot

            self._bot = WeChatBot(config=WeChatConfig.from_env())
        elif self._platform == "qq":
            from .qq_config import QQConfig
            from .qq_bot import QQBot

            self._bot = QQBot(config=QQConfig.from_env())

        # 将统一分发回调注册到下层 bot 的 _message_handlers 中。
        # 所有平台都在原生消息循环中调用 _message_handlers，因此我们的回
        # 调会收到每条消息并转换为 UnifiedMessage 后重新分发给用户。
        self._bot._message_handlers.append(self._dispatch_unified)

    # ------------------------------------------------------------------
    # 内部：消息转换与分发
    # ------------------------------------------------------------------

    def _to_unified(self, platform_msg: Any) -> UnifiedMessage:
        """将平台原生消息转换为 UnifiedMessage。"""
        if self._platform == "feishu":
            return UnifiedMessage(
                message_id=platform_msg.message_id,
                chat_id=platform_msg.chat_id,
                sender_id=platform_msg.sender_open_id or "",
                sender_name=platform_msg.sender_name or "",
                content=platform_msg.get_text(),
                msg_type=platform_msg.msg_type.value,
                create_time=platform_msg.create_time,
                raw_data=platform_msg.raw_data,
                platform="feishu",
                _platform_message=platform_msg,
                _bot=self,
            )
        elif self._platform == "wechat":
            return UnifiedMessage(
                message_id=str(platform_msg.message_id),
                chat_id=platform_msg.from_user_id,
                sender_id=platform_msg.from_user_id,
                sender_name="",
                content=platform_msg.get_text(),
                msg_type=platform_msg.message_type.name.lower() if platform_msg.message_type else "unknown",
                create_time=platform_msg.create_time_ms,
                raw_data=platform_msg.raw_data,
                platform="wechat",
                _platform_message=platform_msg,
                _bot=self,
            )
        elif self._platform == "qq":
            return UnifiedMessage(
                message_id=platform_msg.message_id,
                chat_id=platform_msg.author_openid,
                sender_id=platform_msg.author_openid,
                sender_name=getattr(platform_msg, "author_username", "") or "",
                content=platform_msg.content,
                msg_type="text",
                create_time=None,
                raw_data=getattr(platform_msg, "raw_data", {}),
                platform="qq",
                _platform_message=platform_msg,
                _bot=self,
            )

    async def _dispatch_unified(self, platform_msg: Any) -> None:
        """平台回调入口：转换并分发到用户注册的 handler。"""
        try:
            unified = self._to_unified(platform_msg)

            # 指令分发
            if unified.is_command(self._command_prefix):
                cmd = unified.get_command(self._command_prefix)
                if cmd and cmd[0] in self._command_handlers:
                    try:
                        result = self._command_handlers[cmd[0]](unified, cmd[1])
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception:
                        logger.exception(
                            f"Command handler error: /{cmd[0]}"
                        )

            # 消息分发
            for handler in self._message_handlers:
                try:
                    result = handler(unified)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    logger.exception("Message handler error")
        except Exception:
            logger.exception("Unified dispatch error")

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def on_message(
        self, handler: Callable[[UnifiedMessage], Any]
    ) -> Callable[[UnifiedMessage], Any]:
        """注册消息处理器。"""
        self._message_handlers.append(handler)
        return handler

    def on_command(self, command: str) -> Callable:
        """注册指令处理器。"""

        def decorator(
            handler: Callable[[UnifiedMessage, list[str]], Any],
        ) -> Callable[[UnifiedMessage, list[str]], Any]:
            self._command_handlers[command] = handler
            return handler

        return decorator

    def set_command_prefix(self, prefix: str) -> None:
        """设置指令前缀（默认为 "/"）。"""
        self._command_prefix = prefix

    @property
    def platform(self) -> str:
        """当前使用的平台名称。"""
        return self._platform

    # ------------------------------------------------------------------
    # 消息发送
    # ------------------------------------------------------------------

    async def reply_text(self, msg: UnifiedMessage, text: str) -> Any:
        """回复消息。

        三个平台的 reply_text 签名一致: (platform_message, text)，
        因此无需按平台分支。
        """
        return await self._bot.reply_text(msg._platform_message, text)

    async def send_text(self, text: str, target_id: str | None = None) -> Any:
        """主动发送文本消息。

        Args:
            text: 文本内容。
            target_id: 目标标识。
                - 飞书: open_id（不传则使用 OPEN_ID 配置项）
                - 微信: user_id（不传则发给绑定的账号；需用户先发过消息）
                - QQ:   用户 openid（必填）
        """
        if self._platform == "feishu":
            kwargs: dict[str, Any] = {}
            if target_id:
                kwargs["open_id"] = target_id
            return await self._bot.send_text(text, **kwargs)
        elif self._platform == "wechat":
            return await self._bot.send_text(text, to_user_id=target_id)
        elif self._platform == "qq":
            if not target_id:
                from .qq_bot import QQError
                raise QQError("QQ platform requires target_id (user openid)")
            return await self._bot.send_text(text, target_id)

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """初始化底层 bot（创建 session、刷新 token 等）。"""
        if self._platform == "feishu":
            await self._bot.start()
        elif self._platform in ("wechat", "qq"):
            if hasattr(self._bot, "_init_session"):
                await self._bot._init_session()

    async def close(self) -> None:
        """关闭底层 bot，释放连接。"""
        if hasattr(self._bot, "close"):
            await self._bot.close()

    async def __aenter__(self) -> "UnifiedBot":
        await self.start()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # 运行
    # ------------------------------------------------------------------

    async def run(
        self,
        host: str = "0.0.0.0",
        port: int = 3000,
        path: str = "/",
        on_ready: Callable[["UnifiedBot"], Any] | None = None,
    ) -> None:
        """启动机器人，进入消息循环（阻塞直到被中断）。

        Args:
            host: 飞书 Webhook 绑定地址。
            port: 飞书 Webhook 监听端口。
            path: 飞书 Webhook 路径。
            on_ready: 就绪回调，收到 ``UnifiedBot`` 实例作为参数。
        """
        if self._platform == "feishu":
            await self._run_feishu(host, port, path, on_ready)
        elif self._platform == "wechat":
            await self._run_wechat(on_ready)
        elif self._platform == "qq":
            await self._run_qq(on_ready)

    async def _run_feishu(
        self,
        host: str,
        port: int,
        path: str,
        on_ready: Callable[["UnifiedBot"], Any] | None,
    ) -> None:
        from .handlers import WebhookServer

        await self.start()

        server = WebhookServer(self._bot, host=host, port=port, path=path)
        await server.start()
        logger.info(
            "🚀 Feishu bot running — webhook at http://%s:%s%s", host, port, path
        )

        if on_ready:
            result = on_ready(self)
            if asyncio.iscoroutine(result):
                await result

        self._running = True
        try:
            while self._running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            await server.stop()
            await self.close()

    async def _run_wechat(
        self, on_ready: Callable[["UnifiedBot"], Any] | None
    ) -> None:
        # WeChatBot.run() 内部处理登录和消息轮询
        async def _on_ready() -> None:
            if on_ready:
                result = on_ready(self)
                if asyncio.iscoroutine(result):
                    await result

        await self._bot.run(on_ready=_on_ready)

    async def _run_qq(
        self, on_ready: Callable[["UnifiedBot"], Any] | None
    ) -> None:
        # QQBot.run() does not support on_ready internally. Fire after the first
        # connection succeeds — the bot will call close() if it fails permanently.
        async def _qq_on_ready():
            if on_ready:
                result = on_ready(self)
                if asyncio.iscoroutine(result):
                    await result

        self._bot._on_ready_callback = _qq_on_ready
        await self._bot.run()

    def stop(self) -> None:
        """停止机器人消息循环。"""
        self._running = False
        if hasattr(self._bot, "stop"):
            self._bot.stop()


# ------------------------------------------------------------------
