"""核心路径单元测试 — 覆盖历史上因协议漂移反复出 bug 的路径。

运行方式：
    uv run python -m pytest tests/test_wechat_core.py -v
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


class _MockResponse:
    """Minimal async-context-manager compatible HTTP response mock."""

    def __init__(self, json_body: dict, ok: bool = True):
        self._json = json_body
        self.ok = ok
        self.status = 200

    async def text(self) -> str:
        return json.dumps(self._json)

    async def __aenter__(self) -> "_MockResponse":
        return self

    async def __aexit__(self, *args) -> None:
        pass


def _resp(json_body: dict, ok: bool = True) -> _MockResponse:
    """Shorthand for ``_MockResponse(json_body, ok)``."""
    return _MockResponse(json_body, ok)


def _install_post_mock(bot, *responses: dict):
    """Replace ``bot._session.post`` so it returns pre-baked responses in order.
    The last response repeats.  Returns ``[call_count]``.
    """
    call_count = [0]
    mocks = [_resp(r.get("json", {}), r.get("ok", True)) for r in responses]

    def _post(url, data=None, headers=None, timeout=None, **kwargs):
        idx = min(call_count[0], len(mocks) - 1)
        call_count[0] += 1
        return mocks[idx]

    bot._session.post = _post
    return call_count


def _install_get_mock(bot, *responses: dict):
    """Replace ``bot._session.get``.  Same semantics as ``_install_post_mock``."""
    call_count = [0]
    mocks = [_resp(r.get("json", {}), r.get("ok", True)) for r in responses]

    def _get(url, headers=None, timeout=None, **kwargs):
        idx = min(call_count[0], len(mocks) - 1)
        call_count[0] += 1
        return mocks[idx]

    bot._session.get = _get
    return call_count


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def mock_env():
    """Prevent tests from reading real .env or hitting real services."""
    with patch.dict(os.environ, {}, clear=True):
        yield


def make_mock_bot(with_account=True):
    """Create a WeChatBot with mocked network dependencies."""
    from larky.wechat_bot import WeChatBot
    from larky.wechat_models import WeChatAccount

    bot = WeChatBot.__new__(WeChatBot)
    bot.config = MagicMock()
    bot.config.base_url = "https://ilinkai.weixin.qq.com"
    bot.config.api_timeout_ms = 15000
    bot.config.long_poll_timeout_ms = 35000
    bot.config.bot_type = "3"
    bot._session = MagicMock()
    bot._message_handlers = []
    bot._command_handlers = {}
    bot._command_prefix = "/"
    bot._running = False
    bot._get_updates_buf = ""
    bot._context_tokens = {}
    bot._account = None
    bot._state_dir = ""
    bot._qr_session_key = ""
    from unittest.mock import AsyncMock

    bot._session_guard = MagicMock()
    bot._session_guard.is_paused = MagicMock(return_value=False)
    bot._session_guard.get_remaining_ms = MagicMock(return_value=0)
    bot._session_guard.pause = AsyncMock()  # SessionGuard.pause is async
    bot._long_poll_timeout_ms = 35000
    bot.context_token_updated = MagicMock()
    bot._in_flight = 0

    if with_account:
        bot._account = WeChatAccount(
            account_id="test_account",
            token="test_token",
            base_url="https://ilinkai.weixin.qq.com",
            user_id="test_user",
        )

    return bot


# ═══════════════════════════════════════════════════════════════════════
# Test: send_text — context_token expiry auto-recovery
# ═══════════════════════════════════════════════════════════════════════


class TestSendTextTokenExpiry:
    """send_text retry-on-expiry: the most fragile recovery path."""

    def test_retry_without_token_on_prepare_failed(self):
        """When server returns ret=-2 'prepare failed', clear stale token
        and retry once without it."""
        bot = make_mock_bot()
        bot._context_tokens = {"test_account:test_user": "stale_token"}

        call_count = _install_post_mock(
            bot,
            {"json": {"ret": -2, "errmsg": "prepare failed"}},
            {"json": {"ret": 0, "errmsg": "ok"}},
        )

        import asyncio

        result = asyncio.run(bot.send_text("hello"))
        assert result["message_id"]
        assert call_count[0] == 2, f"Expected 2 calls (fail + retry), got {call_count[0]}"
        assert "test_account:test_user" not in bot._context_tokens

    def test_no_retry_when_explicit_context_token_provided(self):
        """When caller passes an explicit context_token, don't retry —
        the caller knows best."""
        bot = make_mock_bot()

        _install_post_mock(
            bot, {"json": {"ret": -2, "errmsg": "prepare failed"}}
        )

        import asyncio

        with pytest.raises(Exception) as exc_info:
            asyncio.run(bot.send_text("hello", context_token="explicit_token"))
        assert "prepare failed" in str(exc_info.value).lower()

    def test_omits_empty_context_token(self):
        """When no context_token is available, the field should be absent
        from the JSON payload (not serialized as null)."""
        bot = make_mock_bot()
        bot._context_tokens = {}

        captured = []

        def _post(url, data=None, headers=None, timeout=None, **kwargs):
            captured.append(data)
            return _resp({"ret": 0, "errmsg": "ok"})

        bot._session.post = _post

        import asyncio

        asyncio.run(bot.send_text("hello"))
        body = json.loads(captured[0])
        msg = body["msg"]
        assert "context_token" not in msg, (
            f"context_token should be absent when empty, got: {msg.get('context_token')!r}"
        )

    def test_includes_context_token_when_available(self):
        """When a valid context_token is stored, it should be included."""
        bot = make_mock_bot()
        bot._context_tokens = {"test_account:test_user": "valid_ctx_token"}

        captured = []

        def _post(url, data=None, headers=None, timeout=None, **kwargs):
            captured.append(data)
            return _resp({"ret": 0, "errmsg": "ok"})

        bot._session.post = _post

        import asyncio

        asyncio.run(bot.send_text("hello"))
        body = json.loads(captured[0])
        assert body["msg"]["context_token"] == "valid_ctx_token"


# ═══════════════════════════════════════════════════════════════════════
# Test: get_updates — context_token extraction
# ═══════════════════════════════════════════════════════════════════════


class TestGetUpdatesContextToken:
    """context_token is extracted from incoming messages and persisted."""

    def test_extracts_context_token_from_message(self):
        bot = make_mock_bot()

        _install_post_mock(
            bot,
            {
                "json": {
                    "ret": 0,
                    "msgs": [
                        {
                            "seq": 1,
                            "message_id": 100,
                            "from_user_id": "user_abc",
                            "context_token": "fresh_ctx_token",
                            "message_type": 1,
                            "item_list": [
                                {"type": 1, "text_item": {"text": "hello"}}
                            ],
                        }
                    ],
                }
            },
        )

        import asyncio

        messages = asyncio.run(bot.get_updates())
        assert len(messages) == 1
        assert messages[0].context_token == "fresh_ctx_token"
        assert bot._get_context_token("user_abc") == "fresh_ctx_token"

    def test_no_context_token_not_overwritten(self):
        """Messages without context_token don't clear existing tokens."""
        bot = make_mock_bot()
        bot._context_tokens = {"test_account:user_abc": "existing_token"}

        _install_post_mock(
            bot,
            {
                "json": {
                    "ret": 0,
                    "msgs": [
                        {
                            "seq": 1,
                            "message_id": 100,
                            "from_user_id": "user_abc",
                            "message_type": 1,
                            "item_list": [
                                {"type": 1, "text_item": {"text": "hello"}}
                            ],
                        }
                    ],
                }
            },
        )

        import asyncio

        messages = asyncio.run(bot.get_updates())
        assert len(messages) == 1
        assert messages[0].context_token == ""
        assert bot._get_context_token("user_abc") == "existing_token"

    def test_session_expired_errcode_pauses_guard(self):
        """errcode -14 triggers session pause."""
        bot = make_mock_bot()

        _install_post_mock(
            bot,
            {"json": {"ret": -14, "errcode": -14, "errmsg": "session expired"}},
        )

        import asyncio

        messages = asyncio.run(bot.get_updates())
        assert messages == []
        bot._session_guard.pause.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════
# Test: base_info in every API request
# ═══════════════════════════════════════════════════════════════════════


class TestBaseInfoInAPIRequests:
    """Every API request must include base_info with channel_version + bot_agent.

    Tests call the *public methods* (get_updates, notify_start, send_text, etc.)
    rather than _api_request directly, because base_info is added by those
    callers.
    """

    def test_getupdates_has_base_info(self):
        bot = make_mock_bot()
        captured = []

        def _post(url, data=None, headers=None, timeout=None, **kwargs):
            captured.append(json.loads(data))
            return _resp({"ret": 0})

        bot._session.post = _post

        import asyncio

        asyncio.run(bot.get_updates())
        assert len(captured) >= 1
        assert "base_info" in captured[0]
        assert "channel_version" in captured[0]["base_info"]
        assert "bot_agent" in captured[0]["base_info"]

    def test_notifystart_has_base_info(self):
        bot = make_mock_bot()
        captured = []

        def _post(url, data=None, headers=None, timeout=None, **kwargs):
            captured.append(json.loads(data))
            return _resp({"ret": 0})

        bot._session.post = _post

        import asyncio

        asyncio.run(bot.notify_start())
        assert len(captured) >= 1
        payload = captured[0]
        assert "base_info" in payload
        assert "channel_version" in payload["base_info"]

    def test_notifystop_has_base_info(self):
        bot = make_mock_bot()
        captured = []

        def _post(url, data=None, headers=None, timeout=None, **kwargs):
            captured.append(json.loads(data))
            return _resp({"ret": 0})

        bot._session.post = _post

        import asyncio

        asyncio.run(bot.notify_stop())
        assert len(captured) >= 1
        assert "base_info" in captured[0]

    def test_sendmessage_has_base_info(self):
        """send_text wraps msg + base_info in the payload."""
        bot = make_mock_bot()
        captured = []

        def _post(url, data=None, headers=None, timeout=None, **kwargs):
            captured.append(json.loads(data))
            return _resp({"ret": 0, "errmsg": "ok"})

        bot._session.post = _post

        import asyncio

        asyncio.run(bot.send_text("hello"))
        assert len(captured) == 1
        assert "base_info" in captured[0]
        assert "channel_version" in captured[0]["base_info"]
        assert "bot_agent" in captured[0]["base_info"]
        assert "msg" in captured[0]

    def test_check_context_health_has_base_info(self):
        """check_context_health calls getconfig — must include base_info."""
        bot = make_mock_bot()
        bot._context_tokens = {"test_account:test_user": "tok"}
        captured = []

        def _post(url, data=None, headers=None, timeout=None, **kwargs):
            captured.append(json.loads(data))
            return _resp({"ret": 0})

        bot._session.post = _post

        import asyncio

        asyncio.run(bot.check_context_health())
        assert len(captured) >= 1
        assert "base_info" in captured[0]


# ═══════════════════════════════════════════════════════════════════════
# Test: CDNMedia parsing in from_dict
# ═══════════════════════════════════════════════════════════════════════


class TestCDNMediaParsing:
    """Regression tests for CDNMedia extraction in WeChatMessage.from_dict."""

    def test_image_with_cdn_media_thumb(self):
        from larky.wechat_models import WeChatMessage

        msg = WeChatMessage.from_dict(
            {
                "seq": 1,
                "message_id": 100,
                "from_user_id": "u1",
                "item_list": [
                    {
                        "type": 2,
                        "image_item": {
                            "aeskey": "abc",
                            "url": "https://example.com/img.jpg",
                            "media": {
                                "encrypt_query_param": "eq1",
                                "aes_key": "ak1",
                                "encrypt_type": 1,
                            },
                            "thumb_media": {
                                "encrypt_query_param": "eq2",
                                "aes_key": "ak2",
                                "encrypt_type": 1,
                            },
                        },
                    }
                ],
            }
        )
        item = msg.item_list[0]
        assert item.image_item is not None
        assert item.image_item.media is not None
        assert item.image_item.media.aes_key == "ak1"
        assert item.image_item.thumb_media is not None
        assert item.image_item.thumb_media.aes_key == "ak2"

    def test_empty_cdn_media_dict_becomes_none(self):
        from larky.wechat_models import WeChatMessage

        msg = WeChatMessage.from_dict(
            {
                "seq": 1,
                "message_id": 100,
                "from_user_id": "u1",
                "item_list": [
                    {
                        "type": 2,
                        "image_item": {
                            "aeskey": "abc",
                            "url": "https://example.com/img.jpg",
                            "media": {},
                        },
                    }
                ],
            }
        )
        item = msg.item_list[0]
        assert item.image_item is not None
        assert item.image_item.media is None  # empty dict → None

    def test_backward_compat_no_media_field(self):
        """Messages without CDN media fields still parse correctly."""
        from larky.wechat_models import WeChatMessage

        msg = WeChatMessage.from_dict(
            {
                "seq": 1,
                "message_id": 100,
                "from_user_id": "u1",
                "item_list": [
                    {
                        "type": 2,
                        "image_item": {"aeskey": "abc", "url": "https://x.com/i.jpg"},
                    }
                ],
            }
        )
        item = msg.item_list[0]
        assert item.image_item is not None
        assert item.image_item.media is None
        assert item.image_item.url == "https://x.com/i.jpg"

    def test_voice_with_cdn_media(self):
        from larky.wechat_models import WeChatMessage

        msg = WeChatMessage.from_dict(
            {
                "seq": 1,
                "message_id": 100,
                "from_user_id": "u1",
                "item_list": [
                    {
                        "type": 3,
                        "voice_item": {
                            "text": "hello",
                            "encode_type": 1,
                            "media": {
                                "encrypt_query_param": "v1",
                                "aes_key": "vk1",
                                "encrypt_type": 2,
                            },
                        },
                    }
                ],
            }
        )
        item = msg.item_list[0]
        assert item.voice_item is not None
        assert item.voice_item.media is not None
        assert item.voice_item.media.aes_key == "vk1"

    def test_file_with_cdn_media(self):
        from larky.wechat_models import WeChatMessage

        msg = WeChatMessage.from_dict(
            {
                "seq": 1,
                "message_id": 100,
                "from_user_id": "u1",
                "item_list": [
                    {
                        "type": 4,
                        "file_item": {
                            "file_name": "doc.pdf",
                            "md5": "abc",
                            "len": "1024",
                            "media": {
                                "encrypt_query_param": "f1",
                                "aes_key": "fk1",
                                "encrypt_type": 1,
                            },
                        },
                    }
                ],
            }
        )
        item = msg.item_list[0]
        assert item.file_item is not None
        assert item.file_item.media is not None
        assert item.file_item.media.encrypt_query_param == "f1"

    def test_video_with_cdn_media_thumb(self):
        from larky.wechat_models import WeChatMessage

        msg = WeChatMessage.from_dict(
            {
                "seq": 1,
                "message_id": 100,
                "from_user_id": "u1",
                "item_list": [
                    {
                        "type": 5,
                        "video_item": {
                            "video_size": 1024000,
                            "play_length": 30000,
                            "video_md5": "vmd5",
                            "media": {
                                "encrypt_query_param": "vid1",
                                "aes_key": "vidk1",
                                "encrypt_type": 1,
                            },
                            "thumb_media": {
                                "encrypt_query_param": "vt1",
                                "aes_key": "vtk1",
                                "encrypt_type": 1,
                            },
                        },
                    }
                ],
            }
        )
        item = msg.item_list[0]
        assert item.video_item is not None
        assert item.video_item.media is not None
        assert item.video_item.media.aes_key == "vidk1"
        assert item.video_item.thumb_media is not None
        assert item.video_item.thumb_media.aes_key == "vtk1"


# ═══════════════════════════════════════════════════════════════════════
# Test: TOOL_CALL enum values
# ═══════════════════════════════════════════════════════════════════════


class TestToolCallEnum:
    """TOOL_CALL_START/TOOL_CALL_RESULT added in official v2.4.6."""

    def test_tool_call_enum_values(self):
        from larky.wechat_models import MessageItemType

        assert MessageItemType.TOOL_CALL_START.value == 11
        assert MessageItemType.TOOL_CALL_RESULT.value == 12

    def test_tool_call_messages_parse_without_crash(self):
        from larky.wechat_models import WeChatMessage

        msg = WeChatMessage.from_dict(
            {
                "seq": 1,
                "message_id": 100,
                "from_user_id": "u1",
                "item_list": [
                    {"type": 11, "msg_id": "tool_1"},
                    {"type": 12, "msg_id": "tool_2"},
                ],
            }
        )
        assert len(msg.item_list) == 2
        from larky.wechat_models import MessageItemType

        assert msg.item_list[0].type == MessageItemType.TOOL_CALL_START
        assert msg.item_list[1].type == MessageItemType.TOOL_CALL_RESULT


# ═══════════════════════════════════════════════════════════════════════
# Test: send_typing omits empty context_token
# ═══════════════════════════════════════════════════════════════════════


class TestSendTypingContextToken:
    """send_typing must omit context_token when None (same fix as send_text)."""

    def test_omits_context_token_when_none(self):
        bot = make_mock_bot()
        bot._context_tokens = {}

        captured = []

        def _post(url, data=None, headers=None, timeout=None, **kwargs):
            captured.append(json.loads(data))
            return _resp({"ret": 0, "typing_ticket": "ticket_123"})

        bot._session.post = _post

        import asyncio

        asyncio.run(bot.send_typing("test_user"))
        # First call is getconfig — context_token must be absent
        getconfig_payload = captured[0]
        assert "context_token" not in getconfig_payload, (
            f"context_token should be absent when None, got: {getconfig_payload.get('context_token')!r}"
        )

    def test_includes_context_token_when_available(self):
        bot = make_mock_bot()
        bot._context_tokens = {"test_account:test_user": "valid_token"}

        captured = []

        def _post(url, data=None, headers=None, timeout=None, **kwargs):
            captured.append(json.loads(data))
            return _resp({"ret": 0, "typing_ticket": "ticket_123"})

        bot._session.post = _post

        import asyncio

        asyncio.run(bot.send_typing("test_user"))
        getconfig_payload = captured[0]
        assert getconfig_payload["context_token"] == "valid_token"


# ═══════════════════════════════════════════════════════════════════════
# Test: _build_incoming_payload
# ═══════════════════════════════════════════════════════════════════════


class TestBuildIncomingPayload:
    """Redis payload must carry full metadata for downstream consumers."""

    def test_text_message_backward_compat(self):
        from larky.wechat_models import WeChatMessage
        from larky.wechat_service import _build_incoming_payload

        msg = WeChatMessage.from_dict(
            {
                "seq": 1,
                "message_id": 200,
                "from_user_id": "u1",
                "item_list": [{"type": 1, "text_item": {"text": "hello world"}}],
            }
        )
        payload = _build_incoming_payload(msg)
        # Backward-compatible fields
        assert payload["from_user_id"] == "u1"
        assert payload["text"] == "hello world"
        assert payload["message_id"] == 200
        # New fields
        assert payload["has_media"] is False
        assert payload["media_type"] is None
        assert len(payload["items"]) == 1
        assert payload["items"][0]["text"] == "hello world"

    def test_image_message_with_cdn(self):
        from larky.wechat_models import WeChatMessage
        from larky.wechat_service import _build_incoming_payload

        msg = WeChatMessage.from_dict(
            {
                "seq": 1,
                "message_id": 201,
                "from_user_id": "u1",
                "session_id": "sess_abc",
                "context_token": "ctx_xyz",
                "message_type": 1,
                "message_state": 2,
                "item_list": [
                    {
                        "type": 2,
                        "image_item": {
                            "aeskey": "ka1",
                            "url": "https://example.com/photo.jpg",
                            "media": {
                                "encrypt_query_param": "eq1",
                                "aes_key": "ak1",
                                "encrypt_type": 1,
                            },
                        },
                    }
                ],
            }
        )
        payload = _build_incoming_payload(msg)
        assert payload["session_id"] == "sess_abc"
        assert payload["context_token"] == "ctx_xyz"
        assert payload["message_type"] == "USER"
        assert payload["message_state"] == "FINISH"
        assert payload["has_media"] is True
        assert payload["media_type"] == "IMAGE"
        img_item = payload["items"][0]
        assert img_item["image"]["url"] == "https://example.com/photo.jpg"
        assert img_item["image"]["media"]["aes_key"] == "ak1"

    def test_file_message_with_cdn(self):
        from larky.wechat_models import WeChatMessage
        from larky.wechat_service import _build_incoming_payload

        msg = WeChatMessage.from_dict(
            {
                "seq": 1,
                "message_id": 202,
                "from_user_id": "u1",
                "item_list": [
                    {
                        "type": 4,
                        "file_item": {
                            "file_name": "report.pdf",
                            "md5": "d41d8cd98f00b204e9800998ecf8427e",
                            "len": "2048",
                            "media": {
                                "encrypt_query_param": "fq1",
                                "aes_key": "fk1",
                                "encrypt_type": 2,
                            },
                        },
                    }
                ],
            }
        )
        payload = _build_incoming_payload(msg)
        file_item = payload["items"][0]
        assert file_item["file"]["file_name"] == "report.pdf"
        assert file_item["file"]["md5"] == "d41d8cd98f00b204e9800998ecf8427e"
        assert file_item["file"]["media"]["aes_key"] == "fk1"


# ═══════════════════════════════════════════════════════════════════════
# Test: Exponential backoff in getUpdates loop
# ═══════════════════════════════════════════════════════════════════════


class TestExponentialBackoff:
    """getUpdates error loop must use exponential backoff (not fixed 5s)."""

    def test_backoff_resets_on_success(self):
        """Backoff should reset to 1.0 after a successful get_updates call."""
        # The backoff logic is embedded in the run() loop. We verify
        # the pattern by inspecting the source.
        import inspect
        from larky.wechat_bot import WeChatBot

        source = inspect.getsource(WeChatBot.run)
        assert "backoff = 1.0" in source, "Should initialize backoff at 1.0s"
        assert "backoff = min(backoff * 2, 60.0)" in source, (
            "Should double backoff capped at 60s"
        )
        # After a successful get_updates call, backoff must reset:
        # Look for "backoff = 1.0" appearing AFTER the get_updates call
        lines = source.split("\n")
        reset_line = None
        get_updates_line = None
        for i, line in enumerate(lines):
            if "get_updates()" in line:
                get_updates_line = i
            if get_updates_line is not None and "backoff = 1.0" in line:
                reset_line = i
                break
        assert reset_line is not None, "backoff reset after get_updates not found"
        assert reset_line > get_updates_line, (
            "backoff reset must come AFTER get_updates call"
        )


# ═══════════════════════════════════════════════════════════════════════
# Test: CHANNEL_VERSION env override
# ═══════════════════════════════════════════════════════════════════════


class TestChannelVersionEnvOverride:
    """WECHAT_CHANNEL_VERSION env var must override the hardcoded default."""

    def test_default_version(self):
        import importlib
        import larky.wechat_config

        importlib.reload(larky.wechat_config)
        assert larky.wechat_config.CHANNEL_VERSION == "2.4.6"

    def test_env_override(self):
        import importlib
        import larky.wechat_config

        os.environ["WECHAT_CHANNEL_VERSION"] = "3.0.0"
        importlib.reload(larky.wechat_config)
        assert larky.wechat_config.CHANNEL_VERSION == "3.0.0"
        del os.environ["WECHAT_CHANNEL_VERSION"]
        importlib.reload(larky.wechat_config)
