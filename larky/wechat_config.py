import os
from dataclasses import dataclass


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
