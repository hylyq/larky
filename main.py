import asyncio
import logging

from dotenv import load_dotenv

from larky import LarkBot, Message, WebhookServer

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    bot = LarkBot.from_env()

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

    @bot.on_command("getid")
    async def handle_getid(message: Message, args: list[str]):
        open_id = message.sender_open_id
        if open_id:
            await bot.reply_text(message, f"Your Open ID: {open_id}")
        else:
            await bot.reply_text(message, "Unable to get your Open ID.")

    async with bot:
        if bot.config.open_id:
            logger.info(f"Default OPEN_ID configured: {bot.config.open_id}")
        else:
            logger.info("No default OPEN_ID configured. Send /getid to get your open_id.")

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
