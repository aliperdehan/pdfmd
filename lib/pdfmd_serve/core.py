"""The handlers of `pdfmd --serve` and `pdfmd --api` (entry 3do of the maintainer's notes): a request goes in (method, target, JSON body),
a status and a JSON object come out. No sockets here, so a test, a script (`pdfmd --api GET /api/project`) and the HTTP shell see the one thing.

The API is a public contract: every answer carries `api: 1`, an addition keeps the number, a change of meaning raises it. A list is never
an answer by itself (`{"api": 1, "items": [...]}`), so the number always has a place to be.

What belongs to pdfmd itself (which file a bare `pdfmd` builds and why, which metadata files it finds, how a file is written to disk) is passed
in by pdfmd.py as functions, so this package imports nothing from it.
"""

from __future__ import annotations

import contextlib
import html as html_lib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import parse_qs, unquote, urlencode, urlsplit

from .contain import contained

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
HIDDEN_COPY = re.compile(r"[^\s:]*\.pdfmd-live-")      # the name of the copy of an unsaved text (see document_file): a note names the document instead
POSITION = re.compile(r'data-pos="(\d+:\d+-\d+:\d+)"')      # beside every name that starts with a dot
# lines of Pandoc's that say nothing about the document: the option's newer name, and its own second position on a list item (3.1.3)
PANDOC_NOISE = ("Deprecated: --mathml", "Ignoring duplicate attribute data-pos=")


def _remove_preview_copy(path: Path, identity: os.stat_result) -> None:
    """Remove this render's file, leaving any replacement at its old name alone."""
    try:
        current = path.lstat()
    except FileNotFoundError:
        return
    if os.path.samestat(current, identity):
        path.unlink()


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra


def filesystem_error(error: OSError) -> ApiError:
    """Turn expected filesystem failures into the same API error contract for JSON and raw requests."""
    if isinstance(error, FileNotFoundError):
        return ApiError(404, "no_file", "the file no longer exists")
    if isinstance(error, PermissionError):
        return ApiError(403, "permission", "permission denied while accessing the project")
    return ApiError(500, "filesystem", "a filesystem operation failed")


def kind_of(name: str) -> str:
    return KINDS.get(os.path.splitext(name)[1].lower(), "other")


def strip_wrappers(html: str) -> str:
    """Pandoc's `sourcepos` wraps every word in a span of its own; the blocks keep their position, the word wrappers go. A wrapper is
    marked `data-wrapper="1"`; an older Pandoc (3.1.3) does not mark it, and there it is the span whose only attribute is its position."""
    pattern = re.compile(r'<span (?:data-wrapper="1"[^>]*|data-pos="[^"]*")>((?:(?!<span).)*?)</span>', re.S)
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
    `write_bytes(path, data)` is an atomic write; `filters(source, metadata)` is a context manager that yields the Pandoc arguments (the
    filters) pdfmd puts on the document in ``source``, a file holding the text being rendered: the very list a build writes (entry 3do);
    `places()` names the folders outside the project that those filters may open (pdfmd's cache; see contain.py)."""

    def __init__(self, root: Path, pick_main: Optional[Callable] = None, discover: Optional[Callable] = None,
                 write_bytes: Optional[Callable] = None, which: Callable = shutil.which, display: Optional[Callable] = None,
                 filters: Optional[Callable] = None, places: Optional[Callable] = None):
        self.root = Path(root).resolve()
        self.pick_main = pick_main or (lambda root: (None, "not asked"))
        self.discover = discover or (lambda root, main: [])
        self.write_bytes = write_bytes or self._write_bytes
        self.which = which
        self.display = display or str
        self.filters = filters or self._no_filters
        self.places = places or (lambda: [])
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
        except (ApiError, OSError) as error:
            if isinstance(error, OSError):
                error = filesystem_error(error)
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
        # the version a save sends back is the mtime from BEFORE the bytes were read: a file replaced while it is being read then has a
        # newer mtime than the answer, so the save is refused (409); taken after the read, it would name the new file and authorise
        # overwriting a text nobody saw
        version = path.stat().st_mtime_ns
        data = path.read_bytes()
        bom = data.startswith(b"\xef\xbb\xbf")
        try:
            text = data.decode("utf-8-sig" if bom else "utf-8")
        except UnicodeDecodeError:
            raise ApiError(415, "not_text", f"{name} is not UTF-8 text") from None
        crlf = "\r\n" in text
        return 200, {"path": name, "text": text.replace("\r\n", "\n"), "encoding": "utf-8-sig" if bom else "utf-8",
                     "lineEnding": "crlf" if crlf else "lf", "mtime": str(version)}

    def raw(self, query: dict) -> tuple[bytes, str]:
        """`GET /api/raw?path=NAME`: a picture or a PDF of the project, byte for byte, and its type. The one answer that is not JSON (the HTTP
        shell sends it); an error is an `ApiError` as everywhere."""
        try:
            path, name = self.resolve(query.get("path"))
            mime = RAW_TYPES.get(path.suffix.lower())
            if mime is None:
                raise ApiError(415, "not_viewable", f"{name} is not a picture or a PDF")
            if not path.is_file():
                raise ApiError(404, "no_file", f"{name} is not a file of this project")
            return path.read_bytes(), mime
        except OSError as error:
            raise filesystem_error(error) from error

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
        metadata files that pdfmd finds there and the filters pdfmd runs on its own syntax (`filters`: the list a build writes, so CSV tables,
        calc, callouts and the rest show as they do in a build). What the CommonMark reader cannot read stays as typed: citations (`[@key]`:
        pandoc's `commonmark_x` has `sourcepos` but no `citations`, the markdown reader has the other way round) and the markdown reader's
        table captions (`: caption`), until the core renders them by another route (entry 3do)."""
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
        metadata = []
        for item in self.discover(self.root, Path(main) if main else None):
            if item["role"] == "metadata" and not item.get("outside"):
                metadata.append(self.root / item["file"])
                command += ["--metadata-file", str(metadata[-1])]
        # what a build finds: a file named in the text (a CSV, a picture) is looked for beside the document and in the project's folder
        command += ["--resource-path", os.pathsep.join(dict.fromkeys([".", str(folder), str(self.root)]))]
        started = time.monotonic()
        try:
            with self.document_file(path if body.get("path") else None, folder, text) as document, contextlib.ExitStack() as stack:
                # the filters pdfmd runs on a document's own syntax come from pdfmd, the same list as a build's (not a copy of it here);
                # what pdfmd has to say about them (a filter it did not run, and why) is a warning of this render, not a line on the server's console
                said = io.StringIO()
                with contextlib.redirect_stderr(said):
                    arguments = stack.enter_context(self.filters(document, metadata))
                warning_text = said.getvalue()
                if not body.get("path") or document != path:
                    original = path.name if body.get("path") else "document.md"
                    warning_text = warning_text.replace(str(document), original).replace(document.name, original)
                notes = [HIDDEN_COPY.sub("", line) for line in warning_text.splitlines() if line.strip()]
                command += [str(item) for item in (arguments or [])]
                # the filters open only what is inside the project (and pdfmd's own places): a name in the text is not a way out of it
                extra, environment = stack.enter_context(contained(self.root, command, list(self.places())))
                done = subprocess.run(command + extra, input=text.encode("utf-8"), capture_output=True, cwd=str(folder),
                                      timeout=RENDER_TIMEOUT, env=environment)
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
        html = self.preview_images(html, folder)
        html = POSITION.sub(lambda m: f'data-pos="{source}@{m.group(1)}"', html)
        # pandoc 3.13 prefers --math-method, older ones do not know it; pandoc 3.1.3 gives a list item two positions and warns about its own second one
        warnings = notes + [line for line in errors.splitlines() if not any(noise in line for noise in PANDOC_NOISE)]
        return 200, {"html": html, "seconds": seconds, "engine": "pandoc", "warnings": warnings}

    def preview_images(self, markup: str, folder: Path) -> str:
        """Point local image sources at the contained project-file endpoint, preserving other markup."""
        attributes = re.compile(r"(\s+)([^\s=/>]+)(\s*=\s*)(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))", re.S)

        def image(tag: str) -> str:
            def attribute(match: re.Match) -> str:
                if match.group(2).lower() != "src":
                    return match.group(0)
                original = next(value for value in match.groups()[3:] if value is not None)
                try:
                    url = urlsplit(html_lib.unescape(original))
                    if url.scheme or url.netloc or not url.path or url.path.startswith("/"):
                        return match.group(0)
                    target = (folder / unquote(url.path)).resolve()
                    name = target.relative_to(self.root).as_posix()
                    self.resolve(name)  # also excludes the repository's private .git directory
                    if not target.is_file() and folder != self.root:
                        try:
                            root_target = (self.root / unquote(url.path)).resolve()
                            root_name = root_target.relative_to(self.root).as_posix()
                            self.resolve(root_name)
                            if root_target.is_file():
                                target, name = root_target, root_name
                        except (ValueError, OSError, ApiError):
                            pass
                    if target.suffix.lower() not in RAW_TYPES:
                        return match.group(0)
                except (ValueError, OSError, ApiError):
                    return match.group(0)
                query = (url.query + "&" if url.query else "") + urlencode({"path": name})
                rewritten = "/api/raw?" + query + ("#" + url.fragment if url.fragment else "")
                return "".join(match.group(i) for i in (1, 2, 3)) + '"' + html_lib.escape(rewritten, quote=True) + '"'

            return attributes.sub(attribute, tag)

        offsets = [0]
        for line in markup.splitlines(keepends=True):
            offsets.append(offsets[-1] + len(line))

        class Images(HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=False)
                self.edits = []

            def handle_starttag(self, tag, attrs):
                if tag == "img":
                    raw = self.get_starttag_text()
                    line, column = self.getpos()
                    start = offsets[line - 1] + column
                    self.edits.append((start, start + len(raw), image(raw)))

            def handle_startendtag(self, tag, attrs):
                self.handle_starttag(tag, attrs)

        parser = Images()
        parser.feed(markup)
        parser.close()
        pieces, previous = [], 0
        for start, end, replacement in parser.edits:
            pieces.extend((markup[previous:start], replacement))
            previous = end
        return "".join([*pieces, markup[previous:]])

    # ---- helpers ----------------------------------------------------------------------------------------------------------------

    @staticmethod
    @contextlib.contextmanager
    def _no_filters(source: Path, metadata: list):
        yield []

    @contextlib.contextmanager
    def document_file(self, path: Optional[Path], folder: Path, text: str):
        """A file that holds ``text``, for what reads a document's own file to find out what it needs (pdfmd's filters and its settings
        read the document and the folders above it). The file itself when it already says this; otherwise a hidden copy beside it, gone
        when the render is done: the folder's own settings only apply to a file that sits in the folder."""
        if path is not None and path.is_file():
            try:
                if path.read_bytes().decode("utf-8-sig").replace("\r\n", "\n") == text.replace("\r\n", "\n"):
                    yield path
                    return
            except (OSError, UnicodeDecodeError):
                pass
        copy = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=folder, prefix=".pdfmd-live-",
                                             suffix=f"-{path.name if path is not None else 'document.md'}", delete=False) as handle:
                identity = os.fstat(handle.fileno())
                copy = Path(handle.name)
                handle.write(text)
        except OSError:
            if copy is not None:
                _remove_preview_copy(copy, identity)
            with tempfile.TemporaryDirectory(prefix="pdfmd-live-") as scratch:      # a folder that cannot be written to: its settings are lost
                copy = Path(scratch) / (path.name if path is not None else "document.md")
                copy.write_text(text, encoding="utf-8")
                yield copy
            return
        try:
            yield copy
        finally:
            _remove_preview_copy(copy, identity)

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
