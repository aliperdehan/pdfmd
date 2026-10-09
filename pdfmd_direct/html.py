"""`.html` straight to a PDF: WeasyPrint first (quiet, small, no browser), a browser when the page runs scripts or
WeasyPrint cannot draw it, then the other HTML engines and LibreOffice."""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable

HTML_ENGINES = ("weasyprint", "wkhtmltopdf", "prince", "pagedjs-cli")
PATH_NAMES = {
    "chrome": ("google-chrome", "google-chrome-stable", "chrome"),
    "chromium": ("chromium", "chromium-browser"),
    "edge": ("microsoft-edge", "microsoft-edge-stable", "msedge"),
    "brave": ("brave-browser", "brave"),
}
MAC_APPS = {
    "chrome": "Google Chrome.app/Contents/MacOS/Google Chrome",
    "chromium": "Chromium.app/Contents/MacOS/Chromium",
    "edge": "Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "brave": "Brave Browser.app/Contents/MacOS/Brave Browser",
}
WINDOWS_APPS = {
    "chrome": r"Google\Chrome\Application\chrome.exe",
    "chromium": r"Chromium\Application\chrome.exe",
    "edge": r"Microsoft\Edge\Application\msedge.exe",
    "brave": r"BraveSoftware\Brave-Browser\Application\brave.exe",
}
BROWSER_NAMES = tuple(PATH_NAMES)                      # in the order they are tried
REQUEST_WORDS = {"weasy": "weasyprint", "7": "weasyprint", "wkhtml": "wkhtmltopdf", "8": "wkhtmltopdf",
                 "pagedjs": "pagedjs-cli", "9": "pagedjs-cli", "10": "prince", "libreoffice": "soffice",
                 "office": "soffice", "14": "soffice", "google-chrome": "chrome"}
SCRIPT_RE = re.compile(r"<script\b(?![^>]*\btype\s*=\s*[\"']?(?:application/(?:ld\+)?json|text/template|importmap))",
                       re.IGNORECASE)


def has_scripts(text: str) -> bool:
    """True when the page runs code (a `<script>` that is not just data); WeasyPrint does not run it."""
    return bool(SCRIPT_RE.search(text))


def find_browser(name: str, which: Callable[[str], str | None] = shutil.which) -> str | None:
    """The executable of browser `name` (chrome, chromium, edge, brave), on PATH or where its installer puts it."""
    override = os.environ.get("PDFMD_BROWSER")
    if override and name == "chrome" and Path(override).is_file():
        return override
    for candidate in PATH_NAMES.get(name, ()):
        found = which(candidate)
        if found:
            return found
    if sys.platform == "darwin":
        for root in (Path("/Applications"), Path.home() / "Applications"):
            candidate = root / MAC_APPS[name]
            if candidate.is_file():
                return str(candidate)
    elif sys.platform.startswith("win"):
        for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.environ.get(variable)
            if base and (Path(base) / WINDOWS_APPS[name]).is_file():
                return str(Path(base) / WINDOWS_APPS[name])
    return None


def accepts_request(request: str | None) -> bool:
    """False when the user asked for an engine that is not an HTML one (`-e lualatex`): they want the Pandoc route."""
    if not request:
        return True
    word = request.casefold()
    word = REQUEST_WORDS.get(word, word)
    return word in (*HTML_ENGINES, "soffice", "html", "browser", *BROWSER_NAMES)


def attempts(text: str, request: str | None, which: Callable[[str], str | None] = shutil.which,
             soffice: Callable[[], str | None] = lambda: None) -> list[tuple[str, str]]:
    """(name, executable) of the engines to try, in order. A page with scripts goes to a browser first; any other
    page to WeasyPrint first. `request` narrows the list to one engine (or to the browsers, or the HTML engines)."""
    found: dict[str, str] = {}
    for name in HTML_ENGINES:
        path = which(name)
        if path:
            found[name] = path
    for name in BROWSER_NAMES:
        path = find_browser(name, which)
        if path:
            found[name] = path
    path = soffice()
    if path:
        found["soffice"] = path
    browsers = [name for name in BROWSER_NAMES if name in found]
    engines = [name for name in HTML_ENGINES if name in found]
    if request:
        word = request.casefold()
        word = REQUEST_WORDS.get(word, word)
        if word == "browser":
            order = browsers
        elif word == "html":
            order = [*engines, *browsers]
        else:
            order = [word] if word in found else []
    elif has_scripts(text):
        order = [*browsers, *engines, *(["soffice"] if "soffice" in found else [])]
    else:
        order = [*(["weasyprint"] if "weasyprint" in found else []), *browsers,
                 *[name for name in engines if name != "weasyprint"], *(["soffice"] if "soffice" in found else [])]
    return [(name, found[name]) for name in order]


def _engine_command(name: str, executable: str, source: Path, produced: Path, profile: Path) -> list[str]:
    if name == "weasyprint":
        return [executable, str(source), str(produced)]
    if name == "wkhtmltopdf":
        return [executable, "--enable-local-file-access", str(source), str(produced)]
    if name == "prince":
        return [executable, str(source), "-o", str(produced)]
    if name == "pagedjs-cli":
        return [executable, str(source), "-o", str(produced)]
    command = [executable, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--hide-scrollbars",
               f"--user-data-dir={profile}", "--virtual-time-budget=10000", "--run-all-compositor-stages-before-draw",
               f"--print-to-pdf={produced}"]
    if hasattr(os, "geteuid") and os.geteuid() == 0:        # a container: Chrome refuses to start as root otherwise
        command.append("--no-sandbox")
    return command + [source.resolve().as_uri()]


def _run_browser(command: list[str], produced: Path, cwd: Path, timeout: int) -> tuple[bool, str]:
    """Run a browser that prints a page to `produced`. Some builds write the file and then stay running, so the PDF
    is waited for (its size steady for a moment) and the browser is stopped once it is there."""
    with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as errors:
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=errors, cwd=cwd,
                                   start_new_session=hasattr(os, "setsid"))
        deadline = time.monotonic() + timeout
        last_size, steady, timed_out = -1, 0, True
        try:
            while time.monotonic() < deadline:
                size = produced.stat().st_size if produced.is_file() else 0
                if process.poll() is not None:
                    timed_out = False
                    break
                steady = steady + 1 if size and size == last_size else 0
                last_size = size
                if steady >= 3:                                   # unchanged for about 0.75 s
                    timed_out = False
                    break
                time.sleep(0.25)
        finally:
            if process.poll() is None:
                try:
                    if hasattr(os, "killpg"):
                        os.killpg(process.pid, signal.SIGTERM)
                    else:
                        process.terminate()
                    process.wait(timeout=5)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    process.kill()
        if produced.is_file() and produced.stat().st_size > 0:
            return True, ""
        if timed_out:
            return False, f"the browser took more than {timeout} s"
        errors.seek(0)
        return False, (errors.read().strip().splitlines() or ["the browser wrote no PDF"])[-1]


def render_html(source: Path, output: Path, order: list[tuple[str, str]], *,
                soffice_convert: Callable[[Path, Path], tuple[bool, str]] | None = None,
                on_failure: Callable[[str, str, list[str]], None] = lambda name, reason, remaining: None,
                log: Callable[[list, Path], None] = lambda command, cwd: None,
                timeout: int = 180) -> tuple[bool, str, str | None]:
    """Try the engines of `order` until one writes a PDF: (ok, last reason, the engine that did it)."""
    reason = "no HTML engine or browser was found (install WeasyPrint: pip install weasyprint, or Chrome/Edge)"
    for position, (name, executable) in enumerate(order):
        remaining = [other for other, _ in order[position + 1:]]
        scratch = Path(tempfile.mkdtemp(prefix="pdfmd-html-"))
        try:
            produced = scratch / "out.pdf"
            if name == "soffice":
                if soffice_convert is None:
                    continue
                ok, reason = soffice_convert(source, produced)
            else:
                command = _engine_command(name, executable, source, produced, scratch / "profile")
                log(command, source.parent)
                if name in BROWSER_NAMES:
                    ok, reason = _run_browser(command, produced, source.parent, timeout)
                else:
                    try:
                        done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                              cwd=source.parent, timeout=timeout)
                        ok = done.returncode == 0 and produced.is_file() and produced.stat().st_size > 0
                        reason = "" if ok else ((done.stderr.strip() or done.stdout.strip()).splitlines() or
                                                [f"{name} wrote no PDF"])[-1]
                    except subprocess.TimeoutExpired:
                        ok, reason = False, f"{name} took more than {timeout} s"
            if ok and produced.is_file():
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(produced, output)
                return True, "", name
            on_failure(name, reason, remaining)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
    return False, reason, None
