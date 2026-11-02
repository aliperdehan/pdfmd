#!/usr/bin/env python3
"""Point bucket/pdfmd.json (the Scoop manifest) at a pdfmd-cli release on PyPI: only its `version` changes (the install script
asks pip for exactly that version).

    python3 scripts/bump_scoop.py [VERSION] [--tries N] [--wait SECONDS]

Without a VERSION it takes PyPI's newest. Prints the version the manifest now names, and `unchanged` as a second word when it
already named it. Like bump_formula.py, which it shares the PyPI lookup with, it asks again for a release PyPI does not list yet.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bump_formula import fetch  # noqa: E402

MANIFEST = Path(__file__).resolve().parent.parent / "bucket" / "pdfmd.json"


def rewrite(text: str, version: str) -> str:
    """The manifest's text with its `version` replaced (same order of keys, four-space indent, a newline at the end)."""
    manifest = json.loads(text)
    manifest["version"] = version
    return json.dumps(manifest, indent=4, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("version", nargs="?", help="a pdfmd-cli version (default: PyPI's newest)")
    parser.add_argument("--tries", type=int, default=12, help="how often to ask PyPI for a release that is not listed yet")
    parser.add_argument("--wait", type=float, default=10.0, help="seconds between two asks")
    args = parser.parse_args(argv)
    data = fetch(args.version, args.tries, args.wait)
    before = MANIFEST.read_text(encoding="utf-8")
    after = rewrite(before, data["info"]["version"])
    MANIFEST.write_text(after, encoding="utf-8")
    print(data["info"]["version"], "unchanged" if after == before else "changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
