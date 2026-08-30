from __future__ import annotations

import unittest
from datetime import datetime, timezone

from telegram_checkin.runtime import next_run_at


class SchedulerTests(unittest.TestCase):
    def test_uses_same_day_when_schedule_is_ahead(self) -> None:
        now = datetime(2026, 8, 30, 0, 0, tzinfo=timezone.utc)

        scheduled = next_run_at(now, "08:30", "Asia/Shanghai")

        self.assertEqual(scheduled.isoformat(), "2026-08-30T08:30:00+08:00")

    def test_uses_next_day_after_schedule(self) -> None:
        now = datetime(2026, 8, 30, 1, 0, tzinfo=timezone.utc)

        scheduled = next_run_at(now, "08:30", "Asia/Shanghai")

        self.assertEqual(scheduled.isoformat(), "2026-08-31T08:30:00+08:00")


if __name__ == "__main__":
    unittest.main()
