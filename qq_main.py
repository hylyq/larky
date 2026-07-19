"""QQ机器人示例（平台特定示例）

💡 新项目推荐使用 unified_main.py + BOT_PLATFORM=qq 替代。
   API 完全一致，且可随时切换到飞书/微信 无需改代码。
"""

import asyncio
import logging
from datetime import datetime

from dotenv import load_dotenv

from larky import QQBot, QQMessage

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


async def main():
    bot = QQBot.from_env()

    @bot.on_message
    async def on_message(msg: QQMessage):
        if not msg.is_command():
            await bot.reply_text(msg, f"收到: {msg.content}\n发送 /help 查看命令")

    @bot.on_command("help")
    async def cmd_help(msg: QQMessage, _):
        await bot.reply_text(msg, "命令列表:\n/help - 帮助\n/time - 时间\n/echo <文本> - 回显")

    @bot.on_command("time")
    async def cmd_time(msg: QQMessage, _):
        await bot.reply_text(msg, f"时间: {datetime.now():%Y-%m-%d %H:%M:%S}")

    @bot.on_command("echo")
    async def cmd_echo(msg: QQMessage, args: list):
        await bot.reply_text(msg, " ".join(args) if args else "请输入内容")

    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
