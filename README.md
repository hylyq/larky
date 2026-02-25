# Larky

轻量级异步飞书 Lark 机器人模块，专为量化交易通知场景设计。

## 特性

- **异步架构**：基于 aiohttp，高性能异步 I/O
- **轻量依赖**：仅需 aiohttp、python-dotenv、pycryptodome
- **双向通信**：支持消息推送和指令接收
- **自动认证**：自动管理 tenant_access_token，过期自动刷新
- **安全通信**：支持加密消息解密和签名验证
- **装饰器风格**：优雅的消息/指令处理器注册方式
- **类型提示**：完整的类型注解，IDE 友好

## 安装

### 本地开发

```bash
uv sync
```

### 在其他项目中使用

#### 方式一：本地路径安装（推荐开发时使用）

```bash
# 使用 uv 添加本地包（可编辑模式）
uv add --editable /path/to/larky

# 或在 pyproject.toml 中添加
[project]
dependencies = [
    "larky @ file:///path/to/larky",
]
```

#### 方式二：Git 仓库安装

```bash
uv add git+https://github.com/yourname/larky.git
```

#### 方式三：发布到 PyPI

```bash
# 在 larky 项目目录下构建并发布
uv build
uv publish

# 然后在其他项目中安装
uv add larky
```

## 配置

复制 `.env.example` 为 `.env` 并填入你的飞书应用配置：

```env
APP_ID=cli_xxx
APP_SECRET=xxx
VERIFICATION_TOKEN=xxx
ENCRYPT_KEY=xxx
LARK_HOST=https://open.feishu.cn
OPEN_ID=ou_xxx
MAX_RETRIES=3
RETRY_DELAY=1.0
LOG_LEVEL=INFO
```

| 配置项 | 说明 | 必填 | 默认值 |
|--------|------|------|--------|
| `APP_ID` | 飞书应用的 App ID | 是 | - |
| `APP_SECRET` | 飞书应用的 App Secret | 是 | - |
| `VERIFICATION_TOKEN` | 事件订阅的验证 Token | 否 | - |
| `ENCRYPT_KEY` | 消息加密 Key（启用加密时必填） | 否 | - |
| `LARK_HOST` | 飞书 API 地址 | 否 | `https://open.feishu.cn` |
| `OPEN_ID` | 默认接收消息的用户 open_id | 否 | - |
| `MAX_RETRIES` | API 请求最大重试次数 | 否 | `3` |
| `RETRY_DELAY` | API 请求重试延迟（秒） | 否 | `1.0` |
| `LOG_LEVEL` | 日志级别 | 否 | `INFO` |

## 快速开始

### 基本使用

```python
import asyncio
from larky import LarkBot

async def main():
    bot = LarkBot.from_env()
    
    async with bot:
        # 如果设置了 OPEN_ID，可以直接发送消息
        await bot.send_text("Hello!")
        
        # 也可以显式指定接收者
        await bot.send_text("Hello!", open_id="ou_xxx")
        await bot.send_text("Hello!", chat_id="oc_xxx")

asyncio.run(main())
```

### 启动 Webhook 服务器

```python
import asyncio
from larky import LarkBot, Message, WebhookServer

async def main():
    bot = LarkBot.from_env()
    
    # 注册消息处理器
    @bot.on_message
    async def handle_message(message: Message):
        text = message.get_text()
        await bot.reply_text(message, f"收到: {text}")
    
    # 注册指令处理器
    @bot.on_command("ping")
    async def ping(message: Message, args: list[str]):
        await bot.reply_text(message, "Pong!")
    
    async with bot:
        await bot.send_text("🤖 机器人已启动！")
        server = WebhookServer(bot, port=3000)
        await server.start()
        await asyncio.Event().wait()

asyncio.run(main())
```

### 获取用户 Open ID

用户发送 `/getid` 命令，机器人会回复用户的 open_id：

```python
@bot.on_command("getid")
async def handle_getid(message: Message, args: list[str]):
    open_id = message.sender_open_id
    if open_id:
        await bot.reply_text(message, f"Your Open ID: {open_id}")
```

### 集成到量化交易

```python
from larky import LarkBot

bot = LarkBot.from_env()

async def send_trade_alert(symbol: str, action: str, price: float):
    async with bot:
        await bot.send_text(f"📈 Trade Alert: {action} {symbol} @ {price}")

async def send_risk_warning(message: str):
    async with bot:
        await bot.send_text(f"⚠️ Risk Warning: {message}")
```

## API 参考

### LarkBot

```python
bot = LarkBot(
    app_id="xxx",
    app_secret="xxx",
    verification_token="xxx",  # 可选，用于验证事件请求
    encrypt_key="xxx",         # 可选，用于解密消息
    lark_host="https://open.feishu.cn",
    open_id="ou_xxx",          # 可选，默认接收消息的用户
    max_retries=3,             # 可选，API 请求最大重试次数
    retry_delay=1.0,           # 可选，API 请求重试延迟（秒）
)

# 或从环境变量加载
bot = LarkBot.from_env()

# 或使用 LarkConfig
from larky import LarkConfig
config = LarkConfig(
    app_id="xxx",
    app_secret="xxx",
)
bot = LarkBot(config=config)
```

#### 发送消息

```python
# 发送文本消息（使用默认 open_id）
await bot.send_text("Hello")

# 发送文本消息（指定接收者）
await bot.send_text("Hello", open_id="ou_xxx")
await bot.send_text("Hello", chat_id="oc_xxx")
await bot.send_text("Hello", user_id="xxx")
await bot.send_text("Hello", email="user@example.com")

# 回复消息
await bot.reply_text(message, "Reply")

# 发送其他类型消息
await bot.send_message({"text": "Hello"}, msg_type=MessageType.TEXT)
```

#### 注册处理器

```python
# 消息处理器
@bot.on_message
async def handler(message: Message):
    text = message.get_text()
    await bot.reply_text(message, f"Echo: {text}")

# 指令处理器
@bot.on_command("status")
async def status_handler(message: Message, args: list[str]):
    await bot.reply_text(message, "System running normally.")

# 设置指令前缀（默认为 "/"）
bot.set_command_prefix("!")
```

#### 获取用户信息

```python
user_info = await bot.get_user_info("ou_xxx", user_id_type="open_id")
```

### Message

```python
message.message_id       # 消息 ID
message.chat_id          # 会话 ID
message.content          # 消息内容（已解析为 dict）
message.sender_open_id   # 发送者 open_id
message.sender_id        # 发送者 union_id
message.sender_name      # 发送者名称
message.msg_type         # 消息类型 (MessageType 枚举)
message.create_time      # 发送时间戳
message.root_id          # 根消息 ID
message.parent_id        # 父消息 ID
message.raw_data         # 原始 webhook 数据

message.get_text()       # 获取文本内容
message.is_command()     # 是否为指令
message.get_command()    # 获取指令和参数 -> tuple[str, list[str]] | None
```

### MessageType

```python
from larky import MessageType

MessageType.TEXT         # 文本消息
MessageType.POST         # 富文本消息
MessageType.IMAGE        # 图片消息
MessageType.FILE         # 文件消息
MessageType.AUDIO        # 音频消息
MessageType.MEDIA        # 视频消息
MessageType.STICKER      # 表情消息
MessageType.INTERACTIVE  # 交互式卡片消息
```

### LarkConfig

```python
from larky import LarkConfig

config = LarkConfig(
    app_id="xxx",
    app_secret="xxx",
    verification_token="xxx",
    encrypt_key="xxx",
    lark_host="https://open.feishu.cn",
    open_id="ou_xxx",
    max_retries=3,
    retry_delay=1.0,
    log_level="INFO",
)

# 或从环境变量加载
config = LarkConfig.from_env()
```

### 异常类

```python
from larky import LarkError, TokenError, APIError, ValidationError

# LarkError - 基础异常类
# TokenError - Token 获取或刷新失败
# APIError - 飞书 API 调用失败（包含 code 和 msg 属性）
# ValidationError - 参数验证失败
```

### WebhookServer

```python
server = WebhookServer(
    bot,
    host="0.0.0.0",
    port=3000,
    path="/",  # 飞书默认发送到根路径
)

await server.start()
await server.stop()
```

## 运行

```bash
uv run python main.py
```

## 飞书开放平台配置

1. 在 [飞书开放平台](https://open.feishu.cn/) 创建企业自建应用
2. 开启机器人能力
3. 配置事件订阅，添加 `im.message.receive_v1` 事件
4. 设置请求地址为你的服务器地址（如 `http://your-server:3000/`）
5. 如需加密，配置 Encrypt Key 并填入 `.env`
6. 发布应用并添加到群聊或启用单聊

## 项目结构

```
larky/
├── larky/
│   ├── __init__.py     # 包入口
│   ├── bot.py          # LarkBot 核心类
│   ├── config.py       # 配置管理
│   ├── handlers.py     # Webhook 服务器和处理器
│   └── models.py       # 数据模型
├── main.py             # 示例主程序
├── pyproject.toml      # 项目配置
├── .env.example        # 环境变量示例
└── README.md           # 项目文档
```

## 依赖

- Python >= 3.13
- aiohttp >= 3.9.0
- python-dotenv >= 1.0.0
- pycryptodome >= 3.20.0

## License

MIT
