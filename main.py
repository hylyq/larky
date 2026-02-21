import asyncio
import logging
import os

from dotenv import load_dotenv

from larky import LarkBot, Message, WebhookServer

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    bot = LarkBot(
        app_id=os.getenv("APP_ID", ""),
        app_secret=os.getenv("APP_SECRET", ""),
        verification_token=os.getenv("VERIFICATION_TOKEN", ""),
        encrypt_key=os.getenv("ENCRYPT_KEY", ""),
        lark_host=os.getenv("LARK_HOST", "https://open.feishu.cn"),
    )

    @bot.on_message
    async def handle_message(message: Message):
        text = message.get_text()
        logger.info(f"Received message: {text}")
        await bot.reply_text(message, f"Received: {text}")

    @bot.on_command("ping")
    async def handle_ping(message: Message, args: list[str]):
        await bot.reply_text(message, "Pong!")

    @bot.on_command("status")
    async def handle_status(message: Message, args: list[str]):
        await bot.reply_text(message, "System running normally.")

    @bot.on_command("alert")
    async def handle_alert(message: Message, args: list[str]):
        if args:
            level = args[0]
            await bot.reply_text(message, f"Alert level set to: {level}")
        else:
            await bot.reply_text(message, "Usage: /alert <level>")

    async with bot:
        server = WebhookServer(bot, host="0.0.0.0", port=3000)
        await server.start()
        
        try:
            while True:
                await asyncio.sleep(3600)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
