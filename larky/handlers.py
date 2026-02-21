import hashlib
import json
import logging
from typing import Any, Callable

from aiohttp import web

from .bot import LarkBot
from .models import Message, AESCipher

logger = logging.getLogger(__name__)


class WebhookServer:
    def __init__(
        self,
        bot: LarkBot,
        host: str = "0.0.0.0",
        port: int = 3000,
        path: str = "/",
    ):
        self.bot = bot
        self.host = host
        self.port = port
        self.path = path
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        self._app = web.Application()
        self._app.router.add_post(self.path, self._handle_webhook)
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
        logger.info(f"Webhook server started at http://{self.host}:{self.port}{self.path}")

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()

    async def _handle_webhook(self, request: web.Request) -> web.Response:
        try:
            raw_body = await request.read()
            data = json.loads(raw_body)
        except json.JSONDecodeError:
            return web.Response(status=400, text="Invalid JSON")

        data = self._decrypt_data(data)

        if data.get("type") == "url_verification":
            token = data.get("token", "")
            if self.bot.config.verification_token and token != self.bot.config.verification_token:
                logger.warning(f"Invalid verification token: {token}")
                return web.Response(status=403, text="Invalid token")
            return web.json_response({"challenge": data.get("challenge")})

        if self.bot.config.verification_token:
            if not self._verify_signature(request, raw_body):
                logger.warning("Invalid signature")
                return web.Response(status=403, text="Invalid signature")

        try:
            result = await self.bot.handle_webhook_event(data)
            if result:
                return web.json_response(result)
            return web.json_response({})
        except Exception as e:
            logger.exception(f"Error handling webhook: {e}")
            return web.Response(status=500, text=str(e))

    def _decrypt_data(self, data: dict[str, Any]) -> dict[str, Any]:
        encrypt_data = data.get("encrypt")
        if not encrypt_data:
            return data
        
        if not self.bot.config.encrypt_key:
            logger.warning("Received encrypted data but no ENCRYPT_KEY configured")
            raise ValueError("No ENCRYPT_KEY configured but data is encrypted")
        
        try:
            cipher = AESCipher(self.bot.config.encrypt_key)
            decrypted = cipher.decrypt_string(encrypt_data)
            return json.loads(decrypted)
        except Exception as e:
            logger.error(f"Failed to decrypt data: {e}")
            raise

    def _verify_signature(self, request: web.Request, body: bytes) -> bool:
        timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
        nonce = request.headers.get("X-Lark-Request-Nonce", "")
        signature = request.headers.get("X-Lark-Signature", "")
        
        if not all([timestamp, nonce, signature]):
            return True
        
        bytes_b = (timestamp + nonce + self.bot.config.encrypt_key).encode("utf-8") + body
        h = hashlib.sha256(bytes_b)
        
        return h.hexdigest() == signature


class MessageHandler:
    def __init__(self, bot: LarkBot):
        self.bot = bot

    def __call__(self, handler: Callable[[Message], Any]) -> Callable[[Message], Any]:
        return self.bot.on_message(handler)


class CommandHandler:
    def __init__(self, bot: LarkBot, command: str):
        self.bot = bot
        self.command = command

    def __call__(self, handler: Callable[[Message, list[str]], Any]) -> Callable[[Message, list[str]], Any]:
        return self.bot.on_command(self.command)(handler)
