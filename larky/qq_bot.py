import asyncio
import json
import logging
import time
from typing import Any, Callable

import aiohttp

from .qq_config import QQConfig
from .qq_models import QQMessage, QQMessageType, QQAccessToken

logger = logging.getLogger(__name__)

C2C_INTENTS = 1 << 25


class QQError(Exception):
    pass


class QQBot:
    def __init__(self, config: QQConfig | None = None, *, intents: int = C2C_INTENTS):
        self.config = config or QQConfig.from_env()
        self._token: QQAccessToken | None = None
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._message_handlers: list[Callable[[QQMessage], Any]] = []
        self._command_handlers: dict[str, Callable[[QQMessage, list[str]], Any]] = {}
        self._command_prefix = "/"
        self._intents = intents
        self._heartbeat_interval = 45000
        self._session_id: str | None = None
        self._seq: int | None = None
        self._running = False
        self._heartbeat_task: asyncio.Task | None = None
        self._max_reconnect: int = 10
        self._reconnect_delay: float = 5.0
        self._on_ready_callback: Callable[[], Any] | None = None

    @classmethod
    def from_env(cls) -> "QQBot":
        return cls(config=QQConfig.from_env())

    async def __aenter__(self) -> "QQBot":
        await self._init_session()
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def _init_session(self) -> None:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def close(self) -> None:
        self._running = False
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()

    async def _get_token(self) -> str:
        if not self._token or self._token.expires_at - time.time() < 300:
            await self._refresh_token()
        return self._token.token

    async def _refresh_token(self) -> None:
        async with self._session.post(
            self.config.token_url,
            json={"appId": self.config.app_id, "clientSecret": self.config.app_secret},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if not resp.ok:
                raise QQError(f"Token refresh failed: HTTP {resp.status}")
            data = await resp.json()
            if "access_token" not in data:
                raise QQError(f"Failed to get token: {data}")
            self._token = QQAccessToken(
                token=data["access_token"],
                expires_at=int(time.time()) + int(data["expires_in"]),
            )

    async def _api_request(self, method: str, endpoint: str, payload: dict | None = None) -> dict:
        token = await self._get_token()
        headers = {
            "Authorization": f"QQBot {token}",
            "Content-Type": "application/json",
            "X-Union-Appid": self.config.app_id,
        }
        async with self._session.request(
            method, f"{self.config.qq_host}{endpoint}",
            json=payload, headers=headers,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if not resp.ok:
                raise QQError(f"API {endpoint}: HTTP {resp.status}")
            return await resp.json()

    async def send_text(self, text: str, openid: str, msg_id: str | None = None) -> dict:
        payload = {"content": text, "msg_type": QQMessageType.TEXT.value}
        if msg_id:
            payload["msg_id"] = msg_id
            payload["msg_seq"] = 1
        return await self._api_request("POST", f"/v2/users/{openid}/messages", payload)

    async def reply_text(self, message: QQMessage, text: str) -> dict:
        return await self.send_text(text, message.author_openid, message.message_id)

    def on_message(self, handler: Callable[[QQMessage], Any]) -> Callable[[QQMessage], Any]:
        self._message_handlers.append(handler)
        return handler

    def on_command(self, command: str) -> Callable:
        def decorator(handler: Callable[[QQMessage, list[str]], Any]):
            self._command_handlers[command] = handler
            return handler
        return decorator

    async def _handle_event(self, data: dict) -> None:
        op, t, d, s = data.get("op"), data.get("t"), data.get("d", {}), data.get("s")
        if s:
            self._seq = s

        if op == 10:
            self._heartbeat_interval = d.get("heartbeat_interval", 45000)
            # Cancel old heartbeat before creating a new one (avoid duplicates on repeated op 10)
            if self._heartbeat_task and not self._heartbeat_task.done():
                self._heartbeat_task.cancel()
            self._heartbeat_task = asyncio.create_task(self._heartbeat())
            await self._identify()
        elif op == 0:
            if t == "READY":
                self._session_id = d.get("session_id")
                logger.info("Bot ready: %s", d.get("user", {}).get("username", "Unknown"))
                if self._on_ready_callback:
                    result = self._on_ready_callback()
                    if asyncio.iscoroutine(result):
                        await result
            elif t == "C2C_MESSAGE_CREATE":
                await self._dispatch_message(QQMessage.from_event(data))

    async def _dispatch_message(self, msg: QQMessage) -> None:
        if msg.is_command(self._command_prefix):
            if cmd := msg.get_command(self._command_prefix):
                if cmd[0] in self._command_handlers:
                    result = self._command_handlers[cmd[0]](msg, cmd[1])
                    if asyncio.iscoroutine(result):
                        await result
        for handler in self._message_handlers:
            result = handler(msg)
            if asyncio.iscoroutine(result):
                await result

    async def _heartbeat(self) -> None:
        while self._running and self._ws and not self._ws.closed:
            await self._ws.send_json({"op": 1, "d": self._seq})
            await asyncio.sleep(self._heartbeat_interval / 1000)

    async def _identify(self) -> None:
        token = await self._get_token()
        await self._ws.send_json({
            "op": 2,
            "d": {
                "token": f"QQBot {token}",
                "intents": self._intents,
                "shard": [0, 1],
                "properties": {"$os": "larky", "$browser": "larky", "$device": "larky"},
            },
        })

    async def run(self) -> None:
        """Start the bot with reconnection on WebSocket drops."""
        await self._init_session()

        reconnect_count = 0
        while reconnect_count < self._max_reconnect:
            try:
                gateway = (await self._api_request("GET", "/gateway/bot"))["url"]
                logger.info("Connecting to gateway: %s", gateway)
                self._ws = await self._session.ws_connect(gateway)
                self._running = True
                reconnect_count = 0  # reset on successful connection

                async for msg in self._ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        await self._handle_event(json.loads(msg.data))
                    elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                        break
            except Exception as e:
                reconnect_count += 1
                delay = min(self._reconnect_delay * (2 ** (reconnect_count - 1)), 300)
                logger.warning(
                    "QQ WebSocket disconnected (%d/%d), reconnecting in %ds: %s",
                    reconnect_count, self._max_reconnect, delay, e,
                )
                await asyncio.sleep(delay)
            finally:
                self._running = False
                if self._heartbeat_task and not self._heartbeat_task.done():
                    self._heartbeat_task.cancel()

        logger.error("QQ bot stopped after %d reconnect attempts", self._max_reconnect)
        await self.close()
