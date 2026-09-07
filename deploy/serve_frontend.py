"""Static frontend preview server with streaming proxy support.

This is a lightweight local-preview helper, not the production reverse proxy.
It deliberately forwards canonical ``/api/*`` requests without buffering the
response so Server-Sent Events work the same way as through nginx or Vite.
"""
from __future__ import annotations

import http.client
import http.server
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"
BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8005")
FRONTEND_PORT = int(os.environ.get("FRONTEND_PORT", "3002"))

_PROXY_PREFIXES = ("/api/", "/v1/", "/v2/", "/chat", "/detect")
_HOP_BY_HOP_HEADERS = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "transfer-encoding", "upgrade",
}


class KTPHandler(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def do_GET(self) -> None:
        if self._should_proxy():
            self._proxy_request()
            return
        requested = Path(self.translate_path(self.path))
        if not requested.is_file():
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:
        self._proxy_or_not_found()

    def do_PUT(self) -> None:
        self._proxy_or_not_found()

    def do_PATCH(self) -> None:
        self._proxy_or_not_found()

    def do_DELETE(self) -> None:
        self._proxy_or_not_found()

    def do_HEAD(self) -> None:
        self._proxy_or_not_found()

    def do_OPTIONS(self) -> None:
        if self._should_proxy():
            self._proxy_request()
            return
        self.send_response(204)
        self.end_headers()

    def _proxy_or_not_found(self) -> None:
        if self._should_proxy():
            self._proxy_request()
            return
        self.send_error(404)

    def _should_proxy(self) -> bool:
        path = urlsplit(self.path).path
        return path == "/health" or path.startswith(_PROXY_PREFIXES)

    def _proxy_request(self) -> None:
        connection: http.client.HTTPConnection | http.client.HTTPSConnection | None = None
        try:
            backend = urlsplit(BACKEND_URL)
            if backend.scheme not in {"http", "https"} or not backend.netloc:
                raise ValueError("BACKEND_URL must be an absolute http(s) URL")
            connection_type = http.client.HTTPSConnection if backend.scheme == "https" else http.client.HTTPConnection
            connection = connection_type(backend.hostname, backend.port, timeout=300)
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length) if content_length else None
            target = f"{backend.path.rstrip('/')}{self.path}"
            headers = {
                key: value for key, value in self.headers.items()
                if key.lower() not in _HOP_BY_HOP_HEADERS | {"host", "content-length"}
            }
            if body is not None:
                headers["Content-Length"] = str(len(body))
            connection.request(self.command, target, body=body, headers=headers)
            response = connection.getresponse()
            self.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                if key.lower() not in _HOP_BY_HOP_HEADERS:
                    self.send_header(key, value)
            if response.getheader("Content-Type", "").lower().startswith("text/event-stream"):
                self.send_header("Cache-Control", "no-cache")
                self.send_header("X-Accel-Buffering", "no")
            if response.getheader("Content-Length") is None:
                # The upstream may be chunked (notably SSE).  We remove the
                # hop-by-hop framing header, so close this downstream response
                # when the upstream stream finishes to preserve valid framing.
                self.close_connection = True
            self.end_headers()

            if self.command != "HEAD":
                # ``read1`` returns available bytes from the socket instead of
                # waiting for a complete response, which preserves SSE timing.
                while chunk := response.read1(64 * 1024):
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Backend unavailable", "detail": str(exc)}).encode())
        finally:
            if connection is not None:
                connection.close()

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, Idempotency-Key, Last-Event-ID")
        super().end_headers()

    def log_message(self, format, *args) -> None:
        pass


if __name__ == "__main__":
    with http.server.ThreadingHTTPServer(("0.0.0.0", FRONTEND_PORT), KTPHandler) as httpd:
        print(f"KTP frontend preview server running at http://0.0.0.0:{FRONTEND_PORT}")
        print(f"  Static files: {FRONTEND_DIR}")
        print(f"  Streaming API proxy: {BACKEND_URL}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")
