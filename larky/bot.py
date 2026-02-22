import asyncio
import time
from typing import Any, Callable

import aiohttp

from .config import LarkConfig
from .models import Message, MessageType, TenantAccessToken


class LarkBot:
    def __init__(
        self,
        config: LarkConfig | None = None,
        *,
        app_id: str | None = None,
        app_secret: str | None = None,
        verification_token: str = "",
        encrypt_key: str = "",
        lark_host: str = "https://open.feishu.cn",
        open_id: str = "",
    ):
        if config:
            self.config = config
        else:
            self.config = LarkConfig(
                app_id=app_id or "",
                app_secret=app_secret or "",
                verification_token=verification_token,
                encrypt_key=encrypt_key,
                lark_host=lark_host,
                open_id=open_id,
            )
        
        self._access_token: TenantAccessToken | None = None
        self._session: aiohttp.ClientSession | None = None
        self._message_handlers: list[Callable[[Message], Any]] = []
        self._command_handlers: dict[str, Callable[[Message, list[str]], Any]] = {}
        self._command_prefix: str = "/"

    @classmethod
    def from_env(cls) -> "LarkBot":
        return cls(config=LarkConfig.from_env())

    async def __aenter__(self) -> "LarkBot":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def start(self) -> None:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        await self._refresh_access_token()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            raise RuntimeError("Bot not started. Call start() or use async context manager.")
        return self._session

    async def _refresh_access_token(self) -> None:
        session = self._get_session()
        url = f"{self.config.lark_host}/open-apis/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": self.config.app_id,
            "app_secret": self.config.app_secret,
        }
        
        async with session.post(url, json=payload) as resp:
            data = await resp.json()
            if data.get("code") != 0:
                raise Exception(f"Failed to get access token: {data}")
            
            self._access_token = TenantAccessToken(
                token=data["tenant_access_token"],
                expire=data["expire"],
            )

    async def _ensure_valid_token(self) -> str:
        if self._access_token is None or self._access_token.expire - time.time() < 300:
            await self._refresh_access_token()
        return self._access_token.token

    async def _request(
        self,
        method: str,
        endpoint: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = self._get_session()
        token = await self._ensure_valid_token()
        url = f"{self.config.lark_host}/open-apis/{endpoint}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        
        async with session.request(method, url, json=payload, headers=headers, params=params) as resp:
            return await resp.json()

    async def send_text(
        self,
        text: str,
        *,
        open_id: str | None = None,
        user_id: str | None = None,
        chat_id: str | None = None,
        email: str | None = None,
        root_id: str | None = None,
    ) -> dict[str, Any]:
        receive_id_type = None
        receive_id = None
        
        if open_id:
            receive_id_type = "open_id"
            receive_id = open_id
        elif user_id:
            receive_id_type = "user_id"
            receive_id = user_id
        elif chat_id:
            receive_id_type = "chat_id"
            receive_id = chat_id
        elif email:
            receive_id_type = "email"
            receive_id = email
        elif self.config.open_id:
            receive_id_type = "open_id"
            receive_id = self.config.open_id
        
        if not receive_id_type:
            raise ValueError("Must provide one of: open_id, user_id, chat_id, email, or set OPEN_ID in config")
        
        import json
        content = json.dumps({"text": text})
        
        payload = {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": content,
        }
        
        params = {"receive_id_type": receive_id_type}
        
        return await self._request("POST", "im/v1/messages", payload, params)

    async def send_message(
        self,
        content: str | dict[str, Any],
        msg_type: MessageType = MessageType.TEXT,
        *,
        open_id: str | None = None,
        user_id: str | None = None,
        chat_id: str | None = None,
        email: str | None = None,
        root_id: str | None = None,
    ) -> dict[str, Any]:
        receive_id_type = None
        receive_id = None
        
        if open_id:
            receive_id_type = "open_id"
            receive_id = open_id
        elif user_id:
            receive_id_type = "user_id"
            receive_id = user_id
        elif chat_id:
            receive_id_type = "chat_id"
            receive_id = chat_id
        elif email:
            receive_id_type = "email"
            receive_id = email
        elif self.config.open_id:
            receive_id_type = "open_id"
            receive_id = self.config.open_id
        
        if not receive_id_type:
            raise ValueError("Must provide one of: open_id, user_id, chat_id, email, or set OPEN_ID in config")
        
        if isinstance(content, dict):
            import json
            content = json.dumps(content)
        
        payload = {
            "receive_id": receive_id,
            "msg_type": msg_type.value,
            "content": content,
        }
        
        params = {"receive_id_type": receive_id_type}
        
        return await self._request("POST", "im/v1/messages", payload, params)

    async def reply_text(
        self,
        message: Message,
        text: str,
    ) -> dict[str, Any]:
        return await self.send_text(
            text,
            open_id=message.sender_open_id,
        )

    async def get_user_info(self, user_id: str, user_id_type: str = "open_id") -> dict[str, Any]:
        result = await self._request(
            "GET",
            "user/v1/user_info",
            params={"user_id": user_id, "user_id_type": user_id_type},
        )
        return result

    def on_message(self, handler: Callable[[Message], Any]) -> Callable[[Message], Any]:
        self._message_handlers.append(handler)
        return handler

    def on_command(self, command: str) -> Callable:
        def decorator(handler: Callable[[Message, list[str]], Any]) -> Callable[[Message, list[str]], Any]:
            self._command_handlers[command] = handler
            return handler
        return decorator

    def set_command_prefix(self, prefix: str) -> None:
        self._command_prefix = prefix

    async def handle_webhook_event(self, data: dict[str, Any]) -> dict[str, Any] | None:
        if data.get("type") == "url_verification":
            return {"challenge": data.get("challenge")}
        
        message = Message.from_webhook(data)
        
        if message.is_command(self._command_prefix):
            cmd_result = message.get_command(self._command_prefix)
            if cmd_result:
                cmd, args = cmd_result
                if cmd in self._command_handlers:
                    result = self._command_handlers[cmd](message, args)
                    if asyncio.iscoroutine(result):
                        await result
        
        for handler in self._message_handlers:
            result = handler(message)
            if asyncio.iscoroutine(result):
                await result
        
        return None
