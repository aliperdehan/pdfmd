"""The HTTP side of `pdfmd --serve`: 127.0.0.1 only, a random port, a random token, the page of `pdfmd_web` and the JSON of `core`.

The token travels once, in the URL that pdfmd prints (`?t=...`); the server answers it with an HttpOnly, SameSite=Strict cookie and a
redirect, so the page never handles it. A script may send `Authorization: Bearer TOKEN` instead. Every request is checked for the Host
(DNS rebinding), a write for the Origin; no CORS header is ever sent, so no other site can read an answer.
"""

from __future__ import annotations

import hmac
import json
import secrets
import sys
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

from .core import API_VERSION, ApiError, Core

COOKIE = "pdfmd_token"

# Written out: on Windows `mimetypes` reads the registry, where a program may have set .js to text/plain.
MIME = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".gif": "image/gif", ".ico": "image/x-icon", ".pdf": "application/pdf", ".txt": "text/plain; charset=utf-8",
    ".woff2": "font/woff2", ".woff": "font/woff", ".map": "application/json",
}

# The page and its own files only: a document's raw HTML (CommonMark allows it) cannot run a script that holds the token.
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; "
       "frame-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'none'; connect-src 'self'; worker-src 'self' blob:")


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, core: Core, web_root: Path, token: str):
        super().__init__(("127.0.0.1", 0), Handler)
        self.core, self.web_root, self.token = core, Path(web_root).resolve(), token

    @property
    def hosts(self) -> set:
        port = self.server_address[1]
        return {f"127.0.0.1:{port}", f"localhost:{port}"}


class Handler(BaseHTTPRequestHandler):
    server: Server
    protocol_version = "HTTP/1.1"
    server_version = "pdfmd"

    def log_message(self, format, *args):      # silent: stdout carries the one JSON line, stderr is for real trouble
        pass

    # ---- answers ----------------------------------------------------------------------------------------------------------------

    def send(self, status: int, data: bytes, mime: str, headers: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", CSP)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def send_json(self, status: int, answer: dict) -> None:
        self.send(status, json.dumps(answer, ensure_ascii=False).encode("utf-8"), MIME[".json"])

    def refuse(self, status: int, code: str, message: str) -> None:
        self.send_json(status, {"api": API_VERSION, "error": message, "code": code})

    # ---- checks -----------------------------------------------------------------------------------------------------------------

    def authorised(self) -> bool:
        given = self.headers.get("Authorization", "")
        if given.startswith("Bearer "):
            return hmac.compare_digest(given[7:].encode(), self.server.token.encode())
        jar = SimpleCookie()
        try:
            jar.load(self.headers.get("Cookie", ""))
        except Exception:
            return False
        morsel = jar.get(COOKIE)
        return morsel is not None and hmac.compare_digest(morsel.value.encode(), self.server.token.encode())

    def origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        return urlsplit(origin).netloc in self.server.hosts and urlsplit(origin).scheme == "http"

    # ---- verbs ------------------------------------------------------------------------------------------------------------------

    def handle_any(self) -> None:
        # the body is read before anything is answered: a refusal that left it in the socket would have the next request on this
        # keep-alive connection start in the middle of it
        self.body = b""
        length = self.headers.get("Content-Length")
        if length:
            try:
                self.body = self.rfile.read(int(length))
            except (ValueError, OSError):
                self.close_connection = True
                return self.refuse(400, "length", "a bad Content-Length")
        if self.headers.get("Host", "") not in self.server.hosts:
            return self.refuse(403, "host", "this server answers only to 127.0.0.1 and localhost")
        parts = urlsplit(self.path)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        if "t" in query and self.command in ("GET", "HEAD"):          # the printed URL: trade the token for the cookie
            if not hmac.compare_digest(query["t"].encode(), self.server.token.encode()):
                return self.refuse(403, "token", "wrong token")
            rest = urlencode([(k, v) for k, v in query.items() if k != "t"])
            return self.send(302, b"", MIME[".txt"], {
                "Location": parts.path + ("?" + rest if rest else ""),
                "Set-Cookie": f"{COOKIE}={self.server.token}; HttpOnly; SameSite=Strict; Path=/"})
        if not self.authorised():
            return self.send(403, b"Open the URL that `pdfmd --serve` printed: it carries the token.\n", MIME[".txt"])
        if not self.origin_ok():
            return self.refuse(403, "origin", "a request from another origin")
        if parts.path == "/api/raw" and self.command in ("GET", "HEAD"):       # a picture or a PDF as it is, not JSON
            try:
                data, mime = self.server.core.raw(query)
            except ApiError as error:
                return self.refuse(error.status, error.code, error.message)
            return self.send(200, data, mime)
        if parts.path.startswith("/api/") or parts.path == "/api":
            return self.api(parts)
        if self.command not in ("GET", "HEAD"):
            return self.refuse(405, "method", "the page's files are read only")
        self.static(parts.path)

    do_GET = do_HEAD = do_POST = do_PUT = do_DELETE = handle_any

    def api(self, parts) -> None:
        raw = self.body
        target = parts.path + ("?" + parts.query if parts.query else "")
        status, answer = self.server.core.handle("GET" if self.command == "HEAD" else self.command, target, raw)
        self.send_json(status, answer)

    def static(self, path: str) -> None:
        name = path.lstrip("/") or "index.html"
        root = self.server.web_root
        try:
            target = (root / name).resolve()
            target.relative_to(root)
        except (ValueError, OSError):
            return self.send(404, b"not found\n", MIME[".txt"])
        if not target.is_file() or target.suffix.lower() not in MIME:
            return self.send(404, b"not found\n", MIME[".txt"])
        self.send(200, target.read_bytes(), MIME[target.suffix.lower()])


def run(core: Core, web_root: Path, announce=None) -> int:
    """Serve until interrupted. `announce(info)` is called once with `{api, url, port, token, root}` (default: one JSON line on stdout)."""
    token = secrets.token_urlsafe(24)
    server = Server(core, web_root, token)
    port = server.server_address[1]
    info = {"api": API_VERSION, "url": f"http://127.0.0.1:{port}/?t={token}", "port": port, "token": token, "root": core.display(core.root)}
    if announce is None:
        print(json.dumps(info), flush=True)
    else:
        announce(info)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
