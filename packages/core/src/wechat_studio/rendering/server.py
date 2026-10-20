"""Serve one generated preview on localhost without external dependencies."""

from __future__ import annotations

import functools
import http.server
import webbrowser
from pathlib import Path


HOST = "127.0.0.1"
PREVIEW_FILE = "wechat_preview.html"


class PreviewRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()


def create_preview_server(
    build_directory: str | Path,
    *,
    port: int = 0,
) -> http.server.ThreadingHTTPServer:
    build = Path(build_directory).resolve()
    preview = build / PREVIEW_FILE
    if not preview.is_file():
        raise FileNotFoundError(f"Preview page is missing: {preview}")
    handler = functools.partial(PreviewRequestHandler, directory=str(build))
    server = http.server.ThreadingHTTPServer((HOST, port), handler)
    server.daemon_threads = True
    return server


def serve_preview(
    build_directory: str | Path,
    *,
    port: int = 0,
    open_browser: bool = True,
) -> str:
    server = create_preview_server(build_directory, port=port)
    actual_port = server.server_address[1]
    preview_url = f"http://{HOST}:{actual_port}/{PREVIEW_FILE}"
    if open_browser:
        webbrowser.open(preview_url, new=2)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return preview_url
