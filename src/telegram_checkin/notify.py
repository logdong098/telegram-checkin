from __future__ import annotations

import asyncio
import json
import logging
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LOGGER = logging.getLogger(__name__)


class TelegramNotifier:
    """Send alerts through a Bot API token, independent of Telegram Web cookies."""

    def __init__(self, token: str | None, chat_id: str | None, timeout_seconds: int = 15) -> None:
        self._token = token
        self._chat_id = chat_id
        self._timeout_seconds = timeout_seconds

    @property
    def enabled(self) -> bool:
        return bool(self._token and self._chat_id)

    async def send(self, text: str) -> None:
        if not self.enabled:
            LOGGER.warning(
                "Telegram notification skipped: set TELEGRAM_BOT_TOKEN and "
                "TELEGRAM_NOTIFY_CHAT_ID"
            )
            return
        assert self._token is not None
        assert self._chat_id is not None
        await asyncio.to_thread(self._send_sync, text)

    def _send_sync(self, text: str) -> None:
        endpoint = f"https://api.telegram.org/bot{self._token}/sendMessage"
        body = urlencode({"chat_id": self._chat_id, "text": text}).encode("utf-8")
        request = Request(endpoint, data=body, method="POST")
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310 - fixed HTTPS endpoint
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise RuntimeError(f"Telegram Bot API rejected notification: {payload}")
