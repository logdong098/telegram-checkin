from __future__ import annotations

import re
from datetime import date
from typing import Protocol

from .models import BotConfig, CheckResult, CheckStatus, WebsiteConfig
from .storage import AttemptStore


class TelegramSession(Protocol):
    async def open_bot(self, target: str, timeout_seconds: int) -> None: ...

    async def send_command(self, command: str, timeout_seconds: int) -> str: ...

    async def click_button(self, text: str, timeout_seconds: int) -> str: ...


class WebsiteSession(Protocol):
    async def checkin(self, config: WebsiteConfig) -> tuple[bool, str]: ...


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


# Some bots (e.g. @shrekpublic_bot) report the date the check-in
# actually counted towards in the response text, e.g.
#   "签到日期 | 2026-08-29 22:45"
# If that date isn't today, the click succeeded but it only counted as a
# back-fill for a missed day — the user still needs to click again for
# today. We expose the check so per-bot config can opt in.
_CHECKIN_DATE_RE = re.compile(
    r"(?:签到日期|checkin[_ ]?date|date)\s*[\|:｜]\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})",
    re.IGNORECASE,
)


def _extract_checkin_date(text: str | None) -> date | None:
    if not text:
        return None
    m = _CHECKIN_DATE_RE.search(text)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _date_mismatch(
    text: str | None, expected: date
) -> str | None:
    """Return a detail suffix if `text` contains a check-in date that
    isn't today; otherwise None."""
    actual = _extract_checkin_date(text)
    if actual is None or actual == expected:
        return None
    return f"date guard: bot reported {actual.isoformat()}, expected {expected.isoformat()}"


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
        # If the bot reports "success" but the date guard sees an
        # old check-in date, downgrade to UNCONFIRMED so the user (and
        # the notification) can act on it.
        if checkin_status is CheckStatus.SUCCESS and getattr(bot, "enforce_checkin_date", True):
            mismatch = _date_mismatch(checkin_response, local_date)
            if mismatch:
                return CheckResult(
                    bot.target,
                    CheckStatus.UNCONFIRMED,
                    f"{_result_detail(checkin_response)} | {mismatch}",
                )
        return CheckResult(bot.target, checkin_status, _result_detail(checkin_response))
    return CheckResult(bot.target, CheckStatus.UNCONFIRMED, _result_detail(checkin_response))


async def check_website(
    session: WebsiteSession,
    store: AttemptStore,
    config: WebsiteConfig,
    local_date: date,
    target: str,
) -> CheckResult:
    if store.completed_on(target, local_date):
        return CheckResult(target, CheckStatus.SKIPPED, "already completed in local history")

    successful_request, response_text = await session.checkin(config)
    status = classify_patterns(
        response_text,
        config.success_patterns,
        config.already_patterns,
        config.failure_patterns,
    )
    if status is None:
        status = CheckStatus.SUCCESS if successful_request else CheckStatus.FAILED
    return CheckResult(target, status, _result_detail(response_text))


def classify_patterns(
    text: str | None,
    success_patterns: tuple[str, ...],
    already_patterns: tuple[str, ...],
    failure_patterns: tuple[str, ...],
) -> CheckStatus | None:
    if not text:
        return None
    normalized = " ".join(text.casefold().split())
    for status, patterns in (
        (CheckStatus.ALREADY, already_patterns),
        (CheckStatus.SUCCESS, success_patterns),
        (CheckStatus.FAILED, failure_patterns),
    ):
        if any(pattern.casefold() in normalized for pattern in patterns):
            return status
    return None


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
