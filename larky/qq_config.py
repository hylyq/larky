import os
from dataclasses import dataclass


@dataclass
class QQConfig:
    app_id: str
    app_secret: str
    qq_host: str = "https://api.sgroup.qq.com"
    token_url: str = "https://bots.qq.com/app/getAppAccessToken"

    @classmethod
    def from_env(cls) -> "QQConfig":
        return cls(
            app_id=os.getenv("QQ_APP_ID", ""),
            app_secret=os.getenv("QQ_APP_SECRET", ""),
        )
