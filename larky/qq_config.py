import os
from dataclasses import dataclass


@dataclass
class QQConfig:
    app_id: str
    app_secret: str
    qq_host: str = "https://api.sgroup.qq.com"
    token_url: str = "https://bots.qq.com/app/getAppAccessToken"

    def __post_init__(self) -> None:
        if not self.app_id:
            raise ValueError("QQ_APP_ID is required")
        if not self.app_secret:
            raise ValueError("QQ_APP_SECRET is required")

    @classmethod
    def from_env(cls) -> "QQConfig":
        return cls(
            app_id=os.getenv("QQ_APP_ID", ""),
            app_secret=os.getenv("QQ_APP_SECRET", ""),
        )
