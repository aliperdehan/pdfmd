#!/usr/bin/env python3
"""Regenerate pdfmd_inkmd/, the vendored copy of inkmd, from an upstream wheel.

    python3 scripts/vendor_inkmd.py                  # re-vendor INKMD_VERSION
    python3 scripts/vendor_inkmd.py --version 0.5.1  # move to another release
    python3 scripts/vendor_inkmd.py --wheel PATH     # use a local wheel (offline)
    python3 scripts/vendor_inkmd.py --check          # fail if pdfmd_inkmd/ has drifted

pdfmd_inkmd/ is generated, never hand-edited. The only differences from the
upstream wheel are the ones made below: the package is renamed (so it can sit
beside a separately installed `inkmd`), the CLI entry points are dropped, and
the ~10 MB colour-emoji font is left out (inkmd falls back to `[rocket]`-style
labels without it; `pdfmd-cli[emoji]` supplies the font from the real `inkmd`
package at run time). inkmd is MIT-licensed; its LICENSE is copied alongside.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

INKMD_VERSION = "0.5.0"
PACKAGE = "pdfmd_inkmd"
REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET = REPO_ROOT / PACKAGE

# Upstream modules we do not ship: the command-line front end (pdfmd has its
# own) and `python -m inkmd`.
DROP_MODULES = {"cli.py", "__main__.py"}
# Assets we keep: the text font for non-Latin scripts. The emoji font is the
# one deliberate omission.
KEEP_ASSET_DIRS = {"fonts"}

IMPORT_RE = re.compile(r"^(\s*)(from|import)(\s+)inkmd\b", re.MULTILINE)


def fetch_wheel(version: str) -> tuple[bytes, str]:
    """Download inkmd's wheel from PyPI, verified against PyPI's own digest."""
    with urllib.request.urlopen(f"https://pypi.org/pypi/inkmd/{version}/json", timeout=60) as response:
        release = json.load(response)
    wheels = [entry for entry in release["urls"] if entry["packagetype"] == "bdist_wheel"]
    if not wheels:
        raise SystemExit(f"inkmd {version} has no wheel on PyPI")
    entry = wheels[0]
    with urllib.request.urlopen(entry["url"], timeout=120) as response:
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != entry["digests"]["sha256"]:
        raise SystemExit(f"SHA-256 mismatch for {entry['filename']}: got {digest}")
    return data, digest


def read_files(wheel: bytes) -> dict[str, bytes]:
    """Return {path inside the package: bytes} for what we vendor, plus LICENSE."""
    files: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(wheel)) as archive:
        for name in sorted(archive.namelist()):
            parts = name.split("/")
            if ".." in parts or name.startswith("/"):
                raise SystemExit(f"Unsafe path in wheel: {name}")
            if parts[0] == "inkmd" and len(parts) >= 2 and not name.endswith("/"):
                relative = "/".join(parts[1:])
                if parts[1] == "assets" and (len(parts) < 3 or parts[2] not in KEEP_ASSET_DIRS):
                    continue
                if relative in DROP_MODULES:
                    continue
                files[relative] = archive.read(name)
            elif name.endswith(".dist-info/licenses/LICENSE"):
                files["LICENSE"] = archive.read(name)
    if "__init__.py" not in files or "LICENSE" not in files:
        raise SystemExit("Wheel is missing inkmd/__init__.py or its LICENSE")
    return files


def transform(relative: str, data: bytes) -> bytes:
    """Rename inkmd's own imports; leave everything else byte-for-byte."""
    if not relative.endswith(".py"):
        return data
    text = data.decode("utf-8")
    return IMPORT_RE.sub(rf"\1\2\3{PACKAGE}", text).encode("utf-8")


def provenance(version: str, digest: str) -> bytes:
    return (
        f"# Vendored inkmd\n\n"
        f"This directory is a generated copy of inkmd {version} "
        f"(https://github.com/eagredev/inkmd, MIT licence, see LICENSE).\n\n"
        f"- Upstream wheel: `inkmd-{version}-py3-none-any.whl`, SHA-256 `{digest}`\n"
        f"- Regenerate with `python3 scripts/vendor_inkmd.py`; never edit by hand.\n\n"
        f"Differences from upstream, all made by that script:\n\n"
        f"- the package is renamed from `inkmd` to `{PACKAGE}` (imports rewritten), so it\n"
        f"  cannot clash with a separately installed `inkmd`;\n"
        f"- `cli.py` and `__main__.py` are dropped;\n"
        f"- `assets/emoji/` (Noto Color Emoji, about 10 MB) is not shipped. Without it\n"
        f"  inkmd renders emoji as `[rocket]`-style labels. `pdfmd-cli[emoji]` installs the\n"
        f"  real `inkmd` package and pdfmd points this copy at its font.\n\n"
        f"Bundled text font: DejaVu Sans, see `assets/fonts/DejaVuSans-LICENSE.txt`.\n"
    ).encode("utf-8")


def build(version: str, wheel: bytes, digest: str) -> dict[str, bytes]:
    out = {relative: transform(relative, data) for relative, data in read_files(wheel).items()}
    out["VENDORED.md"] = provenance(version, digest)
    return out


def current_tree() -> dict[str, bytes]:
    if not TARGET.is_dir():
        return {}
    return {
        str(path.relative_to(TARGET)).replace("\\", "/"): path.read_bytes()
        for path in sorted(TARGET.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--version", default=INKMD_VERSION, help=f"inkmd release (default {INKMD_VERSION})")
    parser.add_argument("--wheel", type=Path, help="use this local wheel instead of downloading")
    parser.add_argument("--check", action="store_true", help="verify pdfmd_inkmd/ matches upstream; change nothing")
    args = parser.parse_args()

    if args.wheel:
        wheel = args.wheel.read_bytes()
        digest = hashlib.sha256(wheel).hexdigest()
    else:
        wheel, digest = fetch_wheel(args.version)
    expected = build(args.version, wheel, digest)

    if args.check:
        actual = current_tree()
        problems = [f"missing {name}" for name in expected if name not in actual]
        problems += [f"unexpected {name}" for name in actual if name not in expected]
        problems += [f"modified {name}" for name in expected if name in actual and actual[name] != expected[name]]
        if problems:
            print(f"{PACKAGE}/ differs from inkmd {args.version}:", *problems, sep="\n  ", file=sys.stderr)
            return 1
        print(f"{PACKAGE}/ matches inkmd {args.version}")
        return 0

    if TARGET.exists():
        shutil.rmtree(TARGET)
    for relative, data in expected.items():
        destination = TARGET / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    print(f"Vendored inkmd {args.version} into {PACKAGE}/ ({len(expected)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
