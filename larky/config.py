import os
from dataclasses import dataclass


@dataclass
class LarkConfig:
    app_id: str
    app_secret: str
    verification_token: str = ""
    encrypt_key: str = ""
    lark_host: str = "https://open.feishu.cn"
    open_id: str = ""
    max_retries: int = 3
    retry_delay: float = 1.0
    log_level: str = "INFO"

    def __post_init__(self) -> None:
        if not self.app_id:
            raise ValueError("APP_ID is required")
        if not self.app_secret:
            raise ValueError("APP_SECRET is required")
        if self.max_retries < 0:
            raise ValueError("MAX_RETRIES must be non-negative")
        if self.retry_delay <= 0:
            raise ValueError("RETRY_DELAY must be positive")

    @classmethod
    def from_env(cls) -> "LarkConfig":
        return cls(
            app_id=os.getenv("APP_ID", ""),
            app_secret=os.getenv("APP_SECRET", ""),
            verification_token=os.getenv("VERIFICATION_TOKEN", ""),
            encrypt_key=os.getenv("ENCRYPT_KEY", ""),
            lark_host=os.getenv("LARK_HOST", "https://open.feishu.cn"),
            open_id=os.getenv("OPEN_ID", ""),
            max_retries=int(os.getenv("MAX_RETRIES", "3")),
            retry_delay=float(os.getenv("RETRY_DELAY", "1.0")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )
