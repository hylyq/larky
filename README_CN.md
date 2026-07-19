# Larky

轻量级异步机器人模块，支持飞书 Lark、QQ 和微信机器人，专为量化交易通知场景设计。

> 📖 [English Documentation](README.md)

## 特性

- **🎯 统一 API（新功能！）**: 一次编写，多平台运行。通过一个环境变量在飞书/微信/QQ 之间切换 —— 零代码改动
- **异步架构**：基于 aiohttp，高性能异步 I/O
- **轻量依赖**：仅需 aiohttp、python-dotenv、pycryptodome、qrcode
- **多平台支持**：飞书机器人 + QQ机器人 + 微信机器人
- **自动认证**：自动管理 access_token，过期自动刷新
- **装饰器风格**：优雅的消息/指令处理器注册方式
- **类型提示**：完整的类型注解， IDE 友好
- **微信扫码登录**：终端显示二维码，扫码即可登录
- **凭证持久化**：登录信息自动保存，与官方 openclaw 插件兼容
- **主动推送**：支持主动推送消息，适合量化交易通知场景
- **会话保护**：Session Guard 机制，会话过期自动暂停并邮件通知
- **数据持久化**：Context Token 和同步缓冲区自动持久化，重启不丢失

## 安装

```bash
uv sync
```

## 配置

复制 `.env.example` 为 `.env` 并填入配置：

```env
# ===== 平台选择 =====
# 可选值: feishu / wechat / qq
BOT_PLATFORM=feishu

# ===== 飞书机器人配置（BOT_PLATFORM=feishu 时必填）=====
APP_ID=cli_xxx
APP_SECRET=xxx
VERIFICATION_TOKEN=xxx
ENCRYPT_KEY=
LARK_HOST=https://open.feishu.cn
OPEN_ID=

# ===== QQ机器人配置（BOT_PLATFORM=qq 时必填）=====
QQ_APP_ID=xxx
QQ_APP_SECRET=xxx

# ===== 微信机器人无需配置，扫码登录即可使用 =====
```

| 配置项 | 说明 | 必填 |
|--------|------|------|
| `BOT_PLATFORM` | 平台选择：`feishu` / `wechat` / `qq` | 全部（默认 `feishu`） |
| `APP_ID` | 飞书应用的 App ID | 飞书必填 |
| `APP_SECRET` | 飞书应用的 App Secret | 飞书必填 |
| `QQ_APP_ID` | QQ机器人的 App ID | QQ必填 |
| `QQ_APP_SECRET` | QQ机器人的 App Secret | QQ必填 |

> **微信机器人无需配置**：设置 `BOT_PLATFORM=wechat`，运行 `uv run python unified_main.py`，扫码登录即可使用，不需要在 `.env` 文件中配置任何参数。

## 快速开始

### 🎯 统一 API（推荐）

统一 API 让你只需编写一次代码，通过修改 `.env` 中的一行配置即可切换平台。**这是使用 larky 的推荐方式。**

```python
import asyncio
from larky import UnifiedBot, UnifiedMessage

async def main():
    # 平台由 .env 中的 BOT_PLATFORM 控制 —— 代码无需任何改动！
    bot = UnifiedBot()

    @bot.on_message
    async def handle_message(msg: UnifiedMessage):
        """处理非指令消息。"""
        if not msg.is_command("/"):
            await msg.reply(f"收到: {msg.get_text()}\n发送 /help 查看命令")

    @bot.on_command("help")
    async def cmd_help(msg: UnifiedMessage, args: list):
        await msg.reply("命令列表: /help /time /echo /info")

    @bot.on_command("time")
    async def cmd_time(msg: UnifiedMessage, args: list):
        from datetime import datetime
        await msg.reply(f"⏰ {datetime.now():%Y-%m-%d %H:%M:%S}")

    @bot.on_command("echo")
    async def cmd_echo(msg: UnifiedMessage, args: list):
        await msg.reply("📢 " + (" ".join(args) if args else "请输入内容"))

    @bot.on_command("info")
    async def cmd_info(msg: UnifiedMessage, args: list):
        await msg.reply(f"平台: {msg.platform}\n发送者: {msg.sender_id}")

    # 启动回调
    async def on_ready(bot: UnifiedBot):
        await bot.send_text("🤖 机器人已上线！")

    await bot.run(on_ready=on_ready)

asyncio.run(main())
```

**切换平台只需修改 `.env` 中的一行：**

```bash
# 切换到飞书（需 APP_ID + APP_SECRET）
BOT_PLATFORM=feishu

# 切换到微信（无需配置 —— 扫码登录）
BOT_PLATFORM=wechat

# 切换到 QQ（需 QQ_APP_ID + QQ_APP_SECRET）
BOT_PLATFORM=qq
```

运行：
```bash
uv run python unified_main.py
```

### ⚖️ 平台对比

根据你的需求选择合适的平台：

| | 🟢 飞书 | 🔵 微信 | 🟣 QQ |
|---|---|---|---|
| **主动推送** | ✅ 即时发送，无需用户互动 | ⚠️ 用户必须先发消息激活上下文 | ✅ 即时发送 |
| **保活** | ✅ 不需要（Webhook 推送） | ❌ 用户需定期发消息保持上下文有效 | ✅ 不需要（WebSocket 心跳） |
| **需要公网 IP** | ✅ 是（Webhook 回调） | ✅ 否（长轮询） | ✅ 否（WebSocket） |
| **配置复杂度** | 中等（创建应用 + 配置回调） | 简单（扫码即可） | 中等（创建应用） |
| **Token 管理** | 自动刷新 | 过期需重新扫码 | 自动刷新 |
| **消息可靠性** | 高（官方 API） | 中（逆向 iLink 协议） | 高（官方 API） |

> **⚠️ 微信的关键缺陷 —— "保活"问题：**
>
> 微信机器人使用 `context_token` 机制：机器人只有在**用户先发送消息激活上下文后**才能
> 主动推送消息。如果用户长时间不跟机器人互动，`context_token` 会过期，主动推送将失效
> —— 用户必须再发一条消息来重新激活。
>
> 这意味着微信**不适合纯通知场景**——即你希望机器人主动推送告警、而不需要用户定期
> "拍一拍"它才能保持活跃。
>
> **如果你需要可靠的主动推送，请使用飞书或 QQ。** 它们支持随时发送消息，无需用户
> 事先互动。
>
> 但微信也有优势：配置最简单（扫码即可，无需申请开发者账号），非常适合用户频繁
> 主动交互的指令型机器人场景。

### 🔄 迁移指南：微信 → 飞书（Redis + 邮件）

如果你正在运行旧的微信 + Redis + 邮件备份方案（`WeChatService` + `WeChatClient`），
迁移到飞书只需三步，代码改动极小。

**第一步 — 更新 `.env`：**

```diff
+ BOT_PLATFORM=feishu
+ APP_ID=cli_xxxxxxxx
+ APP_SECRET=xxxxxxxxxxxx
+ VERIFICATION_TOKEN=xxxxxx

  # 以下配置完全不变
  REDIS_HOST=localhost
  REDIS_PORT=6379
  BACKUP_EMAIL_TO=your@email.com
  BACKUP_EMAIL_SMTP=smtp.gmail.com
  ...
```

**第二步 — 服务端：命令不变，底层切换：**

```bash
# 旧（微信）
uv run python -m larky

# 新（飞书）— 命令完全一样！
uv run python -m larky
# 🚀 统一消息服务启动中 [platform=feishu]...
```

> **飞书需要公网可达的 Webhook 地址。** 在[飞书开放平台](https://open.feishu.cn/)
> 的事件订阅中配置 `http://<你的服务器IP>:3000/`，并在云防火墙放行 3000 端口。
> 详见上方 [飞书开放平台](#飞书开放平台)。

**第三步 — 量化程序：改两行代码：**

```diff
- from larky import WeChatClient
+ from larky import UnifiedClient

- client = WeChatClient(source="btc-monitor")
+ client = UnifiedClient(source="btc-monitor")

  # 以下完全不变！
  await client.notify("📈 BTC 突破 $100,000")
  await client.notify("🚨 止损触发", priority="high")

  @client.message_handler
  async def on_message(data: dict):
      text = data.get("text", "")
      ...

  @client.status_handler
  async def on_status(data: dict):
      ...

  await client.run()
```

**迁移前后对比：**

| | 旧（微信） | 新（飞书） |
|---|---|---|
| 服务端命令 | `python -m larky` | `python -m larky`*（不变）* |
| 客户端类 | `WeChatClient` | `UnifiedClient` |
| Redis 频道 | `wechat:*` | `bot:*` |
| 登录方式 | 终端扫码 | 飞书开放平台配置 |
| 主动推送 | 需用户先发消息激活 | 即时发送 ✅ |
| 公网要求 | 不需要 | **需要**（端口 3000） |

> **⚠️ 积压消息注意：** 新 Redis 前缀为 `bot:`（旧为 `wechat:`），
> `wechat:pending_messages` 中的历史积压消息不会自动迁移。请先在旧微信服务下
> 让它们发送完毕，或手动处理后再切换。

### 平台特定 API

如果你需要使用平台特定功能（如微信输入状态、媒体访问等），仍然可以直接使用各个 bot 类。统一 API 构建于它们之上，原有的 API 继续可用。

#### 飞书机器人

```python
import asyncio
from larky import LarkBot, Message, WebhookServer

async def main():
    bot = LarkBot.from_env()
    
    @bot.on_message
    async def handle_message(msg: Message):
        await bot.reply_text(msg, f"收到: {msg.get_text()}")
    
    @bot.on_command("ping")
    async def ping(msg: Message, args: list):
        await bot.reply_text(msg, "Pong!")
    
    async with bot:
        server = WebhookServer(bot, port=3000)
        await server.start()
        await asyncio.Event().wait()

asyncio.run(main())
```

### QQ机器人

```python
import asyncio
from larky import QQBot, QQMessage

async def main():
    bot = QQBot.from_env()
    
    @bot.on_message
    async def handle_message(msg: QQMessage):
        if not msg.is_command():
            await bot.reply_text(msg, f"收到: {msg.content}")
    
    @bot.on_command("time")
    async def time_cmd(msg: QQMessage, args: list):
        from datetime import datetime
        await bot.reply_text(msg, f"时间: {datetime.now():%H:%M:%S}")
    
    await bot.run()

asyncio.run(main())
```

### 微信机器人

```python
import asyncio
from larky import WeChatBot, WeChatMessage

async def main():
    bot = WeChatBot.from_env()
    
    @bot.on_message
    async def handle_message(msg: WeChatMessage):
        if not msg.is_command():
            await bot.reply_text(msg, f"收到: {msg.get_text()}")
    
    @bot.on_command("time")
    async def time_cmd(msg: WeChatMessage, args: list):
        from datetime import datetime
        await bot.reply_text(msg, f"时间: {datetime.now():%H:%M:%S}")
    
    # 启动时主动发送欢迎消息（量化交易通知场景）
    async def on_ready():
        if bot.get_user_id():
            await bot.notify("🤖 机器人已启动！")
    
    await bot.run(on_ready=on_ready)

asyncio.run(main())
```

## API 参考

### 🎯 UnifiedBot（推荐）

```python
bot = UnifiedBot()                          # 从 .env 读取 BOT_PLATFORM
bot = UnifiedBot(platform="feishu")         # 显式指定平台

# 注册处理器（所有平台写法完全一致）
@bot.on_message
async def handler(msg: UnifiedMessage): ...

@bot.on_command("cmd")
async def cmd(msg: UnifiedMessage, args: list): ...

# 发送和回复（所有平台写法完全一致）
await bot.reply_text(msg, "回复内容")
await bot.send_text("主动推送消息")
await bot.send_text("发给指定用户", target_id="ou_xxx")

# 快捷回复：直接从消息对象回复
await msg.reply("你好！")

# 生命周期
await bot.run()                             # 启动并阻塞
await bot.run(on_ready=lambda bot: ...)     # 带就绪回调
await bot.run(host="0.0.0.0", port=3000)   # 飞书：自定义 webhook 地址
bot.stop()                                  # 停止消息循环

# 属性
bot.platform                                # "feishu" | "wechat" | "qq"
```

### UnifiedMessage

```python
msg.message_id       # 消息 ID
msg.chat_id          # 会话 ID
msg.sender_id        # 发送者标识
msg.sender_name      # 发送者昵称
msg.content          # 消息文本内容
msg.msg_type         # 消息类型（"text", "image" 等）
msg.platform         # 来源平台（"feishu" | "wechat" | "qq"）
msg.create_time      # 消息创建时间戳（可能为 None）
msg.raw_data         # 原始平台事件数据

msg.get_text()       # 获取文本内容
msg.is_command("/")  # 是否为指令
msg.get_command("/") # 解析指令 → (指令名, 参数列表) 或 None
msg.reply(text)      # 快捷回复此消息
```

### 平台特有 API（高级用法）

```python
bot = LarkBot.from_env()

# 发送消息
await bot.send_text("Hello", open_id="ou_xxx")
await bot.reply_text(message, "Reply")

# 注册处理器
@bot.on_message
async def handler(msg: Message): ...

@bot.on_command("cmd")
async def cmd(msg: Message, args: list): ...
```

### QQ QQBot

```python
bot = QQBot.from_env()

# 发送消息
await bot.send_text("Hello", openid="xxx")
await bot.reply_text(message, "Reply")

# 注册处理器
@bot.on_message
async def handler(msg: QQMessage): ...

@bot.on_command("cmd")
async def cmd(msg: QQMessage, args: list): ...
```

### 微信 WeChatBot

```python
bot = WeChatBot.from_env()

# 主动推送消息（默认发给已绑定用户，量化交易通知推荐使用）
await bot.notify("📈 BTC 突破关键阻力位")

# 回复消息
await bot.reply_text(message, "Reply")

# 获取已绑定用户 ID
user_id = bot.get_user_id()

# 发送输入状态
await bot.send_typing(to_user_id, typing=True)

# 注册处理器
@bot.on_message
async def handler(msg: WeChatMessage): ...

@bot.on_command("cmd")
async def cmd(msg: WeChatMessage, args: list): ...

# 机器人就绪回调
async def on_ready():
    await bot.notify("机器人已上线")

await bot.run(on_ready=on_ready)
```

### Message 对象

**飞书 Message**:
```python
msg.message_id       # 消息 ID
msg.content          # 消息内容
msg.sender_open_id   # 发送者 open_id
msg.get_text()       # 获取文本
msg.is_command()     # 是否为指令
msg.get_command()    # 获取指令和参数
```

**QQ QQMessage**:
```python
msg.message_id       # 消息 ID
msg.content          # 消息内容
msg.author_openid    # 发送者 openid
msg.is_command()     # 是否为指令
msg.get_command()    # 获取指令和参数
```

**微信 WeChatMessage**:
```python
msg.message_id       # 消息 ID
msg.from_user_id     # 发送者 ID (xxx@im.wechat)
msg.get_text()       # 获取文本
msg.is_command()     # 是否为指令
msg.get_command()    # 获取指令和参数
msg.has_media()      # 是否包含媒体
msg.get_media_type() # 获取媒体类型
msg.context_token    # 上下文 token (用于回复)
```

## 运行

```bash
# 🎯 统一 API（推荐）—— 平台由 .env 中的 BOT_PLATFORM 控制
uv run python unified_main.py

# 或使用各平台专用入口：
uv run python main.py          # 飞书机器人
uv run python qq_main.py       # QQ机器人
uv run python wechat_main.py   # 微信机器人
```

## 微信机器人详解

### 扫码登录

首次运行微信机器人时，终端会显示二维码：

```
==================================================
请使用微信扫描以下二维码登录:
==================================================
█▀▀▀▀▀▀▀██▀██████▀██▀█▀▀▀▀█▀███▀▀▀▀▀▀▀█
█ █▀▀▀█ █▄ ▀ ▄█  ███▀▀ ▄▀▀▄ ▄ █ █▀▀▀█ █
...
==================================================
```

用微信扫描二维码完成授权即可登录。

### 登录凭证存储

登录成功后，凭证会自动保存到本地：

```
~/.openclaw/openclaw-weixin/
├── accounts.json          # 账户索引
└── accounts/
    └── <account_id>.json  # 账户凭证
```

**下次运行无需重新扫码**，程序会自动加载已保存的账户。

### 与官方 openclaw 插件兼容

存储格式与官方 `@tencent-weixin/openclaw-weixin` npm 插件完全兼容：

- 用 Python 版本登录后，官方 npm 插件可直接使用
- 用官方 npm 插件登录后，Python 版本也可直接使用
- 两者共享 `~/.openclaw/` 状态目录

### 无需公网 IP

微信机器人使用 HTTP long-polling 方式获取消息，不需要：
- 公网 IP
- Webhook 回调地址
- 端口映射

### Token 有效期

- Token 通常可长期有效（数天到数周）
- Token 过期时需重新扫码登录
- 在其他设备登录同一账号会使当前 token 失效

### 会话保护机制 (Session Guard)

当微信服务器返回会话过期错误（errcode -14）时，系统会自动：

1. **暂停服务 1 小时**：避免频繁无效请求导致 IP 被封禁
2. **发送邮件通知**：提醒用户重新扫码登录
3. **自动恢复**：重新登录后自动清除暂停状态

**触发条件**：
- 用户在微信中删除/解绑了机器人
- Token 长期未使用导致过期

**邮件通知配置**：

```env
BACKUP_EMAIL_FROM=bot@example.com
BACKUP_EMAIL_TO=your@email.com
BACKUP_EMAIL_SMTP=smtp.gmail.com
BACKUP_EMAIL_PORT=587
BACKUP_EMAIL_USER=your@gmail.com
BACKUP_EMAIL_PASSWORD=your-app-password
SERVER_NAME=my-server  # 可选，用于邮件内容标识
```

> **端口说明**：
> - `587` 端口：使用 STARTTLS 方式连接
> - `465` 端口：使用 SSL 直接连接（推荐国内邮箱如 139、QQ 邮箱使用）

### 数据持久化

微信机器人会自动持久化以下数据，重启后自动恢复：

```
~/.openclaw/openclaw-weixin/accounts/
├── <account_id>.json              # 账户凭证 (token, baseUrl, userId)
├── <account_id>.sync.json         # 消息同步缓冲区 (get_updates_buf)
└── <account_id>.context-tokens.json  # 上下文令牌 (用于回复消息)
```

**持久化内容**：
| 文件 | 用途 |
|------|------|
| `*.json` | 登录凭证，避免重复扫码 |
| `*.sync.json` | 消息同步位置，避免消息丢失/重复 |
| `*.context-tokens.json` | 回复令牌，确保消息能正确送达 |

### 主动推送消息

微信机器人支持主动推送消息，非常适合量化交易通知场景：

```python
# 最简单的方式 - 只需一行代码
await bot.notify("📈 BTC 突破 $100,000")
```

`notify()` 方法会自动发送给已绑定的用户，无需指定 `to_user_id`。

### on_ready 回调

`on_ready` 是一个回调函数，在机器人**完全就绪后**自动执行。用于：
- 发送启动通知
- 启动后台任务
- 初始化资源

```python
async def on_ready():
    # 机器人已登录，可以安全地发送消息
    if bot.get_user_id():
        await bot.notify("🤖 机器人已上线")

await bot.run(on_ready=on_ready)
```

**为什么需要 on_ready？**

`run()` 方法内部会执行登录流程，在登录完成前调用 `notify()` 会失败。`on_ready` 确保你的代码在登录完成后才执行。

```python
# ❌ 错误：run() 之前调用会失败
await bot.notify("启动")  # 报错：Not logged in
await bot.run()

# ✅ 正确：在 on_ready 中调用
async def on_ready():
    await bot.notify("启动")
await bot.run(on_ready=on_ready)
```

### 量化交易通知示例

完整的量化交易通知示例：

```python
import asyncio
from larky import WeChatBot, WeChatMessage

bot = WeChatBot.from_env()

async def price_monitor():
    """监控价格并在突破时发送通知"""
    while True:
        price = await get_btc_price()
        if price > 100000:
            await bot.notify(f"📈 BTC 突破 $100,000！当前: ${price:,}")
        await asyncio.sleep(60)

async def on_ready():
    # 发送启动通知
    await bot.notify("🤖 量化交易机器人已启动")
    # 启动价格监控任务
    asyncio.create_task(price_monitor())

async def main():
    @bot.on_command("status")
    async def status(msg: WeChatMessage, args: list):
        price = await get_btc_price()
        await bot.reply_text(msg, f"📊 当前 BTC 价格: ${price:,}")
    
    await bot.run(on_ready=on_ready)

asyncio.run(main())
```

### 🎯 统一多进程架构（所有平台通用）

当多个量化程序需要共享同一个机器人连接时，使用 `UnifiedService` + `UnifiedClient`。**飞书、微信、QQ 通用**：

```
┌─────────────────────────────────────────────────────────┐
│                      服务器                              │
│                                                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐ │
│  │ 量化程序 A  │    │ 量化程序 B  │    │ 量化程序 C  │ │
│  │ (BTC监控)   │    │ (ETH监控)   │    │ (套利策略)  │ │
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
│                   │ UnifiedService  │ ← 唯一平台连接   │
│                   └─────────────────┘   (飞书/微信/QQ) │
└─────────────────────────────────────────────────────────┘
```

**启动步骤：**

```bash
# 1. 启动 Redis
redis-server

# 2. 启动统一消息服务（平台由 .env 中的 BOT_PLATFORM 决定）
uv run python -m larky

# 3. 启动量化程序（可同时运行多个）
uv run python examples/trading_bot_unified.py
uv run python examples/trading_bot_btc.py
uv run python examples/trading_bot_eth.py
```

**量化程序使用 UnifiedClient（平台无关）：**

```python
from larky import UnifiedClient

client = UnifiedClient(source="btc-monitor")

# 发送通知，支持优先级
await client.notify("📈 BTC 突破 $100,000")                      # 普通优先级
await client.notify("🚨 止损触发", priority="high")              # 高优先级 → 队列+邮件备份

# 接收消息
@client.message_handler
async def on_message(data: dict):
    text = data.get("text", "")
    platform = data.get("platform", "")  # "feishu" / "wechat" / "qq"
    if "价格" in text:
        await client.notify(f"当前价格: ${await get_price()}")

# 监控服务状态
@client.status_handler
async def on_status(data: dict):
    if data.get("need_login"):
        logger.warning("服务需要重新认证")
    elif data.get("status") == "offline":
        logger.warning("服务离线")

await client.run()
```

**环境变量：**

```env
REDIS_URL=redis://localhost:6379
# 或
REDIS_HOST=localhost
REDIS_PORT=6379

# 可选：自定义 Redis 频道前缀（默认 "bot"）
BOT_SERVICE_PREFIX=bot
```

> **向后兼容**：微信专用的 `WeChatService` 和 `WeChatClient` 保持不变。
> 新的 `UnifiedService`/`UnifiedClient` 使用独立的 Redis 前缀（`bot:` vs `wechat:`），
> 可与旧部署共存。

### 故障处理（所有平台通用）

**1. 掉线自动重连**

网络波动时自动重连，指数退避（默认最多 10 次）。

**2. 认证过期处理**

| 平台 | 行为 |
|------|------|
| 微信 | 会话过期 → 暂停 + 邮件提醒扫码 |
| 飞书 | Token 自动刷新 — 无需用户操作 |
| QQ | Token 自动刷新 — 无需用户操作 |

**3. 消息优先级与备份发送（所有平台通用）**

```python
# 普通优先级（默认）— 离线时丢弃
await client.notify("📊 日常报告", priority="normal")

# 高优先级 — 离线时邮件备份 + 恢复后自动重发
await client.notify("🚨 紧急通知：止损触发", priority="high")
```

| 优先级 | 在线时 | 离线时 |
|--------|--------|--------|
| `normal`（默认） | 直接发送 | 消息丢弃 |
| `high` | 直接发送 | 1. Redis 队列保存<br>2. 并行发送邮件备份<br>3. 服务恢复后自动重发 |

**4. 状态监控（所有平台通用）**

```python
@client.status_handler
async def on_status(data: dict):
    platform = data.get("platform")
    if data.get("need_login"):
        logger.warning("%s 服务需要重新认证", platform)
    elif data.get("status") == "offline":
        logger.warning("%s 服务离线", platform)
```

## 平台配置

### 飞书开放平台

1. 在 [飞书开放平台](https://open.feishu.cn/) 创建企业自建应用
2. 开启机器人能力
3. 配置事件订阅，添加 `im.message.receive_v1` 事件
4. 设置 Webhook 地址

### QQ开放平台

1. 在 [QQ开放平台](https://q.qq.com/) 创建机器人
2. 获取 App ID 和 App Secret
3. 使用 WebSocket 方式连接，无需配置回调地址

### 微信机器人

微信机器人基于 `@tencent-weixin/openclaw-weixin` 协议实现，无需额外配置开放平台账号。

## 项目结构

```
larky/
├── larky/
│   ├── __init__.py
│   ├── __main__.py         # 微信消息服务入口
│   ├── unified.py          # 🎯 统一 API（UnifiedBot + UnifiedMessage）
│   ├── bot.py              # 飞书 LarkBot
│   ├── config.py           # 飞书配置
│   ├── handlers.py         # 飞书 Webhook
│   ├── models.py           # 飞书模型
│   ├── qq_bot.py           # QQ机器人核心
│   ├── qq_config.py        # QQ配置
│   ├── qq_models.py        # QQ模型
│   ├── wechat_bot.py       # 微信机器人核心
│   ├── wechat_config.py    # 微信配置
│   ├── wechat_models.py    # 微信模型
│   └── wechat_service.py   # 微信消息服务（多进程架构）
├── examples/
│   ├── trading_bot_btc.py  # BTC 监控示例
│   └── trading_bot_eth.py  # ETH 监控示例
├── tests/
│   ├── test_wechat_core.py     # 微信核心路径测试
│   └── test_wechat_priority.py # 微信优先级功能测试
├── unified_main.py         # 🎯 统一 API 入口（推荐）
├── main.py                 # 飞书示例
├── qq_main.py              # QQ示例
├── wechat_main.py          # 微信示例
└── pyproject.toml
```

## 在其他项目中使用

### 方式一：本地路径安装（推荐）

在目标项目的 `pyproject.toml` 中添加：

```toml
[project]
dependencies = [
    "larky @ file:///path/to/larky",
]
```

或使用 uv：

```bash
uv add /path/to/larky
```

### 方式二：Git 安装

```bash
# 从 GitHub
uv add git+https://github.com/hylyq/larky.git

# 从 Gitee（国内镜像）
uv add git+https://gitee.com/JiyunMa/larky.git
```

或在 `pyproject.toml` 中：

```toml
[project]
dependencies = [
    "larky @ git+https://github.com/hylyq/larky.git",
    # 或使用 Gitee 镜像：
    # "larky @ git+https://gitee.com/JiyunMa/larky.git",
]
```

### 方式三：发布到 PyPI

```bash
uv build
uv publish
```

然后其他项目可以直接安装：

```bash
uv add larky
```

### 使用示例

```python
import asyncio
from larky.wechat_service import WeChatClient

async def main():
    client = WeChatClient(source="my-trading-bot")
    
    @client.message_handler
    async def on_message(data: dict):
        text = data.get("text", "")
        if "状态" in text:
            await client.notify("✅ 服务运行正常")
    
    await client.run()

asyncio.run(main())
```

**环境变量配置**（`.env`）：

```env
REDIS_URL=redis://localhost:6379
# 或
REDIS_HOST=localhost
REDIS_PORT=6379
```

## 测试

运行单元测试：

```bash
# 运行微信优先级功能测试
uv run python tests/test_wechat_priority.py
```

## 依赖

- Python >= 3.13
- aiohttp >= 3.9.0
- python-dotenv >= 1.0.0
- pycryptodome >= 3.20.0
- qrcode >= 8.2
- redis >= 5.0.0

## 微信协议兼容性维护指南

微信机器人的实现基于官方 `@tencent-weixin/openclaw-weixin` npm 插件的 iLink 协议。当官方插件更新时，微信服务端可能要求新的字段、拒绝旧协议版本或改变 API 行为——这些都没有公开文档。以下流程帮助你通过对比官方源码来诊断和修复此类问题。

### 何时需要检查协议变动

- 消息日志显示发送成功但微信手机端收不到（API 返回 HTTP 200 但响应体中包含业务错误码）
- 微信能收消息但机器人发不出（或反之）
- 官方 npm 插件最近有新版本发布
- 昨天能用今天突然不行

### 诊断流程

**1. 查看官方插件最新版本：**

```bash
npm view @tencent-weixin/openclaw-weixin version
```

**2. 下载并查看官方源码：**

npm 包内包含完整的 TypeScript 源文件（`.ts`），不只是编译产物：

```bash
mkdir /tmp/openclaw-weixin && cd /tmp/openclaw-weixin
npm pack @tencent-weixin/openclaw-weixin
tar xzf tencent-weixin-openclaw-weixin-*.tgz
```

**3. 对比关键文件：**

| 官方源码 | larky 对应文件 | 检查重点 |
|---|---|---|
| `package/src/api/api.ts` | `larky/wechat_bot.py:_api_request` | 请求体结构、`base_info` 字段、错误处理 |
| `package/src/api/types.ts` | `larky/wechat_models.py` | 消息字段定义、新增枚举值、新增接口 |
| `package/src/messaging/send.ts` | `larky/wechat_bot.py:send_text` | `sendmessage` 请求体格式、必填字段 |
| `package/src/messaging/inbound.ts` | `larky/wechat_bot.py:get_updates` | Context Token 处理、消息解析 |
| `package/src/channel.ts` | `larky/wechat_service.py` | 启动/关闭生命周期、`notifyStart`/`notifyStop` |
| `package/src/api/session-guard.ts` | `larky/wechat_bot.py:SessionGuard` | 会话过期错误码 |

**4. 常见的协议变动：**

| 区域 | 检查点 | 示例 |
|---|---|---|
| `base_info` | 每个 API 请求都必须包含 `{"base_info": {"channel_version": "...", "bot_agent": "..."}}` —— 不仅是 `getupdates` | 2026-07: `sendmessage` 缺少 `base_info` → `ret=-2 prepare failed` |
| `CHANNEL_VERSION` | 必须与 npm 包最新版本号一致 | 在 `wechat_config.py` 中配置，取值自 npm 包的 `package.json` 中的 `version` 字段 |
| 新增端点 | 官方插件可能在启动/关闭时调用新的生命周期端点 | 官方新增了 `notifyStart` / `notifyStop` |
| 新增消息类型 | 检查 `MessageItemType` 和 `MessageType` 枚举 | 官方 v2.4.6 新增 `TOOL_CALL_START=11`, `TOOL_CALL_RESULT=12`（✅ 已于 2026-07-19 添加） |
| HTTP Headers | 验证 `iLink-App-Id`、`iLink-App-ClientVersion`、`SKRouteTag` | 对比官方 `api.ts` 中的 `buildCommonHeaders()` |
| 错误处理 | `sendmessage` 应在 `ret != 0` 时抛异常；`getUpdates` 应优雅处理错误 | 官方 `api.ts:515` 检查 `resp.ret !== 0` |

**5. 更新 CHANNEL_VERSION 并重测：**

修复协议问题后，更新 channel version。可以通过环境变量（无需改代码）：

```bash
export WECHAT_CHANNEL_VERSION="2.5.0"
```

或直接编辑 `wechat_config.py`：

```python
CHANNEL_VERSION = "2.4.6"  # 设置为 npm 包的最新版本号
```

然后用 `LOG_LEVEL=DEBUG` 部署验证，确认 API 响应都返回 `ret=0`。

### 案例：2026-07 协议修复

**症状**：日志显示消息发送成功，但微信手机端完全收不到。

**排查过程**：
1. 下载 `@tencent-weixin/openclaw-weixin@2.4.6`，查看 `api.ts` 中的 `sendMessage()` 函数
2. 发现官方代码在每个 API 调用中都包裹了 `base_info: buildBaseInfo()`：
   ```typescript
   body: JSON.stringify({ ...params.body, base_info: buildBaseInfo() })
   ```
3. larky 只在 `getUpdates` 中带了 `base_info`——`sendmessage`、`getconfig`、`sendtyping` 全都没有

**修复**：给所有 API 请求体添加 `base_info`，新增 `notifyStart`/`notifyStop` 生命周期调用，将 `CHANNEL_VERSION` 升级到 `2.4.6`。同时在 `_api_request` 中增加响应体日志，方便未来快速发现业务错误码。

## 更新日志

### 2026-07-19 — 协议缺口补齐、韧性优化与测试覆盖

**CDN 媒体支持：**

- **CDNMedia 解析**：`WeChatMessage.from_dict()` 现在会解析嵌套的 `media` 和 `thumb_media` 对象（含 `encrypt_query_param`、`aes_key`、`encrypt_type`），覆盖 IMAGE、VOICE、FILE、VIDEO 四种消息类型。此前 CDN 元数据在解析时被静默丢弃。空 CDN 字典会被规范化为 `None`。
- **入站消息完整元数据**：`_handle_incoming_message()` 通过新增的 `_build_incoming_payload()` 向 Redis 发布完整消息元数据——包括媒体类型、CDN 凭证、文件名、图片 URL、会话 ID、context_token 等。下游 `WeChatClient` 订阅者现在可获取富媒体消息的全部上下文。完全向后兼容——只读 `text` 字段的旧消费者不受影响。

**协议同步：**

- **TOOL_CALL_START / TOOL_CALL_RESULT**：`MessageItemType` 新增枚举值 11 和 12（官方插件 v2.4.6）。此前收到这两类消息会抛出 `ValueError`。
- **`send_typing()` 空 token 修复**：`send_typing()` 现在在 token 为空时省略 `context_token` 字段——与上一版本对 `send_text()` 的修复保持一致。防止 Python `None` 被序列化为 JSON `null`。
- **`_api_get()` 业务错误检查**：QR 登录流程的 GET 请求现在会检查 JSON 响应中的 `ret`/`errcode` 并记录业务错误（此前仅检查 HTTP 状态码）。与 `_api_request()` 行为一致。

**韧性优化：**

- **优雅关闭**：`close()` 现在等待最多 5 秒让进行中的 API 请求完成（`_in_flight` 计数器），再关闭 aiohttp session。防止 `send_text` 或 `notify_stop` 被中途中断。
- **指数退避**：getUpdates 错误循环改用指数退避（`1s → 2s → 4s → ... → 60s` 上限），替代固定的 5 秒等待。每次成功轮询后重置为 1s。
- **Token 激活重试**：`activate_context_token()` 新增 `_activate_context_token_with_retry()` 包装，失败时最多重试 2 次（1s / 2s 延迟）。此前单次网络波动就会静默丢弃激活，可能导致 token 提前过期。

**用户体验：**

- **输入状态提示**：内建命令（`/help`、`/status`、`/ping`）在回复前通过 `send_typing()` 在微信客户端显示"正在输入..."。best-effort——token 不可用时静默忽略。

**配置：**

- **`CHANNEL_VERSION` 环境变量覆盖**：设置 `WECHAT_CHANNEL_VERSION=3.0.0` 即可在不修改代码的情况下覆盖硬编码的 channel version，方便快速协议升级。

**测试（32 个测试，此前仅 4 个）：**

- **28 个核心路径单元测试**（`tests/test_wechat_core.py`）：覆盖 token 过期自动恢复、context_token 提取与持久化、5 个 API 请求中的 `base_info` 完整性、6 种媒体类型的 CDNMedia 解析、TOOL_CALL 枚举兼容性、`send_typing` 空 token 序列化、Redis 发布消息元数据完整性、指数退避模式验证、`CHANNEL_VERSION` 环境变量覆盖。
- **修复已有测试**：为 `test_wechat_priority.py` 中的 4 个异步测试补上缺失的 `@pytest.mark.asyncio` 装饰器（此前未被 pytest 收集执行）。

### 2026-07-18 (晚间) - Context Token 保活与队列韧性优化

- **Context token 激活**：对齐官方插件行为——每次收到消息时用新的 `context_token` 调用 `getConfig` API 向微信服务器注册/激活 token，延长有效时长（之前仅存储 token，从未激活）
- **失败消息队列**：新增 `wechat:failed_messages` 队列，用于隔离因 context_token 过期而发送失败的消息，防止其阻塞正常待发队列
- **更智能的重试机制**：移除 `prepare failed` 的无意义 3 次快速重试——过期的 token 不会自行恢复；消息直接移入失败队列并发送邮件备份
- **事件驱动的队列处理**：`_process_pending_messages` 收到新消息（新的 context_token）时立即唤醒处理，不再死等 30 秒
- **更频繁的保活检查**：`WECHAT_KEEPALIVE_INTERVAL_SEC` 默认值从 4 小时缩短至 30 分钟
- **队列排空韧性**：`_drain_queue()` 处理队列中所有消息，单条失败不阻塞其他消息；通过初始计数跟踪防止无限循环
- **省略空 context_token**：`send_text` 在 token 为空时完全省略 JSON 中的 `context_token` 字段（匹配官方插件 JS `undefined` 的行为），不再将 Python `None` 序列化为 JSON `null`（服务器可能拒绝 null 值）
- **失败队列仅在收到新消息时处理**：`QUEUE_FAILED` 仅在 `context_token_updated` 触发（用户发消息）时才排空，而非每 30 秒一次——避免 token 过期时无效重试刷屏日志

### 2026-07-18 - 协议同步至 @tencent-weixin/openclaw-weixin v2.4.6

- **关键修复**：给 `sendmessage`、`getconfig`、`sendtyping` API 请求添加 `base_info`（channel_version + bot_agent）——匹配官方插件 v2.4.6 请求格式。修复发送消息时的 `ret=-2 prepare failed` 错误。
- 新增 `notifyStart` 和 `notifyStop` 生命周期 API 调用（bot 启动/关闭时）
- 新增 `check_context_health()` 方法和定期 keepalive 探活（默认每 4 小时，可通过 `WECHAT_KEEPALIVE_INTERVAL_SEC` 配置）
- `send_text` 在遇到 `prepare failed` 时自动清除过期 token 并无 token 重试一次，失败后回队列重试（最多 3 次）
- API 响应成功时输出 DEBUG 日志，失败时（ret/errcode 非零）输出 ERROR 日志
- 修复清除所有 context token 后磁盘文件未删除的问题
- 修复服务关闭时未调用 `notify_stop` 的问题

### 2026-04-05 - 微信协议适配更新
- 同步缓冲区持久化到 `*.sync.json`
- 服务重启后自动恢复状态

## License

MIT
