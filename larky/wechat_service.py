"""微信消息服务 — 独立进程运行，通过 Redis Pub/Sub 与其他程序通信

已迁移至统一服务架构。WeChatService 和 WeChatClient 现在是
UnifiedService/UnifiedClient 的薄包装，默认使用 platform="wechat"
和 channel_prefix="wechat"。

保留此模块仅为向后兼容。新项目请直接使用：
    from larky import UnifiedService, UnifiedClient

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
from datetime import datetime
from typing import Any, Callable

from dotenv import load_dotenv

from ._email import EmailNotifier as BackupNotifier  # backward-compat re-export
from .service import ServiceStatus  # backward-compat re-export
from .service import UnifiedService as _UnifiedService
from .service import UnifiedClient as _UnifiedClient
from .wechat_models import WeChatMessage, MessageItem, MessageItemType

# 向后兼容的 Redis 频道常量
CHANNEL_INCOMING = "wechat:incoming"
CHANNEL_OUTGOING = "wechat:outgoing"
CHANNEL_STATUS = "wechat:status"
QUEUE_PENDING = "wechat:pending_messages"
QUEUE_FAILED = "wechat:failed_messages"

load_dotenv()

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# 微信富媒体入站消息序列化（WeChat 特有，比统一版本更详细）
# ------------------------------------------------------------------


def _build_incoming_payload(msg: "WeChatMessage") -> dict[str, Any]:
    """将微信消息转换为完整的 Redis 发布载荷（含 CDN 媒体元数据）。"""

    def _item_dict(item: "MessageItem") -> dict[str, Any]:
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
                "text": v.text, "encode_type": v.encode_type,
                "sample_rate": v.sample_rate, "playtime": v.playtime,
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
                "video_size": vid.video_size, "play_length": vid.play_length,
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
        "from_user_id": msg.from_user_id,
        "text": msg.get_text(),
        "message_id": msg.message_id,
        "timestamp": msg.create_time_ms,
        "session_id": msg.session_id,
        "message_type": msg.message_type.name,
        "message_state": msg.message_state.name,
        "context_token": msg.context_token or None,
        "has_media": msg.has_media(),
        "media_type": media_type.name if media_type else None,
        "items": [_item_dict(item) for item in msg.item_list],
    }


# ------------------------------------------------------------------
# WeChatService — 薄包装，委托给 UnifiedService
# ------------------------------------------------------------------


class WeChatService(_UnifiedService):
    """微信消息服务 — 独立进程运行，处理微信消息收发。

    内部委托给 UnifiedService(platform="wechat", channel_prefix="wechat")。
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
        super().__init__(
            platform=platform or "wechat",
            redis_url=redis_url,
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
            channel_prefix=channel_prefix or "wechat",
            max_reconnect=max_reconnect,
            reconnect_delay=reconnect_delay,
        )

    async def _handle_incoming_message(self, msg) -> None:
        """使用微信富媒体载荷格式发布到 Redis。

        从 UnifiedMessage._platform_message 获取原始 WeChatMessage
        以提取完整的 CDN 媒体元数据。
        """
        if msg.is_command("/"):
            cmd = msg.get_command("/")
            if cmd and cmd[0] in ("help", "status", "ping"):
                return

        wc_msg = msg._platform_message  # 原始 WeChatMessage
        data = _build_incoming_payload(wc_msg)

        try:
            await self.redis.publish(
                self._CH_INCOMING,
                json.dumps(data, ensure_ascii=False),
            )
            logger.debug("📤 发布消息到 %s: %s", self._CH_INCOMING, data["text"][:50])
        except Exception as e:
            logger.error("发布消息失败: %s", e)


# ------------------------------------------------------------------
# WeChatClient — 薄包装，委托给 UnifiedClient
# ------------------------------------------------------------------


class WeChatClient(_UnifiedClient):
    """微信客户端 — 量化程序使用此类发送/接收消息。

    内部委托给 UnifiedClient(channel_prefix="wechat")。
    """

    def __init__(self, source: str = "default", **kwargs):
        kwargs.setdefault("channel_prefix", "wechat")
        super().__init__(source=source, **kwargs)


# ------------------------------------------------------------------
# 入口点
# ------------------------------------------------------------------


async def run_service() -> None:
    """运行微信消息服务（python -m larky.wechat_service 入口点）。"""
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
