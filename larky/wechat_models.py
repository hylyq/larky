from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MessageItemType(Enum):
    NONE = 0
    TEXT = 1
    IMAGE = 2
    VOICE = 3
    FILE = 4
    VIDEO = 5
    # Added in official plugin v2.4.6
    TOOL_CALL_START = 11
    TOOL_CALL_RESULT = 12


class MessageType(Enum):
    NONE = 0
    USER = 1
    BOT = 2


class MessageState(Enum):
    NEW = 0
    GENERATING = 1
    FINISH = 2


@dataclass
class TextItem:
    text: str = ""


@dataclass
class CDNMedia:
    encrypt_query_param: str = ""
    aes_key: str = ""
    encrypt_type: int = 0


@dataclass
class ImageItem:
    media: CDNMedia | None = None
    thumb_media: CDNMedia | None = None
    aeskey: str = ""
    url: str = ""


@dataclass
class VoiceItem:
    media: CDNMedia | None = None
    encode_type: int = 0
    sample_rate: int = 0
    playtime: int = 0
    text: str = ""


@dataclass
class FileItem:
    media: CDNMedia | None = None
    file_name: str = ""
    md5: str = ""
    len: str = ""


@dataclass
class VideoItem:
    media: CDNMedia | None = None
    video_size: int = 0
    play_length: int = 0
    video_md5: str = ""
    thumb_media: CDNMedia | None = None


@dataclass
class MessageItem:
    type: MessageItemType = MessageItemType.NONE
    create_time_ms: int = 0
    msg_id: str = ""
    text_item: TextItem | None = None
    image_item: ImageItem | None = None
    voice_item: VoiceItem | None = None
    file_item: FileItem | None = None
    video_item: VideoItem | None = None


@dataclass
class WeChatMessage:
    seq: int = 0
    message_id: int = 0
    from_user_id: str = ""
    to_user_id: str = ""
    client_id: str = ""
    create_time_ms: int = 0
    session_id: str = ""
    message_type: MessageType = MessageType.NONE
    message_state: MessageState = MessageState.NEW
    item_list: list[MessageItem] = field(default_factory=list)
    context_token: str = ""
    raw_data: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def _parse_cdn_media(data: dict[str, Any] | None) -> CDNMedia | None:
        """Parse a CDNMedia from a nested dict, returning None if empty/missing."""
        if not data:
            return None
        media = CDNMedia(
            encrypt_query_param=data.get("encrypt_query_param", ""),
            aes_key=data.get("aes_key", ""),
            encrypt_type=data.get("encrypt_type", 0),
        )
        # Return None if all fields are empty/zero — the server sends
        # empty objects rather than omitting the key when no CDN data exists.
        if not media.encrypt_query_param and not media.aes_key and not media.encrypt_type:
            return None
        return media

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WeChatMessage":
        item_list = []
        for item_data in data.get("item_list", []):
            item_type = MessageItemType(item_data.get("type", 0))
            item = MessageItem(type=item_type)

            if item_type == MessageItemType.TEXT:
                text_data = item_data.get("text_item", {})
                item.text_item = TextItem(text=text_data.get("text", ""))

            elif item_type == MessageItemType.IMAGE:
                img_data = item_data.get("image_item", {})
                item.image_item = ImageItem(
                    media=cls._parse_cdn_media(img_data.get("media")),
                    thumb_media=cls._parse_cdn_media(img_data.get("thumb_media")),
                    aeskey=img_data.get("aeskey", ""),
                    url=img_data.get("url", ""),
                )

            elif item_type == MessageItemType.VOICE:
                voice_data = item_data.get("voice_item", {})
                item.voice_item = VoiceItem(
                    media=cls._parse_cdn_media(voice_data.get("media")),
                    encode_type=voice_data.get("encode_type", 0),
                    sample_rate=voice_data.get("sample_rate", 0),
                    playtime=voice_data.get("playtime", 0),
                    text=voice_data.get("text", ""),
                )

            elif item_type == MessageItemType.FILE:
                file_data = item_data.get("file_item", {})
                item.file_item = FileItem(
                    media=cls._parse_cdn_media(file_data.get("media")),
                    file_name=file_data.get("file_name", ""),
                    md5=file_data.get("md5", ""),
                    len=file_data.get("len", ""),
                )

            elif item_type == MessageItemType.VIDEO:
                video_data = item_data.get("video_item", {})
                item.video_item = VideoItem(
                    media=cls._parse_cdn_media(video_data.get("media")),
                    video_size=video_data.get("video_size", 0),
                    play_length=video_data.get("play_length", 0),
                    video_md5=video_data.get("video_md5", ""),
                    thumb_media=cls._parse_cdn_media(video_data.get("thumb_media")),
                )

            item.create_time_ms = item_data.get("create_time_ms", 0)
            item.msg_id = item_data.get("msg_id", "")
            item_list.append(item)

        return cls(
            seq=data.get("seq", 0),
            message_id=data.get("message_id", 0),
            from_user_id=data.get("from_user_id", ""),
            to_user_id=data.get("to_user_id", ""),
            client_id=data.get("client_id", ""),
            create_time_ms=data.get("create_time_ms", 0),
            session_id=data.get("session_id", ""),
            message_type=MessageType(data.get("message_type", 0)),
            message_state=MessageState(data.get("message_state", 0)),
            item_list=item_list,
            context_token=data.get("context_token", ""),
            raw_data=data,
        )

    def get_text(self) -> str:
        for item in self.item_list:
            if item.type == MessageItemType.TEXT and item.text_item:
                return item.text_item.text
            if item.type == MessageItemType.VOICE and item.voice_item and item.voice_item.text:
                return item.voice_item.text
        return ""

    def is_command(self, prefix: str = "/") -> bool:
        text = self.get_text()
        return text.strip().startswith(prefix)

    def get_command(self, prefix: str = "/") -> tuple[str, list[str]] | None:
        if not self.is_command(prefix):
            return None
        text = self.get_text().strip()[len(prefix):]
        parts = text.split()
        return (parts[0], parts[1:]) if parts else None

    def has_media(self) -> bool:
        for item in self.item_list:
            if item.type in (MessageItemType.IMAGE, MessageItemType.VIDEO, MessageItemType.FILE, MessageItemType.VOICE):
                return True
        return False

    def get_media_type(self) -> MessageItemType | None:
        for item in self.item_list:
            if item.type in (MessageItemType.IMAGE, MessageItemType.VIDEO, MessageItemType.FILE, MessageItemType.VOICE):
                return item.type
        return None


@dataclass
class WeChatAccount:
    account_id: str
    token: str
    base_url: str = "https://ilinkai.weixin.qq.com"
    user_id: str = ""
    name: str = ""
