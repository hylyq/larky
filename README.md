# Larky

轻量级异步机器人模块，支持飞书 Lark 和 QQ 机器人，专为量化交易通知场景设计。

## 特性

- **异步架构**：基于 aiohttp，高性能异步 I/O
- **轻量依赖**：仅需 aiohttp、python-dotenv、pycryptodome
- **多平台支持**：飞书机器人 + QQ机器人（WebSocket 方式）
- **自动认证**：自动管理 access_token，过期自动刷新
- **装饰器风格**：优雅的消息/指令处理器注册方式
- **类型提示**：完整的类型注解，IDE 友好

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
```

| 配置项 | 说明 | 必填 |
|--------|------|------|
| `APP_ID` | 飞书应用的 App ID | 飞书必填 |
| `APP_SECRET` | 飞书应用的 App Secret | 飞书必填 |
| `QQ_APP_ID` | QQ机器人的 App ID | QQ必填 |
| `QQ_APP_SECRET` | QQ机器人的 App Secret | QQ必填 |

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

## 运行

```bash
# 飞书机器人
uv run python main.py

# QQ机器人
uv run python qq_main.py
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

## 项目结构

```
larky/
├── larky/
│   ├── __init__.py
│   ├── bot.py          # 飞书 LarkBot
│   ├── config.py       # 飞书配置
│   ├── handlers.py     # 飞书 Webhook
│   ├── models.py       # 飞书模型
│   ├── qq_bot.py       # QQ机器人核心
│   ├── qq_config.py    # QQ配置
│   └── qq_models.py    # QQ模型
├── main.py             # 飞书示例
├── qq_main.py          # QQ示例
└── pyproject.toml
```

## 依赖

- Python >= 3.13
- aiohttp >= 3.9.0
- python-dotenv >= 1.0.0
- pycryptodome >= 3.20.0

## License

MIT
