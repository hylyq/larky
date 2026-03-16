from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class QQMessageType(Enum):
    TEXT = 0
    MARKDOWN = 2
    ARK = 3
    EMBED = 4
    MEDIA = 7


@dataclass
class QQMessage:
    message_id: str
    content: str
    author_openid: str
    timestamp: str
    raw_data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_event(cls, data: dict[str, Any]) -> "QQMessage":
        d = data.get("d", {})
        author = d.get("author", {})
        return cls(
            message_id=d.get("id", ""),
            content=d.get("content", ""),
            author_openid=author.get("user_openid", ""),
            timestamp=d.get("timestamp", ""),
            raw_data=data,
        )

    def is_command(self, prefix: str = "/") -> bool:
        return self.content.strip().startswith(prefix)

    def get_command(self, prefix: str = "/") -> tuple[str, list[str]] | None:
        if not self.is_command(prefix):
            return None
        parts = self.content.strip()[len(prefix):].split()
        return (parts[0], parts[1:]) if parts else None


@dataclass
class QQAccessToken:
    token: str
    expires_at: int
