"""Simple HTTP server for KTP frontend with API proxy to backend."""
from __future__ import annotations

import http.server
import os
import urllib.request
import urllib.error
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"
BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8005")
FRONTEND_PORT = int(os.environ.get("FRONTEND_PORT", "3002"))


class KTPHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def do_GET(self):
        if self.path.startswith("/v2/") or self.path.startswith("/health") or self.path.startswith("/chat") or self.path.startswith("/detect"):
            self._proxy_request()
            return
        if self.path.startswith("/v1/"):
            self._proxy_request()
            return
        try:
            super().do_GET()
        except (FileNotFoundError, urllib.error.URLError):
            self.path = "/index.html"
            super().do_GET()

    def do_POST(self):
        if self.path.startswith("/v2/") or self.path.startswith("/v1/"):
            self._proxy_request()
            return
        self.send_error(404)

    def do_PUT(self):
        if self.path.startswith("/v2/"):
            self._proxy_request()
            return
        self.send_error(404)

    def do_DELETE(self):
        if self.path.startswith("/v2/"):
            self._proxy_request()
            return
        self.send_error(404)

    def _proxy_request(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else None
            req = urllib.request.Request(
                f"{BACKEND_URL}{self.path}",
                data=body,
                method=self.command,
                headers={k: v for k, v in self.headers.items() if k.lower() not in ("host", "content-length")},
            )
            if body:
                req.add_header("Content-Length", str(len(body)))
            with urllib.request.urlopen(req, timeout=300) as resp:
                self.send_response(resp.status)
                for key, val in resp.getheaders():
                    if key.lower() not in ("transfer-encoding", "connection"):
                        self.send_header(key, val)
                self.end_headers()
                data = resp.read()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(f'{{"error": "Backend unavailable: {e}"}}'.encode())

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    with http.server.HTTPServer(("0.0.0.0", FRONTEND_PORT), KTPHandler) as httpd:
        print(f"KTP frontend server running at http://0.0.0.0:{FRONTEND_PORT}")
        print(f"  Static files: {FRONTEND_DIR}")
        print(f"  API proxy: {BACKEND_URL}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")
