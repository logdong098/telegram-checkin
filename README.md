# telegram-checkin

使用 Playwright 持久化浏览器上下文，完成 Telegram Web 机器人签到以及拾光工坊（`820010.xyz`）签到。

## 首次登录

登录命令把 820010.xyz 和 Telegram Web **两个登录态完全隔离**——它们各自使用一个独立的 Playwright 持久化 profile：

| 任务 | Profile 目录 | 命令 |
|---|---|---|
| 拾光工坊（820010.xyz） | `DATA_DIR/website-browser-profile/` | `login-website` |
| Telegram Web（5 个 bot 签到） | `DATA_DIR/browser-profile/` | `login-telegram` |
| 两者一起 | （各自独立） | `login` |

隔离带来的好处：Telegram 掉登录时只重新跑 `login-telegram` 即可，**不会触碰 820010 的 cookie**；反之亦然。

### 本机首次登录（有显示器）

```bash
cp .env.example .env
python -m pip install -e .
playwright install chromium
# 完整登录（会开 Chromium 窗口，扫码 + 登网站）
telegram-checkin login
```

如果只需要刷新其中一个：

```bash
telegram-checkin login-website   # 只登 820010，不动 Telegram profile
telegram-checkin login-telegram  # 只登 Telegram Web（QR 在 http://HOST:LOGIN_PORT/）
```

### Docker / 无显示器场景

```dotenv
# .env
WEBSITE_LOGIN_HEADLESS=true   # 容器内必须 headless；daemon 仍正常
BROWSER_HEADLESS=true
```

```bash
docker compose up -d --build
# 第一次：完整登录
docker exec -it telegram-checkin-telegram-checkin-1 telegram-checkin login
# 后续：只刷新需要的那一边
docker exec -it telegram-checkin-telegram-checkin-1 telegram-checkin login-telegram
# 打开 http://HOST:LOGIN_PORT/  扫码
```

`once` / `daemon` 时使用无头模式（`BROWSER_HEADLESS=true`）。

## Telegram 通知

必须配置一个 Telegram Bot API bot 用于通知。这个 bot API 通道独立于 Telegram Web cookie，因此 Telegram Web 登录态失效时仍可以发出告警：

```dotenv
TELEGRAM_BOT_TOKEN=123456:replace_me
TELEGRAM_NOTIFY_CHAT_ID=123456789
```

先向该 bot 发送一条消息，或把 bot 加入目标群组。通知包括：

- 820010.xyz 登录态失效；
- Telegram Web 登录态失效；
- 820010.xyz 签到成功（包括"今日已签到"）；
- 网站签到失败或请求异常。

未配置这两个变量时，签到仍会执行，但通知会记录为 warning 并跳过。

## 运行

```bash
telegram-checkin validate
telegram-checkin once
telegram-checkin daemon
```

网站签到按钮默认使用 `#seat-checkin`，请求 `/api/seats/checkin`，而不是调用网站 API 绕过页面；站点返回的 toast/error 文本用于判断成功、已签到或失败。网站必须已经有有效的当前订阅，否则会报告"签到按钮未找到"。

### 第一次跑 820010 会遇到的 onboarding 蒙层

拾光工坊在用户**第一次**点签到时会弹一个 onboarding 蒙层（`#seat-help-scrim.is-open`），它会拦截对 `#seat-checkin` 的点击。`once` / `daemon` 会自动：

1. 检测蒙层是否存在；
2. 先点 "我知道了" / 关闭按钮，或在必要时直接从 DOM 移除蒙层；
3. 用 `force=True` 点击 `#seat-checkin`，但仍要求实际收到 `/api/seats/checkin` 的响应才认为成功（**没有绕过页面、没有伪造请求**）。

如果连试 5 次仍未拿到响应，会抛出 `WebsiteCheckinError` 并触发告警。

## Docker

`compose.yaml` 会持久化 `/data`，其中包含两个 Playwright profile 和 SQLite 历史记录。建议先在有图形界面的机器上执行一次 `telegram-checkin login`，再把同一个 `DATA_DIR`/Docker volume 用于 daemon；daemon 本身保持无头运行。

## 开发

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e . pytest pytest-asyncio
pytest -q
```
