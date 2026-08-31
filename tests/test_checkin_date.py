"""Tests for the bot check-in date guard.

Some Telegram check-in bots (notably @shrekpublic_bot) respond with
"success" on a click but the server-side check-in date is still
yesterday's — meaning the click was a back-fill, not today's check-in.
We want our scheduler to surface this as UNCONFIRMED so the user (and
the notification) sees something is off.
"""
from __future__ import annotations

from datetime import date

import pytest

from telegram_checkin.checker import _date_mismatch, _extract_checkin_date


@pytest.mark.parametrize(
    "text,expected",
    [
        ("签到成功 | 6 花币 当前持有 | 1201 花币 签到日期 | 2026-08-29 22:45", date(2026, 8, 29)),
        ("签到日期:2026-08-31", date(2026, 8, 31)),
        ("签到日期｜2026/8/29", date(2026, 8, 29)),
        ("checkin date: 2026-12-01", date(2026, 12, 1)),
        ("Date | 2026-01-15 12:30", date(2026, 1, 15)),
    ],
)
def test_extract_checkin_date_finds_well_known_shapes(text: str, expected: date) -> None:
    assert _extract_checkin_date(text) == expected


def test_extract_checkin_date_returns_none_when_absent() -> None:
    assert _extract_checkin_date("just a regular reply") is None
    assert _extract_checkin_date("") is None
    assert _extract_checkin_date(None) is None


def test_extract_checkin_date_ignores_garbage() -> None:
    assert _extract_checkin_date("签到日期 | not-a-date") is None
    assert _extract_checkin_date("签到日期 | 2026-13-40") is None  # bad month/day


def test_date_mismatch_flags_old_dates() -> None:
    text = "签到成功 | 6 花币 签到日期 | 2026-08-29 22:45"
    today = date(2026, 8, 31)
    msg = _date_mismatch(text, today)
    assert msg is not None
    assert "2026-08-29" in msg
    assert "2026-08-31" in msg


def test_date_mismatch_passes_when_date_is_today() -> None:
    text = "签到成功 | 6 花币 签到日期 | 2026-08-31 12:00"
    today = date(2026, 8, 31)
    assert _date_mismatch(text, today) is None


def test_date_mismatch_passes_when_no_date_in_text() -> None:
    # Bots that don't report a date at all are unaffected — the guard
    # only fires when we positively see a wrong date.
    text = "签到成功 | 6 花币"
    today = date(2026, 8, 31)
    assert _date_mismatch(text, today) is None
