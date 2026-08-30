# telegram-checkin

使用 Playwright 持久化浏览器上下文，完成 Telegram Web 机器人签到以及拾光工坊（`820010.xyz`）签到。

## 首次登录

登录命令会依次处理两个登录态：

1. 打开一个可交互的 820010.xyz 浏览器窗口。手动登录后，cookie 会保存到 `DATA_DIR/website-browser-profile`。
2. 通过现有的 Telegram Web QR 登录流程。二维码会通过 `LOGIN_PORT` 提供预览，Telegram 登录态保存到 `DATA_DIR/browser-profile`。

本机首次登录建议：

```bash
cp .env.example .env
# 首次登录需要可显示浏览器窗口
# WEBSITE_LOGIN_HEADLESS=false
python -m pip install -e .
playwright install chromium
telegram-checkin login
```

如果已经完成网站登录，只会复用已保存的登录态，不会再次要求登录。之后运行 `once` 或 `daemon` 时使用无头模式（`BROWSER_HEADLESS=true`）。

## Telegram 通知

必须配置一个 Telegram Bot API bot 用于通知。这个 bot API 通道独立于 Telegram Web cookie，因此 Telegram Web 登录态失效时仍可以发出告警：

```dotenv
TELEGRAM_BOT_TOKEN=123456:replace_me
TELEGRAM_NOTIFY_CHAT_ID=123456789
```

先向该 bot 发送一条消息，或把 bot 加入目标群组。通知包括：

- 820010.xyz 登录态失效；
- Telegram Web 登录态失效；
- 820010.xyz 签到成功（包括“今日已签到”）；
- 网站签到失败或请求异常。

未配置这两个变量时，签到仍会执行，但通知会记录为 warning 并跳过。

## 运行

```bash
telegram-checkin validate
telegram-checkin once
telegram-checkin daemon
```

网站签到按钮默认使用 `#seat-checkin`，请求 `/api/seats/checkin`，而不是调用网站 API 绕过页面；站点返回的 toast/error 文本用于判断成功、已签到或失败。网站必须已经有有效的当前订阅，否则会报告“签到按钮未找到”。

## Docker

`compose.yaml` 会持久化 `/data`，其中包含两个 Playwright profile 和 SQLite 历史记录。建议先在有图形界面的机器上执行一次 `telegram-checkin login`，再把同一个 `DATA_DIR`/Docker volume 用于 daemon；daemon 本身保持无头运行。
