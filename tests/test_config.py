from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from telegram_checkin.config import ConfigError, load_app_config, load_runtime_config


class ConfigTests(unittest.TestCase):
    def test_loads_minimal_config_with_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text(
                """
schedule:
  time: "08:30"
  timezone: "Asia/Shanghai"
bots:
  - name: "@example_bot"
""",
                encoding="utf-8",
            )

            config = load_app_config(path)

        self.assertEqual(config.schedule.time, "08:30")
        self.assertEqual(config.bots[0].button_text, "签到")
        self.assertEqual(config.bots[0].start_command, "/start")

    def test_rejects_duplicate_targets_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text(
                """
schedule:
  time: "08:30"
  timezone: "UTC"
bots:
  - name: "@ExampleBot"
  - name: "@examplebot"
""",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigError, "duplicate bot name"):
                load_app_config(path)

    def test_rejects_invalid_schedule_time(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text(
                """
schedule:
  time: "25:00"
  timezone: "UTC"
bots:
  - name: "@example_bot"
""",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigError, "valid 24-hour time"):
                load_app_config(path)

    def test_runtime_uses_persistent_browser_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"DATA_DIR": directory}, clear=True
        ):
            runtime = load_runtime_config()

        self.assertEqual(runtime.browser_profile_path, str(Path(directory) / "browser-profile"))
        self.assertEqual(runtime.login_port, 8080)
        self.assertTrue(runtime.headless)

    def test_runtime_rejects_non_telegram_web_origin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            environment = {
                "DATA_DIR": directory,
                "TELEGRAM_WEB_URL": "https://example.com/",
            }
            with (
                patch.dict("os.environ", environment, clear=True),
                self.assertRaisesRegex(ConfigError, "web.telegram.org"),
            ):
                load_runtime_config()



if __name__ == "__main__":
    unittest.main()
