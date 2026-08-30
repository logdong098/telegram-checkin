from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

DEFAULT_SUCCESS_PATTERNS = ("签到成功", "打卡成功", "check-in successful", "check in successful")
DEFAULT_ALREADY_PATTERNS = ("今日已签到", "今天已签到", "已经签到", "已签到", "already checked in")
DEFAULT_FAILURE_PATTERNS = ("签到失败", "打卡失败", "check-in failed", "check in failed")


@dataclass(frozen=True, slots=True)
class BotConfig:
    target: str
    button_text: str = "签到"
    start_command: str = "/start"
    timeout_seconds: int = 30
    success_patterns: tuple[str, ...] = DEFAULT_SUCCESS_PATTERNS
    already_patterns: tuple[str, ...] = DEFAULT_ALREADY_PATTERNS
    failure_patterns: tuple[str, ...] = DEFAULT_FAILURE_PATTERNS


@dataclass(frozen=True, slots=True)
class ScheduleConfig:
    time: str
    timezone: str


@dataclass(frozen=True, slots=True)
class WebsiteConfig:
    button_text: str = "签到"
    timeout_seconds: int = 30
    success_patterns: tuple[str, ...] = ("签到成功", "check-in successful", "check in successful")
    already_patterns: tuple[str, ...] = ("今日已签到", "今天已签到", "已签到", "already checked in")
    failure_patterns: tuple[str, ...] = ("签到失败", "check-in failed", "check in failed")


@dataclass(frozen=True, slots=True)
class AppConfig:
    schedule: ScheduleConfig
    bots: tuple[BotConfig, ...]
    website: WebsiteConfig = WebsiteConfig()


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    browser_profile_path: str
    website_browser_profile_path: str
    database_path: str
    login_screenshot_path: str
    telegram_web_url: str
    website_url: str
    headless: bool
    website_login_headless: bool
    login_host: str
    login_port: int
    login_timeout_seconds: int
    telegram_bot_token: str | None
    telegram_notify_chat_id: str | None
    notification_timeout_seconds: int


class CheckStatus(str, Enum):
    SUCCESS = "success"
    ALREADY = "already"
    FAILED = "failed"
    UNCONFIRMED = "unconfirmed"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class CheckResult:
    target: str
    status: CheckStatus
    detail: str
