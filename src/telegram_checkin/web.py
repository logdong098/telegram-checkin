from __future__ import annotations

import asyncio
from pathlib import Path
from time import monotonic
from urllib.parse import quote, urlparse

from playwright.async_api import (
    BrowserContext,
    Locator,
    Page,
    Playwright,
    Request,
    Route,
    async_playwright,
)
from playwright.async_api import TimeoutError as PlaywrightTimeout

from .models import RuntimeConfig

_AUTH_SELECTOR = "#auth-pages"
_CHAT_READY_SELECTOR = ".input-search-input"
_COMPOSER_SELECTOR = (
    ".input-message-input[contenteditable='true'], "
    "#editable-message-text[contenteditable='true']"
)
_MESSAGE_SELECTOR = ".bubble[data-mid]:not(.is-out)"
_BUTTON_SELECTOR = ".reply-markup-button"
_SEARCH_SELECTOR = ".input-search-input"
_SEARCH_SCOPE_SELECTOR = "#column-left"
_SEARCH_RESULT_SELECTOR = f"{_SEARCH_SCOPE_SELECTOR} .search-group-content a.row-clickable"
_TOAST_SELECTOR = ".toast, .toast-container"
_BLOCKED_BUTTON_CLASSES = (
    "is-link",
    "is-switch-inline",
    "is-buy",
    "is-url-auth",
    "is-web-view",
    "is-request-phone",
    "is-game",
)


class WebAutomationError(RuntimeError):
    pass


class AuthorizationError(WebAutomationError):
    pass


class BotNotFoundError(WebAutomationError):
    pass


class TelegramWebClient:
    def __init__(self, runtime: RuntimeConfig) -> None:
        self._runtime = runtime
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def __aenter__(self) -> TelegramWebClient:  # noqa: PYI034
        Path(self._runtime.browser_profile_path).mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        self._context = await self._playwright.chromium.launch_persistent_context(
            self._runtime.browser_profile_path,
            headless=self._runtime.headless,
            viewport={"width": 1440, "height": 1000},
            accept_downloads=False,
        )
        await self._context.route("**/*", self._guard_external_navigation)
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        self._page.set_default_timeout(10_000)
        self._page.on("popup", lambda popup: asyncio.create_task(popup.close()))
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._context is not None:
            await self._context.close()
        if self._playwright is not None:
            await self._playwright.stop()

    async def open_home(self) -> None:
        page = self._require_page()
        await page.goto(self._runtime.telegram_web_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(1_500)

    async def ensure_authenticated(self) -> None:
        page = self._require_page()
        if await page.locator(_AUTH_SELECTOR).is_visible():
            raise AuthorizationError("Telegram Web session is not authorized; run the login command first")
        try:
            await page.locator(_CHAT_READY_SELECTOR).first.wait_for(state="visible", timeout=20_000)
        except PlaywrightTimeout as exc:
            raise AuthorizationError("Telegram Web did not reach the authenticated chat interface") from exc

    async def login_required(self) -> bool:
        return await self._require_page().locator(_AUTH_SELECTOR).is_visible()

    async def save_login_preview(self, path: str) -> None:
        auth_page = self._require_page().locator(_AUTH_SELECTOR)
        await auth_page.wait_for(state="visible", timeout=20_000)
        qr_canvas = auth_page.locator("canvas").last
        await qr_canvas.wait_for(state="visible", timeout=20_000)
        await qr_canvas.screenshot(path=path)

    async def open_bot(self, target: str, timeout_seconds: int) -> None:
        page = self._require_page()
        timeout_ms = timeout_seconds * 1_000
        if target.startswith("@"):
            safe_target = quote(target, safe="@_")
            await page.goto(
                f"{self._runtime.telegram_web_url}#{safe_target}",
                wait_until="domcontentloaded",
            )
        else:
            await self._open_bot_by_display_name(target, timeout_ms)

        try:
            await self._composer().wait_for(state="visible", timeout=timeout_ms)
        except PlaywrightTimeout as exc:
            raise BotNotFoundError(f"bot chat did not open: {target}") from exc
        await page.wait_for_timeout(750)

    async def send_command(self, command: str, timeout_seconds: int) -> str:
        before = await self._message_snapshot()
        before_toast = await self._visible_toast_text()
        composer = self._composer()
        await composer.fill(command)
        await composer.press("Enter")
        return await self._wait_for_conversation_change(before, before_toast, timeout_seconds)

    async def click_button(self, text: str, timeout_seconds: int) -> str:
        button = await self._wait_for_button(text, timeout_seconds)
        href = await button.get_attribute("href")
        contains_link = bool(await button.locator("a[href]").count())
        classes = await button.get_attribute("class")
        if not button_action_is_safe(href, contains_link, classes):
            raise WebAutomationError(f"button '{text}' requires an external or sensitive action")

        before = await self._message_snapshot()
        before_toast = await self._visible_toast_text()
        await button.click()
        return await self._wait_for_conversation_change(before, before_toast, timeout_seconds)

    async def _open_bot_by_display_name(self, target: str, timeout_ms: int) -> None:
        page = self._require_page()
        await page.goto(self._runtime.telegram_web_url, wait_until="domcontentloaded")
        await self.ensure_authenticated()
        search = page.locator(_SEARCH_SELECTOR).first
        await search.wait_for(state="visible", timeout=timeout_ms)
        search_query = target[:-4] if target.casefold().endswith(" bot") else target
        await search.fill(search_query)
        try:
            result = await self._wait_for_search_result(target, timeout_ms / 1_000)
            await result.click()
        except TimeoutError as exc:
            raise BotNotFoundError(
                f"bot display name not found: {target}; configure its @username instead"
            ) from exc

    async def _wait_for_search_result(self, target: str, timeout_seconds: float) -> Locator:
        deadline = monotonic() + timeout_seconds
        matches = self._require_page().locator(_SEARCH_RESULT_SELECTOR)
        target_text = " ".join(target.casefold().split())
        target_without_bot = target_text.removesuffix(" bot")
        while monotonic() < deadline:
            for index in range(await matches.count()):
                candidate = matches.nth(index)
                if not await candidate.is_visible():
                    continue
                candidate_text = " ".join(
                    (await candidate.locator(".peer-title").inner_text()).casefold().split()
                )
                if candidate_text in {target_text, target_without_bot} or target_without_bot in candidate_text:
                    return candidate
            await asyncio.sleep(0.5)
        raise TimeoutError(f"search result not found: {target}")

    async def _wait_for_button(self, expected_text: str, timeout_seconds: int) -> Locator:
        deadline = monotonic() + timeout_seconds
        buttons = self._require_page().locator(_BUTTON_SELECTOR)
        while monotonic() < deadline:
            count = await buttons.count()
            for index in range(count - 1, -1, -1):
                candidate = buttons.nth(index)
                if (await candidate.inner_text()).strip() == expected_text and await candidate.is_visible():
                    return candidate
            await asyncio.sleep(0.5)
        raise TimeoutError(f"button not found: {expected_text}")

    async def _wait_for_conversation_change(
        self, before: tuple[tuple[str, str], ...], before_toast: str, timeout_seconds: int
    ) -> str:
        deadline = monotonic() + timeout_seconds
        while monotonic() < deadline:
            after = await self._message_snapshot()
            changed = changed_message_texts(before, after)
            toast = await self._visible_toast_text()
            new_toast = toast if toast != before_toast else ""
            if changed or new_toast:
                return "\n".join((*changed, new_toast) if new_toast else changed)
            await asyncio.sleep(0.5)
        raise TimeoutError(f"conversation did not change within {timeout_seconds} seconds")

    async def _message_snapshot(self) -> tuple[tuple[str, str], ...]:
        messages = self._require_page().locator(_MESSAGE_SELECTOR)
        snapshot: list[tuple[str, str]] = []
        for index in range(await messages.count()):
            message = messages.nth(index)
            message_id = await message.get_attribute("data-mid")
            text = " ".join((await message.inner_text()).split())
            if message_id and text:
                snapshot.append((message_id, text))
        return tuple(snapshot)

    async def _visible_toast_text(self) -> str:
        toasts = self._require_page().locator(_TOAST_SELECTOR)
        for index in range(await toasts.count() - 1, -1, -1):
            toast = toasts.nth(index)
            if await toast.is_visible():
                return " ".join((await toast.inner_text()).split())
        return ""

    def _composer(self) -> Locator:
        return self._require_page().locator(_COMPOSER_SELECTOR).first

    def _require_page(self) -> Page:
        if self._page is None:
            raise RuntimeError("TelegramWebClient is not open")
        return self._page

    async def _guard_external_navigation(self, route: Route, request: Request) -> None:
        if request.is_navigation_request():
            host = urlparse(request.url).hostname
            if host != "web.telegram.org":
                await route.abort()
                return
        await route.continue_()


def changed_message_texts(
    before: tuple[tuple[str, str], ...],
    after: tuple[tuple[str, str], ...],
) -> tuple[str, ...]:
    before_by_id = dict(before)
    before_max_id = max(
        (int(message_id) for message_id, _ in before if message_id.isdecimal()),
        default=None,
    )
    changed: list[str] = []
    for message_id, text in after:
        previous = before_by_id.get(message_id)
        if previous is not None:
            if previous != text:
                changed.append(text)
            continue
        if before_max_id is None or not message_id.isdecimal() or int(message_id) > before_max_id:
            changed.append(text)
    return tuple(changed)


def button_action_is_safe(
    href: str | None, contains_link: bool, classes: str | None
) -> bool:
    if href or contains_link:
        return False
    normalized_classes = (classes or "").casefold()
    return not any(marker in normalized_classes for marker in _BLOCKED_BUTTON_CLASSES)
