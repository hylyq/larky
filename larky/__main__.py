"""微信消息服务入口点

使用方法：
    python -m larky

或者：
    uv run python -m larky
"""

import asyncio
import logging
import os

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

from .wechat_service import WeChatService


async def main() -> None:
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    redis_url = os.getenv("REDIS_URL", f"redis://{redis_host}:{redis_port}")

    service = WeChatService(redis_url=redis_url)
    await service.run()


if __name__ == "__main__":
    asyncio.run(main())
