"""量化交易示例 - ETH 监控服务

可以与 btc_monitor.py 同时运行，共享同一个微信消息服务
"""

import asyncio
import logging
import random
from datetime import datetime

from dotenv import load_dotenv

from larky import WeChatClient

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def get_eth_price() -> float:
    """模拟获取 ETH 价格"""
    return 3500 + random.uniform(-300, 300)


async def main():
    client = WeChatClient(source="eth-monitor")

    @client.message_handler
    async def on_message(data: dict):
        text = data.get("text", "")
        logger.info(f"收到消息: {text}")

        if "eth" in text.lower():
            price = await get_eth_price()
            await client.notify(f"💎 当前 ETH 价格: ${price:,.2f}")

    async def price_monitor():
        while True:
            price = await get_eth_price()
            if price > 4000:
                await client.notify(f"🚀 ETH 突破 $4,000！当前: ${price:,.2f}")
            elif price < 3000:
                await client.notify(f"⚠️ ETH 跌破 $3,000！当前: ${price:,.2f}")
            await asyncio.sleep(60)

    asyncio.create_task(price_monitor())

    await client.notify(f"💎 ETH 监控服务已启动\n⏰ {datetime.now():%Y-%m-%d %H:%M:%S}")
    logger.info("ETH 监控服务运行中...")

    await client.run()


if __name__ == "__main__":
    asyncio.run(main())
