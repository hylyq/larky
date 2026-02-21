# Larky

轻量级异步飞书 Lark 机器人模块，专为量化交易环境设计。

## 特性

- 异步架构，基于 aiohttp
- 轻量依赖：aiohttp、python-dotenv、pycryptodome
- 支持消息推送和指令接收
- 自动管理 tenant_access_token
- 支持加密消息解密
- 支持装饰器风格的消息/指令处理

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

**注意**：依赖会自动安装，无需手动处理。

## 配置

复制 `.env.example` 为 `.env` 并填入你的飞书应用配置：

```env
APP_ID=cli_xxx
APP_SECRET=xxx
VERIFICATION_TOKEN=xxx
ENCRYPT_KEY=xxx
LARK_HOST=https://open.feishu.cn
```

配置项说明：
- `APP_ID`: 飞书应用的 App ID
- `APP_SECRET`: 飞书应用的 App Secret
- `VERIFICATION_TOKEN`: 事件订阅的验证 Token
- `ENCRYPT_KEY`: 消息加密 Key（如启用加密则必填）
- `LARK_HOST`: 飞书 API 地址，默认 `https://open.feishu.cn`

## 快速开始

### 基本使用

```python
import asyncio
from larky import LarkBot

async def main():
    bot = LarkBot(
        app_id="your_app_id",
        app_secret="your_app_secret",
    )
    
    async with bot:
        await bot.send_text("Hello!", open_id="ou_xxx")

asyncio.run(main())
```

### 启动 Webhook 服务器

```python
import asyncio
from larky import LarkBot, Message, WebhookServer

async def main():
    bot = LarkBot.from_env()
    
    @bot.on_message
    async def handle_message(message: Message):
        text = message.get_text()
        await bot.reply_text(message, f"Received: {text}")
    
    @bot.on_command("ping")
    async def ping(message: Message, args: list[str]):
        await bot.reply_text(message, "Pong!")
    
    async with bot:
        server = WebhookServer(bot, port=3000)
        await server.start()
        await asyncio.Event().wait()

asyncio.run(main())
```

### 集成到量化交易

```python
from larky import LarkBot

bot = LarkBot.from_env()

async def send_trade_alert(symbol: str, action: str, price: float):
    async with bot:
        await bot.send_text(
            f"Trade Alert: {action} {symbol} @ {price}",
            open_id="your_open_id"
        )

async def send_risk_warning(message: str):
    async with bot:
        await bot.send_text(
            f"Risk Warning: {message}",
            open_id="your_open_id"
        )
```

## API

### LarkBot

```python
bot = LarkBot(
    app_id="xxx",
    app_secret="xxx",
    verification_token="xxx",  # 可选，用于验证事件请求
    encrypt_key="xxx",         # 可选，用于解密消息
    lark_host="https://open.feishu.cn",
)

# 或从环境变量加载
bot = LarkBot.from_env()
```

#### 发送消息

```python
# 发送文本消息
await bot.send_text("Hello", open_id="ou_xxx")
await bot.send_text("Hello", chat_id="oc_xxx")
await bot.send_text("Hello", user_id="xxx")

# 回复消息
await bot.reply_text(message, "Reply")
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
```

### Message

```python
message.message_id       # 消息ID
message.chat_id          # 会话ID
message.content          # 消息内容（已解析为dict）
message.sender_open_id   # 发送者 open_id
message.msg_type         # 消息类型
message.get_text()       # 获取文本内容
message.is_command()     # 是否为指令
message.get_command()    # 获取指令和参数 (cmd, args)
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

## 飞书配置

1. 在飞书开放平台创建企业自建应用
2. 开启机器人能力
3. 配置事件订阅，添加 `im.message.receive_v1` 事件
4. 设置请求地址为你的服务器地址（如 `http://your-server:3000/`）
5. 如需加密，配置 Encrypt Key 并填入 `.env`

## License

MIT
