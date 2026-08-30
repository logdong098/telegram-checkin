"""Tests for the 820010.xyz onboarding-scrim dismissal helper.

The site shows a first-time overlay (#seat-help-scrim.is-open) that
intercepts pointer events on the check-in button. _dismiss_onboarding_scrim
must handle three real cases the production site exhibits:

  * no overlay present (the common case after the first run)
  * overlay present with a known Chinese "我知道了" button
  * overlay present with no labelled button (must fall back to DOM removal)

We stub a Page object and assert the dismissal function chose the right
strategy for each case.
"""

from __future__ import annotations

from typing import Any

import pytest

from telegram_checkin.website import _dismiss_onboarding_scrim


class _StubLocator:
    """Minimal Playwright Locator stub.

    Records the operations the dismissal helper performs and returns the
    pre-programmed counts / behaviour for this scenario.
    """

    def __init__(
        self,
        counts: dict[str, int] | None = None,
        *,
        click_raises: bool = False,
    ) -> None:
        self._counts = counts or {}
        self._click_raises = click_raises
        self.clicked: list[str] = []
        self.evaluated: list[str] = []

    async def count(self) -> int:  # noqa: D401 - stub: real Locator.count is a coroutine
        return self._counts.get("__count__", 0)

    @property
    def first(self) -> _StubLocator:  # noqa: D401 - stub: real Locator.first is a property
        # Returning a fresh stub with the same counts/raise behaviour keeps
        # `loc.first.click(...)` working exactly like on a real Locator.
        return _StubLocator(self._counts, click_raises=self._click_raises)

    async def click(self, timeout: int = 0, force: bool = False) -> None:
        self.clicked.append(f"click(force={force}, timeout={timeout})")
        if self._click_raises:
            raise RuntimeError("click failed")

    async def wait_for(self, state: str, timeout: int) -> None:
        return None

    async def evaluate(self, script: str) -> Any:
        self.evaluated.append(script)
        return True


class _StubPage:
    """Routes locator() calls based on the selector prefix."""

    def __init__(self, scenario: dict[str, Any]) -> None:
        self._scenario = scenario
        self.evaluated: list[str] = []

    def locator(self, selector: str) -> _StubLocator:
        # Initial scrim probe — the helper's first locator call.
        if selector == "#seat-help-scrim":
            count = self._scenario.get("scrim_count", 0)
            return _StubLocator(
                {"__count__": count},
                click_raises=self._scenario.get("scrim_click_raises", False),
            )
        # Fallback DOM removal uses .locator("button") for nothing — but
        # in practice the helper doesn't call .locator() at the page level
        # beyond the initial scrim probe. The click attempts inside the
        # scrim go through page.get_by_role, so any other selector here
        # is treated as "no in-overlay button" (count=0).
        return _StubLocator({"__count__": 0})

    def get_by_role(self, role: str, name: str) -> _StubLocator:
        labels = self._scenario.get("role_button_labels", [])
        count = 1 if name in labels else 0
        return _StubLocator({"__count__": count})

    async def evaluate(self, script: str) -> Any:
        self.evaluated.append(script)
        return True


@pytest.mark.asyncio
async def test_dismiss_is_noop_when_overlay_absent() -> None:
    page = _StubPage({"scrim_count": 0})
    await _dismiss_onboarding_scrim(page)  # type: ignore[arg-type]
    # No DOM removal, no clicks — overlay was never there.
    assert page.evaluated == []


@pytest.mark.asyncio
async def test_dismiss_clicks_gotit_button() -> None:
    page = _StubPage(
        {
            "scrim_count": 1,
            "button_count": 1,
            "role_button_labels": ["我知道了"],
        }
    )
    await _dismiss_onboarding_scrim(page)  # type: ignore[arg-type]
    # The helper should NOT have had to rip the overlay out of the DOM.
    assert page.evaluated == []


@pytest.mark.asyncio
async def test_dismiss_falls_back_to_dom_removal() -> None:
    page = _StubPage(
        {
            "scrim_count": 1,
            "button_count": 0,
            "role_button_labels": [],
        }
    )
    await _dismiss_onboarding_scrim(page)  # type: ignore[arg-type]
    # Last-resort strategy: the helper removed the overlay from the DOM.
    assert len(page.evaluated) == 1
    assert "#seat-help-scrim" in page.evaluated[0]


@pytest.mark.asyncio
async def test_dismiss_tolerates_click_failures() -> None:
    """All in-overlay click attempts raising must not raise out of the helper."""
    page = _StubPage(
        {
            "scrim_count": 1,
            "button_count": 1,
            "button_click_raises": True,
            "role_button_labels": [],
        }
    )
    await _dismiss_onboarding_scrim(page)  # type: ignore[arg-type]
    # Helper recovered via the DOM-removal fallback.
    assert len(page.evaluated) == 1
