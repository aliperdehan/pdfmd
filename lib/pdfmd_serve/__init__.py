"""`pdfmd --serve` and `pdfmd --api` (entry 3do of the maintainer's notes): the JSON core of the web UI and the local server around it.

`core` holds the handlers (a request in, a status and JSON out; no sockets) and `shell` the HTTP server (127.0.0.1, a random port, a token).
Both are pure: the parts that belong to pdfmd.py (the main document, the metadata files, the atomic write) are passed in.
"""

from .core import API_VERSION, ApiError, Core, parse_body
from .shell import Server, run

__all__ = ["API_VERSION", "ApiError", "Core", "Server", "parse_body", "run"]
