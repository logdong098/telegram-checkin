from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta
from pathlib import Path
from time import monotonic
from zoneinfo import ZoneInfo

from .checker import check_website, run_bot_safely
from .models import AppConfig, CheckResult, CheckStatus, RuntimeConfig
from .notify import TelegramNotifier
from .preview import LoginPreviewServer
from .storage import AttemptStore
from .web import AuthorizationError, TelegramWebClient
from .website import WebsiteClient

LOGGER = logging.getLogger(__name__)


def next_run_at(now: datetime, schedule_time: str, timezone: str) -> datetime:
    zone = ZoneInfo(timezone)
    local_now = now.astimezone(zone)
    hour, minute = (int(part) for part in schedule_time.split(":"))
    candidate = datetime.combine(local_now.date(), time(hour, minute), tzinfo=zone)
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate


async def login(runtime: RuntimeConfig) -> None:
    await _login_website(runtime)

    screenshot = Path(runtime.login_screenshot_path)
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    screenshot.unlink(missing_ok=True)
    try:
        async with TelegramWebClient(runtime) as client:
            await client.open_home()
            if not await client.login_required():
                await client.ensure_authenticated()
                print("Telegram Web session is already authorized")
                return

            async with LoginPreviewServer(
                runtime.login_screenshot_path, runtime.login_host, runtime.login_port
            ):
                print(f"Open http://127.0.0.1:{runtime.login_port} and scan the Telegram QR code")
                deadline = monotonic() + runtime.login_timeout_seconds
                while monotonic() < deadline:
                    if not await client.login_required():
                        await client.ensure_authenticated()
                        print("Telegram Web session authorized")
                        return
                    await client.save_login_preview(runtime.login_screenshot_path)
                    await asyncio.sleep(2)
                raise AuthorizationError(
                    f"Telegram Web login timed out after {runtime.login_timeout_seconds} seconds"
                )
    finally:
        screenshot.unlink(missing_ok=True)


async def run_once(app: AppConfig, runtime: RuntimeConfig) -> tuple[CheckResult, ...]:
    store = AttemptStore(runtime.database_path)
    notifier = TelegramNotifier(
        runtime.telegram_bot_token,
        runtime.telegram_notify_chat_id,
        runtime.notification_timeout_seconds,
    )

    try:
        async with TelegramWebClient(runtime) as client:
            await client.open_home()
            await client.ensure_authenticated()

            zone = ZoneInfo(app.schedule.timezone)
            local_date = datetime.now(zone).date()
            results: list[CheckResult] = []
            for bot in app.bots:
                result = await run_bot_safely(client, store, bot, local_date)
                results.append(result)
                LOGGER.info(
                    "bot=%s status=%s detail=%s", result.target, result.status.value, result.detail
                )
                # A session can expire after the initial page load; verify it
                # between bots so the alert is not delayed until tomorrow.
                await client.ensure_authenticated()
    except AuthorizationError as exc:
        await _send_alert(
            notifier,
            "⚠️ Telegram 登录态已失效，自动签到未执行。请运行 `telegram-checkin login` 重新登录。\n"
            f"原因：{exc}",
        )
        raise

    website_target = runtime.website_url
    try:
        async with WebsiteClient(runtime) as client:
            # Validate the website session even when local history would skip
            # today's click, so expired cookies are still reported promptly.
            await client.open_home()
            await client.ensure_authenticated()
            website_result = await check_website(
                client, store, app.website, local_date, website_target
            )
    except AuthorizationError as exc:
        website_result = CheckResult(website_target, CheckStatus.ERROR, str(exc))
        await _send_alert(
            notifier,
            "⚠️ 820010.xyz 登录态已失效，签到未执行。请运行 `telegram-checkin login` 重新登录。\n"
            f"原因：{exc}",
        )
    except Exception as exc:  # noqa: BLE001 - retain bot check-ins if the site is unavailable
        website_result = CheckResult(
            website_target, CheckStatus.ERROR, f"{type(exc).__name__}: {exc}"
        )
        await _send_alert(
            notifier,
            f"⚠️ 820010.xyz 签到失败\n原因：{website_result.detail}",
        )
    else:
        if website_result.status is not CheckStatus.SKIPPED:
            store.record(website_result, local_date)
        if website_result.status in {CheckStatus.SUCCESS, CheckStatus.ALREADY}:
            await _send_alert(
                notifier,
                f"✅ 820010.xyz 签到成功\n结果：{website_result.detail}",
            )
        elif website_result.status in {
            CheckStatus.FAILED,
            CheckStatus.UNCONFIRMED,
            CheckStatus.ERROR,
        }:
            await _send_alert(
                notifier,
                f"⚠️ 820010.xyz 签到未成功\n结果：{website_result.detail}",
            )

    results.append(website_result)
    return tuple(results)


async def _login_website(runtime: RuntimeConfig) -> None:
    try:
        async with WebsiteClient(runtime, headless=runtime.website_login_headless) as client:
            await client.open_home()
            if await client.login_required():
                if runtime.website_login_headless:
                    raise AuthorizationError(
                        "820010.xyz session is missing; set WEBSITE_LOGIN_HEADLESS=false "
                        "and run login on a machine with a display"
                    )
                print(
                    "A browser window for 820010.xyz has been opened. "
                    "Log in there; the session will be saved automatically."
                )
                await client.wait_for_login(runtime.login_timeout_seconds)
                print("820010.xyz session authorized")
            else:
                print("820010.xyz session is already authorized")
    except AuthorizationError:
        raise
    except Exception as exc:  # noqa: BLE001 - add a useful hint for headless Docker users
        if runtime.website_login_headless is False:
            raise AuthorizationError(
                "could not open the interactive 820010.xyz login browser; "
                "run login on a machine with a display or set WEBSITE_LOGIN_HEADLESS=true"
            ) from exc
        raise


async def _send_alert(notifier: TelegramNotifier, text: str) -> None:
    try:
        await notifier.send(text)
    except Exception:  # noqa: BLE001 - an alert outage must not stop scheduled check-ins
        LOGGER.exception("failed to send Telegram notification")


async def run_daemon(app: AppConfig, runtime: RuntimeConfig) -> None:
    LOGGER.info(
        "scheduler started time=%s timezone=%s bots=%d",
        app.schedule.time,
        app.schedule.timezone,
        len(app.bots),
    )
    while True:
        scheduled = next_run_at(datetime.now().astimezone(), app.schedule.time, app.schedule.timezone)
        delay = max(0.0, (scheduled - datetime.now(scheduled.tzinfo)).total_seconds())
        LOGGER.info("next run at %s", scheduled.isoformat())
        await asyncio.sleep(delay)
        try:
            await run_once(app, runtime)
        except Exception:
            LOGGER.exception("scheduled check-in batch failed")
        await asyncio.sleep(1)


def exit_code(results: tuple[CheckResult, ...]) -> int:
    failing = {CheckStatus.FAILED, CheckStatus.UNCONFIRMED, CheckStatus.ERROR}
    return 1 if any(result.status in failing for result in results) else 0
