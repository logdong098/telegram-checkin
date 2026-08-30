from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from telegram_checkin.models import CheckResult, CheckStatus
from telegram_checkin.storage import AttemptStore


class AttemptStoreTests(unittest.TestCase):
    def test_only_successful_or_already_attempts_complete_the_day(self) -> None:
        local_date = date(2026, 8, 30)
        with tempfile.TemporaryDirectory() as directory:
            store = AttemptStore(str(Path(directory) / "attempts.sqlite3"))
            store.record(
                CheckResult("@bot", CheckStatus.UNCONFIRMED, "timeout"),
                local_date,
            )
            self.assertFalse(store.completed_on("@bot", local_date))

            store.record(
                CheckResult("@bot", CheckStatus.SUCCESS, "签到成功"),
                local_date,
            )
            self.assertTrue(store.completed_on("@bot", local_date))
            self.assertFalse(store.completed_on("@other_bot", local_date))


if __name__ == "__main__":
    unittest.main()
