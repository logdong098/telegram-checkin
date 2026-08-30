from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta
from pathlib import Path
from time import monotonic
from zoneinfo import ZoneInfo

from .checker import run_bot_safely
from .models import AppConfig, CheckResult, CheckStatus, RuntimeConfig
from .preview import LoginPreviewServer
from .storage import AttemptStore
from .web import AuthorizationError, TelegramWebClient

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
    async with TelegramWebClient(runtime) as client:
        await client.open_home()
        await client.ensure_authenticated()

        zone = ZoneInfo(app.schedule.timezone)
        local_date = datetime.now(zone).date()
        results: list[CheckResult] = []
        for bot in app.bots:
            result = await run_bot_safely(client, store, bot, local_date)
            results.append(result)
            LOGGER.info("bot=%s status=%s detail=%s", result.target, result.status.value, result.detail)
        return tuple(results)


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
