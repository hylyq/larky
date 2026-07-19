from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("larky")
except PackageNotFoundError:
    __version__ = "0.0.0.dev"

from .bot import LarkBot, LarkError, TokenError, APIError, ValidationError
from .config import LarkConfig
from .handlers import WebhookServer
from .models import Message, MessageType
from .qq_bot import QQBot, QQError
from .qq_config import QQConfig
from .qq_models import QQMessage, QQMessageType
from .service import UnifiedService, UnifiedClient, BackupNotifier
from .unified import UnifiedBot, UnifiedMessage
from .wechat_bot import WeChatBot, WeChatError
from .wechat_config import WeChatConfig
from .wechat_models import WeChatMessage, WeChatAccount
from .wechat_service import WeChatService, WeChatClient

__all__ = [
    # 统一 API（推荐使用）
    "UnifiedBot",
    "UnifiedMessage",
    # 统一消息服务（多进程架构）
    "UnifiedService",
    "UnifiedClient",
    "BackupNotifier",
    # 飞书
    "LarkBot",
    "LarkError",
    "TokenError",
    "APIError",
    "ValidationError",
    "LarkConfig",
    "WebhookServer",
    "Message",
    "MessageType",
    # QQ
    "QQBot",
    "QQError",
    "QQConfig",
    "QQMessage",
    "QQMessageType",
    # 微信
    "WeChatBot",
    "WeChatError",
    "WeChatConfig",
    "WeChatMessage",
    "WeChatAccount",
    "WeChatService",
    "WeChatClient",
]
