import hashlib
import base64
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MessageType(Enum):
    TEXT = "text"
    POST = "post"
    IMAGE = "image"
    FILE = "file"
    AUDIO = "audio"
    MEDIA = "media"
    STICKER = "sticker"
    INTERACTIVE = "interactive"


@dataclass
class Message:
    message_id: str
    chat_id: str
    msg_type: MessageType
    content: str | dict[str, Any]
    sender_id: str | None = None
    sender_open_id: str | None = None
    sender_name: str | None = None
    create_time: int | None = None
    root_id: str | None = None
    parent_id: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_webhook(cls, data: dict[str, Any]) -> "Message":
        event = data.get("event", {})
        message = event.get("message", {})
        sender = event.get("sender", {})
        sender_id = sender.get("sender_id", {})
        
        content = message.get("content", "")
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                pass
        
        sender_open_id = sender_id.get("open_id") or sender.get("open_id")
        
        return cls(
            message_id=message.get("message_id", ""),
            chat_id=message.get("chat_id", ""),
            msg_type=MessageType(message.get("message_type", "text")),
            content=content,
            sender_id=sender_id.get("union_id"),
            sender_open_id=sender_open_id,
            sender_name=sender.get("sender_id", {}).get("sender_name"),
            create_time=message.get("create_time"),
            root_id=message.get("root_id"),
            parent_id=message.get("parent_id"),
            raw_data=data,
        )

    def is_command(self, prefix: str = "/") -> bool:
        if self.msg_type != MessageType.TEXT:
            return False
        text = self.get_text()
        return text.strip().startswith(prefix)

    def get_command(self, prefix: str = "/") -> tuple[str, list[str]] | None:
        if not self.is_command(prefix):
            return None
        text = self.get_text()
        parts = text.strip()[len(prefix):].split()
        if not parts:
            return None
        return parts[0], parts[1:]

    def get_text(self) -> str:
        if isinstance(self.content, dict):
            return self.content.get("text", "")
        return str(self.content)


@dataclass
class TenantAccessToken:
    token: str
    expire: int


class AESCipher:
    def __init__(self, key: str):
        self.bs = 16
        self.key = hashlib.sha256(key.encode("utf-8")).digest()

    def decrypt(self, enc: bytes) -> bytes:
        iv = enc[: self.bs]
        from Crypto.Cipher import AES

        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        return self._unpad(cipher.decrypt(enc[self.bs:]))

    def decrypt_string(self, enc: str) -> str:
        enc_bytes = base64.b64decode(enc)
        return self.decrypt(enc_bytes).decode("utf-8")

    @staticmethod
    def _unpad(s: bytes) -> bytes:
        return s[: -ord(s[len(s) - 1 :])]
