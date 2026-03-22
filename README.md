# Larky

轻量级异步机器人模块，支持飞书 Lark、QQ 和微信机器人，专为量化交易通知场景设计。

## 特性

- **异步架构**：基于 aiohttp，高性能异步 I/O
- **轻量依赖**：仅需 aiohttp、python-dotenv、pycryptodome、qrcode
- **多平台支持**：飞书机器人 + QQ机器人 + 微信机器人
- **自动认证**：自动管理 access_token，过期自动刷新
- **装饰器风格**：优雅的消息/指令处理器注册方式
- **类型提示**：完整的类型注解，IDE 友好
- **微信扫码登录**：终端显示二维码，扫码即可登录
- **凭证持久化**：登录信息自动保存，与官方 openclaw 插件兼容
- **主动推送**：微信机器人支持主动推送消息，适合量化交易通知场景

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
│   ├── bot.py              # 飞书 LarkBot
│   ├── config.py           # 飞书配置
│   ├── handlers.py         # 飞书 Webhook
│   ├── models.py           # 飞书模型
│   ├── qq_bot.py           # QQ机器人核心
│   ├── qq_config.py        # QQ配置
│   ├── qq_models.py        # QQ模型
│   ├── wechat_bot.py       # 微信机器人核心
│   ├── wechat_config.py    # 微信配置
│   └── wechat_models.py    # 微信模型
├── main.py                 # 飞书示例
├── qq_main.py              # QQ示例
├── wechat_main.py          # 微信示例
└── pyproject.toml
```

## 依赖

- Python >= 3.13
- aiohttp >= 3.9.0
- python-dotenv >= 1.0.0
- pycryptodome >= 3.20.0
- qrcode >= 8.2

## License

MIT
