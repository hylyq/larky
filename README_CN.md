# Larky

轻量级异步机器人模块，支持飞书 Lark、QQ 和微信机器人，专为量化交易通知场景设计。

> 📖 [English Documentation](README.md)

## 特性

- **异步架构**：基于 aiohttp，高性能异步 I/O
- **轻量依赖**：仅需 aiohttp、python-dotenv、pycryptodome、qrcode
- **多平台支持**：飞书机器人 + QQ机器人 + 微信机器人
- **自动认证**：自动管理 access_token，过期自动刷新
- **装饰器风格**：优雅的消息/指令处理器注册方式
- **类型提示**：完整的类型注解， IDE 友好
- **微信扫码登录**：终端显示二维码，扫码即可登录
- **凭证持久化**：登录信息自动保存，与官方 openclaw 插件兼容
- **主动推送**：微信机器人支持主动推送消息，适合量化交易通知场景
- **会话保护**：Session Guard 机制，会话过期自动暂停并邮件通知
- **数据持久化**：Context Token 和同步缓冲区自动持久化，重启不丢失

## 安装

```bash
uv sync
```

## 配置

复制 `.env.example` 为 `.env` 并填入配置：

```env
# 飞书机器人配置
APP_ID=cli_xxx
APP_SECRET=xxx
VERIFICATION_TOKEN=xxx
ENCRYPT_KEY=
LARK_HOST=https://open.feishu.cn
OPEN_ID=

# QQ机器人配置
QQ_APP_ID=xxx
QQ_APP_SECRET=xxx

# 微信机器人无需配置，扫码登录即可使用
```

| 配置项 | 说明 | 必填 |
|--------|------|------|
| `APP_ID` | 飞书应用的 App ID | 飞书必填 |
| `APP_SECRET` | 飞书应用的 App Secret | 飞书必填 |
| `QQ_APP_ID` | QQ机器人的 App ID | QQ必填 |
| `QQ_APP_SECRET` | QQ机器人的 App Secret | QQ必填 |

> **微信机器人无需配置**：直接运行 `uv run python wechat_main.py`，扫码登录即可使用，不需要在 `.env` 文件中配置任何参数。

## 快速开始

### 飞书机器人

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

### 飞书 LarkBot

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
# 飞书机器人
uv run python main.py

# QQ机器人
uv run python qq_main.py

# 微信机器人
uv run python wechat_main.py
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

### 多进程架构

当多个量化程序需要共享同一个微信账号时，使用 `WeChatService` + `WeChatClient` 架构：

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
│                   │  WeChatService  │ ← 唯一微信连接   │
│                   └─────────────────┘                  │
└─────────────────────────────────────────────────────────┘
```

**启动步骤：**

```bash
# 1. 启动 Redis
redis-server

# 2. 启动微信消息服务（唯一微信连接）
uv run python -m larky

# 3. 启动量化程序（可同时运行多个）
uv run python examples/trading_bot_btc.py
uv run python examples/trading_bot_eth.py
```

**量化程序使用 WeChatClient：**

```python
from larky import WeChatClient

client = WeChatClient(source="btc-monitor")

# 发送通知
await client.notify("📈 BTC 突破 $100,000")

# 接收消息
@client.message_handler
async def on_message(data: dict):
    text = data.get("text", "")
    if "价格" in text:
        await client.notify(f"当前价格: ${await get_price()}")

await client.run()
```

**环境变量：**

```env
REDIS_URL=redis://localhost:6379
# 或
REDIS_HOST=localhost
REDIS_PORT=6379
```

### 故障处理

微信消息服务内置以下故障处理机制：

**1. 掉线自动重连**

网络波动导致断开时，服务会自动重连（默认最多 10 次）。

**2. 会话过期保护 (Session Guard)**

当微信服务器返回会话过期错误（errcode -14）时：
- 自动暂停服务 1 小时，避免频繁请求被封禁
- 发送邮件通知用户重新扫码登录
- 重新登录后自动恢复

邮件配置见上方 [会话保护机制](#会话保护机制-session-guard)。

**3. 消息优先级与备份发送**

量化程序发送的消息支持两种优先级：

```python
# 普通消息（默认）- 离线时丢弃
await client.notify("📊 日常报告", priority="normal")

# 高优先级消息 - 离线时邮件备份 + 恢复后重发
await client.notify("🚨 紧急通知：止损触发", priority="high")
```

| 优先级 | 在线时 | 离线时 |
|--------|--------|--------|
| `normal`（默认） | 直接发送微信 | 消息丢弃 |
| `high` | 直接发送微信 | 1. 消息入队保存<br>2. 并行发送邮件备份<br>3. 微信恢复后自动重发 |

**使用场景示例：**

```python
# 日常报告 - 普通优先级，离线时无需通知
await client.notify("📊 每日盈亏: +$1,234", priority="normal")

# 重要交易信号 - 高优先级，确保送达
await client.notify("🚨 止损触发: BTC 跌破 $95,000", priority="high")

# 风险预警 - 高优先级
await client.notify("⚠️ 账户保证金不足，请及时处理", priority="high")
```

**4. 状态监控**

客户端可监听服务状态变化：

```python
@client.status_handler
async def on_status(data: dict):
    if data.get("need_login"):
        # 服务需要重新登录
        logger.warning("微信服务需要重新扫码登录")
    elif data.get("status") == "offline":
        # 服务离线
        logger.warning("微信服务离线")
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
│   └── test_wechat_priority.py  # 微信优先级功能测试
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
| 新增消息类型 | 检查 `MessageItemType` 和 `MessageType` 枚举 | 官方 v2.4.6 新增 `TOOL_CALL_START=11`, `TOOL_CALL_RESULT=12` |
| HTTP Headers | 验证 `iLink-App-Id`、`iLink-App-ClientVersion`、`SKRouteTag` | 对比官方 `api.ts` 中的 `buildCommonHeaders()` |
| 错误处理 | `sendmessage` 应在 `ret != 0` 时抛异常；`getUpdates` 应优雅处理错误 | 官方 `api.ts:515` 检查 `resp.ret !== 0` |

**5. 更新 CHANNEL_VERSION 并重测：**

修复协议问题后，更新 `wechat_config.py`：

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
