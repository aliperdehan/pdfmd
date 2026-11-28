"""Read the running copy's install receipts and check for newer PyPI releases on request."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path, PureWindowsPath

from pdfmd_base import core
from pdfmd_cache import write_cached


DISTRIBUTION = "pdfmd-cli"
UPGRADE_COMMANDS = {
    "pip": f"python -m pip install --upgrade {DISTRIBUTION}",
    "pipx": f"pipx upgrade {DISTRIBUTION}",
    "Homebrew": "brew upgrade pdfmd",
    "Scoop": "scoop update pdfmd",
}
VERSION_CACHE_HOURS = 24


def read_receipt(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, RecursionError):
        return {}
    return value if isinstance(value, dict) else {}


def record_receipt(path: Path, value: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_cached(path, json.dumps(value).encode("utf-8") + b"\n")
    except OSError:
        pass  # the guidance and version notice also work with a read-only cache


def install_source(module: Path, prefix: Path) -> tuple[str, str | None]:
    """Identify the running copy, using manager receipts before pip's INSTALLER marker."""
    if (module.parent / "scripts" / "pdfmd").is_file() and (module.parent / "pyproject.toml").is_file():
        return "checkout", "Update the source checkout you run pdfmd from."

    from csv import Error as CSVError
    from importlib.metadata import PackageNotFoundError, distribution

    unknown = "unknown", None
    try:
        dist = distribution(DISTRIBUTION)
        if (not module.is_file() or Path(dist.locate_file("pdfmd.py")).resolve() != module
                or not any(file.as_posix() == "pdfmd.py" for file in (dist.files or ()))):
            return unknown  # metadata for another copy on sys.path is not evidence about this one
        installer = (dist.read_text("INSTALLER") or "").strip()
    except (PackageNotFoundError, OSError, UnicodeError, RuntimeError, CSVError):
        return unknown

    if module.is_relative_to(prefix):
        # Homebrew and Scoop both run pip in their own venvs. A missing receipt in
        # their app layouts leaves the owner unknown, even if INSTALLER says pip.
        app = prefix.parent
        if prefix.name == "libexec" and app.parent.name == "pdfmd" and app.parent.parent.name == "Cellar":
            source = read_receipt(app / "INSTALL_RECEIPT.json").get("source")
            if isinstance(source, dict) and source.get("path"):
                return "Homebrew", UPGRADE_COMMANDS["Homebrew"]
            return unknown
        if prefix.name == "venv" and app.parent.name == "pdfmd" and app.parent.parent.name == "apps":
            receipt = read_receipt(app / "install.json")
            entry = read_receipt(app / "manifest.json").get("bin")
            if (("bucket" in receipt or "url" in receipt) and isinstance(entry, str)
                    and PureWindowsPath(entry) == PureWindowsPath("venv/Scripts/pdfmd.exe")):
                command = UPGRADE_COMMANDS["Scoop"]
                program_data = os.environ.get("ProgramData")
                global_root = os.environ.get("SCOOP_GLOBAL") or (Path(program_data) / "scoop" if program_data else None)
                if global_root and app.parent.parent.parent == Path(global_root).resolve():
                    command += " --global"
                return "Scoop", command
            return unknown
        pipx_receipt = prefix / "pipx_metadata.json"
        if os.path.lexists(pipx_receipt):
            main = read_receipt(pipx_receipt).get("main_package")
            if (isinstance(main, dict) and main.get("package") == DISTRIBUTION
                    and prefix.name == DISTRIBUTION + str(main.get("suffix") or "")
                    and re.fullmatch(r"pdfmd-cli[a-zA-Z0-9._-]*", prefix.name)):
                return "pipx", f"pipx upgrade {prefix.name}"
            return unknown
        pipx_home = os.environ.get("PIPX_HOME")
        if prefix.parent.name == "venvs" and (prefix.parent.parent.name == "pipx" or
                (pipx_home and prefix.parent.parent == Path(pipx_home).expanduser().resolve())):
            return unknown

    if installer == "pip":
        return "pip", UPGRADE_COMMANDS["pip"]
    return unknown


def upgrade_command() -> None:
    try:
        module, prefix = Path(core.__file__).resolve(), Path(sys.prefix).resolve()
        source, command = install_source(module, prefix)
    except (OSError, RuntimeError, UnicodeError):
        source, command = "unknown", None
    else:
        try:
            key = core.sha256_text(json.dumps([str(module), str(prefix)]))
            record_receipt(core.cache_root() / "install-sources" / f"{key}.json",
                           {"source": source, "version": core.PDFMD_VERSION})
        except (OSError, RuntimeError):
            pass
    if source == "checkout":
        print(f"Install source: checkout\n{command}")
    elif command:
        print(f"Install source: {source}\nRun: {command}")
    else:
        print("Install source unknown. Use the command for the manager you installed pdfmd with:")
        for manager, guidance in UPGRADE_COMMANDS.items():
            print(f"  {manager}: {guidance}")
    if source in ("pip", "unknown"):
        print("For pip, use the Python environment that runs this copy of pdfmd.")


def version_key(value) -> tuple[int, ...]:
    if isinstance(value, str) and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value):
        try:
            return tuple(map(int, value.split(".")))
        except ValueError:
            pass
    return ()


def cache_hours(value) -> int:
    text = str(value).strip()
    try:
        if text.isdecimal() and (hours := int(text)) > 0:
            return hours
    except ValueError:
        pass
    return VERSION_CACHE_HOURS


def latest_version(hours: int) -> str | None:
    try:
        path = core.cache_root() / "pypi-version.json"
    except (OSError, RuntimeError):
        path = None
    if path is not None and (cached := fresh_version(path, hours)) is not None:
        return cached

    from http.client import HTTPException
    from urllib.request import Request

    request = Request(f"https://pypi.org/pypi/{DISTRIBUTION}/json",
                      headers={"User-Agent": f"pdfmd/{core.PDFMD_VERSION}"})
    try:
        with core.open_url(request, core.PROBE_TIMEOUT) as response:
            latest = json.load(response)["info"]["version"]
    except (OSError, HTTPException, ValueError, KeyError, TypeError, RecursionError):
        return None
    if not version_key(latest):
        return None
    if path is not None:
        record_receipt(path, {"version": latest})
    return latest


def fresh_version(path: Path, hours: int) -> str | None:
    """Read a recent successful release check."""
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        return None
    if 0 <= age < hours * 3600:
        cached = read_receipt(path).get("version")
        if version_key(cached):
            return cached
    return None


def report_newer_version(hours) -> None:
    latest = latest_version(cache_hours(hours))
    if latest and version_key(latest) > version_key(core.PDFMD_VERSION):
        print(f"pdfmd {latest} is available on PyPI. See pdfmd --upgrade for guidance.", file=sys.stderr)
