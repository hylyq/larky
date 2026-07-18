import os
from dataclasses import dataclass


CHANNEL_VERSION = "2.4.6"
ILINK_APP_ID = "bot"
BOT_AGENT = os.getenv("WECHAT_BOT_AGENT", "Larky/0.1")


def _build_client_version(version: str) -> int:
    parts = version.split(".")
    major = int(parts[0]) if len(parts) > 0 else 0
    minor = int(parts[1]) if len(parts) > 1 else 0
    patch = int(parts[2]) if len(parts) > 2 else 0
    return ((major & 0xff) << 16) | ((minor & 0xff) << 8) | (patch & 0xff)


def build_base_info() -> dict[str, str]:
    """Build the base_info payload included in every API request (matches official plugin)."""
    return {
        "channel_version": CHANNEL_VERSION,
        "bot_agent": BOT_AGENT,
    }


ILINK_APP_CLIENT_VERSION = _build_client_version(CHANNEL_VERSION)

SESSION_EXPIRED_ERRCODE = -14
SESSION_PAUSE_DURATION_MS = 60 * 60 * 1000


@dataclass
class WeChatConfig:
    base_url: str = "https://ilinkai.weixin.qq.com"
    cdn_base_url: str = "https://novac2c.cdn.weixin.qq.com/c2c"
    bot_type: str = "3"
    long_poll_timeout_ms: int = 35000
    api_timeout_ms: int = 15000
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "WeChatConfig":
        return cls(
            base_url=os.getenv("WECHAT_BASE_URL", "https://ilinkai.weixin.qq.com"),
            cdn_base_url=os.getenv("WECHAT_CDN_BASE_URL", "https://novac2c.cdn.weixin.qq.com/c2c"),
            bot_type=os.getenv("WECHAT_BOT_TYPE", "3"),
            long_poll_timeout_ms=int(os.getenv("WECHAT_LONG_POLL_TIMEOUT_MS", "35000")),
            api_timeout_ms=int(os.getenv("WECHAT_API_TIMEOUT_MS", "15000")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )
