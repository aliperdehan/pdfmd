"""One download of a pinned file, asked again when the mirror that answered was bad.

`mirrors.ctan.org` is a redirector: every request is sent on to some CTAN mirror, and a mirror with an incomplete certificate
chain, a dead connection or a corrupt copy fails a download that the next mirror would serve. For a URL on that host (only that
host) a TLS/certificate, connection or time-out error, or a file that fails its checksum, is retried: the setting
`download-retries` is the number of EXTRA tries after the first (default 2; 0: no retry; a negative number: no limit, Ctrl-C
stops it). Each failed try logs one WARN naming the mirror it reached and the error; the last failure is raised as it is.
"""

from __future__ import annotations

import http.client
import ssl
import socket
import urllib.error
import urllib.request
from typing import Callable
from urllib.parse import urlsplit

REDIRECTOR = "mirrors.ctan.org"
DEFAULT_RETRIES = 2


class ChecksumMismatch(OSError):
    """The download arrived whole but is not the pinned file."""


# TLS and certificate errors, a refused or reset connection, a time-out, a body cut short. An HTTP status (404, 500) is not here.
RETRYABLE = (ssl.SSLError, ssl.CertificateError, ConnectionError, TimeoutError, http.client.IncompleteRead, ChecksumMismatch)


def retries_setting(core) -> int:
    """`download-retries` from the setup's options: extra tries after the first; negative (or infinite) = -1, no limit."""
    value = core.option_flag_number(core.config_options().get("download-retries"))
    if value is None:
        return DEFAULT_RETRIES
    return -1 if value < 0 or value == float("inf") else int(value)


def _retryable(error: BaseException) -> bool:
    if isinstance(error, urllib.error.HTTPError):
        return False
    if isinstance(error, urllib.error.URLError):          # urlopen wraps the TLS, connection and time-out errors of the socket
        error = error.reason
    return (isinstance(error, RETRYABLE)
            or isinstance(error, socket.gaierror) and error.errno == socket.EAI_AGAIN)


class _Recorder(urllib.request.HTTPRedirectHandler):
    """Remembers the last place the redirector sent the request to, so that a failure can name the mirror."""
    last = ""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.last = newurl
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url: str, opener: Callable, log: Callable[[str], None], retries: int = DEFAULT_RETRIES, agent: str = "pdfmd-fonts",
          timeout: int = 300, check: Callable[[bytes], None] | None = None) -> bytes:
    """The bytes at `url`; `check(data)` raises `ChecksumMismatch` for a wrong file. See the module docstring for the retries."""
    again = urlsplit(url).hostname == REDIRECTOR
    tries = 0
    while True:
        recorder = _Recorder()
        mirror = ""
        try:
            request = urllib.request.Request(url, headers={"User-Agent": agent})
            if opener is urllib.request.urlopen:           # the real one: its redirects are watched; a given opener is used as it is
                opener_call = urllib.request.build_opener(recorder).open
            else:
                opener_call = opener
            with opener_call(request, timeout=timeout) as response:
                final = response.geturl() if callable(getattr(response, "geturl", None)) else ""
                mirror = urlsplit(final).hostname or "" if isinstance(final, str) else ""
                data = response.read()
            if check is not None:
                check(data)
            return data
        except Exception as error:
            if not again or not _retryable(error) or (retries >= 0 and tries >= retries):
                raise
            tries += 1
            host = mirror or urlsplit(recorder.last).hostname or "an unknown mirror"
            more = "" if retries < 0 else f" of {retries}"
            log(f"WARN  {REDIRECTOR} sent the download to {host}, which failed: {error}; asking again (retry {tries}{more})")
