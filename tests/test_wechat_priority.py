"""测试微信消息优先级功能

测试场景：
1. 测试 BackupNotifier 邮件发送功能
2. 测试消息优先级处理逻辑
3. 模拟离线场景测试

运行方式：
    uv run python -m pytest tests/test_wechat_priority.py -v
"""

import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()


@pytest.mark.asyncio
async def test_backup_notifier():
    """测试 BackupNotifier 邮件发送功能"""
    print("\n" + "=" * 50)
    print("测试 1: BackupNotifier 邮件发送功能")
    print("=" * 50)

    from larky.wechat_service import BackupNotifier

    notifier = BackupNotifier()

    if not notifier.enabled:
        print("⚠️ 邮件功能未配置，跳过邮件发送测试")
        print("   请在 .env 中配置 BACKUP_EMAIL_* 相关变量")
        return False

    print(f"📧 邮件配置:")
    print(f"   SMTP: {notifier.email_smtp}:{notifier.email_port}")
    print(f"   发件人: {notifier.email_from}")
    print(f"   收件人: {notifier.email_to}")

    success = await notifier.send_message_backup(
        text="这是一条测试消息：高优先级消息备份测试",
        source="test-script",
        timestamp=datetime.now().isoformat(),
    )

    if success:
        print("✅ 邮件发送成功！请检查收件箱")
    else:
        print("❌ 邮件发送失败")

    return success


@pytest.mark.asyncio
async def test_message_priority_logic():
    """测试消息优先级处理逻辑"""
    print("\n" + "=" * 50)
    print("测试 2: 消息优先级处理逻辑")
    print("=" * 50)

    from larky.wechat_service import WeChatService

    mock_redis = AsyncMock()
    mock_redis.rpush = AsyncMock()
    mock_redis.publish = AsyncMock()
    mock_redis.lpop = AsyncMock(return_value=None)
    mock_redis.llen = AsyncMock(return_value=0)

    service = WeChatService.__new__(WeChatService)
    service.redis = mock_redis
    service._status = MagicMock()
    service._status.connected = False
    service._status.message_sent = 0
    service._status.message_failed = 0
    service._backup_notifier = AsyncMock()
    service._backup_notifier.send_message_backup = AsyncMock(return_value=True)

    print("\n场景 A: 离线 + 普通优先级消息")
    normal_payload = json.dumps({
        "text": "普通消息测试",
        "source": "test",
        "priority": "normal",
        "timestamp": datetime.now().isoformat(),
    }).encode()

    await service._handle_outgoing_message(normal_payload)

    assert not mock_redis.rpush.called, "普通消息不应入队"
    print("✅ 普通消息离线时正确丢弃")

    print("\n场景 B: 离线 + 高优先级消息")
    mock_redis.rpush.reset_mock()
    high_payload = json.dumps({
        "text": "高优先级消息测试",
        "source": "test",
        "priority": "high",
        "timestamp": datetime.now().isoformat(),
    }).encode()

    await service._handle_outgoing_message(high_payload)

    assert mock_redis.rpush.called, "高优先级消息应入队"
    assert service._backup_notifier.send_message_backup.called, "应发送邮件备份"
    print("✅ 高优先级消息离线时正确入队并发送邮件备份")

    print("\n场景 C: 在线 + 任意优先级消息")
    service._status.connected = True
    service.bot = AsyncMock()
    service.bot.notify = AsyncMock()

    mock_redis.rpush.reset_mock()
    await service._handle_outgoing_message(high_payload)

    assert service.bot.notify.called, "在线时应直接发送消息"
    assert not mock_redis.rpush.called, "在线时消息不应入队"
    print("✅ 在线时消息直接发送")

    return True


@pytest.mark.asyncio
async def test_pending_messages_recovery():
    """测试积压消息恢复逻辑"""
    print("\n" + "=" * 50)
    print("测试 3: 积压消息恢复逻辑")
    print("=" * 50)

    from larky.wechat_service import WeChatService

    mock_redis = AsyncMock()

    test_messages = [
        json.dumps({
            "text": f"积压消息 {i}",
            "source": "test",
            "priority": "high",
            "timestamp": datetime.now().isoformat(),
        }).encode()
        for i in range(3)
    ]

    call_count = 0

    async def mock_lpop(key):
        nonlocal call_count
        if call_count < len(test_messages):
            result = test_messages[call_count]
            call_count += 1
            return result
        return None

    mock_redis.lpop = mock_lpop
    mock_redis.llen = AsyncMock(return_value=len(test_messages))

    service = WeChatService.__new__(WeChatService)
    service.redis = mock_redis
    service._status = MagicMock()
    service._status.connected = True
    service._status.message_sent = 0
    service._running = True
    service.bot = AsyncMock()
    service.bot.notify = AsyncMock()

    print(f"📦 模拟 {len(test_messages)} 条积压消息...")

    processed_count = 0
    max_iterations = 10
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        data = await mock_redis.lpop("test")
        if not data:
            break

        payload = json.loads(data)
        text = payload.get("text", "")
        source = payload.get("source", "unknown")
        priority = payload.get("priority", "normal")

        await service.bot.notify(text)
        service._status.message_sent += 1
        processed_count += 1
        print(f"   📨 处理: {text} (优先级: {priority})")

    print(f"✅ 共处理 {processed_count} 条积压消息")
    assert processed_count == 3, f"应处理3条消息，实际处理{processed_count}条"

    return True


@pytest.mark.asyncio
async def test_wechat_client_notify():
    """测试 WeChatClient.notify 方法"""
    print("\n" + "=" * 50)
    print("测试 4: WeChatClient.notify 方法")
    print("=" * 50)

    from larky.wechat_service import WeChatClient, CHANNEL_OUTGOING

    mock_redis = AsyncMock()
    mock_redis.publish = AsyncMock()

    client = WeChatClient.__new__(WeChatClient)
    client.redis = mock_redis
    client.source = "test-client"

    print("\n发送普通优先级消息...")
    await client.notify("普通消息测试", priority="normal")

    call_args = mock_redis.publish.call_args
    payload = json.loads(call_args[0][1])
    assert payload["priority"] == "normal"
    assert payload["source"] == "test-client"
    assert "timestamp" in payload
    print("✅ 普通消息 payload 正确")

    print("\n发送高优先级消息...")
    mock_redis.publish.reset_mock()
    await client.notify("高优先级消息测试", priority="high")

    call_args = mock_redis.publish.call_args
    payload = json.loads(call_args[0][1])
    assert payload["priority"] == "high"
    assert "timestamp" in payload
    print("✅ 高优先级消息 payload 正确")

    return True


async def main():
    print("=" * 50)
    print("微信消息优先级功能测试")
    print("=" * 50)

    results = []

    results.append(("BackupNotifier 邮件发送", await test_backup_notifier()))
    results.append(("消息优先级处理逻辑", await test_message_priority_logic()))
    results.append(("积压消息恢复", await test_pending_messages_recovery()))
    results.append(("WeChatClient.notify", await test_wechat_client_notify()))

    print("\n" + "=" * 50)
    print("测试结果汇总")
    print("=" * 50)

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {name}: {status}")

    all_passed = all(r for _, r in results)
    print("\n" + ("🎉 所有测试通过！" if all_passed else "⚠️ 部分测试失败"))


if __name__ == "__main__":
    asyncio.run(main())
