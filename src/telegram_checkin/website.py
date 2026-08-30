from __future__ import annotations

import asyncio
from pathlib import Path
from time import monotonic
from urllib.parse import quote, urlparse

from playwright.async_api import BrowserContext, Page, Playwright, Request, Response, Route, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeout

from .models import RuntimeConfig, WebsiteConfig
from .web import AuthorizationError, WebAutomationError

_SITE_HOSTS = {"820010.xyz", "www.820010.xyz", "auth.820010.xyz"}
_AUTH_FLOW_HOSTS = {"github.com", "linux.do", "oauth.telegram.org", "telegram.org"}
_SITE_ROOT_SELECTOR = "#root"
_CHECKIN_BUTTON_SELECTOR = "#seat-checkin"


class WebsiteCheckinError(WebAutomationError):
    pass


class WebsiteClient:
    """Playwright client for the 820010.xyz account and check-in page."""

    def __init__(self, runtime: RuntimeConfig, *, headless: bool | None = None) -> None:
        self._runtime = runtime
        self._headless = runtime.headless if headless is None else headless
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def __aenter__(self) -> WebsiteClient:  # noqa: PYI034
        Path(self._runtime.website_browser_profile_path).mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        self._context = await self._playwright.chromium.launch_persistent_context(
            self._runtime.website_browser_profile_path,
            headless=self._headless,
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
        await page.goto(self._runtime.website_url, wait_until="domcontentloaded")
        await page.locator(_SITE_ROOT_SELECTOR).wait_for(state="attached", timeout=20_000)
        await page.wait_for_timeout(1_000)

    async def is_authenticated(self) -> bool:
        page = self._require_page()
        if await self._is_login_page():
            return False
        try:
            result = await page.evaluate(
                """async () => {
                    const response = await fetch('/api/me', {credentials: 'same-origin',
                        headers: {Accept: 'application/json'}});
                    return {status: response.status, body: await response.json().catch(() => ({}))};
                }"""
            )
        except Exception:  # noqa: BLE001 - a navigation/network error means not authorized
            return False
        body = result.get("body") if isinstance(result, dict) else None
        return isinstance(body, dict) and bool(body.get("user"))

    async def login_required(self) -> bool:
        return not await self.is_authenticated()

    async def ensure_authenticated(self) -> None:
        if not await self.is_authenticated():
            raise AuthorizationError(
                "820010.xyz session is not authorized; run the login command first"
            )

    async def wait_for_login(self, timeout_seconds: int) -> None:
        page = self._require_page()
        next_url = self._runtime.website_url
        login_url = "https://auth.820010.xyz/login?next=" + quote(next_url, safe="")
        await page.goto(login_url, wait_until="domcontentloaded")
        deadline = monotonic() + timeout_seconds
        while monotonic() < deadline:
            if await self._on_site_host() and await self.is_authenticated():
                return
            await asyncio.sleep(1)
        raise AuthorizationError(
            f"820010.xyz login timed out after {timeout_seconds} seconds"
        )

    async def checkin(self, config: WebsiteConfig) -> tuple[bool, str]:
        await self.open_home()
        await self.ensure_authenticated()
        page = self._require_page()
        button = page.locator(_CHECKIN_BUTTON_SELECTOR).first
        if await button.count() == 0 or config.button_text != "签到":
            button = page.get_by_role("button", name=config.button_text, exact=True).first
        try:
            await button.wait_for(state="visible", timeout=config.timeout_seconds * 1_000)
        except PlaywrightTimeout as exc:
            raise WebsiteCheckinError(
                "820010.xyz check-in button was not found; verify that a subscription is active"
            ) from exc

        try:
            async with page.expect_response(
                lambda response: "/api/seats/checkin" in response.url,
                timeout=config.timeout_seconds * 1_000,
            ) as response_info:
                await button.click()
            response = await response_info.value
        except PlaywrightTimeout as exc:
            raise WebsiteCheckinError("820010.xyz check-in request timed out") from exc

        payload = await _response_payload(response)
        if response.status in {401, 403}:
            raise AuthorizationError("820010.xyz session is no longer authorized")
        detail = _payload_detail(payload)
        if isinstance(payload, dict) and payload.get("ok") is True:
            return True, detail or "签到成功"
        return False, detail or f"check-in request failed (HTTP {response.status})"

    async def _is_login_page(self) -> bool:
        page = self._require_page()
        parsed = urlparse(page.url)
        if parsed.hostname == "auth.820010.xyz":
            return True
        return await page.locator("form#login-form").is_visible()

    async def _on_site_host(self) -> bool:
        hostname = urlparse(self._require_page().url).hostname
        return hostname in {"820010.xyz", "www.820010.xyz"}

    async def _guard_external_navigation(self, route: Route, request: Request) -> None:
        if request.is_navigation_request():
            hostname = urlparse(request.url).hostname
            if hostname not in _SITE_HOSTS and hostname not in _AUTH_FLOW_HOSTS:
                await route.abort()
                return
        await route.continue_()

    def _require_page(self) -> Page:
        if self._page is None:
            raise RuntimeError("WebsiteClient is not open")
        return self._page


async def _response_payload(response: Response) -> object:
    try:
        return await response.json()
    except Exception:  # noqa: BLE001 - retain HTTP status when the server sends non-JSON
        return {}


def _payload_detail(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    value = payload.get("toast") or payload.get("error") or payload.get("message")
    return " ".join(str(value).split())[:500] if value else ""
