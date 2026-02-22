"""飞书机器人主程序"""

import asyncio
import logging
from datetime import datetime
from dotenv import load_dotenv
from larky import LarkBot, Message, WebhookServer

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    bot = LarkBot.from_env()

    @bot.on_message
    async def on_message(msg: Message):
        if not msg.is_command("/"):
            await bot.reply_text(msg, f"收到: {msg.get_text()}\n发送 /help 查看命令")

    @bot.on_command("help")
    async def cmd_help(msg: Message, args: list):
        help_text = """🤖 机器人命令列表：

/help       - 显示此帮助信息
/time       - 显示当前时间
/echo <文本> - 回显你输入的内容
/info       - 显示你的用户信息

直接发送消息，机器人也会自动回复！"""
        await bot.reply_text(msg, help_text)

    @bot.on_command("time")
    async def cmd_time(msg: Message, args: list):
        await bot.reply_text(msg, f"⏰ {datetime.now():%Y-%m-%d %H:%M:%S}")

    @bot.on_command("echo")
    async def cmd_echo(msg: Message, args: list):
        await bot.reply_text(msg, "📢 " + (" ".join(args) if args else "请输入内容"))

    @bot.on_command("info")
    async def cmd_info(msg: Message, args: list):
        info_text = f"""👤 用户信息详情：

消息ID：    {msg.message_id}
聊天ID：    {msg.chat_id}
发送者ID：  {msg.sender_id or 'N/A'}
OpenID：    {msg.sender_open_id}
消息类型：  {msg.msg_type.value}
发送时间：  {msg.create_time or 'N/A'}"""
        await bot.reply_text(msg, info_text)

    async with bot:
        await bot.send_text("🤖 机器人已启动！")
        server = WebhookServer(bot, host="0.0.0.0", port=3000, path="/")
        await server.start()
        logger.info("Webhook 服务器已启动，等待接收消息...")
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
