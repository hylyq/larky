from importlib.metadata import version

__version__ = version("larky")

from .bot import LarkBot, LarkError, TokenError, APIError, ValidationError
from .config import LarkConfig
from .handlers import MessageHandler, CommandHandler, WebhookServer
from .models import Message, MessageType
from .qq_bot import QQBot, QQError
from .qq_config import QQConfig
from .qq_models import QQMessage, QQMessageType
from .unified import UnifiedBot, UnifiedMessage, create_bot
from .wechat_bot import WeChatBot, WeChatError
from .wechat_config import WeChatConfig
from .wechat_models import WeChatMessage, WeChatAccount
from .wechat_service import WeChatService, WeChatClient

__all__ = [
    # 统一 API（推荐使用）
    "UnifiedBot",
    "UnifiedMessage",
    "create_bot",
    # 飞书
    "LarkBot",
    "LarkError",
    "TokenError",
    "APIError",
    "ValidationError",
    "LarkConfig",
    "MessageHandler",
    "CommandHandler",
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
