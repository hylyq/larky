"""微信机器人主程序（平台特定示例）

💡 新项目推荐使用 unified_main.py + BOT_PLATFORM=wechat 替代。
   API 完全一致，且可随时切换到飞书/QQ 无需改代码。

演示：
1. 消息接收和回复
2. 主动推送消息（量化交易通知场景）
"""

import asyncio
import logging
from datetime import datetime

from dotenv import load_dotenv

from larky import WeChatBot, WeChatMessage

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    bot = WeChatBot.from_env()

    @bot.on_message
    async def on_message(msg: WeChatMessage):
        if not msg.is_command("/"):
            text = msg.get_text()
            await bot.reply_text(msg, f"收到: {text}\n发送 /help 查看命令")

    @bot.on_command("help")
    async def cmd_help(msg: WeChatMessage, args: list):
        help_text = """🤖 微信机器人命令列表：

/help       - 显示此帮助信息
/time       - 显示当前时间
/echo <文本> - 回显你输入的内容
/info       - 显示你的用户信息
/notify     - 测试主动推送消息

直接发送消息，机器人也会自动回复！"""
        await bot.reply_text(msg, help_text)

    @bot.on_command("time")
    async def cmd_time(msg: WeChatMessage, args: list):
        await bot.reply_text(msg, f"⏰ {datetime.now():%Y-%m-%d %H:%M:%S}")

    @bot.on_command("echo")
    async def cmd_echo(msg: WeChatMessage, args: list):
        await bot.reply_text(msg, "📢 " + (" ".join(args) if args else "请输入内容"))

    @bot.on_command("info")
    async def cmd_info(msg: WeChatMessage, args: list):
        info_text = f"""👤 用户信息详情：

消息ID：    {msg.message_id}
发送者ID：  {msg.from_user_id}
消息类型：  {msg.message_type.name}
消息状态：  {msg.message_state.name}
发送时间：  {msg.create_time_ms}
媒体类型：  {msg.get_media_type().name if msg.get_media_type() else '无'}"""
        await bot.reply_text(msg, info_text)

    @bot.on_command("notify")
    async def cmd_notify(msg: WeChatMessage, args: list):
        await bot.notify("📢 这是一条主动推送的测试消息（量化交易通知示例）")
        await bot.reply_text(msg, "✅ 已发送测试通知消息")

    async def on_ready():
        logger.info("🤖 微信机器人已就绪，等待消息...")
        if bot.get_user_id():
            await bot.notify(f"🤖 机器人已启动！\n⏰ {datetime.now():%Y-%m-%d %H:%M:%S}")
            logger.info("✅ 已发送启动通知消息")
        else:
            logger.info("💡 提示: 发送任意消息给机器人以建立连接")

    logger.info("微信机器人启动中...")
    await bot.run(on_ready=on_ready)


if __name__ == "__main__":
    asyncio.run(main())
