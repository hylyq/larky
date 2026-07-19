"""量化交易示例 — 使用 UnifiedClient 发送/接收消息

平台由 BOT_PLATFORM 环境变量决定（飞书/微信/QQ 通用）。

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
        """处理收到的消息（所有平台通用）"""
        text = data.get("text", "")
        platform = data.get("platform", "unknown")
        logger.info("收到消息 [%s]: %s", platform, text)

        if "价格" in text or "price" in text.lower():
            price = await get_btc_price()
            await client.notify(f"📊 当前 BTC 价格: ${price:,.2f}")

        elif "状态" in text or "status" in text.lower():
            await client.notify(
                f"✅ BTC 监控服务运行正常\n"
                f"平台: {platform}\n"
                f"⏰ {datetime.now():%Y-%m-%d %H:%M:%S}"
            )

    @client.status_handler
    async def on_status(data: dict):
        """处理服务状态变化"""
        status = data.get("status", "")
        need_login = data.get("need_login", False)
        platform = data.get("platform", "unknown")

        if need_login:
            logger.warning("⚠️ 消息服务需要重新认证！[%s]", platform)
        elif status == "offline":
            logger.warning("⚠️ 消息服务离线 [%s]", platform)
        elif status == "online":
            logger.info("✅ 消息服务在线 [%s]", platform)

    async def price_monitor():
        """价格监控任务 — 突破时发送高优先级通知"""
        while True:
            price = await get_btc_price()
            if price > 100000:
                await client.notify(
                    f"📈 BTC 突破 $100,000！当前: ${price:,.2f}",
                    priority="high",
                )
            elif price < 90000:
                await client.notify(
                    f"📉 BTC 跌破 $90,000！当前: ${price:,.2f}",
                    priority="high",
                )
            await asyncio.sleep(60)

    asyncio.create_task(price_monitor())

    await client.notify(
        f"🚀 BTC 监控服务已启动\n⏰ {datetime.now():%Y-%m-%d %H:%M:%S}"
    )
    logger.info("BTC 监控服务运行中...")

    await client.run()


if __name__ == "__main__":
    asyncio.run(main())
