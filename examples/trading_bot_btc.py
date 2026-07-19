"""量化交易示例 - 使用 UnifiedClient 发送/接收消息（平台无关）

运行前请确保：
1. Redis 服务已启动
2. 统一消息服务已启动 (BOT_PLATFORM=xxx uv run python -m larky)
"""

import asyncio
import logging
import random
from datetime import datetime

from dotenv import load_dotenv

from larky import UnifiedClient

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def get_btc_price() -> float:
    """模拟获取 BTC 价格"""
    return 95000 + random.uniform(-5000, 5000)


async def main():
    client = UnifiedClient(source="btc-monitor")

    @client.message_handler
    async def on_message(data: dict):
        """处理收到的微信消息"""
        text = data.get("text", "")
        logger.info(f"收到消息: {text}")

        if "价格" in text or "price" in text.lower():
            price = await get_btc_price()
            await client.notify(f"📊 当前 BTC 价格: ${price:,.2f}")

        elif "状态" in text or "status" in text.lower():
            await client.notify(f"✅ BTC 监控服务运行正常\n⏰ {datetime.now():%Y-%m-%d %H:%M:%S}")

    @client.status_handler
    async def on_status(data: dict):
        """处理服务状态变化"""
        status = data.get("status", "")
        need_login = data.get("need_login", False)

        if need_login:
            logger.warning("⚠️ 微信服务需要重新扫码登录！")
        elif status == "offline":
            logger.warning("⚠️ 微信服务离线")
        elif status == "online":
            logger.info("✅ 微信服务在线")

    async def price_monitor():
        """价格监控任务"""
        while True:
            price = await get_btc_price()
            if price > 100000:
                await client.notify(f"📈 BTC 突破 $100,000！当前: ${price:,.2f}", priority="high")
            elif price < 90000:
                await client.notify(f"📉 BTC 跌破 $90,000！当前: ${price:,.2f}", priority="high")
            await asyncio.sleep(60)

    asyncio.create_task(price_monitor())

    await client.notify(f"🚀 BTC 监控服务已启动\n⏰ {datetime.now():%Y-%m-%d %H:%M:%S}")
    logger.info("BTC 监控服务运行中...")

    await client.run()


if __name__ == "__main__":
    asyncio.run(main())
