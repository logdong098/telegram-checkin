from __future__ import annotations

import asyncio
from pathlib import Path

_LOGIN_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Telegram Web Login</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem; text-align: center; }
    img { width: min(82vw, 420px); image-rendering: pixelated; border: 1px solid #ddd; border-radius: 12px; }
  </style>
</head>
<body>
  <h1>Telegram Web 登录</h1>
  <p>在手机 Telegram 中打开“设置 → 设备 → 连接桌面设备”，扫描下面二维码。</p>
  <img id="qr" src="/login.png" alt="Telegram 登录二维码">
  <p>二维码每 3 秒自动刷新。登录成功后可关闭此页面。</p>
  <script>
    setInterval(() => document.getElementById('qr').src = '/login.png?t=' + Date.now(), 3000);
  </script>
</body>
</html>
""".encode()


class LoginPreviewServer:
    def __init__(self, screenshot_path: str, host: str, port: int) -> None:
        self._screenshot_path = Path(screenshot_path)
        self._host = host
        self._port = port
        self._server: asyncio.Server | None = None

    async def __aenter__(self) -> LoginPreviewServer:  # noqa: PYI034
        self._server = await asyncio.start_server(self._handle, self._host, self._port)
        return self
    @property
    def port(self) -> int:
        if self._server is None or not self._server.sockets:
            return self._port
        return int(self._server.sockets[0].getsockname()[1])


    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=5)
            path = _request_path(request_line)
            await _discard_headers(reader)
            if path.startswith("/login.png"):
                if self._screenshot_path.exists():
                    await _respond(writer, "200 OK", "image/png", self._screenshot_path.read_bytes())
                else:
                    await _respond(writer, "503 Service Unavailable", "text/plain", b"QR not ready")
            else:
                await _respond(writer, "200 OK", "text/html; charset=utf-8", _LOGIN_PAGE)
        except (ConnectionError, TimeoutError, ValueError):
            if not writer.is_closing():
                await _respond(writer, "400 Bad Request", "text/plain", b"Bad request")
        finally:
            writer.close()
            await writer.wait_closed()


def _request_path(request_line: bytes) -> str:
    parts = request_line.decode("ascii", errors="strict").split()
    if len(parts) != 3 or parts[0] != "GET":
        raise ValueError("only GET is supported")
    return parts[1]


async def _discard_headers(reader: asyncio.StreamReader) -> None:
    while True:
        line = await asyncio.wait_for(reader.readline(), timeout=5)
        if line in {b"\r\n", b"\n", b""}:
            return


async def _respond(
    writer: asyncio.StreamWriter, status: str, content_type: str, body: bytes
) -> None:
    headers = (
        f"HTTP/1.1 {status}\r\n"
        f"Content-Type: {content_type}\r\n"
        "Cache-Control: no-store\r\n"
        "X-Content-Type-Options: nosniff\r\n"
        "Connection: close\r\n"
        f"Content-Length: {len(body)}\r\n\r\n"
    ).encode("ascii")
    writer.write(headers + body)
    await writer.drain()
