"""The handlers of `pdfmd --serve` and `pdfmd --api` (entry 3do of the maintainer's notes): a request goes in (method, target, JSON body),
a status and a JSON object come out. No sockets here, so a test, a script (`pdfmd --api GET /api/project`) and the HTTP shell see the one thing.

The API is a public contract: every answer carries `api: 1`, an addition keeps the number, a change of meaning raises it. A list is never
an answer by itself (`{"api": 1, "items": [...]}`), so the number always has a place to be.

What belongs to pdfmd itself (which file a bare `pdfmd` builds and why, which metadata files it finds, how a file is written to disk) is passed
in by pdfmd.py as functions, so this package imports nothing from it.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import parse_qs, urlsplit

API_VERSION = 1

# Seconds one render may take. A live render is pandoc on a few pages (0.05 s measured); the limit only keeps a hung process from holding a
# request for good, and no sensible knob exists for it (entry 3do records it as a constant on purpose).
RENDER_TIMEOUT = 60

KINDS = {
    ".md": "markdown", ".markdown": "markdown", ".bib": "bib", ".yaml": "metadata", ".yml": "metadata", ".csl": "csl", ".csv": "csv",
    ".typ": "typst", ".tex": "tex", ".html": "html", ".htm": "html", ".css": "css", ".lua": "lua", ".pdf": "pdf", ".txt": "text",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image", ".svg": "image", ".webp": "image",
}
# What /api/raw serves as it is: what the page's viewer can show (a text file goes through /api/file, which keeps its line endings and its mtime).
RAW_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".svg": "image/svg+xml",
             ".webp": "image/webp", ".pdf": "application/pdf"}
SKIPPED_DIRS = {"__pycache__", "node_modules"}
# a position from pandoc reading standard input has no file name (`5:1-6:1`); the page's source mirror wants `name@5:1-6:1`
POSITION = re.compile(r'data-pos="(\d+:\d+-\d+:\d+)"')      # beside every name that starts with a dot


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra


def kind_of(name: str) -> str:
    return KINDS.get(os.path.splitext(name)[1].lower(), "other")


def strip_wrappers(html: str) -> str:
    """Pandoc's `sourcepos` wraps every word in a span of its own; the blocks keep their position, the word wrappers go."""
    pattern = re.compile(r'<span data-wrapper="1"[^>]*>((?:(?!<span).)*?)</span>', re.S)
    while True:
        html, n = pattern.subn(r"\1", html)
        if not n:
            return html


def headings(text: str) -> list[dict]:
    """ATX headings of a Markdown text, outside the front matter and the code fences: `[{level, title, line}]`."""
    items, fence, lines = [], None, text.split("\n")
    start = 0
    if lines and lines[0].rstrip() == "---":
        for i in range(1, len(lines)):
            if lines[i].rstrip() in ("---", "..."):
                start = i + 1
                break
    for i in range(start, len(lines)):
        line = lines[i]
        opener = re.match(r"\s{0,3}(`{3,}|~{3,})", line)
        if opener:
            mark = opener.group(1)[0]
            if fence is None:
                fence = mark
            elif fence == mark:
                fence = None
            continue
        if fence is None:
            m = re.match(r"\s{0,3}(#{1,6})\s+(.*?)(?:\s+#+)?\s*$", line)
            if m:
                items.append({"level": len(m.group(1)), "title": m.group(2).strip(), "line": i + 1})
    return items


class Core:
    """One project folder. `pick_main(root)` -> (relative path or None, why); `discover(root, main)` -> [{"role", "file"}];
    `write_bytes(path, data)` is an atomic write; `filters()` is a context manager that yields the Lua filters (paths) the live view runs
    (pdfmd's own: the CSV tables)."""

    def __init__(self, root: Path, pick_main: Optional[Callable] = None, discover: Optional[Callable] = None,
                 write_bytes: Optional[Callable] = None, which: Callable = shutil.which, display: Optional[Callable] = None,
                 filters: Optional[Callable] = None):
        self.root = Path(root).resolve()
        self.pick_main = pick_main or (lambda root: (None, "not asked"))
        self.discover = discover or (lambda root, main: [])
        self.write_bytes = write_bytes or self._write_bytes
        self.which = which
        self.display = display or str
        self.filters = filters or contextlib.nullcontext
        self.lock = threading.Lock()

    # ---- dispatch ---------------------------------------------------------------------------------------------------------------

    def handle(self, method: str, target: str, body: object = None) -> tuple[int, dict]:
        parts = urlsplit(target)
        query = {key: values[-1] for key, values in parse_qs(parts.query, keep_blank_values=True).items()}
        route = (method.upper(), parts.path.rstrip("/") or "/")
        try:
            handler = ROUTES.get(route)
            if handler is None:
                known = {m for (m, p) in ROUTES if p == route[1]}
                if known:
                    raise ApiError(405, "method", f"{route[1]} answers {', '.join(sorted(known))}, not {route[0]}")
                raise ApiError(404, "no_route", f"no such endpoint: {route[0]} {route[1]}")
            if isinstance(body, (bytes, bytearray)):
                body = parse_body(bytes(body))
            if body is not None and not isinstance(body, dict):
                raise ApiError(400, "body", "the body must be a JSON object")
            status, answer = handler(self, query, body or {})
        except ApiError as error:
            status, answer = error.status, {"error": error.message, "code": error.code, **error.extra}
        return status, {"api": API_VERSION, **answer}

    # ---- paths ------------------------------------------------------------------------------------------------------------------

    def resolve(self, name: object) -> tuple[Path, str]:
        """A path below the project folder: resolved on both sides (a symlink out of the folder, `..` and an absolute name are refused)."""
        if not isinstance(name, str) or not name or "\0" in name:
            raise ApiError(400, "path", "a `path` (a file of the project) is needed")
        target = (self.root / name).resolve()
        try:
            relative = target.relative_to(self.root)
        except ValueError:
            raise ApiError(403, "outside", "that path is outside the project folder") from None
        if ".git" in relative.parts:
            raise ApiError(403, "outside", "the repository's own folder is not served")
        return target, relative.as_posix()

    def tree(self) -> list[dict]:
        found = []

        def walk(folder: Path, prefix: str) -> None:
            try:
                entries = sorted(os.scandir(folder), key=lambda e: e.name.casefold())
            except OSError:
                return
            for entry in entries:
                if entry.name.startswith(".") or entry.name in SKIPPED_DIRS:
                    continue
                if entry.is_dir(follow_symlinks=False):
                    walk(Path(entry.path), prefix + entry.name + "/")
                elif entry.is_file():
                    found.append({"name": prefix + entry.name, "kind": kind_of(entry.name)})

        walk(self.root, "")
        return found

    # ---- endpoints --------------------------------------------------------------------------------------------------------------

    def project(self, query: dict, body: dict) -> tuple[int, dict]:
        main, why = self.pick_main(self.root)
        main = Path(main) if main else None
        try:
            main_name = main.resolve().relative_to(self.root).as_posix() if main else None
        except ValueError:
            main_name = None
        return 200, {"name": self.root.name, "root": self.display(self.root), "main": main_name, "mainWhy": why,
                     "discovered": self.discover(self.root, main), "tree": self.tree()}

    def read_file(self, query: dict, body: dict) -> tuple[int, dict]:
        path, name = self.resolve(query.get("path"))
        if not path.is_file():
            raise ApiError(404, "no_file", f"{name} is not a file of this project")
        data = path.read_bytes()
        bom = data.startswith(b"\xef\xbb\xbf")
        try:
            text = data.decode("utf-8-sig" if bom else "utf-8")
        except UnicodeDecodeError:
            raise ApiError(415, "not_text", f"{name} is not UTF-8 text") from None
        crlf = "\r\n" in text
        return 200, {"path": name, "text": text.replace("\r\n", "\n"), "encoding": "utf-8-sig" if bom else "utf-8",
                     "lineEnding": "crlf" if crlf else "lf", "mtime": str(path.stat().st_mtime_ns)}

    def raw(self, query: dict) -> tuple[bytes, str]:
        """`GET /api/raw?path=NAME`: a picture or a PDF of the project, byte for byte, and its type. The one answer that is not JSON (the HTTP
        shell sends it); an error is an `ApiError` as everywhere."""
        path, name = self.resolve(query.get("path"))
        mime = RAW_TYPES.get(path.suffix.lower())
        if mime is None:
            raise ApiError(415, "not_viewable", f"{name} is not a picture or a PDF")
        if not path.is_file():
            raise ApiError(404, "no_file", f"{name} is not a file of this project")
        return path.read_bytes(), mime

    def put_file(self, query: dict, body: dict) -> tuple[int, dict]:
        path, name = self.resolve(body.get("path"))
        text = body.get("text")
        if not isinstance(text, str):
            raise ApiError(400, "text", "`text` (the whole file) is needed")
        with self.lock:
            bom, crlf = False, False
            if path.exists():
                if not path.is_file():
                    raise ApiError(400, "path", f"{name} is not a file")
                current = str(path.stat().st_mtime_ns)
                if body.get("mtime") != current:
                    raise ApiError(409, "conflict", f"{name} changed on disk since it was read (or no `mtime` was sent): read it again",
                                   mtime=current)
                old = path.read_bytes()
                bom, crlf = old.startswith(b"\xef\xbb\xbf"), b"\r\n" in old
            else:
                raise ApiError(404, "no_file", f"{name} does not exist: create it with POST /api/file")
            text = text.replace("\r\n", "\n")
            data = (text.replace("\n", "\r\n") if crlf else text).encode("utf-8")
            self.write_bytes(path, (b"\xef\xbb\xbf" if bom else b"") + data)
            return 200, {"path": name, "mtime": str(path.stat().st_mtime_ns)}

    def create_file(self, query: dict, body: dict) -> tuple[int, dict]:
        path, name = self.resolve(body.get("path"))
        text = body.get("text", "")
        if not isinstance(text, str):
            raise ApiError(400, "text", "`text` must be a string")
        with self.lock:
            if path.exists():
                raise ApiError(409, "exists", f"{name} already exists (a new file never overwrites)")
            path.parent.mkdir(parents=True, exist_ok=True)
            self.write_bytes(path, text.replace("\r\n", "\n").encode("utf-8"))
            return 201, {"path": name, "mtime": str(path.stat().st_mtime_ns)}

    def outline(self, query: dict, body: dict) -> tuple[int, dict]:
        path, name = self.resolve(query.get("path"))
        if kind_of(name) != "markdown":
            return 200, {"path": name, "items": []}
        if not path.is_file():
            raise ApiError(404, "no_file", f"{name} is not a file of this project")
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            raise ApiError(415, "not_text", f"{name} is not UTF-8 text") from None
        return 200, {"path": name, "items": headings(text.replace("\r\n", "\n"))}

    def render(self, query: dict, body: dict) -> tuple[int, dict]:
        """The live view: pandoc (CommonMark with source positions) on the text as it is now, in the folder of the file, with the
        metadata files that pdfmd finds there. Citations are NOT resolved: pandoc's `commonmark_x` has `sourcepos` but no `citations`
        (the markdown reader has the other way round), so `[@key]` stays as typed until the core renders it by another route (entry 3do)."""
        text = body.get("text")
        if not isinstance(text, str):
            raise ApiError(400, "text", "`text` (what to render) is needed")
        pandoc = self.which("pandoc")
        if not pandoc:
            raise ApiError(503, "no_pandoc", "the live view needs Pandoc, and it is not installed (pdfmd --check-dependencies)")
        folder, source = self.root, ""
        if body.get("path"):
            path, source = self.resolve(body.get("path"))
            folder = path.parent if path.parent.is_dir() else self.root
        command = [pandoc, "-f", "commonmark_x+sourcepos+tex_math_dollars", "-t", "html", "--mathml", "--wrap=none"]
        main, _ = self.pick_main(self.root)
        for item in self.discover(self.root, Path(main) if main else None):
            if item["role"] == "metadata" and not item.get("outside"):
                command += ["--metadata-file", str(self.root / item["file"])]
        # what a build finds: a file named in the text (a CSV, a picture) is looked for beside the document and in the project's folder
        command += ["--resource-path", os.pathsep.join(dict.fromkeys([".", str(folder), str(self.root)]))]
        started = time.monotonic()
        try:
            with self.filters() as lua:
                for path in (lua or []):
                    command += ["--lua-filter", str(path)]
                done = subprocess.run(command, input=text.encode("utf-8"), capture_output=True, cwd=str(folder), timeout=RENDER_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise ApiError(504, "timeout", f"pandoc did not answer in {RENDER_TIMEOUT} s") from None
        except OSError as error:
            raise ApiError(503, "no_pandoc", f"pandoc could not be started: {error}") from None
        seconds = round(time.monotonic() - started, 3)
        errors = done.stderr.decode("utf-8", "replace").strip()
        if done.returncode != 0:
            raise ApiError(422, "render_failed", errors.splitlines()[0] if errors else f"pandoc exited with {done.returncode}",
                           log=errors, seconds=seconds)
        html = strip_wrappers(done.stdout.decode("utf-8", "replace"))
        html = POSITION.sub(lambda m: f'data-pos="{source}@{m.group(1)}"', html)
        warnings = [line for line in errors.splitlines() if "Deprecated: --mathml" not in line]   # pandoc 3.13 prefers --math-method; older ones do not know it
        return 200, {"html": html, "seconds": seconds, "engine": "pandoc", "warnings": warnings}

    # ---- helpers ----------------------------------------------------------------------------------------------------------------

    @staticmethod
    def _write_bytes(path: Path, data: bytes) -> None:
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            with open(temporary, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()


ROUTES: dict = {
    ("GET", "/api/project"): Core.project,
    ("GET", "/api/file"): Core.read_file,
    ("PUT", "/api/file"): Core.put_file,
    ("POST", "/api/file"): Core.create_file,
    ("GET", "/api/outline"): Core.outline,
    ("POST", "/api/render"): Core.render,
}


def parse_body(raw: bytes) -> object:
    """The JSON body of a request: None for no body, ApiError for text that is not JSON."""
    if not raw.strip():
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ApiError(400, "json", "the body is not JSON") from None
