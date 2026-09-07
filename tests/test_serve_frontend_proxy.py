from __future__ import annotations

import http.client
import importlib.util
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def _load_preview_server():
    path = Path(__file__).resolve().parents[1] / "deploy" / "serve_frontend.py"
    spec = importlib.util.spec_from_file_location("ktp_frontend_preview", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preview_proxy_forwards_canonical_methods_and_streams_sse() -> None:
    class BackendHandler(BaseHTTPRequestHandler):
        received: list[tuple[str, str, bytes]] = []

        def _record(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            type(self).received.append((self.command, self.path, self.rfile.read(length)))

        def do_PATCH(self) -> None:
            self._record()
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def do_OPTIONS(self) -> None:
            self._record()
            self.send_response(204)
            self.end_headers()

        def do_GET(self) -> None:
            if self.path != "/api/product/v1/submissions/demo/events":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b"data: first\n\n")
            self.wfile.flush()
            time.sleep(0.15)
            self.wfile.write(b"data: second\n\n")
            self.wfile.flush()

        def log_message(self, *_args) -> None:
            pass

    backend = ThreadingHTTPServer(("127.0.0.1", 0), BackendHandler)
    backend_thread = threading.Thread(target=backend.serve_forever, daemon=True)
    backend_thread.start()
    preview_module = _load_preview_server()
    preview_module.BACKEND_URL = f"http://127.0.0.1:{backend.server_port}"
    preview = ThreadingHTTPServer(("127.0.0.1", 0), preview_module.KTPHandler)
    preview_thread = threading.Thread(target=preview.serve_forever, daemon=True)
    preview_thread.start()

    try:
        connection = http.client.HTTPConnection("127.0.0.1", preview.server_port, timeout=2)
        connection.request("PATCH", "/api/product/v1/datasets/demo", body=b'{"name":"x"}')
        assert connection.getresponse().status == 200
        connection.close()

        connection = http.client.HTTPConnection("127.0.0.1", preview.server_port, timeout=2)
        connection.request("OPTIONS", "/api/product/v1/datasets/demo")
        assert connection.getresponse().status == 204
        connection.close()

        connection = http.client.HTTPConnection("127.0.0.1", preview.server_port, timeout=2)
        connection.request("GET", "/api/product/v1/submissions/demo/events")
        started = time.monotonic()
        response = connection.getresponse()
        assert response.status == 200
        assert response.getheader("X-Accel-Buffering") == "no"
        assert response.read1().startswith(b"data: first")
        assert time.monotonic() - started < 0.1
        connection.close()

        assert ("PATCH", "/api/product/v1/datasets/demo", b'{"name":"x"}') in BackendHandler.received
        assert ("OPTIONS", "/api/product/v1/datasets/demo", b"") in BackendHandler.received
    finally:
        preview.shutdown()
        preview.server_close()
        backend.shutdown()
        backend.server_close()
