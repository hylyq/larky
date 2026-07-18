import asyncio
import base64
import json
import logging
import os
import secrets
import smtplib
import time
import uuid
from datetime import datetime
from email.mime.text import MIMEText
from typing import Any, Callable

import aiohttp
import qrcode

from .wechat_config import (
    WeChatConfig,
    CHANNEL_VERSION,
    ILINK_APP_ID,
    ILINK_APP_CLIENT_VERSION,
    SESSION_EXPIRED_ERRCODE,
    SESSION_PAUSE_DURATION_MS,
)
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


class SessionExpiredNotifier:
    def __init__(self):
        self.enabled = bool(os.getenv("BACKUP_EMAIL_TO"))
        self.email_from = os.getenv("BACKUP_EMAIL_FROM", "")
        self.email_to = os.getenv("BACKUP_EMAIL_TO", "")
        self.email_smtp = os.getenv("BACKUP_EMAIL_SMTP", "smtp.gmail.com")
        self.email_port = int(os.getenv("BACKUP_EMAIL_PORT", "587"))
        self.email_user = os.getenv("BACKUP_EMAIL_USER", "")
        self.email_password = os.getenv("BACKUP_EMAIL_PASSWORD", "")

    async def notify_session_expired(self, account_id: str, server_name: str = "") -> bool:
        if not self.enabled:
            logger.debug("Email notification not configured (BACKUP_EMAIL_TO not set)")
            return False

        subject = "⚠️ 微信机器人会话已过期，需要重新登录"
        message = f"""微信机器人会话已过期，服务已暂停1小时。

时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
账号ID: {account_id}
服务器: {server_name or os.getenv('SERVER_NAME', 'unknown')}

请在服务器上重新扫码登录：
uv run python -m larky.wechat_service

暂停期间消息将无法发送，重新登录后自动恢复。"""

        try:
            await self._send_email(subject, message)
            logger.info(f"📧 会话过期邮件通知已发送: {account_id}")
            return True
        except Exception as e:
            logger.error(f"发送会话过期邮件失败: {e}")
            return False

    async def _send_email(self, subject: str, message: str) -> None:
        loop = asyncio.get_event_loop()

        def send():
            msg = MIMEText(message, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = self.email_from
            msg["To"] = self.email_to

            if self.email_port == 465:
                with smtplib.SMTP_SSL(self.email_smtp, self.email_port) as server:
                    server.login(self.email_user, self.email_password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(self.email_smtp, self.email_port) as server:
                    server.starttls()
                    server.login(self.email_user, self.email_password)
                    server.send_message(msg)

        await loop.run_in_executor(None, send)


class SessionGuard:
    def __init__(self, notifier: SessionExpiredNotifier | None = None):
        self._pause_until: dict[str, float] = {}
        self._notifier = notifier or SessionExpiredNotifier()
        self._notified_accounts: set[str] = set()

    async def pause(self, account_id: str) -> None:
        self._pause_until[account_id] = time.time() * 1000 + SESSION_PAUSE_DURATION_MS
        logger.warning(f"Session paused for account={account_id} for 1 hour")
        
        if account_id not in self._notified_accounts:
            self._notified_accounts.add(account_id)
            await self._notifier.notify_session_expired(account_id)

    def clear_pause(self, account_id: str) -> None:
        if account_id in self._pause_until:
            del self._pause_until[account_id]
        if account_id in self._notified_accounts:
            self._notified_accounts.remove(account_id)
        logger.info(f"Session pause cleared for account={account_id}")

    def is_paused(self, account_id: str) -> bool:
        until = self._pause_until.get(account_id)
        if until is None:
            return False
        if time.time() * 1000 >= until:
            del self._pause_until[account_id]
            if account_id in self._notified_accounts:
                self._notified_accounts.remove(account_id)
            return False
        return True

    def get_remaining_ms(self, account_id: str) -> int:
        until = self._pause_until.get(account_id)
        if until is None:
            return 0
        remaining = until - time.time() * 1000
        if remaining <= 0:
            del self._pause_until[account_id]
            if account_id in self._notified_accounts:
                self._notified_accounts.remove(account_id)
            return 0
        return int(remaining)


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
        self._session_guard = SessionGuard()
        self._long_poll_timeout_ms: int = self.config.long_poll_timeout_ms

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

    def _get_sync_buf_path(self, account_id: str) -> str:
        return os.path.join(self._get_account_dir(), f"{account_id}.sync.json")

    def _get_context_tokens_path(self, account_id: str) -> str:
        return os.path.join(self._get_account_dir(), f"{account_id}.context-tokens.json")

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

    def _load_sync_buf(self, account_id: str) -> str:
        path = self._get_sync_buf_path(account_id)
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("get_updates_buf", "")
        except Exception as e:
            logger.debug(f"Failed to load sync buf: {e}")
        return ""

    def _save_sync_buf(self, account_id: str, buf: str) -> None:
        if not buf:
            return
        dir_path = self._get_account_dir()
        os.makedirs(dir_path, exist_ok=True)
        path = self._get_sync_buf_path(account_id)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"get_updates_buf": buf}, f)
        except Exception as e:
            logger.warning(f"Failed to save sync buf: {e}")

    def _load_context_tokens(self, account_id: str) -> None:
        path = self._get_context_tokens_path(account_id)
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        for user_id, token in data.items():
                            key = f"{account_id}:{user_id}"
                            self._context_tokens[key] = token
                        logger.info(f"Loaded {len(data)} context tokens for account={account_id}")
        except Exception as e:
            logger.debug(f"Failed to load context tokens: {e}")

    def _save_context_tokens(self, account_id: str) -> None:
        prefix = f"{account_id}:"
        tokens = {}
        for k, v in self._context_tokens.items():
            if k.startswith(prefix):
                tokens[k[len(prefix):]] = v
        if not tokens:
            return
        dir_path = self._get_account_dir()
        os.makedirs(dir_path, exist_ok=True)
        path = self._get_context_tokens_path(account_id)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(tokens, f)
        except Exception as e:
            logger.warning(f"Failed to save context tokens: {e}")

    def get_user_id(self) -> str | None:
        if self._account and self._account.user_id:
            return self._account.user_id
        return None

    def _random_wechat_uin(self) -> str:
        uint32 = secrets.randbelow(2**32)
        return base64.b64encode(str(uint32).encode("utf-8")).decode("utf-8")

    def _build_common_headers(self) -> dict[str, str]:
        return {
            "iLink-App-Id": ILINK_APP_ID,
            "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
        }

    def _build_headers(self, token: str | None = None, body: str = "") -> dict[str, str]:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "Content-Length": str(len(body.encode("utf-8"))),
            "X-WECHAT-UIN": self._random_wechat_uin(),
            **self._build_common_headers(),
        }
        if token and token.strip():
            headers["Authorization"] = f"Bearer {token.strip()}"
        return headers

    def _get_context_token(self, user_id: str) -> str | None:
        key = f"{self._account.account_id}:{user_id}" if self._account else user_id
        return self._context_tokens.get(key)

    def _set_context_token(self, user_id: str, token: str) -> None:
        if not self._account or not token:
            return
        key = f"{self._account.account_id}:{user_id}"
        self._context_tokens[key] = token
        self._save_context_tokens(self._account.account_id)
        logger.debug(f"Set context token for {user_id}")

    def _clear_context_token(self, user_id: str) -> None:
        if not self._account:
            return
        key = f"{self._account.account_id}:{user_id}"
        if key in self._context_tokens:
            del self._context_tokens[key]
            self._save_context_tokens(self._account.account_id)
            logger.info(f"Cleared stale context token for {user_id}")

    async def _api_request(
        self,
        endpoint: str,
        payload: dict[str, Any],
        token: str | None = None,
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        if not self._session:
            raise RuntimeError("Session not initialized")

        if self._account and self._session_guard.is_paused(self._account.account_id):
            remaining_min = self._session_guard.get_remaining_ms(self._account.account_id) // 60000
            raise WeChatError(f"Session paused, {remaining_min} min remaining")

        base_url = self._account.base_url if self._account else self.config.base_url
        if not base_url.endswith("/"):
            base_url += "/"
        url = f"{base_url}{endpoint}"

        body = json.dumps(payload)
        headers = self._build_headers(token or (self._account.token if self._account else None), body)
        timeout = (timeout_ms or self.config.api_timeout_ms) / 1000

        logger.debug(f"POST {endpoint} body={body[:200]}...")
        async with self._session.post(url, data=body, headers=headers, timeout=timeout) as resp:
            raw_text = await resp.text()
            logger.info(f"API {endpoint} status={resp.status} body={raw_text[:500]}")
            if not resp.ok:
                raise WeChatError(f"API error {resp.status}: {raw_text}")
            data = json.loads(raw_text)
            ret = data.get("ret", 0)
            errcode = data.get("errcode", 0)
            if ret != 0 or errcode != 0:
                errmsg = data.get("errmsg", "")
                logger.error(f"API {endpoint} business error: ret={ret}, errcode={errcode}, errmsg={errmsg}")
            return data

    async def _api_get(
        self,
        url: str,
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        if not self._session:
            raise RuntimeError("Session not initialized")

        headers = self._build_common_headers()
        timeout = (timeout_ms or self.config.api_timeout_ms) / 1000

        logger.debug(f"GET {url}")
        async with self._session.get(url, headers=headers, timeout=timeout) as resp:
            raw_text = await resp.text()
            logger.debug(f"Response status={resp.status}")
            if not resp.ok:
                raise WeChatError(f"API error {resp.status}: {raw_text}")
            return json.loads(raw_text)

    async def start_qr_login(self) -> dict[str, Any]:
        base_url = "https://ilinkai.weixin.qq.com"
        url = f"{base_url}/ilink/bot/get_bot_qrcode?bot_type={self.config.bot_type}"

        logger.info("Fetching QR code for WeChat login...")
        data = await self._api_get(url)

        self._qr_session_key = str(uuid.uuid4())
        return {
            "qrcode_url": data.get("qrcode_img_content", ""),
            "qrcode": data.get("qrcode", ""),
            "session_key": self._qr_session_key,
            "message": "请使用微信扫描二维码完成登录",
        }

    async def wait_for_qr_login(self, qrcode: str, timeout_ms: int = 300000) -> WeChatAccount:
        base_url = "https://ilinkai.weixin.qq.com"
        current_base_url = base_url

        start_time = time.time()
        poll_timeout = self.config.long_poll_timeout_ms / 1000
        qr_refresh_count = 1
        max_qr_refresh = 3
        scanned_printed = False

        while True:
            elapsed = (time.time() - start_time) * 1000
            if elapsed > timeout_ms:
                raise WeChatError("QR code login timeout")

            url = f"{current_base_url}/ilink/bot/get_qrcode_status?qrcode={qrcode}"

            try:
                data = await self._api_get(url, timeout_ms=self.config.long_poll_timeout_ms)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.warning(f"Poll QR status error: {e}")
                await asyncio.sleep(1)
                continue

            status = data.get("status", "wait")
            logger.debug(f"QR login status: {status}")

            if status == "wait":
                pass
            elif status == "scaned":
                if not scanned_printed:
                    print("\n👀 已扫码，在微信继续操作...")
                    scanned_printed = True
            elif status == "scaned_but_redirect":
                redirect_host = data.get("redirect_host", "")
                if redirect_host:
                    current_base_url = f"https://{redirect_host}"
                    logger.info(f"IDC redirect, switching to {redirect_host}")
            elif status == "expired":
                qr_refresh_count += 1
                if qr_refresh_count > max_qr_refresh:
                    raise WeChatError("QR code expired multiple times, please try again")

                print(f"\n⏳ 二维码已过期，正在刷新...({qr_refresh_count}/{max_qr_refresh})")
                logger.info(f"QR expired, refreshing ({qr_refresh_count}/{max_qr_refresh})")

                qr_result = await self.start_qr_login()
                new_qrcode_url = qr_result.get("qrcode_url", "")
                qrcode = qr_result.get("qrcode", "")

                if new_qrcode_url:
                    print("\n🔄 新二维码已生成，请重新扫描")
                    _print_qr_terminal(new_qrcode_url)
                    print(f"\n或者直接在微信中打开链接:\n{new_qrcode_url}\n")

                scanned_printed = False
                start_time = time.time()
            elif status == "confirmed":
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
                    base_url=baseurl or self.config.base_url,
                    user_id=user_id,
                )
                self._save_account(account)
                self._account = account
                self._session_guard.clear_pause(account_id)
                logger.info(f"WeChat login successful, account_id={account_id}")
                return account

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

        if self._session_guard.is_paused(self._account.account_id):
            remaining_min = self._session_guard.get_remaining_ms(self._account.account_id) // 60000
            logger.warning(f"Session paused, {remaining_min} min remaining, skipping getUpdates")
            await asyncio.sleep(60)
            return []

        payload = {
            "get_updates_buf": self._get_updates_buf,
            "base_info": {"channel_version": CHANNEL_VERSION},
        }

        try:
            data = await self._api_request(
                "ilink/bot/getupdates",
                payload,
                timeout_ms=self._long_poll_timeout_ms,
            )
        except asyncio.TimeoutError:
            logger.debug("getUpdates timeout, returning empty")
            return []
        except Exception as e:
            logger.error(f"getUpdates error: {e}")
            return []

        ret = data.get("ret", 0)
        errcode = data.get("errcode", 0)

        if ret != 0 or errcode != 0:
            errmsg = data.get("errmsg", "")
            logger.error(f"getUpdates failed: ret={ret}, errcode={errcode}, errmsg={errmsg}")

            if errcode == SESSION_EXPIRED_ERRCODE or ret == SESSION_EXPIRED_ERRCODE:
                await self._session_guard.pause(self._account.account_id)
                logger.error("Session expired, pausing for 1 hour")
                return []

            return []

        if data.get("longpolling_timeout_ms"):
            self._long_poll_timeout_ms = data["longpolling_timeout_ms"]
            logger.debug(f"Updated long poll timeout to {self._long_poll_timeout_ms}ms")

        new_buf = data.get("get_updates_buf", "")
        if new_buf:
            self._get_updates_buf = new_buf
            self._save_sync_buf(self._account.account_id, new_buf)

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
        to_user_id: str | None = None,
        context_token: str | None = None,
    ) -> dict[str, Any]:
        if not self._account:
            raise WeChatError("Not logged in")

        if self._session_guard.is_paused(self._account.account_id):
            remaining_min = self._session_guard.get_remaining_ms(self._account.account_id) // 60000
            raise WeChatError(f"Session paused, {remaining_min} min remaining")

        user_id = to_user_id or self._account.user_id
        if not user_id:
            raise WeChatError("No target user_id. User needs to send a message first.")

        ctx_token = context_token or self._get_context_token(user_id)

        client_id = f"openclaw-weixin-{uuid.uuid4().hex[:16]}"
        payload = {
            "msg": {
                "from_user_id": "",
                "to_user_id": user_id,
                "client_id": client_id,
                "message_type": MessageType.BOT.value,
                "message_state": MessageState.FINISH.value,
                "item_list": [{"type": MessageItemType.TEXT.value, "text_item": {"text": text}}],
                "context_token": ctx_token,
            }
        }

        data = await self._api_request("ilink/bot/sendmessage", payload)
        ret = data.get("ret", 0)
        errmsg = data.get("errmsg", "")

        if ret == -2 and "prepare failed" in errmsg.lower() and not context_token:
            stored = self._get_context_token(user_id)
            if stored:
                logger.warning("Context token expired, clearing and retrying without it")
                self._clear_context_token(user_id)
                payload["msg"]["context_token"] = None
                data = await self._api_request("ilink/bot/sendmessage", payload)
                ret = data.get("ret", 0)
                errmsg = data.get("errmsg", "")

        if ret != 0:
            raise WeChatError(f"sendmessage failed: ret={ret}, errmsg={errmsg}")

        return {"message_id": client_id}

    async def notify(self, text: str) -> dict[str, Any]:
        return await self.send_text(text)

    async def reply_text(self, message: WeChatMessage, text: str) -> dict[str, Any]:
        return await self.send_text(text, message.from_user_id, message.context_token)

    async def send_typing(self, to_user_id: str, typing: bool = True) -> None:
        if not self._account:
            raise WeChatError("Not logged in")

        if self._session_guard.is_paused(self._account.account_id):
            return

        ctx_token = self._get_context_token(to_user_id)
        config_data = await self._api_request(
            "ilink/bot/getconfig",
            {"ilink_user_id": to_user_id, "context_token": ctx_token},
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

    async def run(self, on_ready: Callable[[], Any] | None = None) -> None:
        await self._init_session()

        account_ids = self._list_account_ids()
        if account_ids:
            self._account = self._load_account(account_ids[0])
            if self._account:
                logger.info(f"Loaded account: {self._account.account_id}")
                self._get_updates_buf = self._load_sync_buf(self._account.account_id)
                self._load_context_tokens(self._account.account_id)

        if not self._account:
            logger.info("No saved account, starting QR login...")
            await self.login_with_qr()

        if not self._account:
            raise WeChatError("Failed to login")

        logger.info(f"Starting message polling for account: {self._account.account_id}")
        self._running = True

        if on_ready:
            result = on_ready()
            if asyncio.iscoroutine(result):
                await result

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
