"""统一 API 基础测试 — UnifiedBot, UnifiedMessage, UnifiedClient"""

import asyncio
import json
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestUnifiedMessage:
    """UnifiedMessage 核心方法测试"""

    def test_get_text(self):
        from larky import UnifiedMessage
        msg = UnifiedMessage(
            message_id="1", chat_id="c1", sender_id="u1",
            content="hello world", platform="feishu",
        )
        assert msg.get_text() == "hello world"

    def test_is_command_slash(self):
        from larky import UnifiedMessage
        msg = UnifiedMessage(
            message_id="1", chat_id="c1", sender_id="u1",
            content="/help me", platform="feishu",
        )
        assert msg.is_command("/") is True
        assert msg.is_command("!") is False

    def test_is_command_not_command(self):
        from larky import UnifiedMessage
        msg = UnifiedMessage(
            message_id="1", chat_id="c1", sender_id="u1",
            content="hello", platform="wechat",
        )
        assert msg.is_command() is False

    def test_get_command(self):
        from larky import UnifiedMessage
        msg = UnifiedMessage(
            message_id="1", chat_id="c1", sender_id="u1",
            content="/help me please", platform="qq",
        )
        cmd, args = msg.get_command("/")
        assert cmd == "help"
        assert args == ["me", "please"]

    def test_get_command_no_args(self):
        from larky import UnifiedMessage
        msg = UnifiedMessage(
            message_id="1", chat_id="c1", sender_id="u1",
            content="/ping", platform="feishu",
        )
        cmd, args = msg.get_command("/")
        assert cmd == "ping"
        assert args == []

    def test_get_command_not_command(self):
        from larky import UnifiedMessage
        msg = UnifiedMessage(
            message_id="1", chat_id="c1", sender_id="u1",
            content="not a command", platform="feishu",
        )
        assert msg.get_command("/") is None

    def test_custom_prefix(self):
        from larky import UnifiedMessage
        msg = UnifiedMessage(
            message_id="1", chat_id="c1", sender_id="u1",
            content="!help", platform="feishu",
        )
        assert msg.is_command("!") is True
        cmd, args = msg.get_command("!")
        assert cmd == "help"

    def test_reply_requires_bot(self):
        from larky import UnifiedMessage
        msg = UnifiedMessage(
            message_id="1", chat_id="c1", sender_id="u1",
            content="hello", platform="feishu",
        )
        with pytest.raises(RuntimeError, match="not associated"):
            asyncio.run(msg.reply("test"))


class TestUnifiedClient:
    """UnifiedClient 基础测试"""

    def test_notify_payload_structure(self):
        from larky.service import UnifiedClient
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock()

        client = UnifiedClient.__new__(UnifiedClient)
        client._prefix = "bot"
        client.redis = mock_redis
        client.source = "test-source"

        asyncio.run(client.notify("test message", priority="high", target_id="ou_123"))

        assert mock_redis.publish.called
        call_args = mock_redis.publish.call_args
        channel = call_args[0][0]
        payload = json.loads(call_args[0][1])
        assert channel == "bot:outgoing"
        assert payload["text"] == "test message"
        assert payload["priority"] == "high"
        assert payload["source"] == "test-source"
        assert payload["target_id"] == "ou_123"
        assert "timestamp" in payload

    def test_notify_default_priority(self):
        from larky.service import UnifiedClient
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock()

        client = UnifiedClient.__new__(UnifiedClient)
        client._prefix = "bot"
        client.redis = mock_redis
        client.source = "test"

        asyncio.run(client.notify("hello"))
        payload = json.loads(mock_redis.publish.call_args[0][1])
        assert payload["priority"] == "normal"
        assert payload["target_id"] is None


class TestWeChatClientBackwardCompat:
    """确保 WeChatClient 作为薄包装仍正常工作"""

    def test_wechat_client_is_unified_client(self):
        from larky.wechat_service import WeChatClient
        from larky.service import UnifiedClient
        client = WeChatClient.__new__(WeChatClient)
        client._prefix = "wechat"
        assert isinstance(client, UnifiedClient)

    def test_wechat_channel_prefix(self):
        from larky.wechat_service import WeChatClient
        client = WeChatClient.__new__(WeChatClient)
        client._prefix = "wechat"
        assert client._CH_OUTGOING == "wechat:outgoing"
        assert client._CH_INCOMING == "wechat:incoming"
        assert client._CH_STATUS == "wechat:status"


class TestUnifiedBotPlatformDetection:
    """UnifiedBot 平台检测测试"""

    def test_invalid_platform_raises(self):
        from larky.unified import UnifiedBot
        with pytest.raises(ValueError, match="Unknown platform"):
            UnifiedBot(platform="invalid")

    def test_valid_platforms_accepted(self):
        # WeChat requires no config; QQ needs QQ_APP_ID which isn't set in test
        from larky.unified import UnifiedBot
        bot = UnifiedBot(platform="wechat")
        assert bot.platform == "wechat"

    def test_env_var_detection(self):
        os.environ["BOT_PLATFORM"] = "wechat"
        try:
            from larky.unified import UnifiedBot
            bot = UnifiedBot()
            assert bot.platform == "wechat"
        finally:
            del os.environ["BOT_PLATFORM"]
