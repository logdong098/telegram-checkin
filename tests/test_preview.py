from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from telegram_checkin.preview import LoginPreviewServer


class LoginPreviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_serves_login_page_and_current_qr_image(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            screenshot = Path(directory) / "login.png"
            screenshot.write_bytes(b"png-bytes")
            async with LoginPreviewServer(str(screenshot), "127.0.0.1", 0) as server:
                page = await _get(server.port, "/")
                image = await _get(server.port, "/login.png")

        self.assertIn(b"200 OK", page)
        self.assertIn("Telegram Web 登录".encode(), page)
        self.assertIn(b"Content-Type: image/png", image)
        self.assertTrue(image.endswith(b"png-bytes"))


async def _get(port: int, path: str) -> bytes:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(f"GET {path} HTTP/1.1\r\nHost: localhost\r\n\r\n".encode())
    await writer.drain()
    response = await reader.read()
    writer.close()
    await writer.wait_closed()
    return response


if __name__ == "__main__":
    unittest.main()
