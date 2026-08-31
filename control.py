"""Tiny HTTP API so Discord/Telegram bots can toggle destinations."""

from __future__ import annotations

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from destinations import load, set_dest
from env_utils import env_secret

logger = logging.getLogger("rwf.control")


def _token() -> str:
    return env_secret("RWF_CONTROL_TOKEN", "RWF_TOKEN")


class DestHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        logger.info("%s - " + fmt, self.address_string(), *args)

    def _check_auth(self) -> bool:
        expected = _token()
        if not expected:
            return True
        got = (
            self.headers.get("X-RWF-Token")
            or self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        )
        return got == expected

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in {"/", "/health"}:
            self._send(200, {"ok": True, "service": "rwf-watcher"})
            return
        if path == "/destinations":
            if not self._check_auth():
                self._send(401, {"ok": False, "error": "unauthorized"})
                return
            self._send(200, {"ok": True, **load()})
            return
        self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path != "/destinations":
            self._send(404, {"ok": False, "error": "not found"})
            return
        if not self._check_auth():
            self._send(401, {"ok": False, "error": "unauthorized"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send(400, {"ok": False, "error": "invalid json"})
            return
        if not isinstance(data, dict):
            self._send(400, {"ok": False, "error": "invalid json"})
            return
        try:
            result = set_dest(
                str(data.get("platform") or ""),
                str(data.get("id") or ""),
                bool(data.get("enabled")),
            )
        except ValueError as e:
            self._send(400, {"ok": False, "error": str(e)})
            return
        self._send(200, {"ok": True, **result})


def start_control_server(host: str = "0.0.0.0", port: int | None = None) -> ThreadingHTTPServer:
    if port is None:
        raw = os.environ.get("PORT") or os.environ.get("RWF_CONTROL_PORT") or "8080"
        port = int(raw)
    httpd = ThreadingHTTPServer((host, port), DestHandler)
    t = threading.Thread(target=httpd.serve_forever, name="rwf-control", daemon=True)
    t.start()
    logger.info("control HTTP on %s:%s", host, port)
    return httpd
