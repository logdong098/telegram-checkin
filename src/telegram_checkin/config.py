from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from .models import (
    DEFAULT_ALREADY_PATTERNS,
    DEFAULT_FAILURE_PATTERNS,
    DEFAULT_SUCCESS_PATTERNS,
    AppConfig,
    BotConfig,
    RuntimeConfig,
    ScheduleConfig,
    WebsiteConfig,
)


class ConfigError(ValueError):
    pass


def _nonempty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{field} must be a non-empty string")
    return value.strip()


def _patterns(value: object, field: str, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    if not isinstance(value, list) or not value:
        raise ConfigError(f"{field} must be a non-empty list")
    return tuple(_nonempty_string(item, field) for item in value)


def load_app_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {config_path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {config_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError("config root must be a mapping")

    schedule_raw = raw.get("schedule")
    if not isinstance(schedule_raw, dict):
        raise ConfigError("schedule must be a mapping")
    schedule_time = _nonempty_string(schedule_raw.get("time"), "schedule.time")
    _validate_time(schedule_time)
    timezone = _nonempty_string(schedule_raw.get("timezone"), "schedule.timezone")
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ConfigError(f"unknown timezone: {timezone}") from exc

    bots_raw = raw.get("bots")
    if not isinstance(bots_raw, list) or not bots_raw:
        raise ConfigError("bots must be a non-empty list")

    bots: list[BotConfig] = []
    seen_targets: set[str] = set()
    for index, item in enumerate(bots_raw):
        field = f"bots[{index}]"
        if not isinstance(item, dict):
            raise ConfigError(f"{field} must be a mapping")
        target = _nonempty_string(item.get("name"), f"{field}.name")
        target_key = target.casefold()
        if target_key in seen_targets:
            raise ConfigError(f"duplicate bot name: {target}")
        seen_targets.add(target_key)

        timeout = item.get("timeout_seconds", 30)
        if not isinstance(timeout, int) or isinstance(timeout, bool) or not 5 <= timeout <= 300:
            raise ConfigError(f"{field}.timeout_seconds must be an integer from 5 to 300")

        bots.append(
            BotConfig(
                target=target,
                button_text=_nonempty_string(item.get("button", "签到"), f"{field}.button"),
                start_command=_nonempty_string(
                    item.get("start_command", "/start"), f"{field}.start_command"
                ),
                timeout_seconds=timeout,
                success_patterns=_patterns(
                    item.get("success_patterns"), f"{field}.success_patterns", DEFAULT_SUCCESS_PATTERNS
                ),
                already_patterns=_patterns(
                    item.get("already_patterns"), f"{field}.already_patterns", DEFAULT_ALREADY_PATTERNS
                ),
                failure_patterns=_patterns(
                    item.get("failure_patterns"), f"{field}.failure_patterns", DEFAULT_FAILURE_PATTERNS
                ),
            )
        )

    website_raw = raw.get("website", {})
    if website_raw is None:
        website_raw = {}
    if not isinstance(website_raw, dict):
        raise ConfigError("website must be a mapping")
    website_defaults = WebsiteConfig()
    website_timeout = website_raw.get("timeout_seconds", website_defaults.timeout_seconds)
    if (
        not isinstance(website_timeout, int)
        or isinstance(website_timeout, bool)
        or not 5 <= website_timeout <= 300
    ):
        raise ConfigError("website.timeout_seconds must be an integer from 5 to 300")

    return AppConfig(
        schedule=ScheduleConfig(time=schedule_time, timezone=timezone),
        bots=tuple(bots),
        website=WebsiteConfig(
            button_text=_nonempty_string(website_raw.get("button", "签到"), "website.button"),
            timeout_seconds=website_timeout,
            success_patterns=_patterns(
                website_raw.get("success_patterns"),
                "website.success_patterns",
                website_defaults.success_patterns,
            ),
            already_patterns=_patterns(
                website_raw.get("already_patterns"),
                "website.already_patterns",
                website_defaults.already_patterns,
            ),
            failure_patterns=_patterns(
                website_raw.get("failure_patterns"),
                "website.failure_patterns",
                website_defaults.failure_patterns,
            ),
        ),
    )


def load_runtime_config() -> RuntimeConfig:
    data_dir = Path(os.environ.get("DATA_DIR", "./data")).expanduser()
    data_dir.mkdir(parents=True, exist_ok=True)
    login_port = _environment_int("LOGIN_PORT", 8080, 1, 65535)
    login_timeout = _environment_int("LOGIN_TIMEOUT_SECONDS", 300, 30, 1800)
    telegram_web_url = os.environ.get("TELEGRAM_WEB_URL", "https://web.telegram.org/k/").strip()
    parsed_web_url = urlparse(telegram_web_url)
    if (
        parsed_web_url.scheme != "https"
        or parsed_web_url.hostname != "web.telegram.org"
        or not parsed_web_url.path.startswith("/k")
    ):
        raise ConfigError("TELEGRAM_WEB_URL must use https://web.telegram.org/k/")

    website_url = os.environ.get("WEBSITE_URL", "https://www.820010.xyz/").strip()
    parsed_website_url = urlparse(website_url)
    if (
        parsed_website_url.scheme != "https"
        or parsed_website_url.hostname not in {"820010.xyz", "www.820010.xyz"}
    ):
        raise ConfigError("WEBSITE_URL must use https://www.820010.xyz/")

    telegram_bot_token = _optional_environment("TELEGRAM_BOT_TOKEN")
    telegram_notify_chat_id = _optional_environment("TELEGRAM_NOTIFY_CHAT_ID")
    if bool(telegram_bot_token) != bool(telegram_notify_chat_id):
        raise ConfigError(
            "TELEGRAM_BOT_TOKEN and TELEGRAM_NOTIFY_CHAT_ID must be set together"
        )

    return RuntimeConfig(
        browser_profile_path=str(data_dir / "browser-profile"),
        website_browser_profile_path=str(data_dir / "website-browser-profile"),
        database_path=str(data_dir / "checkins.sqlite3"),
        login_screenshot_path=str(data_dir / "telegram-login.png"),
        telegram_web_url=telegram_web_url,
        website_url=website_url,
        headless=_environment_bool("BROWSER_HEADLESS", True),
        website_login_headless=_environment_bool("WEBSITE_LOGIN_HEADLESS", False),
        login_host=os.environ.get("LOGIN_HOST", "0.0.0.0").strip(),
        login_port=login_port,
        login_timeout_seconds=login_timeout,
        telegram_bot_token=telegram_bot_token,
        telegram_notify_chat_id=telegram_notify_chat_id,
        notification_timeout_seconds=_environment_int("NOTIFICATION_TIMEOUT_SECONDS", 15, 5, 120),
    )


def _optional_environment(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return None
    return value.strip()


def _environment_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    normalized = raw.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} must be true or false")


def _environment_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ConfigError(f"{name} must be from {minimum} to {maximum}")
    return value


def _validate_time(value: str) -> None:
    parts = value.split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ConfigError("schedule.time must use HH:MM")
    hour, minute = (int(part) for part in parts)
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ConfigError("schedule.time must be a valid 24-hour time")
