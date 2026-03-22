import asyncio
import base64
import json
import logging
import os
import secrets
import time
import uuid
from typing import Any, Callable

import aiohttp
import qrcode

from .wechat_config import WeChatConfig
from .wechat_models import (
    MessageItemType,
    MessageType,
    MessageState,
    WeChatMessage,
    WeChatAccount,
)

logger = logging.getLogger(__name__)


def _print_qr_terminal(url: str) -> None:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=1,
        border=1,
    )
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)


class WeChatError(Exception):
    pass


class WeChatBot:
    def __init__(self, config: WeChatConfig | None = None):
        self.config = config or WeChatConfig.from_env()
        self._session: aiohttp.ClientSession | None = None
        self._message_handlers: list[Callable[[WeChatMessage], Any]] = []
        self._command_handlers: dict[str, Callable[[WeChatMessage, list[str]], Any]] = {}
        self._command_prefix: str = "/"
        self._running = False
        self._get_updates_buf: str = ""
        self._context_tokens: dict[str, str] = {}
        self._account: WeChatAccount | None = None
        self._state_dir: str = ""
        self._qr_session_key: str = ""

    @classmethod
    def from_env(cls) -> "WeChatBot":
        return cls(config=WeChatConfig.from_env())

    async def __aenter__(self) -> "WeChatBot":
        await self._init_session()
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def _init_session(self) -> None:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def close(self) -> None:
        self._running = False
        if self._session and not self._session.closed:
            await self._session.close()

    def _get_state_dir(self) -> str:
        if not self._state_dir:
            base_dir = os.getenv("OPENCLAW_STATE_DIR", "")
            if not base_dir:
                base_dir = os.path.expanduser("~/.openclaw")
            self._state_dir = os.path.join(base_dir, "openclaw-weixin")
        return self._state_dir

    def _get_account_dir(self) -> str:
        return os.path.join(self._get_state_dir(), "accounts")

    def _get_account_path(self, account_id: str) -> str:
        return os.path.join(self._get_account_dir(), f"{account_id}.json")

    def _get_index_path(self) -> str:
        return os.path.join(self._get_state_dir(), "accounts.json")

    def _load_account(self, account_id: str) -> WeChatAccount | None:
        path = self._get_account_path(account_id)
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return WeChatAccount(
                        account_id=account_id,
                        token=data.get("token", ""),
                        base_url=data.get("baseUrl", self.config.base_url),
                        user_id=data.get("userId", ""),
                    )
        except Exception as e:
            logger.warning(f"Failed to load account {account_id}: {e}")
        return None

    def _save_account(self, account: WeChatAccount) -> None:
        dir_path = self._get_account_dir()
        os.makedirs(dir_path, exist_ok=True)
        path = self._get_account_path(account.account_id)
        data = {
            "token": account.token,
            "baseUrl": account.base_url,
            "userId": account.user_id,
            "savedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass
        self._register_account_id(account.account_id)

    def _register_account_id(self, account_id: str) -> None:
        dir_path = self._get_state_dir()
        os.makedirs(dir_path, exist_ok=True)
        path = self._get_index_path()
        existing = []
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                    if not isinstance(existing, list):
                        existing = []
        except Exception:
            existing = []
        if account_id not in existing:
            existing.append(account_id)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2)

    def _list_account_ids(self) -> list[str]:
        path = self._get_index_path()
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return [id for id in data if isinstance(id, str)]
        except Exception:
            pass
        return []

    def _random_wechat_uin(self) -> str:
        uint32 = secrets.randbelow(2**32)
        return base64.b64encode(str(uint32).encode("utf-8")).decode("utf-8")

    def _build_headers(self, token: str | None = None) -> dict[str, str]:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "X-WECHAT-UIN": self._random_wechat_uin(),
        }
        if token and token.strip():
            headers["Authorization"] = f"Bearer {token.strip()}"
        return headers

    def _get_context_token(self, user_id: str) -> str | None:
        key = f"{self._account.account_id}:{user_id}" if self._account else user_id
        return self._context_tokens.get(key)

    def _set_context_token(self, user_id: str, token: str) -> None:
        key = f"{self._account.account_id}:{user_id}" if self._account else user_id
        self._context_tokens[key] = token
        logger.debug(f"Set context token for {user_id}")

    async def _api_request(
        self,
        endpoint: str,
        payload: dict[str, Any],
        token: str | None = None,
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        if not self._session:
            raise RuntimeError("Session not initialized")

        base_url = self._account.base_url if self._account else self.config.base_url
        if not base_url.endswith("/"):
            base_url += "/"
        url = f"{base_url}{endpoint}"

        body = json.dumps(payload)
        headers = self._build_headers(token or (self._account.token if self._account else None))
        timeout = (timeout_ms or self.config.api_timeout_ms) / 1000

        logger.debug(f"POST {endpoint}")
        async with self._session.post(url, data=body, headers=headers, timeout=timeout) as resp:
            raw_text = await resp.text()
            logger.debug(f"Response status={resp.status}")
            if not resp.ok:
                raise WeChatError(f"API error {resp.status}: {raw_text}")
            return json.loads(raw_text)

    async def start_qr_login(self) -> dict[str, Any]:
        base_url = self.config.base_url
        if not base_url.endswith("/"):
            base_url += "/"
        url = f"{base_url}ilink/bot/get_bot_qrcode?bot_type={self.config.bot_type}"

        logger.info("Fetching QR code for WeChat login...")
        async with self._session.get(url) as resp:
            if not resp.ok:
                text = await resp.text()
                raise WeChatError(f"Failed to get QR code: {resp.status} {text}")
            raw_text = await resp.text()
            data = json.loads(raw_text)

        self._qr_session_key = str(uuid.uuid4())
        return {
            "qrcode_url": data.get("qrcode_img_content", ""),
            "qrcode": data.get("qrcode", ""),
            "session_key": self._qr_session_key,
            "message": "请使用微信扫描二维码完成登录",
        }

    async def wait_for_qr_login(self, qrcode: str, timeout_ms: int = 300000) -> WeChatAccount:
        base_url = self.config.base_url
        if not base_url.endswith("/"):
            base_url += "/"
        url = f"{base_url}ilink/bot/get_qrcode_status?qrcode={qrcode}"

        start_time = time.time()
        poll_timeout = self.config.long_poll_timeout_ms / 1000

        while True:
            elapsed = (time.time() - start_time) * 1000
            if elapsed > timeout_ms:
                raise WeChatError("QR code login timeout")

            try:
                async with self._session.get(url, timeout=poll_timeout) as resp:
                    if not resp.ok:
                        raise WeChatError(f"Failed to poll QR status: {resp.status}")
                    raw_text = await resp.text()
                    data = json.loads(raw_text)
            except asyncio.TimeoutError:
                continue

            status = data.get("status", "wait")
            logger.info(f"QR login status: {status}")

            if status == "confirmed":
                bot_token = data.get("bot_token", "")
                ilink_bot_id = data.get("ilink_bot_id", "")
                baseurl = data.get("baseurl", self.config.base_url)
                user_id = data.get("ilink_user_id", "")

                if not bot_token:
                    raise WeChatError("QR login confirmed but no token received")

                account_id = ilink_bot_id or str(uuid.uuid4())
                account = WeChatAccount(
                    account_id=account_id,
                    token=bot_token,
                    base_url=baseurl,
                    user_id=user_id,
                )
                self._save_account(account)
                self._account = account
                logger.info(f"WeChat login successful, account_id={account_id}")
                return account

            elif status == "expired":
                raise WeChatError("QR code expired, please try again")

            await asyncio.sleep(1)

    async def login_with_qr(self, timeout_ms: int = 300000) -> WeChatAccount:
        qr_result = await self.start_qr_login()
        qrcode_url = qr_result.get("qrcode_url", "")
        qrcode = qr_result.get("qrcode", "")

        if not qrcode:
            raise WeChatError("Failed to get QR code")

        print("\n" + "=" * 50)
        print("请使用微信扫描以下二维码登录:")
        print("=" * 50)
        if qrcode_url:
            _print_qr_terminal(qrcode_url)
        print("\n或者直接在微信中打开链接:")
        print(qrcode_url)
        print("=" * 50 + "\n")

        return await self.wait_for_qr_login(qrcode, timeout_ms)

    async def get_updates(self) -> list[WeChatMessage]:
        if not self._account:
            raise WeChatError("Not logged in")

        payload = {
            "get_updates_buf": self._get_updates_buf,
            "base_info": {"channel_version": "1.0.0"},
        }

        try:
            data = await self._api_request(
                "ilink/bot/getupdates",
                payload,
                timeout_ms=self.config.long_poll_timeout_ms,
            )
        except asyncio.TimeoutError:
            logger.debug("getUpdates timeout, returning empty")
            return []
        except Exception as e:
            logger.error(f"getUpdates error: {e}")
            return []

        ret = data.get("ret", 0)
        if ret != 0:
            errcode = data.get("errcode", 0)
            errmsg = data.get("errmsg", "")
            logger.error(f"getUpdates failed: ret={ret}, errcode={errcode}, errmsg={errmsg}")
            return []

        self._get_updates_buf = data.get("get_updates_buf", "")

        messages = []
        for msg_data in data.get("msgs", []):
            msg = WeChatMessage.from_dict(msg_data)
            if msg.context_token:
                self._set_context_token(msg.from_user_id, msg.context_token)
            messages.append(msg)

        return messages

    async def send_text(
        self,
        text: str,
        to_user_id: str,
        context_token: str | None = None,
    ) -> dict[str, Any]:
        if not self._account:
            raise WeChatError("Not logged in")

        ctx_token = context_token or self._get_context_token(to_user_id)
        if not ctx_token:
            logger.warning(f"No context token for {to_user_id}, message may not be associated")

        client_id = f"openclaw-weixin-{uuid.uuid4().hex[:16]}"
        payload = {
            "msg": {
                "from_user_id": "",
                "to_user_id": to_user_id,
                "client_id": client_id,
                "message_type": MessageType.BOT.value,
                "message_state": MessageState.FINISH.value,
                "item_list": [{"type": MessageItemType.TEXT.value, "text_item": {"text": text}}],
                "context_token": ctx_token,
            }
        }

        await self._api_request("ilink/bot/sendmessage", payload)
        return {"message_id": client_id}

    async def reply_text(self, message: WeChatMessage, text: str) -> dict[str, Any]:
        return await self.send_text(text, message.from_user_id, message.context_token)

    async def send_typing(self, to_user_id: str, typing: bool = True) -> None:
        if not self._account:
            raise WeChatError("Not logged in")

        config_data = await self._api_request(
            "ilink/bot/getconfig",
            {"ilink_user_id": to_user_id},
        )
        typing_ticket = config_data.get("typing_ticket", "")
        if not typing_ticket:
            return

        await self._api_request(
            "ilink/bot/sendtyping",
            {
                "ilink_user_id": to_user_id,
                "typing_ticket": typing_ticket,
                "status": 1 if typing else 2,
            },
        )

    def on_message(self, handler: Callable[[WeChatMessage], Any]) -> Callable[[WeChatMessage], Any]:
        self._message_handlers.append(handler)
        return handler

    def on_command(self, command: str) -> Callable:
        def decorator(handler: Callable[[WeChatMessage, list[str]], Any]):
            self._command_handlers[command] = handler
            return handler
        return decorator

    async def _dispatch_message(self, msg: WeChatMessage) -> None:
        if msg.is_command(self._command_prefix):
            cmd = msg.get_command(self._command_prefix)
            if cmd and cmd[0] in self._command_handlers:
                try:
                    result = self._command_handlers[cmd[0]](msg, cmd[1])
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error(f"Command handler error: {e}")

        for handler in self._message_handlers:
            try:
                result = handler(msg)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Message handler error: {e}")

    async def run(self) -> None:
        await self._init_session()

        account_ids = self._list_account_ids()
        if account_ids:
            self._account = self._load_account(account_ids[0])
            if self._account:
                logger.info(f"Loaded account: {self._account.account_id}")

        if not self._account:
            logger.info("No saved account, starting QR login...")
            await self.login_with_qr()

        if not self._account:
            raise WeChatError("Failed to login")

        logger.info(f"Starting message polling for account: {self._account.account_id}")
        self._running = True

        while self._running:
            try:
                messages = await self.get_updates()
                for msg in messages:
                    await self._dispatch_message(msg)
            except Exception as e:
                logger.error(f"Error in message loop: {e}")
                await asyncio.sleep(5)

    def stop(self) -> None:
        self._running = False
