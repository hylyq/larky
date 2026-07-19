"""统一机器人主程序

通过 .env 中的 BOT_PLATFORM 控制底层使用飞书、微信还是 QQ，
用户代码完全无需关心底层差异。切换平台只需修改 .env 一行配置。

用法:
    BOT_PLATFORM=feishu uv run python unified_main.py
    BOT_PLATFORM=wechat uv run python unified_main.py
    BOT_PLATFORM=qq     uv run python unified_main.py
"""

import asyncio
import logging
from datetime import datetime

from dotenv import load_dotenv

from larky import UnifiedBot, UnifiedMessage

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    # 从 BOT_PLATFORM 环境变量自动选择平台
    bot = UnifiedBot()

    # ------------------------------------------------------------------
    # 消息处理器
    # ------------------------------------------------------------------

    @bot.on_message
    async def on_message(msg: UnifiedMessage):
        """非指令消息自动回复。"""
        if not msg.is_command("/"):
            await msg.reply(f"收到: {msg.get_text()}\n发送 /help 查看命令")

    # ------------------------------------------------------------------
    # 指令处理器
    # ------------------------------------------------------------------

    @bot.on_command("help")
    async def cmd_help(msg: UnifiedMessage, args: list):
        help_text = f"""🤖 机器人命令列表 [{bot.platform}]:

/help       - 显示此帮助信息
/time       - 显示当前时间
/echo <文本> - 回显你输入的内容
/info       - 显示消息详情
/platform   - 显示当前平台

直接发送消息，机器人也会自动回复！"""
        await msg.reply(help_text)

    @bot.on_command("time")
    async def cmd_time(msg: UnifiedMessage, args: list):
        await msg.reply(f"⏰ {datetime.now():%Y-%m-%d %H:%M:%S}")

    @bot.on_command("echo")
    async def cmd_echo(msg: UnifiedMessage, args: list):
        await msg.reply("📢 " + (" ".join(args) if args else "请输入内容"))

    @bot.on_command("info")
    async def cmd_info(msg: UnifiedMessage, args: list):
        info_text = f"""📋 消息详情:

消息ID:   {msg.message_id}
平台:     {msg.platform}
发送者ID: {msg.sender_id}
消息类型: {msg.msg_type}
发送时间: {msg.create_time or 'N/A'}
聊天ID:   {msg.chat_id}"""
        await msg.reply(info_text)

    @bot.on_command("platform")
    async def cmd_platform(msg: UnifiedMessage, args: list):
        platform_names = {
            "feishu": "飞书 (Feishu/Lark)",
            "wechat": "微信 (WeChat)",
            "qq": "QQ",
        }
        name = platform_names.get(bot.platform, bot.platform)
        await msg.reply(f"🖥 当前平台: {name}")

    # ------------------------------------------------------------------
    # 就绪回调
    # ------------------------------------------------------------------

    async def on_ready(bot: UnifiedBot):
        logger.info("🤖 机器人已就绪 [platform=%s]", bot.platform)

    # ------------------------------------------------------------------
    # 启动
    # ------------------------------------------------------------------

    logger.info("启动 %s 机器人...", bot.platform)
    await bot.run(on_ready=on_ready)


if __name__ == "__main__":
    asyncio.run(main())
