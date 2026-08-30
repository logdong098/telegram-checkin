from __future__ import annotations

import unittest
from datetime import date

from telegram_checkin.checker import check_bot, classify_text
from telegram_checkin.models import BotConfig, CheckStatus


class CheckerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bot = BotConfig(target="@example_bot")

    def test_classifies_already_before_other_statuses(self) -> None:
        status = classify_text("🎉 今日已签到，请勿重复操作", self.bot)

        self.assertEqual(status, CheckStatus.ALREADY)

    def test_classifies_success_case_insensitively(self) -> None:
        status = classify_text("CHECK-IN SUCCESSFUL", self.bot)

        self.assertEqual(status, CheckStatus.SUCCESS)


class CheckinWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_sends_start_clicks_button_and_reads_result(self) -> None:
        session = _FakeSession("请选择功能", "🎉 签到成功 | 6 花币")
        store = _FakeStore()

        result = await check_bot(
            session,
            store,
            BotConfig(target="@example_bot"),
            date(2026, 8, 30),
        )

        self.assertEqual(session.calls, [
            ("open", "@example_bot"),
            ("send", "/start"),
            ("click", "签到"),
        ])
        self.assertEqual(result.status, CheckStatus.SUCCESS)

    async def test_does_not_click_after_already_response(self) -> None:
        session = _FakeSession("今日已签到", "should not be used")
        store = _FakeStore()

        result = await check_bot(
            session,
            store,
            BotConfig(target="@example_bot"),
            date(2026, 8, 30),
        )

        self.assertEqual(session.calls, [
            ("open", "@example_bot"),
            ("send", "/start"),
        ])
        self.assertEqual(result.status, CheckStatus.ALREADY)

    async def test_skips_network_when_local_history_is_complete(self) -> None:
        session = _FakeSession("unused", "unused")
        store = _FakeStore(completed=True)

        result = await check_bot(
            session,
            store,
            BotConfig(target="@example_bot"),
            date(2026, 8, 30),
        )

        self.assertEqual(session.calls, [])
        self.assertEqual(result.status, CheckStatus.SKIPPED)


class _FakeSession:
    def __init__(self, start_response: str, checkin_response: str) -> None:
        self.start_response = start_response
        self.checkin_response = checkin_response
        self.calls: list[tuple[str, str]] = []

    async def open_bot(self, target: str, timeout_seconds: int) -> None:
        self.calls.append(("open", target))

    async def send_command(self, command: str, timeout_seconds: int) -> str:
        self.calls.append(("send", command))
        return self.start_response

    async def click_button(self, text: str, timeout_seconds: int) -> str:
        self.calls.append(("click", text))
        return self.checkin_response


class _FakeStore:
    def __init__(self, completed: bool = False) -> None:
        self.completed = completed

    def completed_on(self, target: str, local_date: date) -> bool:
        return self.completed


if __name__ == "__main__":
    unittest.main()
