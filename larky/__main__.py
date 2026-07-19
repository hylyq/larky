"""统一消息服务入口点

由 BOT_PLATFORM 环境变量决定底层平台。

使用方法：
    BOT_PLATFORM=feishu python -m larky
    BOT_PLATFORM=wechat python -m larky
    BOT_PLATFORM=qq     python -m larky

或者：
    BOT_PLATFORM=feishu uv run python -m larky
"""

import asyncio
import logging
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional at module level

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

from .service import UnifiedService


async def main() -> None:
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    redis_url = os.getenv("REDIS_URL", f"redis://{redis_host}:{redis_port}")

    service = UnifiedService(redis_url=redis_url)
    await service.run()


if __name__ == "__main__":
    asyncio.run(main())
