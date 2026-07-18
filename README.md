# Larky

A lightweight async bot framework supporting Feishu (Lark), QQ, and WeChat bots — designed for quantitative trading notification scenarios.

> 📖 [中文文档](README_CN.md)

## Features

- **Async Architecture**: Built on aiohttp for high-performance async I/O
- **Lightweight Dependencies**: Only requires aiohttp, python-dotenv, pycryptodome, and qrcode
- **Multi-Platform**: Feishu bot + QQ bot + WeChat bot
- **Auto Authentication**: Automatic access_token management with refresh-on-expiry
- **Decorator Style**: Elegant message/command handler registration
- **Type Hints**: Complete type annotations for IDE-friendly development
- **WeChat QR Login**: Scan a QR code in the terminal to log in
- **Credential Persistence**: Auto-saved login credentials, compatible with the official openclaw plugin
- **Proactive Push**: WeChat bot supports proactive message push, ideal for trading notifications
- **Session Guard**: Automatic pause and email notification when session expires
- **Data Persistence**: Context tokens and sync buffers auto-persisted, survive restarts

## Installation

```bash
uv sync
```

## Configuration

Copy `.env.example` to `.env` and fill in the configuration:

```env
# Feishu bot configuration
APP_ID=cli_xxx
APP_SECRET=xxx
VERIFICATION_TOKEN=xxx
ENCRYPT_KEY=
LARK_HOST=https://open.feishu.cn
OPEN_ID=

# QQ bot configuration
QQ_APP_ID=xxx
QQ_APP_SECRET=xxx

# WeChat bot — no configuration needed, just scan the QR code
```

| Variable | Description | Required |
|----------|-------------|----------|
| `APP_ID` | Feishu app ID | Feishu |
| `APP_SECRET` | Feishu app secret | Feishu |
| `QQ_APP_ID` | QQ bot app ID | QQ |
| `QQ_APP_SECRET` | QQ bot app secret | QQ |

> **WeChat bot requires no configuration**: Just run `uv run python wechat_main.py`, scan the QR code, and you're ready. No `.env` parameters needed.

## Quick Start

### Feishu Bot

```python
import asyncio
from larky import LarkBot, Message, WebhookServer

async def main():
    bot = LarkBot.from_env()

    @bot.on_message
    async def handle_message(msg: Message):
        await bot.reply_text(msg, f"Received: {msg.get_text()}")

    @bot.on_command("ping")
    async def ping(msg: Message, args: list):
        await bot.reply_text(msg, "Pong!")

    async with bot:
        server = WebhookServer(bot, port=3000)
        await server.start()
        await asyncio.Event().wait()

asyncio.run(main())
```

### QQ Bot

```python
import asyncio
from larky import QQBot, QQMessage

async def main():
    bot = QQBot.from_env()

    @bot.on_message
    async def handle_message(msg: QQMessage):
        if not msg.is_command():
            await bot.reply_text(msg, f"Received: {msg.content}")

    @bot.on_command("time")
    async def time_cmd(msg: QQMessage, args: list):
        from datetime import datetime
        await bot.reply_text(msg, f"Time: {datetime.now():%H:%M:%S}")

    await bot.run()

asyncio.run(main())
```

### WeChat Bot

```python
import asyncio
from larky import WeChatBot, WeChatMessage

async def main():
    bot = WeChatBot.from_env()

    @bot.on_message
    async def handle_message(msg: WeChatMessage):
        if not msg.is_command():
            await bot.reply_text(msg, f"Received: {msg.get_text()}")

    @bot.on_command("time")
    async def time_cmd(msg: WeChatMessage, args: list):
        from datetime import datetime
        await bot.reply_text(msg, f"Time: {datetime.now():%H:%M:%S}")

    # Send welcome message on startup (trading notification use case)
    async def on_ready():
        if bot.get_user_id():
            await bot.notify("🤖 Bot is online!")

    await bot.run(on_ready=on_ready)

asyncio.run(main())
```

## API Reference

### Feishu LarkBot

```python
bot = LarkBot.from_env()

# Send messages
await bot.send_text("Hello", open_id="ou_xxx")
await bot.reply_text(message, "Reply")

# Register handlers
@bot.on_message
async def handler(msg: Message): ...

@bot.on_command("cmd")
async def cmd(msg: Message, args: list): ...
```

### QQ QQBot

```python
bot = QQBot.from_env()

# Send messages
await bot.send_text("Hello", openid="xxx")
await bot.reply_text(message, "Reply")

# Register handlers
@bot.on_message
async def handler(msg: QQMessage): ...

@bot.on_command("cmd")
async def cmd(msg: QQMessage, args: list): ...
```

### WeChat WeChatBot

```python
bot = WeChatBot.from_env()

# Proactive push (defaults to bound user — recommended for trading notifications)
await bot.notify("📈 BTC broke key resistance level")

# Reply to messages
await bot.reply_text(message, "Reply")

# Get the bound user ID
user_id = bot.get_user_id()

# Send typing indicator
await bot.send_typing(to_user_id, typing=True)

# Register handlers
@bot.on_message
async def handler(msg: WeChatMessage): ...

@bot.on_command("cmd")
async def cmd(msg: WeChatMessage, args: list): ...

# Bot-ready callback
async def on_ready():
    await bot.notify("Bot is online")

await bot.run(on_ready=on_ready)
```

### Message Objects

**Feishu Message**:
```python
msg.message_id       # Message ID
msg.content          # Message content
msg.sender_open_id   # Sender open_id
msg.get_text()       # Get text content
msg.is_command()     # Check if it's a command
msg.get_command()    # Get command and arguments
```

**QQ QQMessage**:
```python
msg.message_id       # Message ID
msg.content          # Message content
msg.author_openid    # Sender openid
msg.is_command()     # Check if it's a command
msg.get_command()    # Get command and arguments
```

**WeChat WeChatMessage**:
```python
msg.message_id       # Message ID
msg.from_user_id     # Sender ID (xxx@im.wechat)
msg.get_text()       # Get text content
msg.is_command()     # Check if it's a command
msg.get_command()    # Get command and arguments
msg.has_media()      # Check for media attachments
msg.get_media_type() # Get media type
msg.context_token    # Context token (used for replies)
```

## Running

```bash
# Feishu bot
uv run python main.py

# QQ bot
uv run python qq_main.py

# WeChat bot
uv run python wechat_main.py
```

## WeChat Bot In Depth

### QR Code Login

On first run, a QR code is displayed in the terminal:

```
==================================================
Please scan the QR code with WeChat to log in:
==================================================
█▀▀▀▀▀▀▀██▀██████▀██▀█▀▀▀▀█▀███▀▀▀▀▀▀▀█
█ █▀▀▀█ █▄ ▀ ▄█  ███▀▀ ▄▀▀▄ ▄ █ █▀▀▀█ █
...
==================================================
```

Scan the code with WeChat to authorize and log in.

### Credential Storage

After a successful login, credentials are saved locally:

```
~/.openclaw/openclaw-weixin/
├── accounts.json          # Account index
└── accounts/
    └── <account_id>.json  # Account credentials
```

**No re-scan needed on subsequent runs** — saved accounts are loaded automatically.

### Compatible with the Official openclaw Plugin

The storage format is fully compatible with the official `@tencent-weixin/openclaw-weixin` npm plugin:

- Log in with the Python version, then use the official npm plugin directly
- Log in with the official npm plugin, then use the Python version directly
- Both share the `~/.openclaw/` state directory

### No Public IP Required

The WeChat bot uses HTTP long-polling to receive messages — no:
- Public IP
- Webhook callback URL
- Port forwarding

### Token Lifetime

- Tokens are typically valid for extended periods (days to weeks)
- When a token expires, re-scan the QR code to log in again
- Logging into the same account on another device invalidates the current token

### Session Guard

When the WeChat server returns a session expiry error (errcode -14), the system will:

1. **Pause for 1 hour**: Avoid repeated invalid requests that could lead to an IP ban
2. **Send email notification**: Alert the user to re-scan the QR code
3. **Auto-recovery**: The pause is cleared automatically after re-login

**Triggers**:
- The bot was deleted/unlinked in WeChat
- The token expired from prolonged inactivity

**Email notification configuration**:

```env
BACKUP_EMAIL_FROM=bot@example.com
BACKUP_EMAIL_TO=your@email.com
BACKUP_EMAIL_SMTP=smtp.gmail.com
BACKUP_EMAIL_PORT=587
BACKUP_EMAIL_USER=your@gmail.com
BACKUP_EMAIL_PASSWORD=your-app-password
SERVER_NAME=my-server  # Optional, identifies the server in emails
```

> **Port notes**:
> - `587`: STARTTLS connection
> - `465`: Direct SSL connection (recommended for Chinese email providers like 139, QQ Mail)

### Data Persistence

The WeChat bot automatically persists the following data, surviving restarts:

```
~/.openclaw/openclaw-weixin/accounts/
├── <account_id>.json               # Account credentials (token, baseUrl, userId)
├── <account_id>.sync.json          # Message sync buffer (get_updates_buf)
└── <account_id>.context-tokens.json # Context tokens (used for message replies)
```

**Persisted content**:
| File | Purpose |
|------|---------|
| `*.json` | Login credentials — avoid re-scanning |
| `*.sync.json` | Message sync position — prevent lost/duplicate messages |
| `*.context-tokens.json` | Reply tokens — ensure messages are delivered correctly |

### Proactive Push

The WeChat bot supports proactive push messages, ideal for quantitative trading notifications:

```python
# Simplest usage — just one line
await bot.notify("📈 BTC broke $100,000")
```

`notify()` automatically sends to the bound user — no need to specify `to_user_id`.

### on_ready Callback

`on_ready` is a callback that executes once the bot is **fully ready**. Use it for:
- Sending startup notifications
- Launching background tasks
- Initializing resources

```python
async def on_ready():
    # Bot is logged in — safe to send messages
    if bot.get_user_id():
        await bot.notify("🤖 Bot is online")

await bot.run(on_ready=on_ready)
```

**Why on_ready?**

The `run()` method performs the login flow internally. Calling `notify()` before login completes will fail. `on_ready` ensures your code only runs after login is done.

```python
# ❌ Wrong: calling before run() will fail
await bot.notify("Starting")  # Error: Not logged in
await bot.run()

# ✅ Correct: call inside on_ready
async def on_ready():
    await bot.notify("Starting")
await bot.run(on_ready=on_ready)
```

### Quantitative Trading Notification Example

A complete trading notification example:

```python
import asyncio
from larky import WeChatBot, WeChatMessage

bot = WeChatBot.from_env()

async def price_monitor():
    """Monitor price and send notification on breakout"""
    while True:
        price = await get_btc_price()
        if price > 100000:
            await bot.notify(f"📈 BTC broke $100,000! Current: ${price:,}")
        await asyncio.sleep(60)

async def on_ready():
    # Send startup notification
    await bot.notify("🤖 Trading bot started")
    # Launch price monitor
    asyncio.create_task(price_monitor())

async def main():
    @bot.on_command("status")
    async def status(msg: WeChatMessage, args: list):
        price = await get_btc_price()
        await bot.reply_text(msg, f"📊 Current BTC price: ${price:,}")

    await bot.run(on_ready=on_ready)

asyncio.run(main())
```

### Multi-Process Architecture

When multiple trading programs need to share one WeChat account, use the `WeChatService` + `WeChatClient` architecture:

```
┌─────────────────────────────────────────────────────────┐
│                       Server                             │
│                                                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐ │
│  │  Bot A      │    │  Bot B      │    │  Bot C      │ │
│  │ (BTC watch) │    │ (ETH watch) │    │ (Arbitrage) │ │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘ │
│         │                  │                  │        │
│         └──────────────────┼──────────────────┘        │
│                            ▼                           │
│                   ┌─────────────────┐                  │
│                   │   Redis Pub/Sub │                  │
│                   └────────┬────────┘                  │
│                            │                           │
│                            ▼                           │
│                   ┌─────────────────┐                  │
│                   │  WeChatService  │ ← single WeChat  │
│                   └─────────────────┘   connection     │
└─────────────────────────────────────────────────────────┘
```

**Startup steps:**

```bash
# 1. Start Redis
redis-server

# 2. Start WeChat message service (the single WeChat connection)
uv run python -m larky

# 3. Start trading programs (multiple can run simultaneously)
uv run python examples/trading_bot_btc.py
uv run python examples/trading_bot_eth.py
```

**Trading programs use WeChatClient:**

```python
from larky import WeChatClient

client = WeChatClient(source="btc-monitor")

# Send notifications
await client.notify("📈 BTC broke $100,000")

# Receive messages
@client.message_handler
async def on_message(data: dict):
    text = data.get("text", "")
    if "price" in text:
        await client.notify(f"Current price: ${await get_price()}")

await client.run()
```

**Environment variables:**

```env
REDIS_URL=redis://localhost:6379
# or
REDIS_HOST=localhost
REDIS_PORT=6379
```

### Fault Handling

The WeChat message service includes these fault-handling mechanisms:

**1. Auto-Reconnect on Disconnect**

When the network drops, the service automatically reconnects (default: up to 10 retries).

**2. Session Guard**

When the WeChat server returns a session expiry error (errcode -14):
- Auto-pauses the service for 1 hour to avoid IP bans from repeated requests
- Sends email notification to re-scan the QR code
- Auto-resumes after re-login

See [Session Guard](#session-guard) above for email configuration.

**3. Message Priority & Backup Delivery**

Messages from trading programs support two priority levels:

```python
# Normal priority (default) — dropped when offline
await client.notify("📊 Daily report", priority="normal")

# High priority — email backup when offline + redelivered on recovery
await client.notify("🚨 URGENT: Stop-loss triggered", priority="high")
```

| Priority | Online | Offline |
|----------|--------|---------|
| `normal` (default) | Sent via WeChat | Dropped |
| `high` | Sent via WeChat | 1. Queued for later<br>2. Email backup sent in parallel<br>3. Auto-redelivered when WeChat recovers |

**Usage examples:**

```python
# Daily report — normal priority, no need to notify when offline
await client.notify("📊 Daily P&L: +$1,234", priority="normal")

# Important trade signal — high priority, must be delivered
await client.notify("🚨 Stop-loss triggered: BTC below $95,000", priority="high")

# Risk alert — high priority
await client.notify("⚠️ Margin call — action required", priority="high")
```

**4. Status Monitoring**

Clients can listen for service status changes:

```python
@client.status_handler
async def on_status(data: dict):
    if data.get("need_login"):
        # Service needs re-login
        logger.warning("WeChat service needs QR re-scan")
    elif data.get("status") == "offline":
        # Service is offline
        logger.warning("WeChat service offline")
```

## Platform Setup

### Feishu Open Platform

1. Create a custom app on the [Feishu Open Platform](https://open.feishu.cn/)
2. Enable the bot capability
3. Configure event subscriptions, add the `im.message.receive_v1` event
4. Set the webhook URL

### QQ Open Platform

1. Create a bot on the [QQ Open Platform](https://q.qq.com/)
2. Obtain the App ID and App Secret
3. Uses WebSocket connections — no callback URL needed

### WeChat Bot

The WeChat bot is built on the `@tencent-weixin/openclaw-weixin` protocol — no open-platform developer account required.

## Project Structure

```
larky/
├── larky/
│   ├── __init__.py
│   ├── __main__.py         # WeChat message service entry point
│   ├── bot.py              # Feishu LarkBot
│   ├── config.py           # Feishu configuration
│   ├── handlers.py         # Feishu webhook
│   ├── models.py           # Feishu models
│   ├── qq_bot.py           # QQ bot core
│   ├── qq_config.py        # QQ configuration
│   ├── qq_models.py        # QQ models
│   ├── wechat_bot.py       # WeChat bot core
│   ├── wechat_config.py    # WeChat configuration
│   ├── wechat_models.py    # WeChat models
│   └── wechat_service.py   # WeChat message service (multi-process)
├── examples/
│   ├── trading_bot_btc.py  # BTC monitoring example
│   └── trading_bot_eth.py  # ETH monitoring example
├── tests/
│   └── test_wechat_priority.py  # WeChat priority feature tests
├── main.py                 # Feishu example
├── qq_main.py              # QQ example
├── wechat_main.py          # WeChat example
└── pyproject.toml
```

## Using in Other Projects

### Option 1: Local Path Install (Recommended)

Add to the target project's `pyproject.toml`:

```toml
[project]
dependencies = [
    "larky @ file:///path/to/larky",
]
```

Or with uv:

```bash
uv add /path/to/larky
```

### Option 2: Git Install

```bash
# From GitHub
uv add git+https://github.com/hylyq/larky.git

# From Gitee (China mirror)
uv add git+https://gitee.com/JiyunMa/larky.git
```

Or in `pyproject.toml`:

```toml
[project]
dependencies = [
    "larky @ git+https://github.com/hylyq/larky.git",
    # Or the Gitee mirror:
    # "larky @ git+https://gitee.com/JiyunMa/larky.git",
]
```

### Option 3: Publish to PyPI

```bash
uv build
uv publish
```

Then other projects can install directly:

```bash
uv add larky
```

### Usage Example

```python
import asyncio
from larky.wechat_service import WeChatClient

async def main():
    client = WeChatClient(source="my-trading-bot")

    @client.message_handler
    async def on_message(data: dict):
        text = data.get("text", "")
        if "status" in text:
            await client.notify("✅ Service running normally")

    await client.run()

asyncio.run(main())
```

**Environment variables** (`.env`):

```env
REDIS_URL=redis://localhost:6379
# or
REDIS_HOST=localhost
REDIS_PORT=6379
```

## Tests

Run unit tests:

```bash
# Run WeChat priority feature tests
uv run python tests/test_wechat_priority.py
```

## Dependencies

- Python >= 3.13
- aiohttp >= 3.9.0
- python-dotenv >= 1.0.0
- pycryptodome >= 3.20.0
- qrcode >= 8.2
- redis >= 5.0.0

## Maintaining WeChat Protocol Compatibility

The WeChat bot is a Python reimplementation of the official `@tencent-weixin/openclaw-weixin` npm plugin's iLink protocol. When the official plugin updates, the WeChat server may require new fields, reject old protocol versions, or change API behavior — all without public documentation. The following process helps diagnose and fix such issues by comparing against the official TypeScript source code.

### When to Suspect a Protocol Drift

- Messages stop being delivered but **no errors appear in logs** (API returns HTTP 200 + business error in response body)
- WeChat receives messages but the bot cannot send (or vice versa)
- The official npm plugin has released a new version recently
- The bot was working fine yesterday but stopped today

### Diagnostic Process

**1. Check the latest official plugin version:**

```bash
npm view @tencent-weixin/openclaw-weixin version
```

**2. Download and inspect the official source code:**

The npm package includes full TypeScript source (`.ts` files), not just compiled output:

```bash
mkdir /tmp/openclaw-weixin && cd /tmp/openclaw-weixin
npm pack @tencent-weixin/openclaw-weixin
tar xzf tencent-weixin-openclaw-weixin-*.tgz
```

**3. Compare key files against larky's implementation:**

| Official Source | larky Equivalent | What to Check |
|---|---|---|
| `package/src/api/api.ts` | `larky/wechat_bot.py:_api_request` | Request payload structure, `base_info` fields, error handling |
| `package/src/api/types.ts` | `larky/wechat_models.py` | Message field definitions, new enum values, new interfaces |
| `package/src/messaging/send.ts` | `larky/wechat_bot.py:send_text` | `sendmessage` payload format, required fields |
| `package/src/messaging/inbound.ts` | `larky/wechat_bot.py:get_updates` | Context token handling, message parsing |
| `package/src/channel.ts` | `larky/wechat_service.py` | Startup/shutdown lifecycle, `notifyStart`/`notifyStop` |
| `package/src/api/session-guard.ts` | `larky/wechat_bot.py:SessionGuard` | Session expiry error codes |

**4. Common sources of drift:**

| Area | What to Check | Example |
|---|---|---|
| `base_info` | Every API request must include `{"base_info": {"channel_version": "...", "bot_agent": "..."}}` — not just `getupdates` | 2026-07: `sendmessage` was missing `base_info` → `ret=-2 prepare failed` |
| `CHANNEL_VERSION` | Must match the latest npm package version | Set in `wechat_config.py`, read from `package.json `version` field in the npm package |
| New endpoints | Official plugin may call lifecycle endpoints on startup/shutdown | `notifyStart` / `notifyStop` were added to the official plugin |
| New message types | Check `MessageItemType` and `MessageType` enums | Official v2.4.6 added `TOOL_CALL_START=11`, `TOOL_CALL_RESULT=12` |
| Headers | Verify `iLink-App-Id`, `iLink-App-ClientVersion`, `SKRouteTag` | Compare `buildCommonHeaders()` in official `api.ts` |
| Error handling | `sendmessage` should throw on `ret != 0`; `getUpdates` handles errors gracefully | Official `api.ts:515` checks `resp.ret !== 0` |

**5. Update CHANNEL_VERSION and retest:**

After fixing protocol issues, update `wechat_config.py`:

```python
CHANNEL_VERSION = "2.4.6"  # Set to match npm package version
```

Then deploy and verify with `LOG_LEVEL=DEBUG` to confirm API responses show `ret=0`.

### Example: 2026-07 Protocol Fix

**Symptom**: Messages appeared to send successfully in logs, but WeChat client never received them.

**Investigation**:
1. Downloaded `@tencent-weixin/openclaw-weixin@2.4.6` and inspected `api.ts:sendMessage()`
2. Found the official code wraps every API call with `base_info: buildBaseInfo()`:
   ```typescript
   body: JSON.stringify({ ...params.body, base_info: buildBaseInfo() })
   ```
3. larky only included `base_info` in `getUpdates` — `sendmessage`, `getconfig`, and `sendtyping` were all missing it

**Fix**: Added `base_info` to all API request payloads, added `notifyStart`/`notifyStop` lifecycle calls, bumped `CHANNEL_VERSION` to `2.4.6`. Also added `_api_request` response body logging to surface business error codes in the future.

---

## Changelog

### 2026-07-18 (evening) — Context Token Keepalive & Queue Resilience

- **Context token activation**: Mirror official plugin behavior — call `getConfig` API with fresh `context_token` on every inbound message to register/activate the token with the WeChat server, extending its lifetime (was: token only stored, never activated)
- **Failed message queue**: Added `wechat:failed_messages` queue for messages that fail due to expired context_token, preventing them from blocking the main pending queue
- **Smarter retry**: Removed pointless 3-retry loop for `prepare failed` errors — expired tokens don't fix themselves; messages now move directly to failed queue with email backup
- **Event-driven queue processing**: `_process_pending_messages` now wakes immediately on new inbound messages (fresh context_token) instead of waiting 30s
- **More frequent keepalive**: Default `WECHAT_KEEPALIVE_INTERVAL_SEC` reduced from 4h to 30min
- **Queue drain resilience**: `_drain_queue()` processes all queued messages without blocking on single failures; prevents infinite loops with initial-count tracking

### 2026-07-18 — Protocol Sync with @tencent-weixin/openclaw-weixin v2.4.6

- **Critical**: Added `base_info` (channel_version + bot_agent) to `sendmessage`, `getconfig`, and `sendtyping` API requests — matches official plugin v2.4.6 payload format. Fixes `ret=-2 prepare failed` when sending messages.
- Added `notifyStart` and `notifyStop` lifecycle API calls on bot startup/shutdown
- Added `check_context_health()` method and periodic keepalive probe (every 4h, configurable via `WECHAT_KEEPALIVE_INTERVAL_SEC`)
- `send_text` auto-retries once without context_token on `prepare failed`, then requeues with backoff (max 3 retries)
- API responses now logged at DEBUG level (success) / ERROR level (business errors with non-zero ret/errcode)
- Fixed stale context token file not being deleted when all tokens cleared
- Fixed missing `notify_stop` call on service shutdown

### 2026-04-05 — WeChat Protocol Adaptation Update

Adapted to WeChat official `@tencent-weixin/openclaw-weixin` v2.1.6 protocol changes:

**API Changes**:
- Added required `iLink-App-Id` and `iLink-App-ClientVersion` HTTP headers
- Support for dynamic `longpolling_timeout_ms` adjustment

**Session Guard**:
- Auto-pause for 1 hour on session expiry (errcode -14)
- Email notification for QR re-scan
- Auto-recovery after re-login

**QR Login Enhancements**:
- Support for `scaned_but_redirect` IDC redirection
- Auto-refresh expired QR codes (up to 3 times)
- Real-time scan status feedback

**Data Persistence**:
- Context tokens persisted to `*.context-tokens.json`
- Sync buffer persisted to `*.sync.json`
- State auto-restored after service restart

## License

MIT
