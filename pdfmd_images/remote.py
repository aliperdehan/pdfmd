"""Remote images, fetched once and kept: a build then does not need the network again, an SVG badge can be converted
for LaTeX, and a machine with no network (a sandbox with no DNS) gets one warning instead of one failure per image."""

from __future__ import annotations

import hashlib
import time
import urllib.error
import urllib.request
from pathlib import Path

TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/svg+xml": ".svg",
         "application/pdf": ".pdf"}
SUFFIXES = (".png", ".jpg", ".jpeg", ".svg", ".pdf")
USER_AGENT = "pdfmd (+https://github.com/aliperdehan/pdfmd)"


def _cached(directory: Path, key: str) -> Path | None:
    for suffix in (*SUFFIXES, ".jpg"):
        candidate = directory / f"{key}{suffix}"
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    return None


def fetch(url: str, directory: Path, *, max_age_days: float = 7, timeout: float = 10,
          limit: int = 20 * 1024 * 1024) -> tuple[Path | None, str, bool]:
    """(the local file, "", False), or (None, why, True when the network itself is unreachable).

    A file fetched less than `max_age_days` ago is used as it is; an older one is fetched again, and kept if that
    fails. Only PNG, JPEG, SVG and PDF are kept (what a LaTeX build can use, SVG after conversion)."""
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    old = _cached(directory, key)
    if old is not None and time.time() - old.stat().st_mtime < max_age_days * 86400:
        return old, "", False
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/*,application/pdf"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            kind = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            data = response.read(limit + 1)
    except urllib.error.HTTPError as error:
        error.close()
        return old, f"{error.code} {error.reason}" if old is None else "", False
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        reason = str(getattr(error, "reason", error)) or type(error).__name__
        return old, reason if old is None else "", old is None
    if len(data) > limit:
        return old, f"larger than {limit // (1024 * 1024)} MB", False
    suffix = TYPES.get(kind)
    if suffix is None:
        path_suffix = Path(url.split("?", 1)[0]).suffix.lower()
        suffix = ".jpg" if path_suffix == ".jpeg" else (path_suffix if path_suffix in SUFFIXES else None)
    if suffix is None or not data:
        return old, f"not an image LaTeX can use ({kind or 'unknown type'})", False
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{key}{suffix}"
    partial = target.with_suffix(target.suffix + ".part")
    partial.write_bytes(data)
    partial.replace(target)
    return target, "", False
