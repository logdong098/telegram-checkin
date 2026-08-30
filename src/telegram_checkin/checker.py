from __future__ import annotations

from datetime import date
from typing import Protocol

from .models import BotConfig, CheckResult, CheckStatus
from .storage import AttemptStore


class TelegramSession(Protocol):
    async def open_bot(self, target: str, timeout_seconds: int) -> None: ...

    async def send_command(self, command: str, timeout_seconds: int) -> str: ...

    async def click_button(self, text: str, timeout_seconds: int) -> str: ...


def classify_text(text: str | None, bot: BotConfig) -> CheckStatus | None:
    if not text:
        return None
    normalized = " ".join(text.casefold().split())
    for status, patterns in (
        (CheckStatus.ALREADY, bot.already_patterns),
        (CheckStatus.SUCCESS, bot.success_patterns),
        (CheckStatus.FAILED, bot.failure_patterns),
    ):
        if any(pattern.casefold() in normalized for pattern in patterns):
            return status
    return None


async def check_bot(
    session: TelegramSession,
    store: AttemptStore,
    bot: BotConfig,
    local_date: date,
) -> CheckResult:
    if store.completed_on(bot.target, local_date):
        return CheckResult(bot.target, CheckStatus.SKIPPED, "already completed in local history")

    await session.open_bot(bot.target, bot.timeout_seconds)
    start_response = await session.send_command(bot.start_command, bot.timeout_seconds)
    start_status = classify_text(start_response, bot)
    if start_status is not None:
        return CheckResult(bot.target, start_status, _result_detail(start_response))

    checkin_response = await session.click_button(bot.button_text, bot.timeout_seconds)
    checkin_status = classify_text(checkin_response, bot)
    if checkin_status is not None:
        return CheckResult(bot.target, checkin_status, _result_detail(checkin_response))
    return CheckResult(bot.target, CheckStatus.UNCONFIRMED, _result_detail(checkin_response))


async def run_bot_safely(
    session: TelegramSession,
    store: AttemptStore,
    bot: BotConfig,
    local_date: date,
) -> CheckResult:
    try:
        result = await check_bot(session, store, bot, local_date)
    except Exception as exc:  # noqa: BLE001 - one bot must not abort the remaining batch
        result = CheckResult(bot.target, CheckStatus.ERROR, f"{type(exc).__name__}: {exc}")
    if result.status is not CheckStatus.SKIPPED:
        store.record(result, local_date)
    return result


def _result_detail(text: str | None) -> str:
    if not text:
        return "no recognizable response text"
    return " ".join(text.split())[:500]
